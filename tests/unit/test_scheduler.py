"""C7 — the scheduler: OFF by default, explicit-enable, RECORD_ONLY, never unattended (Inc-7 PART).

The scheduler runs a record-only driver pass ONLY when an operator-written ``SCHEDULER_ENABLE``
marker is present AND the clock is in RTH; otherwise SKIP. Even when enabled it submits NOTHING (no
SUBMIT_GO). The enable gate is ORTHOGONAL to the per-order submit gate, and no submit-path module
may write either operator marker (skeptic A5).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import test_driver as td  # reuse the wired DriverContext + SpyBroker

from trading.scheduler.loop import (
    ENABLE_PHRASE,
    SchedulerAction,
    run_scheduled_pass,
    scheduler_action,
)

_SRC = Path(__file__).resolve().parents[2] / "src" / "trading"


def _always_rth(_now: float) -> bool:
    return True


def _never_rth(_now: float) -> bool:
    return False


def _enable(tmp_path: Path) -> Path:
    marker = tmp_path / "SCHEDULER_ENABLE"
    marker.write_text(f"{ENABLE_PHRASE}\n", encoding="utf-8")
    return marker


def test_scheduler_off_by_default_skips(tmp_path: Path) -> None:
    ctx = td._ctx(tmp_path)
    out = run_scheduled_pass(
        1000.0, ctx, td._cfg(), enable_marker_path=tmp_path / "absent", is_rth=_always_rth
    )
    assert out.action is SchedulerAction.SKIP and out.result is None
    broker = ctx.loop_deps.broker
    assert isinstance(broker, td.SpyBroker) and broker.submits == []


def test_scheduler_skips_outside_rth_even_when_enabled(tmp_path: Path) -> None:
    action, _ = scheduler_action(
        1000.0, td._cfg(), enable_marker_path=_enable(tmp_path), is_rth=_never_rth
    )
    assert action is SchedulerAction.SKIP


def test_scheduler_skips_when_enable_phrase_is_missing(tmp_path: Path) -> None:
    bad = tmp_path / "SCHEDULER_ENABLE"
    bad.write_text("garbage not the phrase\n", encoding="utf-8")
    action, _ = scheduler_action(1000.0, td._cfg(), enable_marker_path=bad, is_rth=_always_rth)
    assert action is SchedulerAction.SKIP  # fail-closed on a malformed marker


def test_scheduler_enabled_in_rth_runs_record_only_zero_submit(tmp_path: Path) -> None:
    ctx = td._ctx(tmp_path)
    out = run_scheduled_pass(
        1000.0, ctx, td._cfg(), enable_marker_path=_enable(tmp_path), is_rth=_always_rth
    )
    assert out.action is SchedulerAction.RECORD_ONLY_PASS
    assert out.result is not None and out.result.candidate_count == 0
    assert out.result.loop_result.submitted_count == 0  # enabled, in RTH, yet ZERO submits (no GO)
    broker = ctx.loop_deps.broker
    assert isinstance(broker, td.SpyBroker) and broker.submits == []


def test_scheduler_does_not_write_the_submit_go_marker(tmp_path: Path) -> None:
    ctx = td._ctx(tmp_path)
    run_scheduled_pass(
        1000.0, ctx, td._cfg(), enable_marker_path=_enable(tmp_path), is_rth=_always_rth
    )
    assert not (tmp_path / "SUBMIT_GO").exists()  # may-RUN never implies may-SUBMIT


# --- skeptic A5: no submit-path module may WRITE an operator marker ---


def test_no_submit_path_module_writes_an_operator_marker() -> None:
    # An operator marker (SUBMIT_GO / SCHEDULER_ENABLE) may only be CREATED by an operator (outside
    # the closure). A submit-path module that both references a marker AND performs a write/touch is
    # an offender — a driver/scheduler that wrote SUBMIT_GO could flip RECORD_ONLY to a real submit.
    write_op = re.compile(r"\.write_text\s*\(|\.touch\s*\(|\bopen\s*\([^)]*['\"][wax]")
    markers = ("SUBMIT_GO", "SCHEDULER_ENABLE")
    offenders: list[str] = []
    for pkg in ("executor", "regime", "allocator", "driver", "scheduler"):
        for py in (_SRC / pkg).rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            ast.parse(text)  # also assert the module is parseable (no silently-skipped file)
            if any(mk in text for mk in markers) and write_op.search(text):
                offenders.append(f"{pkg}/{py.name}")
    assert (
        not offenders
    ), f"a submit-path module references AND may write an operator marker: {offenders}"
