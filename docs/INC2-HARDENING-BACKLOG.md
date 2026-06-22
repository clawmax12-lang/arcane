# Increment 2 — Data-Layer Hardening Backlog

**Source:** adversarial red-team workflow `wf_d4deb502-ad8` (9 specialist lenses → adversarial
verify → synthesis), 2026-06-21. 28 findings raised, 28 survived verification, deduped to ~9 distinct
issues. **Lead triage** below is by Claude this session, re-checked against the actual code (not a
rubber-stamp of the panel). Two items intentionally OVERRIDE the panel's verdict (marked).

## Verdict
Core PIT/leak guarantees are **sound today**: `pit_guard` is base-owned; the `@final` pipeline
re-derives dtype/PIT/quality/schema; no imputation/ffill exists; on Alpaca's real midnight-ET
daily-bar convention every session/ingest_ts derivation is correct. **No verified finding is a live
data leak.** All are latent robustness / fail-closed-taxonomy / contract-vs-reality / observability
gaps — to close before Increment 3 wires the consuming (factor/backtest/scheduler) layers.

## ⚠️ CRITICAL DESIGN CORRECTION (supersedes INCREMENT-2-DESIGN §6)
§6 prescribes deriving sessions via `minute_to_session(direction="previous")` and AST-banning
`.date()`. For **midnight-ET daily-bar labels that is WRONG**: midnight-ET is *before* the session
open, so `minute_to_session(previous)` maps each bar to the PRIOR session = a real ~1-day
look-ahead. **DO NOT** swap the loader's `.date()` to `minute_to_session`. Correct approach: a
fail-closed midnight-ET assertion + a dedicated calendar daily-bar-label helper; STEP-8 leak-lint's
`.date()` ban must whitelist that helper.

## FIX NOW (before Increment 3)
1. **[HIGH] ALPACA-001 — transport.** VERIFIED: alpaca-py 0.43.4 uses `requests` (common/rest.py),
   not httpx; `_fetch` catches `httpx.HTTPError` → live network errors escape uncaught. Catch
   `requests.exceptions.RequestException`; fix the test to raise the real transport class.
2. **[MED] CAL-001/PIT-1 — session derivation.** Add fail-closed midnight-ET + real-session
   assertion in `_fetch`; add a calendar daily-bar-label helper (removes hand-rolled `.date()`).
   Do NOT use `minute_to_session` (see correction).
3. **[MED] PIT-2/QG-002 — empty after session mask.** Raise `DataFetchError` after the mask +
   tz-safe empty `ingest_ts` stamp (today it escapes as a raw `TypeError`).
4. **[MED] SURV-1 — feed/SIP provenance.** `is_sip_consolidated` is caller-`feed`-derived; pin it:
   `SUPPORTED_FEEDS` allow-list (reject unsupported feed → `FeedMismatchError`) + class-attr
   `IS_SIP_CONSOLIDATED`.
5. **[MED] PIT-3 — ordering.** Restore design step (h): `assert_utc` BEFORE stamping/`pit_guard` so a
   tz-naive `_fetch` fails closed with `CalendarError`, not a raw `TypeError`.
6. **[MED] CACHE-001/CACHE-002 — cache robustness.** Implement ADR-F7 disk-under-threshold cache
   pause + warn; clean `.parquet.tmp` orphans in `_reconcile()`.
7. **[LOW, clean] PIT-4/MAINT-001 — wire `read_dotenv`.** Make `load_settings` fall back to `.env`
   (os.environ wins) so `pytest -m live` authenticates. **[OVERRIDE panel "won't-fix":** orphaned
   code contradicting docs is a smell; fix is small, backward-compatible, tested.]
8. **[MED] Doc honesty.** Correct overstated claims: `coverage_degraded`/G4 is reported-not-enforced;
   leak-lint + prefix-stability NOT yet in `make inc2` (STEP 8); fix design §6 per the correction.

## DEFER (with target increment)
- coverage_degraded **G4 end-to-end** (BarMeta field + expected-grid + integration test) → STEP 7.
- **Structured logging / metrics** (cache hit/miss, pit-drop count, fetch latency, silent
  corrupt-evict, DataFetchError) → dedicated observability pass. **(Operator priority — do early.)**
- **PIT-empties-all-rows semantics** (empty LoadResult vs typed `PITEmptyError`) + test → STEP 7.
- **Structural TEXTUAL-loader sanitize() enforcement** (sealed `TextualLoader` base / leak-lint
  rule) → first TEXTUAL source increment.
- **Cache key-format validation** (path-traversal hardening) → with STEP-8 leak-lint (keys are
  SHA-256 today, so not currently reachable).
- **Error-taxonomy reconciliation** (design §12 names vs `errors.py`) + fate of dead guards → STEP 8.
- **[OVERRIDE panel "fix-now" ARCH-002]** Move RTH/session filtering into the `@final` base → DEFER
  to STEP 7 when a 2nd loader exists; correctness is guarded now by #2's assertion, and a speculative
  base refactor with one consumer risks premature/wrong abstraction (midnight-ET subtlety proves
  base daily-labeling is non-trivial).

## WON'T FIX (subsumed / by design)
- **CAL-003** (NotSessionError untyped) — subsumed by #2's midnight-ET guard (a non-session daily bar
  can no longer reach the stamp).

