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

import itertools
import math
from collections.abc import Sequence
from typing import Final

import numpy as np
import numpy.typing as npt

from trading.bias_gate._normal import norm_cdf, norm_ppf
from trading.bias_gate.thresholds import BOOTSTRAP_B, BOOTSTRAP_SEED, CSCV_BLOCKS, MIN_OOS_BARS

#: A 2-D float matrix (T_obs rows × S strategies) of aligned per-obs OOS net returns.
Matrix = npt.NDArray[np.float64]

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


# --- C7: family/selection-level judges (PBO via CSCV, conservative SPA) ---


#: A clean family matrix must be finite and ruin-free before any family judge trusts it.
def _matrix_is_admissible(matrix: Matrix, *, min_strategies: int) -> bool:
    if matrix.ndim != 2:
        return False
    n_obs, n_strat = matrix.shape
    if n_strat < min_strategies or n_obs < MIN_OOS_BARS:
        return False
    if not bool(np.isfinite(matrix).all()):
        return False
    if bool((matrix <= _RUIN).any()):
        return False
    # Reject ANY constant column (red-team TT-1): a constant-NONZERO series has a per-obs Sharpe of
    # NaN, but ``np.std`` leaves ~1e-16 (not bit-zero) so an exact ``omega==0`` guard misses it,
    # SPA/PBO silently PASS. A constant column is degenerate (no variation) — fail closed for the
    # whole family. Mirrors the ``min == max`` constant detector in ``_moments``.
    return not bool((matrix.max(axis=0) == matrix.min(axis=0)).any())


def _column_sharpes(block: Matrix) -> Matrix:
    """Per-column per-obs Sharpe over the block rows; NaN where the column is flat (sd==0)."""
    mu = block.mean(axis=0)
    sd = block.std(axis=0, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        sharpe = mu / sd
    sharpe[sd == 0.0] = np.nan
    out: Matrix = np.asarray(sharpe, dtype="float64")
    return out


def _cscv_block_indices(n_obs: int) -> list[npt.NDArray[np.intp]] | None:
    """Partition rows into the largest even count of blocks (<= CSCV_BLOCKS), each >= 2 rows."""
    largest_even = min(CSCV_BLOCKS, (n_obs // 2) * 2)
    for k in range(largest_even, 1, -2):
        if n_obs // k >= 2:
            return [np.asarray(b, dtype=np.intp) for b in np.array_split(np.arange(n_obs), k)]
    return None


def pbo_fraction(perf_matrix: Matrix) -> float:
    """Probability of Backtest Overfitting via CSCV; NaN ⇒ KILL (S<2 / T<60 / non-finite / ruin).

    The fraction of combinatorially-symmetric splits where the in-sample-best strategy ranks at or
    below the OOS median (logit ``ω <= 0``). High PBO ⇒ the selection is overfit. Accept iff < 0.5.
    """
    matrix = np.asarray(perf_matrix, dtype="float64")
    if not _matrix_is_admissible(matrix, min_strategies=2):
        return float("nan")
    _, n_strat = matrix.shape
    blocks = _cscv_block_indices(matrix.shape[0])
    if blocks is None:
        return float("nan")
    k = len(blocks)
    lo, hi = 1.0 / (n_strat + 1), n_strat / (n_strat + 1)  # rank clip (avoid ±inf logits)
    overfit = 0
    valid = 0
    for combo in itertools.combinations(range(k), k // 2):
        is_set = set(combo)
        is_rows = np.concatenate([blocks[i] for i in combo])
        oos_rows = np.concatenate([blocks[i] for i in range(k) if i not in is_set])
        is_sh = _column_sharpes(matrix[is_rows])
        oos_sh = _column_sharpes(matrix[oos_rows])
        valid_mask = np.isfinite(is_sh) & np.isfinite(oos_sh)
        if int(valid_mask.sum()) < 2:
            continue
        valid += 1
        n_star = int(np.argmax(np.where(valid_mask, is_sh, -np.inf)))
        valid_oos = oos_sh[valid_mask]
        less = int((valid_oos < oos_sh[n_star]).sum())
        rel = (less + 1) / (valid_oos.size + 1)
        rel = min(max(rel, lo), hi)
        omega = math.log(rel / (1.0 - rel))
        if omega <= 0.0:
            overfit += 1
    if valid == 0:
        return float("nan")
    return overfit / valid


def _stationary_bootstrap_indices(
    n_obs: int, n_boot: int, mean_block_len: int, rng: np.random.Generator
) -> npt.NDArray[np.intp]:
    """Politis-Romano stationary-bootstrap row indices, shape (n_boot, n_obs), wrap-around."""
    p = 1.0 / mean_block_len
    new_block = rng.random((n_boot, n_obs)) < p
    new_block[:, 0] = True
    starts = rng.integers(0, n_obs, size=(n_boot, n_obs))
    pos = np.broadcast_to(np.arange(n_obs), (n_boot, n_obs))
    idx_ff = np.maximum.accumulate(np.where(new_block, pos, 0), axis=1)
    block_start_value = np.take_along_axis(starts, idx_ff, axis=1)
    offset = pos - idx_ff
    out: npt.NDArray[np.intp] = (block_start_value + offset) % n_obs
    return out


def spa_pvalue(
    perf_matrix: Matrix, *, n_bootstrap: int = BOOTSTRAP_B, seed: int = BOOTSTRAP_SEED
) -> float:
    """Hansen (2005) SPA p-value, conservative least-favorable recentering; NaN ⇒ KILL.

    Tests whether the BEST candidate's OOS mean beats a zero benchmark after the full search. The
    least-favorable (studentized Reality-Check) recentering centers EVERY model at its sample mean —
    harder to pass than SPA_c, the SAFE direction for a KILL-gate. Fail-closed on S<2, T<60, any
    constant column, ruin, or a non-finite matrix. Accept (family) iff p < 0.05.
    """
    matrix = np.asarray(perf_matrix, dtype="float64")
    # SPA over a single candidate is meaningless (no "best of N" to test) — require >= 2 (FC-3),
    # matching pbo_fraction; a lone S=1 family is already short-circuited by evaluate_family.
    if not _matrix_is_admissible(matrix, min_strategies=2):
        return float("nan")
    n_obs = matrix.shape[0]
    rng = np.random.default_rng(seed)
    mean_block_len = math.ceil(math.sqrt(n_obs))
    idx = _stationary_bootstrap_indices(n_obs, n_bootstrap, mean_block_len, rng)
    boot_means = matrix[idx].mean(axis=1)  # (B, S)
    d_bar = matrix.mean(axis=0)  # (S,)
    omega = np.sqrt(n_obs * boot_means.var(axis=0, ddof=0))  # (S,)
    if not bool(np.isfinite(omega).all()) or bool((omega == 0.0).any()):
        return float("nan")
    root_t = math.sqrt(n_obs)
    v_obs = max(0.0, float((root_t * d_bar / omega).max()))
    z = root_t * (boot_means - d_bar) / omega  # (B, S), null-centered (least favorable)
    v_boot = np.maximum(0.0, z.max(axis=1))  # (B,)
    return float((v_boot >= v_obs).mean())
