"""Console STATE READER — the grounded, sanitized operator briefing (Inc-8 PART B; widened Inc-8.5).

Gathers the facts the conversational Q&A responder is allowed to answer from: the kill-switch HARD
state, the honest RECORD-ONLY mode invariant, the news digest, the advisory regime (REPORT-ONLY —
read here, never read by the acting path), and — added in Inc-8.5 so the chat has real substance —
a static "what ARCANE is" context, the gate verdict + why, an honest "no live equity is read" line,
the slow-loop agents' health, the gate's n_trials high-water-mark, and presence-only operator
posture markers. Every fact is §4.2-sanitized and carries its ``as_of`` where applicable. A missing
/ invalid / STALE artifact resolves to "otillgänglig" (a G1-class staleness guard), so the operator
is never told a stale advisory is fresh — §9 honesty, R3 cite-your-inputs. NO live broker call is
ever made; the console stays a file-grounded reader, never a broker client. The operator-posture
markers are read by PRESENCE ONLY — their contents (the SUBMIT_GO phrase) are never read.
"""

from __future__ import annotations

import json
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

#: Inc-8.5 read-only state the briefing may consult. LOCAL literals (not imported from bias_gate /
#: slowloop / scheduler) so no new import edge is added into the boundary — re-proven by the
#: boundary test. They MIRROR the real producers' paths (orchestrator / high_water_mark / markers).
DEFAULT_HEALTH_PATH = Path("state/slowloop/_health.json")
DEFAULT_HWM_PATH = Path("state/n_trials_high_water_mark.json")
_HWM_KEY = "n_trials_high_water_mark"
_SCHEDULER_MARKER = Path("state/SCHEDULER_ENABLE")
_SUBMIT_GO_MARKER = Path("state/SUBMIT_GO")
_LIVE_MODE_MARKER = Path("state/LIVE_MODE_CONFIRMED")

_UNAVAILABLE = "otillgänglig (saknas eller föråldrad)"

#: The honest, sourced invariant of the sealed system — not an invented number (§9).
_MODE_TEXT = (
    "RECORD-ONLY. Schemaläggaren är vilande. Inga riktiga ordrar har lagts. "
    "(ADR §0: de 4 leksaksstrategierna dödas alla av gaten → 0 survivors → 0 ordrar.)"
)

#: A static, honest description so the model can answer "vad är ARCANE / förklara gaten" truthfully
#: WITHOUT inventing live data. Labelled as a standing description, not today's numbers.
_ARCANE_CONTEXT = (
    "ARCANE är ett AUTONOMT, PAPER-ONLY trading-forskningssystem. Hot-loop (order, sizing, kill "
    "switch) är deterministisk Python; LLM:er är RÅDGIVANDE i slow-loop och rör aldrig mäklaren. "
    "Gaten är en ALLA-av bias/kill-gate (DSR/PSR/PBO/SPA/walk-forward) som ANTINGEN godkänner "
    "ELLER dödar varje strategi. Regimen är RÅDGIVANDE (DERIVED) och påverkar aldrig gaten/sizing. "
    "Systemet är record-only: de 4 leksaksstrategierna dödas alla av gaten → 0 survivors "
    "→ 0 ordrar (ADR §0)."
)

#: Honest non-answer to "hur mycket har vi tjänat?" — no equity file exists and the console may not
#: call the broker, so we never fabricate a $ figure.
_EQUITY_TEXT = (
    "Record-only pappersexperiment — ingen live-equity läses (konsolen ringer aldrig mäklaren)."
)


@dataclass(frozen=True, slots=True)
class StatePaths:
    """The read-only state files/markers the briefing may consult (real defaults; injectable).

    Bundling them keeps ``gather_briefing``/``read_command_map`` tidy and lets tests point them
    at a ``tmp_path`` for hermeticity. Marker fields are read by PRESENCE only — never contents.
    """

    health: Path = DEFAULT_HEALTH_PATH
    hwm: Path = DEFAULT_HWM_PATH
    scheduler_marker: Path = _SCHEDULER_MARKER
    submit_go_marker: Path = _SUBMIT_GO_MARKER
    live_mode_marker: Path = _LIVE_MODE_MARKER


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


