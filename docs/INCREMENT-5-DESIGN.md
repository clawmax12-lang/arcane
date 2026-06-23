# ARCANE Increment 5 — Bias/Kill Gate + Telegram Notifier (decision-grade)

> **Source:** design panel `wf_inc5` (4 specialist lenses — bias-statistics correctness DSR/PSR/PBO/SPA/WF,
> M18 trial-identity + ledger high-water-mark, executor-safety + Telegram + deferred submit,
> adversarial scope-and-seal skeptic — → skeptic cross-check → this synthesis), 2026-06-23,
> adjudicated against the real sealed Inc-1..4 code (`engine.py`, `statistics.py`, `walk_forward.py`,
> `cost_model.py`, `ledger_integration.py`, `spec.py`, `resolve.py`, `trial_ledger.py`,
> `kill_switch.py`, `settings.py`, `sanitize.py`, `leak_lint.py`, the AST name-ban test, `pyproject.toml`,
> `.gitignore`, `Makefile`) and the live env (`numpy 2.4.6`, `pandas 3.0.3`, **scipy ABSENT** —
> `ModuleNotFoundError` confirmed).
> **THE GATE'S JOB IS TO SAY NO.** ADR-001 §0: ARCANE is an EDGE-FALSIFICATION harness. Accepting ZERO
> survivors out of the 4 toy strategies on a survivorship-biased, survivorship-UNVERIFIED universe is a
> **SUCCESS**, not a failure. Never loosen a threshold to manufacture a survivor. Fail-CLOSED: any
> NaN/missing/degenerate/ruin/under-sample input ⇒ **KILL**, never a pass.

---

## CHECKPOINT — operator decisions (read first)

Three things need an operator signature before the build seals. Everything else is panel-decided and
within ADR §8 (no ADR edit). All choices below are conservative whichever way they go; the only risk is
**silent divergence**, so each is pinned as a `Final` module constant with an ADR-§8 docstring and a test.

### (1) Recommended conservative-standard threshold table

| Test | Threshold (recommended) | Level | Fail-closed ⇒ KILL when |
|---|---|---|---|
| **T1 consistency guard** (look-ahead repro) | per-fold `allclose(atol=1e-9, rtol=0)` AND concat-Sharpe `\|a−b\|≤1e-9` AND `spec_hash`+`cost_model_id` match | per-strategy | any mismatch; either side non-finite |
| **T2 survivorship** | both `survivorship_biased` AND `survivorship_unverified` are `False` | per-strategy | either `True` (ALWAYS this run — Polygon absent) |
| **DSR** (deflated Sharpe) | `DSR > 0.95` | per-strategy | `N`<1; `T`<60; ruin; denom≤0; `SR0` non-finite; `V`≤0 |
| **PSR** (probabilistic Sharpe) | `PSR > 0.95` | per-strategy | `T`<60; `std==0`; ruin; denom≤0 |
| **PBO** (CSCV) | `PBO < 0.5` | **family** | `S`<2; zero valid CSCV splits |
| **SPA** (Hansen) | `p < 0.05` | **family** | `T`<60; `S`<1; any `ω_k==0`/non-finite; ruin |
| **WF-OOS** (12/3/3) | `oos_annualized_sharpe` finite & `>0` AND `fraction_folds_positive >= 0.60` AND `>=2` folds AND geometry `12/3/3` | per-strategy | any NaN; `<2` folds; wrong geometry |
| **enough_samples** | `True` (`oos_bars >= 60`) | veto | `False` |
| **cost-stress** | DSR & PSR & WF still pass at `cost_scale = 2.0` AND `3.0` | per-strategy | any regression |

ALL-of: `allocated = all(component.passed)`. **Any FAMILY failure ⇒ EVERY member KILLED** with
`reason="family_overfit"` (you cannot be individually not-overfit if the family you were selected from
is overfit). **Recommendation: adopt verbatim.**

### (2) DSR reading — OPERATOR SIGN (MR-3)

ADR §8 literally says "Deflated Sharpe > 0 with p < 0.05". The Bailey/López-de-Prado DSR estimator IS a
probability in (0,1) (it is PSR evaluated at the deflated benchmark SR0). "DSR > 0 at the 5% level"
⇔ **`DSR > 0.95`**. **Recommendation: `DSR > 0.95`** (the stricter, single-statistic reading). The
alternative two-statistic form (a separate point-estimate `> 0` AND a separate `p < 0.05`) is looser and
risks a silent accept. Whichever is signed becomes `DSR_THRESHOLD: Final = 0.95` with an ADR-§8 docstring.

### (3) Candidate-set assembly policy — OPERATOR SIGN (MR-4)

PBO/SPA are FAMILY tests; they are undefined for `S=1`. **Recommendation: the gate's unit of evaluation
is a candidate FAMILY (a batch), minimum family size `>= 2`; `S<2` ⇒ family tests KILL (never skip).**
This is the correct edge-falsification posture (ADR §0) but it has teeth: **a lone candidate is
structurally un-allocatable until batched.** The 4 toy strategies are evaluated as ONE family. Operator
must explicitly accept that lone candidates cannot be allocated alone.

### (4) Build-now vs DEFER the paper submit

**Recommendation: BUILD the gate (Part B) + the Telegram notifier (Part C). DEFER the first paper submit
(hard).** One-line reason: the executor is a verified NO-OP (`runner.execute_paper` always returns
`submitted=False`; `broker_paper.submit` raises `NotImplementedError`), Murphy guards G1–G10 are unwired,
§8 abandonment is partial, and the notifier itself is only live-verified by one ping this run — the first
ACT deserves a focused run with guards wired and an explicit operator go.

### (5) ADR risk

**NONE.** Inc-5 is fully WITHIN ADR §8 — no threshold change, no §8 amendment, no Inc-4 reopen. The two
operator checkpoints above are interpretation calls, not ADR edits.

### (6) scipy / dependency decision

**Do NOT add scipy.** All gate math (DSR/PSR/PBO/SPA/WF) needs only a normal CDF/PPF, supplied by a
pure-numpy `erf`-based CDF + Acklam PPF (`<1.15e-9` accuracy). scipy is absent (confirmed), ADR §2 flags
the disk as tight, and there is **no** math in scope that requires scipy. A bare `import scipy` anywhere
in `bias_gate` is forbidden (it would `ImportError` at runtime). The stationary bootstrap uses
`np.random.default_rng(seed=0)` (numpy `np.random` is leak-lint-allowed). pyproject deps are UNCHANGED.

### (7) Evidence-plumbing decision

