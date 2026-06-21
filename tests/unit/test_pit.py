"""Tests for the point-in-time guard (Increment 2 STEP 4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from trading.data.errors import PITViolationError
from trading.data.pit import AsOf, pit_guard


def _frame(ingest_utc: list[str]) -> pd.DataFrame:
    ts = pd.to_datetime(ingest_utc, utc=True).as_unit("ns")
    return pd.DataFrame(
        {"close": [1.0] * len(ts), "ingest_ts": ts},
        index=pd.DatetimeIndex(ts, name="ts"),
    )


def test_asof_accepts_past_utc() -> None:
    AsOf(datetime(2024, 7, 1, tzinfo=UTC))  # must not raise


def test_asof_rejects_naive() -> None:
    with pytest.raises(PITViolationError):
        AsOf(datetime(2024, 7, 1))


def test_asof_rejects_non_utc() -> None:
    from zoneinfo import ZoneInfo

    with pytest.raises(PITViolationError):
        AsOf(datetime(2024, 7, 1, 12, tzinfo=ZoneInfo("America/New_York")))


def test_asof_rejects_future() -> None:
    with pytest.raises(PITViolationError):
        AsOf(datetime.now(UTC) + timedelta(days=365))


def test_pit_guard_drops_future_rows() -> None:
    df = _frame(["2024-07-01 00:00", "2024-07-02 00:00", "2024-07-03 00:00"])
    out = pit_guard(df, AsOf(datetime(2024, 7, 2, tzinfo=UTC)))
    assert len(out) == 2  # 07-03 ingest is after as_of -> dropped


def test_pit_guard_requires_ingest_ts() -> None:
    with pytest.raises(PITViolationError):
        pit_guard(pd.DataFrame({"close": [1.0]}), AsOf(datetime(2024, 7, 2, tzinfo=UTC)))


def test_pit_guard_rejects_null_ingest() -> None:
    df = _frame(["2024-07-01 00:00"])
    df.loc[df.index[0], "ingest_ts"] = pd.NaT
    with pytest.raises(PITViolationError):
        pit_guard(df, AsOf(datetime(2024, 7, 2, tzinfo=UTC)))
