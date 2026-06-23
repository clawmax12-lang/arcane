"""Tripwire A1 — the M18 trial identity: fold cost NUMERICS + WF geometry into the recorded trial.

The sealed Inc-4 engine records ``record_strategy_trial(ledger, spec)`` →
``spec.canonical_params()``, which carries only the ``cost_model_id`` LABEL and ZERO walk-forward
geometry. So two evals with distinct cost numbers under the same label, or distinct fold geometry,
collapse to ONE ``combo_hash`` → ``n_trials`` under-counts → DSR under-deflates (M18).

The Inc-5 evaluation layer composes a RICHER identity here (no Inc-4 edit). ``eval_trial_params`` is
a SUPERSET of ``spec.canonical_params()`` with the cost numerics and the fold geometry nested under
``cost`` / ``wf``, so a swept cost/fold is a DISTINCT ledger row. Because the keys differ from the
engine's spec-only row, the two coexist (a ``+1`` over-count per spec) — over-counting is SAFE for
M18 (it deflates the Sharpe MORE; never less). Every value is ``str``/``int`` (floats via lossless
``float.hex()``), so the ledger's canonical JSON is byte-stable and re-runs are idempotent.
"""

from __future__ import annotations

from typing import Any

from trading.backtest.cost_model import CostModel
from trading.backtest.spec import StrategySpec
from trading.backtest.walk_forward import WalkForwardConfig


def cost_canonical(cost: CostModel) -> dict[str, str]:
    """Lossless JSON-native identity of the cost model's full field set (floats via ``float.hex``).

    Covers EVERY ``CostModel`` field; a reflective-completeness test fails if a future swept knob
    is added to the model but not folded in here.
    """
    return {
        "cost_model_id": cost.cost_model_id,
        "commission_bps": cost.commission_bps.hex(),
        "half_spread_bps": cost.half_spread_bps.hex(),
        "slippage_bps": cost.slippage_bps.hex(),
        "cost_scale": cost.cost_scale.hex(),
    }


def wf_canonical(folds: WalkForwardConfig) -> dict[str, int | str]:
    """Lossless, JSON-native identity of the walk-forward geometry (covers EVERY field)."""
    return {
        "train_months": folds.train_months,
        "test_months": folds.test_months,
        "step_months": folds.step_months,
        "purge_bars": folds.purge_bars,
        "embargo_frac": folds.embargo_frac.hex(),
    }


def eval_trial_params(
    spec: StrategySpec, cost: CostModel, folds: WalkForwardConfig
) -> dict[str, Any]:
    """The Inc-5 trial identity: ``spec.canonical_params()`` + nested cost numerics + fold geometry.

    Record it via ``TrialLedger.record(kind="strategy", ref_id=spec.name, params=...)`` BEFORE any
    ``n_trials`` deflation read. An un-encodable value would RAISE inside ``TrialLedger._canonical``
    (no ``default=str``) — fail closed, never a silent collision.
    """
    return {
        **spec.canonical_params(),
        "cost": cost_canonical(cost),
        "wf": wf_canonical(folds),
    }
