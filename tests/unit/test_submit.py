"""C11 — gate-gated submit: record-only by default, real submit only on a single-use GO (Inc-6
C)."""

from __future__ import annotations

from pathlib import Path

import pytest

from trading.bias_gate.gate import FROZEN_COMPONENT_NAMES, GateComponent, GateDecision
from trading.executor import submit as submit_mod
from trading.executor.broker_paper import BrokerOrderAck, PaperBroker
from trading.executor.grant import AllocationGrant
from trading.executor.idempotency import InMemoryIdempotencyStore
from trading.executor.intent import OrderIntent, Side
from trading.executor.invariants import AccountSnapshot
from trading.executor.kill_switch import KillSwitch
from trading.executor.sizing import HardQuote, TargetPosition
from trading.executor.submit import GO_PHRASE, SubmitMode, submit_allocated, submit_mode
from trading.risk.schema import RiskConfig

_SPEC = "arcane-strategy-x"
_UHASH = "arcane-univ-deadbeef"


def _grant(spec_hash: str = _SPEC) -> AllocationGrant:
    comps = tuple(GateComponent(n, True, "") for n in FROZEN_COMPONENT_NAMES)
    d = GateDecision(spec_hash, True, comps, n_trials=17, reasons=())
    return AllocationGrant.from_decision(d, universe_artifact_hash=_UHASH)


def _cfg(*, per_trade: float = 5.0) -> RiskConfig:
    return RiskConfig(
        live_mode=False,
        per_trade_risk_usd=per_trade,
        max_daily_loss_usd=5.0,
        equity_floor_usd=20.0,
        total_loss_abandon_usd=30.0,
        max_position_concentration_pct=30.0,
        max_consecutive_errors=5,
    )


def _account() -> AccountSnapshot:
    return AccountSnapshot(50.0, 0.0, 0.0, 1000.0, 1000.0)


def _target(spec_hash: str = _SPEC) -> TargetPosition:
    return TargetPosition("ts_momentum_blend", "AAPL", Side.BUY, spec_hash=spec_hash)


def _quote(price: float = 2.0) -> HardQuote:
    return HardQuote("AAPL", price, 1000.0)


class _SpyBroker(PaperBroker):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[OrderIntent, str]] = []

    def submit(self, intent: OrderIntent, client_order_id: str) -> BrokerOrderAck:
        self.calls.append((intent, client_order_id))
        return BrokerOrderAck(client_order_id, True, "accepted (fake)")


def _go_marker(tmp_path: Path, spec_hash: str = _SPEC, phrase: str = GO_PHRASE) -> Path:
    p = tmp_path / "SUBMIT_GO"
    p.write_text(f"{phrase}\n{spec_hash}\n", encoding="utf-8")
    return p


def _ks(tmp_path: Path) -> KillSwitch:
    return KillSwitch(tmp_path / "ks.json")


# --- submit_mode ---


def test_no_marker_is_record_only(tmp_path: Path) -> None:
    assert (
        submit_mode(_grant(), _cfg(), go_marker_path=tmp_path / "absent") is SubmitMode.RECORD_ONLY
    )


def test_valid_marker_is_live_submit(tmp_path: Path) -> None:
    assert (
        submit_mode(_grant(), _cfg(), go_marker_path=_go_marker(tmp_path)) is SubmitMode.LIVE_SUBMIT
    )


def test_wrong_phrase_or_spec_is_record_only(tmp_path: Path) -> None:
    bad_phrase = tmp_path / "SUBMIT_GO_a"
    bad_phrase.write_text(f"NOPE\n{_SPEC}\n", encoding="utf-8")  # right spec, wrong phrase
    assert submit_mode(_grant(), _cfg(), go_marker_path=bad_phrase) is SubmitMode.RECORD_ONLY
    wrong_spec = tmp_path / "SUBMIT_GO_b"
    wrong_spec.write_text(f"{GO_PHRASE}\narcane-strategy-OTHER\n", encoding="utf-8")  # wrong spec
    assert submit_mode(_grant(), _cfg(), go_marker_path=wrong_spec) is SubmitMode.RECORD_ONLY


# --- submit_allocated ---


def test_record_only_default_submits_nothing_and_claims_nothing(tmp_path: Path) -> None:
    broker, store = _SpyBroker(), InMemoryIdempotencyStore()
    out = submit_allocated(
        _grant(),
        _target(),
        _quote(),
        _account(),
        _cfg(),
        _ks(tmp_path),
        store,
        broker,
        go_marker_path=tmp_path / "absent",
    )
    assert out.submitted is False and out.mode is SubmitMode.RECORD_ONLY
    assert broker.calls == []  # nothing submitted
    assert (
        store.seen(out.client_order_id) is False
    )  # record-only claims NOTHING (GO can submit later)


