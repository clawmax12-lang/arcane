"""C6 — G1–G10 boundaries, fail-closed modes, and the §4.3 non-gating teeth (Increment 6 PART B)."""

from __future__ import annotations

import math
from typing import Any

import pytest

from trading.guards import checks
from trading.guards.checks import STATE_CHECKS
from trading.guards.inputs import GuardState
from trading.guards.levels import GuardLevel


def _state(**over: Any) -> GuardState:
    base: dict[str, Any] = dict(
        now_epoch=1000.0,
        data_as_of_epoch=1000.0,
        last_broker_ok_epoch=1000.0,
        last_llm_ok_epoch=1000.0,
        equity_now=50.0,
        equity_prev=50.0,
        equity_dt_s=60.0,
        orders_in_window=0,
        order_baseline=1.0,
        ntp_offset_s=0.0,
    )
    base.update(over)
    return GuardState(**base)


def test_guard_state_rejects_non_finite() -> None:
    for bad in ("now_epoch", "equity_now", "order_baseline"):
        with pytest.raises(ValueError):
            _state(**{bad: math.nan})
    with pytest.raises(ValueError):
        _state(ntp_offset_s=math.inf)


def test_g1_data_staleness_boundaries() -> None:
    assert (
        checks.g1_data_staleness(_state(data_as_of_epoch=1001.0)).level is GuardLevel.RED
    )  # future
    assert checks.g1_data_staleness(_state(now_epoch=1301.0)).level is GuardLevel.ORANGE  # 301s
    assert checks.g1_data_staleness(_state(now_epoch=1601.0)).level is GuardLevel.RED  # 601s
    assert checks.g1_data_staleness(_state(now_epoch=1100.0)).level is GuardLevel.GREEN


def test_g2_fill_delay_boundaries() -> None:
    assert checks.g2_fill_delay(_state()).level is GuardLevel.GREEN  # no pending
    assert checks.g2_fill_delay(_state(pending_order_age_s=31.0)).level is GuardLevel.ORANGE
    assert checks.g2_fill_delay(_state(pending_order_age_s=121.0)).level is GuardLevel.RED
    assert checks.g2_fill_delay(_state(pending_order_age_s=-1.0)).level is GuardLevel.RED


def test_g4_broker_heartbeat_boundaries() -> None:
    assert checks.g4_broker_heartbeat(_state(now_epoch=1061.0)).level is GuardLevel.ORANGE
    assert checks.g4_broker_heartbeat(_state(now_epoch=1181.0)).level is GuardLevel.RED
    assert checks.g4_broker_heartbeat(_state(now_epoch=1010.0)).level is GuardLevel.GREEN


def test_g5_llm_heartbeat_is_advisory() -> None:
    # LLM down ⇒ degrade-and-page (ORANGE, non-gating), NEVER halt — the deterministic loop runs on.
    hot = checks.g5_llm_heartbeat(_state(now_epoch=1301.0))
    assert hot.level is GuardLevel.ORANGE and hot.gates_orders is False
    assert checks.g5_llm_heartbeat(_state(now_epoch=1100.0)).level is GuardLevel.GREEN


def test_g6_time_drift_fails_closed_on_missing_ntp() -> None:
    assert checks.g6_time_drift(_state(ntp_offset_s=None)).level is GuardLevel.RED
    assert checks.g6_time_drift(_state(ntp_offset_s=1.5)).level is GuardLevel.RED
    assert checks.g6_time_drift(_state(ntp_offset_s=-1.5)).level is GuardLevel.RED
    assert checks.g6_time_drift(_state(ntp_offset_s=0.5)).level is GuardLevel.GREEN


def test_g7_equity_velocity_boundaries_and_fail_closed() -> None:
    assert (
        checks.g7_equity_velocity(_state(equity_dt_s=0.0)).level is GuardLevel.RED
    )  # single sample
    assert checks.g7_equity_velocity(_state(equity_prev=0.0)).level is GuardLevel.RED  # zero base
    assert (
        checks.g7_equity_velocity(_state(equity_now=60.0, equity_dt_s=30.0)).level is GuardLevel.RED
    )  # +20%
    assert (
        checks.g7_equity_velocity(_state(equity_now=55.0, equity_dt_s=30.0)).level
        is GuardLevel.ORANGE
    )  # +10%
    assert (
        checks.g7_equity_velocity(_state(equity_now=52.0, equity_dt_s=30.0)).level
        is GuardLevel.GREEN
    )  # +4%
    # a big move OUTSIDE the velocity window is not a spike
    assert (
        checks.g7_equity_velocity(_state(equity_now=70.0, equity_dt_s=600.0)).level
        is GuardLevel.GREEN
    )


def test_g8_order_frequency_fail_closed_and_burst() -> None:
    assert checks.g8_order_frequency(_state(order_baseline=0.0)).level is GuardLevel.RED
    assert checks.g8_order_frequency(_state(order_baseline=-1.0)).level is GuardLevel.RED
    assert (
        checks.g8_order_frequency(_state(orders_in_window=10, order_baseline=1.0)).level
        is GuardLevel.ORANGE
    )
    assert (
        checks.g8_order_frequency(_state(orders_in_window=2, order_baseline=1.0)).level
        is GuardLevel.GREEN
    )


def test_g9_correlation_spike_is_advisory() -> None:
    hot = checks.g9_correlation_spike(_state(exposures=(1.0, 2.0, 0.5)))
    assert hot.level is GuardLevel.ORANGE and hot.gates_orders is False
    assert checks.g9_correlation_spike(_state(exposures=(1.0, -1.0))).level is GuardLevel.GREEN
    assert checks.g9_correlation_spike(_state(exposures=(1.0,))).level is GuardLevel.GREEN


def test_g10_prompt_injection_is_advisory() -> None:
    hot = checks.g10_prompt_injection(_state(injection_flags_24h=11))
    assert hot.level is GuardLevel.ORANGE and hot.gates_orders is False
    assert checks.g10_prompt_injection(_state(injection_flags_24h=5)).level is GuardLevel.GREEN


def test_derived_guards_can_never_gate_an_order_teeth() -> None:
    # TEETH (§4.3): G5/G9/G10 results must ALWAYS have gates_orders=False, no matter the input.
    advisory = {"G5_llm_heartbeat", "G9_correlation_spike", "G10_prompt_injection"}
    s = _state(now_epoch=99999.0, exposures=(1.0, 1.0), injection_flags_24h=99)
    for check in STATE_CHECKS:
        r = check(s)
        if r.guard_id in advisory:
            assert r.gates_orders is False, f"{r.guard_id} must never gate an order"
        else:
            assert r.gates_orders is True, f"{r.guard_id} must gate orders"
    # and the gating subset never contains an advisory guard id
    gating_ids = {check(s).guard_id for check in STATE_CHECKS if check(s).gates_orders}
    assert gating_ids.isdisjoint(advisory)
