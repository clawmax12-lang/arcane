"""Concrete universe sources (Increment 2 STEP 7).

Only ``OperatorFileUniverse`` ships today: an operator-curated, content-hashed watchlist that is
deterministic (same bytes → same ``universe_hash``), reproducible, and HONEST about being non-PIT —
the opposite of a hardcoded code literal or a moving vendor snapshot. ``AlpacaTodayUniverse``
(``get_all_assets``) and ``PolygonUniverse`` (real PIT) are deliberately deferred (see
``docs/INC2-HARDENING-BACKLOG.md``); both would still be NON-PIT / fail T2 except a real Polygon
source carrying per-(symbol,date) membership intervals.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import ClassVar, Final

import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from trading.data.errors import UniverseConfigError
from trading.data.pit import AsOf
from trading.data.universe import PITUniverse, SourceTier

logger = logging.getLogger(__name__)

# Repo-root config (…/Trade/config/universe.yaml); resolved here, never read from a global.
_DEFAULT_CONFIG: Final[Path] = Path(__file__).resolve().parents[3] / "config" / "universe.yaml"


class UniverseFileModel(BaseModel):
    """Frozen, fail-closed schema for ``config/universe.yaml`` (mirrors ``RiskConfig``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbols: list[str]


class OperatorFileUniverse(PITUniverse):
    """The wired default: an operator-curated, content-hashed watchlist. Honest NON-PIT (DEGRADED).

    Membership does NOT vary with ``as_of`` (the file has no per-date intervals) — and THAT is
    exactly why it is non-PIT and T2 fails closed. The base re-derives the survivorship verdict from
    ``SOURCE_TIER``; this class cannot mint a clean verdict.
    """

    SOURCE_TIER: ClassVar[SourceTier] = SourceTier.OPERATOR_FILE

    def __init__(self, *, config_path: Path | None = None) -> None:
        self._path = config_path or _DEFAULT_CONFIG

    def _members(self, as_of: AsOf, session: pd.Timestamp) -> tuple[frozenset[str], str]:
        try:
            raw_bytes = self._path.read_bytes()
        except OSError as exc:
            logger.warning("universe.refused error=UniverseConfigError path=%s", self._path)
            raise UniverseConfigError(
                f"cannot read universe config at {self._path}: {exc}"
            ) from exc

        try:
            data = yaml.safe_load(raw_bytes)
        except yaml.YAMLError as exc:
            raise UniverseConfigError(
                f"universe config at {self._path} is not valid YAML: {exc}"
            ) from exc

        if not isinstance(data, dict):
            raise UniverseConfigError(
                f"universe config at {self._path} must be a mapping, got {type(data).__name__}"
            )
        try:
            model = UniverseFileModel(**data)
        except ValidationError as exc:
            raise UniverseConfigError(f"invalid universe config at {self._path}: {exc}") from exc

        symbols = frozenset(model.symbols)
        if not symbols:
            raise UniverseConfigError(f"universe config at {self._path} lists no symbols")
        # Content-address the RAW bytes (not the parsed set) — mirrors cache_key / risk.yaml
        # discipline, so a same-file load is deterministic and a changed symbol is detectable.
        artifact_hash = hashlib.sha256(raw_bytes).hexdigest()
        return symbols, artifact_hash


def default_universe(*, config_path: Path | None = None) -> OperatorFileUniverse:
    """The wired default — ``OperatorFileUniverse`` on ``config/universe.yaml`` (offline)."""
    return OperatorFileUniverse(config_path=config_path)
