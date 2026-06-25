"""C2 / GRD-4 — a latched HARD_STOP survives deletion of the kill-switch json file (tombstone).

Inc-6 left a latched HARD_STOP NOT durable across deletion of ``state/kill_switch.json`` (the
in-memory latch dies on restart; a fresh process re-read a MISSING json as ARMED). Inc-7 adds a
durable ``HARD_STOP.tombstone`` written on the first hard_stop: a missing json + a present tombstone
fails SAFE to HARD_STOPPED. The crash-ordering rule (skeptic GRD-4) is pinned both directions:
``arm`` writes the ARMED json FIRST then unlinks the tombstone, and a present validly-ARMED json
WINS over a stale tombstone. The whole-dir ``rm -rf state/`` wipe is the operator/Murphy residual.
"""

from __future__ import annotations

from pathlib import Path

from trading.executor.kill_switch import KillSwitch, KillSwitchState

_TOMB = "HARD_STOP.tombstone"


def test_hard_stop_writes_a_durable_tombstone(tmp_path: Path) -> None:
    KillSwitch(tmp_path / "ks.json").hard_stop("abandonment")
    assert (tmp_path / _TOMB).exists()


def test_hard_stop_survives_kill_switch_json_deletion(tmp_path: Path) -> None:
    p = tmp_path / "ks.json"
    KillSwitch(p).hard_stop("abandonment")
    p.unlink()  # the single-file attack: delete ONLY the json, leaving the tombstone
    # A fresh instance (a restarted process) must still read HARD_STOPPED off the tombstone.
    fresh = KillSwitch(p)
    assert fresh.read() is KillSwitchState.HARD_STOPPED
    assert fresh.allows_new_orders() is False


def test_missing_json_with_tombstone_is_hard_stopped(tmp_path: Path) -> None:
    # No json at all but a tombstone present (e.g. json deleted, process restarted) -> HARD_STOPPED.
    (tmp_path / _TOMB).write_text('{"state": "HARD_STOPPED", "reason": "x"}', encoding="utf-8")
    assert KillSwitch(tmp_path / "ks.json").read() is KillSwitchState.HARD_STOPPED


def test_rearm_removes_the_tombstone_and_is_durable(tmp_path: Path) -> None:
    p = tmp_path / "ks.json"
    k = KillSwitch(p)
    k.hard_stop("abandon")
    assert (tmp_path / _TOMB).exists()
    k.arm(operator_authority=True)
    assert not (tmp_path / _TOMB).exists()  # re-arm cleared the terminal marker
    # a fresh process reads the durable ARMED json (not a stale tombstone).
    assert KillSwitch(p).read() is KillSwitchState.ARMED


def test_rearm_wins_over_a_stale_tombstone(tmp_path: Path) -> None:
    # Crash-ordering: arm() wrote the ARMED json but crashed BEFORE unlinking the tombstone, leaving
    # json=ARMED + a STALE tombstone. A present, valid ARMED json MUST WIN (the json is the
    # authority; _load never consults the tombstone when the json is readable).
    p = tmp_path / "ks.json"
    KillSwitch(p).hard_stop("abandon")  # writes json=HARD_STOPPED + tombstone
    p.write_text('{"state": "ARMED", "reason": "operator re-arm"}', encoding="utf-8")  # re-arm json
    assert (tmp_path / _TOMB).exists()  # tombstone NOT yet unlinked (the simulated crash)
    assert KillSwitch(p).read() is KillSwitchState.ARMED  # the valid ARMED json wins


def test_fresh_start_without_tombstone_is_armed(tmp_path: Path) -> None:
    # No regression: a genuine first boot (no json, no tombstone) is ARMED.
    assert KillSwitch(tmp_path / "ks.json").read() is KillSwitchState.ARMED


def test_rm_rf_state_dir_residual_is_a_fresh_armed_boot(tmp_path: Path) -> None:
    # Documented operator/Murphy residual: a whole-dir ``rm -rf state/`` removes BOTH the json and
    # the tombstone. With the dir gone, ``read()`` fails SAFE to TRIPPED (unresolvable-path);
    # but the next boot recreates ``state/`` (preflight's mkdir), at which point a missing json + no
    # tombstone is indistinguishable from a first-ever boot -> ARMED. No in-band file defends this.
    state = tmp_path / "state"
    state.mkdir()
    KillSwitch(state / "ks.json").hard_stop("abandon")
    for f in state.iterdir():
        f.unlink()
    state.rmdir()
    assert (
        KillSwitch(state / "ks.json").read() is KillSwitchState.TRIPPED
    )  # dir gone -> conservative
    state.mkdir()  # the next boot recreates state/ (preflight) -> indistinguishable from first boot
    assert KillSwitch(state / "ks.json").read() is KillSwitchState.ARMED
