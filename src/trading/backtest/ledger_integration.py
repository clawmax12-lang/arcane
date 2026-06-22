"""Strategy-trial recording — REUSE the Inc-3 ``TrialLedger`` (do NOT fork it).

Every evaluated strategy is recorded as a trial BEFORE any statistic is computed, so there is no
uncounted evaluation path (the M18 under-count vector). A strategy trial is
``record(kind="strategy", ref_id=spec.name, params=spec.canonical_params())`` in the SAME ``trials``
table as the factor trials, so ``n_trials = COUNT(*)`` spans BOTH layers (ADR §5 cumulative count;
building the 13 factors + 4 strategies makes ``n_trials = 17``).

The recorded ``params`` is the SAME JSON-native dict that ``spec_hash`` hashes, so the ledger's
canonical-JSON of it is byte-identical to the ``spec_hash`` basis. Distinct specs therefore map to
distinct ledger rows and ``n_trials`` can never under-count two real strategies as one.
``INSERT OR IGNORE`` makes a re-run of the same spec a no-op (monotonic; never double-counts).
"""

from __future__ import annotations

from trading.backtest.spec import StrategySpec
from trading.factors.trial_ledger import TrialLedger, TrialRecord

STRATEGY_KIND = "strategy"


def record_strategy_trial(ledger: TrialLedger, spec: StrategySpec) -> TrialRecord:
    """Record one strategy/param combo as a trial (idempotent); returns the stored record."""
    return ledger.record(STRATEGY_KIND, spec.name, spec.canonical_params())
