"""Content-addressed cache for sealed ``MembershipArtifact`` JSON (Increment 6 PART A).

Mirrors ``ParquetCache`` discipline at a smaller scale (artifacts are tiny): the filename IS the
content hash, writes are atomic (temp -> fsync -> ``os.replace``), and a read RE-VALIDATES by
re-hashing the loaded artifact — a corrupt/tampered file is a MISS (self-healed by unlink),
NEVER served. Caching is an optimization, so a write is PAUSED when free disk is below the floor
(ADR-F7) rather than risk a disk-exhaustion Murphy event. A miss is always safe: the gate's T2 then
finds no hash-matching artifact and fails CLOSED.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Final

from trading.data.membership_artifact import (
    MembershipArtifact,
    artifact_from_json,
    artifact_to_json,
    membership_artifact_hash,
)

logger = logging.getLogger(__name__)

MIN_FREE_DISK_BYTES: Final[int] = 1024 * 1024 * 1024  # 1 GiB (ADR-F7), same floor as ParquetCache


class MembershipCache:
    """File cache of sealed membership artifacts, keyed by their content hash."""

    def __init__(self, directory: Path, *, min_free_bytes: int = MIN_FREE_DISK_BYTES) -> None:
        self._dir = directory
        self._min_free = min_free_bytes
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self._dir / f"{key}.json"

    def get(self, key: str) -> MembershipArtifact | None:
        """Return the artifact for ``key``, or None on a miss / corrupt / hash-mismatch
        (self-heals)."""
        path = self._path(key)
        if not path.exists():
            return None
        try:
            artifact = artifact_from_json(path.read_text(encoding="utf-8"))
            if membership_artifact_hash(artifact) != key:
                raise ValueError("cached artifact hash does not match its key")
        except Exception:
            path.unlink(missing_ok=True)  # self-heal: a corrupt/tampered entry is never served
            return None
        return artifact

    def put(self, artifact: MembershipArtifact) -> str:
        """Atomically seal ``artifact``; return its content key. Paused under disk pressure.

        The key is returned regardless of whether the bytes persisted — under ADR-F7 disk pressure
        the write is skipped and a later ``get`` just misses (fail-closed downstream), not a crash.
        """
        key = membership_artifact_hash(artifact)
        free = shutil.disk_usage(self._dir).free
        if free < self._min_free:
            logger.warning(
                "membership cache write paused for %s: free disk %d B < floor %d B (ADR-F7)",
                key,
                free,
                self._min_free,
            )
            return key
        tmp = self._dir / f"{key}.json.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(artifact_to_json(artifact))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self._path(key))
        return key