`BacktestResult` exposes per-fold + concatenated OOS **annualized** Sharpe (`×√252`) and a **FULL-SAMPLE**
index-less `equity_curve` — it does **NOT** expose the OOS net RETURN SERIES, per-obs Sharpe, skew,
kurtosis, or T. DSR/PSR need return moments + T; PBO/SPA need the per-fold return series. **Decision: the
gate RECOMPUTES the OOS net return series by re-running Inc-4's PUBLIC pure primitives**
(`factor_matrix → compose_positions → gross_returns → cost.per_bar_cost`, sliced to `walk_forward_folds`
test windows). **No Inc-4 edit, no `oos_net_returns` accessor.** A two-way CONSISTENCY GUARD (T1) asserts
the recompute matches the sealed result bit-for-bit (per-fold allclose AND concat equality AND hashes),
else KILL. This is strictly safer than reopening a sealed increment.

---

## 0. Mandate & invariant

Increment 5 builds the **ALL-of bias/kill gate** — the FIRST place in ARCANE that emits an
accept/kill VERDICT — on top of the sealed Inc-4 verdict-free `BacktestResult`. Two load-bearing
principles:

1. **The gate exists to KILL** (ADR §0 = facit). It computes the ADR §8 panel and fails CLOSED on every
   degenerate input. ZERO survivors on the toys is the SUCCESS criterion; the survivorship veto (T2) alone
   forces it this run, and the statistics gate is the independent second wall.
2. **Inc-4 stays SEALED.** The Inc-4 backtest package carries an AST name-ban forbidding the bias-gate
   symbols. Those symbols become LEGAL **only** in the new `src/trading/bias_gate/` package. The gate
   consumes ONLY public Inc-4 surfaces (`factor_matrix`, `compose_positions`, `gross_returns`, `_executed`,
   `strategy_warmup`, `walk_forward_folds`, `annualized_sharpe`, `BacktestResult`, `WalkForwardConfig`,
   `CostModel`, `ResolvedStrategy`, `SymbolPanel`, `record_strategy_trial`, `TrialLedger`). It adds NO field
   to `BacktestResult` and touches NO Inc-4 source.

Mirrors the proven idioms: typed fail-closed `ArcaneError` taxonomy; the `kill_switch` atomic
`temp→fsync→os.replace` write idiom; lossless `float.hex()` canonical hashing (the `idempotency` idiom);
`mypy --strict` (`files=["src/trading"]`); ruff/black; `leak_lint` over the new package; `>=85%` coverage.

### 0.1 GROUND-TRUTH CORRECTIONS the implementer MUST honor (from the skeptic cross-check)

- **The AST `_FORBIDDEN_SYMBOLS` set is `{deflated, dsr, reality_check, pbo, psr, allocated, accept,
  approve, kill, verdict, passed}`** — it INCLUDES `passed` and `approve` (the brief omitted them). These
  are banned **only inside `src/trading/backtest/*.py`** (the test scans `pkg.glob("*.py")` over the
  backtest dir). They are **LEGAL in `src/trading/bias_gate/`**. Do NOT add a `passed`/`approve`/`verdict`
  accessor to `backtest`. `make inc5` adds a teeth test that the Inc-4 name-ban still scans ONLY `backtest`
  and still passes unchanged.
- **`spec.canonical_params()` ALREADY folds in `cost_model_id`** (the label) but NOT the cost *numerics*
  and NOT the WF geometry. So the A1 enriched-identity fix is scoped to the cost numbers + WF geometry,
  NOT the label.
- **`combo_hash` keys on `(kind, ref_id, params)`** — an enriched params dict is a DISTINCT combo_hash
  from the engine's spec-only row, so the gate's enriched record coexists (the `+1` over-count is real and
  SAFE: it deflates MORE).
- **`equity_curve` is FULL-SAMPLE** (`np.cumprod(1+net)` over ALL bars; the OOS index is the appended
  union of `fold.test`) — the OOS series is unrecoverable from it. This is the linchpin justifying the
  recompute.
- **`engine.run` reads `ledger.n_trials()` RAW** into `BacktestResult.n_trials_at_eval` (line 225) — it
  is NOT high-water-checked. `result.n_trials_at_eval` is provenance ONLY; the gate's authoritative `N`
  is `hwm.checked_n_trials(ledger.n_trials())`.
- **`SymbolPanel.survivorship_unverified` is a settable field** copied into BOTH result flags. T2 keys off
  the result flags; the Inc-5 driver also asserts `survivorship_unverified is True` this run so a manual
  `False` is caught.

---

## PART A — the 4 tripwires (cleared as the gate's mandatory prerequisite)

PART A is not a sibling of PART B; it is the precondition for PART B's correctness. The four tripwires
live in the new `bias_gate` package (NOT in sealed Inc-4) and each has a RED-first regression test.

### A1 — trial identity (M18): enrich the recorded trial with cost numerics + fold geometry

**Problem (repro-confirmed):** `engine.run` records `record_strategy_trial(ledger, spec)` →
`spec.canonical_params()`, which carries only the `cost_model_id` LABEL and ZERO WF geometry. Two
evaluations with distinct cost numbers (6 bps vs 18 bps under the same `conservative_v1` label) and
distinct geometry (12/3/3 vs 24/6/6) collapse to ONE `combo_hash` → `n_trials` under-counts → DSR
under-deflates.

**File:** `src/trading/bias_gate/trial_identity.py` (pure; no Inc-4 edit).

```python
def cost_canonical(c: CostModel) -> dict[str, str]:
    return {
        "cost_model_id": c.cost_model_id,
        "commission_bps": c.commission_bps.hex(),
        "half_spread_bps": c.half_spread_bps.hex(),
        "slippage_bps": c.slippage_bps.hex(),
        "cost_scale": c.cost_scale.hex(),
    }

def wf_canonical(w: WalkForwardConfig) -> dict[str, int | str]:
    return {
        "train_months": w.train_months, "test_months": w.test_months,
        "step_months": w.step_months, "purge_bars": w.purge_bars,
        "embargo_frac": w.embargo_frac.hex(),
    }

def eval_trial_params(spec: StrategySpec, cost: CostModel, folds: WalkForwardConfig) -> dict[str, Any]:
    return {**spec.canonical_params(), "cost": cost_canonical(cost), "wf": wf_canonical(folds)}
```

**Record (Inc-5 driver, BEFORE any n_trials read):**
`ledger.record(kind="strategy", ref_id=spec.name, params=eval_trial_params(spec, cost, folds))`.
This is a SUPERSET row (distinct nested `cost`/`wf` keys ⇒ distinct `combo_hash`), so it coexists with the
engine's spec-only row. The engine's row means `n_trials` over-counts the baseline by `+1` per spec —
**over-counting is SAFE for M18** (it deflates MORE). Do NOT "fix" the `+1` by reopening Inc-4.

