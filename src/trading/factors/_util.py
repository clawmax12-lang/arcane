"""Trailing-only, NaN-safe helpers for factor ``_raw`` implementations.

Every helper uses ONLY same-bar or trailing (positive-offset) data, and maps undefined results to
``NaN`` (never ``-inf``, never a fabricated fill), so a factor built from them is prefix-stable and
its undefined cells stay honest holes the base's GUARD B accepts (a ``+/-inf`` would be rejected).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def log_safe(price: pd.Series) -> pd.Series:
    """Natural log of a price; ``NaN`` (never ``-inf``) where ``price <= 0`` (fail-closed)."""
    p = price.astype("float64")
    # mask <=0 (and NaN) to NaN BEFORE the log so log(0)'s -inf can never reach the base.
    return np.log(p.where(p > 0))


def log_return(close: pd.Series, periods: int) -> pd.Series:
    """Trailing ``periods``-bar log return ``log(close_t) - log(close_{t-periods})``."""
    lc = log_safe(close)
    return lc - lc.shift(periods)
