"""C4 — T2 survivorship is UNFORGEABLE: hash-bound PIT artifact + window coverage (Increment 6).

The Increment-5 ``_PIT_VERIFIER_WIRED`` bool-only path is DELETED. T2 passes ONLY when a real,
content-addressed POLYGON_PIT ``MembershipArtifact`` is bound to the result by hash AND covers every
backtested symbol across the whole window. The load-bearing teeth: a universe that DROPS a name
before
its delist (the survivorship sin), or whose name delists mid-window, must FAIL.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from trading.backtest.statistics import BacktestResult
from trading.bias_gate.gate import GateComponent
from trading.bias_gate.tests_t2 import t2_survivorship
from trading.data.membership_artifact import (
    MembershipArtifact,
    ProvenanceBinding,
    SymbolMembership,
    membership_artifact_hash,
)
from trading.data.universe import SourceTier

_WIN_START = datetime(2021, 1, 1, tzinfo=UTC)
_WIN_END = datetime(2023, 6, 1, tzinfo=UTC)
_AS_OF = datetime(2023, 6, 1, tzinfo=UTC)


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


def _artifact(members: tuple[SymbolMembership, ...], **kw: object) -> MembershipArtifact:
    base: dict[str, object] = dict(
        schema_version=1,
        source_tier=SourceTier.POLYGON_PIT,
        as_of=_AS_OF,
        vintage=_AS_OF,
        members=members,
    )
    base.update(kw)
    return MembershipArtifact(**base)  # type: ignore[arg-type]


def _binding(traded: tuple[str, ...], art_hash: str) -> ProvenanceBinding:
    return ProvenanceBinding(
        membership_artifact_hash=art_hash,
        traded_symbols=traded,
        window_start=_WIN_START,
        window_end=_WIN_END,
        as_of=_AS_OF,
    )


_CLEAN_MEMBERS = (
    SymbolMembership("AAPL", active=True, listed_utc=None, delisted_utc=None),
    SymbolMembership("MSFT", active=True, listed_utc=None, delisted_utc=None),
)


def test_returns_gate_component() -> None:
    comp = t2_survivorship(_result())
    assert isinstance(comp, GateComponent) and comp.name == "T2_survivorship"


def test_missing_binding_or_artifact_fails_closed() -> None:
    assert t2_survivorship(_result()).passed is False  # legacy single-arg → fail closed
    art = _artifact(_CLEAN_MEMBERS)
    b = _binding(("AAPL", "MSFT"), membership_artifact_hash(art))
    assert t2_survivorship(_result(), b, None).passed is False
    assert t2_survivorship(_result(), None, art).passed is False


def test_passes_with_bound_pit_artifact_covering_the_window() -> None:
    art = _artifact(_CLEAN_MEMBERS)
    b = _binding(("AAPL", "MSFT"), membership_artifact_hash(art))
    comp = t2_survivorship(_result(biased=False, unverified=False), b, art)
    assert comp.passed is True
    assert "PIT-verified" in comp.reason


def test_drops_a_traded_symbol_before_its_delist_fails_closed() -> None:
    # THE load-bearing teeth: the backtest TRADED SIVB, but the artifact OMITS it (survivorship
    # sin).
    art = _artifact(_CLEAN_MEMBERS)  # only AAPL/MSFT
    b = _binding(("AAPL", "MSFT", "SIVB"), membership_artifact_hash(art))
    comp = t2_survivorship(_result(), b, art)
    assert comp.passed is False
    assert "missing" in comp.reason and "SIVB" in comp.reason


def test_symbol_delisted_mid_window_fails_closed() -> None:
    members = (
        SymbolMembership("AAPL", active=True, listed_utc=None, delisted_utc=None),
        SymbolMembership(
            "SIVB", active=True, listed_utc=None, delisted_utc=datetime(2023, 3, 28, tzinfo=UTC)
        ),
    )
    art = _artifact(members)
    b = _binding(("AAPL", "SIVB"), membership_artifact_hash(art))  # window_end=2023-06-01 > delist
    comp = t2_survivorship(_result(), b, art)
    assert comp.passed is False
    assert "not PIT-active across the whole window" in comp.reason and "SIVB" in comp.reason


def test_symbol_listed_after_window_start_fails_closed() -> None:
    members = (
        SymbolMembership(
            "NEW", active=True, listed_utc=datetime(2022, 1, 1, tzinfo=UTC), delisted_utc=None
        ),
    )
    art = _artifact(members)
    b = _binding(("NEW",), membership_artifact_hash(art))  # window_start=2021-01-01 < list
    assert t2_survivorship(_result(), b, art).passed is False


def test_hash_mismatch_fails_closed() -> None:
    art = _artifact(_CLEAN_MEMBERS)
    b = _binding(("AAPL", "MSFT"), "arcane-univ-WRONGHASH")
    comp = t2_survivorship(_result(), b, art)
    assert comp.passed is False and "hash" in comp.reason


def test_wrong_source_tier_fails_closed() -> None:
    art = _artifact(_CLEAN_MEMBERS, source_tier=SourceTier.OPERATOR_FILE)
    b = _binding(("AAPL", "MSFT"), membership_artifact_hash(art))  # hash matches, tier wrong
    comp = t2_survivorship(_result(), b, art)
    assert comp.passed is False and "POLYGON_PIT" in comp.reason


def test_future_vintage_fails_closed() -> None:
    art = _artifact(_CLEAN_MEMBERS, vintage=datetime(2023, 7, 1, tzinfo=UTC))  # after as_of
    b = _binding(("AAPL", "MSFT"), membership_artifact_hash(art))
    assert t2_survivorship(_result(), b, art).passed is False


def test_artifact_snapshot_before_window_end_fails_closed() -> None:
    # An artifact reconstructed BEFORE the window end cannot see in-window delistings → reject.
    early = datetime(2021, 6, 1, tzinfo=UTC)
    art = _artifact(_CLEAN_MEMBERS, as_of=early, vintage=early)
    b = _binding(("AAPL", "MSFT"), membership_artifact_hash(art))
    assert t2_survivorship(_result(), b, art).passed is False


@pytest.mark.parametrize(("biased", "unverified"), [(True, False), (False, True), (True, True)])
def test_self_attested_flags_are_an_extra_wall(biased: bool, unverified: bool) -> None:
    # Even a perfectly-bound artifact cannot pass if the result self-attests biased/unverified.
    art = _artifact(_CLEAN_MEMBERS)
    b = _binding(("AAPL", "MSFT"), membership_artifact_hash(art))
    assert t2_survivorship(_result(biased=biased, unverified=unverified), b, art).passed is False


def test_malformed_artifact_fails_closed_via_exception() -> None:
    # A tz-naive delist date vs a tz-aware window raises on comparison → caught → fail closed.
    members = (
        SymbolMembership("AAPL", active=True, listed_utc=None, delisted_utc=datetime(2023, 5, 1)),
    )
    art = _artifact(members)
    b = _binding(("AAPL",), membership_artifact_hash(art))
    comp = t2_survivorship(_result(), b, art)
    assert comp.passed is False
    assert "failed closed" in comp.reason


def test_global_bool_path_is_deleted() -> None:
    import trading.bias_gate.tests_t2 as t2

    assert not hasattr(t2, "_PIT_VERIFIER_WIRED")  # the forgeable bool fallback is GONE
