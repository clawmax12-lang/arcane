"""C3 / tripwire A2 — the n_trials high-water-mark (DB deletion cannot reset the deflation count).

``TrialLedger`` fails closed on a CORRUPT db but NOT a MISSING one — raw deletion of the ``.db``
recreates a fresh 0-trial ledger, silently resetting the DSR deflation input to 0 (the M18 vector).
The high-water-mark is a persistent monotonic floor (the ``kill_switch.json`` atomic-write idiom):
``checked_n_trials`` RAISES if the live count ever drops below the recorded mark.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from trading.bias_gate.errors import HighWaterMarkError
from trading.bias_gate.high_water_mark import NTrialsHighWaterMark


def _hwm(tmp_path: Path) -> NTrialsHighWaterMark:
    return NTrialsHighWaterMark(tmp_path / "n_trials_high_water_mark.json")


def test_fresh_start_returns_live_and_records_it(tmp_path: Path) -> None:
    hwm = _hwm(tmp_path)
    assert hwm.checked_n_trials(0) == 0
    assert hwm.checked_n_trials(3) == 3


def test_monotonic_rise_persists_atomically_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "n_trials_high_water_mark.json"
    assert NTrialsHighWaterMark(path).checked_n_trials(8) == 8
    # a brand-new instance reads the persisted mark — a later DROP must raise.
    fresh = NTrialsHighWaterMark(path)
    assert fresh.checked_n_trials(8) == 8  # equal is fine
    assert fresh.checked_n_trials(12) == 12  # rise is fine
    with pytest.raises(HighWaterMarkError):
        NTrialsHighWaterMark(path).checked_n_trials(5)  # DB deleted -> count fell -> fail closed


def test_drop_to_zero_raises(tmp_path: Path) -> None:
    hwm = _hwm(tmp_path)
    hwm.checked_n_trials(17)
    with pytest.raises(HighWaterMarkError):
        hwm.checked_n_trials(0)


def test_drop_to_partial_raises(tmp_path: Path) -> None:
    hwm = _hwm(tmp_path)
    hwm.checked_n_trials(10)
    with pytest.raises(HighWaterMarkError):
        hwm.checked_n_trials(7)


@pytest.mark.parametrize("bad", [-1, True, False, 1.5, "5", None])
def test_non_nonnegative_int_live_count_is_rejected(tmp_path: Path, bad: object) -> None:
    with pytest.raises(HighWaterMarkError):
        _hwm(tmp_path).checked_n_trials(bad)  # type: ignore[arg-type]


def test_corrupt_mark_file_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "n_trials_high_water_mark.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(HighWaterMarkError):
        NTrialsHighWaterMark(path).checked_n_trials(5)


@pytest.mark.parametrize(
    "payload",
    [
        '{"n_trials_high_water_mark": "5"}',  # string, not int
        '{"n_trials_high_water_mark": true}',  # bool, not int
        '{"n_trials_high_water_mark": -3}',  # negative
        '{"n_trials_high_water_mark": 1.5}',  # float
        '{"wrong_key": 5}',  # missing key
        "[]",  # not an object
    ],
)
def test_malformed_mark_payload_fails_closed(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "n_trials_high_water_mark.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(HighWaterMarkError):
        NTrialsHighWaterMark(path).checked_n_trials(5)


def test_dangling_symlink_path_fails_closed(tmp_path: Path) -> None:
    target = tmp_path / "missing.json"
    link = tmp_path / "n_trials_high_water_mark.json"
    link.symlink_to(target)  # dangling: target does not exist
    with pytest.raises(HighWaterMarkError):
        NTrialsHighWaterMark(link).checked_n_trials(5)


def test_persisted_schema_is_the_expected_key(tmp_path: Path) -> None:
    path = tmp_path / "n_trials_high_water_mark.json"
    NTrialsHighWaterMark(path).checked_n_trials(9)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {"n_trials_high_water_mark": 9}


def test_verify_writable_passes_on_a_writable_dir(tmp_path: Path) -> None:
    _hwm(tmp_path).verify_writable()  # no raise
    assert not (tmp_path / "n_trials_high_water_mark.json.probe").exists()
