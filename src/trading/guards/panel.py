"""GuardPanel + apply_guards — the ONE place guard severity touches the kill switch (Inc-6 PART B).

``GuardPanel.assess`` runs G1–G10 over the injected state and folds the reconciler's drift into a G3
result. ``apply_guards`` is the SINGLE applier (so no guard can forget to page on RED): it maps the
graduated levels onto the kill switch + notifier, with two load-bearing rules:

  * Only GATING guards (HARD/STRUCTURED, §4.3) may mutate the kill switch. A RED gating guard
    hard_stops + auto-flats; an ORANGE gating guard trips. ADVISORY guards (G5/G9/G10, DERIVED/
    TEXTUAL) may ONLY page — they never trip or hard_stop (DERIVED data cannot trigger an action).
  * On RED the ``hard_stop`` is latched DURABLY FIRST, THEN the page is attempted. A RED page that
    fails to deliver is recorded (``page_error``) but NEVER aborts the already-issued hard_stop — a
    dropped page must not cost us the halt. ``apply_guards`` is total (never raises).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from trading.executor.kill_switch import KillSwitch
from trading.executor.reconciler import ReconResult
from trading.guards.checks import STATE_CHECKS, StateCheck
from trading.guards.inputs import GuardState
from trading.guards.levels import GuardLevel, GuardResult, recon_to_guard, worst_level
from trading.notify.telegram import Severity


class Pager(Protocol):
    """Minimal pager surface (``TelegramNotifier`` satisfies it); keeps guards
    transport-agnostic."""

    def page_operator(self, severity: Severity, text: str) -> None: ...


@dataclass(frozen=True, slots=True)
class GuardApplication:
    """Outcome of applying the guard results to the kill switch + notifier."""

    worst: GuardLevel
    auto_flat: bool
    tripped: bool
    paged: bool
    page_error: str | None


def g3_from_recon(recon: ReconResult) -> GuardResult:
    """Fold the reconciler's drift level into a gating G3 guard result (no kill mutation here)."""
    return GuardResult(
        guard_id="G3_reconciliation_drift",
        level=recon_to_guard(recon.level),
        reason=recon.reason,
        gates_orders=True,
    )


class GuardPanel:
    """Assemble the full guard verdict set for a loop pass (G1–G10 + G3-from-reconciler)."""

    def __init__(self, state_checks: Sequence[StateCheck] = STATE_CHECKS) -> None:
        self._checks = tuple(state_checks)

    def assess(self, state: GuardState, recon: ReconResult) -> tuple[GuardResult, ...]:
        return (*(check(state) for check in self._checks), g3_from_recon(recon))


def _try_page(notifier: Pager, severity: Severity, text: str) -> str | None:
    try:
        notifier.page_operator(severity, text)
        return None
    except Exception as exc:  # never let a page failure propagate out of the applier
        return type(exc).__name__


def _join(results: Sequence[GuardResult]) -> str:
    return "; ".join(f"{r.guard_id}={r.reason}" for r in results)


def apply_guards(
    results: Sequence[GuardResult], kill_switch: KillSwitch, notifier: Pager
) -> GuardApplication:
    """Map guard results onto the kill switch + notifier. Total (never raises)."""
    gating_red = [r for r in results if r.level is GuardLevel.RED and r.gates_orders]
    gating_orange = [r for r in results if r.level is GuardLevel.ORANGE and r.gates_orders]
    advisory = [r for r in results if not r.gates_orders and r.level is not GuardLevel.GREEN]

    auto_flat = False
    tripped = False
    paged = False
    page_error: str | None = None

    if gating_red:
        reason = "RED guards: " + _join(gating_red)
        kill_switch.hard_stop(reason)  # durable latch FIRST — survives a page failure
        auto_flat = True
        page_error = _try_page(notifier, Severity.RED, reason)
        paged = page_error is None
    elif gating_orange:
        kill_switch.trip("ORANGE guards: " + _join(gating_orange))
        tripped = True

    # Advisory (non-gating) alerts: best-effort page ONLY, never a kill-switch mutation (§4.3).
    if advisory and not gating_red:
        _try_page(notifier, Severity.ORANGE, "advisory: " + _join(advisory))

    return GuardApplication(
        worst=worst_level(results),
        auto_flat=auto_flat,
        tripped=tripped,
        paged=paged,
        page_error=page_error,
    )