---

# Comprehensive sealing red-team (2026-06-22, before sealing Increment 2)

**Method (honest):** a Workflow red-team (`wf_84eb8983-25d`, 10 lenses → 2 diverse skeptics/finding →
synthesis) was launched but the Anthropic API was under a **transient server-side rate limit** ("not
your usage limit") that killed most finder/verify agents across two attempts. Wave-1 completed and the
**SURV lens produced two findings, both confirmed real by two independent adversarial verifiers**
(reachability + exploit). The remaining lenses were then completed by a **single-threaded main-loop
adversarial review** (rate-limit-safe) focused on the genuinely-new STEP-7/STEP-8 surface
(`universe.py`/`expected_grid`, `prefix_stability.py`, `leak_lint.py`, the STEP-7 calendar helpers);
the unchanged files (loader/alpaca/calendar/cache/quality/pit/schema/sanitize) were already certified
by the prior red-team `wf_d4deb502-ad8` (no live leak) and re-grepped clean here.

## Verdict
**No confirmed LIVE leak in the shipped Increment-2 system.** The core PIT / look-ahead / survivorship
guarantees hold structurally. Two cheap, in-scope, zero-risk hardenings of *existing* guards qualified
as fix-now and were remediated before sealing; everything else is latent (needs a future consumer) and
deferred.

## FIX NOW — DONE (remediated this pass)
1. **[SURV-1] `UniverseMeta` forward-dated vintage.** `__post_init__` enforced the vintage *presence*
   tripwire but not its *ordering*, so a future-dated `membership_vintage` was constructible —
   asymmetric with `pit_guard` (ingest_ts≤as_of) and `AsOf` (reject-future). Confirmed real by 2
   verifiers (unreachable today: no PIT source ships and the `@final` builder never threads a vintage,
   so it would hit `RestatedMembershipError` first — but it is the next obvious fake-PIT variant the
   tripwire missed). **Fixed:** added the `membership_vintage ≤ as_of` guard (any non-None vintage,
   defense-in-depth) + recorded `membership_vintage` in the T2 evidence dict for auditability + tests.
2. **[LEAKLINT-WL] DATE_TRUNC whitelist was name-only, not calendar-scoped.** A same-named helper
   (`session_label_for_daily_bar`/`daily_bar_instant`) in any other `data/` module would have received
   the truncation-primitive pass. **Fixed:** the whitelist now applies only inside `calendar.py`
   (faithful to the spec's `calendar.` prefix; the calendar is the sole session authority) + test.
   (No behaviour change on real `data/` — the calendar helpers use only `.tz_localize/.tz_convert`,
   never a banned primitive — this purely removes a latent hole.)

## DEFER (real but latent — to the Polygon / Increment-3 factor increment)
- **[SURV-2] Thread `membership_vintage` through the `@final` base + AST-ban direct `UniverseMeta(...)`
  construction.** Today a future `POLYGON_PIT` subclass would always raise (the base has no vintage
  channel), and no AST rule bans hand-minting a meta outside `as_of_members`. Both verifiers say DEFER:
  landing the vintage API now pre-designs for a source whose shape isn't final (scope creep), and the
  AST ban alone "only blocks the future author harder." Ship both halves with the real PolygonUniverse.
- **Extend `leak_lint` to the factor layer (Inc-3) and add `.shift(<neg>)`, `.rolling(center=True)`,
  `.resample()`, `.reindex(+fill)` bans there.** These look-ahead primitives are out of `data/`'s scope
  today (none present) and are already caught at runtime by the prefix-stability property for factors;
  the static ban adds value once the factor layer exists and `leak_lint` scans it.
- **`prefix_stability` frame-adequacy contract.** `first_violation` is vacuous on frames with <2 rows
  and `check_registry` does not enforce a minimum frame size / count; harmless today (empty registry),
  but Inc-3's `validate_all()` should pass a panel of adequately-long frames (and may sample `k` to
  avoid the O(n²) recompute on long series). Document the contract when factors register.
- **`expected_grid` tz-aware bounds robustness.** `sessions_in_range(start, end)` is exercised only via
  the (not-yet-wired) G4 coverage path; tz-aware bounds vs the calendar's tz-naive sessions is an
  untested edge. Revisit when `quality.coverage_report` is actually enforced.
- (carried, unchanged) alpaca-py non-UTC `start/end` mis-clamp; structured-logging/metrics unification;
  PIT-empties-all-rows semantics; cache key-format path-traversal; error-taxonomy reconciliation; real
  `PolygonUniverse` / `AlpacaTodayUniverse`.

## WON'T FIX (by design, documented)
- **Empty `prefix_stability` registry is a vacuous pass today.** Honest: there are no factors in
  Increment 2. The leak-catching *teeth* are proven by the STEP-8 tests (every classic leak shape is
  caught); Inc-3 factors register via `check_registry` with zero rework.
- **`leak_lint` static-bypass (alias `d=ts.date;d()`, `getattr(ts,"date")()`).** `leak_lint` is an
  AST smell-catcher, not an adversarial sandbox; the **runtime prefix-stability property is the real
  guarantee** (ADR §7). The bypasses are not present in `data/` and would be caught at runtime in a
  factor. Documented rather than chased.
