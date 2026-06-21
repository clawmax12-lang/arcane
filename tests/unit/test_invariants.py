"""Tests for the pre-submit invariant chain (Increment 1 safety spine).

These prove the spine's reason for existing: a clean order passes, and every gate
rejects its violation. Ordering is asserted (earlier gates win) so a tripped kill
switch is reported even when a later cap is also violated.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from trading.executor.idempotency import InMemoryIdempotencyStore, client_order_id
from trading.executor.intent import OrderIntent
from trading.executor.invariants import AccountSnapshot, evaluate_pre_submit
from trading.executor.kill_switch import KillSwitch
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


def snapshot(**over: Any) -> AccountSnapshot:
    base: dict[str, Any] = {
        "equity_usd": 50.0,
        "realized_daily_loss_usd": 0.0,
        "cumulative_loss_usd": 0.0,
        "data_as_of_epoch": 1_000.0,
        "now_epoch": 1_000.0,
    }
    base.update(over)
    return AccountSnapshot(**base)


def armed_switch(tmp_path: Path) -> KillSwitch:
    return KillSwitch(tmp_path / "ks.json")


def test_clean_intent_accepted(tmp_path: Path) -> None:
    store = InMemoryIdempotencyStore()
    d = evaluate_pre_submit(INTENT, snapshot(), CFG, armed_switch(tmp_path), store.seen)
    assert d.accepted is True
    assert d.failed_gate is None
    assert d.client_order_id.startswith("arcane-")


def test_kill_switch_tripped_rejects(tmp_path: Path) -> None:
    ks = armed_switch(tmp_path)
    ks.trip("orange guard")
    d = evaluate_pre_submit(INTENT, snapshot(), CFG, ks, InMemoryIdempotencyStore().seen)
    assert d.accepted is False
    assert d.failed_gate == "kill_switch"


def test_kill_switch_checked_before_caps(tmp_path: Path) -> None:
    ks = armed_switch(tmp_path)
    ks.trip("x")
    over_cap = OrderIntent(
        strategy_id="orb",
        symbol="AAPL",
        side="buy",
        qty=1.0,
        intended_risk_usd=5.0,  # also violates the per-trade cap
        est_position_value_usd=10.0,
    )
    d = evaluate_pre_submit(over_cap, snapshot(), CFG, ks, InMemoryIdempotencyStore().seen)
    assert d.failed_gate == "kill_switch"  # earlier gate wins


def test_stale_data_rejected(tmp_path: Path) -> None:
    d = evaluate_pre_submit(
        INTENT,
        snapshot(data_as_of_epoch=0.0, now_epoch=1_000.0),
        CFG,
        armed_switch(tmp_path),
        InMemoryIdempotencyStore().seen,
    )
    assert d.failed_gate == "data_freshness"


def test_future_dated_data_rejected(tmp_path: Path) -> None:
    d = evaluate_pre_submit(
        INTENT,
        snapshot(data_as_of_epoch=2_000.0, now_epoch=1_000.0),
        CFG,
        armed_switch(tmp_path),
        InMemoryIdempotencyStore().seen,
    )
    assert d.failed_gate == "data_freshness"


def test_per_trade_cap_rejected(tmp_path: Path) -> None:
    over = OrderIntent(
        strategy_id="orb",
        symbol="AAPL",
        side="buy",
        qty=1.0,
        intended_risk_usd=5.0,
        est_position_value_usd=10.0,
    )
    d = evaluate_pre_submit(
        over, snapshot(), CFG, armed_switch(tmp_path), InMemoryIdempotencyStore().seen
    )
    assert d.failed_gate == "per_trade_cap"


def test_daily_loss_cap_rejected(tmp_path: Path) -> None:
    d = evaluate_pre_submit(
        INTENT,
        snapshot(realized_daily_loss_usd=5.0),
        CFG,
        armed_switch(tmp_path),
        InMemoryIdempotencyStore().seen,
    )
    assert d.failed_gate == "daily_loss_cap"


def test_equity_floor_rejected(tmp_path: Path) -> None:
    d = evaluate_pre_submit(
        INTENT,
        snapshot(equity_usd=19.0),
        CFG,
        armed_switch(tmp_path),
        InMemoryIdempotencyStore().seen,
    )
    assert d.failed_gate == "equity_floor"


def test_total_loss_abandon_rejected(tmp_path: Path) -> None:
    d = evaluate_pre_submit(
        INTENT,
        snapshot(cumulative_loss_usd=30.5),
        CFG,
        armed_switch(tmp_path),
        InMemoryIdempotencyStore().seen,
    )
    assert d.failed_gate == "total_loss_abandon"


def test_concentration_rejected(tmp_path: Path) -> None:
    big = OrderIntent(
        strategy_id="orb",
        symbol="AAPL",
        side="buy",
        qty=1.0,
        intended_risk_usd=1.0,
        est_position_value_usd=40.0,  # 80% of $50
    )
    d = evaluate_pre_submit(
        big, snapshot(), CFG, armed_switch(tmp_path), InMemoryIdempotencyStore().seen
    )
    assert d.failed_gate == "concentration"


def test_duplicate_idempotency_rejected(tmp_path: Path) -> None:
    store = InMemoryIdempotencyStore()
    store.remember(client_order_id(INTENT))  # pretend already submitted
    d = evaluate_pre_submit(INTENT, snapshot(), CFG, armed_switch(tmp_path), store.seen)
    assert d.failed_gate == "idempotency"


def test_mistake_check_rejected(tmp_path: Path) -> None:
    def always_block(intent: OrderIntent, snap: AccountSnapshot) -> str | None:
        return "BLOCKED: matches pattern M7 (news blindspot)"

    d = evaluate_pre_submit(
        INTENT,
        snapshot(),
        CFG,
        armed_switch(tmp_path),
        InMemoryIdempotencyStore().seen,
        mistake_checker=always_block,
    )
    assert d.failed_gate == "mistake_check"
