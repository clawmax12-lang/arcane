"""The slow-loop ORCHESTRATOR — run agents, validate, fail closed, alert (Inc-8 PART A).

``run_agent`` is the single safety choke for an agent's output. It runs the agent, then FAILS CLOSED
on any anomaly: an exception during ``produce``, an ``uncertain`` status (R1), or a below-floor
confidence (R2) → DISCARD (the last-known-good artifact on disk is left byte-identical, never a torn
file), increment a persisted consecutive-failure counter, and page the operator ORANGE once the
count reaches ``alert_after`` (default 3 — one step before §8's "5 consecutive scheduler errors"
abandonment). A healthy run atomically writes the artifact and resets the counter.

§1.2: agents are independent — one bad agent never stops the others; the failure is local, the alert
is global. This module imports NO broker and NO submit-path actuator; its only side effects are a
file write (the agent's own output domain), a counter file, and a best-effort ORANGE page.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import structlog

from trading.notify.telegram import Severity
from trading.slowloop.contract import AgentArtifact
from trading.slowloop.llm.anthropic_client import Responder
from trading.slowloop.store import write_artifact

_log = structlog.get_logger(__name__)

DEFAULT_CONFIDENCE_FLOOR: float = 0.4  # R2: "if you're not sure, say 0.4"
DEFAULT_ALERT_AFTER: int = 3  # §1.2 ">3 consecutive failures"; one step before §8's 5-error trip
DEFAULT_HEALTH_PATH = Path("state/slowloop/_health.json")


class Agent(Protocol):
    """A slow-loop agent: a name, exactly ONE output path (§1.2), and a ``produce`` step."""

    name: str
    output_path: Path

    def produce(self, responder: Responder) -> AgentArtifact: ...


class Pager(Protocol):
    """The notifier subset the orchestrator needs (the real ``TelegramNotifier`` satisfies it)."""

    def page_operator(self, severity: Severity, text: str) -> None: ...


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    agent_name: str
    written: bool
    reason: str
    consecutive_failures: int
    paged: bool


def _load_health(path: Path) -> dict[str, int]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): int(v) for k, v in raw.items() if isinstance(v, int)}


def _save_health(path: Path, health: dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(health, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def run_agent(
    agent: Agent,
    responder: Responder,
    *,
    notifier: Pager | None = None,
    health_path: Path = DEFAULT_HEALTH_PATH,
    confidence_floor: float = DEFAULT_CONFIDENCE_FLOOR,
    alert_after: int = DEFAULT_ALERT_AFTER,
) -> AgentRunResult:
    """Run one agent; write its artifact on success, else discard + count + (ORANGE) page."""
    discard_reason: str | None = None
    artifact: AgentArtifact | None = None
    try:
        artifact = agent.produce(responder)
    except Exception as exc:  # fail closed on ANY agent error (incl. schema ValidationError)
        discard_reason = f"produce_failed:{type(exc).__name__}"

    if artifact is not None:
        if artifact.status == "uncertain":
            discard_reason = "status_uncertain"
        elif artifact.confidence < confidence_floor:
            discard_reason = f"confidence_below_floor:{artifact.confidence}"

    if discard_reason is None and artifact is not None:
        write_artifact(agent.output_path, artifact)  # atomic; last-known-good only ever advances
        health = _load_health(health_path)
        health[agent.name] = 0
        _save_health(health_path, health)
        return AgentRunResult(agent.name, True, "ok", 0, False)

    # DISCARD path — the prior artifact on disk is untouched (no write happened).
    health = _load_health(health_path)
    failures = health.get(agent.name, 0) + 1
    health[agent.name] = failures
    _save_health(health_path, health)
    paged = False
    if failures >= alert_after and notifier is not None:
        notifier.page_operator(
            Severity.ORANGE,
            f"slow-loop agent '{agent.name}' failing: {failures} consecutive ({discard_reason})",
        )
        paged = True
    _log.warning(
        "agent_discarded", agent=agent.name, reason=discard_reason, failures=failures, paged=paged
    )
    return AgentRunResult(agent.name, False, discard_reason or "discarded", failures, paged)
