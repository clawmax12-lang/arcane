"""Tests for the registry-wide prefix-stability (look-ahead) property — Increment 2 STEP 8.

The property ``compute(df[:k]) == compute(df[:k+1])[:k]`` *is* the definition of no-look-ahead:
truncating the input to its first k rows must not change the first k outputs. These tests prove
two things at once: legitimate trailing factors pass, and — critically — the harness has TEETH
(every classic leak shape is CAUGHT). A leak detector that never fires is worthless (the
"red-team your own safety code" insight).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from trading.data.errors import PrefixStabilityError
from trading.data.prefix_stability import (
    assert_prefix_stable,
    check_registry,
    first_violation,
)


@dataclass(frozen=True)
class _Factor:
    """A minimal ``PrefixComputation``: a named close->series transform."""

    id: str
    fn: Callable[[pd.DataFrame], pd.Series]

    def compute(self, df: pd.DataFrame) -> pd.Series:
        return self.fn(df)


def _frame(closes: list[float]) -> pd.DataFrame:
    n = len(closes)
    idx = pd.date_range("2024-01-02", periods=n, freq="D", tz="UTC")
    idx.name = "ts"
    c = pd.Series(closes, index=idx, dtype="Float64")
    return pd.DataFrame(
        {
            "open": c,
            "high": c + 1,
            "low": c - 1,
            "close": c,
            "volume": pd.Series([100] * n, index=idx, dtype="Int64"),
        }
    )


_SAMPLE = _frame([10.0, 11.0, 12.0, 11.5, 13.0, 12.0, 14.0, 13.5])


# --- legitimate trailing factors are prefix-stable ---

GOOD: list[_Factor] = [
    _Factor("identity_close", lambda df: df["close"]),
    _Factor("trailing_return", lambda df: df["close"].pct_change().shift(1)),
    _Factor("trailing_mean_3", lambda df: df["close"].rolling(3).mean()),
    _Factor("trailing_z", lambda df: df["close"].rolling(4).apply(lambda w: w.iloc[-1] - w.mean())),
]


@pytest.mark.parametrize("factor", GOOD, ids=lambda f: f.id)
def test_good_factors_are_prefix_stable(factor: _Factor) -> None:
    assert first_violation(factor, _SAMPLE) is None
    assert_prefix_stable(factor, _SAMPLE)  # does not raise


# --- classic leak shapes are CAUGHT (teeth) ---

LEAKY: list[_Factor] = [
    _Factor("full_series_z", lambda df: (df["close"] - df["close"].mean()) / df["close"].std()),
    _Factor("centered_roll", lambda df: df["close"].rolling(3, center=True).mean()),
    _Factor("future_shift", lambda df: df["close"].shift(-1)),
    _Factor("normalize_by_last", lambda df: df["close"] / df["close"].iloc[-1]),
]


@pytest.mark.parametrize("factor", LEAKY, ids=lambda f: f.id)
def test_leaky_factors_are_caught(factor: _Factor) -> None:
    v = first_violation(factor, _SAMPLE)
    assert v is not None, f"{factor.id} should be flagged as a look-ahead leak"
    assert v.computation_id == factor.id
    assert 1 <= v.k <= len(_SAMPLE)
    with pytest.raises(PrefixStabilityError, match=factor.id):
        assert_prefix_stable(factor, _SAMPLE)


def test_length_mismatch_is_a_violation() -> None:
    drops_first = _Factor("drops_first", lambda df: df["close"].iloc[1:])
    v = first_violation(drops_first, _SAMPLE)
    assert v is not None
    assert "length" in v.reason.lower()


def test_compute_that_raises_on_short_prefix_is_a_violation() -> None:
    def _raise_on_short(df: pd.DataFrame) -> pd.Series:
        if len(df) < 3:
            raise ValueError("needs >= 3 rows")
        return df["close"]

    v = first_violation(_Factor("raises_on_short", _raise_on_short), _SAMPLE)
    assert v is not None
    assert "raised" in v.reason.lower()


def test_compute_that_raises_on_full_frame_is_a_violation() -> None:
    # fail-closed: a registered computation that blows up on the full frame is a violation,
    # reported at k = len(df), not an unhandled crash of the harness.
    def _raise_on_full(df: pd.DataFrame) -> pd.Series:
        if len(df) >= len(_SAMPLE):
            raise ValueError("boom on full frame")
        return df["close"]

    v = first_violation(_Factor("raises_on_full", _raise_on_full), _SAMPLE)
    assert v is not None
    assert v.k == len(_SAMPLE)
    assert "full frame" in v.reason.lower()


def test_fixed_length_output_is_a_per_prefix_length_violation() -> None:
    # output length ignores the input -> the per-prefix length guard fires (not the full-frame one).
    fixed = _Factor("fixed_len", lambda df: pd.Series([1.0] * len(_SAMPLE)))
    v = first_violation(fixed, _SAMPLE)
    assert v is not None
    assert 1 <= v.k < len(_SAMPLE)
    assert "length" in v.reason.lower()


def test_output_type_change_is_a_violation() -> None:
    # DataFrame on the full frame but Series on a prefix -> type mismatch is caught (fail-closed).
    morph = _Factor(
        "type_morph", lambda df: df[["close"]] if len(df) == len(_SAMPLE) else df["close"]
    )
    v = first_violation(morph, _SAMPLE)
    assert v is not None


# --- registry-wide entry point (what Increment-3 validate_all() will call) ---


def test_check_registry_passes_for_good_factors() -> None:
    check_registry(GOOD, [_SAMPLE])  # no raise


def test_check_registry_raises_on_first_leak() -> None:
    with pytest.raises(PrefixStabilityError):
        check_registry([GOOD[0], LEAKY[0]], [_SAMPLE])


def test_empty_registry_vacuously_passes() -> None:
    check_registry([], [_SAMPLE])  # no factors registered yet (Increment 2) -> trivially clean


# --- property: a trailing factor stays stable across many generated frames ---


@given(
    closes=st.lists(
        st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        min_size=2,
        max_size=12,
    )
)
def test_trailing_return_is_prefix_stable_property(closes: list[float]) -> None:
    factor = _Factor("trailing_return", lambda df: df["close"].pct_change().shift(1))
    assert first_violation(factor, _frame(closes)) is None
