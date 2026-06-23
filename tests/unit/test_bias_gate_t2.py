"""C4 / red-team D1 — T2 survivorship is UNFORGEABLE: a token-gated, hash-bound PIT binding.

The binding can no longer be hand-built (``ProvenanceBinding`` is token-gated; only
``provenance_binding_from`` mints it from a real POLYGON_PIT snapshot whose ``universe_hash`` is
base-owned). So T2's hash bind ties the artifact to a REAL Polygon membership — a fabricated
artifact
fails (hash mismatch). The coverage logic (``_covers_window``) is unit-tested directly.
"""

from __future__ import annotations

from datetime import UTC, datetime

import _gate_fixtures as fx
import pytest

from trading.backtest.statistics import BacktestResult
from trading.bias_gate.gate import GateComponent
from trading.bias_gate.tests_t2 import _covers_window, t2_survivorship
from trading.data.membership_artifact import (
    MembershipArtifact,
    SymbolMembership,
    provenance_binding_from,
)
from trading.data.universe import SourceTier

_AS_OF = datetime(2023, 6, 1, tzinfo=UTC)
_WIN_START = datetime(2021, 1, 1, tzinfo=UTC)
_WIN_END = datetime(2023, 6, 1, tzinfo=UTC)
_SYMS = ("AAPL", "MSFT")


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


def _valid(symbols: tuple[str, ...] = _SYMS):
    snap = fx.pit_snapshot(symbols, _AS_OF)
    art = fx.matching_artifact(symbols, _AS_OF)
    binding = provenance_binding_from(
        snap, traded_symbols=symbols, window_start=_WIN_START, window_end=_WIN_END
    )
    return binding, art


def test_returns_gate_component() -> None:
    comp = t2_survivorship(_result())
    assert isinstance(comp, GateComponent) and comp.name == "T2_survivorship"


def test_missing_binding_or_artifact_fails_closed() -> None:
    assert t2_survivorship(_result()).passed is False
    binding, art = _valid()
    assert t2_survivorship(_result(), binding, None).passed is False
    assert t2_survivorship(_result(), None, art).passed is False


def test_passes_with_a_producer_minted_binding_and_matching_artifact() -> None:
    binding, art = _valid()
    comp = t2_survivorship(_result(), binding, art)
    assert comp.passed is True and "PIT-verified" in comp.reason


def test_forged_artifact_dropping_a_symbol_fails_closed() -> None:
    # binding is over a real 3-symbol snapshot; a forged artifact that DROPS SIVB hashes
    # differently.
    snap = fx.pit_snapshot(("AAPL", "MSFT", "SIVB"), _AS_OF)
    binding = provenance_binding_from(
        snap, traded_symbols=("AAPL", "MSFT", "SIVB"), window_start=_WIN_START, window_end=_WIN_END
    )
    forged = fx.matching_artifact(("AAPL", "MSFT"), _AS_OF)  # SIVB dropped -> different hash
    comp = t2_survivorship(_result(), binding, forged)
    assert comp.passed is False and "hash" in comp.reason


def test_wrong_source_tier_artifact_fails_closed() -> None:
    binding, _ = _valid()
    operator_art = MembershipArtifact(
        1,
        SourceTier.OPERATOR_FILE,
        _AS_OF,
        _AS_OF,
        (SymbolMembership("AAPL", True, None, None), SymbolMembership("MSFT", True, None, None)),
    )
    assert t2_survivorship(_result(), binding, operator_art).passed is False


def test_artifact_snapshot_before_window_end_fails_closed() -> None:
    snap = fx.pit_snapshot(_SYMS, datetime(2021, 6, 1, tzinfo=UTC))  # as_of < window_end
    art = fx.matching_artifact(_SYMS, datetime(2021, 6, 1, tzinfo=UTC))
    binding = provenance_binding_from(
        snap, traded_symbols=_SYMS, window_start=_WIN_START, window_end=_WIN_END
    )
    assert t2_survivorship(_result(), binding, art).passed is False


@pytest.mark.parametrize(("biased", "unverified"), [(True, False), (False, True), (True, True)])
def test_self_attested_flags_are_an_extra_wall(biased: bool, unverified: bool) -> None:
    binding, art = _valid()
    assert (
        t2_survivorship(_result(biased=biased, unverified=unverified), binding, art).passed is False
    )


def test_malformed_artifact_fails_closed_via_exception() -> None:
    snap = fx.pit_snapshot(("AAPL",), _AS_OF)
    binding = provenance_binding_from(
        snap, traded_symbols=("AAPL",), window_start=_WIN_START, window_end=_WIN_END
    )
    # a tz-naive delist date vs the tz-aware window raises inside _covers_window -> caught -> fail
    bad_art = MembershipArtifact(
        1,
        SourceTier.POLYGON_PIT,
        _AS_OF,
        _AS_OF,
        (SymbolMembership("AAPL", True, None, datetime(2023, 5, 1)),),
    )
    comp = t2_survivorship(_result(), binding, bad_art)
    assert comp.passed is False


def test_covers_window_logic_directly() -> None:
    clean = SymbolMembership("AAPL", active=True, listed_utc=None, delisted_utc=None)
    assert _covers_window(clean, _WIN_START, _WIN_END) is True
    delisted_mid = SymbolMembership(
        "SIVB", active=True, listed_utc=None, delisted_utc=datetime(2023, 3, 28, tzinfo=UTC)
    )
    assert _covers_window(delisted_mid, _WIN_START, _WIN_END) is False  # delisted before window end
    listed_late = SymbolMembership(
        "NEW", active=True, listed_utc=datetime(2022, 1, 1, tzinfo=UTC), delisted_utc=None
    )
    assert _covers_window(listed_late, _WIN_START, _WIN_END) is False  # listed after window start
    inactive = SymbolMembership("X", active=False, listed_utc=None, delisted_utc=None)
    assert _covers_window(inactive, _WIN_START, _WIN_END) is False


def test_gate_panel_cross_check_rejects_a_forged_subset() -> None:
    # red-team D1: even a producer-minted binding is rejected if its traded-set/window does not
    # match
    # the panel the engine actually ran (a driver cannot bind a survivor-subset).
    from trading.bias_gate.gate import _t2_component

    panel = fx.panel(300, n_symbols=2)  # SYM0, SYM1
    idx = panel.bars["SYM0"].index
    snap = fx.pit_snapshot(("SYM0", "SYM1"), fx.AS_OF.ts)
    art = fx.matching_artifact(("SYM0", "SYM1"), fx.AS_OF.ts)
    ws, we = idx.min().to_pydatetime(), idx.max().to_pydatetime()
    subset = provenance_binding_from(snap, traded_symbols=("SYM0",), window_start=ws, window_end=we)
    assert _t2_component(_result(), subset, art, panel).passed is False  # subset != panel
    full = provenance_binding_from(
        snap, traded_symbols=("SYM0", "SYM1"), window_start=ws, window_end=we
    )
    assert _t2_component(_result(), full, art, panel).passed is True  # honest binding passes


def test_global_bool_path_is_deleted() -> None:
    import trading.bias_gate.tests_t2 as t2

    assert not hasattr(t2, "_PIT_VERIFIER_WIRED")  # the forgeable bool fallback is GONE
