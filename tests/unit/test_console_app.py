"""C4 — console WIRING + END-TO-END integration with fakes (Inc-8 PART B).

Proves the whole two-way console works as one: getUpdates -> auth -> sanitize -> deterministic
dispatch -> (kill_switch escalate | grounded Q&A) -> outbound reply. All faked (no network,
no LLM, no real broker); the live round-trip is a separate ``@pytest.mark.live`` smoke.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from trading.console.app import (
    build_console_deps,
    build_poller,
    make_telegram_fetcher,
)
from trading.notify.telegram import TelegramNotifier

_OP = "123456789"
_TOKEN = "111:fake-bot-token"


class _FakeKill:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self._state = "ARMED"

    def trip(self, reason: str) -> object:
        self.calls.append(("trip", reason))
        self._state = "TRIPPED"
        return self._state

    def hard_stop(self, reason: str) -> object:
        self.calls.append(("hard_stop", reason))
        self._state = "HARD_STOPPED"
        return self._state

    def read(self) -> object:
        return self._state

    def reason(self) -> str:
        return "test-reason"


def _spy_notifier() -> tuple[TelegramNotifier, list[str]]:
    sent: list[str] = []

    def sender(url: str, body: dict[str, str]) -> None:
        sent.append(body["text"])

    return TelegramNotifier(_TOKEN, _OP, sender=sender), sent


def _msg(uid: int, text: str) -> dict[str, object]:
    return {
        "update_id": uid,
        "message": {"chat": {"id": int(_OP), "type": "private"}, "text": text},
    }


def test_make_telegram_fetcher_passes_offset_and_returns_only_dict_updates() -> None:
    captured: dict[str, Any] = {}

    def http_get(url: str, params: dict[str, int]) -> dict[str, Any]:
        captured["url"] = url
        captured["params"] = params
        return {"result": [_msg(5, "hej"), "garbage-not-a-dict"]}

    fetch = make_telegram_fetcher(_TOKEN, http_get=http_get)
    updates = fetch(42)
    assert captured["params"]["offset"] == 42
    assert captured["params"]["timeout"] == 25
    assert _TOKEN in captured["url"]  # the token lives only in this (non-logged) URL
    assert len(updates) == 1 and updates[0]["update_id"] == 5  # the non-dict update is filtered out


def test_make_telegram_fetcher_omits_offset_on_cold_start() -> None:
    captured: dict[str, Any] = {}

    def http_get(url: str, params: dict[str, int]) -> dict[str, Any]:
        captured["params"] = params
        return {"result": []}

    make_telegram_fetcher(_TOKEN, http_get=http_get)(None)
    assert "offset" not in captured["params"]


def test_end_to_end_status_and_grounded_qa(tmp_path: Path) -> None:
    notifier, sent = _spy_notifier()
    kill = _FakeKill()

    def fake_responder(system: str, user: str) -> str:
        # grounded: the briefing (RECORD-ONLY) must be present in what the model is asked
        assert "RECORD-ONLY" in user
        return "Det går bra — 0 trades, allt record-only."

    deps = build_console_deps(
        notifier=notifier,
        kill_switch=kill,
        responder=fake_responder,
        news_path=tmp_path / "news_state.json",
        regime_advisory_path=tmp_path / "regime_advisory.json",
        now_provider=lambda: datetime(2026, 6, 26, 14, 0, tzinfo=UTC),
    )

    offset_path = tmp_path / "console_offset.json"
    offset_path.write_text(json.dumps({"offset": 0}), encoding="utf-8")
    fetch = lambda _offset: [_msg(0, "/status"), _msg(1, "hur går det?")]  # noqa: E731
    poller = build_poller(
        token=_TOKEN, operator_chat_id=_OP, deps=deps, offset_path=offset_path, fetch_updates=fetch
    )

    handled = poller.poll_once()
    assert handled == 2
    assert any("RECORD-ONLY" in s or "ARMED" in s for s in sent)  # the /status read
    assert any("Det går bra" in s for s in sent)  # the grounded Q&A reply
    assert kill.calls == []  # neither /status nor a question touched the kill switch


def test_default_now_provider_is_used_when_not_injected(tmp_path: Path) -> None:
    # Exercises the real default clock (_utc_now): a read command gathers a briefing using it.
    notifier, _ = _spy_notifier()
    deps = build_console_deps(
        notifier=notifier,
        kill_switch=_FakeKill(),
        responder=lambda s, u: "unused",
        news_path=tmp_path / "n.json",
        regime_advisory_path=tmp_path / "r.json",
    )
    text = deps.reads["/nyheter"]()  # -> gather_briefing(now=_utc_now())
    assert "Nyheter" in text


def test_end_to_end_pausa_trips_the_kill_switch(tmp_path: Path) -> None:
    notifier, sent = _spy_notifier()
    kill = _FakeKill()
    deps = build_console_deps(
        notifier=notifier,
        kill_switch=kill,
        responder=lambda s, u: "unused",
        news_path=tmp_path / "n.json",
        regime_advisory_path=tmp_path / "r.json",
    )
    offset_path = tmp_path / "console_offset.json"
    offset_path.write_text(json.dumps({"offset": 0}), encoding="utf-8")
    poller = build_poller(
        token=_TOKEN,
        operator_chat_id=_OP,
        deps=deps,
        offset_path=offset_path,
        fetch_updates=lambda _o: [_msg(0, "/pausa")],
    )
    poller.poll_once()
    assert kill.calls == [("trip", "operator /pausa via console")]
    assert len(sent) == 1


def test_end_to_end_trade_order_is_refused_without_responder_or_kill_switch(tmp_path: Path) -> None:
    notifier, sent = _spy_notifier()
    kill = _FakeKill()
    answered: list[str] = []
    deps = build_console_deps(
        notifier=notifier,
        kill_switch=kill,
        responder=lambda s, u: answered.append(u) or "should not be called",  # type: ignore[func-returns-value]
        news_path=tmp_path / "n.json",
        regime_advisory_path=tmp_path / "r.json",
    )
    offset_path = tmp_path / "console_offset.json"
    offset_path.write_text(json.dumps({"offset": 0}), encoding="utf-8")
    poller = build_poller(
        token=_TOKEN,
        operator_chat_id=_OP,
        deps=deps,
        offset_path=offset_path,
        fetch_updates=lambda _o: [_msg(0, "köp 100 AAPL nu")],
    )
    poller.poll_once()
    assert kill.calls == []
    assert answered == []  # the trade order never reached the LLM
    assert (
        len(sent) == 1 and "gate" in sent[0].lower()
    )  # deterministic refusal naming the gate path
