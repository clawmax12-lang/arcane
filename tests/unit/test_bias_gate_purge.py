"""C4 / tripwire A3 — purge is RE-DERIVED from the strategy's factors, never author-declared.

ADR §8 / design §6: a fitted (or any leak-sensitive) consumer must set
``purge >= max_total_window + label_horizon``, re-derived from the strategy's OWN bound factors (the
registry-2 lesson — never trust an author-declared constant). ``required_purge_bars`` computes the
floor; ``assert_purge_adequate`` fails closed if a ``WalkForwardConfig`` under-purges.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from trading.backtest.engine import strategy_warmup
from trading.backtest.resolve import ResolvedStrategy, resolve_spec
from trading.backtest.strategies import default_strategies
from trading.backtest.walk_forward import WalkForwardConfig
from trading.bias_gate.errors import PurgeUnderspecifiedError
from trading.bias_gate.evidence import assert_purge_adequate, required_purge_bars
from trading.factors.registry import default_registry
from trading.factors.trial_ledger import TrialLedger


def _resolved(name: str = "ts_meanrev_short") -> ResolvedStrategy:
    ledger = TrialLedger(Path(tempfile.mkdtemp()) / "trials.db")
    registry = default_registry(ledger)
    spec = next(s for s in default_strategies() if s.name == name)
    return resolve_spec(spec, registry)


def test_required_purge_is_warmup_plus_label_horizon() -> None:
    rs = _resolved("ts_meanrev_short")  # warmup 27
    assert required_purge_bars(rs, label_horizon=1) == strategy_warmup(rs) + 1
    assert required_purge_bars(rs, label_horizon=5) == strategy_warmup(rs) + 5


def test_required_purge_is_re_derived_per_strategy() -> None:
    # deepest strategy demands a deeper purge than the shallow one (re-derived, not a constant).
    deep = required_purge_bars(_resolved("ts_momentum_blend"), label_horizon=1)  # 169 + 1
    shallow = required_purge_bars(_resolved("ts_meanrev_short"), label_horizon=1)  # 27 + 1
    assert deep == 170
    assert shallow == 28
    assert deep > shallow


def test_label_horizon_below_one_fails_closed() -> None:
    rs = _resolved()
    with pytest.raises(PurgeUnderspecifiedError):
        required_purge_bars(rs, label_horizon=0)
    with pytest.raises(PurgeUnderspecifiedError):
        required_purge_bars(rs, label_horizon=-3)


def test_assert_purge_adequate_rejects_an_under_purged_config() -> None:
    rs = _resolved("ts_meanrev_short")  # needs purge >= 28
    under = WalkForwardConfig(purge_bars=1)  # the Inc-4 default — far too shallow for a gate
    with pytest.raises(PurgeUnderspecifiedError):
        assert_purge_adequate(under, rs, label_horizon=1)


def test_assert_purge_adequate_accepts_sufficient_or_larger_purge() -> None:
    rs = _resolved("ts_meanrev_short")  # needs 28
    need = required_purge_bars(rs, label_horizon=1)
    assert assert_purge_adequate(WalkForwardConfig(purge_bars=need), rs, label_horizon=1) == need
    # a deliberately LARGER purge (more conservative) is allowed.
    assert (
        assert_purge_adequate(WalkForwardConfig(purge_bars=need + 50), rs, label_horizon=1) == need
    )
