# Increment 3 — Factor-Layer Red-Team Backlog

**Source:** adversarial red-team Workflow `wf_5b8d385e-493` (6 finder lenses across 2 waves —
factor-leak, trial-ledger, registry/contract, leak-lint-bypass, fail-open-numerics,
adversarial-skeptic — all 6 alive; 13 findings → triaged to 12). 2026-06-22.

**Method (honest, per insight-autonomous-quality-discipline).** The FIND phase succeeded (6/6 finders,
each running empirical Bash repros). The VERIFY (24 prover/refuter agents) and SYNTHESIS phases were
**entirely killed by a transient server-side rate limit** ("Server is temporarily limiting requests
— not your usage limit" = infra, not quota). A rate-limited "0 confirmed" is **NOT** a pass, so the
fix-driving findings were **verified SINGLE-THREADED in the main loop** with my own empirical repros
(`registry-1`, `leak-1`, `ledger-1` all reproduced; `leaklint-1`'s no-runtime-backstop nuance
confirmed across ffill/fillna/bfill/interpolate). The lower-severity completeness items were taken on
the finders' own reproduced evidence and fixed defensively.

## Verdict
**No confirmed LIVE look-ahead leak in the shipped Increment-3 system.** The 13 factors are proven
prefix-stable on BOTH `_raw` and `compute()`; the core leak guarantees (GUARD B inf-rejection, the
single shift(1), the dual prefix-stability gate) hold structurally. Every finding is a gate-rigor
improvement, a fail-closed-posture hardening, or a static-net completeness gap — not a reachable leak
in the honest shipped factors.

## FIX NOW — DONE (remediated in `9914b86`, TDD + gated)
1. **[MED] registry-1 — validate_all per-factor depth-slice missed length-dependent leaks.** My
   speed optimization (`df.iloc[:depth]`) only checked short prefixes; a leak activating at
   `len(df) > depth` slipped. **Reproduced:** a `len>=70` leak PASSED the sliced gate while
   `first_violation` on the FULL 343-row frame caught it at k=22. **Fix:** `validate_all` checks
   prefix-stability on the FULL provided frame (no slice), on both `_raw` and `compute()`.
2. **[MED] registry-2 — adequacy floor trusted author-declared `raw_lookback` (circular).** An
   understated lookback shrinks the floor below the true reach. **Fix:** `floor = max(2*MAX_TOTAL_
   WINDOW+5, ABSOLUTE_MIN=256)` — closes understated reaches up to ~128 even when the declared
   lookback is tiny.
3. **[LOW] failopen-1 — value-degenerate panel ⇒ vacuous gate.** A constant input ⇒ `std==0` ⇒
   GUARD C masks all z to NaN ⇒ an all-NaN output makes the prefix check vacuously true. **Fix:**
   `validate_all` asserts each factor produces ≥1 non-NaN `compute()` value on ≥1 frame, else
   `FrameAdequacyError` (value-adequacy, not just length).
4. **[LOW] leak-1 — GUARD B silently coerced off-contract dtypes.** `to_numpy(dtype="float64")`
   coerces an object Series of numeric strings / bools instead of failing closed. **Reproduced.**
   **Fix:** GUARD A rejects any non-real-numeric dtype (object/bool/complex) before `to_numpy`.
5. **[LOW] ledger-1 — `INSERT OR IGNORE` swallows NOT-NULL, then a None SELECT-back ⇒ bare
   `TypeError`.** **Reproduced** (a NULL insert silently no-ops). **Fix:** a None row raises
   fail-closed `TrialLedgerError` (an under-count is the M18 vector).
6. **[LOW] skeptic-1 — SHIFT_NEG didn't cover `.diff(<neg>)` / `.pct_change(periods=<neg>)`.** These
   are `.shift(-1)` siblings (runtime prefix-stability DOES catch them, so the architecture held —
   completeness gap in the static net only). **Fix:** the negative-period ban now covers shift/diff/
   pct_change.
7. **[LOW] leaklint-3 — `.floor(freq="D")` keyword form and a dict-keyed ticker universe dodged the
   AST checks.** **Fix:** DATE_TRUNC also flags the `freq=` keyword; MODULE_TICKERS also scans dict
   KEYS.
8. **[docs] leaklint-2 / leaklint-4.** `_raw` purity requirement now documented (prefix-stability
   assumes a pure, deterministic `_raw`); the design doc corrected — `.expanding()` / `.ewm()` are
   TRAILING/prefix-stable and correctly NOT flagged (they are permitted, not leaks).

## DEFER (real but latent — needs a future consumer / a bigger design)
- **[ledger-2] DB-file-deletion resets `n_trials` to 0 (no high-water-mark).** The single silent-
  lower-count path that survives (every other corruption form fails closed). Already DEFERRED in the
  ledger docstring — same posture as `kill_switch.json` tampering. **Close before the Inc-4/5 DSR
  consumer wires `n_trials`:** persist a monotonic high-water-mark outside the DB and raise if the
  row count ever drops below it; until then keep the ledger on durable storage.
- **[registry-2 residual] author-trust circularity.** The `ABSOLUTE_MIN=256` floor + full-frame
  check close understated reaches up to ~128; a doubly-adversarial author (understates `raw_lookback`
  AND the true reach exceeds ~128) could still slip. A fully author-trust-free gate would re-derive
  each factor's true reach — over-engineering for the honest single-operator 13; revisit if a factor
  with a >250-bar lookback is added.
- **[leaklint-2 structural] stateful-`_raw` enforcement.** prefix-stability assumes purity;
  `validate_all` computes the full frame first, so a memoizing `_raw` could be seeded with future
  stats. Documented in the `_raw` contract; STRUCTURAL enforcement (a fresh factor instance per
  prefix call) needs a factory protocol on the registry — defer until a real need.
- **[skeptic-2] validate_all is test-only (no production caller).** Correct by design (look-ahead is
  a DEV/gate-time check, not a runtime cost); the committed `test_default_registry_validates_clean`
  runs the FULL `default_registry()` through `validate_all`, so any factor added to `default_factors()`
  is auto-gated. A future author who builds a factor OUTSIDE the canonical list must add it there.

## WON'T FIX (by design / best-effort, documented)
- **[leaklint-1] aliased imputation bypass** (`fn = s.fillna; fn(0)`, `getattr(s,"ffill")()`).
  leak_lint is an AST **smell-catcher, not an adversarial sandbox** (the Inc-2 backlog WON'T-FIX,
  re-confirmed). The DIRECT `.fillna/.ffill/.bfill/.interpolate` ARE caught — the accidental-mistake
  defense. **New nuance:** unlike look-ahead leaks, imputation has **no runtime backstop**
  (ffill/fillna/bfill/interpolate are all prefix-stable in realistic constructions — verified), so
  the direct-form static ban is load-bearing; deliberate aliasing to self-sabotage is out of the
  single-operator threat model and uncatchable by any static linter.
- **leak_lint general static-bypass** (alias / getattr for resample/sort/shift, a variable-`freq`
  `.floor(var)`, a variable negative shift `.shift(-k)`). Same best-effort posture; for look-ahead
  primitives the **runtime prefix-stability-on-`_raw` is the real guarantee** (ADR §7).
