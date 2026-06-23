"""C1 — the gate thresholds are the operator-signed conservative ADR-§8 standard (frozen constants).

A loosened threshold defeats the gate (ADR §0). These constants are the single source of truth and
must match the operator checkpoint verbatim; a test pins each so a silent drift fails the suite.
"""

from __future__ import annotations

from trading.bias_gate import thresholds as T


def test_threshold_values_match_the_operator_signed_standard() -> None:
    assert T.DSR_THRESHOLD == 0.95
    assert T.PSR_THRESHOLD == 0.95
    assert T.PBO_THRESHOLD == 0.5
    assert T.SPA_ALPHA == 0.05
    assert T.WF_MIN_FRACTION_FOLDS == 0.60
    assert T.MIN_OOS_BARS == 60
    assert T.MIN_FOLDS == 2
    assert T.COST_STRESS_SCALES == (2.0, 3.0)
    assert T.MIN_FAMILY_SIZE == 2
    assert T.WF_TRAIN_MONTHS == 12
    assert T.WF_TEST_MONTHS == 3
    assert T.WF_STEP_MONTHS == 3


def test_bootstrap_and_cscv_params_are_deterministic_and_bounded() -> None:
    assert T.BOOTSTRAP_B == 2000
    assert T.BOOTSTRAP_SEED == 0
    assert T.CSCV_BLOCKS == 16
    assert T.CSCV_BLOCKS % 2 == 0  # CSCV needs an even block count (half in / half out)


def test_thresholds_are_in_sane_ranges() -> None:
    assert 0.5 < T.DSR_THRESHOLD < 1.0
    assert 0.5 < T.PSR_THRESHOLD < 1.0
    assert 0.0 < T.PBO_THRESHOLD <= 0.5  # conservative: overfit prob must be below half
    assert 0.0 < T.SPA_ALPHA <= 0.05
    assert 0.5 <= T.WF_MIN_FRACTION_FOLDS <= 1.0
