"""Frozen, operator-signed gate thresholds — the conservative ADR-§8 standard (one source of truth).

A loosened threshold defeats the gate (ADR §0: the gate's job is to KILL). Every value was signed at
the Increment-5 operator checkpoint (2026-06-23) and is the conservative ADR-§8 / textbook value.
A test pins each value so a silent drift fails the suite; never edit one to manufacture a survivor.
"""

from __future__ import annotations

from typing import Final

# --- per-strategy probability hurdles (Bailey & López de Prado 2014) ---
#: DSR as the strict single-statistic probability: "Deflated Sharpe > 0 at the 5% level" (ADR §8).
DSR_THRESHOLD: Final[float] = 0.95
#: PSR(0) > 0.95 — the probability the true Sharpe exceeds 0 (ADR §8).
PSR_THRESHOLD: Final[float] = 0.95

# --- family / selection-level hurdles ---
#: Probability of Backtest Overfitting (CSCV, Bailey-Borwein-LdP-Zhu 2015): accept iff PBO < 0.5.
PBO_THRESHOLD: Final[float] = 0.5
#: Hansen (2005) SPA: the best candidate is significant iff its bootstrap p-value < 0.05.
SPA_ALPHA: Final[float] = 0.05

# --- walk-forward OOS criterion (ADR §8 walk-forward 12/3/3) ---
#: >= 60% of OOS folds must be positive (ADR §8).
WF_MIN_FRACTION_FOLDS: Final[float] = 0.60
WF_TRAIN_MONTHS: Final[int] = 12
WF_TEST_MONTHS: Final[int] = 3
WF_STEP_MONTHS: Final[int] = 3
#: A ratio on < 2 OOS folds is noise — require at least this many folds.
MIN_FOLDS: Final[int] = 2

# --- small-sample floor (ADR §8: ratios are noise below a trade-count floor) ---
#: Minimum OOS observations for a Sharpe statistic to be admissible (mirrors Inc-4 MIN_OOS_BARS).
MIN_OOS_BARS: Final[int] = 60

# --- conservative-live-cost veto (ADR §8 2x/3x cost stress) ---
#: DSR/PSR/WF must still pass with cost scaled by EACH of these (cost_scale stress handle is >= 1).
COST_STRESS_SCALES: Final[tuple[float, ...]] = (2.0, 3.0)

# --- family assembly (operator-signed: a lone candidate is structurally un-allocatable) ---
#: PBO/SPA are undefined for a single candidate; require a family of at least this many.
MIN_FAMILY_SIZE: Final[int] = 2

# --- deterministic bootstrap / CSCV parameters ---
#: Hansen SPA stationary-bootstrap resample count.
BOOTSTRAP_B: Final[int] = 2000
#: Fixed RNG seed so the bootstrap is fully deterministic (reproducible verdicts).
BOOTSTRAP_SEED: Final[int] = 0
#: CSCV partitions the OOS timeline into this many even blocks (half in-sample / half out).
CSCV_BLOCKS: Final[int] = 16
