"""Graduated guard levels + the one place guard severity is ordered (Increment 6 PART B).

``GuardLevel`` mirrors the reconciler's ``ReconLevel`` so the two compose: GREEN < YELLOW < ORANGE <
RED. ``GuardResult`` is one guard's verdict, carrying ``gates_orders`` — whether this guard's
level may
BLOCK a new order (HARD/STRUCTURED, §4.3) or only escalate the LOOP (DERIVED/TEXTUAL guards page and
can hard_stop but must NEVER gate an order).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from trading.executor.reconciler import ReconLevel


class GuardLevel(StrEnum):
    GREEN = "GREEN"  # healthy
    YELLOW = "YELLOW"  # log / dashboard banner
    ORANGE = "ORANGE"  # pause new orders (kill_switch.trip)
    RED = "RED"  # disaster — auto-flat + kill_switch.hard_stop + page


_ORDER: dict[GuardLevel, int] = {
    GuardLevel.GREEN: 0,
    GuardLevel.YELLOW: 1,
    GuardLevel.ORANGE: 2,
    GuardLevel.RED: 3,
}

_RECON_TO_GUARD: dict[ReconLevel, GuardLevel] = {
    ReconLevel.OK: GuardLevel.GREEN,
    ReconLevel.YELLOW: GuardLevel.YELLOW,
    ReconLevel.ORANGE: GuardLevel.ORANGE,
    ReconLevel.RED: GuardLevel.RED,
}


@dataclass(frozen=True, slots=True)
class GuardResult:
    """One guard's verdict. ``gates_orders`` False ⇒ advisory-only (§4.3): may page, never
    blocks."""

    guard_id: str
    level: GuardLevel
    reason: str
    gates_orders: bool


def worst_level(results: Iterable[GuardResult]) -> GuardLevel:
    """The most severe level across results (GREEN if none) — the loop's overall guard posture."""
    return max(
        (r.level for r in results),
        key=lambda level: _ORDER[level],
        default=GuardLevel.GREEN,
    )


def recon_to_guard(level: ReconLevel) -> GuardLevel:
    """Map the reconciler's drift level onto the guard scale (G3 delegates to the reconciler)."""
    return _RECON_TO_GUARD[level]
