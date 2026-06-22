"""Tests for the SQLite TrialLedger — Increment 3 cluster 2 (the §5 / M18 overfit defense).

The ledger counts every DISTINCT (kind, ref_id, params) factor/param combo ever evaluated —
``n_trials`` is the Deflated-Sharpe / M18 search-breadth deflation input, so UNDER-counting is the
exact fail-open vector the ledger exists to defend. These tests prove: idempotent per combo;
monotonic (no API can lower the count, no delete path exists); fail-closed on a corrupt DB; build
twice against the same path does not double-count; unencodable params are rejected.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from trading.factors.errors import TrialLedgerError
from trading.factors.trial_ledger import TrialLedger, TrialRecord


def _ledger(tmp_path: Path, *, clock: float = 1000.0) -> TrialLedger:
    return TrialLedger(tmp_path / "trials.sqlite", clock=lambda: clock)


def test_record_and_count(tmp_path: Path) -> None:
    led = _ledger(tmp_path)
    assert led.n_trials() == 0
    rec = led.record("factor", "mom_21d", {"z_window": 21, "raw_lookback": 21})
    assert isinstance(rec, TrialRecord)
    assert rec.kind == "factor" and rec.ref_id == "mom_21d"
    assert rec.params == {"z_window": 21, "raw_lookback": 21}
    assert led.n_trials() == 1


def test_record_is_idempotent_per_combo(tmp_path: Path) -> None:
    led = _ledger(tmp_path)
    first = led.record("factor", "mom_21d", {"z_window": 21})
    again = led.record("factor", "mom_21d", {"z_window": 21})  # same combo => no-op
    assert led.n_trials() == 1
    assert first.combo_hash == again.combo_hash
    assert first.created == again.created  # created is first-write-wins, not overwritten


def test_distinct_params_are_distinct_trials(tmp_path: Path) -> None:
    led = _ledger(tmp_path)
    led.record("factor", "mom_21d", {"z_window": 21})
    led.record("factor", "mom_21d", {"z_window": 63})  # a sweep over z_window is a NEW hypothesis
    led.record("factor", "mom_63d", {"z_window": 21})  # different ref_id is a new trial
    assert led.n_trials() == 3


def test_build_twice_same_path_does_not_double_count(tmp_path: Path) -> None:
    path = tmp_path / "trials.sqlite"
    led1 = TrialLedger(path, clock=lambda: 1.0)
    for i in range(13):
        led1.record("factor", f"f{i}", {"z_window": 21})
    assert led1.n_trials() == 13
    # A fresh process re-registers the SAME 13 (default_registry runs at every start) -> still 13.
    led2 = TrialLedger(path, clock=lambda: 2.0)
    for i in range(13):
        led2.record("factor", f"f{i}", {"z_window": 21})
    assert led2.n_trials() == 13


def test_new_combo_monotonically_increments(tmp_path: Path) -> None:
    path = tmp_path / "trials.sqlite"
    led = TrialLedger(path, clock=lambda: 1.0)
    for i in range(13):
        led.record("factor", f"f{i}", {"z_window": 21})
    assert led.n_trials() == 13
    led.record("factor", "f_new", {"z_window": 21})
    assert led.n_trials() == 14


def test_trials_lists_all_records(tmp_path: Path) -> None:
    led = _ledger(tmp_path)
    led.record("factor", "a", {"z_window": 21})
    led.record("factor", "b", {"z_window": 21})
    recs = led.trials()
    assert len(recs) == 2
    assert {r.ref_id for r in recs} == {"a", "b"}
    assert all(isinstance(r, TrialRecord) for r in recs)


# --- monotonicity is STRUCTURAL: no API can lower the count (mirror universe.py forge-proofing) ---


def test_no_mutating_api_exists(tmp_path: Path) -> None:
    led = _ledger(tmp_path)
    forbidden = {"delete", "remove", "clear", "drop", "reset", "update", "decrement", "pop"}
    present = {name for name in dir(led) if any(f in name.lower() for f in forbidden)}
    assert present == set(), f"a count-lowering API would break monotonicity: {present}"


# --- fail-closed: a corrupt DB raises, NEVER returns 0 / a lower count ---


def test_corrupt_db_fails_closed_on_open(tmp_path: Path) -> None:
    path = tmp_path / "trials.sqlite"
    path.write_bytes(b"this is not a sqlite database, it is garbage" * 8)
    with pytest.raises(TrialLedgerError):
        TrialLedger(path)


def test_tampered_params_json_fails_closed_on_read(tmp_path: Path) -> None:
    import sqlite3

    path = tmp_path / "trials.sqlite"
    led = TrialLedger(path, clock=lambda: 1.0)
    led.record("factor", "a", {"z_window": 21})
    conn = sqlite3.connect(path)  # tamper a stored row's params_json to invalid JSON
    with conn:
        conn.execute("UPDATE trials SET params_json = ?", ("{not valid json",))
    conn.close()
    with pytest.raises(TrialLedgerError, match="corrupt"):
        led.trials()


def test_corrupt_db_fails_closed_on_read(tmp_path: Path) -> None:
    path = tmp_path / "trials.sqlite"
    led = TrialLedger(path, clock=lambda: 1.0)
    led.record("factor", "a", {"z_window": 21})
    path.write_bytes(b"corruption after a valid write" * 8)  # truncate/clobber the DB
    with pytest.raises(TrialLedgerError):
        led.n_trials()


# --- unencodable params are rejected (no default=str coercion that could collide combos) ---


def test_unencodable_params_are_rejected(tmp_path: Path) -> None:
    led = _ledger(tmp_path)

    class _Weird:
        pass

    with pytest.raises(TrialLedgerError, match="encod"):
        led.record("factor", "x", {"obj": _Weird()})  # type: ignore[dict-item]
    assert led.n_trials() == 0  # nothing recorded on a rejected trial


def test_param_key_order_does_not_change_the_combo(tmp_path: Path) -> None:
    led = _ledger(tmp_path)
    led.record("factor", "a", {"z_window": 21, "raw_lookback": 5})
    led.record("factor", "a", {"raw_lookback": 5, "z_window": 21})  # same combo, different order
    assert led.n_trials() == 1
