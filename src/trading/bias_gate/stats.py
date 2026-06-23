"""The statistical judges — PSR / DSR / cross-trial variance (Bailey & López de Prado 2014).

Pure functions over a per-observation OOS net-return sequence. Each returns a probability in (0, 1)
or **NaN** on any degenerate input (T below the floor, ruin, zero variance, a non-positive PSR
denominator, N < 1, V <= 0). The composer applies the POSITIVE-form threshold ``metric > THRESHOLD``
so a NaN metric is KILLED automatically (never a De-Morgan fail-open). The Sharpe here is
PER-OBSERVATION (``mean/std``, ``ddof=1``) — NEVER the annualized ``BacktestResult`` field, which
would inflate ``SR_hat`` ~16× and pass everything (the cardinal fail-open, MR-2). Skew/kurtosis are
population moments (the SciPy ``bias=True`` convention); kurtosis is NON-excess (normal = 3).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Final

import numpy as np
import numpy.typing as npt

from trading.bias_gate._normal import norm_cdf, norm_ppf
from trading.bias_gate.thresholds import MIN_OOS_BARS

#: Euler-Mascheroni constant — the expected-max-of-N-Gaussians deflation coefficient.
_EULER_GAMMA: Final[float] = 0.5772156649015329
#: A per-bar return <= -1.0 zeroes the account (ruin); past it every moment is fictional.
_RUIN: Final[float] = -1.0

#: Accept either a plain float sequence or an already-materialized float64 array.
FloatSeq = Sequence[float] | npt.NDArray[np.float64]


def _finite_returns(oos_returns: FloatSeq) -> npt.NDArray[np.float64]:
    """The finite (non-NaN, non-inf) values of a return sequence as a float64 array."""
    arr: npt.NDArray[np.float64] = np.asarray(oos_returns, dtype="float64")
    finite: npt.NDArray[np.float64] = arr[np.isfinite(arr)]
    return finite


def _has_ruin(arr: npt.NDArray[np.float64]) -> bool:
    """True if any finite return is <= -1.0 (an account-zeroing bar)."""
    return bool((arr <= _RUIN).any())


def _moments(arr: npt.NDArray[np.float64]) -> tuple[float, float, float]:
    """Return ``(per_obs_sharpe, skew, kurtosis_nonexcess)`` or NaNs on a degenerate window."""
    if arr.size < 2:
        return (float("nan"), float("nan"), float("nan"))
    # A truly CONSTANT window has zero variance, but float mean-rounding leaves np.std at ~1e-18
    # (not bit-zero) so ``sd1 == 0`` misses it and yields an absurd ~1e15 Sharpe (fail OPEN). Detect
    # the constant case exactly via min == max before trusting the std.
    if float(arr.max()) == float(arr.min()):
        return (float("nan"), float("nan"), float("nan"))
    mu = float(arr.mean())
    sd1 = float(arr.std(ddof=1))
    if not math.isfinite(sd1) or sd1 == 0.0:
        return (float("nan"), float("nan"), float("nan"))
    centered = arr - mu
    m2 = float((centered**2).mean())  # population 2nd central moment
    if not math.isfinite(m2) or m2 <= 0.0:
        return (float("nan"), float("nan"), float("nan"))
    skew = float((centered**3).mean()) / m2**1.5
    kurt = float((centered**4).mean()) / m2**2  # non-excess (normal == 3)
    sr_hat = mu / sd1
    if not (math.isfinite(sr_hat) and math.isfinite(skew) and math.isfinite(kurt)):
        return (float("nan"), float("nan"), float("nan"))
    return (sr_hat, skew, kurt)


def per_obs_sharpe(oos_returns: FloatSeq) -> float:
    """Per-observation Sharpe ``mean/std(ddof=1)``; NaN on < 2 points or a zero-variance window."""
    return _moments(_finite_returns(oos_returns))[0]


def _prob_above(sr_hat: float, sr_star: float, skew: float, kurt: float, n_obs: int) -> float:
    """PSR-style probability that the true Sharpe exceeds ``sr_star``; NaN if denom<=0 / n_obs<2.

    ``denom = 1 - skew*SR_hat + (kurt-1)/4 * SR_hat^2`` can go non-positive on heavy tails — an
    EXPLICIT NaN there (not a ``sqrt(neg)`` accident) so the KILL is deterministic.
    """
    if n_obs < 2 or not math.isfinite(sr_hat):
        return float("nan")
    denom = 1.0 - skew * sr_hat + (kurt - 1.0) / 4.0 * sr_hat**2
    if not math.isfinite(denom) or denom <= 0.0:
        return float("nan")
    z = (sr_hat - sr_star) * math.sqrt(n_obs - 1) / math.sqrt(denom)
    if not math.isfinite(z):
        return float("nan")
    return norm_cdf(z)


def psr_probability(oos_returns: FloatSeq) -> float:
    """PSR(0): the probability the true per-obs Sharpe > 0; NaN on any degenerate window (KILL)."""
    r = _finite_returns(oos_returns)
    if r.size < MIN_OOS_BARS or _has_ruin(r):
        return float("nan")
    sr_hat, skew, kurt = _moments(r)
    return _prob_above(sr_hat, 0.0, skew, kurt, r.size)


def expected_max_sharpe(n_trials: int, variance: float) -> float:
    """The deflated benchmark Sharpe SR0 = expected max of ``N`` trial Sharpes; NaN if N<1 or V<=0.

    ``SR0 = sqrt(V) * [(1-γ)·Φ⁻¹(1 - 1/N) + γ·Φ⁻¹(1 - 1/(N·e))]`` for N>=2; 0 for N==1 (no
    deflation — never call ``Φ⁻¹(0)``). Grows with N (more trials ⇒ a higher hurdle).
    """
    if n_trials < 1 or not math.isfinite(variance) or variance <= 0.0:
        return float("nan")
    if n_trials == 1:
        return 0.0
    a = norm_ppf(1.0 - 1.0 / n_trials)
    b = norm_ppf(1.0 - 1.0 / (n_trials * math.e))
    sr0 = math.sqrt(variance) * ((1.0 - _EULER_GAMMA) * a + _EULER_GAMMA * b)
    return sr0 if math.isfinite(sr0) else float("nan")


def cross_trial_variance(oos_returns: FloatSeq, family_sharpes: Sequence[float]) -> float:
    """The DSR deflation variance V = max(V_obs, V_null); NaN if this window is degenerate.

    ``V_null = denom / (T-1)`` is the asymptotic variance of the Sharpe estimator (the analytic
    floor). ``V_obs`` is the dispersion of the family's per-obs Sharpes (>= 2 finite needed). The
    floor guarantees a near-zero family dispersion can never deflate the hurdle below the analytic
    minimum (more conservative).
    """
    r = _finite_returns(oos_returns)
    sr_hat, skew, kurt = _moments(r)
    if not math.isfinite(sr_hat) or r.size < 2:
        return float("nan")
    denom = 1.0 - skew * sr_hat + (kurt - 1.0) / 4.0 * sr_hat**2
    if not math.isfinite(denom) or denom <= 0.0:
        return float("nan")
    v_null = denom / (r.size - 1)
    finite_family = np.asarray([s for s in family_sharpes if math.isfinite(s)], dtype="float64")
    if finite_family.size >= 2:
        v_obs = float(finite_family.var(ddof=1))
        return max(v_obs, v_null)
    return v_null


def dsr_probability(oos_returns: FloatSeq, n_trials: int, family_sharpes: Sequence[float]) -> float:
    """The Deflated Sharpe Ratio probability (PSR vs the N-trial-deflated hurdle); NaN ⇒ KILL.

    Fail-closed on N<1, T below the floor, ruin, a degenerate window, V<=0, or a non-finite SR0.
    When ``SR_hat <= SR0`` the numerator is <= 0 ⇒ DSR <= 0.5 < 0.95 (deflation correctly KILLs).
    """
    if n_trials < 1:
        return float("nan")
    r = _finite_returns(oos_returns)
    if r.size < MIN_OOS_BARS or _has_ruin(r):
        return float("nan")
    sr_hat, skew, kurt = _moments(r)
    if not math.isfinite(sr_hat):
        return float("nan")
    variance = cross_trial_variance(r, family_sharpes)
    if not math.isfinite(variance) or variance <= 0.0:
        return float("nan")
    sr0 = expected_max_sharpe(n_trials, variance)
    if not math.isfinite(sr0):
        return float("nan")
    return _prob_above(sr_hat, sr0, skew, kurt, r.size)
