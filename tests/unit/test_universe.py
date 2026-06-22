"""Tests for the PIT universe core + survivorship T2 (Increment 2 STEP 7).

Each test guards a STRUCTURAL invariant from the design: survivorship-cleanliness must be
unrepresentable while Polygon is deferred (T2 never passes), the meta is forge-proof, the @final
base — not the subclass — owns the verdict, and no hardcoded symbol list can masquerade as PIT.
"""

from __future__ import annotations

import ast
import dataclasses
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from trading.data.errors import (
    HardcodedUniverseError,
    NonPITMembershipError,
    PITViolationError,
    RestatedMembershipError,
    UniverseConfigError,
    UniverseEmptyError,
)
from trading.data.pit import AsOf
from trading.data.quality import coverage_report
from trading.data.reliability import Reliability
from trading.data.universe import (
    TIER_IS_PIT,
    BiasTestResult,
    PITUniverse,
    SourceTier,
    UniverseMeta,
    UniverseSnapshot,
    expected_grid,
    is_pit,
    survivorship_t2,
)

_AS_OF = AsOf(datetime(2024, 7, 9, tzinfo=UTC))
_DATA_DIR = Path(__file__).resolve().parents[2] / "src" / "trading" / "data"


class _FakeUniverse(PITUniverse):
    SOURCE_TIER = SourceTier.OPERATOR_FILE

    def __init__(
        self, symbols: frozenset[str] = frozenset({"AAPL", "MSFT"}), artifact_hash: str = "a" * 64
    ) -> None:
        self._symbols = symbols
        self._hash = artifact_hash

    def _members(self, as_of: AsOf, session: pd.Timestamp) -> tuple[frozenset[str], str]:
        return self._symbols, self._hash


def _meta(tier: SourceTier = SourceTier.OPERATOR_FILE, **kw: object) -> UniverseMeta:
    base: dict[str, object] = {
        "as_of": _AS_OF.ts,
        "session": pd.Timestamp("2024-07-09"),
        "source_tier": tier,
        "is_pit_membership": is_pit(tier),
        "member_count": 2,
        "universe_hash": "h" * 64,
        "loader": "X",
    }
    base.update(kw)
    return UniverseMeta(**base)  # type: ignore[arg-type]


# --- the single PIT authority ---


def test_tier_mapping_is_complete() -> None:
    # Every SourceTier must have an explicit PIT decision — none granted by omission.
    assert set(TIER_IS_PIT) == set(SourceTier)


def test_is_pit_authority() -> None:
    assert is_pit(SourceTier.OPERATOR_FILE) is False
    assert is_pit(SourceTier.ALPACA_TODAY) is False
    assert is_pit(SourceTier.POLYGON_PIT) is True


# --- forge-proof meta (INV-2 / INV-7) ---


def test_meta_rejects_clean_non_pit_tier() -> None:
    with pytest.raises(NonPITMembershipError):
        _meta(SourceTier.OPERATOR_FILE, is_pit_membership=True)


def test_survivorship_unverified_is_derived_not_a_field() -> None:
    names = {f.name for f in dataclasses.fields(UniverseMeta)}
    assert "survivorship_unverified" not in names  # nothing to forge
    assert _meta(SourceTier.OPERATOR_FILE).survivorship_unverified is True


def test_pit_tier_requires_membership_vintage() -> None:
    with pytest.raises(RestatedMembershipError):
        _meta(SourceTier.POLYGON_PIT)  # is_pit=True but no vintage -> fake-PIT refused
    ok = _meta(SourceTier.POLYGON_PIT, membership_vintage=_AS_OF.ts)
    assert ok.survivorship_unverified is False


def test_pit_membership_vintage_must_not_be_after_as_of() -> None:
    # SURV-1 (sealing red-team): a FORWARD-dated vintage is a survivorship look-ahead — mirror
    # pit_guard's ingest_ts<=as_of and AsOf's reject-future. Completes the upgrade tripwire so the
    # future Polygon author cannot mint fake-PIT by post-dating instead of by omission.
    future = _AS_OF.ts + timedelta(days=1)
    with pytest.raises(RestatedMembershipError):
        _meta(SourceTier.POLYGON_PIT, membership_vintage=future)
    # vintage == as_of and vintage < as_of are both accepted (not a look-ahead).
    assert (
        _meta(SourceTier.POLYGON_PIT, membership_vintage=_AS_OF.ts).survivorship_unverified is False
    )
    past = _AS_OF.ts - timedelta(days=30)
    assert _meta(SourceTier.POLYGON_PIT, membership_vintage=past).survivorship_unverified is False


