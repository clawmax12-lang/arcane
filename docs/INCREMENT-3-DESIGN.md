# ARCANE Increment 3 — Alpha-Factor Spine Design (decision-grade)

> **Source:** design panel `wf_03e33f11-392` (4 specialist lenses — factor look-ahead/leak,
> quant factor design, architecture/registry/trial-ledger, adversarial skeptic — → synthesis),
> 2026-06-22, adjudicated by the lead this session and re-checked against the real Inc-2 code.
> **Scope verdict: WITHIN ADR-001 §5 lean scope · no ADR change · no operator decision required.**
> Factors are **SIGNAL INFRASTRUCTURE**, not edge claims, not trade decisions (ADR-001 §0 = facit).
> Built honest and lean; the Increment-5 bias gate kills non-survivors. The executor stays NO-OP.

---

## 0. Mandate & invariant

Increment 3 builds the **leak-proof-by-construction alpha-factor layer** on top of the sealed Inc-2
PIT data spine. The single load-bearing principle (ADR-001 §7): **look-ahead correctness is
STRUCTURAL, not disciplinary.** `AlphaFactor.compute()` is `@final`; authors implement only
`_raw(df) -> pd.Series`. The base owns strictly-trailing rolling-z, `clip[-3,3]`, and the **one
mandatory `shift(1)`** so a value at bar *t* uses only data ≤ *t-1*. A look-ahead leak is a *test
failure* (registry-wide prefix-stability run on **both `_raw` and `compute()`**), not a code-review
judgment call.

Mirrors the proven Inc-1/Inc-2 idioms verbatim in intent: the `@final` base where a subclass
implements one hook and the base re-derives every correctness property (`DataLoader._fetch`,
`PITUniverse._members`); the typed fail-closed `ArcaneError` taxonomy; SHA-256 canonical-JSON
content hashing + atomic durable writes (`data/cache.py`, `executor/idempotency.py`); the AST
leak-lint smell-catcher backed by the runtime property as the real guarantee; `mypy --strict`,
ruff/black, ≥85% coverage.

**Reliability:** every factor's output is **DERIVED** (CLAUDE.md §4.3) — advisory, MAY NEVER gate an
order. `reliability` is a read-only base property (no settable field to forge); the registry rejects
any factor whose `reliability` is not `DERIVED`.

---

## 1. RESOLVED CONFLICT (decision · rationale · rejected alternative)

**T1 — trial-ledger store: SQLite vs append-only JSONL.** *DECISION: **SQLite**, mirroring
`executor/idempotency.py` `SqliteIdempotencyStore` (a `PRIMARY KEY` + `INSERT OR IGNORE` =
idempotent at-most-once, restart-safe, crash-durable).* Rationale: ADR-001 §3 explicitly names the
ledger/state store as **SQLite (stdlib), fail-closed, restart-safe**. JSONL has no atomic
single-record commit (a multi-process append over `PIPE_BUF` tears the final line), forces either a
full reparse on every `n_trials()` or a silent under-count on a corrupt line — and **under-counting
`n_trials` deflates the Deflated-Sharpe / M18 overfit penalty, which is the exact fail-open vector
the ledger exists to defend** (insight: *fs reads fail open*). *Rejected:* JSONL-append (no atomic
commit; under-count-on-corrupt is fail-open); a separate persisted high-water-mark file (the SQLite
no-delete API + `INSERT OR IGNORE` PK is structurally monotonic already, and the proven
`idempotency.py` template carries none — a direct DB-file tamper is out-of-API, the same posture as
`kill_switch.json`).

---

## 2. The FINAL `compute()` template (the structural heart) — `factors/base.py`