**Fail-closed behavior:** all values are `str`/`int` so canonical `json.dumps(sort_keys, separators)` is
byte-identical (lossless `float.hex()`); an un-encodable param RAISES inside `TrialLedger._canonical`
(no `default=str`). leak_lint-safe: pure dict construction, no banned primitive.

**Test (RED-first):** (a) 3 distinct cost/fold configs ⇒ 3 trials; an identical re-run ⇒ 1 (monotonic,
idempotent). (b) **Reflective completeness:** `eval_trial_params`' nested `cost`/`wf` dicts contain ALL
`model_fields` of `CostModel`/`WalkForwardConfig`, so adding a field to either model FAILS the test until
it is folded into identity (defends the "forgot a swept knob" rebirth of M18).

### A2 — ledger high-water-mark: monotonic floor that DB deletion cannot reset

**Problem:** raw deletion of the ledger `.db` recreates a fresh 0-trial ledger (`TrialLedger` fails closed
only on a CORRUPT db, not a MISSING one) → the DSR deflation input silently resets to 0.

**File:** `src/trading/bias_gate/high_water_mark.py`. New error `HighWaterMarkError(ArcaneError)` in
`src/trading/bias_gate/errors.py` (root `BiasGateError(ArcaneError)`).

```python
DEFAULT_HWM_PATH = Path("state/n_trials_high_water_mark.json")

class NTrialsHighWaterMark:
    def __init__(self, path: Path = DEFAULT_HWM_PATH) -> None: ...
    def verify_writable(self) -> None: ...                      # probe-file write/unlink (kill_switch idiom)
    def checked_n_trials(self, live_count: int) -> int:
        # reject non-int / bool / negative live_count  -> HighWaterMarkError
        # mark = self._read_mark()
        # if live_count < mark:  raise HighWaterMarkError   (a regression — DB deleted/tampered/rolled back)
        # if live_count > mark:  self._write_mark(live_count)  (atomic temp->fsync->os.replace)
        # return live_count
```

`_read_mark` fail-closed: `FileNotFoundError` ⇒ `0` ONLY if `not path.is_symlink()` and `parent.is_dir()`,
else raise; any `OSError`/json/key/type error ⇒ raise; reject `bool` via `isinstance(mark, bool)`; mark
must be a non-negative `int`. `_write_mark` mirrors `kill_switch._write` verbatim
(`parent.mkdir(parents=True, exist_ok=True)`, write to `path.name + ".tmp"`, `flush()` + `os.fsync(fileno())`,
`os.replace(tmp, path)`). Schema: `{"n_trials_high_water_mark": <int>}`. The mark only RISES
(write on `>` only — no fsync churn on a flat/repeated read).

**The gate's SOLE n_trials source** is `n_trials = hwm.checked_n_trials(ledger.n_trials())` — never
`ledger.n_trials()` directly, never `result.n_trials_at_eval`. `ledger.n_trials()` is evaluated first so
its own corrupt-DB RAISE fires before HWM logic. An AST test asserts no bare `.n_trials()` in `bias_gate`
flows into a deflation function without passing through `checked_n_trials`.

**RESIDUAL (carried into the seal, MR-7 — do NOT silently drop):** the HWM lives in the gitignored
`state/` zone. Deleting BOTH the ledger `.db` AND the HWM json resets to a believable 0-trial fresh start;
the HWM cannot defend against simultaneous deletion of its own record. For a paper-only $50 experiment this
is documented as a residual escalated to Murphy-guard/operator territory (see Inc-5 backlog), NOT
over-engineered with a committed floor.

### A3 — re-derived purge `>= max_total_window + label_horizon`

**Problem:** `WalkForwardConfig.purge_bars` defaults to `1` (correct for Inc-4 non-fitted close-to-close),
but an author-declared purge is trusted; a future fitted consumer that under-purges leaks.

**File:** `src/trading/bias_gate/evidence.py` (a non-verdict evidence helper). New error
`PurgeUnderspecifiedError(BiasGateError)`.

```python
def required_purge_bars(strategy: ResolvedStrategy, *, label_horizon: int = 1) -> int:
    return strategy_warmup(strategy) + label_horizon   # strategy_warmup is a public Inc-4 helper
```

`strategy_warmup` (Inc-4 `engine.py:134`) = `max(rl.factor.raw_lookback + rl.factor.z_window + 1)` over
the strategy's OWN bound legs — re-derived from facts, never author-declared (the registry-2 lesson).
`label_horizon` is an EXPLICIT gate parameter (`H=1` this run, close-to-close), never read from the spec.

**Assertion, run in the Inc-5 driver BEFORE `BacktestEngine.run`:**
```python
need = required_purge_bars(resolved, label_horizon=H)
if wf.purge_bars < need:
    raise PurgeUnderspecifiedError(
        f"WalkForwardConfig.purge_bars={wf.purge_bars} < required {need} = "
        f"warmup({strategy_warmup(resolved)}) + label_horizon({H}); a fitted/Inc-5 consumer must "
        f"purge >= the deepest factor pipeline + holding horizon")
# defensive ceiling: a per-strategy warmup can never exceed the registry-wide max
assert strategy_warmup(resolved) + H <= registry.max_total_window() + H
assert need >= 1   # fail closed if the horizon term degenerates to 0
```

`<` (not `!=`) so a deliberately-LARGER purge (more conservative) is allowed; under-purge fails closed.

**Test (RED-first):** an under-purged config raises `PurgeUnderspecifiedError`; a sufficient/over-purged
config passes; the `need >= 1` floor fires on a degenerate horizon.

### A4 — T2 survivorship fail-closed (degraded is the only reachable state this run)

**Problem/posture:** ADR §8 — "T2 returns `passed=False` with a reason rather than a false pass."
`SymbolPanel.survivorship_unverified` defaults `True` and the engine copies it into BOTH result flags.
Polygon (the PIT-universe verifier) is deferred, so this run is ALWAYS degraded ⇒ T2 always fails ⇒ KILL.

**File:** `src/trading/bias_gate/tests_t2.py`.

```python
def t2_survivorship(result: BacktestResult) -> GateComponent:
    if result.survivorship_biased or result.survivorship_unverified:
        return GateComponent(
            name="T2_survivorship", passed=False,
            reason=(f"survivorship unverified (biased={result.survivorship_biased}, "
                    f"unverified={result.survivorship_unverified}); PIT universe deferred — "
                    f"fail closed (ADR §8)"))
    return GateComponent(name="T2_survivorship", passed=True, reason="PIT-verified")
```

