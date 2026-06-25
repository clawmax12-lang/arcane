"""C14 — the end-to-end null: with T2 CAPABLE, the 4 edgeless toys STILL all KILL (ADR §0).

This is the load-bearing proof that wiring Polygon did NOT manufacture an allocation. The toys
are run
with a VALID, hash-bound POLYGON_PIT membership artifact so T2 PASSES — yet the independent
statistical
wall (DSR/PSR/PBO/SPA/WF) still kills every one. Zero allocations ⇒ zero grants ⇒ zero
orders. A non-zero result here is a RED flag to investigate, never a milestone.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

import _gate_fixtures as fx

from trading.backtest.engine import SymbolPanel
from trading.bias_gate.gate import FamilyMember, evaluate_family
from trading.bias_gate.high_water_mark import NTrialsHighWaterMark
from trading.data.membership_cache import MembershipCache
from trading.data.universe import UniverseSnapshot
from trading.executor.grant import AllocationDenied, AllocationGrant

_PURGE = 200  # matches the composer fixture (>= deepest toy warmup + label_horizon)
_TOYS = ("ts_momentum_blend", "ts_meanrev_short", "trend_location", "lowvol_liquid_tilt")
_STAT_COMPONENTS = {
    "DSR_deflated_sharpe",
    "PSR_prob_sharpe",
    "WF_OOS",
    "enough_samples",
    "cost_stress",
    "PBO_overfit",
    "SPA_superiority",
}


def _pit_panel() -> SymbolPanel:
    # survivorship_unverified=False so the self-attested advisory wall in T2 does not block the
    # decomposition proof — the LOAD-BEARING T2 check is the hash-bound artifact below.
    return SymbolPanel(
        bars={f"SYM{i}": fx.bars(1300, seed=20 + i) for i in range(2)},
        survivorship_unverified=False,
    )


def _universe_and_cache(
    tmp_path: Path, panel: SymbolPanel
) -> tuple[UniverseSnapshot, MembershipCache]:
    # A REAL base-produced POLYGON_PIT snapshot (token-gated producer; carries the base-minted PIT
    # proof) + a content-addressed cache the GATE itself reads (D1-residual: no caller-supplied
    # binding/artifact). The gate derives the binding from the panel and loads the artifact by hash.
    syms = tuple(sorted(panel.bars.keys()))
    snapshot = fx.pit_snapshot(syms, fx.AS_OF.ts)
    cache = fx.seeded_cache(tmp_path, syms, fx.AS_OF.ts)  # key == snapshot.meta.universe_hash
    return snapshot, cache


def _toy_family(
    tmp_path: Path,
) -> tuple[list[FamilyMember], object, NTrialsHighWaterMark, MembershipCache]:
    led = fx.ledger(tmp_path)
    reg = fx.registry(led)
    panel = _pit_panel()
    folds = fx.WalkForwardConfig(purge_bars=_PURGE)
    snapshot, cache = _universe_and_cache(tmp_path, panel)
    members: list[FamilyMember] = []
    for name in _TOYS:
        strat = fx.resolved(name, reg)
        result = fx.run_result(strat, panel, led, folds=folds)
        members.append(
            FamilyMember(
                strategy=strat,
                panel=panel,
                cost=fx.CostModel(),
                folds=folds,
                as_of=fx.AS_OF,
                result=result,
                universe=snapshot,
            )
        )
    return members, led, NTrialsHighWaterMark(tmp_path / "hwm.json"), cache


def test_t2_passes_for_the_toys_but_the_stats_still_kill_them(tmp_path: Path) -> None:
    members, led, hwm, cache = _toy_family(tmp_path)
    decisions = evaluate_family(
        members, ledger=led, hwm=hwm, label_horizon=1, membership_cache=cache
    )
    assert len(decisions) == 4
    for d in decisions:
        assert d.allocated is False  # the gate's JOB on a no-edge toy: say NO
        by_name = {c.name: c.passed for c in d.components}
        # T2 is now CAPABLE of passing (hash-bound PIT artifact) — it is NOT the blocker here...
        assert by_name.get("T2_survivorship") is True
        # ...yet at least one INDEPENDENT statistical judge kills the toy (the real wall).
        failed_stats = {n for n, ok in by_name.items() if not ok} & _STAT_COMPONENTS
        assert failed_stats, f"a no-edge toy was not killed by the stats: {d.reasons}"


def test_zero_grants_and_zero_orders(tmp_path: Path) -> None:
    members, led, hwm, cache = _toy_family(tmp_path)
    decisions = evaluate_family(
        members, ledger=led, hwm=hwm, label_horizon=1, membership_cache=cache
    )
    grants = []
    for d in decisions:
        with contextlib.suppress(AllocationDenied):
            grants.append(AllocationGrant.from_decision(d, universe_artifact_hash="arcane-univ-x"))
    assert grants == []  # ZERO grants mintable ⇒ structurally ZERO orders (ADR §0)
