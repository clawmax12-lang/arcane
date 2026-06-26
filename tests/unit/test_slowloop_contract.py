"""C1 — the slow-loop agent ARTIFACT CONTRACT (Inc-8 PART A).

§4.3 is baked into the TYPE: an agent literally cannot mint a gateable artifact. ``reliability``
is ``Literal["textual","derived"]`` — there is no field an agent can set to HARD/STRUCTURED — and a
submit-path reader that maps it through ``Reliability`` + ``require_gateable`` raises on DERIVED.
The contract is frozen + extra-forbid; confidence is bounded [0,1] (R2); sources are cited (R3); the
regime-advisory label is constrained to the EXISTING ``RegimeLabel`` space so an agent can never
widen the label universe the deterministic posture was built against.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from trading.data.errors import ReliabilityError
from trading.data.reliability import Reliability, require_gateable
from trading.regime.labels import RegimeLabel
from trading.slowloop.contract import (
    AgentArtifact,
    DailyReportPayload,
    NewsPayload,
    RegimeAdvisoryPayload,
    Source,
)

_TS = datetime(2026, 6, 26, 9, 30, tzinfo=UTC)


def _news_artifact(**over: object) -> AgentArtifact:
    base: dict[str, object] = dict(
        schema_version=1,
        agent_name="news",
        reliability="textual",
        confidence=0.6,
        as_of=_TS,
        produced_at=_TS,
        model_id="claude-test",
        sources=[Source(kind="news", ref="reuters: markets steady", as_of=_TS)],
        status="ok",
        payload=NewsPayload(headline_count=3, summary="quiet overnight", tone="mixed"),
    )
    base.update(over)
    return AgentArtifact(**base)  # type: ignore[arg-type]


def test_valid_news_artifact_constructs() -> None:
    art = _news_artifact()
    assert art.agent_name == "news"
    assert isinstance(art.payload, NewsPayload)
    assert art.payload.headline_count == 3


def test_reliability_cannot_be_gateable() -> None:
    # The whole §4.3 point: an agent cannot declare HARD/STRUCTURED.
    for forged in ("hard", "structured", "HARD", "anything"):
        with pytest.raises(ValidationError):
            _news_artifact(reliability=forged)


def test_confidence_is_bounded_unit_interval() -> None:
    for bad in (-0.01, 1.01, 2.0, -5.0):
        with pytest.raises(ValidationError):
            _news_artifact(confidence=bad)
    for ok in (0.0, 0.4, 1.0):
        assert _news_artifact(confidence=ok).confidence == ok


def test_extra_fields_forbidden_and_model_frozen() -> None:
    with pytest.raises(ValidationError):
        _news_artifact(surprise="i am an injected field")
    art = _news_artifact()
    with pytest.raises(ValidationError):
        art.confidence = 0.99  # type: ignore[misc]


def test_ok_status_requires_at_least_one_source() -> None:
    # R3 — an "ok" claim must cite its inputs; an empty source list on an ok claim is rejected.
    with pytest.raises(ValidationError):
        _news_artifact(sources=[])
    # an explicitly UNCERTAIN artifact may carry no sources (it is the R1 escape hatch).
    art = _news_artifact(status="uncertain", sources=[])
    assert art.status == "uncertain"


def test_regime_advisory_label_must_be_a_known_regime_label() -> None:
    good = AgentArtifact(
        schema_version=1,
        agent_name="regime_synth",
        reliability="derived",
        confidence=0.55,
        as_of=_TS,
        produced_at=_TS,
        model_id="claude-test",
        sources=[Source(kind="market", ref="spy proxy", as_of=_TS)],
        status="ok",
        payload=RegimeAdvisoryPayload(label=RegimeLabel.HIGH_VOL_DOWN, rationale="vix up"),
    )
    assert good.payload.label is RegimeLabel.HIGH_VOL_DOWN
    # An advisory label outside the deterministic StrEnum space is rejected at the schema boundary.
    with pytest.raises(ValidationError):
        RegimeAdvisoryPayload(label="panic_vol_crash", rationale="made up")  # type: ignore[arg-type]


def test_daily_report_payload_roundtrips() -> None:
    art = AgentArtifact(
        schema_version=1,
        agent_name="daily_report",
        reliability="textual",
        confidence=1.0,
        as_of=_TS,
        produced_at=_TS,
        model_id="claude-test",
        sources=[Source(kind="state", ref="loop_result", as_of=_TS)],
        status="ok",
        payload=DailyReportPayload(report_markdown="0 trades, 0 survivors, gate killed all 4 toys"),
    )
    assert isinstance(art.payload, DailyReportPayload)


def test_artifact_json_roundtrips_losslessly() -> None:
    art = _news_artifact()
    again = AgentArtifact.model_validate_json(art.model_dump_json())
    assert again == art


def test_payload_discriminator_routes_by_kind() -> None:
    # A JSON payload with kind="regime_advisory" deserializes into the right payload type.
    art = _news_artifact(
        agent_name="regime_synth",
        reliability="derived",
        payload=RegimeAdvisoryPayload(label=RegimeLabel.LOW_VOL_UP, rationale="calm"),
    )
    again = AgentArtifact.model_validate_json(art.model_dump_json())
    assert isinstance(again.payload, RegimeAdvisoryPayload)
    assert again.payload.label is RegimeLabel.LOW_VOL_UP


def test_artifact_reliability_maps_to_a_non_gateable_tier() -> None:
    # Submit-path-side guard: an advisory artifact's reliability can NEVER satisfy require_gateable.
    for art in (_news_artifact(), _news_artifact(reliability="derived")):
        tier = Reliability(art.reliability)
        assert tier not in (Reliability.HARD, Reliability.STRUCTURED)
        with pytest.raises(ReliabilityError):
            require_gateable(tier)