T2 passes ONLY when BOTH flags are `False` (the dual-False check; no default-True else-branch). The Inc-5
driver also asserts `result.survivorship_unverified is True` this run (Polygon absent) so a manually-set
`False` is caught. `passed` is a legal symbol in `bias_gate` (it is banned only in `backtest`).

---

## PART B — the bias_gate package (the ALL-of verdict)

### B.0 Package layout (`src/trading/bias_gate/`)

| file | contents |
|---|---|
| `__init__.py` | package marker; re-exports the public `evaluate_family`, `GateDecision`, `GateComponent` |
| `errors.py` | `BiasGateError(ArcaneError)`, `HighWaterMarkError`, `PurgeUnderspecifiedError`, `EvidenceConsistencyError` |
| `_normal.py` | pure-numpy `norm_cdf` (erf) + `norm_ppf` (Acklam) — NO scipy |
| `thresholds.py` | all `Final` constants (`DSR_THRESHOLD=0.95`, `PSR_THRESHOLD=0.95`, `PBO_THRESHOLD=0.5`, `SPA_ALPHA=0.05`, `WF_MIN_FRACTION_FOLDS=0.60`, `MIN_OOS_BARS=60`, `COST_STRESS_SCALES=(2.0,3.0)`, `MIN_FAMILY_SIZE=2`, `BOOTSTRAP_B=2000`, `CSCV_BLOCKS=16`) each docstring-cited to ADR §8 |
| `trial_identity.py` | A1 — `cost_canonical`/`wf_canonical`/`eval_trial_params` |
| `high_water_mark.py` | A2 — `NTrialsHighWaterMark` |
| `evidence.py` | A3 `required_purge_bars`; the impure evidence ASSEMBLER (recompute OOS series + consistency guard) |
| `tests_t2.py` | A4 — `t2_survivorship` |
| `stats.py` | pure judges: `dsr_probability`, `psr_probability`, `cross_trial_variance`, `pbo_fraction`, `spa_pvalue`, `wf_oos_ok` |
| `gate.py` | the pure `combine_verdict` / `evaluate_family` ALL-of composer → `GateDecision` |

### B.1 The pure `GateEvidence` + the evidence ASSEMBLER

The impure assembler is isolated; the judge is a pure deterministic function over plain floats/arrays so
it is trivially testable on adversarial tails and cannot fail-open via hidden IO (R1 + immutability).

```python
@dataclass(frozen=True, slots=True)
class GateEvidence:                       # ONE candidate's recomputed evidence
    spec_hash: str
    cost_model_id: str
    n_trials: int                         # authoritative HWM-checked count
    oos_returns: tuple[float, ...]        # per-obs OOS net, fold-ordered
    per_fold_oos_returns: tuple[tuple[float, ...], ...]
    per_fold_oos_sharpe: tuple[float, ...]   # copied from BacktestResult for WF + the consistency guard
    enough_samples: bool
    survivorship_biased: bool
    survivorship_unverified: bool
    train_months: int; test_months: int; step_months: int

@dataclass(frozen=True, slots=True)
class GateFamilyEvidence:                  # the family bundle for PBO/SPA
    members: tuple[GateEvidence, ...]
    perf_matrix: tuple[tuple[float, ...], ...]   # S x T_obs aligned per-obs OOS returns
```

**Assembler — recompute the OOS net series via Inc-4 PUBLIC primitives, no Inc-4 edit:**

```python
def build_evidence(strategy: ResolvedStrategy, panel: SymbolPanel, *, cost: CostModel,
                   folds: WalkForwardConfig, result: BacktestResult,
                   n_trials: int) -> GateEvidence:
    sessions = panel.bars[next(iter(panel.bars))].index   # re-assert monotonic+unique+tz-aware else KILL
    fold_list = walk_forward_folds(sessions, folds)
    net_by_symbol = {}
    for sym, bars in panel.bars.items():
        tw = compose_positions(strategy, factor_matrix(strategy, bars))
        net_by_symbol[sym] = gross_returns(tw, bars["close"]) - cost.per_bar_cost(_executed(tw))
    net = pd.DataFrame(net_by_symbol).mean(axis=1)        # exactly the engine's mean(axis=1)
    per_fold = tuple(net.loc[f.test].to_numpy("float64", na_value=np.nan) for f in fold_list)
    oos = np.concatenate(per_fold) if per_fold else np.array([], dtype="float64")
    # --- CONSISTENCY GUARD (T1) — the single most important fail-open defense ---
    gate_per_fold = tuple(annualized_sharpe(pd.Series(a)) for a in per_fold)   # gate's annualized recompute
    _assert_consistent(gate_per_fold, result.per_fold_oos_sharpe,
                       annualized_sharpe(pd.Series(oos)), result.oos_annualized_sharpe,
                       strategy.spec_hash, result.spec_hash, cost.cost_model_id, result.cost_model_id)
    return GateEvidence(..., oos_returns=tuple(map(float, oos)),
                        per_fold_oos_returns=tuple(tuple(map(float, a)) for a in per_fold),
                        per_fold_oos_sharpe=result.per_fold_oos_sharpe, n_trials=n_trials, ...)
```

**Consistency guard (MR-1 — pin the STRICT per-fold form, NOT the weaker concat-only form):** require
ALL of — per-fold `np.allclose(gate_per_fold, result.per_fold_oos_sharpe, atol=1e-9, rtol=0)` AND
concat-Sharpe `|a−b|≤1e-9` AND `spec_hash` match AND `cost_model_id` match. The per-fold check is the
binding one (PBO/SPA consume per-fold series; a concat-only check can pass while an individual fold
diverged in a sign-canceling way). **Explicit NaN handling (H-1):** treat "either side non-finite" as a
KILL — do NOT rely on `NaN==NaN`/`allclose` semantics being safe by accident:
```python
def _eq(a: float, b: float) -> bool:
    return bool(np.isfinite(a) and np.isfinite(b) and abs(a - b) <= 1e-9)
```
Any mismatch ⇒ raise `EvidenceConsistencyError` (the recompute diverged from the sealed engine; fail
closed, never gate on a stale/wrong series — defends against a future pandas/numpy `pct_change`/`cumprod`
NaN-semantics drift).

**No imputation/sort/resample/centered-rolling/negative-shift** — `fold.test` is already an ordered
`DatetimeIndex` from the splitter; NaN price-hole bars are kept NaN and masked ONLY inside each statistic's
`_finite()` mask (mirrors `statistics._finite`). Candidate ranking uses `np.argsort` (numpy), never pandas
`.sort_*`. leak_lint-clean.

