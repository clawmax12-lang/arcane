# ARCANE — Current State & Resume Pointer

> **If you (a future/compacted session) remember nothing else, read this file, then
> `docs/adr/ADR-001-foundation.md`, then run `make inc1`.** This is the canonical,
> version-controlled state so the process is never lost to a context compaction.

**As of:** 2026-06-22 · **Branch:** `build/increment-2-data` — pushed; `main` fast-forwarded to it on GitHub.
**Head:** `45d292a` · `make inc1` AND `make inc2` → PASS (97.0% cov, `mypy --strict`, leak-lint clean). **✅ INCREMENT 2 SEALED** — all STEPs 0–8 done, live-proven, comprehensive sealing red-team complete (no confirmed live leak), all fix-now remediated. **NEXT (a future run, NOT started): Increment 3 — factors (10–15, lean).**

---

## 🌙 Autonomous overnight run — ✅ COMPLETE 2026-06-22 (scope: "Finish Increment 2" — DONE; STOPPED as instructed)

All four phases done; Increment 2 is SEALED. The run STOPPED here — Increment 3 was NOT started.

1. ✅ **STEP 8 DONE** (commit `8d213bf`) — `data/prefix_stability.py` (registry-wide
   `compute(df[:k]) == compute(df[:k+1])[:k]`, fail-closed, proven to CATCH leaky factors) +
   `data/leak_lint.py` (AST ban-list: DATE_TRUNC `.date()`/`.normalize()`/`.floor(freq)`,
   GET_CALENDAR outside `calendar.py`, IMPUTATION `.fillna/.ffill/.bfill`, MODULE_TICKERS; AST not
   substring; **whitelists** `session_label_for_daily_bar`/`daily_bar_instant`). `leak-lint` wired
   as an explicit `make inc2` step; prefix-stability runs in the gated pytest suite.
2. ✅ **Comprehensive sealing red-team DONE** — Workflow `wf_84eb8983-25d` was throttled by a
   transient server-side rate limit (NOT a usage limit); SURV lens completed with 2 findings, both
   confirmed by 2 independent adversarial verifiers; remaining lenses finished by single-threaded
   main-loop review of the new STEP-7/8 surface; unchanged files already certified by
   `wf_d4deb502-ad8`. **Verdict: no confirmed live leak.** Full triage: `docs/INC2-HARDENING-BACKLOG.md`.
3. ✅ **Remediated all fix-now** (commit `45d292a`): SURV-1 `membership_vintage<=as_of` guard +
   T2-evidence auditability; LEAKLINT-WL calendar-scoped DATE_TRUNC whitelist. Both TDD, gated.
4. ✅ **Increment 2 SEALED.** STOPPED. Increment 3 NOT started (per the run's hard stop).

Discipline held EVERY step: TDD → `make inc1 && make inc2` green → commit → push → fast-forward
`main` → update this file + project memory.

---

## Where we are

```
✅ Onboarding   5 keys verified (Alpaca paper, Anthropic, Tavily, Firecrawl+MCP, Apify)
✅ ADR-001      architecture decided (edge-falsification harness; paper-only; lean scope)
✅ Inc 1        SAFETY SPINE — built, TDD, and CERTIFIED by 3 adversarial red-team passes
✅ Inc 2        Alpaca data spine — STEPs 0–8 DONE, live-proven, sealing red-team complete, SEALED
⬜ Inc 3        Factors (10–15, lean)   ← NEXT (a future run; NOT started)
⬜ Inc 4        Strategies + backtest
⬜ Inc 5        Bias-gate + FIRST paper submit   (needs Discord paging webhook first)
⬜ Inc 6        Regime + allocator
⬜ Inc 7        Agents + orchestration
⬜ Inc 8        Dashboard (Layer 15 — the LAST layer; a real UI needs the engine first)
```

Honest scope (ADR-001): Inc 1–8 ≈ 55–90 focused build+test hours + a mandatory 14-day paper soak.
**The executor is currently a NO-OP** — `broker_paper.submit()` raises NotImplementedError; nothing trades.

## Increment 2 — SEALED (what's done); Increment 3 is the next run (NOT started)

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

**STEP 8 DONE** (commit `8d213bf`). `data/prefix_stability.py`: registry-generic look-ahead
property `compute(df[:k]) == compute(df[:k+1])[:k]`, pure/typed/fail-closed (raise·length·type·
index·dtype divergence ⇒ VIOLATION), generic over any iterable of computations so Inc-3
`AlphaFactor` plugs in with zero rework (`validate_all()` calls `check_registry`); tests prove
TEETH (full-series-z / centered-window / future-shift / normalize-by-last all CAUGHT).
`data/leak_lint.py`: AST ban-list over `data/` — DATE_TRUNC (`.date()`/`.normalize()` 0-arg,
`.floor(freq)`), GET_CALENDAR (outside `calendar.py`), IMPUTATION (`.fillna/.ffill/.bfill`),
MODULE_TICKERS (≥3 ticker-shaped literals); AST not substring (proven NOT to trip on
`schema.validate(df)`, `unicodedata.normalize(form,s)`, `np.floor(arr)`); whitelists
`session_label_for_daily_bar`/`daily_bar_instant`. `leak-lint` is an explicit `make inc2` step;
prefix-stability runs in the gated pytest suite.

**SEALING RED-TEAM COMPLETE + REMEDIATED** (commit `45d292a`). Comprehensive adversarial pass over
the whole layer incl. universe + STEP 8 (Workflow `wf_84eb8983-25d` was throttled by a transient
server-side rate limit, NOT a usage limit; SURV lens completed with 2 findings confirmed by 2
independent verifiers; the rest finished by single-threaded main-loop review of the new STEP-7/8
surface; unchanged files already certified by `wf_d4deb502-ad8`). **Verdict: no confirmed live
leak.** Two cheap in-scope hardenings of existing guards remediated (TDD, gated): **SURV-1**
`UniverseMeta` now rejects a `membership_vintage` after `as_of` (mirrors `pit_guard`/`AsOf`) + T2
records the vintage in evidence; **LEAKLINT-WL** the DATE_TRUNC whitelist is now scoped to
`calendar.py` only. Everything else deferred to the Polygon/Inc-3 increment or documented WON'T-FIX.
Full triage: `docs/INC2-HARDENING-BACKLOG.md`.

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

**NEXT (a FUTURE run — NOT started this session): Increment 3 — factors (10–15, lean).** Increment 2
is sealed; do not reopen it without cause. When you start Inc 3: the `AlphaFactor` base registers
its factors with `prefix_stability.check_registry` (zero rework), extend `leak_lint` to scan the
factor layer (and add `.shift(<neg>)`/`.rolling(center=True)`/`.resample()` bans there), and clear
the Inc-3-targeted DEFERs in `docs/INC2-HARDENING-BACKLOG.md` (SURV-2 vintage-threading, real
PolygonUniverse, prefix-stability frame-adequacy contract).

Carried DEFER (recorded in `docs/INC2-HARDENING-BACKLOG.md`):
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
