"""Pure, deterministic risk-cap checks — arithmetic only (no I/O, no globals, no LLM).

Each function answers one question against the configured limits and returns a
``CapResult``. These are the arithmetic heart of the pre-submit invariant chain and are
exhaustively property-tested: a cap must NEVER report ``ok`` when its limit is exceeded.

Non-finite inputs (NaN/inf) are treated as a VIOLATION (fail-closed) — NaN compares
False to every threshold, so without this guard a NaN would silently pass every cap.

Convention: loss inputs are POSITIVE magnitudes (a $4 loss is ``4.0``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from trading.risk.schema import RiskConfig


@dataclass(frozen=True, slots=True)
class CapResult:
    """Result of a single cap check. ``ok`` False means the order/loop must stop."""

    ok: bool
    reason: str = ""


def check_per_trade_risk(cfg: RiskConfig, intended_risk_usd: float) -> CapResult:
    if not math.isfinite(intended_risk_usd):
        return CapResult(False, f"intended risk {intended_risk_usd} is not finite")
    if intended_risk_usd <= 0:
        return CapResult(False, f"intended risk {intended_risk_usd} must be positive")
    if intended_risk_usd > cfg.per_trade_risk_usd:
        return CapResult(
            False,
            f"intended risk {intended_risk_usd} exceeds per-trade cap {cfg.per_trade_risk_usd}",
        )
    return CapResult(True)


def check_daily_loss(cfg: RiskConfig, realized_daily_loss_usd: float) -> CapResult:
    if not math.isfinite(realized_daily_loss_usd):
        return CapResult(False, f"daily loss {realized_daily_loss_usd} is not finite")
    if realized_daily_loss_usd >= cfg.max_daily_loss_usd:
        return CapResult(
            False,
            f"daily loss {realized_daily_loss_usd} reached cap {cfg.max_daily_loss_usd}",
        )
    return CapResult(True)


def check_equity_floor(cfg: RiskConfig, equity_usd: float) -> CapResult:
    if not math.isfinite(equity_usd):
        return CapResult(False, f"equity {equity_usd} is not finite")
    if equity_usd < cfg.equity_floor_usd:
        return CapResult(
            False,
            f"equity {equity_usd} below floor {cfg.equity_floor_usd} (§8.2 abandon)",
        )
    return CapResult(True)


def check_total_loss_abandon(cfg: RiskConfig, cumulative_loss_usd: float) -> CapResult:
    if not math.isfinite(cumulative_loss_usd):
        return CapResult(False, f"cumulative loss {cumulative_loss_usd} is not finite")
    if cumulative_loss_usd > cfg.total_loss_abandon_usd:
        return CapResult(
            False,
            f"cumulative loss {cumulative_loss_usd} exceeds abandon threshold "
            f"{cfg.total_loss_abandon_usd} (§8.1)",
        )
    return CapResult(True)


def check_concentration(cfg: RiskConfig, position_value_usd: float, equity_usd: float) -> CapResult:
    if not math.isfinite(position_value_usd) or not math.isfinite(equity_usd):
        return CapResult(
            False, f"non-finite concentration inputs ({position_value_usd}, {equity_usd})"
        )
    if equity_usd <= 0:
        return CapResult(False, f"non-positive equity {equity_usd}")
    pct = position_value_usd / equity_usd * 100.0
    if pct > cfg.max_position_concentration_pct:
        return CapResult(
            False,
            f"concentration {pct:.1f}% exceeds cap {cfg.max_position_concentration_pct}%",
        )
    return CapResult(True)
