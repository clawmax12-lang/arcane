# ARCANE — Current State & Resume Pointer

> **If you (a future/compacted session) remember nothing else, read this file, then
> `docs/adr/ADR-001-foundation.md`, then run `make inc1`.** This is the canonical,
> version-controlled state so the process is never lost to a context compaction.

**As of:** 2026-06-21 · **Branch:** `build/increment-2-data` — pushed; `main` fast-forwarded to it on GitHub.
**Head:** `3d44ead` · `make inc1` AND `make inc2` → PASS (~96.6% cov, `mypy --strict`). **STEP 6 PROVEN on live Alpaca IEX data.**

---

## Where we are

```
✅ Onboarding   5 keys verified (Alpaca paper, Anthropic, Tavily, Firecrawl+MCP, Apify)
✅ ADR-001      architecture decided (edge-falsification harness; paper-only; lean scope)
✅ Inc 1        SAFETY SPINE — built, TDD, and CERTIFIED by 3 adversarial red-team passes
🔄 Inc 2        Alpaca data spine — STEPs 0–6 DONE (STEP 6 proven on LIVE data); red-team running → remediate → STEP 7  ← HERE
⬜ Inc 3        Factors (10–15, lean)
⬜ Inc 4        Strategies + backtest
⬜ Inc 5        Bias-gate + FIRST paper submit   (needs Discord paging webhook first)
⬜ Inc 6        Regime + allocator
⬜ Inc 7        Agents + orchestration
⬜ Inc 8        Dashboard (Layer 15 — the LAST layer; a real UI needs the engine first)
```

Honest scope (ADR-001): Inc 1–8 ≈ 55–90 focused build+test hours + a mandatory 14-day paper soak.
**The executor is currently a NO-OP** — `broker_paper.submit()` raises NotImplementedError; nothing trades.

## Exact next step (Increment 2 — STEP 7 of 9)

**IN FLIGHT:** data-layer adversarial red-team (Workflow `wf_d4deb502-ad8` — 9 specialist lenses →
adversarial verify → prioritized backlog). **Remediate its verified `fix_now` backlog BEFORE STEP 7.**
STEP 6 is now proven end-to-end on live IEX data; the vendor pydantic-`TzInfo(0)` bug is fixed by a
structural tz-canonicalization in the `@final` base loader (commit `3d44ead`). Known-open suspect the
audit will rule on: `settings.read_dotenv()` is orphaned, so `pytest -m live` can't auth from `.env`.

Full design + build plan: `docs/INCREMENT-2-DESIGN.md`. DONE & committed: STEP 0 deps+gate ·
STEP 1 reliability+errors · STEP 2 bar schema+BarMeta+IEX stamp · STEP 3 calendar(side='left'
half-open RTH)+quality gate · STEP 4 PIT guard + content-addressed Parquet cache · STEP 5 FINAL
`@final` `DataLoader` · STEP 6 `AlpacaBarLoader` (real IEX daily `_fetch` + contract tests,
network faked; one `live` smoke behind `pytest -m live`).

⚠️ FIXED THIS SESSION (commit `d917b25`): `.gitignore` line 19 was an UNANCHORED `data/` that
matched `src/trading/data/` and silently UNTRACKED the entire data layer — the STEP 2–5
`feat(data)` commits contained ONLY test files, zero implementation. A `git clean -fdx` or a
fresh clone would have destroyed all of Inc-2 while `make inc2` stayed green on the on-disk
files. Now anchored to `/data/` + `/logs/`; all 11 `src/trading/data/*.py` (incl. the Inc-1
`sanitize.py`) are tracked (rescue `d917b25`, STEP 6 tests `945557c`). **If you ever see a green
gate but `git ls-files` is missing a source dir again — this is the footgun; check `.gitignore`.**

**NEXT = STEP 7** — `src/trading/data/universe.py`: a point-in-time universe whose survivorship
bias-test returns `passed=False` (we have no PIT membership history → the universe is DEGRADED,
never silently survivorship-clean). Then STEP 8 (`data/prefix_stability.py` registry-wide
hypothesis + `data/leak_lint.py` AST ban-list — incl. banning `xcals.get_calendar` outside
`calendar.py`, per its docstring — both wired into `make inc2`). Then **red-team the data layer**
(look-ahead / survivorship / staleness / cache-poisoning) before Increment 3.

Data-layer red-team backlog (found, not yet hardened):
- alpaca-py `StockBarsRequest` STRIPS tzinfo (stores naive UTC wall-clock). `_fetch` passes UTC
  today so it is safe, but a non-UTC tz-aware `start`/`end` would be silently mis-clamped.
  Consider asserting/converting the window to UTC in `LoadParams.build` or `_fetch`.

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
