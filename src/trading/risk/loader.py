"""Fail-closed loader for ``config/risk.yaml``.

Any read, parse, or validation failure raises ``RiskConfigError``; callers must treat
that as "refuse to trade". There is no partial or default risk config — a missing or
malformed limits file means the system does not trade, full stop.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from .errors import RiskConfigError
from .schema import RiskConfig


def load_risk_config(path: str | Path) -> RiskConfig:
    """Load and validate the risk config, or raise ``RiskConfigError`` (fail-closed)."""
    p = Path(path)

    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise RiskConfigError(f"cannot read risk config at {p}: {exc}") from exc

    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RiskConfigError(f"risk config at {p} is not valid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise RiskConfigError(f"risk config at {p} must be a mapping, got {type(raw).__name__}")

    try:
        return RiskConfig(**raw)
    except ValidationError as exc:
        raise RiskConfigError(f"invalid risk config at {p}: {exc}") from exc
