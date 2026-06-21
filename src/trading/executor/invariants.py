"""The pre-submit invariant chain — the gate every order must pass.

This is the deterministic heart of the executor. It composes the kill switch, data
freshness, the risk caps, concentration, idempotency, and a pluggable mistake check
into a single ordered, fail-closed evaluation. The FIRST failing gate rejects the
order; nothing downstream is consulted. There is no path to the broker that skips it.

PHI1: no LLM is imported here. The mistake check is a plain deterministic callable.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from trading.executor.idempotency import client_order_id
from trading.executor.intent import OrderIntent
from trading.executor.kill_switch import KillSwitch
from trading.risk import constants as C
from trading.risk.caps import (
    check_concentration,
    check_daily_loss,
    check_equity_floor,
    check_per_trade_risk,
    check_total_loss_abandon,
)
from trading.risk.schema import RiskConfig


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    """The HARD/STRUCTURED state a decision is gated on (§4.3). All values in USD/epoch.

    Every field must be FINITE: a NaN/inf snapshot would make every reject-if-violated
    gate pass (NaN compares False to all thresholds), so non-finite input is rejected at
    construction — the chain can never see one (red-team finding #1).
    """

    equity_usd: float
    realized_daily_loss_usd: float
    cumulative_loss_usd: float
    data_as_of_epoch: float
    now_epoch: float

    def __post_init__(self) -> None:
        for name in (
            "equity_usd",
            "realized_daily_loss_usd",
            "cumulative_loss_usd",
            "data_as_of_epoch",
            "now_epoch",
        ):
            value = getattr(self, name)
            if not math.isfinite(value):
                raise ValueError(f"AccountSnapshot.{name} must be finite, got {value!r}")


@dataclass(frozen=True, slots=True)
class GateDecision:
    """Outcome of the chain. ``accepted`` False names the first gate that failed."""

    accepted: bool
    client_order_id: str
    failed_gate: str | None = None
    reason: str = ""


#: A mistake check returns a block reason, or None to allow. Pure & deterministic.
MistakeChecker = Callable[[OrderIntent, AccountSnapshot], str | None]


def _no_mistakes(intent: OrderIntent, snapshot: AccountSnapshot) -> str | None:
    return None


def evaluate_pre_submit(
    intent: OrderIntent,
    snapshot: AccountSnapshot,
    cfg: RiskConfig,
    kill_switch: KillSwitch,
    seen: Callable[[str], bool],
    *,
    max_bar_age_s: float = C.MAX_BAR_AGE_SECONDS,
    mistake_checker: MistakeChecker = _no_mistakes,
) -> GateDecision:
    """Run the ordered, fail-closed gate chain. First failure rejects the order."""
    coid = client_order_id(intent)

    # 1. Kill switch — only ARMED permits new orders.
    if not kill_switch.allows_new_orders():
        return GateDecision(False, coid, "kill_switch", f"kill switch is {kill_switch.read()}")

    # 2. Data freshness (M17) — no trading on stale or future-dated bars.
    age = snapshot.now_epoch - snapshot.data_as_of_epoch
    if age < 0 or age > max_bar_age_s:
        return GateDecision(
            False,
            coid,
            "data_freshness",
            f"data age {age:.1f}s outside [0, {max_bar_age_s}s] (M17)",
        )

    # 3-7. Risk caps — evaluate each once, in explicit order; first failure rejects.
    per_trade = check_per_trade_risk(cfg, intent.intended_risk_usd)
    if not per_trade.ok:
        return GateDecision(False, coid, "per_trade_cap", per_trade.reason)
    daily = check_daily_loss(cfg, snapshot.realized_daily_loss_usd)
    if not daily.ok:
        return GateDecision(False, coid, "daily_loss_cap", daily.reason)
    floor = check_equity_floor(cfg, snapshot.equity_usd)
    if not floor.ok:
        return GateDecision(False, coid, "equity_floor", floor.reason)
    total = check_total_loss_abandon(cfg, snapshot.cumulative_loss_usd)
    if not total.ok:
        return GateDecision(False, coid, "total_loss_abandon", total.reason)
    conc = check_concentration(cfg, intent.est_position_value_usd, snapshot.equity_usd)
    if not conc.ok:
        return GateDecision(False, coid, "concentration", conc.reason)

    # 8. Idempotency (M10) — reject a client_order_id we have already submitted.
    if seen(coid):
        return GateDecision(False, coid, "idempotency", f"duplicate client_order_id {coid} (M10)")

    # 9. Mistake fingerprint check (M1-M20) — pluggable, deterministic, no LLM.
    block = mistake_checker(intent, snapshot)
    if block is not None:
        return GateDecision(False, coid, "mistake_check", block)

    return GateDecision(True, coid)
