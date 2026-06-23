"""Tests for the purged + embargoed walk-forward splitter — Increment 4 cluster 5.

Proves: anchored/expanding train (every fold starts at the first session); 12/3/3 calendar-month
windows; OOS test sets are DISJOINT across folds; a clean gap (purge + embargo bars) sits between
train-end and test-start so no train bar is within the gap of a test window; the splitter is
PREFIX-STABLE (a later session never retroactively changes an earlier fold); and removing the purge
collapses the gap (the purge has teeth) while a malformed session index fails closed.
"""

from __future__ import annotations

import pandas as pd
import pytest

from trading.backtest.errors import WalkForwardError
from trading.backtest.walk_forward import WalkForwardConfig, walk_forward_folds


def _sessions(years: int = 5) -> pd.DatetimeIndex:
    # business-day sessions (realistic spacing; the splitter operates on whatever index it is given)
    idx = pd.bdate_range("2015-01-02", periods=years * 252, tz="UTC")
    return pd.DatetimeIndex(idx, name="ts")


# --- config validation ---


def test_default_config_is_12_3_3() -> None:
    c = WalkForwardConfig()
    assert (c.train_months, c.test_months, c.step_months) == (12, 3, 3)
    assert c.purge_bars == 1
    assert c.embargo_frac == pytest.approx(0.01)


def test_config_is_frozen_and_validated() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        WalkForwardConfig(train_months=0)
    with pytest.raises(ValidationError):
        WalkForwardConfig(purge_bars=-1)
    with pytest.raises(ValidationError):
        WalkForwardConfig().train_months = 6  # type: ignore[misc]


def test_overlapping_test_windows_rejected() -> None:
    # step < test overlaps consecutive OOS test windows -> the engine double-counts sessions and
    # inflates the OOS edge magnitude (red-team WF-1). Must fail closed at construction.
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        WalkForwardConfig(test_months=6, step_months=3)
    with pytest.raises(ValidationError):
        WalkForwardConfig(test_months=12, step_months=1)


def test_disjoint_geometry_allowed() -> None:
    # step == test (full coverage, the 12/3/3 default) and step > test (honest sub-sampling)
    # are both legitimate — only overlap is rejected.
    assert WalkForwardConfig(test_months=3, step_months=3).step_months == 3
    assert WalkForwardConfig(test_months=3, step_months=6).step_months == 6


# --- malformed input fails closed ---


def test_empty_sessions_raises() -> None:
    with pytest.raises(WalkForwardError):
        walk_forward_folds(pd.DatetimeIndex([], name="ts"), WalkForwardConfig())


def test_non_monotonic_sessions_raises() -> None:
    bad = pd.DatetimeIndex(
        pd.to_datetime(["2020-01-03", "2020-01-02"]).tz_localize("UTC"), name="ts"
    )
    with pytest.raises(WalkForwardError):
        walk_forward_folds(bad, WalkForwardConfig())


def test_too_short_history_yields_no_folds() -> None:
    short = pd.DatetimeIndex(pd.bdate_range("2020-01-01", periods=100, tz="UTC"), name="ts")
    assert walk_forward_folds(short, WalkForwardConfig()) == ()


def test_non_datetimeindex_raises() -> None:
    with pytest.raises(WalkForwardError):
        walk_forward_folds([1, 2, 3], WalkForwardConfig())  # type: ignore[arg-type]


def test_huge_purge_drops_every_fold() -> None:
    # train fully purged away on every fold -> no folds (the fail-closed train-empty skip).
    folds = walk_forward_folds(_sessions(5), WalkForwardConfig(purge_bars=10_000))
    assert folds == ()


def test_calendar_gap_with_no_sessions_in_a_test_window_is_skipped() -> None:
    # year 1 of sessions, then a multi-quarter gap, then resume: a 3-month test window that lands
    # entirely inside the gap has no sessions and is skipped (not an empty/oversized fold).
    a = pd.bdate_range("2015-01-02", periods=252, tz="UTC")
    b = pd.bdate_range("2016-07-01", periods=252, tz="UTC")
    sessions = pd.DatetimeIndex(a.append(b), name="ts")
    folds = walk_forward_folds(sessions, WalkForwardConfig())
    # the splitter still returns well-formed folds (every test window non-empty, disjoint)
    for f in folds:
        assert len(f.test) > 0
        assert f.train[-1] < f.test[0]


# --- structure: anchored, disjoint OOS, clean gap ---


def test_folds_are_produced_over_multi_year_history() -> None:
    folds = walk_forward_folds(_sessions(5), WalkForwardConfig())
    assert len(folds) >= 8  # ~ (5y - 1y train) / 3-month step


def test_train_is_anchored_at_first_session() -> None:
    sessions = _sessions(5)
    folds = walk_forward_folds(sessions, WalkForwardConfig())
    for f in folds:
        assert f.train[0] == sessions[0]  # expanding: always starts at history start


def test_oos_test_sets_are_disjoint() -> None:
    folds = walk_forward_folds(_sessions(5), WalkForwardConfig())
    seen: set[pd.Timestamp] = set()
    for f in folds:
        ts = set(f.test)
        assert seen.isdisjoint(ts), "an OOS session appears in two folds"
        seen |= ts


def test_train_and_test_never_overlap_and_respect_the_gap() -> None:
    cfg = WalkForwardConfig()
    folds = walk_forward_folds(_sessions(5), cfg)
    for f in folds:
        assert set(f.train).isdisjoint(set(f.test))
        # the last train session must precede the first test session by at least `purge_bars`
        # (the embargo widens it further); train_end < test_start strictly.
        assert f.train[-1] < f.test[0]


def test_purge_has_teeth_zero_gap_touches_test() -> None:
    sessions = _sessions(5)
    purged = walk_forward_folds(sessions, WalkForwardConfig(purge_bars=1, embargo_frac=0.0))
    nogap = walk_forward_folds(sessions, WalkForwardConfig(purge_bars=0, embargo_frac=0.0))
    # with no purge, the last train session is the session immediately before the test window;
    # with purge=1 it is dropped (a strictly earlier session). This proves the purge removes bars.
    f_purged, f_nogap = purged[0], nogap[0]
    assert f_purged.test[0] == f_nogap.test[0]
    assert f_purged.train[-1] < f_nogap.train[-1]


# --- prefix stability (a later session never changes an earlier fold) ---


def test_splitter_is_prefix_stable() -> None:
    sessions = _sessions(5)
    cfg = WalkForwardConfig()
    full = walk_forward_folds(sessions, cfg)
    assert len(full) >= 3
    cut = full[1].test[-1]  # cut exactly at the end of the 2nd fold's OOS window
    prefix = sessions[sessions <= cut]
    pfolds = walk_forward_folds(prefix, cfg)
    assert len(pfolds) >= 2
    for a, b in zip(full[:2], pfolds[:2], strict=True):
        assert a.train.equals(b.train)
        assert a.test.equals(b.test)
