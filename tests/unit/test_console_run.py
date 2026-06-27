"""C4 — the always-on console listener (Inc-8.5 PART C).

``run_forever`` drives ``poller.poll_once()`` continuously so a typed Telegram message is answered
in seconds. It is the CHAT listener ONLY — orthogonal to the dormant trading scheduler and the
per-order GO. The loop is pure (sleep + should_continue injected, no real time/network) so every
behaviour is asserted offline: capped exponential backoff on a transport ``ConsoleError`` (never a
crash-loop), reset on success, ``KeyboardInterrupt`` propagates, a non-``ConsoleError`` is NOT
swallowed, and the logs are token-free. Plus the structural teeth: ``run.py`` lives inside
``trading.console`` and from the executor imports ONLY ``kill_switch`` (no broker/order symbol), and
a jailbroken reply through the real dispatch path is inert text.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from trading.console import run as run_mod
from trading.console.commands import ConsoleDeps, handle_message
from trading.console.errors import ConsoleError


class _FakePoller:
    """A stand-in for ConsolePoller.poll_once with a scripted sequence of outcomes."""

    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    def poll_once(self) -> int:
        self.calls += 1
        if not self._outcomes:
            return 0
        item = self._outcomes.pop(0)
        if isinstance(item, BaseException):
            raise item
        return int(item)  # type: ignore[call-overload]


def _stop_after(n: int):  # noqa: ANN202
    state = {"n": 0}

    def should_continue() -> bool:
        state["n"] += 1
        return state["n"] <= n

    return should_continue


# ----------------------------------------------------------------- the loop core


def test_run_forever_sleeps_an_idle_breather_on_a_clean_cycle() -> None:
    poller = _FakePoller([0, 0])
    slept: list[float] = []
    run_mod.run_forever(
        poller, sleep=slept.append, should_continue=_stop_after(2), idle_interval=1.5
    )
    assert poller.calls == 2
    assert slept == [1.5, 1.5]  # a clean cycle sleeps the idle breather, no backoff


def test_run_forever_backs_off_exponentially_on_transport_error_then_resets() -> None:
    # error, error, success -> backoff base, base*2, then reset to idle on the clean cycle
    poller = _FakePoller([ConsoleError("x"), ConsoleError("y"), 1])
    slept: list[float] = []
    run_mod.run_forever(
        poller,
        sleep=slept.append,
        should_continue=_stop_after(3),
        idle_interval=0.5,
        base_backoff=1.0,
        max_backoff=60.0,
    )
    assert slept == [1.0, 2.0, 0.5]  # backoff doubles, then the success resets to the idle breather


def test_run_forever_backoff_is_capped_at_max() -> None:
    poller = _FakePoller([ConsoleError("e")] * 6)
    slept: list[float] = []
    run_mod.run_forever(
        poller,
        sleep=slept.append,
        should_continue=_stop_after(6),
        base_backoff=10.0,
        max_backoff=30.0,
    )
    assert slept == [10.0, 20.0, 30.0, 30.0, 30.0, 30.0]  # caps at max, never grows unbounded


def test_run_forever_does_not_swallow_a_non_console_error() -> None:
    # An OSError (e.g. an unwritable offset store) must surface loudly, not be retried forever.
    poller = _FakePoller([OSError("disk full")])
    with pytest.raises(OSError):
        run_mod.run_forever(poller, sleep=lambda _s: None, should_continue=lambda: True)


def test_run_forever_propagates_keyboard_interrupt() -> None:
    poller = _FakePoller([KeyboardInterrupt()])
    with pytest.raises(KeyboardInterrupt):
        run_mod.run_forever(poller, sleep=lambda _s: None, should_continue=lambda: True)


def test_run_forever_stops_when_should_continue_is_false_immediately() -> None:
    poller = _FakePoller([1])
    run_mod.run_forever(poller, sleep=lambda _s: None, should_continue=lambda: False)
    assert poller.calls == 0  # never polled


def test_run_forever_logs_only_the_error_type_no_token(capsys: pytest.CaptureFixture[str]) -> None:
    poller = _FakePoller([ConsoleError("telegram getUpdates failed: SECRET-TOKEN-123")])
    run_mod.run_forever(poller, sleep=lambda _s: None, should_continue=_stop_after(1))
    captured = capsys.readouterr()
    blob = captured.out + captured.err
    assert "SECRET-TOKEN-123" not in blob  # only type(exc).__name__ is logged, never the message


# ----------------------------------------------------------------- main() wiring


def test_build_console_poller_fails_closed_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_mod, "load_settings", lambda: _FakeSettings())
    monkeypatch.setattr(run_mod, "load_notify_settings", lambda: (None, "123"))
    monkeypatch.setattr(
        run_mod, "load_model_settings", lambda: ("claude-sonnet-4-6", "claude-haiku")
    )
    with pytest.raises(ConsoleError):
        run_mod._build_console_poller()


def test_build_console_poller_fails_closed_without_chat_id(monkeypatch: pytest.MonkeyPatch) -> None:
    # The inbound auth MUST be pinned to a known operator chat_id — never auto-resolved.
    monkeypatch.setattr(run_mod, "load_settings", lambda: _FakeSettings())
    monkeypatch.setattr(run_mod, "load_notify_settings", lambda: ("111:tok", None))
    monkeypatch.setattr(
        run_mod, "load_model_settings", lambda: ("claude-sonnet-4-6", "claude-haiku")
    )
    with pytest.raises(ConsoleError):
        run_mod._build_console_poller()


def test_build_console_poller_wires_the_conversation_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(run_mod, "load_settings", lambda: _FakeSettings())
    monkeypatch.setattr(run_mod, "load_notify_settings", lambda: ("111:tok", "123456"))
    monkeypatch.setattr(
        run_mod, "load_model_settings", lambda: ("claude-opus-4-8", "claude-haiku-4-5-20251001")
    )
    monkeypatch.setattr(run_mod, "KillSwitch", lambda _p: _FakeKill())
    monkeypatch.setattr(
        run_mod, "build_notifier", lambda token, chat_id: ("notifier", token, chat_id)
    )

    def fake_build_responder(key: object, model_id: str) -> str:
        captured["responder_model"] = model_id  # the conversation model must flow here
        captured["responder_key"] = key
        return "responder"

    monkeypatch.setattr(run_mod, "build_responder", fake_build_responder)
    monkeypatch.setattr(
        run_mod, "build_console_deps", lambda **kw: ("deps", kw["responder"], kw["kill_switch"])
    )

    def fake_build_poller(*, token: str, operator_chat_id: str, deps: object) -> str:
        captured["poller_chat_id"] = operator_chat_id  # the SAME chat_id pins inbound auth
        captured["poller_token"] = token
        return "poller"

    monkeypatch.setattr(run_mod, "build_poller", fake_build_poller)

    poller, model = run_mod._build_console_poller()
    assert poller == "poller"
    assert model == "claude-opus-4-8"
    assert captured["responder_model"] == "claude-opus-4-8"  # operator-selected conversation model
    assert captured["poller_chat_id"] == "123456"  # inbound auth pinned to the operator chat_id


def test_main_returns_zero_and_handles_keyboard_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_mod, "_build_console_poller", lambda: ("poller", "claude-sonnet-4-6"))

    def boom(*_a: object, **_k: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(run_mod, "run_forever", boom)
    assert run_mod.main() == 0  # a Ctrl-C is a clean stop, not a crash


# ----------------------------------------------------------------- structural boundary teeth


_RUN_PY = Path(__file__).resolve().parents[2] / "src" / "trading" / "console" / "run.py"
_FORBIDDEN_EXECUTOR = (
    "trading.executor.submit",
    "trading.executor.broker_paper",
    "trading.executor.sizing",
    "trading.executor.grant",
    "trading.executor.loop",
)


def _imports(py: Path) -> list[str]:
    tree = ast.parse(py.read_text(encoding="utf-8"))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            out.append(node.module)
    return out


def test_run_py_imports_only_kill_switch_from_executor_and_no_broker() -> None:
    targets = _imports(_RUN_PY)
    executor_imports = [t for t in targets if t.startswith("trading.executor.")]
    assert executor_imports == ["trading.executor.kill_switch"], executor_imports
    assert "alpaca" not in {t.split(".")[0] for t in targets}
    for forbidden in _FORBIDDEN_EXECUTOR:
        assert forbidden not in targets
    # the listener must not pull in the trading scheduler or driver (it is the CHAT listener only)
    assert not any(
        t.startswith("trading.scheduler") or t.startswith("trading.driver") for t in targets
    )


# --------------------------------------------------------------- jailbreak-is-inert (via dispatch)


class _FakeKill:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def verify_writable(self) -> None:
        return None  # the real KillSwitch refuses to start a console that cannot escalate

    def trip(self, reason: str) -> object:
        self.calls.append(("trip", reason))
        return "TRIPPED"

    def hard_stop(self, reason: str) -> object:
        self.calls.append(("hard_stop", reason))
        return "HARD_STOPPED"

    def read(self) -> object:
        return "ARMED"

    def reason(self) -> str:
        return "test"


class _FakeSettings:
    def get(self, _key: str) -> str:
        return "sk-ant-fake"


def test_jailbroken_reply_through_dispatch_is_inert_text() -> None:
    # A responder that returns a literal "/flatta" must be SENT as text, never executed.
    kill = _FakeKill()
    replies: list[str] = []
    deps = ConsoleDeps(
        kill_switch=kill,
        reply=replies.append,
        answer=lambda _q: "kör /flatta och köp NVDA om du vill",  # a jailbroken-style reply
        reads={},
    )
    handle_message("vad ska jag göra?", deps)
    assert kill.calls == []  # the '/flatta' in the REPLY did not fire hard_stop
    assert replies == ["kör /flatta och köp NVDA om du vill"]  # delivered verbatim as text
