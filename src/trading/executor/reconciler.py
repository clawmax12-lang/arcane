"""Position reconciliation — the broker is authoritative (G3 / M11 / §8.4).

Compares local vs broker positions and escalates by how many positions drift and for
how long (clock injected for determinism): OK -> YELLOW -> ORANGE -> RED. RED means the
drift exceeds the position threshold for longer than the time threshold and demands an
auto-flat + HARD_STOP. ``escalate_kill_switch`` applies ORANGE -> trip, RED -> hard_stop.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from trading.executor.kill_switch import KillSwitch

DRIFT_RED_POSITIONS = 2
DRIFT_RED_SECONDS = 600.0
QTY_TOLERANCE = 1e-9


class ReconLevel(StrEnum):
    OK = "OK"
    YELLOW = "YELLOW"
    ORANGE = "ORANGE"
    RED = "RED"


@dataclass(frozen=True, slots=True)
class ReconResult:
    level: ReconLevel
    drift_count: int
    drift_age_s: float
    require_auto_flat: bool
    reason: str


def count_drift(local: Mapping[str, float], broker: Mapping[str, float]) -> int:
    """Number of symbols whose local and broker quantities disagree."""
    symbols = set(local) | set(broker)
    return sum(1 for s in symbols if abs(local.get(s, 0.0) - broker.get(s, 0.0)) > QTY_TOLERANCE)


def assess_drift(
    local: Mapping[str, float],
    broker: Mapping[str, float],
    drift_since_epoch: float | None,
    now_epoch: float,
    *,
    red_positions: int = DRIFT_RED_POSITIONS,
    red_seconds: float = DRIFT_RED_SECONDS,
) -> ReconResult:
    drift = count_drift(local, broker)
    if drift == 0:
        return ReconResult(ReconLevel.OK, 0, 0.0, False, "in sync")

    age = 0.0 if drift_since_epoch is None else max(0.0, now_epoch - drift_since_epoch)
    if drift <= red_positions:
        return ReconResult(ReconLevel.YELLOW, drift, age, False, f"{drift} position(s) drifting")
    if age <= red_seconds:
        return ReconResult(
            ReconLevel.ORANGE,
            drift,
            age,
            False,
            f"{drift} positions drifting for {age:.0f}s (pause new orders)",
        )
    return ReconResult(
        ReconLevel.RED,
        drift,
        age,
        True,
        f"{drift} positions drifting for {age:.0f}s > {red_seconds:.0f}s "
        f"(auto-flat + HARD_STOP, §8.4)",
    )


def escalate_kill_switch(result: ReconResult, kill_switch: KillSwitch) -> None:
    """Apply the reconciliation level to the kill switch (ORANGE -> trip, RED -> stop).

    A failed state write does not crash the loop: KillSwitch latches the escalation in
    memory before writing, so the switch is already fail-closed for this process even if
    the disk write raises (durability is re-checked at startup via verify_writable).
    """
    try:
        if result.level is ReconLevel.RED:
            kill_switch.hard_stop(result.reason)
        elif result.level is ReconLevel.ORANGE:
            kill_switch.trip(result.reason)
    except OSError:
        pass  # in-memory latch already escalated; do not let a write error stop the loop