def _load_health(path: Path) -> dict[str, int] | None:
    """Read ``_health.json`` ({agent: consecutive_failures}); fail closed to None on any anomaly."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    return {str(k): int(v) for k, v in raw.items() if isinstance(v, int)}


def _load_hwm_int(path: Path) -> int | None:
    """Read the n_trials high-water-mark int; fail closed to None on missing/corrupt/non-int."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    value = raw.get(_HWM_KEY)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _yn(present: bool) -> str:
    return "ja" if present else "nej"


def gather_briefing(
    kill_switch: KillSwitchReader,
    *,
    news_path: Path,
    regime_advisory_path: Path,
    now: datetime,
    max_age: timedelta = DEFAULT_MAX_AGE,
    state_paths: StatePaths | None = None,
) -> Briefing:
    """Assemble the sanitized, freshness-guarded briefing the responder may answer from."""
    paths = state_paths or StatePaths()
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
    facts.append(
        BriefingFact("om_arcane", sanitize(_ARCANE_CONTEXT), None, "statisk projektbeskrivning")
    )
    facts.append(
        BriefingFact("gate_utfall", sanitize(gate_kill_summary()), None, "ADR §0 (record-only)")
    )
    facts.append(BriefingFact("equity", sanitize(_EQUITY_TEXT), None, "Inc-7 seal (record-only)"))

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

    health = _load_health(paths.health)
    if health is not None and health:
        pairs = ", ".join(f"{k}={v}" for k, v in sorted(health.items()))
        facts.append(
            BriefingFact(
                key="agent_halsa",
                text=sanitize(f"{pairs} (fel i rad; 0 = friskt)"),
                as_of=None,
                source="_health.json (HARD)",
            )
        )
    else:
        facts.append(BriefingFact("agent_halsa", _UNAVAILABLE, None, "_health.json"))

    n_trials = _load_hwm_int(paths.hwm)
    if n_trials is not None:
        facts.append(
            BriefingFact(
                key="gate_trials",
                text=sanitize(f"Gaten har utvärderat {n_trials} trials (high-water-mark)"),
                as_of=None,
                source="n_trials_high_water_mark.json (HARD)",
            )
        )
    else:
        facts.append(
            BriefingFact("gate_trials", _UNAVAILABLE, None, "n_trials_high_water_mark.json")
        )

    # PRESENCE-ONLY operator posture: read .is_file() booleans, NEVER the marker contents.
    facts.append(
        BriefingFact(
            key="operator_lage",
            text=sanitize(
                f"schemaläggare aktiverad: {_yn(paths.scheduler_marker.is_file())}; "
                f"SUBMIT_GO: {_yn(paths.submit_go_marker.is_file())}; "
                f"live-läge bekräftat: {_yn(paths.live_mode_marker.is_file())}"
            ),
            as_of=None,
            source="state/ markers (presence, HARD)",
        )
    )

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
    state_paths: StatePaths | None = None,
) -> dict[str, Callable[[], str]]:
    """The deterministic read-only command handlers (no LLM): /status /regim /nyheter /help …."""

    def _briefing() -> Briefing:
        return gather_briefing(
            ks,
            news_path=news_path,
            regime_advisory_path=regime_advisory_path,
            now=now_provider(),
            state_paths=state_paths,
        )

    def _regim() -> str:
        f = _briefing().get("regim_radgivande")
        return f"Regim (rådgivande): {f.text}" if f else "Regim: otillgänglig"

    def _nyheter() -> str:
        f = _briefing().get("nyheter")
        return f"Nyheter: {f.text}" if f else "Nyheter: otillgänglig"

    def _halsa() -> str:
        f = _briefing().get("agent_halsa")
        return f"Agent-hälsa: {f.text}" if f else "Agent-hälsa: otillgänglig"

    def _trials() -> str:
        f = _briefing().get("gate_trials")
        return f"Gate-trials: {f.text}" if f else "Gate-trials: otillgänglig"

    return {
        "/status": lambda: status_text(ks),
        "/regim": _regim,
        "/nyheter": _nyheter,
        "/halsa": _halsa,
        "/trials": _trials,
        "/vad-dödade-gaten": gate_kill_summary,
        "/help": lambda: (
            "Kommandon: /status (läge), /pausa (stoppa nya ordrar), /flatta (hard stop), "
            "/regim, /nyheter, /halsa, /trials, /vad-dödade-gaten, /help. Eller fråga fritt "
            '(t.ex. "hur går det?").'
        ),
    }