```python
class AlphaFactor(ABC):
    id: ClassVar[str]                 # unique factor id (registry key)
    rationale: ClassVar[str]          # non-empty canonical economic rationale
    z_window: ClassVar[int] = 21      # strictly-trailing z lookback
    raw_lookback: ClassVar[int]       # the longest trailing offset _raw reaches back (frame-adequacy)

    @property
    def reliability(self) -> Reliability:   # read-only; no settable field to forge (§4.3)
        return Reliability.DERIVED

    @final
    def compute(self, df: pd.DataFrame) -> pd.Series:
        # STEP 0  assert canonical bar index (UTC, monotonic-unique 'ts') + OHLCV cols present
        # STEP 1  raw = self._raw(df)                      # the SOLE author hook
        # GUARD A type/shape/alignment: isinstance Series & raw.index.equals(df.index) & len match
        # GUARD B finiteness-on-_raw (BEFORE z): no +/-inf (NaN allowed) — the CRITICAL guard
        # STEP 4  mean = raw.rolling(z_window, min_periods=z_window).mean()        # trailing, no center
        # STEP 5  std  = raw.rolling(z_window, min_periods=z_window).std(ddof=1)   # ddof pinned
        # GUARD C z = (raw-mean)/std, then z.where(std > 0, pd.NA)   # zero-variance => NaN, never inf
        # GUARD D post-z finiteness assert (NaN allowed)
        # STEP 8  clipped = z.clip(-3, 3)
        # STEP 9  out = clipped.shift(1)                   # THE single mandatory shift (t uses <= t-1)
        # GUARD E out length + index equality + float dtype
        return out

    @abstractmethod
    def _raw(self, df: pd.DataFrame) -> pd.Series: ...     # trailing/same-bar only; NaN-guard divisions
```

`AlphaFactor` satisfies `data/prefix_stability.PrefixComputation` (it has `.id` + `.compute`), so
`check_registry` consumes it with **zero rework**.

### 2.1 Why prefix-stability alone is NOT sufficient — the guards that close what it misses

`prefix_stability` proves *no future dependence*; it does **not** prove *no fabricated signal* and is
**masked** by the wrapper. Three leak/forgery surfaces survive a `compute()`-only property check and
are closed by explicit guards:

| Surface | Why prefix-stability misses it | Closed by |
|---|---|---|
| **inf laundering** (`amihud |ret|/0`, `rel_volume`/0, `sma==0`) | an inf-producing `_raw` is perfectly prefix-stable (`inf==inf` compares equal); inf survives rolling-z to finite-looking values, then `inf.clip(-3,3)` fabricates a saturated **±3 max-conviction** signal | **GUARD B**: assert `not np.isinf(raw.to_numpy(float, na_value=nan)).any()` **before** z-scoring; NaN allowed, inf ⇒ `FactorContractError`. Authors map divisions to NaN via `.where(denom>0)` — never `.fillna/.ffill/.bfill` (banned + fabricating). |
| **leaky `_raw` masked by the wrapper** (e.g. `_raw = close/close.max()`) | a global *rescale* leak is **scale-invariant under z-scoring** → `compute()` is identical with/without it; clip saturation hides large-magnitude leaks; the `min_periods` NaN head compares `NaN==NaN` equal | run `assert_prefix_stable` on **both** a `_raw`-wrapper (`id+'__raw'`) **and** the full `compute()` over the adversarial panel |
| **zero-variance window** (flat series) | `0/0==NaN` is a coincidence, not a guarantee; a non-zero numerator over `std==0` → inf | **GUARD C**: explicit `z.where(std>0, pd.NA)`; **GUARD D** post-z inf assert |

NaN is the **honest undefined/warmup marker** (§4.3 DERIVED honesty) — never imputed, never
fabricated into an extreme.

### 2.2 The single-shift contract (and why "ban `.shift()` in `_raw`" is wrong)

The base applies **exactly one** `shift(1)` — the publication shift moving a signal computed *at t*
to *published at t using ≤ t-1*. `_raw` returns the signal **aligned to bar t** and **MAY** use
**positive** `.shift(n)` as a **trailing lookback offset** (`close.shift(21)` = "close 21 bars ago";
`close.shift(1)` for the log-return / prev-close in `vol_21d`/`atr_14`). So a blanket "no `.shift()`
in `_raw`" ban is **infeasible** — legitimate factors need it. A *double alignment-shift* (an author
adding a second `shift(1)` for publication on top of the base) is a **staleness** bug (the value uses
≤ *t-2*) — it uses only *past* data, so it is **not a look-ahead leak** and prefix-stability correctly
does not flag it. It is caught by **per-factor value tests** (each factor's output at a known bar is
asserted against the hand-computed value). Only **negative** shifts (the actual future leak) are
AST-banned (SHIFT_NEG).

---

## 3. The lean factor set (13, well-known families only — ADR §5)

All standard/textbook, one `_raw` each, correlated families intentionally retained (the Inc-5 bias
gate prunes; **no orthogonalization** — pre-pruning for orthogonality is itself a tuning-toward-profit
move ADR §5 forbids). `z_window=21` for all unless noted. Every division is NaN-guarded with
`.where(denom>0)` so `_raw` never emits inf on real thin-IEX zero-range / zero-volume bars.

