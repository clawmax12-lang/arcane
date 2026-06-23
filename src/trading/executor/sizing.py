"""Deterministic position sizing within the immutable caps (Increment 6 PART C).

From an allocated survivor's target + a FRESH HARD quote + the account snapshot, produce a
conservative
whole-share ``OrderIntent`` that fits ``config/risk.yaml`` — or ``NoTrade`` (the default). The
notional
at-risk is computed as ``qty x the fresh quote`` (never caller-reported), closing the self-reported
notional attack. With ``per_trade_risk_usd = $1`` and any real share price > $1 the budget buys ZERO
whole shares ⇒ ``NoTrade`` — the EXPECTED, CORRECT outcome (ADR §0). The integer-share floor is the
safe choice: it NEVER rounds a sub-cap budget up into a submit, and never loosens a cap to "fit" $1.

§4.3: every input is HARD/STRUCTURED (a fresh quote, broker equity). The target is built
from broker-authoritative positions or a deterministic flat constant — NEVER an agent/LLM output
(PHI1). Anything missing / non-finite / non-positive / stale ⇒ ``NoTrade``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from trading.executor.grant import AllocationGrant
from trading.executor.intent import OrderIntent, Side
from trading.executor.invariants import AccountSnapshot
from trading.risk import constants as C
from trading.risk.schema import RiskConfig


@dataclass(frozen=True, slots=True)
class TargetPosition:
    """The desired entry for ONE strategy in ONE symbol (broker-sourced or a deterministic flat).

    ``spec_hash`` is the allocated strategy's config hash — ``submit_allocated`` binds it to the
    grant's ``spec_hash`` so a grant for strategy A can never drive an order for strategy B.
    """

    strategy_id: str
    symbol: str
    side: Side
    spec_hash: str


@dataclass(frozen=True, slots=True)
class HardQuote:
    """A point-in-time HARD price for sizing — carries its own freshness (M17)."""

    symbol: str
    price: float
    as_of_epoch: float


@dataclass(frozen=True, slots=True)
class Sized:
    intent: OrderIntent


@dataclass(frozen=True, slots=True)
class NoTrade:
    reason: str


SizingOutcome = Sized | NoTrade


def size_order(
    grant: AllocationGrant,
    target: TargetPosition,
    quote: HardQuote,
    account: AccountSnapshot,
    cfg: RiskConfig,
    *,
    max_quote_age_s: float = C.MAX_BAR_AGE_SECONDS,
) -> SizingOutcome:
    """Size a conservative whole-share order within caps, or ``NoTrade``. Fail-closed by default."""
    if quote.symbol != target.symbol:
        return NoTrade(f"quote symbol {quote.symbol} != target symbol {target.symbol}")
    if not math.isfinite(quote.price) or quote.price <= 0:
        return NoTrade(f"non-finite/non-positive price {quote.price!r}")
    age = account.now_epoch - quote.as_of_epoch
    if age < 0 or age > max_quote_age_s:
        return NoTrade(f"quote age {age:.1f}s outside [0, {max_quote_age_s}s] (M17 stale)")
    if account.equity_usd < cfg.equity_floor_usd:
        return NoTrade(f"equity {account.equity_usd} below floor {cfg.equity_floor_usd}")

    # Budget = the strictest of: per-trade cap, the concentration headroom, the equity-floor
    # headroom.
    budget = min(
        cfg.per_trade_risk_usd,
        cfg.max_position_concentration_pct / 100.0 * account.equity_usd,
        account.equity_usd - cfg.equity_floor_usd,
    )
    if budget <= 0:
        return NoTrade(f"non-positive sizing budget ${budget:.2f}")

    qty = math.floor(budget / quote.price)
    if qty < 1:
        return NoTrade(
            f"budget ${budget:.2f} buys 0 whole shares of {target.symbol} @ ${quote.price:.2f} "
            f"(expected at $1 caps)"
        )

    notional = (
        qty * quote.price
    )  # WHOLE notional at risk (no protective stop exists this increment)
    # Strict re-checks (guaranteed by the budget above; defense-in-depth — never round-and-submit).
    if notional > cfg.per_trade_risk_usd:
        return NoTrade(f"notional ${notional:.2f} exceeds per-trade cap ${cfg.per_trade_risk_usd}")
    if notional / account.equity_usd * 100.0 > cfg.max_position_concentration_pct:
        return NoTrade(f"notional ${notional:.2f} exceeds concentration cap")
    if account.equity_usd - notional < cfg.equity_floor_usd:
        return NoTrade(f"notional ${notional:.2f} would breach the equity floor")

    intent = OrderIntent(
        strategy_id=target.strategy_id,
        symbol=target.symbol,
        side=target.side,
        qty=float(qty),
        intended_risk_usd=notional,
        est_position_value_usd=notional,
    )
    return Sized(intent)
