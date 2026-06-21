"""Tests for the fail-closed data-quality gate (Increment 2 STEP 3)."""

from __future__ import annotations

import pandas as pd
import pytest

from trading.data.errors import DuplicateBarError, FinitenessError, QualityError
from trading.data.quality import (
    assert_finite,
    assert_sorted,
    coverage_report,
    dedupe_or_raise,
    run_quality_gate,
)


def _bars(n: int = 3) -> pd.DataFrame:
    ts = pd.to_datetime([f"2024-07-01 13:3{i}:00" for i in range(n)], utc=True).as_unit("ns")
    df = pd.DataFrame(
        {
            "open": [10.0 + i for i in range(n)],
            "high": [10.6 + i for i in range(n)],
            "low": [9.9 + i for i in range(n)],
            "close": [10.5 + i for i in range(n)],
            "volume": [100 + i for i in range(n)],
            "trade_count": [5 + i for i in range(n)],
            "vwap": [10.2 + i for i in range(n)],
            "ingest_ts": ts,
        },
        index=pd.DatetimeIndex(ts, name="ts"),
    )
    return df.astype(
        {
            "open": "Float64",
            "high": "Float64",
            "low": "Float64",
            "close": "Float64",
            "volume": "Int64",
            "trade_count": "Int64",
            "vwap": "Float64",
        }
    )


def test_finite_passes() -> None:
    assert_finite(_bars())


def test_inf_rejected() -> None:
    df = _bars()
    df.loc[df.index[0], "close"] = float("inf")
    with pytest.raises(FinitenessError):
        assert_finite(df)


def test_nan_in_nonnull_rejected() -> None:
    df = _bars()
    df.loc[df.index[0], "volume"] = pd.NA
    with pytest.raises(FinitenessError):
        assert_finite(df)


def test_sorted_passes_unsorted_raises() -> None:
    assert_sorted(_bars())
    shuffled = _bars().iloc[::-1]
    with pytest.raises(QualityError):
        assert_sorted(shuffled)


def test_identical_duplicate_collapsed() -> None:
    df = _bars(2)
    dup = pd.concat([df, df.iloc[[0]]]).sort_index()
    out = dedupe_or_raise(dup)
    assert out.index.is_unique
    assert len(out) == 2


def test_conflicting_duplicate_raises() -> None:
    df = _bars(2)
    conflict = df.iloc[[0]].copy()
    conflict.loc[conflict.index[0], "close"] = 999.0
    bad = pd.concat([df, conflict]).sort_index()
    with pytest.raises(DuplicateBarError):
        dedupe_or_raise(bad)


def test_already_unique_unchanged() -> None:
    df = _bars(3)
    assert dedupe_or_raise(df) is df


def test_run_quality_gate_returns_clean_frame() -> None:
    out = run_quality_gate(_bars(3))
    assert out.index.is_unique and len(out) == 3


def test_coverage_report_full_and_degraded() -> None:
    expected = pd.to_datetime(
        ["2024-07-01 13:30", "2024-07-01 13:31", "2024-07-01 13:32"], utc=True
    )
    full = coverage_report(expected, expected)
    assert full.coverage_degraded is False and full.missing == 0

    actual = expected[:2]  # one bar missing — must report, never impute
    degraded = coverage_report(actual, expected)
    assert degraded.coverage_degraded is True
    assert degraded.missing == 1 and degraded.present == 2
