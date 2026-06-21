"""``OrderIntent`` — the only object the executor will accept (frozen, validated).

Nothing reaches the broker except a validated ``OrderIntent``. Enums make illegal
sides/types unrepresentable; the validators enforce market-vs-limit pricing rules,
reject non-finite numerics (inf/nan), and CANONICALIZE the identity fields (symbol,
strategy_id) so cosmetic Unicode/whitespace variants resolve to one representation —
closing the idempotency-dedup-miss vector (red-team finding #3).
"""

from __future__ import annotations

import math
import re
import unicodedata
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SYMBOL_RE = re.compile(r"^[A-Z0-9.\-]{1,15}$")
_STRATEGY_RE = re.compile(r"^[a-z0-9_\-]{1,64}$")


def _strip_format_chars(value: str) -> str:
    """NFKC-normalize and remove Unicode format/invisible characters (category Cf)."""
    normalized = unicodedata.normalize("NFKC", value)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Cf")


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

    @field_validator("symbol", mode="after")
    @classmethod
    def _canon_symbol(cls, value: str) -> str:
        canonical = _strip_format_chars(value).strip().upper()
        if not _SYMBOL_RE.match(canonical):
            raise ValueError(f"invalid symbol {value!r} (canonical {canonical!r})")
        return canonical

    @field_validator("strategy_id", mode="after")
    @classmethod
    def _canon_strategy(cls, value: str) -> str:
        canonical = _strip_format_chars(value).strip().casefold()
        if not _STRATEGY_RE.match(canonical):
            raise ValueError(f"invalid strategy_id {value!r} (canonical {canonical!r})")
        return canonical

    @model_validator(mode="after")
    def _check_finite_and_pricing(self) -> OrderIntent:
        for name, value in (
            ("qty", self.qty),
            ("intended_risk_usd", self.intended_risk_usd),
            ("est_position_value_usd", self.est_position_value_usd),
        ):
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite, got {value!r}")
        if self.limit_price is not None and not math.isfinite(self.limit_price):
            raise ValueError("limit_price must be finite")

        if self.order_type is OrderType.LIMIT:
            if self.limit_price is None or self.limit_price <= 0:
                raise ValueError("limit order requires a positive limit_price")
        elif self.limit_price is not None:
            raise ValueError("market order must not set limit_price")
        return self
