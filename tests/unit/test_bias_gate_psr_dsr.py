"""C6 — PSR + DSR + cross-trial variance (Bailey & López de Prado 2014), fail-closed at the tails.

PSR(0) is the probability the true (per-obs) Sharpe exceeds 0. DSR deflates the hurdle by the
expected max Sharpe over ``N`` trials (multiple-testing). Every degenerate input (T<60, ruin, zero
variance, denom<=0, N<1) yields NaN so the positive-form threshold (``metric > 0.95``, applied by
the composer) KILLs — never a NaN-comparison fail-open.
"""

from __future__ import annotations

import math

import numpy as np

from trading.bias_gate.stats import (
    _prob_above,
    cross_trial_variance,
    dsr_probability,
    expected_max_sharpe,
    per_obs_sharpe,
    psr_probability,
)
from trading.bias_gate.thresholds import MIN_OOS_BARS


def _series(mean: float, std: float, n: int, seed: int) -> list[float]:
    rng = np.random.default_rng(seed)
    return [float(x) for x in rng.normal(mean, std, n)]


# --- per_obs_sharpe ---


def test_per_obs_sharpe_basic_and_degenerate() -> None:
    r = _series(0.01, 0.01, 300, seed=1)
    sr = per_obs_sharpe(r)
    assert 0.5 < sr < 1.6  # ~1.0 per-obs
    assert math.isnan(per_obs_sharpe([0.01] * 100))  # zero variance
    assert math.isnan(per_obs_sharpe([0.01]))  # < 2 points


# --- PSR ---


def test_psr_high_for_a_strong_edge() -> None:
    psr = psr_probability(_series(0.01, 0.01, 300, seed=2))
    assert psr > 0.95


def test_psr_low_for_a_negative_mean_series() -> None:
    psr = psr_probability(_series(-0.01, 0.01, 300, seed=3))
    assert psr < 0.05  # clearly fails the > 0.95 hurdle


def test_psr_fails_closed_on_short_sample() -> None:
    assert math.isnan(psr_probability(_series(0.01, 0.01, MIN_OOS_BARS - 1, seed=4)))


def test_psr_fails_closed_on_ruin() -> None:
    r = _series(0.01, 0.01, 300, seed=5)
    r[150] = -1.5  # an account-zeroing bar
    assert math.isnan(psr_probability(r))


def test_psr_fails_closed_on_zero_variance() -> None:
    assert math.isnan(psr_probability([0.001] * 300))


# --- the denom<=0 branch (probe the moment tail directly) ---


def test_prob_above_fails_closed_on_nonpositive_denominator() -> None:
    # denom = 1 - skew*SR + (kurt-1)/4*SR^2 ; choose SR=2, skew=1, kurt=1 -> denom = 1-2+0 = -1
    assert math.isnan(_prob_above(sr_hat=2.0, sr_star=0.0, skew=1.0, kurt=1.0, n_obs=300))


def test_prob_above_normal_case_is_a_probability() -> None:
    p = _prob_above(sr_hat=0.1, sr_star=0.0, skew=0.0, kurt=3.0, n_obs=300)
    assert 0.0 < p < 1.0


# --- expected max Sharpe (the deflation hurdle) grows with N ---


def test_expected_max_sharpe_grows_with_n() -> None:
    v = 0.01
    s2 = expected_max_sharpe(2, v)
    s100 = expected_max_sharpe(100, v)
    s10000 = expected_max_sharpe(10_000, v)
    assert 0.0 <= s2 < s100 < s10000
    assert expected_max_sharpe(1, v) == 0.0  # N=1: no deflation (never call Phi^-1(0))


def test_expected_max_sharpe_fails_closed() -> None:
    assert math.isnan(expected_max_sharpe(0, 0.01))  # N<1
    assert math.isnan(expected_max_sharpe(100, 0.0))  # V<=0
    assert math.isnan(expected_max_sharpe(100, -1.0))


# --- cross-trial variance: floored at the analytic null ---


def test_cross_trial_variance_floors_at_v_null() -> None:
    r = _series(0.01, 0.01, 300, seed=6)
    v_no_family = cross_trial_variance(r, ())  # only V_null
    assert v_no_family > 0.0
    # a widely dispersed family raises V (V_obs > V_null)
    dispersed = (0.05, 0.5, -0.4, 0.3)
    v_family = cross_trial_variance(r, dispersed)
    assert v_family >= v_no_family
    assert v_family >= float(np.var(dispersed, ddof=1)) - 1e-12


# --- DSR ---


def test_dsr_equals_psr_when_n_is_one() -> None:
    r = _series(0.01, 0.01, 300, seed=7)
    assert dsr_probability(r, 1, ()) == psr_probability(r)


def test_dsr_is_deflated_below_psr_for_many_trials() -> None:
    # a MARGINAL edge (a strong edge saturates both probs at Φ→1.0 and the gap is invisible).
    r = _series(0.003, 0.012, 300, seed=8)
    psr = psr_probability(r)
    dsr_many = dsr_probability(r, 1000, ())
    assert psr < 1.0  # not saturated, so the deflation gap is observable
    assert dsr_many < psr  # the deflation bites


def test_dsr_is_monotonic_nonincreasing_in_n() -> None:
    r = _series(0.012, 0.01, 300, seed=9)
    d1 = dsr_probability(r, 1, ())
    d10 = dsr_probability(r, 10, ())
    d1000 = dsr_probability(r, 1000, ())
    assert d1 >= d10 >= d1000


def test_dsr_kills_when_sharpe_below_the_deflated_hurdle() -> None:
    # a marginal edge against a huge trial count -> SR_hat <= SR0 -> DSR <= 0.5 -> KILL
    r = _series(0.0015, 0.01, 300, seed=10)
    assert dsr_probability(r, 100_000, ()) <= 0.5


def test_dsr_fails_closed_on_degenerate_inputs() -> None:
    r = _series(0.01, 0.01, 300, seed=11)
    assert math.isnan(dsr_probability(r, 0, ()))  # N<1
    assert math.isnan(dsr_probability(_series(0.01, 0.01, 40, seed=12), 10, ()))  # T<60
    ruin = _series(0.01, 0.01, 300, seed=13)
    ruin[10] = -2.0
    assert math.isnan(dsr_probability(ruin, 10, ()))  # ruin
