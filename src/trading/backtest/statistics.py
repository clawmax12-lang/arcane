"""Backtest statistics — COMPUTE-AND-REPORT ONLY (the Inc-4/Inc-5 boundary).

Pure reductions over a realized-returns series: annualized Sharpe (ddof=1, sqrt(252), zero rf),
total/annualized return, max drawdown, average turnover, per-fold OOS positivity. Every reduction
masks non-finite inputs and returns NaN (never 0 or inf) on a degenerate window (empty, flat, or a
total wipeout), so a noisy fold can never masquerade as a real number.

``BacktestResult`` is a FROZEN container of RAW statistics with NO ``passed`` / ``accepted`` /
``allocated`` / ``verdict`` field: Inc-4 NEVER applies an ADR §8 threshold or an accept/kill call
(that is the Increment-5 bias gate). A committed AST name-ban test forbids any bias-gate symbol
(``deflated``/``dsr``/``reality_check``/``pbo``/``psr``/``allocated``/``accept``/``kill``/``verdict``)
anywhere in this package, so the boundary cannot be crossed by accident.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt
import pandas as pd

TRADING_DAYS_PER_YEAR: Final[int] = 252


def _finite(series: pd.Series) -> npt.NDArray[np.float64]:
    """The finite (non-NaN, non-inf) values of a series as a float64 array."""
    arr: npt.NDArray[np.float64] = series.to_numpy(dtype="float64", na_value=np.nan)
    return arr[np.isfinite(arr)]


def annualized_sharpe(returns: pd.Series, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    """Annualized Sharpe (ddof=1, zero rf); NaN on < 2 points or a zero-variance window."""
    r = _finite(returns)
    if r.size < 2:
        return float("nan")
    sd = float(r.std(ddof=1))
    if not np.isfinite(sd) or sd == 0.0:
        return float("nan")
    return float(r.mean() / sd * np.sqrt(periods_per_year))


def total_return(returns: pd.Series) -> float:
    """Cumulative compounded return; NaN on an empty window."""
    r = _finite(returns)
    if r.size == 0:
        return float("nan")
    return float(np.prod(1.0 + r) - 1.0)


def annualized_return(returns: pd.Series, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    """CAGR = (1 + total) ** (ppy / n) - 1; NaN on an empty window or a total wipeout (<= -100%)."""
    r = _finite(returns)
    if r.size == 0:
        return float("nan")
    growth = float(np.prod(1.0 + r))
    if growth <= 0.0:  # a total wipeout: CAGR is undefined (no real fractional power of <= 0)
        return float("nan")
    return float(growth ** (periods_per_year / r.size) - 1.0)


def max_drawdown(returns: pd.Series) -> float:
    """Worst peak-to-trough of the compounded equity curve (<= 0); NaN on an empty window."""
    r = _finite(returns)
    if r.size == 0:
        return float("nan")
    equity = np.cumprod(1.0 + r)
    running_max = np.maximum.accumulate(equity)
    return float((equity / running_max - 1.0).min())


def average_turnover(turnover: pd.Series) -> float:
    """Mean per-bar turnover; NaN on an empty series."""
    t = _finite(turnover)
    if t.size == 0:
        return float("nan")
    return float(t.mean())


def fraction_positive(values: Sequence[float]) -> float:
    """Fraction of finite values that are strictly positive; NaN if none are finite."""
    finite = [v for v in values if v == v and v not in (float("inf"), float("-inf"))]
    if not finite:
        return float("nan")
    return sum(1 for v in finite if v > 0.0) / len(finite)


@dataclass(frozen=True, slots=True)
class BacktestResult:
    """A frozen, statistics-ONLY backtest artifact (no accept/kill verdict — the Inc-5 boundary).

    The un-prefixed headline stats (``total_return``, ``annualized_return``, ``annualized_sharpe``,
    ``max_drawdown``) are FULL-SAMPLE descriptive (train + OOS blended). The ``oos_*`` stats and
    ``per_fold_oos_sharpe`` are the train-free OUT-OF-SAMPLE edge evidence (ADR §0: walk-forward OOS
    is the primary evidence). A reader / the Inc-5 consumer must read ``oos_*``, never the blended
    headline, as the edge metric.
    """

    spec_hash: str
    cost_model_id: str
    n_bars: int
    total_return: float
    annualized_return: float
    annualized_sharpe: float
    max_drawdown: float
    average_turnover: float
    #: OUT-OF-SAMPLE edge stats over the concatenated fold test windows (the honest edge metric).
    oos_total_return: float
    oos_annualized_sharpe: float
    oos_max_drawdown: float
    per_fold_oos_sharpe: tuple[float, ...]
    fraction_folds_positive: float
    #: live, fail-closed read from the SHARED trial ledger at eval time (the Inc-5 DSR/M18 input).
    n_trials_at_eval: int
    #: provenance from the non-PIT operator universe; Inc-5's T2 must read these, not a clean pass.
    survivorship_biased: bool
    survivorship_unverified: bool
    #: ADR §8 small-sample floor — REPORTED, never used to gate (ratios are noise below a floor).
    enough_samples: bool
    train_months: int
    test_months: int
    step_months: int
    anchored: bool
    #: the net (after-cost) compounded equity curve, for inspection.
    equity_curve: tuple[float, ...]
