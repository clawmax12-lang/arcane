"""Startup preflight — refuse to trade unless the safety substrate is healthy.

Any entrypoint that runs the executor MUST call ``preflight`` before starting the loop.
It verifies the kill-switch state store is writable (a kill switch we cannot escalate to
disk is not a kill switch — red-team residual) and asserts the paper-only handoff
invariant. Failure aborts startup rather than trading in a degraded state.
"""

from __future__ import annotations

from trading.executor.kill_switch import KillSwitch
from trading.executor.live_mode import assert_paper_for_handoff


def preflight(kill_switch: KillSwitch, config_live_mode: bool) -> None:
    """Verify the safety substrate or raise. Call before any trading loop starts.

    Raises:
        KillSwitchUnwritableError: the kill-switch state store is not writable.
        AssertionError: a LIVE_MODE flag is set (paper-only handoff invariant violated).
    """
    kill_switch.verify_writable()
    assert_paper_for_handoff(config_live_mode)
