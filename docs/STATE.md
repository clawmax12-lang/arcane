# ARCANE — Current State & Resume Pointer

> **If you (a future/compacted session) remember nothing else, read this file, then
> `docs/adr/ADR-001-foundation.md`, then run `make inc1`.** This is the canonical,
> version-controlled state so the process is never lost to a context compaction.

**As of:** 2026-06-21 · **Branch:** `build/increment-2-data` (off `main`, NOT pushed)
**Head:** `510df2a` · `make inc1` AND `make inc2` → PASS (222 tests, 97% cov, `mypy --strict`).

---

## Where we are

```
✅ Onboarding   5 keys verified (Alpaca paper, Anthropic, Tavily, Firecrawl+MCP, Apify)
✅ ADR-001      architecture decided (edge-falsification harness; paper-only; lean scope)
✅ Inc 1        SAFETY SPINE — built, TDD, and CERTIFIED by 3 adversarial red-team passes
🔄 Inc 2        Alpaca data spine — STEPs 0–5 of 9 DONE (structural spine); STEP 6 next  ← HERE
⬜ Inc 3        Factors (10–15, lean)
⬜ Inc 4        Strategies + backtest
⬜ Inc 5        Bias-gate + FIRST paper submit   (needs Discord paging webhook first)
⬜ Inc 6        Regime + allocator
⬜ Inc 7        Agents + orchestration
⬜ Inc 8        Dashboard (Layer 15 — the LAST layer; a real UI needs the engine first)
```

Honest scope (ADR-001): Inc 1–8 ≈ 55–90 focused build+test hours + a mandatory 14-day paper soak.
**The executor is currently a NO-OP** — `broker_paper.submit()` raises NotImplementedError; nothing trades.

## Exact next step (Increment 2 — STEP 6 of 9)

Full design + build plan: `docs/INCREMENT-2-DESIGN.md`. DONE & committed: STEP 0 deps+gate ·
STEP 1 reliability+errors · STEP 2 bar schema+BarMeta+IEX stamp · STEP 3 calendar(side='left'
half-open RTH)+quality gate · STEP 4 PIT guard + content-addressed Parquet cache · STEP 5 FINAL
`@final` `DataLoader` (structural PIT pipeline). `make inc2` green (222 tests, 97%).

**NEXT = STEP 6** — `src/trading/data/alpaca_loader.py` (`AlpacaBarLoader(DataLoader)`, `_fetch`
ONLY; verified alpaca-py 0.43.4 API in design §5): `StockHistoricalDataClient(api_key/secret from
`trading.settings`, raw_data=False, NO paper arg)`, `StockBarsRequest(timeframe=TimeFrame(1, Day),
feed=DataFeed.IEX, adjustment=Adjustment.ALL, sort=Sort.ASC, limit=None)`, `.df` → drop the symbol
MultiIndex level, rename `timestamp`→`ts`, stamp feed/reliability; clamp `end <= now-16min` (IEX
403 foot-gun); empty → `DataFetchError`; wrap `APIError`/`httpx.HTTPError` → `DataFetchError`.
Override `_align_calendar` for daily session validity. Mock the network via a recorded fixture; put
the one live call behind the `live` pytest marker (excluded from `make inc2`).
Then STEP 7 (`data/universe.py` — PIT universe DEGRADED, survivorship bias-test returns
`passed=False`) and STEP 8 (`data/prefix_stability.py` registry-wide hypothesis + `data/leak_lint.py`
AST ban-list, both wired into `make inc2`). Then **red-team the data layer** (look-ahead /
survivorship / staleness / cache-poisoning) before Increment 3.

## Non-negotiable invariants (do not regress)

- `LIVE_MODE = false` in config AND code; `paper=True` hardcoded; the LLM is never in the submit path.
- Config can only make risk limits STRICTER than the floor-of-floors (equity $20 / total-loss $30).
- Every error path fails CLOSED; non-finite inputs are rejected at construction.
- Red-team any safety/money-path code until an adjudicator certifies no reachable fail-open.

## Where the detail lives

- `docs/adr/ADR-001-foundation.md` — binding architecture decisions + rationale.
- `docs/RISK_REGISTER.md` — risk register from the design workflow.
- `CLAUDE.md` — governance (axioms, mistake taxonomy, never-do list, abandonment triggers).
- Project memory (`~/.claude/projects/-Users-maxagent-Trade/memory/`) — status + the hard-won
  insights (`insight-adversarial-self-review`, `insight-fail-open-patterns`, build conventions,
  operator working style). Loaded automatically each session.
- Session log: `~/.claude/session-data/2026-06-21-arcane-inc1-session.tmp`.
