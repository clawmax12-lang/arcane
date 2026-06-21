"""Regression tests for red-team workflow wf_453c8909-dd7 (2026-06-21).

Each test reproduces a confirmed fail-open exploit and asserts it is now closed.
Findings 1-3 (finiteness + idempotency canonicalization) are covered here; findings
4-6 (sanitizer, kill switch) are covered in their own module tests.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from trading.executor.idempotency import client_order_id
from trading.executor.intent import OrderIntent
from trading.executor.invariants import AccountSnapshot
from trading.risk.caps import (
    check_concentration,
    check_daily_loss,
    check_equity_floor,
    check_per_trade_risk,
    check_total_loss_abandon,
)
from trading.risk.schema import RiskConfig

CFG = RiskConfig(
    live_mode=False,
    per_trade_risk_usd=5.0,
    max_daily_loss_usd=15.0,
    equity_floor_usd=20.0,
    total_loss_abandon_usd=30.0,
    max_position_concentration_pct=50.0,
    max_consecutive_errors=5,
)
BASE: dict[str, Any] = {
    "strategy_id": "orb",
    "symbol": "AAPL",
    "side": "buy",
    "qty": 1.0,
    "intended_risk_usd": 1.0,
    "est_position_value_usd": 10.0,
}
NONFINITE = (float("nan"), float("inf"), float("-inf"))
SNAP_FIELDS = (
    "equity_usd",
    "realized_daily_loss_usd",
    "cumulative_loss_usd",
    "data_as_of_epoch",
    "now_epoch",
)


# --- Finding #1 (CRITICAL): NaN/inf in AccountSnapshot bypassed every risk gate ---


@pytest.mark.parametrize("field", SNAP_FIELDS)
@pytest.mark.parametrize("bad", NONFINITE)
def test_finding1_nonfinite_snapshot_rejected(field: str, bad: float) -> None:
    good: dict[str, float] = {
        "equity_usd": 50.0,
        "realized_daily_loss_usd": 0.0,
        "cumulative_loss_usd": 0.0,
        "data_as_of_epoch": 1_000.0,
        "now_epoch": 1_000.0,
    }
    good[field] = bad
    with pytest.raises(ValueError):
        AccountSnapshot(**good)


@pytest.mark.parametrize("bad", NONFINITE)
def test_finding1_caps_reject_nonfinite(bad: float) -> None:
    assert not check_per_trade_risk(CFG, bad).ok
    assert not check_daily_loss(CFG, bad).ok
    assert not check_equity_floor(CFG, bad).ok
    assert not check_total_loss_abandon(CFG, bad).ok
    assert not check_concentration(CFG, bad, 50.0).ok
    assert not check_concentration(CFG, 10.0, bad).ok


# --- Finding #2 (HIGH): OrderIntent accepted inf for qty/risk/value ---


@pytest.mark.parametrize("field", ["qty", "intended_risk_usd", "est_position_value_usd"])
@pytest.mark.parametrize("bad", [float("inf"), float("nan")])
def test_finding2_nonfinite_intent_rejected(field: str, bad: float) -> None:
    with pytest.raises(ValidationError):
        OrderIntent(**{**BASE, field: bad})


def test_finding2_inf_limit_price_rejected() -> None:
    with pytest.raises(ValidationError):
        OrderIntent(**{**BASE, "order_type": "limit", "limit_price": float("inf")})


# --- Finding #3 (HIGH): idempotency dedup miss via unnormalized identity fields ---


def test_finding3_symbol_canonicalized() -> None:
    assert OrderIntent(**{**BASE, "symbol": "aapl"}).symbol == "AAPL"
    assert OrderIntent(**{**BASE, "symbol": "AAPL "}).symbol == "AAPL"
    assert OrderIntent(**{**BASE, "symbol": "AAPL​"}).symbol == "AAPL"  # zero-width


def test_finding3_cosmetic_variants_share_client_order_id() -> None:
    ids = {
        client_order_id(OrderIntent(**{**BASE, "symbol": s}))
        for s in ("AAPL", "aapl", "AAPL ", "AAPL​")
    }
    assert len(ids) == 1  # all cosmetic variants -> one id -> dedup works


def test_finding3_delimiter_injection_rejected() -> None:
    with pytest.raises(ValidationError):
        OrderIntent(**{**BASE, "symbol": "AAPL|x"})
    with pytest.raises(ValidationError):
        OrderIntent(**{**BASE, "strategy_id": "orb|AAPL"})


def test_finding3_distinct_orders_distinct_ids() -> None:
    a = client_order_id(OrderIntent(**{**BASE, "qty": 1.0}))
    b = client_order_id(OrderIntent(**{**BASE, "qty": 2.0}))
    assert a != b
