"""Floor-of-floors — hardcoded safety limits that configuration can NEVER loosen.

These constants encode CLAUDE.md §8 (abandonment triggers) and the bounds of the
$50 paper experiment. They are deliberately module-level, grep-able, and immutable.
``config/risk.yaml`` may only set values that are *stricter* than these; any attempt
to set a looser value is rejected at load time (fail-closed). See ``schema.RiskConfig``.

Why a separate floor layer: a single bad edit to a YAML file must never be able to
weaken a risk limit. The YAML is operator convenience; this module is the law.
"""

from __future__ import annotations

from typing import Final

# --- Starting baseline (informational) ---
STARTING_CAPITAL_USD: Final[float] = 50.0

# --- Abandonment / hard floors (CLAUDE.md §8) ---
EQUITY_FLOOR_USD: Final[float] = 20.0  # §8.2 equity floor breach -> abandon
TOTAL_LOSS_ABANDON_USD: Final[float] = 30.0  # §8.1 project total loss -> abandon
MAX_CONSECUTIVE_SCHEDULER_ERRORS: Final[int] = 5  # §8.3

# --- Per-trade / daily ceilings (config may be stricter, never looser) ---
PER_TRADE_RISK_USD_CEILING: Final[float] = 5.0
DAILY_LOSS_USD_CEILING: Final[float] = 15.0

# --- Data freshness (M17): orders may not be placed on stale bars ---
MAX_BAR_AGE_SECONDS: Final[float] = 300.0

# --- Live-mode safety (PHI1 / §7): the code-level default is ALWAYS paper ---
LIVE_MODE_CODE_DEFAULT: Final[bool] = False
