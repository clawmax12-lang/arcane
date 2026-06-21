"""Tests for the startup preflight (wires verify_writable + paper handoff).

Closes the v2 red-team residual that verify_writable() had no production caller.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from trading.executor.kill_switch import KillSwitch, KillSwitchUnwritableError
from trading.executor.preflight import preflight


def test_preflight_passes_for_writable_paper(tmp_path: Path) -> None:
    preflight(KillSwitch(tmp_path / "ks.json"), config_live_mode=False)  # must not raise


def test_preflight_aborts_when_store_unwritable(tmp_path: Path) -> None:
    sub = tmp_path / "ro"
    sub.mkdir()
    os.chmod(sub, 0o500)
    try:
        with pytest.raises(KillSwitchUnwritableError):
            preflight(KillSwitch(sub / "ks.json"), config_live_mode=False)
    finally:
        os.chmod(sub, 0o700)


def test_preflight_aborts_on_live_config(tmp_path: Path) -> None:
    with pytest.raises(AssertionError):
        preflight(KillSwitch(tmp_path / "ks.json"), config_live_mode=True)
