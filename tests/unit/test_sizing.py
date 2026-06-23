"""C10 — sizing within caps: the $1 cap yields NoTrade for any real share (Increment 6 PART C)."""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from trading.bias_gate.gate import FROZEN_COMPONENT_NAMES, GateComponent, GateDecision
from trading.executor.grant import AllocationGrant
from trading.executor.intent import Side
from trading.executor.invariants import AccountSnapshot
from trading.executor.sizing import HardQuote, NoTrade, Sized, TargetPosition, size_order
from trading.risk.schema import RiskConfig

_UHASH = "arcane-univ-deadbeef"


def _grant() -> AllocationGrant:
    comps = tuple(GateComponent(n, True, "") for n in FROZEN_COMPONENT_NAMES)
    decision = GateDecision("arcane-strategy-x", True, comps, n_trials=17, reasons=())
    return AllocationGrant.from_decision(decision, universe_artifact_hash=_UHASH)


def _cfg(*, per_trade: float = 1.0) -> RiskConfig:
    return RiskConfig(
        live_mode=False,
        per_trade_risk_usd=per_trade,
        max_daily_loss_usd=5.0,
        equity_floor_usd=20.0,
        total_loss_abandon_usd=30.0,
        max_position_concentration_pct=30.0,
        max_consecutive_errors=5,
    )


def _account(*, equity: float = 50.0, now: float = 1000.0) -> AccountSnapshot:
    return AccountSnapshot(
        equity_usd=equity,
        realized_daily_loss_usd=0.0,
        cumulative_loss_usd=0.0,
        data_as_of_epoch=now,
        now_epoch=now,
    )


def _target() -> TargetPosition:
    return TargetPosition(
        strategy_id="ts_momentum_blend", symbol="AAPL", side=Side.BUY, spec_hash="arcane-strategy-x"
    )


def _quote(*, price: float = 150.0, as_of: float = 1000.0) -> HardQuote:
    return HardQuote(symbol="AAPL", price=price, as_of_epoch=as_of)


@given(price=st.floats(min_value=1.01, max_value=100_000.0, allow_nan=False, allow_infinity=False))
def test_dollar_cap_always_yields_no_trade_for_any_real_share(price: float) -> None:
    out = size_order(_grant(), _target(), _quote(price=price), _account(), _cfg(per_trade=1.0))
    assert isinstance(out, NoTrade)  # $1 buys 0 whole shares of any $>1 stock — the expected null


def test_fail_closed_on_non_finite_or_nonpositive_price() -> None:
    for bad in (math.nan, math.inf, 0.0, -5.0):
        out = size_order(_grant(), _target(), _quote(price=bad), _account(), _cfg())
        assert isinstance(out, NoTrade)


def test_fail_closed_on_stale_quote() -> None:
    stale = _quote(as_of=0.0)  # ~1000s old vs now=1000
    assert isinstance(size_order(_grant(), _target(), stale, _account(), _cfg()), NoTrade)
    future = _quote(as_of=2000.0)  # quote from the future
    assert isinstance(size_order(_grant(), _target(), future, _account(), _cfg()), NoTrade)


def test_fail_closed_on_symbol_mismatch() -> None:
    q = HardQuote(symbol="MSFT", price=10.0, as_of_epoch=1000.0)
    assert isinstance(size_order(_grant(), _target(), q, _account(), _cfg()), NoTrade)


def test_fail_closed_below_equity_floor() -> None:
    out = size_order(_grant(), _target(), _quote(price=2.0), _account(equity=19.0), _cfg())
    assert isinstance(out, NoTrade)


def test_sizes_a_whole_share_when_caps_allow() -> None:
    # With a $5 per-trade cap and a $2 stock, budget=$5 -> 2 whole shares -> $4 notional, all
    # caps OK.
    out = size_order(_grant(), _target(), _quote(price=2.0), _account(), _cfg(per_trade=5.0))
    assert isinstance(out, Sized)
    assert out.intent.qty == 2.0
    assert out.intent.intended_risk_usd == pytest.approx(4.0)
    assert out.intent.est_position_value_usd == pytest.approx(4.0)
    assert out.intent.intended_risk_usd <= 5.0  # within per-trade cap


def test_share_pricier_than_cap_is_no_trade_never_rounds_to_submit() -> None:
    # price $10 > per-trade $5 -> 0 whole shares affordable within the cap -> NoTrade (not a
    # 0-qty submit)
    out = size_order(_grant(), _target(), _quote(price=10.0), _account(), _cfg(per_trade=5.0))
    assert isinstance(out, NoTrade) and "0 whole shares" in out.reason


def test_a_sized_intent_satisfies_caps_independently() -> None:
    out = size_order(_grant(), _target(), _quote(price=2.0), _account(), _cfg(per_trade=5.0))
    assert isinstance(out, Sized)
    notional = out.intent.qty * 2.0
    assert notional <= 5.0  # per-trade
    assert notional / 50.0 * 100.0 <= 30.0  # concentration
    assert 50.0 - notional >= 20.0  # equity floor