**RUIN precondition (H-3 — first-class, before any moment):** the gate re-implements the Inc-4
`statistics._has_ruin` check (`any r <= -1.0`) on `oos_returns` and KILLs before computing any
`SR_hat`/skew/kurt — a wiped series must never feed finite-looking moments into PSR/DSR (the exact Inc-4
red-team lesson: ruin panels caught a wiped fold scoring positive).

### B.2 Pure normal CDF/PPF — `_normal.py` (NO scipy)

```python
def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def norm_ppf(p: float) -> float:            # Acklam rational approx, |err| < 1.15e-9 over (0,1)
    if not (0.0 < p < 1.0):
        raise BiasGateError(f"norm_ppf domain (0,1), got {p}")   # never return +-inf silently
    ...  # a[6],b[5],c[6],d[4], break pl=0.02425
```

Pinned reference unit tests (1e-9): `norm_cdf(1.96)=0.9750021049`, `norm_ppf(0.975)=1.9599639845`,
`norm_ppf(0.95)=1.6448536270`. Forbid any `import scipy` anywhere in the package (a grep test).

### B.3 PSR — `psr_probability` (Bailey & López de Prado 2014)

`r` = finite OOS **per-obs** net returns, `T=len(r)`. **Use the per-obs Sharpe computed FRESH from the
recomputed array — NEVER `result.oos_annualized_sharpe` (×√252) (MR-2: feeding the annualized value
inflates `SR_hat` ~16× and passes everything — the single most likely catastrophic fail-open).**

```
SR_hat = mean(r) / std(r, ddof=1)                          # PER-OBSERVATION
denom  = 1 - γ3*SR_hat + ((γ4 - 1)/4) * SR_hat**2          # γ3 sample skew, γ4 full (non-excess) kurtosis
PSR(SR*) = Φ( (SR_hat - SR*) * sqrt(T - 1) / sqrt(denom) ),  SR* = 0
ACCEPT iff PSR > 0.95
```

**Fail-closed (positive-form, explicit KILL — H-2):** `T<60` ⇒ KILL; `std==0` or non-finite ⇒ KILL;
ruin (already pre-checked) ⇒ KILL; `denom <= 0` or non-finite ⇒ **explicit KILL** (heavy tails can drive
denom ≤ 0; do NOT lean on `sqrt(neg)=NaN` comparison luck). Threshold is `metric > THRESHOLD` returning a
bool that DEFAULTS to KILL (never a De-Morgan `not (PSR <= 0.95)`, which fails OPEN on NaN).

### B.4 DSR — `dsr_probability` (Bailey & López de Prado 2014)

DSR = PSR evaluated against a DEFLATED benchmark `SR0` that accounts for `N` trials (multiple testing).

```
N  = hwm.checked_n_trials(ledger.n_trials())              # MR-5: HWM, NOT result.n_trials_at_eval
γ  = 0.5772156649  (Euler-Mascheroni)
SR0 = sqrt(V) * [ (1-γ)*Φ⁻¹(1 - 1/N) + γ*Φ⁻¹(1 - 1/(N*e)) ]      # N>=2
SR0 = 0.0  when N == 1   (no deflation; do NOT call Φ⁻¹(0))
DSR = Φ( (SR_hat - SR0) * sqrt(T - 1) / sqrt(denom) )     # same denom as PSR; SR_hat per-obs
ACCEPT iff DSR > 0.95
```

