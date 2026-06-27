"""``CompositeNewsSource`` — priority-ordered, first FULL success, never merge (Inc-8.6).

The composite tries its sources IN ORDER and returns the FIRST non-raising call's result — even an
empty list (a source saying "no news" is authoritative, distinct from "source down"). It RAISES
``NewsSourceError`` only if EVERY source raised. It NEVER silently merges a partial set: a fallback
fires ONLY when the primary RAISES, so the heavy 100-item Apify fallback never burns the free-tier
compute while Tavily is healthy.
"""

from __future__ import annotations

from collections.abc import Sequence

import structlog

from trading.slowloop.agents.news import NewsItem, NewsSource
from trading.slowloop.sources.errors import NewsSourceError

_log = structlog.get_logger(__name__)


class CompositeNewsSource:
    """A priority-ordered ``NewsSource`` — first non-raising source wins; all-fail raises."""

    def __init__(self, sources: Sequence[NewsSource]) -> None:
        if not sources:
            raise NewsSourceError("CompositeNewsSource requires at least one source")
        self._sources = tuple(sources)

    def __call__(self) -> list[NewsItem]:
        failures: list[str] = []
        for index, source in enumerate(self._sources):
            try:
                return list(source())  # first NON-RAISING call wins (even []), never merged
            except NewsSourceError as exc:
                failures.append(f"{index}:{type(exc).__name__}")
                _log.warning("news_source_failed", index=index, error=type(exc).__name__)
        raise NewsSourceError(f"all {len(self._sources)} news sources failed ({failures})")
