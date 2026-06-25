"""C7 — the driver: the FIRST real caller of the acting path, RECORD-ONLY (Inc-7 PART C).

``drive_once`` wires PIT-universe → backtest → bias gate → allocator → run_loop_pass. With the 4
edgeless toys the gate KILLS all → the allocator allocates NOBODY → the loop submits NOTHING (ADR0).
It is fail-closed (a Polygon error / unbindable universe ABORTS to zero candidates, never partial),
the safety machinery still runs on an assembly error, and it NEVER writes the operator SUBMIT_GO.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import _gate_fixtures as fx

from trading.backtest.engine import SymbolPanel
from trading.bias_gate.high_water_mark import NTrialsHighWaterMark
from trading.data.errors import PolygonProvenanceError
from trading.data.membership_cache import MembershipCache
from trading.data.polygon_universe import PolygonPITUniverse
from trading.driver.run_once import DriverContext, drive_once
from trading.executor.broker_paper import BrokerOrderAck, PaperBroker
from trading.executor.idempotency import InMemoryIdempotencyStore
from trading.executor.intent import OrderIntent
from trading.executor.invariants import AccountSnapshot
from trading.executor.kill_switch import KillSwitch, KillSwitchState
from trading.executor.loop import LoopDeps, LoopInputs
from trading.guards.abandonment import AbandonmentState
from trading.guards.inputs import GuardState
from trading.guards.panel import GuardPanel
from trading.notify.telegram import Severity
from trading.regime.model import DeterministicRegimeModel
from trading.risk.schema import RiskConfig

_TOYS = ("ts_momentum_blend", "ts_meanrev_short", "trend_location", "lowvol_liquid_tilt")
_SYMS = ("SYM0", "SYM1")


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


def _pit_panel() -> SymbolPanel:
    return SymbolPanel(
        bars={s: fx.bars(1300, seed=20 + i) for i, s in enumerate(_SYMS)},
        survivorship_unverified=False,
    )


def _fetch_active(symbol: str, date_str: str) -> list[dict]:
    return [{"ticker": symbol, "active": True, "delisted_utc": None, "list_date": None}]


def _fetch_raises(symbol: str, date_str: str) -> list[dict]:
    raise PolygonProvenanceError("polygon 429 (fake)")


def _ctx(
    tmp_path: Path,
    *,
    fetch: Any = _fetch_active,
    aband: AbandonmentState | None = None,
    broker: SpyBroker | None = None,
) -> DriverContext:
    led = fx.ledger(tmp_path)
    reg = fx.registry(led)
    panel = _pit_panel()
    cache = MembershipCache(tmp_path / "mem")
    universe = PolygonPITUniverse(
        _SYMS, fetch=fetch, cache=cache
    )  # seals the artifact into `cache`
    loop_inputs = LoopInputs(
        local_positions={},
        broker_positions={},
        drift_since_epoch=None,
        now_epoch=1000.0,
        guard_state=_guard_state(),
        abandonment_state=aband or AbandonmentState(cumulative_loss_usd=0.0, equity_usd=50.0),
        snapshot=AccountSnapshot(50.0, 0.0, 0.0, 1000.0, 1000.0),
        candidates=(),
    )
    loop_deps = LoopDeps(
        kill_switch=KillSwitch(tmp_path / "ks.json"),
        notifier=FakePager(),
        broker=broker or SpyBroker(),
        store=InMemoryIdempotencyStore(),
        guard_panel=GuardPanel(),
        cfg=_cfg(),
        go_marker_path=tmp_path / "SUBMIT_GO",  # must never be created by the driver
    )
    return DriverContext(
        strategies=[fx.resolved(name, reg) for name in _TOYS],
        panel=panel,
        universe=universe,
        market_proxy=fx.bars(400, seed=99),
        as_of=fx.AS_OF,
        cost=fx.CostModel(),
        folds=fx.WalkForwardConfig(purge_bars=200),
        ledger=led,
        hwm=NTrialsHighWaterMark(tmp_path / "hwm.json"),
        membership_cache=cache,
        regime_model=DeterministicRegimeModel(),
        loop_inputs=loop_inputs,
        loop_deps=loop_deps,
    )


def test_driver_four_toys_zero_submits_end_to_end(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    out = drive_once(ctx)
    assert out.assembly_error is None
    assert out.snapshot_hash is not None  # the proof-bearing PIT snapshot was built + sealed
    assert len(out.decisions) == 4 and all(
        d.allocated is False for d in out.decisions
    )  # ALL KILLED
    assert out.candidate_count == 0  # the allocator allocated NOBODY
    assert out.loop_result.submitted_count == 0  # the loop submitted NOTHING (ADR §0)
    broker = ctx.loop_deps.broker
    assert isinstance(broker, SpyBroker) and broker.submits == []


def test_driver_never_writes_the_operator_go_marker(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    drive_once(ctx)
    assert not (
        tmp_path / "SUBMIT_GO"
    ).exists()  # RECORD_ONLY: the driver never authorizes a submit


def test_driver_fails_closed_on_a_polygon_error(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, fetch=_fetch_raises)  # the PIT fetch raises -> abort, never partial
    out = drive_once(ctx)
    assert out.assembly_error == "PolygonProvenanceError"
    assert out.candidate_count == 0 and out.loop_result.submitted_count == 0
    assert out.decisions == ()  # no gating happened — but the loop still ran (see below)


def test_safety_machinery_runs_even_when_assembly_fails(tmp_path: Path) -> None:
    # a Polygon error ABORTS assembly, but the loop's recon/guards/§8 escalation STILL runs: an
    # abandonment trigger this pass must still hard_stop (escalation is never skipped on a failure).
    ctx = _ctx(
        tmp_path,
        fetch=_fetch_raises,
        aband=AbandonmentState(cumulative_loss_usd=31.0, equity_usd=50.0),
    )
    out = drive_once(ctx)
    assert out.assembly_error == "PolygonProvenanceError"
    assert out.loop_result.disaster is True  # §8 abandonment still escalated
    assert ctx.loop_deps.kill_switch.read() is KillSwitchState.HARD_STOPPED
    assert out.loop_result.submitted_count == 0
