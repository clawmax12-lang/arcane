"""Console DISPATCH — deterministic commands, escalate-only controls, refuse-trade (Inc-8 PART B).

The most important boundary in this increment. Command recognition is gated on the LITERAL leading
slash of the operator's text and exact membership of a FROZEN allow-list, decided by Python string
equality BEFORE the LLM is ever consulted — never the LLM deciding to act. ``sanitize`` is purely
subtractive, so a body can never sanitize INTO a command. Acting commands map ONLY to the EXISTING
deterministic ``kill_switch`` escalate methods (trip/hard_stop) — there is NO ``arm`` path (§7:
re-arm stays CLI-only). A trade order is refused deterministically, naming the gate->GO path. The
responder's reply is sent as TEXT; it is NEVER fed back into dispatch — so a jailbroken model that
emits ``/flatta`` cannot trigger a control.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final, Protocol

from trading.data.sanitize import sanitize


class KillSwitchLike(Protocol):
    """Exactly the two ESCALATE methods the console may call — no ``arm`` is reachable from here."""

    def trip(self, reason: str) -> object: ...

    def hard_stop(self, reason: str) -> object: ...


def _no_op_refresh() -> object:
    """Default ``refresh_news``: do nothing (used when no live news source is wired)."""
    return None


@dataclass(frozen=True, slots=True)
class ConsoleDeps:
    """The injected, deterministic actuators + the grounded Q&A responder (wired in C4)."""

    kill_switch: KillSwitchLike
    reply: Callable[
        [str], None
    ]  # send a message to the operator (notifier.send_message — sanitizes)
    answer: Callable[[str], str]  # the grounded, report-only Q&A responder
    reads: Mapping[str, Callable[[], str]]  # read-only command -> text (/status, /regim, ...)
    # Inc-8.6 PART C: best-effort, rate-limited, fail-closed on-demand news refresh. Default no-op
    # so existing constructions keep working; the real one (build_news_refresher) is wired in C5.
    refresh_news: Callable[[], object] = _no_op_refresh


# A trade-intent matcher (broad = more refusals = safer, per operator). Runs on sanitized text.
_TRADE_INTENT: Final[re.Pattern[str]] = re.compile(
    r"\b(köp\w*|sälj\w*|buy|sell|long|short|blank\w*|g[åa]\s+l[åa]ng|g[åa]\s+kort)\b",
    re.IGNORECASE,
)

# A GENEROUS market/news/status relevance heuristic (sv+en). When the operator asks how things are
# going OR about the market/news, the console PROACTIVELY freshens real news before answering ("it
# should just happen", per operator) — NOT a canned-response selector: the reply is always the real
# conversation; this only decides whether to freshen the underlying DATA. The hard cost bound is the
# fail-closed cooldown in news_refresh, not this regex; it errs toward firing but skips abstract
# questions ("förklara en sharpe-kvot") so it does not fetch news for an unrelated definition.
_NEWS_RELEVANT: Final[re.Pattern[str]] = re.compile(
    r"(nyhet|news|rubrik|headline|marknad|market|b[öo]rs|stock|aktie|index|s&p|nasdaq|dow"
    r"|makro|macro|r[äa]nt|yield|inflation|fed|vix|regim|regime"
    r"|hur\s+g[åa]r|hur\s+ligger|hur\s+ser\s+det\s+ut|hur\s+[äa]r\s+l[äa]get|l[äa]get"
    r"|vad\s+h[äa]nder|vad\s+tror\s+du|hur\s+m[åa]r|how'?s\s+it\s+going|what'?s\s+(happening|up)"
    r"|idag|dagens|i\s*natt|[öo]vernatt|today|tonight|overnight)",
    re.IGNORECASE,
)

_PAUSA_REASON: Final[str] = "operator /pausa via console"
_FLATTA_REASON: Final[str] = "operator /flatta via console"

_PAUSA_REPLY: Final[str] = (
    "⏸️ Pausad. Kill switch → TRIPPED: inga nya ordrar. "
    "(Återställning sker bara via operator-CLI, aldrig härifrån.)"
)
_FLATTA_REPLY: Final[str] = (
    "🛑 Flatta begärd. Kill switch → HARD_STOPPED: inga nya ordrar; den deterministiska loopen "
    "flattar ev. positioner. (Nu: record-only, 0 positioner.)"
)
_UNKNOWN_REPLY: Final[str] = (
    "Okänt kommando. Tillgängligt: /status, /pausa, /flatta, /regim, /nyheter, /halsa, /trials, "
    '/vad-dödade-gaten, /help. Eller fråga mig vad som helst (t.ex. "hur går det?").'
)
_TRADE_REFUSAL: Final[str] = (
    "Jag kan inte lägga ordrar. Bara gate→GO-vägen kan skapa en order — konsolen kan bara "
    "läsa status, pausa (/pausa) eller flatta (/flatta)."
)


def _dispatch_command(token: str, deps: ConsoleDeps) -> None:
    if token == "/pausa":
        deps.kill_switch.trip(_PAUSA_REASON)  # ESCALATE only — monotonic, idempotent
        deps.reply(_PAUSA_REPLY)
    elif token == "/flatta":
        deps.kill_switch.hard_stop(_FLATTA_REASON)
        deps.reply(_FLATTA_REPLY)
    elif token == "/nyheter":
        deps.refresh_news()  # force a fresh fetch (rate-limited, swallowed) BEFORE the read
        deps.reply(deps.reads[token]())
    elif token in deps.reads:
        deps.reply(deps.reads[token]())  # READ-ONLY state lookup
    else:
        deps.reply(_UNKNOWN_REPLY)  # unknown /command — never silent execution


def handle_message(text: str, deps: ConsoleDeps) -> None:
    """Route one authenticated operator message: command / trade-refusal / grounded Q&A.

    The fork happens ONCE on the inbound operator text. The Q&A responder's reply is passed only to
    ``deps.reply`` — it is never fed back into this dispatcher, so an LLM reply can never become an
    action.
    """
    stripped = text.lstrip()
    if stripped.startswith("/"):
        token = stripped.split(maxsplit=1)[0].lower().split("@", 1)[0]
        _dispatch_command(token, deps)
        return
    sanitized = sanitize(text)
    if _TRADE_INTENT.search(sanitized):
        deps.reply(_TRADE_REFUSAL)  # deterministic refusal — no LLM call, no broker contact
        return
    if _NEWS_RELEVANT.search(sanitized):
        deps.refresh_news()  # "it just happens": freshen real news before grounding (swallowed)
    deps.reply(deps.answer(sanitized))  # grounded conversational Q&A (text only)
