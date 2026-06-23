"""C5 — the evidence ASSEMBLER + the T1 consistency guard (MR-1, the linchpin fail-open defense).

The gate recomputes the OOS net return series from Inc-4's PUBLIC primitives (no Inc-4 edit, no
``oos_net_returns`` accessor) and a STRICT consistency guard asserts the recompute matches the
sealed ``BacktestResult`` per-fold (1e-9) AND on the concatenated Sharpe AND on ``spec_hash`` +
``cost_model_id``. Any divergence ⇒ ``EvidenceConsistencyError`` (fail closed — never judge a stale
or wrong series). Both-NaN folds AGREE (a degenerate fold is consistently degenerate); a
NaN-vs-finite fold is a real divergence and RAISES.
"""

from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path

import _gate_fixtures as fx
import numpy as np
import pytest

from trading.bias_gate.errors import EvidenceConsistencyError
from trading.bias_gate.evidence import GateEvidence, _agree, build_evidence


def _evidence(tmp_path: Path, name: str = "ts_meanrev_short") -> tuple[GateEvidence, object]:
    led = fx.ledger(tmp_path)
    reg = fx.registry(led)
    strat = fx.resolved(name, reg)
    panel = fx.panel(1300)
    result = fx.run_result(strat, panel, led)
    ev = build_evidence(
        strat, panel, cost=fx.CostModel(), folds=fx.WalkForwardConfig(), result=result, n_trials=99
    )
    return ev, result


# --- the pure agreement helper (probe the NaN tails directly) ---


def test_agree_both_nan_is_consistent() -> None:
    assert _agree(float("nan"), float("nan")) is True  # both folds degenerate => they AGREE


def test_agree_nan_vs_finite_is_a_divergence() -> None:
    assert _agree(float("nan"), 0.8) is False
    assert _agree(0.8, float("nan")) is False


def test_agree_finite_equal_within_tol() -> None:
    assert _agree(1.234567890, 1.234567890 + 5e-10) is True
    assert _agree(1.0, 1.0 + 1e-6) is False


def test_agree_inf_is_a_divergence() -> None:
    assert _agree(float("inf"), float("inf")) is False
    assert _agree(float("inf"), 1.0) is False


# --- the full assembler against a REAL engine run ---


def test_build_evidence_recompute_matches_the_sealed_result(tmp_path: Path) -> None:
    ev, result = _evidence(tmp_path)
    assert isinstance(ev, GateEvidence)
    assert ev.spec_hash == result.spec_hash
    assert ev.cost_model_id == result.cost_model_id
    assert ev.n_trials == 99
    # per-fold structure mirrors the sealed result
    assert len(ev.per_fold_oos_returns) == len(result.per_fold_oos_sharpe)
    assert len(ev.oos_returns) == sum(len(f) for f in ev.per_fold_oos_returns)
    assert len(ev.oos_returns) > 0
    # carried-through WF inputs
    assert ev.per_fold_oos_sharpe == result.per_fold_oos_sharpe
    assert ev.fraction_folds_positive == result.fraction_folds_positive


def test_tampered_per_fold_sharpe_raises(tmp_path: Path) -> None:
    led = fx.ledger(tmp_path)
    reg = fx.registry(led)
    strat = fx.resolved("ts_meanrev_short", reg)
    panel = fx.panel(1300)
    result = fx.run_result(strat, panel, led)
    n = len(result.per_fold_oos_sharpe)
    tampered = replace(result, per_fold_oos_sharpe=tuple(99.0 for _ in range(n)))
    with pytest.raises(EvidenceConsistencyError):
        build_evidence(
            strat,
            panel,
            cost=fx.CostModel(),
            folds=fx.WalkForwardConfig(),
            result=tampered,
            n_trials=1,
        )


def test_spec_hash_mismatch_raises(tmp_path: Path) -> None:
    led = fx.ledger(tmp_path)
    reg = fx.registry(led)
    strat = fx.resolved("ts_meanrev_short", reg)
    panel = fx.panel(1300)
    result = fx.run_result(strat, panel, led)
    with pytest.raises(EvidenceConsistencyError):
        build_evidence(
            strat,
            panel,
            cost=fx.CostModel(),
            folds=fx.WalkForwardConfig(),
            result=replace(result, spec_hash="arcane-strategy-WRONG"),
            n_trials=1,
        )


def test_cost_model_id_mismatch_raises(tmp_path: Path) -> None:
    led = fx.ledger(tmp_path)
    reg = fx.registry(led)
    strat = fx.resolved("ts_meanrev_short", reg)
    panel = fx.panel(1300)
    result = fx.run_result(strat, panel, led)
    with pytest.raises(EvidenceConsistencyError):
        build_evidence(
            strat,
            panel,
            cost=fx.CostModel(),
            folds=fx.WalkForwardConfig(),
            result=replace(result, cost_model_id="WRONG_v9"),
            n_trials=1,
        )


def test_nan_vs_finite_fold_divergence_raises(tmp_path: Path) -> None:
    # force a single result fold Sharpe to NaN while the recompute stays finite -> real divergence.
    led = fx.ledger(tmp_path)
    reg = fx.registry(led)
    strat = fx.resolved("ts_meanrev_short", reg)
    panel = fx.panel(1300)
    result = fx.run_result(strat, panel, led)
    pf = list(result.per_fold_oos_sharpe)
    assert any(math.isfinite(s) for s in pf)
    first_finite = next(i for i, s in enumerate(pf) if math.isfinite(s))
    pf[first_finite] = float("nan")
    with pytest.raises(EvidenceConsistencyError):
        build_evidence(
            strat,
            panel,
            cost=fx.CostModel(),
            folds=fx.WalkForwardConfig(),
            result=replace(result, per_fold_oos_sharpe=tuple(pf)),
            n_trials=1,
        )


def test_oos_returns_are_plain_finite_floats_or_nan(tmp_path: Path) -> None:
    ev, _ = _evidence(tmp_path)
    for arr in ev.per_fold_oos_returns:
        for x in arr:
            assert isinstance(x, float)
            assert math.isfinite(x) or math.isnan(x)  # never inf
    assert all(not math.isinf(x) for x in ev.oos_returns)
    # numpy round-trips cleanly
    assert np.asarray(ev.oos_returns, dtype="float64").ndim == 1
