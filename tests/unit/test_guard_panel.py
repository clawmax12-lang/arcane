"""C7 — apply_guards: the single kill-switch mutator + graduated response (Increment 6 PART B)."""

from __future__ import annotations

from pathlib import Path

from trading.executor.kill_switch import KillSwitch, KillSwitchState
from trading.executor.reconciler import ReconLevel, ReconResult
from trading.guards.levels import GuardLevel, GuardResult
from trading.guards.panel import apply_guards, g3_from_recon
from trading.notify.errors import NotifierError
from trading.notify.telegram import Severity


class FakePager:
    def __init__(self, raise_on: Severity | None = None) -> None:
        self.calls: list[tuple[Severity, str]] = []
        self._raise_on = raise_on

    def page_operator(self, severity: Severity, text: str) -> None:
        self.calls.append((severity, text))
        if self._raise_on is not None and severity is self._raise_on:
            raise NotifierError("simulated page delivery failure")


def _g(guard_id: str, level: GuardLevel, *, gates: bool) -> GuardResult:
    return GuardResult(guard_id=guard_id, level=level, reason="r", gates_orders=gates)


def _ks(tmp_path: Path) -> KillSwitch:
    return KillSwitch(tmp_path / "ks.json")


def test_green_yellow_do_not_mutate_kill_switch(tmp_path: Path) -> None:
    ks = _ks(tmp_path)
    pager = FakePager()
    out = apply_guards([_g("G1", GuardLevel.GREEN, gates=True)], ks, pager)
    apply_guards([_g("G1", GuardLevel.YELLOW, gates=True)], ks, pager)
    assert ks.read() is KillSwitchState.ARMED
    assert out.auto_flat is False and out.tripped is False


def test_orange_gating_trips_only(tmp_path: Path) -> None:
    ks = _ks(tmp_path)
    pager = FakePager()
    out = apply_guards([_g("G1", GuardLevel.ORANGE, gates=True)], ks, pager)
    assert ks.read() is KillSwitchState.TRIPPED
    assert out.tripped is True and out.auto_flat is False


def test_red_gating_hard_stops_pages_and_auto_flats(tmp_path: Path) -> None:
    ks = _ks(tmp_path)
    pager = FakePager()
    out = apply_guards([_g("G6", GuardLevel.RED, gates=True)], ks, pager)
    assert ks.read() is KillSwitchState.HARD_STOPPED
    assert out.auto_flat is True and out.paged is True and out.page_error is None
    assert pager.calls and pager.calls[0][0] is Severity.RED


def test_red_page_failure_still_hard_stops_teeth(tmp_path: Path) -> None:
    # The disaster hard_stop is latched BEFORE the page; a page that raises must NOT abort it.
    ks = _ks(tmp_path)
    pager = FakePager(raise_on=Severity.RED)
    out = apply_guards([_g("G6", GuardLevel.RED, gates=True)], ks, pager)  # must not raise
    assert ks.read() is KillSwitchState.HARD_STOPPED
    assert out.auto_flat is True and out.paged is False and out.page_error == "NotifierError"


def test_advisory_guard_never_mutates_kill_switch(tmp_path: Path) -> None:
    # §4.3: a DERIVED/TEXTUAL guard (gates_orders=False) may page but NEVER touch the kill switch.
    ks = _ks(tmp_path)
    pager = FakePager()
    out = apply_guards([_g("G10_prompt_injection", GuardLevel.ORANGE, gates=False)], ks, pager)
    assert ks.read() is KillSwitchState.ARMED  # NOT tripped
    assert out.tripped is False and out.auto_flat is False
    assert pager.calls and pager.calls[0][0] is Severity.ORANGE  # advisory page only


def test_panel_assess_includes_g3_from_recon() -> None:
    recon = ReconResult(ReconLevel.RED, 3, 700.0, True, "drift")
    g3 = g3_from_recon(recon)
    assert g3.guard_id == "G3_reconciliation_drift"
    assert g3.level is GuardLevel.RED and g3.gates_orders is True