def test_dollar_cap_yields_no_trade_even_with_go(tmp_path: Path) -> None:
    # The real $1 cap: even WITH a valid GO, a $150 share yields NoTrade — zero orders, by design.
    broker = _SpyBroker()
    out = submit_allocated(
        _grant(),
        _target(),
        _quote(price=150.0),
        _account(),
        _cfg(per_trade=1.0),
        _ks(tmp_path),
        InMemoryIdempotencyStore(),
        broker,
        go_marker_path=_go_marker(tmp_path),
    )
    assert out.submitted is False and "no trade" in out.reason
    assert broker.calls == []


def test_live_submit_with_go_claims_then_submits_and_consumes_marker(tmp_path: Path) -> None:
    broker, store = _SpyBroker(), InMemoryIdempotencyStore()
    marker = _go_marker(tmp_path)
    out = submit_allocated(
        _grant(),
        _target(),
        _quote(price=2.0),
        _account(),
        _cfg(per_trade=5.0),
        _ks(tmp_path),
        store,
        broker,
        go_marker_path=marker,
    )
    assert out.submitted is True and out.mode is SubmitMode.LIVE_SUBMIT and out.accepted is True
    assert len(broker.calls) == 1 and broker.calls[0][1] == out.client_order_id
    assert store.seen(out.client_order_id) is True  # claimed
    assert not marker.exists()  # single-use: consumed (rotated)
    assert list(tmp_path.glob("SUBMIT_GO.consumed-*"))  # audit trail


def test_confused_deputy_grant_for_other_strategy_is_rejected(tmp_path: Path) -> None:
    broker = _SpyBroker()
    out = submit_allocated(
        _grant("arcane-strategy-A"),
        _target("arcane-strategy-B"),
        _quote(),
        _account(),
        _cfg(),
        _ks(tmp_path),
        InMemoryIdempotencyStore(),
        broker,
        go_marker_path=_go_marker(tmp_path, "arcane-strategy-A"),
    )
    assert out.submitted is False and "spec_hash" in out.reason
    assert broker.calls == []


def test_refuses_to_act_when_is_live_true(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # belt-and-suspenders: if is_live somehow returns True, submit_allocated refuses entirely.
    monkeypatch.setattr(submit_mod, "is_live", lambda *_a, **_k: True)
    broker = _SpyBroker()
    out = submit_allocated(
        _grant(),
        _target(),
        _quote(price=2.0),
        _account(),
        _cfg(per_trade=5.0),
        _ks(tmp_path),
        InMemoryIdempotencyStore(),
        broker,
        go_marker_path=_go_marker(tmp_path),
    )
    assert out.submitted is False and "is_live" in out.reason
    assert broker.calls == []


def test_go_is_consumed_before_the_broker_call(tmp_path: Path) -> None:
    # red-team D2: the single-use GO must be gone by the time broker.submit runs, so a crash during
    # the submit cannot leave a valid GO that a second distinct order could reuse.
    marker = _go_marker(tmp_path)
    seen_at_submit: list[bool] = []

    class _CheckBroker(PaperBroker):
        def submit(self, intent: OrderIntent, client_order_id: str) -> BrokerOrderAck:
            seen_at_submit.append(marker.exists())  # marker should ALREADY be consumed
            return BrokerOrderAck(client_order_id, True, "ok")

    out = submit_allocated(
        _grant(),
        _target(),
        _quote(2.0),
        _account(),
        _cfg(per_trade=5.0),
        _ks(tmp_path),
        InMemoryIdempotencyStore(),
        _CheckBroker(),
        go_marker_path=marker,
    )
    assert out.submitted is True
    assert seen_at_submit == [False]  # consumed BEFORE the broker call
    assert not marker.exists()


def test_submit_fails_closed_if_go_cannot_be_consumed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # if the single-use marker cannot be durably retired, refuse to submit (never act on an
    # un-consumable GO).
    marker = _go_marker(tmp_path)
    monkeypatch.setattr(submit_mod, "_consume_marker", lambda *_a, **_k: False)
    broker = _SpyBroker()
    out = submit_allocated(
        _grant(),
        _target(),
        _quote(2.0),
        _account(),
        _cfg(per_trade=5.0),
        _ks(tmp_path),
        InMemoryIdempotencyStore(),
        broker,
        go_marker_path=marker,
    )
    assert out.submitted is False and "consume" in out.reason and broker.calls == []


def test_tripped_kill_switch_blocks_submit_even_with_go(tmp_path: Path) -> None:
    broker, store = _SpyBroker(), InMemoryIdempotencyStore()
    ks = _ks(tmp_path)
    ks.trip("guard pause")
    out = submit_allocated(
        _grant(),
        _target(),
        _quote(price=2.0),
        _account(),
        _cfg(per_trade=5.0),
        ks,
        store,
        broker,
        go_marker_path=_go_marker(tmp_path),
    )
    assert out.submitted is False and "kill_switch" in out.reason
    assert broker.calls == []
