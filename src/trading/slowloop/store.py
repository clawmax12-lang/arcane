"""The atomic, fail-closed artifact STORE (Inc-8 PART A).

Writes mirror ``kill_switch._write`` EXACTLY — temp -> fsync -> ``os.replace`` — so a half-written
artifact is never observable: a reader sees either the prior valid file or the new one, never a torn
one. ``read_artifact`` fails CLOSED: a missing / torn / corrupt / schema-invalid file returns
``None`` ("unavailable") and NEVER raises into a reader. A corrupt file is indistinguishable from
"no data yet", and "no data" is always safe — the acting path already fails closed to zero trades.
"""

from __future__ import annotations

import os
from pathlib import Path

import structlog
from pydantic import ValidationError

from trading.slowloop.contract import AgentArtifact

_log = structlog.get_logger(__name__)


def write_artifact(path: Path, artifact: AgentArtifact) -> None:
    """Atomically persist ``artifact`` to ``path`` (temp -> fsync -> os.replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(artifact.model_dump_json())
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def read_artifact(path: Path) -> AgentArtifact | None:
    """Return the validated artifact at ``path``, or ``None`` on ANY anomaly (fail closed).

    A missing file, a torn/partial write, malformed JSON, or a schema-invalid payload (e.g. a forged
    ``reliability:"hard"``) all resolve to ``None`` — never an exception into the caller. The caller
    treats ``None`` as "unavailable" and reuses last-known-good or its own zero-candidate
    fail-closed path.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return None
    try:
        return AgentArtifact.model_validate_json(text)
    except (ValidationError, ValueError) as exc:
        _log.warning("artifact_read_failed", path=str(path), error=type(exc).__name__)
        return None
