"""C8 — §8 abandonment evaluator + §5.2 paging escalation ladder (Increment 6 PART B)."""

from __future__ import annotations

from pathlib import Path

import pytest

from trading.executor.kill_switch import KillSwitch, KillSwitchState
from trading.guards.abandonment import (
    AbandonmentState,
    engage_abandonment,
    evaluate_abandonment,
)
from trading.guards.page_escalation import EscalationAction, PageEscalation, apply_escalation
from trading.notify.errors import NotifierError
from trading.notify.telegram import Severity
from trading.risk.caps import check_equity_floor, check_total_loss_abandon
from trading.risk.schema import RiskConfig


def _cfg() -> RiskConfig:
    return RiskConfig(
        live_mode=False,
        per_trade_risk_usd=1.0,
        max_daily_loss_usd=5.0,
        equity_floor_usd=20.0,
        total_loss_abandon_usd=30.0,
        max_position_concentration_pct=30.0,
        max_consecutive_errors=5,
    )


def _healthy(**over: object) -> AbandonmentState:
    base: dict[str, object] = dict(cumulative_loss_usd=0.0, equity_usd=50.0)
    base.update(over)
    return AbandonmentState(**base)  # type: ignore[arg-type]


class FakePager:
    def __init__(self, raise_on: Severity | None = None) -> None:
        self.calls: list[tuple[Severity, str]] = []
        self._raise_on = raise_on

    def page_operator(self, severity: Severity, text: str) -> None:
        self.calls.append((severity, text))
        if self._raise_on is severity:
            raise NotifierError("boom")


# --- §8 abandonment boundary table ---


def test_no_trigger_when_healthy() -> None:
    assert evaluate_abandonment(_healthy(), _cfg()).triggered is False


@pytest.mark.parametrize(
    ("over", "trigger_substr"),
    [
        (dict(cumulative_loss_usd=30.01), "total_loss"),
        (dict(equity_usd=19.99), "equity_floor"),
        (dict(consecutive_scheduler_errors=5), "consecutive_errors"),
        (dict(recon_red=True), "reconciliation"),
        (dict(llm_calls_24h=100, llm_failures_24h=31), "llm_failure"),
        (dict(mistake_counts_7d=(1, 3)), "mistake"),
        (dict(calib_weeks_over_30pct=2), "calibration"),
        (dict(abandon_marker_present=True), "operator_abandon"),
    ],
)
def test_each_trigger_fires_at_boundary(over: dict[str, object], trigger_substr: str) -> None:
    v = evaluate_abandonment(_healthy(**over), _cfg())
    assert v.triggered is True
    assert v.trigger_id is not None and trigger_substr in v.trigger_id


@pytest.mark.parametrize(
    "over",
    [
        dict(cumulative_loss_usd=30.0),  # not strictly over
        dict(equity_usd=20.0),  # at floor, not below
        dict(consecutive_scheduler_errors=4),
        dict(llm_calls_24h=100, llm_failures_24h=30),  # 30% not > 30%
        dict(mistake_counts_7d=(2, 2)),
        dict(calib_weeks_over_30pct=1),
    ],
)
def test_just_inside_does_not_trigger(over: dict[str, object]) -> None:
    assert evaluate_abandonment(_healthy(**over), _cfg()).triggered is False


def test_loss_and_equity_triggers_agree_with_the_sealed_caps() -> None:
    # REUSE proof: §8.1/§8.2 must AGREE with the pre-submit caps on the same inputs (no
    # re-encoding).
    cfg = _cfg()
    for loss in (29.0, 30.0, 30.01, 31.0):
        cap_ok = check_total_loss_abandon(cfg, loss).ok
        ab = evaluate_abandonment(_healthy(cumulative_loss_usd=loss), cfg)
        triggered_by_loss = ab.trigger_id is not None and "total_loss" in ab.trigger_id
        assert triggered_by_loss == (not cap_ok)
    for eq in (50.0, 20.0, 19.99, 10.0):
        cap_ok = check_equity_floor(cfg, eq).ok
        ab = evaluate_abandonment(_healthy(equity_usd=eq), cfg)
        triggered_by_eq = ab.trigger_id is not None and "equity_floor" in ab.trigger_id
        assert triggered_by_eq == (not cap_ok)


