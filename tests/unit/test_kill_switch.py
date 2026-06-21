"""Tests for the kill switch (Increment 1 safety spine).

Covers: fresh ARMED start, escalation, monotonicity (no auto de-escalation),
operator-only re-arm, crash-safe persistence, and fail-safe corrupt-file handling.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from trading.executor.kill_switch import (
    KillSwitch,
    KillSwitchAuthorityError,
    KillSwitchState,
    KillSwitchUnwritableError,
)


def test_fresh_is_armed(tmp_path: Path) -> None:
    k = KillSwitch(tmp_path / "ks.json")
    assert k.read() is KillSwitchState.ARMED
    assert k.allows_new_orders() is True


def test_trip_blocks_orders_and_persists(tmp_path: Path) -> None:
    p = tmp_path / "ks.json"
    KillSwitch(p).trip("orange guard")
    # A fresh instance on the same path sees the persisted state (restart-safe).
    reloaded = KillSwitch(p)
    assert reloaded.read() is KillSwitchState.TRIPPED
    assert reloaded.allows_new_orders() is False


def test_hard_stop_is_terminal_and_monotonic(tmp_path: Path) -> None:
    p = tmp_path / "ks.json"
    k = KillSwitch(p)
    k.hard_stop("abandonment trigger")
    assert k.read() is KillSwitchState.HARD_STOPPED
    # trip() must not lower a HARD_STOPPED switch.
    k.trip("noise")
    assert k.read() is KillSwitchState.HARD_STOPPED


def test_trip_does_not_downgrade_when_already_tripped(tmp_path: Path) -> None:
    p = tmp_path / "ks.json"
    k = KillSwitch(p)
    k.hard_stop("abandon")
    k.trip("later orange")
    assert k.read() is KillSwitchState.HARD_STOPPED


def test_agent_cannot_rearm(tmp_path: Path) -> None:
    p = tmp_path / "ks.json"
    k = KillSwitch(p)
    k.trip("x")
    with pytest.raises(KillSwitchAuthorityError):
        k.arm(operator_authority=False)
    assert k.read() is KillSwitchState.TRIPPED


def test_operator_can_rearm_from_tripped(tmp_path: Path) -> None:
    p = tmp_path / "ks.json"
    k = KillSwitch(p)
    k.trip("x")
    k.arm(operator_authority=True)
    assert k.read() is KillSwitchState.ARMED


def test_operator_can_reset_from_hard_stop(tmp_path: Path) -> None:
    p = tmp_path / "ks.json"
    k = KillSwitch(p)
    k.hard_stop("abandon")
    k.arm(operator_authority=True)
    assert k.read() is KillSwitchState.ARMED


def test_corrupt_file_fails_safe_to_tripped(tmp_path: Path) -> None:
    p = tmp_path / "ks.json"
    p.write_text("{ not json")
    assert KillSwitch(p).read() is KillSwitchState.TRIPPED


def test_unknown_state_fails_safe_to_tripped(tmp_path: Path) -> None:
    p = tmp_path / "ks.json"
    p.write_text(json.dumps({"state": "WHATEVER"}))
    assert KillSwitch(p).read() is KillSwitchState.TRIPPED


def test_atomic_write_leaves_no_tmp_and_valid_json(tmp_path: Path) -> None:
    p = tmp_path / "ks.json"
    KillSwitch(p).trip("x")
    assert not (tmp_path / "ks.json.tmp").exists()
    json.loads(p.read_text(encoding="utf-8"))  # main file is always valid JSON


# --- Red-team regression: kill-switch fail-open vectors (wf_453c8909-dd7) ---


def test_finding5_dangling_symlink_fails_safe_to_tripped(tmp_path: Path) -> None:
    p = tmp_path / "ks.json"
    os.symlink(tmp_path / "nonexistent_target.json", p)  # dangling symlink
    assert KillSwitch(p).read() is KillSwitchState.TRIPPED


def test_finding6_failed_escalation_write_still_blocks(tmp_path: Path) -> None:
    sub = tmp_path / "ro"
    sub.mkdir()
    p = sub / "ks.json"
    k = KillSwitch(p)
    assert k.read() is KillSwitchState.ARMED
    os.chmod(sub, 0o500)  # read-only dir: the state write will fail
    try:
        with pytest.raises(OSError):
            k.trip("emergency")
        # The disk write failed, but the in-memory latch escalated -> fail CLOSED.
        assert k.read() is KillSwitchState.TRIPPED
        assert k.allows_new_orders() is False
    finally:
        os.chmod(sub, 0o700)


def test_verify_writable_raises_on_readonly_store(tmp_path: Path) -> None:
    sub = tmp_path / "ro2"
    sub.mkdir()
    os.chmod(sub, 0o500)
    try:
        with pytest.raises(KillSwitchUnwritableError):
            KillSwitch(sub / "ks.json").verify_writable()
    finally:
        os.chmod(sub, 0o700)


def test_verify_writable_ok_on_writable_store(tmp_path: Path) -> None:
    KillSwitch(tmp_path / "ks.json").verify_writable()  # must not raise
