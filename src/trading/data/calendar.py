"""Exchange-calendar / RTH / tz authority — XNYS, ``side='left'`` (half-open ``[open, close)``).

The SOLE source of session/RTH truth: a vendor's bar timestamps are never trusted for session
logic. UTC end-to-end; America/New_York is display-only. ``get_calendar`` is AST-banned
elsewhere in ``data/`` (STEP 8), mirroring the broker's paper-only pin — one calendar, one
boundary convention. ``side='left'`` makes the open minute a trading minute and the close
minute NOT, closing the close-bar off-by-one by construction.
"""

from __future__ import annotations

from typing import Final

import exchange_calendars as xcals
import numpy as np
import numpy.typing as npt
import pandas as pd

from trading.data.errors import CalendarError

SESSION: Final[str] = "XNYS"
DISPLAY_TZ: Final[str] = "America/New_York"

XNYS: Final = xcals.get_calendar(SESSION, side="left")


def assert_utc(index: pd.DatetimeIndex) -> None:
    """Raise ``CalendarError`` unless the index is tz-aware UTC (never trust tz-naive)."""
    if index.tz is None or str(index.tz) != "UTC":
        raise CalendarError(f"index must be tz-aware UTC, got tz={index.tz!r}")


def session_for(ts: pd.Timestamp) -> pd.Timestamp:
    """The trading session a UTC minute belongs to (``direction='previous'`` — never future)."""
    return XNYS.minute_to_session(ts, direction="previous")


def as_of_session(as_of_ts: pd.Timestamp) -> pd.Timestamp:
    """The most recent session at or before ``as_of`` (never a future session)."""
    return XNYS.minute_to_session(as_of_ts, direction="previous")


def session_close(session: pd.Timestamp) -> pd.Timestamp:
    return XNYS.session_close(session)


def daily_bar_visible(session: pd.Timestamp, as_of_ts: pd.Timestamp) -> bool:
    """A daily bar is visible only once its session has CLOSED at or before ``as_of``."""
    return bool(XNYS.session_close(session) <= as_of_ts)


def rth_mask(index: pd.DatetimeIndex) -> npt.NDArray[np.bool_]:
    """Vectorized mask: True where the UTC minute is a trading minute (half-open [open, close))."""
    assert_utc(index)
    if len(index) == 0:
        return np.zeros(0, dtype=bool)
    trading = XNYS.minutes_in_range(index.min(), index.max())
    return np.asarray(index.isin(trading), dtype=bool)


def to_display(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Convert a UTC index to the display tz (America/New_York). Display only — never gating."""
    assert_utc(index)
    return index.tz_convert(DISPLAY_TZ)
