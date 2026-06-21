"""Tests for the LIVE_MODE triple-lock gate (Increment 1 safety spine).

The defining safety property: live trading is impossible unless ALL THREE locks are
open, and the code lock is closed by default — so config + CLI alone can never arm it.
"""

from __future__ import annotations

import itertools
from pathlib import Path

import pytest

from trading.executor.live_mode import (
    LIVE_CONFIRM_PHRASE,
    LiveModeStatus,
    assert_paper_for_handoff,
    cli_lock_open,
    code_lock_open,
    is_live,
)
from trading.risk import constants as C


def test_truth_table_only_all_true_is_live() -> None:
    for code, conf, cli in itertools.product([False, True], repeat=3):
        status = LiveModeStatus(code_lock=code, config_lock=conf, cli_lock=cli)
        assert status.is_live is (code and conf and cli)


def test_code_lock_closed_by_default() -> None:
    assert code_lock_open() is False
    assert C.LIVE_MODE_CODE_DEFAULT is False


def test_cannot_go_live_via_config_and_cli_alone(tmp_path: Path) -> None:
    marker = tmp_path / "LIVE_MODE_CONFIRMED"
    marker.write_text(LIVE_CONFIRM_PHRASE)
    assert cli_lock_open(marker) is True
    # config True + CLI marker present, but the code lock is still closed -> paper.
    assert is_live(config_live_mode=True, marker_path=marker) is False


def test_cli_lock_absent_marker(tmp_path: Path) -> None:
    assert cli_lock_open(tmp_path / "nope") is False


def test_cli_lock_wrong_content(tmp_path: Path) -> None:
    marker = tmp_path / "LIVE_MODE_CONFIRMED"
    marker.write_text("yes please go live")
    assert cli_lock_open(marker) is False


def test_handoff_assertion_passes_for_paper() -> None:
    assert_paper_for_handoff(config_live_mode=False)


def test_handoff_assertion_fails_if_config_live() -> None:
    with pytest.raises(AssertionError):
        assert_paper_for_handoff(config_live_mode=True)
