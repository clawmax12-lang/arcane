# ARCANE — Current State & Resume Pointer

> **If you (a future/compacted session) remember nothing else, read this file, then
> `docs/adr/ADR-001-foundation.md`, then run `make inc1`.** This is the canonical,
> version-controlled state so the process is never lost to a context compaction.

**As of:** 2026-06-23 · **Branch:** `build/increment-4-backtest` — pushed; `main` fast-forwarded to it.
**Head:** `b5739e5` (last code commit; this STATE+backlog+memory seal sits on top) · `make inc1` AND
`inc2` AND `inc3` AND `inc4` → PASS (97.67% cov, `mypy --strict`, leak-lint clean over data + factors +
backtest). **✅ INC 2 SEALED** (`22cc76f`). **✅ INC 3 SEALED** (`2512d3f`). **✅ INCREMENT 4 SEALED +
RE-AUDITED** — strategies + walk-forward backtest done, design-panel-driven, red-team-hardened across TWO
independent rounds; round 2 found + fixed 3 reachable fail-opens (ruin-aware stats + WF overlap reject,
`b5739e5`). **NEXT (a future run, NOT started): Increment 5 — the bias/kill gate (DSR/PSR/PBO/Reality-Check,
ALL-of accept-or-kill) + the FIRST paper submit.**

## ✅ Increment 4 — strategies + walk-forward backtest (SEALED)

Design panel `wf_6158e014-a7e` (4 lenses + synthesis) → `docs/INCREMENT-4-DESIGN.md`; **checkpoint all 4
operator criteria FALSE → autonomous** (conservative/standard cost; standard de-Prado purged+embargoed
12/3/3 anchored; 4 strategies; no ADR change / Inc-5 NOT pulled). New sibling pkg `src/trading/backtest/`.
TDD build, 9 clusters green + committed, then red-team + remediate + seal:
1. C1 `06d3ed1` — `errors.py` (`BacktestError`(ArcaneError) sibling) + `make inc4` gate.
2. C2 `984c3fc` — frozen `StrategySpec`/`FactorLeg`; `spec_hash` = SHA-256 over canonical JSON with
   lossless `float.hex()`; structurally no threshold field (`extra=forbid`).
3. C3 `ff1b4f4` — `resolve_spec` + `FactorRegistry.get` fail-closed (`UnknownFactorError`); phantom
   `factor_id` can't reach `run`.
4. C4 `bff19b6`/`0eeae7f` — conservative `CostModel` (~6 bps floor, `cost_scale≥1`, turnover-driven,
   no zero/neg fill; the M3 defense).
5. C5 `bc94f28` — `walk_forward.py` purged+embargoed 12/3/3 anchored splitter (prefix-stable, disjoint OOS).
6. C6 `a928562` — compute-only `statistics.py` + `BacktestResult` (NO verdict field) + AST verdict name-ban.
7. C7 `f44e035` — `ledger_integration.py` (REUSE `TrialLedger`, kind=strategy, `n_trials` 13→17) + the 4
   default strategies + `PositionMode`.
8. C8 `dbcd1af` — `@final BacktestEngine.run()`: ONE execution `shift(1)` + factor `shift(1)`, pnl
   `position.shift(1)*close.pct_change()-cost` (all trailing); GUARD A/B, warmup+value adequacy, as_of
   PIT re-check, net≤gross; `PositionView`/`RealizedView` causality adapters + perfect-foresight off-by-one
   MUST-FAIL canary.
9. C9 `dc2a08e`/`d49411e` — 4-strategy end-to-end integration + leak_lint backtest-root teeth; engine 100%.

**RED-TEAM COMPLETE + REMEDIATED** (`8915ec3`). Workflow `wf_60bf76b3-d42` (6 finder lenses / 2 waves of 3,
all alive, empirical repros; **not throttled** this run). **Verdict: no reachable look-ahead leak and no
reachable Inc-5 boundary violation** — the off-by-one is load-bearing (mutation-confirmed), join causal,
`BacktestResult` verdict-free, cost conservative+monotone, `n_trials` identity field-complete. **4 fix-now
remediated** (lead-verified by own repros, TDD+gated): RT03 `pct_change(fill_method=None)`; M3-COST-01
`total_bps` non-finite fails closed; skeptic-1 explicit train-free `oos_*` stats (headline documented
full-sample); F1 corrected design §7 (prefix-stability does NOT catch a dropped exec shift — the
value-test + canary do). Full triage + DEFER (Inc-5 tripwires) / WON'T-FIX: `docs/INC4-HARDENING-BACKLOG.md`.

**RED-TEAM ROUND 2 — independent re-audit + REMEDIATED** (`b5739e5`). On operator request, a fresh 6-lens
Workflow `wf_618edde8-565` re-audited the seal. Finders ran (25 findings) but **Verify/Synth were 100%
rate-limited** (infra) — so material findings were verified single-threaded with own repros (NOT treated
as a clean pass; `insight-autonomous-quality-discipline`). **3 reachable fix-now remediated** (TDD+gated):
NUM-2 `annualized_sharpe` scored a WIPED fold (`net ≤ -1.0`, reachable on a short into a >100% bar) as a
strong POSITIVE; NUM-1/3 `max_drawdown` reported a false `0.0` on ruin; WF-1 `step_months < test_months`
double-counted overlapped OOS sessions. Fix: ruin-aware stats (Sharpe/CAGR→NaN, total/max_dd→`-1.0`,
never a win) + `WalkForwardConfig` rejects `step < test`. Nil practical impact on the shipped large-cap
config, but these are the exact stats Inc-5's gate consumes (ADR §0). Lead's own deterministic probes
(ledger=17, cost floor/monotone, verdict-free, causal-join teeth, end-to-end honest noise-Sharpes)
re-confirmed clean. See `docs/INC4-HARDENING-BACKLOG.md` → "Red-team ROUND 2".

