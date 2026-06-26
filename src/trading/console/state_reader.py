"""Console STATE READER — the grounded, sanitized operator briefing (Inc-8 PART B).

Gathers the facts the Q&A responder is allowed to answer from: the kill-switch HARD state, the
honest RECORD-ONLY mode invariant, the news digest, and the advisory regime (REPORT-ONLY — read
here, never read by the acting path). Every fact is §4.2-sanitized and carries its ``as_of``.
A missing / invalid / STALE artifact resolves to "otillgänglig" (a G1-class staleness guard), so the
operator is never told a stale advisory is fresh — §9 honesty, R3 cite-your-inputs. NO live broker
call is ever made; the console stays a file-grounded reader, never a broker client.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

from trading.data.sanitize import sanitize
from trading.slowloop.contract import AgentArtifact, NewsPayload, RegimeAdvisoryPayload
from trading.slowloop.store import read_artifact

#: Past this age an advisory artifact is treated as unavailable rather than stale-trusted (R9).
DEFAULT_MAX_AGE = timedelta(hours=18)

_UNAVAILABLE = "otillgänglig (saknas eller föråldrad)"

#: The honest, sourced invariant of the sealed system — not an invented number (§9).
_MODE_TEXT = (
    "RECORD-ONLY. Schemaläggaren är vilande. Inga riktiga ordrar har lagts. "
    "(ADR §0: de 4 leksaksstrategierna dödas alla av gaten → 0 survivors → 0 ordrar.)"
)


class KillSwitchReader(Protocol):
    """The read-only subset of the kill switch the briefing needs (the real one satisfies it)."""

    def read(self) -> object: ...

    def reason(self) -> str: ...


@dataclass(frozen=True, slots=True)
class BriefingFact:
    key: str
    text: str  # sanitized
    as_of: str | None
    source: str


@dataclass(frozen=True, slots=True)
class Briefing:
    facts: tuple[BriefingFact, ...]

    def get(self, key: str) -> BriefingFact | None:
        return next((f for f in self.facts if f.key == key), None)

    def to_prompt_text(self) -> str:
        lines = []
        for f in self.facts:
            stamp = f" [as_of {f.as_of}]" if f.as_of else ""
            lines.append(f"- {f.key}{stamp} (källa: {f.source}): {f.text}")
        return "\n".join(lines)


def _state_value(ks: KillSwitchReader) -> str:
    value = ks.read()
    return getattr(value, "value", str(value))


def _fresh_artifact(path: Path, now: datetime, max_age: timedelta) -> AgentArtifact | None:
    art = read_artifact(path)
    if art is None:
        return None
    # treat an aware/naive as_of robustly; a future or recent as_of is fresh, an old one is stale.
    age = now - art.as_of
    if age > max_age:
        return None
    return art


def gather_briefing(
    kill_switch: KillSwitchReader,
    *,
    news_path: Path,
    regime_advisory_path: Path,
    now: datetime,
    max_age: timedelta = DEFAULT_MAX_AGE,
) -> Briefing:
    """Assemble the sanitized, freshness-guarded briefing the responder may answer from."""
    facts: list[BriefingFact] = []

    facts.append(
        BriefingFact(
            key="kill_switch",
            text=sanitize(f"{_state_value(kill_switch)} ({kill_switch.reason()})"),
            as_of=None,
            source="state/kill_switch.json (HARD)",
        )
    )
    facts.append(BriefingFact("mode", sanitize(_MODE_TEXT), None, "Inc-7 seal (record-only)"))

    news = _fresh_artifact(news_path, now, max_age)
    if news is not None and isinstance(news.payload, NewsPayload):
        p = news.payload
        facts.append(
            BriefingFact(
                key="nyheter",
                text=sanitize(f"{p.summary} (ton={p.tone}, {p.headline_count} rubriker)"),
                as_of=news.as_of.isoformat(),
                source=f"news_state.json TEXTUAL conf={news.confidence}",
            )
        )
    else:
        facts.append(BriefingFact("nyheter", _UNAVAILABLE, None, "news_state.json"))

    advisory = _fresh_artifact(regime_advisory_path, now, max_age)
    if advisory is not None and isinstance(advisory.payload, RegimeAdvisoryPayload):
        p2 = advisory.payload
        facts.append(
            BriefingFact(
                key="regim_radgivande",
                text=sanitize(
                    f"{p2.label.value} — {p2.rationale} "
                    "(DERIVED/rådgivande, REPORT-ONLY: påverkar inte gaten eller sizing)"
                ),
                as_of=advisory.as_of.isoformat(),
                source=f"regime_advisory.json DERIVED conf={advisory.confidence}",
            )
        )
    else:
        facts.append(BriefingFact("regim_radgivande", _UNAVAILABLE, None, "regime_advisory.json"))

    return Briefing(tuple(facts))


def gate_kill_summary() -> str:
    """The honest §0/§9 answer to "vad dödade gaten idag?" for the sealed record-only system."""
    return (
        "Gaten dödade alla 4 leksaksstrategier (ADR §0): 0 survivors, 0 ordrar. "
        "Systemet är record-only — ingen riktig order har lagts."
    )


def status_text(ks: KillSwitchReader) -> str:
    """The deterministic /status read (no LLM)."""
    return f"Kill switch: {_state_value(ks)} ({sanitize(ks.reason())}). Läge: {_MODE_TEXT}"


def read_command_map(
    ks: KillSwitchReader,
    *,
    news_path: Path,
    regime_advisory_path: Path,
    now_provider: Callable[[], datetime],
) -> dict[str, Callable[[], str]]:
    """The deterministic read-only command handlers (no LLM): /status /regim /nyheter /help."""

    def _briefing() -> Briefing:
        return gather_briefing(
            ks, news_path=news_path, regime_advisory_path=regime_advisory_path, now=now_provider()
        )

    def _regim() -> str:
        f = _briefing().get("regim_radgivande")
        return f"Regim (rådgivande): {f.text}" if f else "Regim: otillgänglig"

    def _nyheter() -> str:
        f = _briefing().get("nyheter")
        return f"Nyheter: {f.text}" if f else "Nyheter: otillgänglig"

    return {
        "/status": lambda: status_text(ks),
        "/regim": _regim,
        "/nyheter": _nyheter,
        "/vad-dödade-gaten": gate_kill_summary,
        "/help": lambda: (
            "Kommandon: /status (läge), /pausa (stoppa nya ordrar), /flatta (hard stop), "
            '/regim, /nyheter, /vad-dödade-gaten, /help. Eller fråga fritt (t.ex. "hur går det?").'
        ),
    }
