"""C5 — graduated GuardLevel + ReconLevel parity (Increment 6 PART B)."""

from __future__ import annotations

import dataclasses

import pytest

from trading.executor.reconciler import ReconLevel
from trading.guards.levels import GuardLevel, GuardResult, recon_to_guard, worst_level


def _r(level: GuardLevel) -> GuardResult:
    return GuardResult(guard_id="Gx", level=level, reason="", gates_orders=True)


def test_worst_level_folds_green_yellow_orange_red() -> None:
    assert worst_level([]) is GuardLevel.GREEN
    assert worst_level([_r(GuardLevel.GREEN), _r(GuardLevel.YELLOW)]) is GuardLevel.YELLOW
    assert worst_level([_r(GuardLevel.YELLOW), _r(GuardLevel.ORANGE)]) is GuardLevel.ORANGE
    assert (
        worst_level([_r(GuardLevel.GREEN), _r(GuardLevel.RED), _r(GuardLevel.ORANGE)])
        is GuardLevel.RED
    )


def test_recon_to_guard_parity() -> None:
    assert recon_to_guard(ReconLevel.OK) is GuardLevel.GREEN
    assert recon_to_guard(ReconLevel.YELLOW) is GuardLevel.YELLOW
    assert recon_to_guard(ReconLevel.ORANGE) is GuardLevel.ORANGE
    assert recon_to_guard(ReconLevel.RED) is GuardLevel.RED


def test_guard_result_is_frozen() -> None:
    r = _r(GuardLevel.RED)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.level = GuardLevel.GREEN  # type: ignore[misc]
