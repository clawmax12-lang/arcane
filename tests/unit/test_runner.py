"""Tests for the no-op paper executor (Increment 1 safety spine).

Proves the end-to-end path: an accepted intent is gated and its idempotency key
recorded, but nothing is ever submitted; a rejected intent stops at its gate.
"""

from __future__ import annotations

from pathlib import Path

from trading.executor.idempotency import InMemoryIdempotencyStore, client_order_id
from trading.executor.intent import OrderIntent
from trading.executor.invariants import AccountSnapshot
from trading.executor.kill_switch import KillSwitch
from trading.executor.runner import execute_paper
from trading.risk.schema import RiskConfig

CFG = RiskConfig(
    live_mode=False,
    per_trade_risk_usd=1.0,
    max_daily_loss_usd=5.0,
    equity_floor_usd=20.0,
    total_loss_abandon_usd=30.0,
    max_position_concentration_pct=30.0,
    max_consecutive_errors=5,
)
INTENT = OrderIntent(
    strategy_id="orb",
    symbol="AAPL",
    side="buy",
    qty=1.0,
    intended_risk_usd=1.0,
    est_position_value_usd=10.0,
)
SNAP = AccountSnapshot(
    equity_usd=50.0,
    realized_daily_loss_usd=0.0,
    cumulative_loss_usd=0.0,
    data_as_of_epoch=1_000.0,
    now_epoch=1_000.0,
)


def test_accepted_intent_is_recorded_but_not_submitted(tmp_path: Path) -> None:
    ks = KillSwitch(tmp_path / "ks.json")
    store = InMemoryIdempotencyStore()
    result = execute_paper(INTENT, SNAP, CFG, ks, store)
    assert result.decision.accepted is True
    assert result.submitted is False  # no-op in Increment 1
    assert store.seen(client_order_id(INTENT)) is True  # idempotency key claimed


def test_rejected_intent_stops_at_gate(tmp_path: Path) -> None:
    ks = KillSwitch(tmp_path / "ks.json")
    ks.trip("orange")
    store = InMemoryIdempotencyStore()
    result = execute_paper(INTENT, SNAP, CFG, ks, store)
    assert result.submitted is False
    assert result.decision.accepted is False
    assert result.decision.failed_gate == "kill_switch"
    # A rejected order must NOT consume the idempotency key.
    assert store.seen(client_order_id(INTENT)) is False


def test_replayed_intent_rejected_by_idempotency(tmp_path: Path) -> None:
    ks = KillSwitch(tmp_path / "ks.json")
    store = InMemoryIdempotencyStore()
    first = execute_paper(INTENT, SNAP, CFG, ks, store)
    assert first.decision.accepted is True
    # Same intent again -> idempotency gate rejects the duplicate.
    second = execute_paper(INTENT, SNAP, CFG, ks, store)
    assert second.decision.accepted is False
    assert second.decision.failed_gate == "idempotency"