**Cross-trial variance `V` (MR-5 — adopt Lens-1's definition verbatim):**
```
if family has S>=2 finite per-obs Sharpes {SR_i}:  V_obs = np.var(SR_array, ddof=1)
V_null = denom / (T - 1)                            # asymptotic variance of the Sharpe estimator
V = max(V_obs_or_null, V_null)                       # floor: a degenerate near-zero dispersion can never
                                                     # deflate the hurdle below the analytic floor
```
A LARGER `V` ⇒ larger `SR0` ⇒ harder (conservative). With `S` small the deflation leans on `V_null`
(documented). **Fail-closed:** every PSR rule applies; `N<1` ⇒ KILL; `SR0` non-finite ⇒ KILL; `V<=0` or
non-finite ⇒ KILL. If `SR_hat <= SR0` the numerator is ≤0 ⇒ `DSR <= 0.5 < 0.95` ⇒ correctly KILL (the
deflation biting — the desired NO).

### B.5 PBO via CSCV — `pbo_fraction` (Bailey-Borwein-LdP-Zhu 2015) — FAMILY

PBO = fraction of CSCV splits where the IS-best strategy ranks below the OOS median. Inputs: `perf_matrix`
shape `(T_obs, S)` of per-obs OOS net returns, aligned to a common length (truncate to the min common
finite length; if alignment loses `>50%` of any column ⇒ KILL).

- **`S < 2` OR `<2` disjoint blocks ⇒ KILL** (cannot assess selection overfit on a single candidate;
  fail closed, NOT a free pass — MR-4).
- Partition `T_obs` rows into `S_blk` EVEN blocks (`S_blk = 16` if `T_obs >= 16*S`, else the largest even
  `S_blk >= 2` with each block `>= max(60//S_blk, 2)`; if none fits ⇒ KILL). Enumerate all
  `C(S_blk, S_blk/2)` IS-halves (`itertools.combinations`; `S_blk=16` ⇒ 12870 combos — bounded).
- Per split: IS = chosen blocks concatenated, OOS = complement; per strategy compute IS per-obs Sharpe +
  OOS per-obs Sharpe (NaN/ruin ⇒ exclude that strategy from THIS split; `<2` remaining ⇒ skip the split);
  `n* = argmax(IS Sharpe)`; its OOS rank `r ∈ (0,1]`; logit `ω = ln(r/(1-r))` (clip `r` to
  `[1/(S+1), S/(S+1)]` to avoid ±inf). `PBO = fraction of splits with ω <= 0`.
- ACCEPT (family) iff `PBO < 0.5`. **Fail-closed:** zero valid splits ⇒ KILL; non-finite `ω` after
  clipping ⇒ that split counts as overfit (`ω<=0`). Ranking via `np.argsort` (never pandas `.sort_*`).

### B.6 SPA — `spa_pvalue` (Hansen 2005, stationary bootstrap) — FAMILY

SPA tests whether the BEST candidate's OOS performance exceeds a zero benchmark after the full search
(data-snooping). SPA strictly dominates White's RC, so **build SPA; expose White RC only if free**
(D — do not double the bootstrap surface). `d_{k,t}` = per-obs OOS net returns (benchmark 0).

```
ω_k = stationary-bootstrap std of sqrt(T_obs)*mean(d_k)
V_SPA = max_k sqrt(T_obs)*mean(d_k) / ω_k
# Politis-Romano stationary bootstrap: geometric block, mean length L = ceil(sqrt(T_obs)),
# B = 2000 resamples, rng = np.random.default_rng(seed=0)  (deterministic, leak-lint-allowed)
# center each replicate (null of no outperformance); Hansen recentering:
#   g_k = mean(d_k) * 1{ mean(d_k) >= -sqrt((ω_k^2 / T_obs) * 2*ln(ln(T_obs))) }
p = fraction of bootstrap V* >= observed V_SPA
ACCEPT (family) iff p < 0.05
```

**Fail-closed:** `T_obs<60` ⇒ KILL; `S<1` ⇒ KILL; any `ω_k==0` or non-finite ⇒ KILL; any ruin bar ⇒ KILL.

### B.7 WF-OOS criterion — `wf_oos_ok` (reuse Inc-4 outputs)

This per-strategy criterion is fully computed by the sealed `BacktestResult`; only threshold it:
```
ACCEPT iff (result.oos_annualized_sharpe is finite AND > 0)
       AND (result.fraction_folds_positive is finite AND >= 0.60)
       AND len(result.per_fold_oos_sharpe) >= 2
       AND result.train_months==12 AND result.test_months==3 AND result.step_months==3
```
This is the ONLY path that uses the ANNUALIZED field (sign-preserving, harmless — MR-2). Fail-closed:
NaN OOS Sharpe (Inc-4 already returns NaN on a ruin/degenerate concat) ⇒ KILL; NaN
`fraction_folds_positive` ⇒ KILL; `<2` folds ⇒ KILL; non-12/3/3 geometry ⇒ KILL.

### B.8 The ALL-of composer + the frozen verdict — `gate.py`

```python
@dataclass(frozen=True, slots=True)
class GateComponent:
    name: str
    passed: bool
    reason: str

@dataclass(frozen=True, slots=True)
class GateDecision:                     # the NEW verdict-bearing type — legal ONLY in bias_gate
    spec_hash: str
    allocated: bool                     # the verdict (ALLOCATED if True, else KILLED)
    components: tuple[GateComponent, ...]
    n_trials: int
    reasons: tuple[str, ...]            # the failing component reasons (empty iff allocated)

def evaluate_family(members: Sequence[FamilyMember], *, ledger, hwm, label_horizon=1) -> tuple[GateDecision, ...]:
    # 1. require len(members) >= MIN_FAMILY_SIZE else every member KILLED reason='family_too_small'
    # 2. per member: A3 purge assert; build_evidence (recompute + T1 consistency guard); A4 T2;
    #    DSR (N via hwm), PSR, WF, enough_samples veto, cost-stress (re-run engine at cost_scale 2.0 & 3.0)
    # 3. family: PBO < 0.5 ; SPA p < 0.05  (over perf_matrix)
    # 4. allocated_member = (family ok) AND all(per-strategy components passed)
    # 5. if any family test fails -> EVERY member KILLED with reason='family_overfit'
```

**Frozen §8 component tuple for THIS slice (D — bound the verdict surface):**
`{T1 consistency, T2 survivorship, DSR, PSR, PBO, SPA, WF, enough_samples, cost-stress}`. The remaining
ADR §8 tests (regime/time/calendar splits, adversarial windows 2018/2020/2022, block-bootstrap CI,
Bonferroni+BH-FDR, holdout veto, curve-fit perturbation) are **DEFERRED** with a backlog entry — this
bounds the increment. The slice is a frozen module constant; a test asserts `evaluate_family`'s component
set equals it.

**Cost-stress:** re-run `BacktestEngine.run` (public) at `CostModel(cost_scale=2.0)` and `3.0` (same
`cost_model_id` label, distinct numerics — each a counted trial via A1) and require DSR/PSR/WF still pass.

**n_trials deflation wiring:** `N` is read EXACTLY ONCE per family via `hwm.checked_n_trials(ledger.n_trials())`
AFTER all A1 records are written, and threaded into every member's DSR. Never from `result.n_trials_at_eval`.

**EXPECTED RESULT on the 4 toys this run:** KILL — the T2 survivorship veto alone forces it; the
statistics gate is the independent second wall. Two committed canaries (the teeth, never loosen a
threshold): a must-FAIL test asserting the toy family KILLs, and a must-PASS test on a SYNTHETIC
strong-edge series (high SR, low N, both survivorship flags `False`) proving the gate CAN ALLOCATE without
lowering any real-data threshold.

---

## PART C — Telegram notifier + DEFERRED paper submit

### C.1 Telegram notifier — `src/trading/notify/telegram.py`

New package `src/trading/notify/__init__.py`. Uses `httpx` (already a dep — no new dep). Bot
`@Traderexperimentbot`; `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`.

**Settings:** extend `settings.OPTIONAL_KEYS` with `("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")`; add
`load_notify_settings()` returning `(token, chat_id)` from `load_settings().get(...)`. (`.env` already in
`.gitignore`; add empty `TELEGRAM_BOT_TOKEN=` / `TELEGRAM_CHAT_ID=` placeholders to `.env.example`.)

**API (testable without network — inject a `Sender`):**
```python
class Severity(StrEnum): YELLOW="yellow"; ORANGE="orange"; RED="red"   # mirrors §5.1 graduated response

Sender = Callable[[str, dict[str, str]], None]    # (url, body) -> None ; default posts via httpx.Client

class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, *, sender: Sender = _httpx_sender) -> None: ...
    def send_message(self, text: str) -> None: ...                 # sanitize -> send
    def page_operator(self, severity: Severity, text: str) -> None: ...  # '[RED] ' tag; RED failure RE-RAISES
    def send_daily_report(self, report: str) -> None: ...          # sanitize, chunk <=4096, send sequentially

def from_settings(s, *, sender=_httpx_sender) -> TelegramNotifier:
    # raise NotifierMisconfiguredError if token None/empty;
    # if chat_id None -> resolve_chat_id(token, sender) (one getUpdates round-trip); raise if unresolvable
```

**Fail-closed / secrets discipline (the worst fail-open is a dropped RED page):**
- `page_operator(RED)` on sender failure **RE-RAISES** `NotifierError` — never swallowed; the spec forbids
  a bare `except` around it. A test asserts RED re-raises when the sender fails.
- **Token never logged.** Build the URL (`https://api.telegram.org/bot{token}/sendMessage`) as a
  non-logged local var. httpx exceptions embed `exc.request.url` (which contains `/bot{token}/`), so catch
  ALL httpx exceptions and re-wrap as `NotifierError(type(exc).__name__ + status)` — never stringify the
  original `exc` or the URL. `structlog` logs only `{severity, status, ok}` (and on error the exception
  TYPE + status); never the URL/token. A grep/AST test forbids a literal bot-token pattern
  (`\d{8,}:[A-Za-z0-9_-]{30,}`) anywhere under `src/` and asserts the token never reaches a structlog arg.
- **Every body passes through `trading.data.sanitize.sanitize()` BEFORE the body dict is built** (§4.2,
  the M13 defense). `sanitize` is fail-closed (returns `""` on any exception); if it returns `""` send a
  fixed placeholder `"[message redacted by sanitizer]"` (Telegram rejects an empty body). The notifier is
  NOT presented as a sanitization guarantee (sanitize is best-effort; the operator is a human reading
  evidence, not an LLM acting on it).
- `chat_id` auto-resolve: `getUpdates` returns empty if the bot has no recent messages, so resolve
  correctly RAISES `NotifierMisconfiguredError` with a message instructing the operator to send any message
  to `@Traderexperimentbot` first. Whether the resolved `chat_id` is written back to `.env` automatically
  is an operator preference (default: print for the operator to paste — do NOT auto-mutate a secret file).

**The one live verified ping (memory insight "fakes must mirror reality"):** unit tests inject
`sender=fake` (a list-appending callable) — zero network. One test marked `@pytest.mark.live`
(`pyproject` already has `addopts = "-q -m 'not live'"`, so it is EXCLUDED from `make inc5`) sends a single
real message — `from_settings(load_notify_settings()).page_operator(Severity.YELLOW, "ARCANE Inc-5
notifier wire-up ping — paper only, no trades")` — and asserts a 2xx. The operator runs it once manually
at wire-up, confirms receipt on `@Traderexperimentbot`, and records the verification (NOT the body/token)
in STATE.md.

### C.2 EXPLICIT DEFER of the paper submit

**DEFER (hard). Build the gate + notifier now.** The executor is a verified NO-OP
(`runner.execute_paper` always returns `submitted=False`; `broker_paper.submit` raises
`NotImplementedError`). The first ACT deserves a focused run with guards wired + tested behind an explicit
operator go.

**KEY SAFETY INVARIANT wired NOW so the deferred work inherits it:** the gate's ALLOCATED set is the SOLE
input to any future submit path; `assert gate_status == ALLOCATED` is a precondition (ADR §8); broker stays
`paper=True` hardcoded; `evaluate_pre_submit` is a SECOND independent fail-closed gate. A **handoff test
asserts NO order-submit call site exists anywhere in `bias_gate`** (the package never imports
`broker_paper`/`runner` submit symbols).

**HARD prerequisites for the deferred submit (Inc-5 backlog — next run's task #1):**
1. notifier live-verified (this run's ping);
2. Murphy guards G1–G10 wired AND each unit-tested with a yellow/orange/red graduated-response assertion;
3. §8 abandonment triggers §8.1–§8.8 wired into the runner loop AND tested (total-loss>$30, equity<$20,
   5 consec errors, recon-drift>2 for >10min, LLM-fail>30%/24h, mistake-cat ×3/7d, calib>30% ×2wk,
   `make abandon`);
4. executor transitions NO-OP → gate-gated submit, structurally UNREACHABLE unless `gate_status==ALLOCATED`
   AND `evaluate_pre_submit` accepted AND `is_live() is False`;
5. size strictly within `config/risk.yaml` caps (`per_trade_risk_usd=1.0`, `max_position_concentration_pct=30`,
   equity floor 20, total loss 30);
6. idempotent `client_order_id` (already deterministic).

---

## make inc5 gate (mirror inc4 + leak_lint over the new package)

```make
inc5:
	$(PY) ruff check src tests
	$(PY) black --check src tests
	$(PY) python -m trading.data.leak_lint src/trading/data src/trading/factors src/trading/backtest src/trading/bias_gate src/trading/notify
	$(PY) mypy
	$(PY) pytest --cov=trading --cov-report=term-missing --cov-fail-under=85 -q
	@echo "Increment 5 gate: PASS"
```

`make inc1 && inc2 && inc3 && inc4 && inc5` must all stay green every commit. `mypy` already covers
`src/trading` (`files=["src/trading"]`), so the new packages are type-checked automatically.
`bias_gate` + `notify` must avoid every leak_lint-banned primitive: `.fillna/.ffill/.bfill/.interpolate`
(IMPUTATION), `.sort_values/.sort_index` (SORT), `.resample/.asfreq` (RESAMPLE),
`.shift(neg)/.diff(neg)/.pct_change(neg)` (SHIFT_NEG), `.rolling(center!=False)` (CENTERED_ROLLING),
bare `get_calendar`, module-scope `>=3` ticker literals. `np.sort/argsort/np.random` are fine. `make inc5`
also runs a TEETH test asserting the Inc-4 backtest name-ban still scans ONLY `backtest` and still passes
unchanged (the seal is not weakened by the new legal symbols).

---

## TDD build clusters (each: tests RED-first → `inc1..inc5` green → commit → push → ff main → STATE+memory)

| C | name | files | key tests (RED-first) |
|---|---|---|---|
| **C1** | errors + pure normals | `bias_gate/errors.py`, `bias_gate/_normal.py`, `bias_gate/thresholds.py` | every error is an `ArcaneError`; `norm_cdf(1.96)=0.9750021049`, `norm_ppf(0.975)=1.9599639845` to 1e-9; `norm_ppf` raises on `p<=0`/`p>=1`; no `import scipy` anywhere in the package; thresholds equal the §8 values verbatim |
| **C2** | A1 trial identity | `bias_gate/trial_identity.py` | 3 distinct cost/fold configs → 3 trials; identical re-run → 1; `eval_trial_params` covers ALL `model_fields` of `CostModel`/`WalkForwardConfig` (reflective completeness); `+1` engine-row over-count is present and SAFE; un-encodable param raises |
| **C3** | A2 high-water-mark | `bias_gate/high_water_mark.py` | drop-to-0 raises; drop-to-partial raises; corrupt/symlink/non-int/bool mark raises; monotonic rise persists atomically; `verify_writable` probe; `checked_n_trials` is the SOLE n_trials path (AST test) |
| **C4** | A3 purge + A4 T2 | `bias_gate/evidence.py` (`required_purge_bars`), `bias_gate/tests_t2.py` | under-purge raises `PurgeUnderspecifiedError`; over-purge passes; `need>=1` floor; T2 KILLs when either flag True; T2 passes only on dual-False; driver asserts `survivorship_unverified is True` this run |
| **C5** | evidence assembler + T1 guard | `bias_gate/evidence.py` (`build_evidence`) | recompute equals sealed result per-fold (allclose 1e-9) AND concat AND hashes; a mutated/divergent series raises `EvidenceConsistencyError`; either-side-NaN ⇒ KILL; ruin pre-check KILLs before any moment; no banned primitive |
| **C6** | PSR + DSR + V | `bias_gate/stats.py` | per-obs (NOT annualized) `SR_hat`; `denom<=0` ⇒ explicit KILL; ruin/`T<60`/`std==0` ⇒ KILL; `SR0` grows with N (0→~1.83→~2.53 for N=1,17,100); `V=max(obs,V_null)` floor; `SR_hat<=SR0` ⇒ DSR<0.95 KILL; positive-form thresholds default to KILL on NaN |
| **C7** | PBO + SPA (family) | `bias_gate/stats.py` | `S<2`/zero-valid-splits ⇒ KILL; CSCV `ω<=0` overfit fraction; `np.argsort` ranking; SPA stationary bootstrap deterministic (seed=0), `ω_k==0` ⇒ KILL; ruin ⇒ KILL |
| **C8** | WF + ALL-of composer | `bias_gate/gate.py`, `bias_gate/tests_t2.py` wiring | WF NaN/`<2`-fold/wrong-geometry ⇒ KILL; family overfit KILLs EVERY member; cost-stress 2×/3× re-run; N via HWM only; the 4 toys KILL (must-FAIL canary); synthetic strong-edge ALLOCATES (must-PASS canary); frozen §8 component tuple test |
| **C9** | Telegram notifier | `notify/__init__.py`, `notify/telegram.py`, `settings.py` (OPTIONAL_KEYS + `load_notify_settings`), `.env.example` | sanitize-before-send; RED failure re-raises; missing-token raises; chat_id auto-resolve with fake Sender; token never in logs (grep test); one `@pytest.mark.live` ping excluded from `make inc5` |
| **C10** | make inc5 + handoff invariant + leak_lint | `Makefile` (`inc5` + widen leak-lint roots), Inc-5 driver | the 4 toys run end-to-end → all KILLED; planted `shift(-1)`/`resample`/`sort_values` in a `bias_gate` file is leak-lint-flagged; Inc-4 name-ban still scans ONLY `backtest` and passes; NO submit call site in `bias_gate` (handoff test); `inc1..inc5` all green |

---

## Red-team plan (wave-based; attack the teeth; probe the tails; finish single-threaded if throttled)

**Wave 1 — attack the consistency guard (T1, the linchpin fail-open).** Feed a recompute that diverges
from the sealed result by exactly 1 bar / a different cost rounding / a reversed fold concat order — the
per-fold allclose MUST KILL. Feed a NaN-vs-NaN pair both sides — MUST KILL (H-1, not pass by float luck).
Feed a hash-mismatched `cost_model_id` — MUST KILL.

**Wave 2 — attack the unit confusion (MR-2).** Plant `oos_annualized_sharpe` into the PSR/DSR `SR_hat`
slot — assert the gate uses the per-obs recompute (the planted ~16× value would pass everything; the test
must show it does NOT reach the formula).

**Wave 3 — probe the tails (the ruin/denominator/ruin-before-moment insight).** Ruin fold (`r<=-1`),
heavy-tail fold driving `denom<=0`, `T=59` (just under floor), `std==0`, all-NaN fold, `N=0`/`N=1`,
`V=0`, a single-symbol degenerate panel — every one MUST KILL via an EXPLICIT KILL branch, never a
NaN-comparison accident.

**Wave 4 — attack the deflation count (M18/A1/A2).** Sweep cost numerics + fold geometry under the SAME
label and assert `n_trials` rises (A1 reflective-completeness). Delete the ledger `.db` and assert the HWM
RAISES; delete BOTH `.db` + HWM and confirm the documented RESIDUAL (MR-7) is reproducible and NAMED in
the seal (not silently passing).

**Wave 5 — attack the family logic (MR-4).** `S=1` ⇒ PBO/SPA KILL (not skip); a one-overfit-member family
⇒ EVERY member KILLED `family_overfit`; the must-PASS synthetic strong-edge family ALLOCATES without any
threshold loosened.

**Wave 6 — attack the notifier (token leak / dropped RED page).** Force an httpx error and assert the
token never reaches logs (grep the captured log); assert `page_operator(RED)` re-raises; assert
`sanitize()` runs before every body; assert the live ping is excluded from `make inc5`.

**Wave 7 — attack the seal boundary.** Assert the Inc-4 backtest name-ban still scans ONLY `backtest`,
still passes, and the new legal symbols (`dsr`/`pbo`/`accept`/`verdict`/`allocated`/`passed`) never appear
in any `backtest/*.py`. Assert `bias_gate` imports only public Inc-4 symbols and no submit call site.

**Throttling discipline (the wf_618edde8-565 lesson):** if any wave is rate-limited or the suite throttles,
finish the remaining must-fail/must-pass canaries SINGLE-THREADED and re-prove each gate still CATCHES with
an adversarial must-fail case before sealing. Never seal on a throttled-skipped teeth test.

---

## Non-negotiables + deferred items

**Non-negotiables:** the gate's job is to KILL; ZERO survivors = SUCCESS; NEVER loosen a threshold to
manufacture a survivor; fail-CLOSED on any NaN/missing/degenerate/ruin/under-sample input; Inc-4 stays
SEALED (recompute, no accessor, no field, no name-ban edit); the executor stays NO-OP and `paper=True`
hardcoded; the LLM is never in the submit path; N flows through the HWM, never `result.n_trials_at_eval`;
the RED page never swallows; the token is never logged.

**Deferred items (Inc-5 backlog):**
- The 9/12 remaining ADR §8 tests (regime/time/calendar splits, adversarial windows, block-bootstrap CI,
  Bonferroni+BH-FDR, holdout veto, curve-fit perturbation) → a later increment.
- The simultaneous ledger+HWM deletion residual (MR-7) → Murphy-guard/operator attestation, documented.
- The first paper submit + Murphy guards G1–G10 + §8 abandonment loop → next run (prereqs in §C.2).
- White RC (SPA dominates) → expose only if free.
- Polygon PIT-universe verification (the only legitimate way to set `survivorship_unverified=False`) →
  unblocks an ALLOCATE path on real data.
