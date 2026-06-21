"""``RiskConfig`` — the only risk configuration the system trusts.

Frozen, validated, fail-closed. Enforces the floor-of-floors from ``constants.py``
plus internal-consistency invariants. A config that violates any bound raises and the
executor refuses to trade: there is no "best effort" with risk limits.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import constants as C


class RiskConfig(BaseModel):
    """Operator-tunable risk limits, bounded by the hardcoded floor-of-floors."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    live_mode: bool = False
    per_trade_risk_usd: float = Field(gt=0)
    max_daily_loss_usd: float = Field(gt=0)
    equity_floor_usd: float = Field(gt=0)
    total_loss_abandon_usd: float = Field(gt=0)
    max_position_concentration_pct: float = Field(gt=0, le=100)
    max_consecutive_errors: int = Field(gt=0)

    @model_validator(mode="after")
    def _enforce_floor_of_floors(self) -> RiskConfig:
        errors: list[str] = []

        # The config may only be *stricter* than the hard floors — never looser.
        if self.equity_floor_usd < C.EQUITY_FLOOR_USD:
            errors.append(
                f"equity_floor_usd={self.equity_floor_usd} is below the hard floor "
                f"{C.EQUITY_FLOOR_USD} (§8.2); config may not loosen it"
            )
        if self.total_loss_abandon_usd > C.TOTAL_LOSS_ABANDON_USD:
            errors.append(
                f"total_loss_abandon_usd={self.total_loss_abandon_usd} exceeds the hard "
                f"cap {C.TOTAL_LOSS_ABANDON_USD} (§8.1); config may not tolerate more loss"
            )
        if self.per_trade_risk_usd > C.PER_TRADE_RISK_USD_CEILING:
            errors.append(
                f"per_trade_risk_usd={self.per_trade_risk_usd} exceeds ceiling "
                f"{C.PER_TRADE_RISK_USD_CEILING}"
            )
        if self.max_daily_loss_usd > C.DAILY_LOSS_USD_CEILING:
            errors.append(
                f"max_daily_loss_usd={self.max_daily_loss_usd} exceeds ceiling "
                f"{C.DAILY_LOSS_USD_CEILING}"
            )
        if self.max_consecutive_errors > C.MAX_CONSECUTIVE_SCHEDULER_ERRORS:
            errors.append(
                f"max_consecutive_errors={self.max_consecutive_errors} exceeds "
                f"{C.MAX_CONSECUTIVE_SCHEDULER_ERRORS} (§8.3)"
            )

        # Internal consistency: a single trade can't risk more than a whole day, and a
        # day can't lose more than the total-loss abandonment threshold.
        if self.per_trade_risk_usd > self.max_daily_loss_usd:
            errors.append(
                f"per_trade_risk_usd={self.per_trade_risk_usd} exceeds "
                f"max_daily_loss_usd={self.max_daily_loss_usd}"
            )
        if self.max_daily_loss_usd > self.total_loss_abandon_usd:
            errors.append(
                f"max_daily_loss_usd={self.max_daily_loss_usd} exceeds "
                f"total_loss_abandon_usd={self.total_loss_abandon_usd}"
            )

        # The equity floor must sit below starting capital or the experiment cannot run.
        if self.equity_floor_usd >= C.STARTING_CAPITAL_USD:
            errors.append(
                f"equity_floor_usd={self.equity_floor_usd} must be below starting "
                f"capital {C.STARTING_CAPITAL_USD}"
            )

        if errors:
            raise ValueError("; ".join(errors))
        return self
