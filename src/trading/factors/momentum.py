"""Momentum factors — trailing price-return signals (Jegadeesh-Titman family).

Each ``_raw`` is a trailing log return; positive ``.shift(n)`` is a LOOKBACK offset (close ``n``
bars ago), never an output-alignment shift (the base owns the single ``shift(1)``).
"""

from __future__ import annotations

from typing import ClassVar

import pandas as pd

from trading.factors._util import log_return, log_safe
from trading.factors.base import AlphaFactor


class Mom21d(AlphaFactor):
    id: ClassVar[str] = "mom_21d"
    family: ClassVar[str] = "momentum"
    rationale: ClassVar[str] = "1-month trailing price momentum (Jegadeesh-Titman)."
    raw_lookback: ClassVar[int] = 21

    def _raw(self, df: pd.DataFrame) -> pd.Series:
        return log_return(df["close"], 21)


class Mom63d(AlphaFactor):
    id: ClassVar[str] = "mom_63d"
    family: ClassVar[str] = "momentum"
    rationale: ClassVar[str] = "3-month intermediate momentum (trend-continuation horizon)."
    raw_lookback: ClassVar[int] = 63

    def _raw(self, df: pd.DataFrame) -> pd.Series:
        return log_return(df["close"], 63)


class Mom126Skip21(AlphaFactor):
    id: ClassVar[str] = "mom_126_skip21"
    family: ClassVar[str] = "momentum"
    rationale: ClassVar[str] = "6-month return skipping the recent 1 month (removes ST reversal)."
    raw_lookback: ClassVar[int] = 147

    def _raw(self, df: pd.DataFrame) -> pd.Series:
        lc = log_safe(df["close"])
        return lc.shift(21) - lc.shift(147)
