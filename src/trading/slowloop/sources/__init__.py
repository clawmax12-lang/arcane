"""Real slow-loop vendor adapters (Inc-8.6) — the keys finally ring.

These adapters implement the agents' INJECTED source seams (``NewsSource``, ``MarketSummarySource``)
with real Tavily / Apify / FRED transports, mirroring ``data/polygon_universe.py`` discipline: a
throttle that SLEEPS (not fails), a typed fail-closed error on ANY 429/timeout/non-200/malformed
(never a partial/fabricated set), and a token that lives ONLY in the request header/params and is
never logged. They live INSIDE ``trading.slowloop`` so they stay outside the deterministic submit
path (PHI1) — proven by ``tests/unit/test_inc8_boundary.py``. They import NO broker symbol.
"""
