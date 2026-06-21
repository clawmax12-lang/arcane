"""Tests for the data-layer reliability tiers + error taxonomy (Increment 2 STEP 1).

These cover the runtime guard and the error taxonomy. The TYPE-level enforcement
(TEXTUAL/DERIVED frames forbidden at gates) arrives in STEP 5 over the ImmutableFrame
carrier and is verified there by `mypy --strict`.
"""

from __future__ import annotations

import pytest

from trading.data import errors
from trading.data.errors import DataError, ReliabilityError
from trading.data.reliability import Reliability, is_gateable, require_gateable
from trading.risk.errors import ArcaneError


def test_reliability_members() -> None:
    assert {r.value for r in Reliability} == {"hard", "structured", "textual", "derived"}


@pytest.mark.parametrize("rel", [Reliability.HARD, Reliability.STRUCTURED])
def test_gateable_tiers_allowed(rel: Reliability) -> None:
    assert is_gateable(rel) is True
    require_gateable(rel)  # must not raise


@pytest.mark.parametrize("rel", [Reliability.TEXTUAL, Reliability.DERIVED])
def test_non_gateable_tiers_rejected(rel: Reliability) -> None:
    assert is_gateable(rel) is False
    with pytest.raises(ReliabilityError):
        require_gateable(rel)


def test_error_taxonomy_are_arcane_errors() -> None:
    names = [
        "DataError",
        "DataFetchError",
        "SchemaError",
        "FinitenessError",
        "CalendarError",
        "QualityError",
        "FeedMismatchError",
        "PITViolationError",
        "RestatedSourceError",
        "CacheError",
        "ReliabilityError",
    ]
    for name in names:
        cls = getattr(errors, name)
        assert issubclass(cls, DataError)
        assert issubclass(cls, ArcaneError)
