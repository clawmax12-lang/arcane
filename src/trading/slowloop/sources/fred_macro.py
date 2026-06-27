"""``FredMacroSource`` — a real, fail-closed FRED macro summary for the regime agent (Inc-8.6).

Feeds the EXISTING ``RegimeSynthAgent`` (its ``market_summary_source`` is a ``() -> str`` seam) with
a compact, honest summary from a small fixed set of FRED series (10y/2y yields, the 10y-2y curve,
VIX, fed funds) — so the advisory regime becomes REAL (FRED-grounded), not fake.

Discipline (mirrors ``data/polygon_universe.py``): a min-interval throttle that SLEEPS; the API key
in the ``api_key`` query param ONLY (FRED's auth), never logged; exceptions re-wrapped to TYPE-only.
FAIL CLOSED: any series transport/HTTP/parse failure, or a series with no recent numeric value,
raises ``MacroSourceError`` (the agent's ``produce`` then raises → the orchestrator discards,
last-good kept). The summary is numeric but the agent sanitizes it before the LLM (uniform §4.2
choke). The values are HARD/STRUCTURED numbers, advisory only — never a gate input.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Final

import httpx

from trading.slowloop.sources.errors import MacroSourceError

logger = logging.getLogger(__name__)

_FRED_BASE: Final[str] = "https://api.stlouisfed.org"
_OBS_PATH: Final[str] = "/fred/series/observations"
_DEFAULT_MIN_INTERVAL_S: Final[float] = 0.5

#: (series_id, swedish_label, unit_suffix) — the lean macro picture the regime agent reasons over.
DEFAULT_SERIES: Final[tuple[tuple[str, str, str], ...]] = (
    ("DGS10", "10y", "%"),
    ("DGS2", "2y", "%"),
    ("T10Y2Y", "10y-2y", ""),
    ("VIXCLS", "VIX", ""),
    ("DFF", "styrränta", "%"),
)


class FredMacroSource:
    """Default FRED macro source: fetches a few series and formats a compact summary. Key hidden."""

    def __init__(
        self,
        token: str,
        *,
        series: tuple[tuple[str, str, str], ...] = DEFAULT_SERIES,
        client: httpx.Client | None = None,
        base_url: str = _FRED_BASE,
        timeout: float = 20.0,
        min_interval_s: float = _DEFAULT_MIN_INTERVAL_S,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not token:
            raise MacroSourceError("FredMacroSource requires a token (fail closed)")
        self._token = token
        self._series = series
        self._client = client
        self._base = base_url
        self._timeout = timeout
        self._min_interval = min_interval_s
        self._sleeper = sleeper
        self._clock = clock
        self._last_call: float | None = None

    def _throttle(self) -> None:
        if self._last_call is not None:
            wait = self._min_interval - (self._clock() - self._last_call)
            if wait > 0:
                self._sleeper(wait)
        self._last_call = self._clock()

    def _fetch_latest(self, series_id: str) -> tuple[str, float]:
        """Return ``(date, value)`` of the most recent NUMERIC observation; raise on any failure."""
        self._throttle()
        url = self._base + _OBS_PATH
        params: dict[str, str | int] = {
            "series_id": series_id,
            "api_key": self._token,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 10,  # skip recent "." (holiday/weekend) placeholders
        }
        client = self._client or httpx.Client()
        try:
            resp = client.get(url, params=params, timeout=self._timeout)
        except Exception as exc:
            raise MacroSourceError(
                f"fred fetch failed for {series_id}: {type(exc).__name__}"
            ) from None
        finally:
            if self._client is None:
                client.close()
        if resp.status_code // 100 != 2:
            raise MacroSourceError(f"fred returned HTTP {resp.status_code} for {series_id}")
        try:
            payload = resp.json()
        except Exception as exc:
            raise MacroSourceError(
                f"fred malformed JSON for {series_id}: {type(exc).__name__}"
            ) from None
        obs = payload.get("observations") if isinstance(payload, dict) else None
        if not isinstance(obs, list):
            raise MacroSourceError(f"fred malformed observations for {series_id}")
        for row in obs:
            if not isinstance(row, dict):
                continue
            raw = row.get("value")
            try:
                value = float(str(raw))  # "." / None raise ValueError -> try the next, older obs
            except ValueError:
                continue
            return str(row.get("date", "")), value
        raise MacroSourceError(f"fred had no recent numeric observation for {series_id}")

    def __call__(self) -> str:
        parts: list[str] = []
        as_of = ""
        for series_id, label, unit in self._series:
            date_str, value = self._fetch_latest(series_id)
            as_of = max(as_of, date_str)  # newest observation date across the set
            shown = f"{value:+.2f}" if label == "10y-2y" else f"{value:.2f}"
            parts.append(f"{label} {shown}{unit}")
        summary = "Makroläge (FRED, " + as_of + "): " + ", ".join(parts) + "."
        logger.debug("fred.macro built summary len=%d as_of=%s", len(summary), as_of)
        return summary