| # | id | family | `_raw` (on the canonical OHLCV daily frame) | lookback | rationale |
|---|---|---|---|---|---|
| 1 | `mom_21d` | momentum | `log(close) - log(close.shift(21))` | 21 | 1-month price momentum (Jegadeesh–Titman) |
| 2 | `mom_63d` | momentum | `log(close) - log(close.shift(63))` | 63 | 3-month intermediate momentum |
| 3 | `mom_126_skip21` | momentum | `log(close.shift(21)) - log(close.shift(147))` | 147 | 6-1 skip-a-month momentum (removes 1-mo reversal) — **drives `MAX_TOTAL_WINDOW`** |
| 4 | `reversal_5d` | meanrev | `-(log(close) - log(close.shift(5)))` | 5 | short-horizon mean reversion (Lehmann; Lo–MacKinlay) |
| 5 | `vol_21d` | volatility | `lr.rolling(21).std(ddof=1)`, `lr=log(close)-log(close.shift(1))` | 22 | trailing realized volatility (low-vol/risk) |
| 6 | `atr_14` | volatility | `(TR.rolling(14).mean()/close).where(close>0)`, `TR=max(high-low,|high-pc|,|low-pc|)`, `pc=close.shift(1)` | 14 | Wilder ATR / close (gap-aware range) |
| 7 | `dollar_vol_21d` | volume | `log1p((close*volume).rolling(21).mean())` | 21 | trailing avg dollar volume (liquidity/size) |
| 8 | `rel_volume_21d` | volume | `(v / v.rolling(21).mean()).where(avg>0)`, `v=volume` | 21 | relative volume spike vs own trailing baseline |
| 9 | `amihud_illiq_21d` | volume | `log1p(((|ret|/(close*volume)).where(dv>0)).rolling(21).mean())` | 22 | Amihud (2002) illiquidity — **the inf landmine** |
| 10 | `hl_range_21d` | range | `((high-low)/close).where(close>0).rolling(21).mean()` | 21 | trailing intrabar range (Parkinson-style) |
| 11 | `close_loc_in_range` | range | `((close-low)/(high-low)).where(span>0)` (same-bar) | 0 | close location in bar range (Williams %R / %K) |
| 12 | `dist_from_sma_50` | range | `((close-sma)/sma).where(sma>0)`, `sma=close.rolling(50).mean()` | 50 | distance from 50-day SMA (trend stretch) |
| 13 | `sma_ratio_20_50` | range | `(f/s - 1).where(s>0)`, `f=close.rolling(20).mean()`, `s=close.rolling(50).mean()` | 50 | fast/slow SMA ratio (golden/death-cross state) |

Build assertion: `10 <= len(default_registry) <= 15` (ADR §5 budget; never exceed 15).

---

## 4. Shared registry — `factors/registry.py`

Mirrors the Inc-2 `@final`-base + `check_registry` idiom.

- **`register(factor)`** — assert `isinstance(factor, AlphaFactor)`; reject a duplicate `id`
  (`DuplicateFactorError`); assert `type(factor).reliability is Reliability.DERIVED` else
  `FactorContractError` (forge-proof §4.3, mirrors `universe.py` "no writable field to forge").
- **`validate_all(frames)`** — the **hard gate** (run in a committed pytest):
  1. `MAX_TOTAL_WINDOW = max(raw_lookback + z_window + 1)` over all factors (147+21+1 = **169**);
     raise **`FrameAdequacyError`** if `frames` is empty or any `len(frame) < 2*MAX_TOTAL_WINDOW + 5`
     (**343** rows) — a too-short frame yields all-NaN prefixes that pass *vacuously* (the M4/M18
     false-green vector; clears the Inc-2 "prefix-stability frame-adequacy" DEFER).
  2. `assert_prefix_stable` on **both** a `_raw`-wrapper `PrefixComputation` (`id+'__raw'`) **and**
     the full `compute()` for every factor over every frame (reuses
     `data/prefix_stability.assert_prefix_stable` — zero rework).
- **`default_registry(ledger, ...)`** — constructs the **frozen 13-factor tuple** (literal, order as
  in §3), registers each, and **records each as a trial** into the `TrialLedger` at registration
  (`id` + full params incl. `z_window` + `raw_lookback`). Build-failing `10 <= count <= 15`.

