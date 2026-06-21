"""Tests for the pure risk-cap functions (Increment 1 safety spine).

Boundary unit tests plus property proofs that a cap can never report ``ok`` once its
limit is exceeded, for any value in the invalid range.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

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
    per_trade_risk_usd=1.0,
    max_daily_loss_usd=5.0,
    equity_floor_usd=20.0,
    total_loss_abandon_usd=30.0,
    max_position_concentration_pct=30.0,
    max_consecutive_errors=5,
)


def test_per_trade_within_cap_ok() -> None:
    assert check_per_trade_risk(CFG, 1.0).ok


def test_per_trade_zero_blocked() -> None:
    assert not check_per_trade_risk(CFG, 0.0).ok


def test_per_trade_over_cap_blocked() -> None:
    assert not check_per_trade_risk(CFG, 1.01).ok


def test_daily_under_cap_ok() -> None:
    assert check_daily_loss(CFG, 4.99).ok


def test_daily_at_cap_blocked() -> None:
    assert not check_daily_loss(CFG, 5.0).ok


def test_equity_at_floor_ok() -> None:
    assert check_equity_floor(CFG, 20.0).ok


def test_equity_below_floor_blocked() -> None:
    assert not check_equity_floor(CFG, 19.99).ok


def test_total_loss_at_threshold_ok() -> None:
    assert check_total_loss_abandon(CFG, 30.0).ok


def test_total_loss_over_threshold_blocked() -> None:
    assert not check_total_loss_abandon(CFG, 30.01).ok


def test_concentration_at_cap_ok() -> None:
    assert check_concentration(CFG, 15.0, 50.0).ok  # 30% of $50


def test_concentration_over_cap_blocked() -> None:
    assert not check_concentration(CFG, 16.0, 50.0).ok  # 32%


def test_concentration_zero_equity_blocked() -> None:
    assert not check_concentration(CFG, 1.0, 0.0).ok


@given(extra=st.floats(min_value=1e-6, max_value=1e6))
def test_per_trade_over_cap_always_blocked(extra: float) -> None:
    assert not check_per_trade_risk(CFG, CFG.per_trade_risk_usd + extra).ok


@given(loss=st.floats(min_value=CFG.total_loss_abandon_usd + 1e-6, max_value=1e9))
def test_total_loss_over_threshold_always_blocked(loss: float) -> None:
    assert not check_total_loss_abandon(CFG, loss).ok


@given(equity=st.floats(min_value=0.0, max_value=CFG.equity_floor_usd - 1e-6))
def test_equity_below_floor_always_blocked(equity: float) -> None:
    assert not check_equity_floor(CFG, equity).ok
