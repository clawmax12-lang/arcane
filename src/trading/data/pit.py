"""Point-in-time guard — the structural look-ahead defense.

``AsOf`` is a frozen, validated PIT clock (tz-aware UTC, never in the future). ``pit_guard``
drops every row whose ``ingest_ts`` is after ``as_of``, so a backtest standing at ``as_of``
can never see data that did not yet exist. A missing or null ``ingest_ts`` is refused (a
restated source without per-row vintage cannot be made point-in-time).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pandas as pd

from trading.data.errors import PITViolationError


@dataclass(frozen=True, slots=True)
class AsOf:
    """The point-in-time clock a load is evaluated against. Tz-aware UTC, not in the future."""

    ts: datetime

    def __post_init__(self) -> None:
        if self.ts.tzinfo is None or self.ts.utcoffset() != timedelta(0):
            raise PITViolationError(f"as_of must be tz-aware UTC, got {self.ts!r}")
        if self.ts > datetime.now(UTC):
            raise PITViolationError(f"as_of {self.ts!r} is in the future")


def pit_guard(df: pd.DataFrame, as_of: AsOf) -> pd.DataFrame:
    """Drop rows whose ``ingest_ts`` is after ``as_of`` (requires a non-null ingest_ts column)."""
    if "ingest_ts" not in df.columns:
        raise PITViolationError("frame has no ingest_ts column (PIT guard cannot run)")
    if bool(df["ingest_ts"].isna().any()):
        raise PITViolationError("ingest_ts contains nulls (cannot establish vintage)")
    keep = (df["ingest_ts"] <= pd.Timestamp(as_of.ts)).to_numpy()
    return df[keep]
