"""C3 — GRD-1 (arm the §5.2 ladder), GRD-2 (paging fails CLOSED), GRD-3 (§8 auto-flatten).

These were the carried Inc-6 tripwires that ARM the instant a driver wires the acting loop. The loop
now: opens the §5.2 escalation ladder on a RED disaster (idempotent first-write-wins so the 60-min
terminal clock is never reset — GRD-1); leaves a durable PAGE_PENDING tombstone + keeps the ladder
running when a RED page was NOT confirmed delivered, so a dropped page fails CLOSED (GRD-2); and
auto-flattens open positions on §8 abandonment (GRD-3, after the durable hard_stop).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from trading.executor.broker_paper import BrokerOrderAck, PaperBroker
from trading.executor.idempotency import InMemoryIdempotencyStore
from trading.executor.intent import OrderIntent
from trading.executor.invariants import AccountSnapshot
from trading.executor.kill_switch import KillSwitch, KillSwitchState
from trading.executor.loop import LoopDeps, LoopInputs, run_loop_pass
from trading.guards.abandonment import AbandonmentState, engage_abandonment, evaluate_abandonment
from trading.guards.inputs import GuardState
from trading.guards.page_escalation import PageEscalation
from trading.guards.panel import GuardPanel
from trading.notify.errors import NotifierError
from trading.notify.telegram import Severity
from trading.risk.schema import RiskConfig


class FakePager:
    def __init__(self, *, raise_on: Severity | None = None) -> None:
        self.calls: list[tuple[Severity, str]] = []
        self._raise_on = raise_on

    def page_operator(self, severity: Severity, text: str) -> None:
        self.calls.append((severity, text))
        if self._raise_on is severity:
            raise NotifierError("boom")


class SpyBroker(PaperBroker):
    def __init__(self) -> None:
        super().__init__()
        self.flats = 0

    def flat_all(self) -> bool:
        self.flats += 1  # Alpaca close_all_positions is a no-op when already flat (idempotent)
        return True

    def submit(self, intent: OrderIntent, client_order_id: str) -> BrokerOrderAck:
        raise AssertionError("submit must never be called on a disaster pass")


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


def _guard_state(**over: Any) -> GuardState:
    base: dict[str, Any] = dict(
        now_epoch=1000.0,
        data_as_of_epoch=1000.0,
        last_broker_ok_epoch=1000.0,
        last_llm_ok_epoch=1000.0,
        equity_now=50.0,
        equity_prev=50.0,
        equity_dt_s=60.0,
        orders_in_window=0,
        order_baseline=1.0,
        ntp_offset_s=0.0,
    )
    base.update(over)
    return GuardState(**base)


def _aband(**over: Any) -> AbandonmentState:
    base: dict[str, Any] = dict(cumulative_loss_usd=0.0, equity_usd=50.0)
    base.update(over)
    return AbandonmentState(**base)


def _deps(tmp_path: Path, *, pager: FakePager | None = None) -> LoopDeps:
    return LoopDeps(
        kill_switch=KillSwitch(tmp_path / "ks.json"),
        notifier=pager or FakePager(),
        broker=SpyBroker(),
        store=InMemoryIdempotencyStore(),
        guard_panel=GuardPanel(),
        cfg=_cfg(),
        page_escalation=PageEscalation(tmp_path / "page.json"),
    )


def _inputs(
    *,
    guard_state: GuardState | None = None,
    aband: AbandonmentState | None = None,
    now: float = 1000.0,
) -> LoopInputs:
    return LoopInputs(
        local_positions={},
        broker_positions={},
        drift_since_epoch=None,
        now_epoch=now,
        guard_state=guard_state or _guard_state(),
        abandonment_state=aband or _aband(),
        snapshot=AccountSnapshot(50.0, 0.0, 0.0, 1000.0, 1000.0),
        candidates=(),
    )


def _opened_epoch(tmp_path: Path) -> float:
    return float(json.loads((tmp_path / "page.json").read_text())["opened_epoch"])


# --- GRD-1: the loop arms the ladder ONCE; the 60-min terminal liquidate fires ---


def test_loop_arms_ladder_once_and_terminal_liquidate_fires(tmp_path: Path) -> None:
    deps = _deps(tmp_path)
    broker = deps.broker
    assert isinstance(broker, SpyBroker)
    red = _guard_state(ntp_offset_s=None)  # G6 RED disaster
    run_loop_pass(_inputs(guard_state=red, now=1000.0), deps)  # opens the episode at t=1000
    assert deps.page_escalation.is_open() is True
    assert _opened_epoch(tmp_path) == 1000.0
    assert deps.kill_switch.read() is KillSwitchState.HARD_STOPPED  # RED guard latched the halt
    flats_after_disaster = broker.flats  # the loop auto-flatted the RED pass

    # A LATER pass whose guard CLEARED but the switch is still HARD_STOPPED: the loop does NOT
    # auto-flat, so the ONLY flat is the ladder's terminal liquidate at +60 min.
    run_loop_pass(_inputs(guard_state=_guard_state(), now=1000.0 + 3601), deps)
    assert broker.flats == flats_after_disaster + 1  # exactly the terminal-liquidate flat
    assert deps.kill_switch.read() is KillSwitchState.HARD_STOPPED
    assert any(sev is Severity.RED for sev, _ in deps.notifier.calls)


def test_ladder_clock_monotonic_across_cause_change(tmp_path: Path) -> None:
    # skeptic A4: a co-occurring SECOND disaster (a different cause) must NOT reset opened_epoch, or
    # the 60-min terminal clock would never arrive. First-write-wins per episode.
    deps = _deps(tmp_path)
    run_loop_pass(
        _inputs(guard_state=_guard_state(ntp_offset_s=None), now=1000.0), deps
    )  # guard RED
    assert _opened_epoch(tmp_path) == 1000.0
    # later pass: BOTH the guard RED and §8 abandonment fire (the cause flips) at a later t.
    run_loop_pass(
        _inputs(
            guard_state=_guard_state(ntp_offset_s=None),
            aband=_aband(cumulative_loss_usd=31.0),
            now=1500.0,
        ),
        deps,
    )
    assert _opened_epoch(tmp_path) == 1000.0  # opened_epoch UNCHANGED (clock not reset)


# --- GRD-2: a dropped RED page fails CLOSED (still arms the ladder + leaves a tombstone) ---


def test_dropped_red_guard_page_still_enters_ladder_and_leaves_tombstone(tmp_path: Path) -> None:
    deps = _deps(tmp_path, pager=FakePager(raise_on=Severity.RED))  # the RED page will be dropped
    out = run_loop_pass(_inputs(guard_state=_guard_state(ntp_offset_s=None)), deps)
    assert out.page_undelivered is True
    assert (
        deps.page_escalation.is_open() is True
    )  # the armed ladder IS the retry (resend->liquidate)
    assert (
        deps.page_escalation.is_pending() is True
    )  # durable observable signal of the dropped page
    assert deps.kill_switch.read() is KillSwitchState.HARD_STOPPED  # the halt still latched


def test_dropped_abandonment_page_is_undelivered_and_arms_ladder(tmp_path: Path) -> None:
    deps = _deps(tmp_path, pager=FakePager(raise_on=Severity.RED))
    out = run_loop_pass(_inputs(aband=_aband(cumulative_loss_usd=31.0)), deps)
    assert out.page_undelivered is True
    assert deps.page_escalation.is_open() is True and deps.page_escalation.is_pending() is True


def test_page_pending_cleared_only_by_operator_ack_or_resolve(tmp_path: Path) -> None:
    esc = PageEscalation(tmp_path / "page.json")
    esc.open_page("RED:guard", opened_epoch=1000.0)
    esc.mark_pending("RED:guard", opened_epoch=1000.0)
    assert esc.is_pending() is True
    esc.acknowledge("RED:guard")  # operator ACK clears the tombstone
    assert esc.is_pending() is False
    esc.mark_pending("RED:guard", opened_epoch=1000.0)
    esc.resolve()  # operator recovery (resolve) clears it too
    assert esc.is_pending() is False


def test_recovered_rearmed_pass_resolves_the_episode(tmp_path: Path) -> None:
    deps = _deps(tmp_path)
    run_loop_pass(
        _inputs(guard_state=_guard_state(ntp_offset_s=None)), deps
    )  # disaster opens episode
    assert deps.page_escalation.is_open() is True
    deps.kill_switch.arm(operator_authority=True)  # operator recovers the system
    run_loop_pass(_inputs(), deps)  # a clean (ARMED, no-disaster) pass resolves the stale episode
    assert deps.page_escalation.is_open() is False


# --- GRD-3: §8 abandonment auto-flattens open positions (after the durable hard_stop) ---


def test_abandonment_auto_flattens_positions(tmp_path: Path) -> None:
    deps = _deps(tmp_path)
    out = run_loop_pass(_inputs(aband=_aband(cumulative_loss_usd=31.0)), deps)
    assert out.disaster is True and out.auto_flatted is True
    broker = deps.broker
    assert isinstance(broker, SpyBroker)
    assert broker.flats >= 1  # GRD-3: positions flattened on abandonment, not just hard-stopped
    assert deps.kill_switch.read() is KillSwitchState.HARD_STOPPED


def test_engage_hard_stops_before_flat_and_a_flat_failure_does_not_unhalt(tmp_path: Path) -> None:
    ks = KillSwitch(tmp_path / "ks.json")
    seen_state: list[KillSwitchState] = []

    def failing_flat() -> None:
        seen_state.append(ks.read())  # the state visible to the flat (must already be HARD_STOPPED)
        raise RuntimeError("broker unreachable")  # the flat itself fails

    v = evaluate_abandonment(_aband(cumulative_loss_usd=31.0), _cfg())
    paged = engage_abandonment(v, ks, FakePager(), broker_flat_fn=failing_flat)
    assert seen_state == [KillSwitchState.HARD_STOPPED]  # hard_stop latched BEFORE the flat ran
    assert ks.read() is KillSwitchState.HARD_STOPPED  # a flat failure never un-halts us
    assert paged is True  # the RED page still delivered
