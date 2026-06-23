"""C13 — run_loop_pass: safety escalation strictly precedes any submit (Increment 6 PART C)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from trading.bias_gate.gate import FROZEN_COMPONENT_NAMES, GateComponent, GateDecision
from trading.executor.broker_paper import BrokerOrderAck, PaperBroker
from trading.executor.grant import AllocationGrant
from trading.executor.idempotency import InMemoryIdempotencyStore
from trading.executor.intent import OrderIntent, Side
from trading.executor.invariants import AccountSnapshot
from trading.executor.kill_switch import KillSwitch, KillSwitchState
from trading.executor.loop import LoopDeps, LoopInputs, SubmitCandidate, run_loop_pass
from trading.executor.sizing import HardQuote, TargetPosition
from trading.executor.submit import GO_PHRASE
from trading.guards.abandonment import AbandonmentState
from trading.guards.inputs import GuardState
from trading.guards.panel import GuardPanel
from trading.notify.telegram import Severity
from trading.risk.schema import RiskConfig

_SPEC = "arcane-strategy-x"


class FakePager:
    def __init__(self) -> None:
        self.calls: list[tuple[Severity, str]] = []

    def page_operator(self, severity: Severity, text: str) -> None:
        self.calls.append((severity, text))


class SpyBroker(PaperBroker):
    def __init__(self) -> None:
        super().__init__()
        self.flats = 0
        self.submits: list[str] = []

    def flat_all(self) -> bool:
        self.flats += 1
        return True

    def submit(self, intent: OrderIntent, client_order_id: str) -> BrokerOrderAck:
        self.submits.append(client_order_id)
        return BrokerOrderAck(client_order_id, True, "accepted (fake)")


def _cfg(*, per_trade: float = 5.0) -> RiskConfig:
    return RiskConfig(
        live_mode=False,
        per_trade_risk_usd=per_trade,
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


def _snapshot() -> AccountSnapshot:
    return AccountSnapshot(50.0, 0.0, 0.0, 1000.0, 1000.0)


def _deps(
    tmp_path: Path, *, per_trade: float = 5.0, go: bool = False
) -> tuple[LoopDeps, SpyBroker]:
    broker = SpyBroker()
    go_path = tmp_path / "SUBMIT_GO"
    if go:
        go_path.write_text(f"{GO_PHRASE}\n{_SPEC}\n", encoding="utf-8")
    deps = LoopDeps(
        kill_switch=KillSwitch(tmp_path / "ks.json"),
        notifier=FakePager(),
        broker=broker,
        store=InMemoryIdempotencyStore(),
        guard_panel=GuardPanel(),
        cfg=_cfg(per_trade=per_trade),
        go_marker_path=go_path,
    )
    return deps, broker


def _candidate() -> SubmitCandidate:
    comps = tuple(GateComponent(n, True, "") for n in FROZEN_COMPONENT_NAMES)
    grant = AllocationGrant.from_decision(
        GateDecision(_SPEC, True, comps, 17, ()), universe_artifact_hash="arcane-univ-x"
    )
    target = TargetPosition("ts_momentum_blend", "AAPL", Side.BUY, spec_hash=_SPEC)
    return SubmitCandidate(grant, target, HardQuote("AAPL", 2.0, 1000.0))


def _inputs(
    *,
    guard_state: GuardState | None = None,
    aband: AbandonmentState | None = None,
    local: dict[str, float] | None = None,
    broker_pos: dict[str, float] | None = None,
    drift_since: float | None = None,
    now: float = 1000.0,
    candidates: tuple[SubmitCandidate, ...] = (),
) -> LoopInputs:
    return LoopInputs(
        local_positions=local or {},
        broker_positions=broker_pos or {},
        drift_since_epoch=drift_since,
        now_epoch=now,
        guard_state=guard_state or _guard_state(),
        abandonment_state=aband or _aband(),
        snapshot=_snapshot(),
        candidates=candidates,
    )


def test_all_green_no_candidates_no_submit(tmp_path: Path) -> None:
    deps, broker = _deps(tmp_path)
    out = run_loop_pass(_inputs(), deps)
    assert out.disaster is False and out.submitted_count == 0
    assert broker.flats == 0 and broker.submits == []
    assert deps.kill_switch.read() is KillSwitchState.ARMED


def test_recon_red_auto_flats_and_blocks_submit_even_with_a_candidate(tmp_path: Path) -> None:
    # THE ordering teeth: a RED recon pass auto-flats and submits ZERO even though a grant is
    # present.
    deps, broker = _deps(tmp_path, go=True)
    out = run_loop_pass(
        _inputs(
            local={"A": 1.0, "B": 1.0, "C": 1.0},
            broker_pos={},
            drift_since=1000.0,
            now=1700.0,
            candidates=(_candidate(),),
        ),
        deps,
    )
    assert out.disaster is True and out.auto_flatted is True and out.submitted_count == 0
    assert broker.submits == []  # NEVER submitted on a disaster pass
    assert deps.kill_switch.read() is KillSwitchState.HARD_STOPPED


def test_red_guard_blocks_submit(tmp_path: Path) -> None:
    deps, broker = _deps(tmp_path, go=True)
    out = run_loop_pass(
        _inputs(guard_state=_guard_state(ntp_offset_s=None), candidates=(_candidate(),)),  # G6 RED
        deps,
    )
    assert out.disaster is True and out.submitted_count == 0 and broker.submits == []
    assert deps.kill_switch.read() is KillSwitchState.HARD_STOPPED


def test_abandonment_trigger_blocks_submit(tmp_path: Path) -> None:
    deps, broker = _deps(tmp_path, go=True)
    out = run_loop_pass(
        _inputs(aband=_aband(cumulative_loss_usd=31.0), candidates=(_candidate(),)), deps
    )
    assert out.disaster is True and out.submitted_count == 0 and broker.submits == []
    assert deps.kill_switch.read() is KillSwitchState.HARD_STOPPED


def test_tripped_switch_still_escalates_on_red_guard(tmp_path: Path) -> None:
    deps, broker = _deps(tmp_path)
    deps.kill_switch.trip("prior pause")
    out = run_loop_pass(_inputs(guard_state=_guard_state(ntp_offset_s=2.0)), deps)  # G6 RED
    assert out.armed_at_start is False  # already TRIPPED
    assert deps.kill_switch.read() is KillSwitchState.HARD_STOPPED  # escalated to RED anyway
    assert out.submitted_count == 0


def test_all_green_with_go_submits_when_caps_allow(tmp_path: Path) -> None:
    # Proves the path CAN act: all-green + a valid GO + a $2 stock under a $5 cap -> 1 submit.
    deps, broker = _deps(tmp_path, per_trade=5.0, go=True)
    out = run_loop_pass(_inputs(candidates=(_candidate(),)), deps)
    assert out.disaster is False and out.submitted_count == 1
    assert len(broker.submits) == 1


def test_dollar_cap_yields_zero_submit_even_all_green_with_go(tmp_path: Path) -> None:
    # The real $1 cap with a real-priced share -> NoTrade -> zero submits (the expected null).
    deps, broker = _deps(tmp_path, per_trade=1.0, go=True)
    expensive = SubmitCandidate(
        _candidate().grant,
        TargetPosition("ts_momentum_blend", "AAPL", Side.BUY, spec_hash=_SPEC),
        HardQuote("AAPL", 150.0, 1000.0),
    )
    out = run_loop_pass(_inputs(candidates=(expensive,)), deps)
    assert out.disaster is False and out.submitted_count == 0 and broker.submits == []


def test_scheduler_error_in_safety_steps_fails_closed(tmp_path: Path) -> None:
    class BoomPanel(GuardPanel):
        def assess(self, state: Any, recon: Any) -> Any:
            raise RuntimeError("guard adapter blew up")

    deps, broker = _deps(tmp_path, go=True)
    deps = LoopDeps(
        kill_switch=deps.kill_switch,
        notifier=deps.notifier,
        broker=broker,
        store=deps.store,
        guard_panel=BoomPanel(),
        cfg=deps.cfg,
        go_marker_path=deps.go_marker_path,
    )
    out = run_loop_pass(_inputs(candidates=(_candidate(),)), deps)
    assert out.scheduler_error == "RuntimeError"
    assert out.submitted_count == 0 and broker.submits == []
