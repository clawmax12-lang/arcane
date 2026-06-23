"""C9 — AllocationGrant: an order can be minted ONLY for a genuinely-allocated strategy (Inc-6
PART C).

Closes the type-confusion CRITICAL: ``bias_gate.verdict.GateDecision`` is hand-constructable
(``allocated=True, components=()``), so ``from_decision`` does NOT trust ``allocated`` — it
re-runs the
ALL-of (every frozen component present AND passed, T2 among them, non-blank spec_hash). A killed or
half-built decision raises ``AllocationDenied`` BEFORE any OrderIntent can exist.
"""

from __future__ import annotations

import pytest

from trading.bias_gate.gate import FROZEN_COMPONENT_NAMES, GateComponent, GateDecision
from trading.executor.grant import AllocationDenied, AllocationGrant

_UHASH = "arcane-univ-deadbeef"


def _decision(
    *,
    allocated: bool = True,
    components: tuple[GateComponent, ...] | None = None,
    spec_hash: str = "arcane-strategy-x",
) -> GateDecision:
    if components is None:
        components = tuple(GateComponent(n, True, "") for n in FROZEN_COMPONENT_NAMES)
    reasons = tuple(c.reason for c in components if not c.passed)
    return GateDecision(spec_hash, allocated, components, n_trials=17, reasons=reasons)


def test_mints_for_a_fully_allocated_decision() -> None:
    grant = AllocationGrant.from_decision(_decision(), universe_artifact_hash=_UHASH)
    assert grant.spec_hash == "arcane-strategy-x"
    assert grant.universe_artifact_hash == _UHASH
    assert grant.n_trials == 17
    assert grant.decision_id  # a stable replay key


def test_denies_a_killed_decision() -> None:
    with pytest.raises(AllocationDenied):
        AllocationGrant.from_decision(_decision(allocated=False), universe_artifact_hash=_UHASH)


def test_denies_allocated_true_with_a_failing_component() -> None:
    comps = list(GateComponent(n, True, "") for n in FROZEN_COMPONENT_NAMES)
    comps[1] = GateComponent(
        comps[1].name, False, "T2 failed"
    )  # T2 not passed, but allocated forged
    with pytest.raises(AllocationDenied):
        AllocationGrant.from_decision(
            _decision(allocated=True, components=tuple(comps)), universe_artifact_hash=_UHASH
        )


def test_denies_empty_components_even_if_allocated_true() -> None:
    with pytest.raises(AllocationDenied):
        AllocationGrant.from_decision(
            _decision(allocated=True, components=()), universe_artifact_hash=_UHASH
        )


def test_denies_missing_required_component() -> None:
    # all-but-one of the frozen components, every one passed, allocated forged True -> still denied
    partial = tuple(GateComponent(n, True, "") for n in FROZEN_COMPONENT_NAMES[:-1])
    with pytest.raises(AllocationDenied):
        AllocationGrant.from_decision(
            _decision(allocated=True, components=partial), universe_artifact_hash=_UHASH
        )


def test_denies_missing_t2_specifically() -> None:
    without_t2 = tuple(
        GateComponent(n, True, "") for n in FROZEN_COMPONENT_NAMES if n != "T2_survivorship"
    ) + (
        GateComponent("EXTRA_filler", True, ""),
    )
    with pytest.raises(AllocationDenied):
        AllocationGrant.from_decision(
            _decision(allocated=True, components=without_t2), universe_artifact_hash=_UHASH
        )


def test_denies_blank_spec_hash() -> None:
    with pytest.raises(AllocationDenied):
        AllocationGrant.from_decision(_decision(spec_hash=""), universe_artifact_hash=_UHASH)


def test_direct_construction_without_mint_token_is_denied() -> None:
    with pytest.raises(AllocationDenied):
        AllocationGrant(
            spec_hash="x",
            universe_artifact_hash=_UHASH,
            n_trials=1,
            decision_id="d",
            _token=object(),
        )


def test_grant_is_immutable() -> None:
    grant = AllocationGrant.from_decision(_decision(), universe_artifact_hash=_UHASH)
    with pytest.raises(AttributeError):
        grant.spec_hash = "y"  # type: ignore[misc]


def test_gatedecision_has_no_deserialization_path() -> None:
    # red-team D3: from_decision is a STRUCTURAL re-check of trusted in-process gate output. That is
    # safe ONLY while GateDecision is never deserialized from untrusted bytes — pin that here.
    from trading.bias_gate.verdict import GateDecision as BiasGateDecision

    for attr in ("from_json", "from_dict", "load", "loads", "parse_raw", "model_validate"):
        assert not hasattr(
            BiasGateDecision, attr
        ), f"GateDecision.{attr} would turn from_decision into a deserialization sink (D3)"


def test_decision_id_is_stable_and_binds_identity() -> None:
    d = _decision()
    g1 = AllocationGrant.from_decision(d, universe_artifact_hash=_UHASH)
    g2 = AllocationGrant.from_decision(d, universe_artifact_hash=_UHASH)
    assert g1.decision_id == g2.decision_id
    # a different strategy yields a different decision id (non-replayable)
    other = AllocationGrant.from_decision(
        _decision(spec_hash="arcane-strategy-y"), universe_artifact_hash=_UHASH
    )
    assert other.decision_id != g1.decision_id
