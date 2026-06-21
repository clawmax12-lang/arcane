# ARCANE — Current State & Resume Pointer

> **If you (a future/compacted session) remember nothing else, read this file, then
> `docs/adr/ADR-001-foundation.md`, then run `make inc1`.** This is the canonical,
> version-controlled state so the process is never lost to a context compaction.

**As of:** 2026-06-21 · **Branch:** `build/increment-1-safety-spine` (off `main`, NOT pushed)
**Head:** `b3b7cfb` · `make inc1` → PASS (169 tests, 97% cov, `mypy --strict`).

---

## Where we are

```
✅ Onboarding   5 keys verified (Alpaca paper, Anthropic, Tavily, Firecrawl+MCP, Apify)
✅ ADR-001      architecture decided (edge-falsification harness; paper-only; lean scope)
✅ Inc 1        SAFETY SPINE — built, TDD, and CERTIFIED by 3 adversarial red-team passes
⬜ Inc 2        Alpaca data spine            ← NEXT
⬜ Inc 3        Factors (10–15, lean)
⬜ Inc 4        Strategies + backtest
⬜ Inc 5        Bias-gate + FIRST paper submit   (needs Discord paging webhook first)
⬜ Inc 6        Regime + allocator
⬜ Inc 7        Agents + orchestration
⬜ Inc 8        Dashboard (Layer 15 — the LAST layer; a real UI needs the engine first)
```

Honest scope (ADR-001): Inc 1–8 ≈ 55–90 focused build+test hours + a mandatory 14-day paper soak.
**The executor is currently a NO-OP** — `broker_paper.submit()` raises NotImplementedError; nothing trades.

## Exact next step (Increment 2)

1. Add a `data` dependency-group to `pyproject.toml`: `alpaca-py, numpy, pandas, polars, duckdb,
   pyarrow, httpx`; `uv sync`.
2. Build `src/trading/data/loader.py` — the ADR-001 §7 `DataLoader` contract: FINAL `load()` with a
   content-addressed Parquet cache, schema validation, staleness detection, tz/RTH alignment, and a
   point-in-time leak guard (`ingest_ts <= as_of`). TDD; sanitize TEXTUAL sources at the loader boundary.
3. Wire `broker_paper.submit` to a real alpaca-py paper client constructed with `paper=ALPACA_PAPER`.
4. **Any executor entrypoint MUST call** `trading.executor.preflight.preflight(kill_switch, cfg.live_mode)`
   before its loop (verifies the kill-switch store is writable + asserts paper-only).
5. Define a `make inc2` gate; keep it green; then **red-team the data layer** (leak / staleness /
   cache-poisoning) before Increment 3.

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
