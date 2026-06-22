"""Volatility factors — trailing realized volatility and average true range."""

from __future__ import annotations

from typing import ClassVar

import pandas as pd

from trading.factors._util import log_return
from trading.factors.base import AlphaFactor


class Vol21d(AlphaFactor):
    id: ClassVar[str] = "vol_21d"
    family: ClassVar[str] = "volatility"
    rationale: ClassVar[str] = "Trailing 21-day realized volatility of daily log returns (low-vol)."
    raw_lookback: ClassVar[int] = 22

    def _raw(self, df: pd.DataFrame) -> pd.Series:
        lr = log_return(df["close"], 1)
        return lr.rolling(21, min_periods=21).std(ddof=1)


class Atr14(AlphaFactor):
    id: ClassVar[str] = "atr_14"
    family: ClassVar[str] = "volatility"
    rationale: ClassVar[str] = "Wilder Average True Range / close — gap-aware trailing range."
    raw_lookback: ClassVar[int] = 15

    def _raw(self, df: pd.DataFrame) -> pd.Series:
        high = df["high"].astype("float64")
        low = df["low"].astype("float64")
        close = df["close"].astype("float64")
        prev_close = close.shift(1)  # trailing lookback; skipna max => row 0 falls back to high-low
        true_range = pd.concat(
            [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
        ).max(axis=1)
        atr = true_range.rolling(14, min_periods=14).mean()
        return (atr / close).where(close > 0)
