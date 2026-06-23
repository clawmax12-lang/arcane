"""Tripwire A4 — the T2 survivorship test (fails CLOSED while no PIT verifier is wired).

ADR §8: while survivorship is unverified, T2 must return ``passed=False`` with a reason, not a false
pass. The ``BacktestResult.survivorship_*`` flags are SELF-ATTESTED — a caller can construct
``SymbolPanel(survivorship_unverified=False)`` (a bare, forgeable kwarg) and flip T2 to a pass
(red-team FC-1, the cardinal sin). So T2 does NOT trust the bare flags: while no PIT-universe
verifier is wired (``_PIT_VERIFIER_WIRED`` — Polygon deferred), survivorship is
UNVERIFIABLE by any code path, and T2 fails CLOSED UNCONDITIONALLY regardless of the flags. When a
real PIT verifier is wired (a future increment), T2 falls back to requiring BOTH flags ``False``.
The flags are reported in the reason for auditability but cannot, alone, grant a pass.
"""

from __future__ import annotations

from typing import Final

from trading.backtest.statistics import BacktestResult
from trading.bias_gate.verdict import GateComponent

_NAME = "T2_survivorship"

#: No PIT-universe verifier (Polygon) is wired yet, so survivorship cannot be VERIFIED by any
#: shipped code path. A self-attested ``survivorship_unverified=False`` is therefore untrustworthy
#: T2 fails closed unconditionally. Flip to True only when a real PIT provenance check is wired.
_PIT_VERIFIER_WIRED: Final[bool] = False


def t2_survivorship(result: BacktestResult) -> GateComponent:
    """Pass ONLY with a wired PIT verifier AND both flags False; else fail closed (ADR §8)."""
    if not _PIT_VERIFIER_WIRED or result.survivorship_biased or result.survivorship_unverified:
        return GateComponent(
            name=_NAME,
            passed=False,
            reason=(
                "survivorship NOT verifiable — no PIT verifier is wired (Polygon deferred); "
                f"a self-attested flag (biased={result.survivorship_biased}, "
                f"unverified={result.survivorship_unverified}) cannot grant a pass; fail closed"
            ),
        )
    return GateComponent(name=_NAME, passed=True, reason="PIT-verified survivorship")
