"""``build_news_source`` / ``build_market_summary_source`` — wire sources from tokens (Inc-8.6).

The factory keeps the adapters decoupled from ``settings`` (the runner reads ``.env`` and passes the
tokens in). News: Tavily primary + Apify fallback (a ``CompositeNewsSource`` when both are present,
the single adapter when only one is, ``None`` when neither). Macro: a ``FredMacroSource`` when the
FRED key is present, else ``None`` (the macro/regime agent is simply not scheduled — degrade, never
crash). Returning ``None`` is the honest "this source is not configured" signal the runner respects.
"""

from __future__ import annotations

from collections.abc import Callable

from trading.slowloop.agents.news import NewsSource
from trading.slowloop.sources.apify_news import ApifyNewsSource
from trading.slowloop.sources.composite import CompositeNewsSource
from trading.slowloop.sources.fred_macro import FredMacroSource
from trading.slowloop.sources.tavily_news import HttpxTavilyNews


def build_news_source(
    *, tavily_token: str | None, apify_token: str | None, query: str | None = None
) -> NewsSource | None:
    """Compose the live news source from available tokens (Tavily primary, Apify fallback)."""
    sources: list[NewsSource] = []
    if tavily_token:
        sources.append(
            HttpxTavilyNews(tavily_token, query=query) if query else HttpxTavilyNews(tavily_token)
        )
    if apify_token:
        sources.append(
            ApifyNewsSource(apify_token, query=query) if query else ApifyNewsSource(apify_token)
        )
    if not sources:
        return None
    if len(sources) == 1:
        return sources[0]
    return CompositeNewsSource(sources)


def build_market_summary_source(*, fred_token: str | None) -> Callable[[], str] | None:
    """Build the FRED-backed market-summary source for the regime agent, or ``None`` if no key."""
    if not fred_token:
        return None
    return FredMacroSource(fred_token)
