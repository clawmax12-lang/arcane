# ARCANE — Current State & Resume Pointer

> **If you (a future/compacted session) remember nothing else, read this file, then
> `docs/adr/ADR-001-foundation.md`, then run `make inc1`.** This is the canonical,
> version-controlled state so the process is never lost to a context compaction.

**As of:** 2026-06-22 · **Branch:** `build/increment-2-data` — pushed; `main` fast-forwarded to it on GitHub.
**Head:** `f032218` · `make inc1` AND `make inc2` → PASS (~96.8% cov, `mypy --strict`). STEP 6 live-proven; red-team remediated; **STEP 7 (PIT universe + T2 + G4) DONE.**

---

## Where we are

```
✅ Onboarding   5 keys verified (Alpaca paper, Anthropic, Tavily, Firecrawl+MCP, Apify)
✅ ADR-001      architecture decided (edge-falsification harness; paper-only; lean scope)
✅ Inc 1        SAFETY SPINE — built, TDD, and CERTIFIED by 3 adversarial red-team passes
🔄 Inc 2        Alpaca data spine — STEPs 0–7 DONE (+ red-team-hardened, live-proven); STEP 8 next  ← HERE
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

**RED-TEAM COMPLETE** (`wf_d4deb502-ad8`, 9 lenses → adversarial verify → synth; 28 findings → ~9
issues; core PIT/leak guarantees were sound, no finding was a live leak). **All 8 `fix_now` items
REMEDIATED, gated, committed:** ALPACA-001 transport (`requests`, not httpx — was an uncaught
network-failure hole) · midnight-ET fail-closed session assertion via `calendar.session_label_for_daily_bar`
(replaced silent session-filtering) · empty/non-session fail-closed · `assert_utc` before stamping ·
feed/SIP provenance pinned (`SUPPORTED_FEEDS` + `IS_SIP_CONSOLIDATED`) · cache ADR-F7 disk-low pause +
`.parquet.tmp` cleanup · `read_dotenv` wired into `load_settings` (live auth works) · doc honesty
(G4 not wired; design §6 daily-label correction). Full triage + DEFER / WON'T-FIX: `docs/INC2-HARDENING-BACKLOG.md`.

**STEP 7 DONE** (design panel `wf_cf814eed-72a` → build, commits `12ce785`/`f032218`).
`data/universe.py` + `universe_sources.py`: PIT universe with survivorship-cleanliness STRUCTURALLY
UNREACHABLE (`SourceTier`+`TIER_IS_PIT` authority; forge-proof derived `survivorship_unverified`;
`@final as_of_members` derives the verdict from the subclass tier; `survivorship_t2` always
`passed=False`; no-hardcoded-list AST guard + content-hash). `OperatorFileUniverse` reads
content-hashed `config/universe.yaml` (honest non-PIT). `expected_grid` wired the deferred **G4**
coverage report (PIT-honest, DST-correct). Observability via stdlib logging. 40+ invariant tests.

**NEXT = STEP 8** — `data/prefix_stability.py` (registry-wide `compute(df[:k]) == compute(df[:k+1])[:k]`
property) + `data/leak_lint.py` (AST ban-list: `.date()`/`.floor`/`.normalize`/`get_calendar` outside
`calendar.py`, module-scope ticker literals — **whitelist** `calendar.session_label_for_daily_bar` /
`daily_bar_instant`), both wired into `make inc2`. Then the **comprehensive data-layer red-team**
(incl. universe + STEP 8) before Increment 3. Remaining DEFERs in `docs/INC2-HARDENING-BACKLOG.md`
(AlpacaTodayUniverse, real PolygonUniverse, full structured-logging unification, PIT-empties semantics).

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
