"""Tests for the conservative cost model — Increment 4 cluster 4 (M3 defense).

Proves: cost is charged on EVERY fill (turnover-driven, no zero-cost fills except a no-change bar);
each bps component has a hardcoded conservative FLOOR that config cannot lower (the constants.py
EQUITY_FLOOR idiom); cost_scale only ever RAISES cost (ge 1.0) and never below the floor;
per_bar_cost is >= 0 always and == 0 only on zero turnover;
doubling cost_scale doubles the cost; and a non-finite position fails closed (the GUARD-B idiom).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from trading.backtest.cost_model import (
    COMMISSION_FLOOR_BPS,
    HALF_SPREAD_FLOOR_BPS,
    SLIPPAGE_FLOOR_BPS,
    CostModel,
)
from trading.backtest.errors import CostModelError


def _pos(values: list[float]) -> pd.Series:
    idx = pd.date_range("2020-01-01", periods=len(values), freq="D", tz="UTC")
    return pd.Series(values, index=idx, dtype="float64")


# --- conservative defaults + floors (config cannot lower cost) ---


def test_default_total_bps_is_six_one_way() -> None:
    cm = CostModel()
    assert cm.total_bps == pytest.approx(
        COMMISSION_FLOOR_BPS + HALF_SPREAD_FLOOR_BPS + SLIPPAGE_FLOOR_BPS
    )
    assert cm.total_bps == pytest.approx(6.0)


@pytest.mark.parametrize(
    "field,floor",
    [
        ("commission_bps", COMMISSION_FLOOR_BPS),
        ("half_spread_bps", HALF_SPREAD_FLOOR_BPS),
        ("slippage_bps", SLIPPAGE_FLOOR_BPS),
    ],
)
def test_a_component_below_its_floor_is_rejected(field: str, floor: float) -> None:
    with pytest.raises(ValidationError):
        CostModel(**{field: floor - 0.5})  # type: ignore[arg-type]
    # at/above the floor is allowed (you may be MORE pessimistic)
    CostModel(**{field: floor + 1.0})  # type: ignore[arg-type]


def test_cost_scale_cannot_lower_cost_below_floor() -> None:
    with pytest.raises(ValidationError):
        CostModel(cost_scale=0.0)
    with pytest.raises(ValidationError):
        CostModel(cost_scale=0.5)  # < 1 would make a fill cheaper than the floor


@pytest.mark.parametrize("bad", [float("inf"), float("nan")])
def test_non_finite_bps_rejected(bad: float) -> None:
    with pytest.raises(ValidationError):
        CostModel(slippage_bps=bad)


def test_cost_model_is_frozen() -> None:
    with pytest.raises(ValidationError):
        CostModel().cost_scale = 2.0  # type: ignore[misc]


# --- per_bar_cost: turnover-driven, >= 0, zero only on no change ---


def test_entry_from_flat_costs() -> None:
    cm = CostModel()
    cost = cm.per_bar_cost(_pos([1.0, 1.0, 1.0]))
    # bar 0 enters from flat (turnover |1-0|=1) -> nonzero; bars 1,2 unchanged -> zero.
    assert cost.iloc[0] == pytest.approx(6.0 * 1e-4 * 1.0)
    assert cost.iloc[1] == pytest.approx(0.0)
    assert cost.iloc[2] == pytest.approx(0.0)


def test_full_flip_costs_twice_the_one_way() -> None:
    cm = CostModel()
    cost = cm.per_bar_cost(_pos([1.0, -1.0]))  # turnover at bar1 = |-1-1| = 2
    assert cost.iloc[1] == pytest.approx(6.0 * 1e-4 * 2.0)


def test_zero_position_has_zero_cost() -> None:
    cm = CostModel()
    cost = cm.per_bar_cost(_pos([0.0, 0.0, 0.0]))
    assert (cost == 0.0).all()


def test_cost_scale_is_linear_and_monotone() -> None:
    pos = _pos([0.5, -0.5, 0.5])
    base = CostModel().per_bar_cost(pos)
    stressed = CostModel(cost_scale=3.0).per_bar_cost(pos)
    assert (stressed >= base).all()
    assert stressed.to_numpy() == pytest.approx(3.0 * base.to_numpy())


def test_non_finite_position_fails_closed() -> None:
    cm = CostModel()
    with pytest.raises(CostModelError):
        cm.per_bar_cost(_pos([1.0, float("nan"), 1.0]))
    with pytest.raises(CostModelError):
        cm.per_bar_cost(_pos([1.0, float("inf")]))


def test_empty_position_returns_empty_cost() -> None:
    cm = CostModel()
    cost = cm.per_bar_cost(_pos([]))
    assert len(cost) == 0


@given(
    st.lists(
        st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=60,
    )
)
def test_cost_is_nonnegative_and_zero_iff_no_turnover(values: list[float]) -> None:
    cm = CostModel()
    pos = _pos(values)
    cost = cm.per_bar_cost(pos)
    arr = cost.to_numpy()
    assert (arr >= 0.0).all()  # never a negative (rebate) cost
    prior = np.concatenate([[0.0], np.asarray(values)[:-1]])
    turnover = np.abs(np.asarray(values) - prior)
    # a no-change bar is EXACTLY free (the M3 "no zero-cost fills" claim is about real trades).
    assert (arr[turnover == 0.0] == 0.0).all()
    # a MATERIAL trade always costs > 0. (An infinitesimal subnormal turnover can underflow the
    # 6e-4 * turnover product to 0.0 — mathematically fine and irrelevant to a [-1,1] position.)
    material = turnover > 1e-9
    assert (arr[material] > 0.0).all()
