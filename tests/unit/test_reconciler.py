"""Tests for position reconciliation drift escalation (Increment 1 safety spine)."""

from __future__ import annotations

from pathlib import Path

from trading.executor.kill_switch import KillSwitch, KillSwitchState
from trading.executor.reconciler import (
    ReconLevel,
    assess_drift,
    count_drift,
    escalate_kill_switch,
)


def test_count_drift() -> None:
    assert count_drift({"AAPL": 1.0}, {"AAPL": 1.0}) == 0
    assert count_drift({"AAPL": 1.0}, {"AAPL": 2.0}) == 1
    assert count_drift({"AAPL": 1.0}, {}) == 1  # local has a position broker doesn't
    assert count_drift({}, {"TSLA": 3.0, "NVDA": 1.0}) == 2


def test_no_drift_is_ok() -> None:
    r = assess_drift({"AAPL": 1.0}, {"AAPL": 1.0}, None, 1_000.0)
    assert r.level is ReconLevel.OK
    assert r.require_auto_flat is False


def test_small_drift_is_yellow() -> None:
    r = assess_drift({"AAPL": 1.0}, {"AAPL": 2.0}, 900.0, 1_000.0)
    assert r.level is ReconLevel.YELLOW
    assert r.require_auto_flat is False


def test_large_recent_drift_is_orange() -> None:
    local = {"A": 1.0, "B": 1.0, "C": 1.0}
    broker: dict[str, float] = {}
    r = assess_drift(local, broker, drift_since_epoch=900.0, now_epoch=1_000.0)  # age 100s
    assert r.level is ReconLevel.ORANGE
    assert r.require_auto_flat is False


def test_large_sustained_drift_is_red_and_flats() -> None:
    local = {"A": 1.0, "B": 1.0, "C": 1.0}
    broker: dict[str, float] = {}
    r = assess_drift(local, broker, drift_since_epoch=0.0, now_epoch=700.0)  # age 700s > 600
    assert r.level is ReconLevel.RED
    assert r.require_auto_flat is True


def test_escalate_orange_trips_switch(tmp_path: Path) -> None:
    ks = KillSwitch(tmp_path / "ks.json")
    r = assess_drift({"A": 1.0, "B": 1.0, "C": 1.0}, {}, 900.0, 1_000.0)
    escalate_kill_switch(r, ks)
    assert ks.read() is KillSwitchState.TRIPPED


def test_escalate_red_hard_stops_switch(tmp_path: Path) -> None:
    ks = KillSwitch(tmp_path / "ks.json")
    r = assess_drift({"A": 1.0, "B": 1.0, "C": 1.0}, {}, 0.0, 700.0)
    escalate_kill_switch(r, ks)
    assert ks.read() is KillSwitchState.HARD_STOPPED


def test_escalate_yellow_leaves_switch_armed(tmp_path: Path) -> None:
    ks = KillSwitch(tmp_path / "ks.json")
    r = assess_drift({"AAPL": 1.0}, {"AAPL": 2.0}, 900.0, 1_000.0)
    escalate_kill_switch(r, ks)
    assert ks.read() is KillSwitchState.ARMED
