"""The agent ARTIFACT CONTRACT — §4.3 baked into the type (Inc-8 PART A).

Every slow-loop agent emits exactly one ``AgentArtifact``: a frozen, extra-forbid pydantic v2 model
whose ``reliability`` is ``Literal["textual","derived"]`` — there is NO field an agent can set to
HARD/STRUCTURED, so an agent literally cannot mint a gateable artifact (§4.3). ``confidence`` is
bounded [0,1] (R2); ``sources`` cite the inputs (R3, required for an ``ok`` claim); ``status``
carries the R1 ``uncertain`` escape hatch. The payload is a discriminated union per agent; the
regime-advisory label is constrained to the EXISTING ``RegimeLabel`` space so an agent can never
widen the label universe the deterministic posture (Inc-7) was built against.

A submit-path-side reader maps ``reliability`` through ``Reliability`` + ``require_gateable`` (which
RAISES on DERIVED), so even a hand-edited artifact advises but never gates, sizes, or places orders.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from trading.regime.labels import RegimeLabel

SCHEMA_VERSION = 1

#: An agent may declare ONLY advisory reliability tiers — never a gateable (HARD/STRUCTURED) one.
AdvisoryReliability = Literal["textual", "derived"]


class Source(BaseModel):
    """A cited input (R3): what evidence backs the claim, and as-of when."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["news", "macro", "market", "social", "state"]
    ref: str  # a sanitized, url-stripped reference (title / source name) — never raw external text
    as_of: datetime


class NewsPayload(BaseModel):
    """The NEWS/OVERNIGHT agent's digest — TEXTUAL evidence, never a command."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["news"] = "news"
    headline_count: int = Field(ge=0)
    summary: str  # sanitized digest
    salient_symbols: tuple[str, ...] = ()
    tone: Literal["risk_on", "risk_off", "mixed", "unclear"] = "unclear"


class RegimeAdvisoryPayload(BaseModel):
    """The agent-fed advisory regime — DERIVED. REPORT-ONLY in Inc-8 (acting path never reads it).

    ``label`` is the EXISTING ``RegimeLabel`` StrEnum — an advisory label outside that space fails
    validation, so the advisory can never introduce a label the deterministic posture / spec
    ``eligible_regimes`` were never declared against.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["regime_advisory"] = "regime_advisory"
    label: RegimeLabel
    rationale: str  # sanitized


class DailyReportPayload(BaseModel):
    """The Daily Report synthesizer's honest §9 report — TEXTUAL, sent to the pager, never gated."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["daily_report"] = "daily_report"
    report_markdown: str  # sanitized, honest (incl. the boring 0-trade days)


#: Discriminated by ``kind`` so a persisted artifact deserializes into the right payload type.
Payload = Annotated[
    NewsPayload | RegimeAdvisoryPayload | DailyReportPayload,
    Field(discriminator="kind"),
]


class AgentArtifact(BaseModel):
    """A schema-validated §4.3-tagged slow-loop agent output (frozen, extra-forbid, fail-closed)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = SCHEMA_VERSION
    agent_name: str
    reliability: AdvisoryReliability
    confidence: float = Field(ge=0.0, le=1.0)
    as_of: datetime  # the data's effective time (aware UTC)
    produced_at: datetime  # when this artifact was written (aware UTC)
    model_id: str
    sources: list[Source]
    status: Literal["ok", "uncertain"] = "ok"
    payload: Payload

    @model_validator(mode="after")
    def _ok_claims_must_cite(self) -> AgentArtifact:
        # R3: an "ok" claim must cite at least one input. An "uncertain" artifact (the R1 escape
        # hatch) may carry none — it is discarded by the orchestrator anyway.
        if self.status == "ok" and not self.sources:
            raise ValueError("an 'ok' artifact must cite at least one source (R3)")
        return self