**NEXT (a FUTURE run — NOT started): Increment 5 — the ALL-of bias/kill gate + FIRST paper submit.** The
Inc-4 DEFERs Inc-5 must clear FIRST: (1) fold cost/fold-geometry into the trial identity before the DSR
consumer reads `n_trials` (M18); (2) build the monotonic ledger high-water-mark before the first
`n_trials` DSR read; (3) a FITTED consumer must set `purge ≥ max_total_window + label_horizon`; (4) T2
must read `survivorship_biased` (never a clean pass). Discord paging webhook is also a prerequisite for
the first paper submit. Increment 4 is sealed; do not reopen without cause.

## ✅ Increment 3 — alpha factors (SEALED)

Design panel `wf_03e33f11-392` → `docs/INCREMENT-3-DESIGN.md` (WITHIN ADR §5 lean scope, no ADR
change). TDD build, all 5 clusters green + committed; then red-team + remediate + seal:
1. STEP 1 (`f69c905`) — FINAL `AlphaFactor` base (compute() @final, STEP 0–10 + GUARD A–E:
   inf-on-_raw rejected before z, std==0⇒NaN explicit, the one mandatory shift(1)); `factors/errors.py`
   roots at `risk.errors.ArcaneError`; reliability=DERIVED read-only (§4.3).
2. STEP 2 (`5fa9d55`) — SQLite `TrialLedger` (INSERT OR IGNORE PK, structurally monotonic,
   fail-closed on corrupt/missing — the M18 defense; mirrors `executor/idempotency.py`).
3. STEP 3 (`bbb317a`) — the lean **13** standard factors (momentum: mom_21d/mom_63d/mom_126_skip21;
   meanrev: reversal_5d; volatility: vol_21d/atr_14; volume: dollar_vol_21d/rel_volume_21d/
   amihud_illiq_21d; range: hl_range_21d/close_loc_in_range/dist_from_sma_50/sma_ratio_20_50), each
   one NaN-guarded `_raw` (`.where(denom>0)`, `log_safe`); correlated families KEPT (no
   orthogonalization — bias gate prunes). **Trial ledger n_trials = 13.**
4. STEP 4 (`2ec7f9a`) — `FactorRegistry` + `default_registry`; `validate_all` runs prefix-stability
   on BOTH `_raw` AND `compute()` (a power-of-2 future-scale leak is bit-exactly masked on compute()
   yet caught on _raw — proven) + frame-adequacy; forge-proof register (dup/non-DERIVED rejected);
   seeds the ledger with 13 idempotently.
5. STEP 5 (`51faaac`) — `leak_lint` + SHIFT_NEG/CENTERED_ROLLING/RESAMPLE/SORT/interpolate, scan
   widened to factors/; `make inc3` gate created.

**RED-TEAM COMPLETE + REMEDIATED** (`9914b86`). Workflow `wf_5b8d385e-493` (6 finder lenses/2 waves,
all alive, 13 findings); the VERIFY+SYNTH phases were throttled by a transient server-side rate limit
(NOT quota), so the fix-driving findings were verified **single-threaded** in the main loop with
empirical repros (per insight-autonomous-quality-discipline). **Verdict: no confirmed live leak** —
the 13 factors are prefix-stable on _raw AND compute. **8 fix-now hardenings remediated** (TDD,
gated): validate_all now checks the FULL frame (not a depth-slice — closed a length-dependent leak
hole) + absolute-min floor + value-adequacy; GUARD A rejects off-contract dtypes; ledger None-guard;
leak_lint +diff/pct_change-neg, +.floor(freq=kw), +dict-tickers; `_raw` purity documented. Full
triage + DEFER/WON'T-FIX: `docs/INC3-HARDENING-BACKLOG.md`.

**NEXT (a FUTURE run — NOT started): Increment 4 — strategies + backtest.** Increment 3 is sealed; do
not reopen without cause. When Inc 4 starts: `StrategySpec` (frozen, YAML, references only registered
`factor_id`s + regime labels + z-crossings — structurally no hand-coded thresholds); the walk-forward
backtest; bump `n_trials` in the ledger for every factor/param/strategy combo evaluated. The Inc-3
DEFERs to clear: ledger DB-deletion high-water-mark (before the DSR consumer wires n_trials), the
registry-2 author-trust residual, stateful-_raw structural enforcement.

---

### (archived) Increment 3 build pointer — superseded by the seal above
Build complete at `51faaac` (clusters 1–5); red-team + remediation + seal followed.

### (archived) Increment 2 seal pointer
**Head:** `22cc76f` · `make inc1` AND `make inc2` → PASS. **✅ INCREMENT 2 SEALED** — all STEPs 0–8 done, live-proven, comprehensive sealing red-team complete (no confirmed live leak), all fix-now remediated.

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
✅ Inc 3        Factors (lean 13) — built, red-team-hardened, SEALED (`2512d3f`)
✅ Inc 4        Strategies (4) + walk-forward backtest — built, red-team-hardened, SEALED (`8915ec3`)
⬜ Inc 5        Bias-gate + FIRST paper submit   ← NEXT (a future run; NOT started; needs Discord webhook)
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
