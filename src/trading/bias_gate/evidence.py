"""Evidence helpers — tripwire A3 (re-derived purge floor) + (C5) the OOS-series assembler.

A3: a leak-sensitive consumer must purge ``>= max_total_window + label_horizon``, re-derived from
the strategy's OWN bound factors (never an author-declared constant — the registry-2 lesson).
``required_purge_bars`` reuses the public Inc-4 ``strategy_warmup`` (deepest factor pipeline) and
``assert_purge_adequate`` fails closed if a ``WalkForwardConfig`` under-purges. The impure OOS
assembler + the T1 consistency guard are added in cluster C5 (this module is extended, not forked).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd

from trading.backtest.cost_model import CostModel
from trading.backtest.engine import (
    SymbolPanel,
    _executed,
    compose_positions,
    factor_matrix,
    strategy_warmup,
)
from trading.backtest.resolve import ResolvedStrategy
from trading.backtest.statistics import BacktestResult, annualized_sharpe
from trading.backtest.walk_forward import WalkForwardConfig, walk_forward_folds
from trading.bias_gate.errors import EvidenceConsistencyError, PurgeUnderspecifiedError

#: Per-fold / concatenated Sharpe agreement tolerance for the T1 consistency guard.
_CONSISTENCY_ATOL: Final[float] = 1e-9


def required_purge_bars(strategy: ResolvedStrategy, *, label_horizon: int = 1) -> int:
    """The purge floor = deepest factor pipeline (``strategy_warmup``) + the label/holding horizon.

    ``label_horizon`` is an EXPLICIT gate parameter (close-to-close ⇒ 1), never read from the spec.
    A horizon below 1 is degenerate and fails closed.
    """
    if label_horizon < 1:
        raise PurgeUnderspecifiedError(
            f"label_horizon must be >= 1 (a holding horizon), got {label_horizon}"
        )
    return strategy_warmup(strategy) + label_horizon


def assert_purge_adequate(
    folds: WalkForwardConfig, strategy: ResolvedStrategy, *, label_horizon: int = 1
) -> int:
    """Return the required purge if ``folds.purge_bars`` meets it; else raise (fail closed).

    ``<`` (not ``!=``) so a deliberately LARGER purge (more conservative) is allowed; only an
    UNDER-purge fails closed.
    """
    need = required_purge_bars(strategy, label_horizon=label_horizon)
    if folds.purge_bars < need:
        raise PurgeUnderspecifiedError(
            f"WalkForwardConfig.purge_bars={folds.purge_bars} < required {need} = "
            f"warmup({strategy_warmup(strategy)}) + label_horizon({label_horizon}); a "
            "leak-sensitive consumer must purge >= the deepest factor pipeline + holding horizon"
        )
    return need


# --- C5: the impure evidence assembler + the T1 consistency guard ---


@dataclass(frozen=True, slots=True)
class GateEvidence:
    """One candidate's recomputed OOS evidence + the carried-through Inc-4 WF/provenance fields.

    ``oos_returns`` / ``per_fold_oos_returns`` are the gate's OWN recompute (per-obs net), fed to
    PSR/DSR/PBO/SPA. The Sharpe / fraction / survivorship / sample fields are copied verbatim from
    the sealed ``BacktestResult`` (the T1 guard has already proven the recompute agrees with them).
    """

    spec_hash: str
    cost_model_id: str
    n_trials: int
    oos_returns: tuple[float, ...]
    per_fold_oos_returns: tuple[tuple[float, ...], ...]
    per_fold_oos_sharpe: tuple[float, ...]
    oos_annualized_sharpe: float
    fraction_folds_positive: float
    enough_samples: bool
    survivorship_biased: bool
    survivorship_unverified: bool
    train_months: int
    test_months: int
    step_months: int


def _agree(a: float, b: float) -> bool:
    """True iff two Sharpes are consistent: BOTH NaN (degenerate folds agree) or finite & close.

    A NaN-vs-finite pair (or an ``inf``) is a REAL divergence and returns False (fail closed). The
    both-NaN branch is deliberate: a legitimately ruined/degenerate fold yields NaN in BOTH the
    sealed result and the recompute — they AGREE — so the guard must not raise on it (the ruin KILL
    is the judges' job, not a consistency error).
    """
    if math.isnan(a) and math.isnan(b):
        return True
    if not (math.isfinite(a) and math.isfinite(b)):
        return False
    return abs(a - b) <= _CONSISTENCY_ATOL


def _assert_consistent(
    gate_per_fold: tuple[float, ...],
    result_per_fold: tuple[float, ...],
    gate_concat: float,
    result_concat: float,
    gate_spec_hash: str,
    result_spec_hash: str,
    gate_cost_id: str,
    result_cost_id: str,
) -> None:
    """Raise ``EvidenceConsistencyError`` unless the recompute matches the sealed result exactly."""
    if gate_spec_hash != result_spec_hash:
        raise EvidenceConsistencyError(
            f"spec_hash mismatch: recompute {gate_spec_hash!r} vs result {result_spec_hash!r}"
        )
    if gate_cost_id != result_cost_id:
        raise EvidenceConsistencyError(
            f"cost_model_id mismatch: recompute {gate_cost_id!r} vs result {result_cost_id!r}"
        )
    if len(gate_per_fold) != len(result_per_fold):
        raise EvidenceConsistencyError(
            f"fold count mismatch: recompute {len(gate_per_fold)} vs result {len(result_per_fold)}"
        )
    for i, (g, r) in enumerate(zip(gate_per_fold, result_per_fold, strict=True)):
        if not _agree(g, r):
            raise EvidenceConsistencyError(
                f"per-fold OOS Sharpe divergence at fold {i}: recompute {g!r} vs result {r!r}"
            )
    if not _agree(gate_concat, result_concat):
        raise EvidenceConsistencyError(
            f"concat OOS Sharpe divergence: recompute {gate_concat!r} vs result {result_concat!r}"
        )


def _panel_sessions(panel: SymbolPanel) -> pd.DatetimeIndex:
    if not panel.bars:
        raise EvidenceConsistencyError("panel has no symbols")
    ref = next(iter(panel.bars.values())).index
    if not isinstance(ref, pd.DatetimeIndex) or ref.tz is None:
        raise EvidenceConsistencyError("panel bars must have a tz-aware DatetimeIndex")
    if not ref.is_monotonic_increasing or not ref.is_unique:
        raise EvidenceConsistencyError(
            "panel session index must be monotonic-increasing and unique"
        )
    return ref


def build_evidence(
    strategy: ResolvedStrategy,
    panel: SymbolPanel,
    *,
    cost: CostModel,
    folds: WalkForwardConfig,
    result: BacktestResult,
    n_trials: int,
) -> GateEvidence:
    """Recompute the OOS net series via Inc-4 PUBLIC primitives; fail closed unless it matches.

    Mirrors ``BacktestEngine.run``'s EXACT net computation (no Inc-4 edit): per symbol
    ``executed * close.pct_change(fill_method=None) - cost.per_bar_cost(executed)`` then
    ``mean(axis=1)``; the OOS index is the appended union of the fold test windows. The T1 guard
    asserts the recompute equals the sealed ``BacktestResult`` (per-fold + concat Sharpe + hashes).
    """
    sessions = _panel_sessions(panel)
    fold_list = walk_forward_folds(sessions, folds)
    if not fold_list:
        raise EvidenceConsistencyError("panel too short to form a walk-forward fold")

    net_by_symbol: dict[str, pd.Series] = {}
    for sym, bars in panel.bars.items():
        target_w = compose_positions(strategy, factor_matrix(strategy, bars))
        executed = _executed(target_w)
        close = bars["close"].astype("float64")
        gross = executed * close.pct_change(fill_method=None)
        net_by_symbol[sym] = gross - cost.per_bar_cost(executed)
    net = pd.DataFrame(net_by_symbol).mean(axis=1)

    oos_index = fold_list[0].test
    for fold in fold_list[1:]:
        oos_index = oos_index.append(fold.test)

    gate_per_fold = tuple(annualized_sharpe(net.loc[f.test]) for f in fold_list)
    gate_concat = annualized_sharpe(net.loc[oos_index])
    _assert_consistent(
        gate_per_fold,
        result.per_fold_oos_sharpe,
        gate_concat,
        result.oos_annualized_sharpe,
        strategy.spec_hash,
        result.spec_hash,
        cost.cost_model_id,
        result.cost_model_id,
    )

    per_fold_returns = tuple(
        tuple(float(x) for x in net.loc[f.test].to_numpy(dtype="float64", na_value=np.nan))
        for f in fold_list
    )
    oos_returns = tuple(
        float(x) for x in net.loc[oos_index].to_numpy(dtype="float64", na_value=np.nan)
    )
    return GateEvidence(
        spec_hash=result.spec_hash,
        cost_model_id=result.cost_model_id,
        n_trials=n_trials,
        oos_returns=oos_returns,
        per_fold_oos_returns=per_fold_returns,
        per_fold_oos_sharpe=result.per_fold_oos_sharpe,
        oos_annualized_sharpe=result.oos_annualized_sharpe,
        fraction_folds_positive=result.fraction_folds_positive,
        enough_samples=result.enough_samples,
        survivorship_biased=result.survivorship_biased,
        survivorship_unverified=result.survivorship_unverified,
        train_months=result.train_months,
        test_months=result.test_months,
        step_months=result.step_months,
    )