def test_llm_failure_fails_closed_on_zero_calls_with_a_failure() -> None:
    v = evaluate_abandonment(_healthy(llm_calls_24h=0, llm_failures_24h=1), _cfg())
    assert v.triggered is True and v.trigger_id is not None and "llm_failure" in v.trigger_id


def test_engage_abandonment_hard_stops_and_is_idempotent(tmp_path: Path) -> None:
    ks = KillSwitch(tmp_path / "ks.json")
    pager = FakePager()
    v = evaluate_abandonment(_healthy(cumulative_loss_usd=31.0), _cfg())
    engage_abandonment(v, ks, pager)
    assert ks.read() is KillSwitchState.HARD_STOPPED
    engage_abandonment(v, ks, pager)  # idempotent (monotonic hard_stop)
    assert ks.read() is KillSwitchState.HARD_STOPPED
    assert any(sev is Severity.RED for sev, _ in pager.calls)


def test_engage_does_nothing_when_not_triggered(tmp_path: Path) -> None:
    ks = KillSwitch(tmp_path / "ks.json")
    engage_abandonment(evaluate_abandonment(_healthy(), _cfg()), ks, FakePager())
    assert ks.read() is KillSwitchState.ARMED


# --- §5.2 paging escalation ladder ---


def test_escalation_ladder_tick_table(tmp_path: Path) -> None:
    esc = PageEscalation(tmp_path / "page.json", ack_path=tmp_path / "PAGE_ACK")
    esc.open_page("page-1", opened_epoch=1000.0)
    assert esc.tick(1000.0) is EscalationAction.NONE
    assert esc.tick(1000.0 + 901) is EscalationAction.RESEND_15
    assert esc.tick(1000.0 + 1801) is EscalationAction.RESEND_30
    assert esc.tick(1000.0 + 3601) is EscalationAction.TERMINAL_LIQUIDATE


def test_acknowledge_stops_escalation(tmp_path: Path) -> None:
    esc = PageEscalation(tmp_path / "page.json", ack_path=tmp_path / "PAGE_ACK")
    esc.open_page("page-1", opened_epoch=1000.0)
    esc.acknowledge("page-1")
    assert esc.tick(1000.0 + 3601) is EscalationAction.NONE


def test_escalation_state_survives_restart(tmp_path: Path) -> None:
    PageEscalation(tmp_path / "page.json").open_page("page-1", opened_epoch=1000.0)
    # a fresh instance (crash/restart) still escalates from the persisted opened_epoch
    reloaded = PageEscalation(tmp_path / "page.json")
    assert reloaded.tick(1000.0 + 3601) is EscalationAction.TERMINAL_LIQUIDATE


def test_no_open_page_is_none(tmp_path: Path) -> None:
    assert PageEscalation(tmp_path / "page.json").tick(99999.0) is EscalationAction.NONE


def test_apply_terminal_liquidate_does_all_three(tmp_path: Path) -> None:
    ks = KillSwitch(tmp_path / "ks.json")
    pager = FakePager()
    flats: list[bool] = []
    apply_escalation(
        EscalationAction.TERMINAL_LIQUIDATE, ks, pager, broker_flat_fn=lambda: flats.append(True)
    )
    assert flats == [True]  # closed all
    assert ks.read() is KillSwitchState.HARD_STOPPED  # halted
    assert any(sev is Severity.RED for sev, _ in pager.calls)  # final RED page


def test_apply_resend_only_pages(tmp_path: Path) -> None:
    ks = KillSwitch(tmp_path / "ks.json")
    pager = FakePager()
    apply_escalation(EscalationAction.RESEND_15, ks, pager, broker_flat_fn=lambda: None)
    assert ks.read() is KillSwitchState.ARMED  # a resend never halts
    assert pager.calls and pager.calls[0][0] is Severity.ORANGE
