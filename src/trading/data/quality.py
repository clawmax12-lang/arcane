"""Fail-closed data-quality gate — raises on the first failure, never silently fixes data.

Order: **G1** finiteness (``np.isfinite``; inf/NaN → ``FinitenessError``, run BEFORE pandera
which admits inf) → **G2** monotonic index → **G3** exact-duplicate collapse with a RAISE on a
timestamp that has *conflicting* values (never silent pick-last) → **G4** coverage report.

CRITICAL: an IEX coverage hole is NEVER imputed (no ffill / zero-fill). A filled hole
fabricates a volume/illiquidity edge — the apex data leak. ``coverage_report`` only *reports*
missing bars; the loader stamps ``coverage_degraded`` and downstream type-forbids the frame
from a HARD gate. Re-run on every cache read.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from trading.data.errors import DuplicateBarError, FinitenessError, QualityError

# Non-nullable numeric columns that must be finite (vwap is nullable -> excluded).
_FINITE_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close", "volume", "trade_count")


@dataclass(frozen=True, slots=True)
class CoverageReport:
    expected: int
    present: int
    missing: int
    coverage_degraded: bool


def assert_finite(df: pd.DataFrame) -> None:
    """G1: reject NaN/inf in the non-nullable numeric columns (runs before pandera ge=0)."""
    for col in _FINITE_COLUMNS:
        values = df[col].to_numpy(dtype="float64", na_value=np.nan)
        if not np.isfinite(values).all():
            raise FinitenessError(f"column {col!r} contains non-finite (NaN/inf) values")


def assert_sorted(df: pd.DataFrame) -> None:
    """G2: the index must be monotonic non-decreasing (vendor order is not trusted blindly)."""
    if not df.index.is_monotonic_increasing:
        raise QualityError("bar index is not monotonic increasing")


def dedupe_or_raise(df: pd.DataFrame) -> pd.DataFrame:
    """G3: collapse rows identical in (ts, values); RAISE on a ts with conflicting values."""
    if df.index.is_unique:
        return df
    keep = ~df.reset_index().duplicated().to_numpy()
    collapsed = df[keep]
    if not collapsed.index.is_unique:
        conflicts = collapsed.index[collapsed.index.duplicated(keep=False)].unique().tolist()
        raise DuplicateBarError(f"conflicting duplicate bars at timestamps {conflicts}")
    return collapsed


def run_quality_gate(df: pd.DataFrame) -> pd.DataFrame:
    """Run G1 -> G2 -> G3 in order (fail-closed); return the conflict-free, unique-index frame."""
    assert_finite(df)
    assert_sorted(df)
    return dedupe_or_raise(df)


def coverage_report(actual: pd.DatetimeIndex, expected: pd.DatetimeIndex) -> CoverageReport:
    """G4: report missing bars vs the calendar's expected grid. NEVER imputes — only reports."""
    expected_n = len(expected)
    present = int(np.asarray(expected.isin(actual)).sum())
    missing = expected_n - present
    return CoverageReport(
        expected=expected_n,
        present=present,
        missing=missing,
        coverage_degraded=missing > 0,
    )