def test_t2_evidence_records_membership_vintage() -> None:
    # The T2 verdict must be auditable: the vintage it trusted (or its absence) is in the evidence.
    clean = survivorship_t2(_meta(SourceTier.POLYGON_PIT, membership_vintage=_AS_OF.ts))
    assert clean.evidence["membership_vintage"] == _AS_OF.ts.isoformat()
    degraded = survivorship_t2(_meta(SourceTier.OPERATOR_FILE))
    assert degraded.evidence["membership_vintage"] == "none"


def test_meta_reliability_is_structured() -> None:
    assert _meta().reliability is Reliability.STRUCTURED


# --- T2 never passes on any reachable path (INV-1) ---


def test_t2_never_passes_for_shipped_tiers() -> None:
    for tier in (SourceTier.OPERATOR_FILE, SourceTier.ALPACA_TODAY):
        res = survivorship_t2(_meta(tier))
        assert res.passed is False
        assert res.reason  # non-empty


def test_no_shipped_subclass_declares_polygon_pit() -> None:
    offenders: list[str] = []
    for py in _DATA_DIR.glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if "PITUniverse" not in {b.id for b in node.bases if isinstance(b, ast.Name)}:
                continue
            for stmt in node.body:
                val: ast.expr | None = None
                if isinstance(stmt, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "SOURCE_TIER" for t in stmt.targets
                ):
                    val = stmt.value
                elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    val = stmt.value if stmt.target.id == "SOURCE_TIER" else None
                if isinstance(val, ast.Attribute) and val.attr == "POLYGON_PIT":
                    offenders.append(f"{py.name}:{node.name}")
    assert not offenders, f"a shipped subclass declares POLYGON_PIT: {offenders}"


def test_bias_test_result_rejects_silent_false() -> None:
    with pytest.raises(ValueError, match="reason"):
        BiasTestResult(test_id="T2", passed=False, reason="", as_of=_AS_OF.ts, evidence={})


def test_t2_result_is_json_serializable() -> None:
    r = survivorship_t2(_meta())
    payload = json.dumps(
        {
            "test_id": r.test_id,
            "passed": r.passed,
            "reason": r.reason,
            "as_of": r.as_of.isoformat(),
            "evidence": dict(r.evidence),
        }
    )
    assert '"passed": false' in payload


# --- the @final base owns the verdict (INV-3) ---


def test_no_universe_subclass_overrides_as_of_members() -> None:
    offenders: list[str] = []
    for py in _DATA_DIR.glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and "PITUniverse" in {
                b.id for b in node.bases if isinstance(b, ast.Name)
            }:
                methods = {
                    n.name
                    for n in node.body
                    if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
                }
                if "as_of_members" in methods:
                    offenders.append(f"{py.name}:{node.name}")
    assert not offenders, f"@final as_of_members overridden in: {offenders}"


def test_adversarial_members_cannot_mint_clean_verdict() -> None:
    # Even a subclass that tries to hand back a 'clean' signal still yields unverified=True,
    # because the base builds the meta from SOURCE_TIER, not from _members output.
    snap = _FakeUniverse().as_of_members(as_of=_AS_OF)
    assert snap.meta.survivorship_unverified is True
    assert survivorship_t2(snap.meta).passed is False


# --- no hardcoded list (INV-4) ---


def test_empty_artifact_hash_refused() -> None:
    with pytest.raises(HardcodedUniverseError):
        _FakeUniverse(artifact_hash="").as_of_members(as_of=_AS_OF)


