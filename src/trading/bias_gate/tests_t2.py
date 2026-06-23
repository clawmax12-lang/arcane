"""Tripwire A4 — the T2 survivorship test (fails CLOSED while the universe is unverified).

ADR §8: while survivorship is unverified, T2 must return ``passed=False`` with a reason, not a false
pass. Polygon (the PIT-universe verifier) is deferred, so this run is ALWAYS degraded and T2
ALWAYS contributes a KILL. T2 passes ONLY when BOTH result flags are ``False`` — there is no
default-True else-branch that could leak a clean pass.
"""

from __future__ import annotations

from trading.backtest.statistics import BacktestResult
from trading.bias_gate.verdict import GateComponent

_NAME = "T2_survivorship"


def t2_survivorship(result: BacktestResult) -> GateComponent:
    """Pass ONLY when both survivorship flags are False; else fail closed with a reason."""
    if result.survivorship_biased or result.survivorship_unverified:
        return GateComponent(
            name=_NAME,
            passed=False,
            reason=(
                f"survivorship unverified (biased={result.survivorship_biased}, "
                f"unverified={result.survivorship_unverified}); PIT universe deferred "
                "— fail closed (ADR §8)"
            ),
        )
    return GateComponent(name=_NAME, passed=True, reason="PIT-verified survivorship")
