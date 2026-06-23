"""T2 survivorship — the UNFORGEABLE point-in-time membership check (Increment 6 PART A).

History: T2 was once flippable to PASS via a self-attested
``SymbolPanel(survivorship_unverified=False)`` bare kwarg → full ALLOCATE (red-team FC-1, the
cardinal sin). Increment 5 made it fail CLOSED behind a module-global ``_PIT_VERIFIER_WIRED`` bool;
but flipping that bool would have FALLEN BACK to the same self-attested flags, re-opening FC-1.
Increment 6 DELETES the bool-only path entirely.

T2 now passes ONLY when a real, content-addressed ``MembershipArtifact`` (sourced from Polygon PIT
reference data) is bound to the result BY HASH and COVERS every backtested symbol across the whole
backtest window. To forge a pass you would have to produce a Polygon-shaped artifact whose canonical
bytes hash to the value already bound AND that lists every traded symbol as PIT-active across the
window — i.e. actually do the survivorship-correct reconstruction. The old self-attested flags
survive ONLY as an AND-ed, advisory extra wall (strictly stricter, never the grant). Missing
binding/artifact, a hash mismatch, a wrong tier, a future vintage, a dropped symbol, or ANY
exception → ``passed=False``.
"""

from __future__ import annotations

from datetime import datetime

from trading.backtest.statistics import BacktestResult
from trading.bias_gate.verdict import GateComponent
from trading.data.membership_artifact import (
    MembershipArtifact,
    ProvenanceBinding,
    SymbolMembership,
    membership_artifact_hash,
)
from trading.data.universe import SourceTier, is_pit

_NAME = "T2_survivorship"


def _covers_window(member: SymbolMembership, window_start: datetime, window_end: datetime) -> bool:
    """A symbol covers the window iff it was PIT-active across ALL of [window_start, window_end].

    Conservative v1 semantics: a name that delisted mid-window (or listed after the window opened)
    is NOT eligible for that window — this is exactly the survivorship distinction a flat watchlist
    gets wrong. ``listed_utc``/``delisted_utc`` may be None (interval open on that side).
    """
    if member.active is not True:
        return False
    # delisted within/at the window end ⇒ not active across the whole window
    delisted_in_window = member.delisted_utc is not None and member.delisted_utc <= window_end
    # listed after the window opened ⇒ not active at window start
    listed_after_start = member.listed_utc is not None and member.listed_utc > window_start
    return not (delisted_in_window or listed_after_start)


def t2_survivorship(
    result: BacktestResult,
    binding: ProvenanceBinding | None = None,
    artifact: MembershipArtifact | None = None,
) -> GateComponent:
    """Pass ONLY with a hash-bound, window-covering POLYGON_PIT artifact; else fail CLOSED.

    Any missing input, mismatch, or exception fails closed with a recorded reason (auditability).
    """
    if binding is None or artifact is None:
        return GateComponent(
            name=_NAME,
            passed=False,
            reason=(
                "survivorship NOT verifiable — no PIT membership artifact is bound to this result; "
                "fail closed (a self-attested flag can never grant a pass)"
            ),
        )
    if not binding.traded_symbols:
        # red-team D5: nothing-to-verify must NOT be a PASS (fail closed on ambiguity).
        return GateComponent(
            name=_NAME,
            passed=False,
            reason="no traded symbols to verify survivorship over — fail closed",
        )
    try:
        tier_ok = artifact.source_tier == SourceTier.POLYGON_PIT and is_pit(artifact.source_tier)
        hash_ok = membership_artifact_hash(artifact) == binding.membership_artifact_hash
        # No future knowledge (vintage/as_of ≤ backtest clock) AND the snapshot is taken at/after
        # the window end so every in-window delisting is visible to the membership.
        vintage_ok = (
            artifact.vintage <= binding.as_of
            and artifact.as_of <= binding.as_of
            and artifact.as_of >= binding.window_end
        )
        missing = [s for s in binding.traded_symbols if artifact.member_for(s) is None]
        no_missing = not missing
        uncovered = [
            s
            for s in binding.traded_symbols
            if (m := artifact.member_for(s)) is not None
            and not _covers_window(m, binding.window_start, binding.window_end)
        ]
        coverage_ok = not uncovered
        # Self-attested flags are AND-ed in as a strictly-stricter advisory wall, never the grant.
        flags_ok = (not result.survivorship_biased) and (not result.survivorship_unverified)

        passed = bool(
            tier_ok and hash_ok and vintage_ok and no_missing and coverage_ok and flags_ok
        )
        if passed:
            ws = binding.window_start.isoformat()[:10]
            we = binding.window_end.isoformat()[:10]
            return GateComponent(
                name=_NAME,
                passed=True,
                reason=(
                    f"PIT-verified survivorship: {len(binding.traded_symbols)} symbols "
                    f"active across [{ws}, {we}] (artifact {binding.membership_artifact_hash[:16]})"
                ),
            )
        reasons = []
        if not tier_ok:
            reasons.append(f"source tier {artifact.source_tier} is not POLYGON_PIT")
        if not hash_ok:
            reasons.append("membership artifact hash does not match the bound hash")
        if not vintage_ok:
            reasons.append("artifact vintage/as_of out of bounds vs the backtest window/clock")
        if not no_missing:
            reasons.append(f"traded symbols missing from the PIT membership: {sorted(missing)}")
        if not coverage_ok:
            reasons.append(f"symbols not PIT-active across the whole window: {sorted(uncovered)}")
        if not flags_ok:
            reasons.append("result self-attests survivorship-biased/unverified")
        return GateComponent(name=_NAME, passed=False, reason="; ".join(reasons))
    except Exception as exc:  # fail closed on ANY malformed artifact/binding
        return GateComponent(
            name=_NAME,
            passed=False,
            reason=f"survivorship verification failed closed: {type(exc).__name__}: {exc}",
        )
