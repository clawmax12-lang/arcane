"""Shared agent helpers — fail-closed parsing of an LLM reply (Inc-8 PART C)."""

from __future__ import annotations

import json
import re
from typing import Any

from trading.slowloop.errors import AgentValidationError

_FENCE_OPEN = re.compile(r"^```[a-zA-Z]*\n?")
_FENCE_CLOSE = re.compile(r"\n?```$")


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse an LLM reply into a JSON object, stripping markdown fences; fail closed otherwise.

    A non-JSON or non-object reply raises ``AgentValidationError`` so the orchestrator discards the
    output and keeps the last-known-good artifact — an agent can never half-produce a gating one.
    """
    s = text.strip()
    if s.startswith("```"):
        s = _FENCE_CLOSE.sub("", _FENCE_OPEN.sub("", s)).strip()
    try:
        obj = json.loads(s)
    except (ValueError, TypeError) as exc:
        raise AgentValidationError(
            f"agent reply was not valid JSON: {type(exc).__name__}"
        ) from None
    if not isinstance(obj, dict):
        raise AgentValidationError("agent reply was not a JSON object")
    return obj