Errors: `factors/errors.py` rooted at **`trading.risk.errors.ArcaneError`** (factors are a *sibling*
layer to the data spine — NOT `data.errors.DataError`, so a factor fault is not mis-bucketed by an
`except DataError`): `FactorError(ArcaneError)` → `FactorContractError`, `DuplicateFactorError`,
`FrameAdequacyError`, `TrialLedgerError`.

---

## 5. Trial ledger — `factors/trial_ledger.py` (the §5 / M18 overfit defense)

**SQLite**, mirroring `executor/idempotency.py`:

- **Schema:** `trials(combo_hash TEXT PRIMARY KEY, kind TEXT, ref_id TEXT, params_json TEXT,
  created REAL)`; `PRAGMA synchronous=FULL` (fsync-durable commits).
- **`combo_hash`** = SHA-256 over canonical `json.dumps({kind, ref_id, params}, sort_keys=True,
  separators=(',',':'))` — the **same** canonical-hash idiom as `data.cache.cache_key` /
  `executor.idempotency` (cross-module consistency). Params canonicalized losslessly; unencodable
  params raise (no `default=str` float coercion that could collide distinct combos).
- **`record(kind, ref_id, params)`** = `INSERT OR IGNORE` (re-recording an existing combo is a no-op).
- **`n_trials()`** = `SELECT COUNT(*)` over distinct combos = the cumulative count of every distinct
  `(kind, ref_id, params)` factor/param combo **ever** evaluated (the DSR/M18 search-breadth
  deflation input; distinct combos, not raw evals — deterministic).
- **MONOTONICITY is STRUCTURAL:** **no** `delete`/`update`/`clear`/`remove` API exists on the type;
  `INSERT OR IGNORE` + PK can only grow or no-op (a test asserts no such attribute exists).
- **FAIL-CLOSED:** a missing / unreadable / corrupt DB raises `TrialLedgerError` (mirrors
  `kill_switch` corrupt ⇒ TRIPPED); `n_trials()` **never** silently returns `0` or a lower count.
  An explicitly-initialized existing 0-row DB legitimately reports `0` (a valid fresh state).

**Documented residual (DEFER to Inc-4/5 sweeps):** a factor *formula rewrite* that keeps the same
`id`+params is **not** counted as a new trial. A code-fingerprint (`inspect.getsource(_raw)`) in
`combo_hash` was **rejected** for Inc-3 — it makes `n_trials` fragile to cosmetic/black reformatting,
breaking the "build-twice ⇒ stable count" invariant. In Inc-3 the 13 factors are fixed and no sweeps
run; param-based hashing is exactly correct. When Inc-4/5 sweeps params, bump an explicit param (or
add a `formula_version`) so a semantic change is a new trial.

---

## 6. Leak-lint extension — `data/leak_lint.py` (AST, widened scan to `factors/`)

