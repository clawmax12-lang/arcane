"""Increment 7 LIVE smoke — drive the WHOLE pipeline against the REAL Polygon PIT source (no order).

``@pytest.mark.live`` is EXCLUDED from every inc gate. This proves the first real driver wires the
REAL Polygon PIT universe (a real reference fetch for AAPL/MSFT) through the backtest → bias gate →
allocator → ``run_loop_pass`` — and that the 4 edgeless toys are STILL all KILLED → zero candidates
→ ZERO orders (ADR §0). It is RECORD_ONLY by construction: no ``SUBMIT_GO`` exists, so even a
survivor (there are none) would not submit. Fakes mirror real vendor behavior
(insight-fakes-must-mirror-reality); the broker is a spy whose ``submit`` fails the test if called.
"""

from __future__ import annotations

from pathlib import Path

import _gate_fixtures as fx
import pytest
import test_driver as td

from trading.backtest.engine import SymbolPanel
from trading.bias_gate.high_water_mark import NTrialsHighWaterMark
from trading.data.membership_cache import MembershipCache
from trading.data.polygon_universe import HttpxPolygonReference, PolygonPITUniverse
from trading.driver.run_once import DriverContext, drive_once
from trading.executor.invariants import AccountSnapshot
from trading.executor.kill_switch import KillSwitch
from trading.executor.loop import LoopDeps, LoopInputs
from trading.guards.abandonment import AbandonmentState
from trading.guards.panel import GuardPanel
from trading.regime.model import DeterministicRegimeModel
from trading.settings import load_settings

_REAL_SYMS = ("AAPL", "MSFT")


@pytest.mark.live
def test_driver_real_polygon_pit_four_toys_zero_submits(tmp_path: Path) -> None:
    token = load_settings().get("POLYGON_API_KEY")
    if not token:
        pytest.skip("POLYGON_API_KEY not set")

    led = fx.ledger(tmp_path)
    reg = fx.registry(led)
    panel = SymbolPanel(
        bars={s: fx.bars(1300, seed=20 + i) for i, s in enumerate(_REAL_SYMS)},
        survivorship_unverified=False,
    )
    cache = MembershipCache(tmp_path / "mem")
    universe = PolygonPITUniverse(
        _REAL_SYMS, fetch=HttpxPolygonReference(token, min_interval_s=13.0), cache=cache
    )
    broker = td.SpyBroker()
    ctx = DriverContext(
        strategies=[fx.resolved(name, reg) for name in td._TOYS],
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
        loop_inputs=LoopInputs(
            local_positions={},
            broker_positions={},
            drift_since_epoch=None,
            now_epoch=1000.0,
            guard_state=td._guard_state(),
            abandonment_state=AbandonmentState(cumulative_loss_usd=0.0, equity_usd=50.0),
            snapshot=AccountSnapshot(50.0, 0.0, 0.0, 1000.0, 1000.0),
            candidates=(),
        ),
        loop_deps=LoopDeps(
            kill_switch=KillSwitch(tmp_path / "ks.json"),
            notifier=td.FakePager(),
            broker=broker,
            store=td.InMemoryIdempotencyStore(),
            guard_panel=GuardPanel(),
            cfg=td._cfg(),
            go_marker_path=tmp_path / "SUBMIT_GO",
        ),
    )

    out = drive_once(ctx)
    assert out.assembly_error is None
    assert out.snapshot_hash is not None  # a REAL Polygon PIT snapshot was built + sealed
    assert len(out.decisions) == 4 and all(d.allocated is False for d in out.decisions)
    assert out.candidate_count == 0 and out.loop_result.submitted_count == 0  # ZERO orders (ADR §0)
    assert broker.submits == []
    assert not (tmp_path / "SUBMIT_GO").exists()  # record-only: never authorized a submit
