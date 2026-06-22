"""Volume / liquidity factors — dollar volume, relative volume, Amihud illiquidity.

Every division is NaN-guarded with ``.where(denom > 0)`` so a real thin-IEX zero-volume bar yields
``NaN`` (the honest hole), never ``+/-inf`` (which the base's GUARD B would reject) and never a
fabricated extreme.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np
import pandas as pd

from trading.factors._util import log_return
from trading.factors.base import AlphaFactor


class DollarVol21d(AlphaFactor):
    id: ClassVar[str] = "dollar_vol_21d"
    family: ClassVar[str] = "volume"
    rationale: ClassVar[str] = "Trailing 21-day average dollar volume (liquidity/size)."
    raw_lookback: ClassVar[int] = 21

    def _raw(self, df: pd.DataFrame) -> pd.Series:
        dollar_vol = df["close"].astype("float64") * df["volume"].astype("float64")
        return np.log1p(dollar_vol.rolling(21, min_periods=21).mean())


class RelVolume21d(AlphaFactor):
    id: ClassVar[str] = "rel_volume_21d"
    family: ClassVar[str] = "volume"
    rationale: ClassVar[str] = "Volume relative to its trailing 21-day average (activity spike)."
    raw_lookback: ClassVar[int] = 21

    def _raw(self, df: pd.DataFrame) -> pd.Series:
        v = df["volume"].astype("float64")
        avg = v.rolling(21, min_periods=21).mean()
        return (v / avg).where(avg > 0)  # all-zero-volume window => NaN, never inf


class AmihudIlliq21d(AlphaFactor):
    id: ClassVar[str] = "amihud_illiq_21d"
    family: ClassVar[str] = "volume"
    rationale: ClassVar[str] = "Amihud (2002) illiquidity: trailing |return|/dollar-volume."
    raw_lookback: ClassVar[int] = 22

    def _raw(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"].astype("float64")
        abs_ret = log_return(close, 1).abs()
        dollar_vol = close * df["volume"].astype("float64")
        illiq = (abs_ret / dollar_vol).where(dollar_vol > 0)  # zero-volume bar => NaN, never inf
        return np.log1p(illiq.rolling(21, min_periods=21).mean())
