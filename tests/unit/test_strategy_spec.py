"""Tests for the frozen StrategySpec + spec_hash — Increment 4 cluster 2.

Proves: frozen + extra='forbid' (a smuggled threshold/level key is rejected; ADR §7 has no field for
a hand-coded threshold); leg shape (non-empty, unique ids, weight magnitude in (0,1], finite);
name NFKC canonicalization (the intent.py idiom); and a LOSSLESS, deterministic spec_hash over
canonical JSON with float weights via float.hex(). A 1e-9 weight change yields a different hash (no
precision collision), the same spec yields an identical hash across fresh constructions, and
canonical_params() is JSON-native (no raw floats) so the ledger re-serializes the SAME bytes (the C7
spec_hash == combo_hash basis; the M18 under-count defense).
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from trading.backtest.spec import (
    CompositionRule,
    Direction,
    FactorLeg,
    StrategySpec,
)


def _spec(**over: object) -> StrategySpec:
    base: dict[str, object] = {
        "name": "ts_momentum_blend",
        "legs": (
            FactorLeg(factor_id="mom_21d", weight=0.34, direction=Direction.LONG),
            FactorLeg(factor_id="mom_63d", weight=0.33, direction=Direction.LONG),
        ),
        "rule": CompositionRule.Z_WEIGHTED_SUM,
        "composite_scale": 1.0,
        "spec_version": 1,
        "cost_model_id": "conservative_v1",
    }
    base.update(over)
    return StrategySpec(**base)  # type: ignore[arg-type]


# --- shape / frozen / extra=forbid ---


def test_valid_spec_constructs() -> None:
    s = _spec()
    assert s.name == "ts_momentum_blend"
    assert len(s.legs) == 2
    assert s.rule is CompositionRule.Z_WEIGHTED_SUM


def test_spec_is_frozen() -> None:
    s = _spec()
    with pytest.raises(ValidationError):
        s.composite_scale = 2.0  # type: ignore[misc]


def test_spec_rejects_a_smuggled_threshold_key() -> None:
    # ADR §7: structurally NO threshold field; extra='forbid' rejects any smuggled cutoff/level.
    with pytest.raises(ValidationError):
        _spec(threshold=30.0)
    with pytest.raises(ValidationError):
        _spec(rsi_level=70)


def test_leg_is_frozen_and_forbids_extra() -> None:
    leg = FactorLeg(factor_id="mom_21d", weight=0.5, direction=Direction.SHORT)
    with pytest.raises(ValidationError):
        leg.weight = 0.6  # type: ignore[misc]
    smuggled = {"factor_id": "mom_21d", "weight": 0.5, "direction": Direction.LONG, "cutoff": 1.0}
    with pytest.raises(ValidationError):
        FactorLeg(**smuggled)  # type: ignore[arg-type]


# --- leg weight: positive magnitude in (0, 1], finite ---


@pytest.mark.parametrize("bad", [0.0, -0.4, 1.5, float("inf"), float("nan")])
def test_leg_weight_must_be_finite_magnitude_in_unit_interval(bad: float) -> None:
    with pytest.raises(ValidationError):
        FactorLeg(factor_id="mom_21d", weight=bad, direction=Direction.LONG)


def test_leg_signed_weight_applies_direction() -> None:
    assert FactorLeg(
        factor_id="x", weight=0.4, direction=Direction.LONG
    ).signed_weight == pytest.approx(0.4)
    assert FactorLeg(
        factor_id="x", weight=0.4, direction=Direction.SHORT
    ).signed_weight == pytest.approx(-0.4)


def test_leg_factor_id_pattern() -> None:
    # uppercase/dash banned
    with pytest.raises(ValidationError):
        FactorLeg(factor_id="MOM-21D", weight=0.5, direction=Direction.LONG)


# --- spec-level legs validation ---


def test_empty_legs_rejected() -> None:
    with pytest.raises(ValidationError):
        _spec(legs=())


def test_duplicate_factor_ids_rejected() -> None:
    with pytest.raises(ValidationError):
        _spec(
            legs=(
                FactorLeg(factor_id="mom_21d", weight=0.5, direction=Direction.LONG),
                FactorLeg(factor_id="mom_21d", weight=0.5, direction=Direction.SHORT),
            )
        )


def test_composite_scale_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        _spec(composite_scale=0.0)
    with pytest.raises(ValidationError):
        _spec(composite_scale=-1.0)


def test_name_is_nfkc_canonicalized() -> None:
    # uppercase -> casefold; the intent.py canonicalization idiom.
    assert _spec(name="TS_Momentum_Blend").name == "ts_momentum_blend"
    with pytest.raises(ValidationError):
        _spec(name="bad name!")  # space + punctuation rejected


# --- spec_hash: lossless, deterministic, covariant ---


def test_spec_hash_is_deterministic_across_fresh_constructions() -> None:
    assert _spec().spec_hash == _spec().spec_hash
    assert _spec().spec_hash.startswith("arcane-strategy-")


def test_spec_hash_distinguishes_a_1e9_weight_change() -> None:
    a = _spec()
    b = _spec(
        legs=(
            FactorLeg(factor_id="mom_21d", weight=0.34 + 1e-9, direction=Direction.LONG),
            FactorLeg(factor_id="mom_63d", weight=0.33, direction=Direction.LONG),
        )
    )
    assert a.spec_hash != b.spec_hash  # float.hex() is lossless — no precision collision


@pytest.mark.parametrize(
    "field,value",
    [
        ("rule", CompositionRule.Z_WEIGHTED_SUM),  # same -> same (sanity sentinel handled below)
        ("composite_scale", 2.0),
        ("spec_version", 2),
        ("cost_model_id", "conservative_v2"),
    ],
)
def test_spec_hash_changes_when_a_field_changes(field: str, value: object) -> None:
    base = _spec()
    changed = _spec(**{field: value})
    if field == "rule":
        assert base.spec_hash == changed.spec_hash  # identical rule -> identical hash
    else:
        assert base.spec_hash != changed.spec_hash


def test_spec_hash_changes_when_direction_flips() -> None:
    base = _spec()
    flipped = _spec(
        legs=(
            FactorLeg(factor_id="mom_21d", weight=0.34, direction=Direction.SHORT),
            FactorLeg(factor_id="mom_63d", weight=0.33, direction=Direction.LONG),
        )
    )
    assert base.spec_hash != flipped.spec_hash


def test_canonical_params_is_json_native_and_order_independent() -> None:
    s = _spec()
    params = s.canonical_params()
    # JSON-native: re-serializing never raises and has NO raw float (weights are hex strings) — this
    # is what lets the ledger re-serialize the SAME bytes (C7 byte-identity).
    dumped = json.dumps(params, sort_keys=True, separators=(",", ":"))
    assert "0x" in dumped  # float.hex() form present
    # leg order is canonicalized (sorted by factor_id) so a commutative Z_WEIGHTED_SUM reorder is
    # the SAME trial (avoids n_trials inflation from cosmetic reordering).
    reordered = _spec(
        legs=(
            FactorLeg(factor_id="mom_63d", weight=0.33, direction=Direction.LONG),
            FactorLeg(factor_id="mom_21d", weight=0.34, direction=Direction.LONG),
        )
    )
    assert s.spec_hash == reordered.spec_hash
