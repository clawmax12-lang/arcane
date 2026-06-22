"""Tests for the factor-layer error taxonomy — Increment 3.

Factors are a SIBLING layer to the data spine, so their errors root at the SAME
``trading.risk.errors.ArcaneError`` as ``data.errors.DataError`` — NOT under ``DataError`` (a factor
fault must not be mis-bucketed by an ``except DataError`` handler). Every failure is a specific,
catchable exception; the default on any uncertainty is to RAISE (fail closed).
"""

from __future__ import annotations

import pytest

from trading.factors.errors import (
    DuplicateFactorError,
    FactorContractError,
    FactorError,
    FrameAdequacyError,
    TrialLedgerError,
)
from trading.risk.errors import ArcaneError

_SUBCLASSES = [
    FactorContractError,
    DuplicateFactorError,
    FrameAdequacyError,
    TrialLedgerError,
]


def test_factor_error_roots_at_arcane_error_not_data_error() -> None:
    assert issubclass(FactorError, ArcaneError)
    # A factor fault is NOT a DataError (sibling layers; importing DataError must not be a parent).
    from trading.data.errors import DataError

    assert not issubclass(FactorError, DataError)


@pytest.mark.parametrize("exc", _SUBCLASSES, ids=lambda e: e.__name__)
def test_each_is_a_distinct_catchable_factor_error(exc: type[FactorError]) -> None:
    assert issubclass(exc, FactorError)
    with pytest.raises(FactorError):
        raise exc("boom")
    # and catchable as the project-root ArcaneError
    with pytest.raises(ArcaneError):
        raise exc("boom")
