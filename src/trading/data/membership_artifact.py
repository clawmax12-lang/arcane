"""Point-in-time membership artifact + its content-addressed hash (Increment 6 PART A).

The ``MembershipArtifact`` is the unforgeable record of which symbols were point-in-time ACTIVE at
an ``as_of`` (with their delist boundaries), produced by ``PolygonPITUniverse`` from a real Polygon
PIT query. The bias-gate T2 verifier binds against it BY HASH: to forge a survivorship pass you
would have to produce a Polygon-shaped artifact that covers every traded symbol's window AND whose
canonical bytes hash to the value already sealed on the result — i.e. actually do the PIT
reconstruction.

These types live in the DATA layer (not ``bias_gate``) so the producer (``polygon_universe.py``)
and the consumer (``bias_gate/tests_t2.py``) share them without an import cycle — ``bias_gate``
already depends on ``data``, never the reverse.

Hashing is canonical: members sorted by symbol, ``sort_keys`` + compact separators, datetimes as
ISO-8601. The hash is order-independent and changes on ANY single-field edit (drop a symbol, move a
delist date, change the vintage) — exactly the tampering a survivorship attack would attempt.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from trading.data.errors import ProvenanceBindingError
from trading.data.universe import SourceTier, UniverseSnapshot, is_pit


@dataclass(frozen=True, slots=True)
class SymbolMembership:
    """One symbol's PIT membership record at the artifact's ``as_of`` date.

    ``active`` is whether the symbol was tradable AT ``as_of``. ``delisted_utc`` is ``None`` (or
    after the backtest window end) ⇒ the membership interval stays open through the window; a value
    inside the window means the symbol delisted mid-window (a survivorship hazard T2 must catch).
    """

    symbol: str
    active: bool
    listed_utc: datetime | None
    delisted_utc: datetime | None


@dataclass(frozen=True, slots=True)
class MembershipArtifact:
    """A sealed, content-addressed point-in-time membership set for one ``as_of``."""

    schema_version: int
    source_tier: SourceTier  # the producing tier — T2 requires POLYGON_PIT
    as_of: datetime
    vintage: datetime  # reconstruction date (== as_of for a single-as_of artifact)
    members: tuple[SymbolMembership, ...]

    def member_for(self, symbol: str) -> SymbolMembership | None:
        for m in self.members:
            if m.symbol == symbol:
                return m
        return None


_BIND_MINT = object()  # module-private sentinel — the only key that opens the constructor


class ProvenanceBinding:
    """The hash-bind passed ALONGSIDE a ``BacktestResult`` to T2 — the UNFORGEABLE pass key.

    Constructible ONLY via ``provenance_binding_from`` (the ``_BIND_MINT`` token gate), which
    derives
    the ``membership_artifact_hash`` from a real ``POLYGON_PIT`` ``UniverseSnapshot`` (whose
    ``universe_hash`` is owned by the ``@final`` base from the class tier — not author-declarable).
    A caller therefore cannot hand-build a binding carrying a forged hash; T2's artifact must
    hash to
    this real value, so a fabricated artifact can never pass (red-team D1 — the FC-1 cardinal sin).
    ``traded_symbols`` / window come from the panel the engine actually ran (the gate cross-checks).
    """

    __slots__ = (
        "membership_artifact_hash",
        "traded_symbols",
        "window_start",
        "window_end",
        "as_of",
    )

    membership_artifact_hash: str
    traded_symbols: tuple[str, ...]  # == sorted(panel.bars.keys())
    window_start: datetime  # == panel index min
    window_end: datetime  # == panel index max
    as_of: datetime

    def __init__(
        self,
        *,
        membership_artifact_hash: str,
        traded_symbols: tuple[str, ...],
        window_start: datetime,
        window_end: datetime,
        as_of: datetime,
        _token: object,
    ) -> None:
        if _token is not _BIND_MINT:
            raise ProvenanceBindingError(
                "ProvenanceBinding is constructible only via provenance_binding_from"
            )
        object.__setattr__(self, "membership_artifact_hash", membership_artifact_hash)
        object.__setattr__(self, "traded_symbols", traded_symbols)
        object.__setattr__(self, "window_start", window_start)
        object.__setattr__(self, "window_end", window_end)
        object.__setattr__(self, "as_of", as_of)

    def __setattr__(self, name: str, value: object) -> None:  # frozen
        raise AttributeError("ProvenanceBinding is immutable")

    def __repr__(self) -> str:
        return (
            f"ProvenanceBinding(hash={self.membership_artifact_hash!r}, "
            f"traded_symbols={self.traded_symbols!r})"
        )


def provenance_binding_from(
    snapshot: UniverseSnapshot,
    *,
    traded_symbols: tuple[str, ...],
    window_start: datetime,
    window_end: datetime,
) -> ProvenanceBinding:
    """Mint the unforgeable T2 binding from a real POLYGON_PIT snapshot + the engine's panel facts.

    The hash is taken from ``snapshot.meta.universe_hash`` (base-owned, from a real Polygon fetch) —
    NEVER a caller-supplied string. A non-PIT snapshot is refused (only a survivorship-clean source
    can produce a binding). ``traded_symbols`` is sorted; the gate verifies it equals the real
    panel.
    """
    if snapshot.meta.source_tier != SourceTier.POLYGON_PIT or not is_pit(snapshot.meta.source_tier):
        raise ProvenanceBindingError(
            f"ProvenanceBinding requires a POLYGON_PIT snapshot, got {snapshot.meta.source_tier}"
        )
    if not traded_symbols:
        raise ProvenanceBindingError("ProvenanceBinding requires at least one traded symbol")
    return ProvenanceBinding(
        membership_artifact_hash=snapshot.meta.universe_hash,
        traded_symbols=tuple(sorted(traded_symbols)),
        window_start=window_start,
        window_end=window_end,
        as_of=snapshot.meta.as_of,
        _token=_BIND_MINT,
    )


def _canonical(artifact: MembershipArtifact) -> Mapping[str, Any]:
    """Deterministic, order-independent representation (members sorted by symbol)."""
    return {
        "schema_version": artifact.schema_version,
        "source_tier": str(artifact.source_tier.value),
        "as_of": artifact.as_of.isoformat(),
        "vintage": artifact.vintage.isoformat(),
        "members": [
            {
                "symbol": m.symbol,
                "active": m.active,
                "listed_utc": m.listed_utc.isoformat() if m.listed_utc is not None else None,
                "delisted_utc": (
                    m.delisted_utc.isoformat() if m.delisted_utc is not None else None
                ),
            }
            for m in sorted(artifact.members, key=lambda m: m.symbol)
        ],
    }


def membership_artifact_hash(artifact: MembershipArtifact) -> str:
    """Content hash over the canonical bytes (sorted members, compact JSON, ISO datetimes)."""
    payload = json.dumps(_canonical(artifact), sort_keys=True, separators=(",", ":"))
    return "arcane-univ-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def artifact_to_json(artifact: MembershipArtifact) -> str:
    """Serialize to the canonical JSON used for hashing — a sealed artifact round-trips
    losslessly."""
    return json.dumps(_canonical(artifact), sort_keys=True, separators=(",", ":"))


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


def artifact_from_json(text: str) -> MembershipArtifact:
    """Parse a sealed artifact back from its canonical JSON (raises on malformed input)."""
    data = json.loads(text)
    members = tuple(
        SymbolMembership(
            symbol=str(m["symbol"]),
            active=bool(m["active"]),
            listed_utc=_parse_dt(m.get("listed_utc")),
            delisted_utc=_parse_dt(m.get("delisted_utc")),
        )
        for m in data["members"]
    )
    return MembershipArtifact(
        schema_version=int(data["schema_version"]),
        source_tier=SourceTier(data["source_tier"]),
        as_of=datetime.fromisoformat(data["as_of"]),
        vintage=datetime.fromisoformat(data["vintage"]),
        members=members,
    )
