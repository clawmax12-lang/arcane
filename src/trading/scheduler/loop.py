"""The OFF-by-default, explicit-enable, RECORD_ONLY scheduler (Increment 7 PART C).

A THIN deterministic loop (NOT APScheduler / cron) that runs ONE record-only driver pass ONLY when
ALL hold: (a) an operator-written ``state/SCHEDULER_ENABLE`` marker containing the exact phrase is
present; (b) the injected clock is in RTH; (c) ``is_live`` is False. It ships DORMANT — no cron is
registered; it is invoked only by an operator. The scheduler-enable gate (may-RUN) is ORTHOGONAL to
the per-order ``SUBMIT_GO`` gate (may-SUBMIT): enabling the scheduler NEVER authorizes a real order,
and even when enabled ``drive_once`` is RECORD_ONLY. The scheduler has NO authority to write the
``SUBMIT_GO`` / ``SCHEDULER_ENABLE`` markers (a committed test pins that), NO path to live_mode, and
imports NO LLM/agent module (PHI1 — this package is in the submit-path AST scan).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from trading.driver.run_once import DriverContext, DriverResult, drive_once
from trading.executor.live_mode import is_live
from trading.risk.schema import RiskConfig

#: The exact phrase the operator-enable marker must contain to ALLOW record-only scheduled passes.
#: Distinct from the per-order ``SUBMIT_GO`` phrase — enabling the scheduler is NOT a submit GO.
ENABLE_PHRASE: Final[str] = "I_AUTHORIZE_SCHEDULER_RECORD_ONLY"
DEFAULT_ENABLE_MARKER: Final[Path] = Path("state/SCHEDULER_ENABLE")


class SchedulerAction(StrEnum):
    SKIP = "SKIP"  # OFF by default / outside RTH / live — do nothing
    RECORD_ONLY_PASS = "RECORD_ONLY_PASS"  # enabled + RTH — one record-only driver pass


@dataclass(frozen=True, slots=True)
class SchedulerOutcome:
    action: SchedulerAction
    result: DriverResult | None  # the driver result if a pass ran, else None
    reason: str


def _enabled(marker_path: Path) -> bool:
    try:
        if not marker_path.is_file():
            return False
        lines = [ln.strip() for ln in marker_path.read_text(encoding="utf-8").splitlines()]
    except OSError:
        return False
    return ENABLE_PHRASE in lines


def scheduler_action(
    now_epoch: float,
    cfg: RiskConfig,
    *,
    enable_marker_path: Path = DEFAULT_ENABLE_MARKER,
    is_rth: Callable[[float], bool],
) -> tuple[SchedulerAction, str]:
    """Decide whether to run a record-only pass. SKIP unless enabled AND in RTH AND paper."""
    if is_live(cfg.live_mode):
        return SchedulerAction.SKIP, "is_live() True — the scheduler never runs toward a live order"
    if not _enabled(enable_marker_path):
        return SchedulerAction.SKIP, "no SCHEDULER_ENABLE marker — OFF by default (operator-gated)"
    if not is_rth(now_epoch):
        return SchedulerAction.SKIP, "outside regular trading hours"
    return SchedulerAction.RECORD_ONLY_PASS, "enabled + RTH — one record-only driver pass"


def run_scheduled_pass(
    now_epoch: float,
    ctx: DriverContext,
    cfg: RiskConfig,
    *,
    enable_marker_path: Path = DEFAULT_ENABLE_MARKER,
    is_rth: Callable[[float], bool],
) -> SchedulerOutcome:
    """Run ONE scheduler tick. RECORD_ONLY: even when enabled, ``drive_once`` submits nothing."""
    action, reason = scheduler_action(
        now_epoch, cfg, enable_marker_path=enable_marker_path, is_rth=is_rth
    )
    if action is SchedulerAction.SKIP:
        return SchedulerOutcome(action, None, reason)
    return SchedulerOutcome(action, drive_once(ctx), reason)
