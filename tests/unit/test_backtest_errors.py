"""Tests for the backtest-layer error taxonomy — Increment 4 cluster 1.

The backtest is a SIBLING layer to the data spine and the factor layer, so its errors root at the
SAME ``ArcaneError`` as ``DataError`` / ``FactorError`` — NOT under either (a backtest fault must
not be mis-bucketed by an ``except DataError`` / ``except FactorError`` handler). Every failure is a
specific, catchable exception; the default on uncertainty is to RAISE (fail closed).
"""

from __future__ import annotations

import pytest

from trading.backtest.errors import (
    BacktestContractError,
    BacktestError,
    CostModelError,
    FrameAdequacyError,
    StrategySpecError,
    UnknownFactorError,
    WalkForwardError,
)
from trading.risk.errors import ArcaneError

_SUBCLASSES = [
    StrategySpecError,
    UnknownFactorError,
    CostModelError,
    WalkForwardError,
    BacktestContractError,
    FrameAdequacyError,
]


def test_backtest_error_roots_at_arcane_not_data_or_factor() -> None:
    assert issubclass(BacktestError, ArcaneError)
    # Sibling-layer isolation: a backtest fault is NEITHER a DataError NOR a FactorError, so it is
    # never swallowed by a handler scoped to those layers.
    from trading.data.errors import DataError
    from trading.factors.errors import FactorError

    assert not issubclass(BacktestError, DataError)
    assert not issubclass(BacktestError, FactorError)


@pytest.mark.parametrize("exc", _SUBCLASSES, ids=lambda e: e.__name__)
def test_each_is_a_distinct_catchable_backtest_error(exc: type[BacktestError]) -> None:
    assert issubclass(exc, BacktestError)
    with pytest.raises(BacktestError):
        raise exc("boom")
    # and catchable as the project-root ArcaneError
    with pytest.raises(ArcaneError):
        raise exc("boom")


def test_unknown_factor_is_a_strategy_spec_error() -> None:
    # A spec referencing an unregistered factor_id is a SPEC fault (a natural sub-hierarchy).
    assert issubclass(UnknownFactorError, StrategySpecError)
    with pytest.raises(StrategySpecError):
        raise UnknownFactorError("mom_999d")
