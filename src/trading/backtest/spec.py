"""``StrategySpec`` — the FROZEN, hashable strategy definition (ADR §7 strategy-as-composition).

A strategy COMBINES registered factor signals into a target position; it owns no look-ahead. The
spec references ONLY ``factor_id``s and a fixed ``CompositionRule`` in the factor's already-z-scored
``[-3, 3]`` space, so there is structurally NO field for a hand-coded threshold (``extra='forbid'``
rejects any smuggled ``threshold``/``level``/``cutoff`` key). The frozen pydantic-v2 idiom of
``executor/intent.py`` (``ConfigDict(frozen=True, extra='forbid')``, NFKC-canonical names).

``spec_hash`` is a deterministic SHA-256 over canonical JSON of the FULL field set, using the
``trial_ledger._canonical`` idiom (``sort_keys``, compact separators, NO ``default=str``) with float
weights serialized losslessly via ``float.hex()`` (the ``idempotency`` idiom). A 1e-9 weight change
yields a new hash and a forced Inc-5 re-gate (ADR §7). ``canonical_params()`` returns a fully
JSON-NATIVE dict (every float already a hex string), so the trial ledger re-serializes the SAME
bytes; that byte-identity is the M18 under-count defense (``spec_hash`` and combo_hash are driven by
identical canonical JSON; see ``ledger_integration``).

Phase 1 here is registry-FREE shape validation; Phase 2 (``resolve_spec``) binds the registry as a
separate step. Regime-label references are deferred to Increment 6.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_NAME_RE = re.compile(r"^[a-z0-9_]{1,64}$")
_FACTOR_ID_RE = re.compile(r"^[a-z0-9_]{1,64}$")


def _strip_format_chars(value: str) -> str:
    """NFKC-normalize and remove Unicode format/invisible characters (category Cf)."""
    normalized = unicodedata.normalize("NFKC", value)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Cf")


class Direction(StrEnum):
    """A leg's exposure sign (mirrors ``executor.intent.Side``)."""

    LONG = "long"
    SHORT = "short"


class CompositionRule(StrEnum):
    """How legs combine into a composite signal. Start with ONE; a new rule is a counted trial."""

    #: composite = sum_i (signed_weight_i * factor_i_z); a commutative weighted sum in z-space.
    Z_WEIGHTED_SUM = "z_weighted_sum"


class FactorLeg(BaseModel):
    """One factor's contribution to a strategy: a registered ``factor_id``, a magnitude, a sign."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    factor_id: str = Field(min_length=1)
    #: Magnitude in (0, 1]; the SIGN is carried by ``direction`` (no double-sign ambiguity).
    weight: float = Field(gt=0.0, le=1.0, allow_inf_nan=False)
    direction: Direction = Direction.LONG

    @field_validator("factor_id", mode="after")
    @classmethod
    def _check_factor_id(cls, value: str) -> str:
        if not _FACTOR_ID_RE.match(value):
            raise ValueError(f"invalid factor_id {value!r} (must match {_FACTOR_ID_RE.pattern})")
        return value

    @property
    def signed_weight(self) -> float:
        """The directed weight: ``+weight`` for LONG, ``-weight`` for SHORT."""
        return self.weight if self.direction is Direction.LONG else -self.weight


class StrategySpec(BaseModel):
    """A frozen, hashable strategy: a composition of registered factor legs in z-space."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    legs: tuple[FactorLeg, ...]
    rule: CompositionRule = CompositionRule.Z_WEIGHTED_SUM
    composite_scale: float = Field(default=1.0, gt=0.0, allow_inf_nan=False)
    spec_version: int = Field(default=1, ge=1)
    #: The cost-model version this spec is bound to (folded into ``spec_hash`` so a cost change is a
    #: new trial). ``run`` asserts the supplied ``CostModel.cost_model_id`` matches (fail-closed).
    cost_model_id: str = Field(default="conservative_v1", min_length=1)

    @field_validator("name", mode="after")
    @classmethod
    def _canon_name(cls, value: str) -> str:
        canonical = _strip_format_chars(value).strip().casefold()
        if not _NAME_RE.match(canonical):
            raise ValueError(f"invalid strategy name {value!r} (canonical {canonical!r})")
        return canonical

    @model_validator(mode="after")
    def _check_legs(self) -> StrategySpec:
        if not self.legs:
            raise ValueError("StrategySpec requires at least one leg")
        ids = [leg.factor_id for leg in self.legs]
        if len(set(ids)) != len(ids):
            raise ValueError(f"duplicate factor_id in legs: {ids}")
        return self

    def canonical_params(self) -> dict[str, Any]:
        """The lossless, JSON-NATIVE canonical representation (floats as ``float.hex()`` strings).

        Legs are sorted by ``factor_id`` so a commutative ``Z_WEIGHTED_SUM`` reorder is the SAME
        trial (no ``n_trials`` inflation from reordering). Every value is str/int/list/dict, so any
        canonical ``json.dumps(sort_keys, separators)`` of this dict is byte-identical regardless of
        who serializes it, which is what makes ``spec_hash`` and the ledger ``combo_hash`` agree.
        """
        return {
            "name": self.name,
            "rule": self.rule.value,
            "composite_scale": self.composite_scale.hex(),
            "spec_version": self.spec_version,
            "cost_model_id": self.cost_model_id,
            "legs": [
                {
                    "factor_id": leg.factor_id,
                    "weight": leg.weight.hex(),
                    "direction": leg.direction.value,
                }
                for leg in sorted(self.legs, key=lambda lg: lg.factor_id)
            ],
        }

    @property
    def spec_hash(self) -> str:
        """Deterministic identity over the FULL field set; any change → a new hash (ADR §7)."""
        payload = json.dumps(self.canonical_params(), sort_keys=True, separators=(",", ":"))
        return "arcane-strategy-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:40]