The runtime **prefix-stability-on-`_raw`** is the load-bearing guarantee; leak-lint is the
complementary AST smell-catcher (best-effort, per the Inc-2 backlog WON'T-FIX note). New checks added
to `_Visitor.visit_Call` (all respect the existing `calendar.py` whitelist scoping):

- **SHIFT_NEG** — `func.attr=='shift'`: flag if `arg0` is `ast.UnaryOp(op=ast.USub)` **OR** a
  negative-valued `ast.Constant`, and inspect a `periods=` keyword the same way. **CRITICAL:**
  `.shift(-1)` parses as `UnaryOp(USub, Constant(1))`, **not** a negative `Constant` — a
  Constant-only check misses every negative shift. Positive `.shift(1/21/63/126/147)` stays allowed.
- **CENTERED_ROLLING** — `func.attr=='rolling'`: flag if a `center` keyword's value is
  `ast.Constant(True)` (center is keyword-only in pandas). Trailing `.rolling(n)` stays clean.
- **RESAMPLE** — `func.attr in {'resample','asfreq'}`: flag unconditionally (re-bucketing can pull a
  bar into an interval that closes in the future; breaks the `len(out)==len(df)` contract).
- **SORT** (defense-in-depth) — `func.attr in {'sort_values','sort_index'}`: reordering rows destroys
  time alignment (a later row can land at an earlier position).
- **IMPUTATION** (existing) — add **`interpolate`** to `_IMPUTATION_METHODS`; the rule now applies to
  `factors/` once the scan root includes it.

**Caught at RUNTIME only (NOT AST):** full-series / normalize-by-last reductions (whole-series
`.mean()/.std()/.max()/.sum()/.rank()` broadcast back, `.iloc[-1]`, `.tail(1)` as a normalizer). A
trailing `.rolling().mean()` shares the method name, so a static ban would be leaky (substring) or
block legitimate calls — these are exactly the contextual leaks the prefix-stability property (run
on `_raw`) catches by construction. (Note — `.expanding()` and `.ewm()` are TRAILING and therefore
prefix-stable: they are **permitted**, not leaks, and correctly trip nothing — red-team leaklint-4.)

---

## 7. The `make inc3` gate

```make
inc3:
	$(PY) ruff check src tests
	$(PY) black --check src tests
	$(PY) python -m trading.data.leak_lint src/trading/data src/trading/factors
	$(PY) mypy
	$(PY) pytest --cov=trading --cov-report=term-missing --cov-fail-under=85 -q
	@echo "Increment 3 gate: PASS"
```

`make inc1 && make inc2 && make inc3` must all stay green every commit (`data/` is already
leak-clean, so the widened two-root scan is backward-compatible). The registry-wide prefix-stability
+ frame-adequacy run **inside pytest** via `tests/unit/test_factor_registry.py`: it builds
`default_registry()` against a temp SQLite ledger, calls `validate_all([adequate adversarial
panels])`, and asserts (a) a deliberately-leaky `_raw` inserted into a registry copy makes
`validate_all` **raise** `PrefixStabilityError`, and (b) an inadequate frame raises
`FrameAdequacyError`.

---

## 8. Build clusters (TDD, each: tests → `make inc1 && make inc2 && make inc3` green → commit → push → ff main → STATE+memory)

1. **`factors/errors.py`** — `FactorError(ArcaneError)` + `FactorContractError`,
   `DuplicateFactorError`, `FrameAdequacyError`, `TrialLedgerError` (mirror `data/errors.py`).
2. **`factors/base.py`** — `AlphaFactor` `@final` base: STEP 0–10 + GUARD A–E, read-only DERIVED
   `reliability`, the `_raw` contract. TDD: a leaky/inf/misaligned fake `_raw` is rejected; a clean
   trailing `_raw` passes; `std==0 ⇒ NaN`; `close_loc` same-bar ⇒ `shift(1)` makes it *t-1*; per-bar
   value assertions catch double-shift staleness.
3. **`factors/trial_ledger.py`** — SQLite `TrialLedger` (mirror `executor/idempotency.py`). TDD:
   idempotent re-record no-ops; build-twice-same-path ⇒ `n_trials` stable; new combo increments;
   corrupt/missing DB raises; no `clear/delete/update` attribute exists.
4. **`factors/{momentum,meanrev,volatility,volume,range}.py` + `factors/registry.py`** — the 13
   `_raw`s + `FactorRegistry` + `default_registry()`. TDD: every factor finite-or-NaN on a panel with
   a zero-range / zero-volume / zero-change bar (amihud/rel_volume edge ⇒ NaN, not ±3); a
   deliberately-leaky `_raw` makes `validate_all` raise; an inadequate frame raises
   `FrameAdequacyError`; `10 ≤ count ≤ 15`; ledger seeded with 13.
5. **`data/leak_lint.py` extension + `make inc3`** — SHIFT_NEG / CENTERED_ROLLING / RESAMPLE / SORT +
   `interpolate`, scan widened to `factors/`, Makefile `inc3`. TDD (`test_leak_lint.py` style): each
   new rule has teeth + a clean look-alike; positive `.shift(1)` and trailing `.rolling(21)` not
   flagged; `factors/` scans clean; `inc1`/`inc2` stay green.

Then **Phase C** red-team (wave-based) → **Phase D** remediate + seal.

---

## 9. Non-negotiables carried into Increment 3

- The executor stays NO-OP; nothing trades; `LIVE_MODE=false`; the LLM is never in the submit path.
- Factor output is **DERIVED** — advisory, never gates an order (§4.3).
- Every error path fails **CLOSED**; non-finite (`inf`) `_raw` is rejected; NaN is the honest hole.
- **Do NOT tune toward backtest profit** (ADR §0). Keep the 13 correlated factors; **no
  orthogonalization** — the Inc-5 bias gate prunes (~2 survivors expected). `n_trials` counts all 13.
- Look-ahead is a **test failure** (prefix-stability on `_raw` AND `compute()`), not a review call.
