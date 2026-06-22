"""Range / trend-location factors — intrabar range, close location, SMA distance & ratio.

``close_loc_in_range`` is the only SAME-BAR factor (no lookback): it reads where the close sits in
the bar's own high-low range. The base's single ``shift(1)`` then publishes that location at ``t``
using only data ``<= t-1`` — so the author must NOT pre-shift it.
"""

from __future__ import annotations

from typing import ClassVar

import pandas as pd

from trading.factors.base import AlphaFactor


class HlRange21d(AlphaFactor):
    id: ClassVar[str] = "hl_range_21d"
    family: ClassVar[str] = "range"
    rationale: ClassVar[str] = "Trailing 21-day mean of (high-low)/close (Parkinson-style range)."
    raw_lookback: ClassVar[int] = 21

    def _raw(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"].astype("float64")
        hl = df["high"].astype("float64") - df["low"].astype("float64")
        rng = (hl / close).where(close > 0)
        return rng.rolling(21, min_periods=21).mean()


class CloseLocInRange(AlphaFactor):
    id: ClassVar[str] = "close_loc_in_range"
    family: ClassVar[str] = "range"
    rationale: ClassVar[str] = "Close location within the bar's range (Williams %R / stoch %K)."
    raw_lookback: ClassVar[int] = 0

    def _raw(self, df: pd.DataFrame) -> pd.Series:
        high = df["high"].astype("float64")
        low = df["low"].astype("float64")
        close = df["close"].astype("float64")
        span = high - low
        return ((close - low) / span).where(span > 0)  # high==low (=>close) => NaN, never inf


class DistFromSma50(AlphaFactor):
    id: ClassVar[str] = "dist_from_sma_50"
    family: ClassVar[str] = "range"
    rationale: ClassVar[str] = "Distance of close from its trailing 50-day SMA (trend stretch)."
    raw_lookback: ClassVar[int] = 50

    def _raw(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"].astype("float64")
        sma = close.rolling(50, min_periods=50).mean()
        return ((close - sma) / sma).where(sma > 0)


class SmaRatio2050(AlphaFactor):
    id: ClassVar[str] = "sma_ratio_20_50"
    family: ClassVar[str] = "range"
    rationale: ClassVar[str] = "Fast/slow trailing SMA ratio, 20 vs 50 (golden/death-cross state)."
    raw_lookback: ClassVar[int] = 50

    def _raw(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"].astype("float64")
        fast = close.rolling(20, min_periods=20).mean()
        slow = close.rolling(50, min_periods=50).mean()
        return (fast / slow - 1.0).where(slow > 0)
