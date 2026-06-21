"""``OrderIntent`` — the only object the executor will accept (frozen, validated).

Nothing reaches the broker except a validated ``OrderIntent``. Enums make illegal
sides/types unrepresentable; the validator enforces market-vs-limit pricing rules.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"


class TimeInForce(StrEnum):
    DAY = "day"
    GTC = "gtc"
    IOC = "ioc"


class OrderIntent(BaseModel):
    """A fully-specified order request, prior to risk gating and submission."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    side: Side
    qty: float = Field(gt=0)
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    time_in_force: TimeInForce = TimeInForce.DAY
    intended_risk_usd: float = Field(gt=0)
    est_position_value_usd: float = Field(gt=0)

    @model_validator(mode="after")
    def _check_pricing(self) -> OrderIntent:
        if self.order_type is OrderType.LIMIT:
            if self.limit_price is None or self.limit_price <= 0:
                raise ValueError("limit order requires a positive limit_price")
        elif self.limit_price is not None:
            raise ValueError("market order must not set limit_price")
        return self