def _module_scope_ticker_literals(source: str) -> list[str]:
    tree = ast.parse(source)
    found: list[str] = []
    for node in tree.body:  # MODULE scope only
        if isinstance(node, ast.Assign):
            value: ast.expr | None = node.value
        elif isinstance(node, ast.AnnAssign):
            value = node.value
        else:
            continue
        elts: list[ast.expr] | None = None
        if isinstance(value, ast.List | ast.Tuple | ast.Set):
            elts = list(value.elts)
        elif (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id in {"frozenset", "set"}
            and value.args
            and isinstance(value.args[0], ast.List | ast.Tuple | ast.Set)
        ):
            elts = list(value.args[0].elts)
        if elts is None:
            continue
        strs = [e for e in elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        if len(strs) >= 3:
            found.append(ast.dump(value)[:60])
    return found


def test_no_module_scope_ticker_literals_in_universe_py() -> None:
    src = (_DATA_DIR / "universe.py").read_text(encoding="utf-8")
    assert _module_scope_ticker_literals(src) == []
    # negative fixture: the scanner DOES catch a hardcoded list (so the test has teeth).
    assert _module_scope_ticker_literals('TICKERS = ["AAA", "BBB", "CCC"]\n')


def test_no_llm_imports_in_universe() -> None:
    banned = ("anthropic", "openai", "llm")
    for name in ("universe.py", "universe_sources.py"):
        tree = ast.parse((_DATA_DIR / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    assert not any(b in a.name.lower() for b in banned), f"{name}:{a.name}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not any(b in node.module.lower() for b in banned), f"{name}:{node.module}"


# --- empty + PIT-clock + immutability (INV-5 / INV-6 / INV-8) ---


def test_empty_members_raises_universe_empty() -> None:
    with pytest.raises(UniverseEmptyError):
        _FakeUniverse(symbols=frozenset()).as_of_members(as_of=_AS_OF)


def test_malformed_symbol_rejected() -> None:
    with pytest.raises(UniverseConfigError, match="malformed"):
        _FakeUniverse(symbols=frozenset({"aapl", "MSFT"})).as_of_members(as_of=_AS_OF)


def test_as_of_required_typeerror() -> None:
    with pytest.raises(TypeError):
        _FakeUniverse().as_of_members()  # type: ignore[call-arg]


def test_future_as_of_rejected() -> None:
    with pytest.raises(PITViolationError):
        AsOf(datetime(2999, 1, 1, tzinfo=UTC))


def test_session_resolved_to_prior_session() -> None:
    snap = _FakeUniverse().as_of_members(as_of=_AS_OF)
    assert snap.meta.session <= pd.Timestamp("2024-07-09")


def test_snapshot_symbols_immutable_and_sorted() -> None:
    snap = _FakeUniverse().as_of_members(as_of=_AS_OF)
    assert isinstance(snap.symbols, frozenset)
    assert snap.sorted_symbols() == ("AAPL", "MSFT")
    assert snap.contains("AAPL") and not snap.contains("TSLA")
    assert snap.as_of == _AS_OF.ts


# --- expected_grid / G4 coverage wiring (Commit B) ---


def _grid_snap(as_of: AsOf) -> UniverseSnapshot:
    return _FakeUniverse(symbols=frozenset({"AAPL", "MSFT"})).as_of_members(as_of=as_of)


def test_expected_grid_dst_golden() -> None:
    snap = _grid_snap(AsOf(datetime(2024, 7, 31, tzinfo=UTC)))
    grid = expected_grid(snap, start=pd.Timestamp("2024-01-01"), end=pd.Timestamp("2024-07-31"))
    inst = grid.expected_daily_instants("AAPL")
    assert pd.Timestamp("2024-01-02 05:00", tz="UTC") in inst  # EST midnight
    assert pd.Timestamp("2024-07-01 04:00", tz="UTC") in inst  # EDT midnight (DST-correct)


def test_expected_grid_clamps_to_visible() -> None:
    # as_of mid-session (2024-07-03 12:00Z): that day's bar is not yet visible (closes 17:00Z).
    snap = _grid_snap(AsOf(datetime(2024, 7, 3, 12, tzinfo=UTC)))
    grid = expected_grid(snap, start=pd.Timestamp("2024-07-01"), end=pd.Timestamp("2024-07-10"))
    assert pd.Timestamp("2024-07-02") in grid.sessions
    assert pd.Timestamp("2024-07-03") not in grid.sessions  # PIT-honest: not yet closed at as_of


def test_expected_grid_carries_survivorship_bias_flag() -> None:
    snap = _grid_snap(AsOf(datetime(2024, 7, 10, tzinfo=UTC)))
    grid = expected_grid(snap, start=pd.Timestamp("2024-07-01"), end=pd.Timestamp("2024-07-09"))
    assert grid.coverage_is_survivorship_biased is True  # mirrors the non-PIT snapshot


def test_expected_daily_instants_unknown_symbol() -> None:
    snap = _grid_snap(AsOf(datetime(2024, 7, 10, tzinfo=UTC)))
    grid = expected_grid(snap, start=pd.Timestamp("2024-07-01"), end=pd.Timestamp("2024-07-09"))
    with pytest.raises(KeyError):
        grid.expected_daily_instants("TSLA")


def test_g4_coverage_report_reports_holes_without_imputation() -> None:
    snap = _grid_snap(AsOf(datetime(2024, 7, 31, tzinfo=UTC)))
    grid = expected_grid(snap, start=pd.Timestamp("2024-07-01"), end=pd.Timestamp("2024-07-10"))
    expected = grid.expected_daily_instants("AAPL")
    actual = expected.delete(1)  # punch one hole
    rep = coverage_report(actual, expected)
    assert rep.expected == len(expected)
    assert rep.present == len(expected) - 1
    assert rep.missing == 1
    assert rep.coverage_degraded is True  # reported, never imputed
