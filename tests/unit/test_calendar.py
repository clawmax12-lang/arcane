"""Golden tests for the calendar / RTH / tz authority (Increment 2 STEP 3).

Pins the half-open ``[open, close)`` boundary on a half-day, DST open shifts, and the
PIT-safe daily-visibility rule. These are the exact spots a backtest gets silently poisoned.
"""

from __future__ import annotations

import pandas as pd
import pytest

from trading.data import calendar as cal
from trading.data.errors import CalendarError


def _utc(*stamps: str) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(list(stamps), utc=True))


def test_assert_utc_rejects_naive() -> None:
    with pytest.raises(CalendarError):
        cal.assert_utc(pd.DatetimeIndex(pd.to_datetime(["2024-07-01 13:30"])))


def test_assert_utc_rejects_non_utc() -> None:
    idx = pd.DatetimeIndex(pd.to_datetime(["2024-07-01 09:30"])).tz_localize("America/New_York")
    with pytest.raises(CalendarError):
        cal.assert_utc(idx)


def test_assert_utc_accepts_utc() -> None:
    cal.assert_utc(_utc("2024-07-01 13:30"))  # must not raise


def test_early_close_is_half_open() -> None:
    # 2024-07-03 early close 13:00 ET = 17:00 UTC; side='left' -> 17:00 is NOT a trading minute.
    mask = cal.rth_mask(_utc("2024-07-03 13:30", "2024-07-03 16:59", "2024-07-03 17:00"))
    assert mask.tolist() == [True, True, False]


def test_dst_open_shifts() -> None:
    # EST (winter): 09:30 ET open = 14:30 UTC. EDT (summer): 09:30 ET open = 13:30 UTC.
    assert cal.rth_mask(_utc("2024-01-02 14:30", "2024-01-02 14:29")).tolist() == [True, False]
    assert cal.rth_mask(_utc("2024-07-01 13:30", "2024-07-01 13:29")).tolist() == [True, False]


def test_daily_bar_visible_only_after_close() -> None:
    session = cal.session_for(pd.Timestamp("2024-07-03 14:00", tz="UTC"))
    close = pd.Timestamp("2024-07-03 17:00", tz="UTC")
    assert cal.daily_bar_visible(session, close) is True
    assert cal.daily_bar_visible(session, close - pd.Timedelta(minutes=1)) is False


def test_session_for_label() -> None:
    assert cal.session_for(pd.Timestamp("2024-07-01 15:00", tz="UTC")) == pd.Timestamp("2024-07-01")


def test_to_display_converts_to_ny() -> None:
    out = cal.to_display(_utc("2024-07-01 13:30"))
    assert str(out.tz) == "America/New_York"
    assert out[0].hour == 9 and out[0].minute == 30  # 13:30 UTC == 09:30 EDT


def test_empty_index_rth_mask() -> None:
    assert cal.rth_mask(_utc()).tolist() == []
