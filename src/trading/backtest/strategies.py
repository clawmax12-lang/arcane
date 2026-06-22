"""The default strategy set — a small handful (4) of standard factor compositions (ADR §5).

Each is a textbook composition of registered ``factor_id``s in already-z-scored space, with fixed
literal weights (NO grids, NO orthogonalization — pre-pruning for orthogonality is itself a tuning
move ADR §5 forbids). Correlated families are kept on purpose (``trend_location`` shares ``mom_63d``
with ``ts_momentum_blend``); the Increment-5 bias gate prunes (~2 survivors expected). Each spec is
a COUNTED trial. Time-series per-symbol; cross-sectional construction is deferred (see design doc).
"""

from __future__ import annotations

from trading.backtest.spec import (
    CompositionRule,
    Direction,
    FactorLeg,
    PositionMode,
    StrategySpec,
)


def default_strategies() -> tuple[StrategySpec, ...]:
    """The frozen 4 default strategies (order is canonical)."""
    return (
        StrategySpec(
            name="ts_momentum_blend",
            legs=(
                FactorLeg(factor_id="mom_21d", weight=0.34, direction=Direction.LONG),
                FactorLeg(factor_id="mom_63d", weight=0.33, direction=Direction.LONG),
                FactorLeg(factor_id="mom_126_skip21", weight=0.33, direction=Direction.LONG),
            ),
            rule=CompositionRule.Z_WEIGHTED_SUM,
            position_mode=PositionMode.LONG_SHORT,
        ),
        StrategySpec(
            name="ts_meanrev_short",
            legs=(
                FactorLeg(factor_id="reversal_5d", weight=0.6, direction=Direction.LONG),
                FactorLeg(factor_id="close_loc_in_range", weight=0.4, direction=Direction.SHORT),
            ),
            rule=CompositionRule.Z_WEIGHTED_SUM,
            position_mode=PositionMode.LONG_SHORT,
        ),
        StrategySpec(
            name="trend_location",
            legs=(
                FactorLeg(factor_id="sma_ratio_20_50", weight=0.4, direction=Direction.LONG),
                FactorLeg(factor_id="dist_from_sma_50", weight=0.3, direction=Direction.LONG),
                FactorLeg(factor_id="mom_63d", weight=0.3, direction=Direction.LONG),
            ),
            rule=CompositionRule.Z_WEIGHTED_SUM,
            position_mode=PositionMode.LONG_ONLY,
        ),
        StrategySpec(
            name="lowvol_liquid_tilt",
            legs=(
                FactorLeg(factor_id="vol_21d", weight=0.4, direction=Direction.SHORT),
                FactorLeg(factor_id="amihud_illiq_21d", weight=0.3, direction=Direction.SHORT),
                FactorLeg(factor_id="dollar_vol_21d", weight=0.3, direction=Direction.LONG),
            ),
            rule=CompositionRule.Z_WEIGHTED_SUM,
            position_mode=PositionMode.LONG_ONLY,
        ),
    )
