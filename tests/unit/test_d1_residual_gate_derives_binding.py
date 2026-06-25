"""C1 / D1-residual — the gate DERIVES the T2 binding + LOADS the artifact (no caller-supplied obj).

Inc-6 left the LAST caller-supplied objects on the trust path: ``FamilyMember.binding`` and
``FamilyMember.artifact``. Inc-7 deletes both; the gate now carries only a proof-bearing
``UniverseSnapshot`` and DERIVES the ``ProvenanceBinding`` (via ``provenance_binding_from`` — which
requires the base-minted ``PITMembershipProof``) and LOADS the artifact from the content-addressed
``MembershipCache`` keyed by ``snapshot.meta.universe_hash``. A hand-built (proof-less) POLYGON_PIT
snapshot is therefore UNBINDABLE end-to-end; a cache miss fails T2 closed; a degenerate panel is a
per-member KILL, never a ``StopIteration`` that aborts the whole family.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from pathlib import Path

import _gate_fixtures as fx

from trading.backtest.engine import SymbolPanel
from trading.backtest.statistics import BacktestResult
from trading.bias_gate.gate import FamilyMember, _t2_component, evaluate_family
from trading.bias_gate.high_water_mark import NTrialsHighWaterMark
from trading.executor.grant import AllocationDenied, AllocationGrant

_AS_OF = datetime(2024, 1, 1, tzinfo=UTC)


def _result(*, biased: bool = False, unverified: bool = False) -> BacktestResult:
    return BacktestResult(
        spec_hash="arcane-strategy-x",
        cost_model_id="conservative_v1",
        n_bars=300,
        total_return=0.1,
        annualized_return=0.1,
        annualized_sharpe=1.0,
        max_drawdown=-0.1,
        average_turnover=0.05,
        oos_total_return=0.05,
        oos_annualized_sharpe=0.8,
        oos_max_drawdown=-0.08,
        per_fold_oos_sharpe=(0.8, 0.9),
        fraction_folds_positive=1.0,
        n_trials_at_eval=17,
        survivorship_biased=biased,
        survivorship_unverified=unverified,
        enough_samples=True,
        train_months=12,
        test_months=3,
        step_months=3,
        anchored=True,
        equity_curve=(1.0, 1.1),
    )


def _panel() -> SymbolPanel:
    return SymbolPanel(
        bars={"SYM0": fx.bars(300, seed=1), "SYM1": fx.bars(300, seed=2)},
        survivorship_unverified=False,
    )


# --- the structural fact: FamilyMember no longer carries caller-supplied binding/artifact ---


def test_family_member_has_no_caller_supplied_binding_or_artifact_fields() -> None:
    fields = FamilyMember.__dataclass_fields__
    assert "binding" not in fields and "artifact" not in fields  # the forgeable inputs are GONE
    assert "universe" in fields  # the proof-bearing snapshot is the ONLY membership input now


# --- D1-residual must-FAIL teeth ---


def test_hand_built_pit_snapshot_unbindable_through_the_gate(tmp_path: Path) -> None:
    # A forged POLYGON_PIT snapshot (forged hash, NO base-minted proof) must be unbindable.
    # provenance_binding_from raises -> _t2_component fails CLOSED before any hash compare.
    panel = _panel()
    forged = fx.forged_pit_snapshot(("SYM0", "SYM1"), _AS_OF)
    cache = fx.seeded_cache(
        tmp_path, ("SYM0", "SYM1"), _AS_OF
    )  # even a real cache cannot rescue it
    comp = _t2_component(_result(), forged, panel, cache)
    assert comp.passed is False
    assert "bindable" in comp.reason or "proof" in comp.reason or "PIT" in comp.reason


def test_cache_miss_fails_T2_closed(tmp_path: Path) -> None:
    # A GENUINE proof-bearing snapshot but the artifact is not in the cache (miss / no cache) ->
    # no hash-matching artifact -> T2 fails CLOSED.
    panel = _panel()
    snap = fx.pit_snapshot(("SYM0", "SYM1"), _AS_OF)
    assert _t2_component(_result(), snap, panel, None).passed is False  # no cache at all
    empty_cache = fx.seeded_cache(tmp_path, ("OTHER",), _AS_OF)  # seeded with a DIFFERENT artifact
    assert _t2_component(_result(), snap, panel, empty_cache).passed is False  # miss on our hash


def test_empty_or_degenerate_panel_kills_member_not_crashes(tmp_path: Path) -> None:
    # red-team A2: an empty panel.bars must be a per-member KILL, never a StopIteration that aborts
    # the whole family evaluation.
    snap = fx.pit_snapshot(("SYM0", "SYM1"), _AS_OF)
    cache = fx.seeded_cache(tmp_path, ("SYM0", "SYM1"), _AS_OF)
    empty = SymbolPanel(bars={}, survivorship_unverified=False)
    comp = _t2_component(_result(), snap, empty, cache)  # must NOT raise
    assert comp.passed is False


# --- D1-residual must-PASS (capability, no allocation) ---


def test_real_proof_bearing_snapshot_with_seeded_cache_passes_t2(tmp_path: Path) -> None:
    # A REAL base-produced POLYGON_PIT snapshot + the matching artifact sealed in the cache ->
    # the gate derives the binding from the panel and loads the artifact by hash -> T2 PASSES.
    panel = _panel()
    snap = fx.pit_snapshot(("SYM0", "SYM1"), _AS_OF)
    cache = fx.seeded_cache(tmp_path, ("SYM0", "SYM1"), _AS_OF)
    comp = _t2_component(_result(), snap, panel, cache)
    assert comp.passed is True and "PIT-verified" in comp.reason


# --- end-to-end: even with a forged universe wired, no grant can be minted ---


def test_forged_universe_through_evaluate_family_mints_no_grant(tmp_path: Path) -> None:
    led = fx.ledger(tmp_path)
    reg = fx.registry(led)
    panel = _panel()
    folds = fx.WalkForwardConfig(purge_bars=200)
    forged = fx.forged_pit_snapshot(("SYM0", "SYM1"), _AS_OF)
    cache = fx.seeded_cache(tmp_path, ("SYM0", "SYM1"), _AS_OF)
    members = [
        FamilyMember(
            strategy=fx.resolved(name, reg),
            panel=panel,
            cost=fx.CostModel(),
            folds=folds,
            as_of=fx.AS_OF,
            result=fx.run_result(fx.resolved(name, reg), panel, led, folds=folds),
            universe=forged,  # the FORGE — unbindable, so T2 fails closed
        )
        for name in ("ts_momentum_blend", "ts_meanrev_short")
    ]
    hwm = NTrialsHighWaterMark(tmp_path / "hwm.json")
    decisions = evaluate_family(members, ledger=led, hwm=hwm, membership_cache=cache)
    grants = []
    for d in decisions:
        with contextlib.suppress(AllocationDenied):
            grants.append(AllocationGrant.from_decision(d, universe_artifact_hash="arcane-univ-x"))
    assert grants == []  # a forged universe never produces a grant (T2 fails closed)
    for d in decisions:
        by_name = {c.name: c.passed for c in d.components}
        assert by_name["T2_survivorship"] is False
