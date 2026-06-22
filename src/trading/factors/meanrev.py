"""Mean-reversion factors — short-horizon return-reversal signals (Lehmann; Lo-MacKinlay)."""

from __future__ import annotations

from typing import ClassVar

import pandas as pd

from trading.factors._util import log_return
from trading.factors.base import AlphaFactor


class Reversal5d(AlphaFactor):
    id: ClassVar[str] = "reversal_5d"
    family: ClassVar[str] = "meanrev"
    rationale: ClassVar[str] = "Short-horizon mean reversion: negated 5-day return (oversold)."
    raw_lookback: ClassVar[int] = 5

    def _raw(self, df: pd.DataFrame) -> pd.Series:
        return -log_return(df["close"], 5)
