"""C7 — PBO via CSCV (Bailey et al. 2015) + a conservative SPA p-value (Hansen 2005), family-level.

PBO = the probability the in-sample-best strategy ranks below the OOS median across combinatorially
symmetric train/test splits (high ⇒ overfit). SPA tests whether the BEST candidate's OOS mean beats
a zero benchmark after the full search (the multiple-testing / data-snooping question). The SPA here
uses the CONSERVATIVE least-favorable (studentized Reality-Check) recentering: harder to pass, the
SAFE direction for a KILL-gate. Both fail CLOSED on S<2, T<60, a constant column, or ruin.
"""

from __future__ import annotations

import math

import numpy as np

from trading.bias_gate.stats import pbo_fraction, spa_pvalue
from trading.bias_gate.thresholds import MIN_OOS_BARS

_T = 256


def _noise_matrix(s: int, seed: int, mean: float = 0.0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal(mean, 0.01, (_T, s)).astype("float64")


def _genuine_edge_matrix(seed: int) -> np.ndarray:
    """One strategy with a consistent positive drift; the rest are noise."""
    m = _noise_matrix(6, seed)
    rng = np.random.default_rng(seed + 1)
    m[:, 0] = rng.normal(0.004, 0.01, _T)  # a real, persistent edge in column 0
    return m


def _overfit_matrix() -> np.ndarray:
    """Strategies that WIN the first half and LOSE the second (selection is pure overfit)."""
    s = 6
    m = np.zeros((_T, s), dtype="float64")
    half = _T // 2
    for i in range(s):
        drift = 0.002 * (i + 1)
        rng = np.random.default_rng(100 + i)
        noise = rng.normal(0.0, 0.005, _T)
        m[:half, i] = drift + noise[:half]  # strong in-sample
        m[half:, i] = -drift + noise[half:]  # weak out-of-sample (anti-persistent)
    return m


# --- PBO (CSCV) ---


def test_pbo_low_for_a_genuine_persistent_edge() -> None:
    pbo = pbo_fraction(_genuine_edge_matrix(seed=1))
    assert 0.0 <= pbo < 0.5  # a persistent winner is NOT overfit


def test_pbo_high_for_an_anti_persistent_overfit_family() -> None:
    pbo = pbo_fraction(_overfit_matrix())
    assert pbo > 0.5  # IS-best is OOS-worst => overfit


def test_pbo_fails_closed_on_single_candidate() -> None:
    assert math.isnan(pbo_fraction(_noise_matrix(1, seed=2)))  # S < 2 => undefined


def test_pbo_fails_closed_on_too_few_rows() -> None:
    short = _noise_matrix(4, seed=3)[: MIN_OOS_BARS - 1]
    assert math.isnan(pbo_fraction(short))


def test_pbo_fails_closed_on_ruin() -> None:
    m = _noise_matrix(4, seed=4)
    m[10, 2] = -1.5  # an account-zeroing bar
    assert math.isnan(pbo_fraction(m))


def test_pbo_is_a_fraction() -> None:
    pbo = pbo_fraction(_noise_matrix(8, seed=5))
    assert 0.0 <= pbo <= 1.0


# --- SPA (Hansen, conservative) ---


def test_spa_significant_for_a_strong_edge() -> None:
    m = _genuine_edge_matrix(seed=6)
    p = spa_pvalue(m, n_bootstrap=500, seed=0)
    assert p < 0.05  # the genuine edge is significant after the search


def test_spa_not_significant_for_pure_noise() -> None:
    m = _noise_matrix(6, seed=7, mean=0.0)
    p = spa_pvalue(m, n_bootstrap=500, seed=0)
    assert p > 0.05  # no edge => not significant => KILL


def test_spa_is_deterministic_for_a_fixed_seed() -> None:
    m = _genuine_edge_matrix(seed=8)
    assert spa_pvalue(m, n_bootstrap=500, seed=0) == spa_pvalue(m, n_bootstrap=500, seed=0)


def test_spa_fails_closed_on_degenerate_inputs() -> None:
    assert math.isnan(spa_pvalue(_noise_matrix(6, seed=9)[: MIN_OOS_BARS - 1], n_bootstrap=200))
    assert math.isnan(spa_pvalue(np.zeros((_T, 0)), n_bootstrap=200))  # S < 1
    const = _noise_matrix(3, seed=10)
    const[:, 1] = 0.001  # a zero-variance column => omega == 0
    assert math.isnan(spa_pvalue(const, n_bootstrap=200, seed=0))
    ruin = _noise_matrix(3, seed=11)
    ruin[5, 0] = -2.0
    assert math.isnan(spa_pvalue(ruin, n_bootstrap=200, seed=0))
