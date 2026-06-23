"""C12 — reconciliation: drift escalation + RED auto-flat + startup orphan resolve (Inc-6 PART
C)."""

from __future__ import annotations

from pathlib import Path

from trading.executor.kill_switch import KillSwitch, KillSwitchState
from trading.executor.reconcile_loop import reconcile_claimed_orders, reconcile_once
from trading.notify.telegram import Severity


class FakePager:
    def __init__(self) -> None:
        self.calls: list[tuple[Severity, str]] = []

    def page_operator(self, severity: Severity, text: str) -> None:
        self.calls.append((severity, text))


def _ks(tmp_path: Path) -> KillSwitch:
    return KillSwitch(tmp_path / "ks.json")


def test_in_sync_is_ok_no_escalation(tmp_path: Path) -> None:
    ks = _ks(tmp_path)
    flats: list[bool] = []
    out = reconcile_once(
        {"AAPL": 1.0},
        {"AAPL": 1.0},
        None,
        1000.0,
        kill_switch=ks,
        notifier=FakePager(),
        broker_flat_fn=lambda: flats.append(True),
    )
    assert out.result.require_auto_flat is False and out.auto_flatted is False
    assert ks.read() is KillSwitchState.ARMED and flats == []


def test_red_drift_auto_flats_hard_stops_and_pages(tmp_path: Path) -> None:
    ks = _ks(tmp_path)
    pager = FakePager()
    flats: list[bool] = []
    # 3 positions disagree, drifting for 700s > 600s -> RED
    out = reconcile_once(
        {"A": 1.0, "B": 1.0, "C": 1.0},
        {},
        1000.0,
        1700.0,
        kill_switch=ks,
        notifier=pager,
        broker_flat_fn=lambda: flats.append(True),
    )
    assert out.result.require_auto_flat is True
    assert out.auto_flatted is True and flats == [True]
    assert ks.read() is KillSwitchState.HARD_STOPPED
    assert out.paged is True and pager.calls[0][0] is Severity.RED


def test_orange_drift_trips_without_auto_flat(tmp_path: Path) -> None:
    ks = _ks(tmp_path)
    # 3 positions drift for only 100s (< 600s) -> ORANGE
    out = reconcile_once(
        {"A": 1.0, "B": 1.0, "C": 1.0},
        {},
        1000.0,
        1100.0,
        kill_switch=ks,
        notifier=FakePager(),
        broker_flat_fn=lambda: None,
    )
    assert out.result.require_auto_flat is False and out.auto_flatted is False
    assert ks.read() is KillSwitchState.TRIPPED


def test_flat_failure_does_not_undo_hard_stop(tmp_path: Path) -> None:
    ks = _ks(tmp_path)

    def boom() -> None:
        raise RuntimeError("broker flat failed")

    out = reconcile_once(
        {"A": 1.0, "B": 1.0, "C": 1.0},
        {},
        1000.0,
        1700.0,
        kill_switch=ks,
        notifier=FakePager(),
        broker_flat_fn=boom,  # raises
    )
    assert ks.read() is KillSwitchState.HARD_STOPPED  # latched despite the flat failure
    assert out.auto_flatted is False  # the flat did not confirm


def test_reconcile_claimed_orders_resolves_status() -> None:
    statuses = {"arcane-a": "filled", "arcane-b": "lookup_failed:APIError"}
    out = reconcile_claimed_orders(["arcane-a", "arcane-b"], lambda c: statuses[c])
    assert out == statuses  # surfaces status, never blind re-submits
