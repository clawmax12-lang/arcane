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
