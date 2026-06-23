# ARCANE Increment 4 — Strategies + Walk-Forward Backtest Design (decision-grade)

> **Source:** design panel `wf_6158e014-a7e` (4 specialist lenses — backtest look-ahead/purge-embargo,
> quant strategy/cost, architecture/registry/ledger reuse, adversarial skeptic — → synthesis),
> 2026-06-23, adjudicated by the lead this session and re-checked against the real Inc-1/2/3 code.
> **Checkpoint verdict: all FOUR operator-decision criteria are FALSE → the lead proceeds autonomously.**
> A backtest exists to **TRY TO KILL** a strategy (ADR-001 §0 = facit), never to manufacture a
> profitable curve. The executor stays NO-OP. Inc-4 is **COMPUTE-AND-REPORT ONLY** — it computes
> statistics; it NEVER gates, approves, or kills (that ALL-of bias/kill gate is Increment 5).

---

## 0. Mandate & invariant

Increment 4 builds the **leak-proof-by-construction walk-forward backtest** on top of the sealed Inc-2
PIT data spine and the Inc-3 alpha-factor layer. The single load-bearing principle (ADR-001 §7):
**look-ahead correctness is STRUCTURAL, not disciplinary.** The backtest is the FIRST place in ARCANE
that JOINS a signal series to a realized RETURN series — that join is the entire new attack surface and
is NOT covered by any Inc-3 gate (those prove a factor COLUMN is causal; they say nothing about whether
the engine multiplies `position[t]` by the right return). So:

- `BacktestEngine.run()` is `@final` (mirrors `DataLoader.load`, `AlphaFactor.compute`). The base owns the
  ENTIRE look-ahead-sensitive sequence; the SOLE untrusted author hook is `Strategy._target_positions`.
- A backtest leak is a **test failure** — an engine-level causality property (reusing
  `data/prefix_stability`) run on BOTH the signal→position MAPPING and the position→return JOIN, plus a
  perfect-foresight off-by-one MUST-FAIL canary — not a code-review judgment call.
- **Reliability:** strategy positions are derived from DERIVED factors and are themselves advisory; a
  `BacktestResult` is **statistics only**, with NO `passed/accepted/allocated/verdict` field (§4.3 / the
  Inc-5 boundary), enforced by an AST name-ban test.

Mirrors the proven idioms verbatim in intent: the `@final` base with one hook + trusted re-derivation;
typed fail-closed `ArcaneError` taxonomy; SHA-256 canonical-JSON content hashing with **lossless
`float.hex()`** (the `executor.idempotency.client_order_id` idiom); the AST leak-lint smell-catcher
backed by the runtime property as the real guarantee; `mypy --strict`, ruff/black, ≥85% coverage.

---

## 1. RESOLVED CONFLICTS (decision · rationale · rejected alternative)

**B1 — engine shape: `@final` class vs free function.** *DECISION: a `@final` `BacktestEngine.run()`
whose sole override point is `Strategy._target_positions(signals) -> positions`.* Rationale: the
position→return lag and the pnl formula MUST live in trusted base code (ADR §7) — a free function
`backtest(strategy, data)` puts the alignment in author code where a missing shift is a silent M4 leak.
*Rejected:* free-function / event-loop engines (off-by-one in the loop index is just as silent;
vectorized + the prefix-stability property gives a MECHANICAL proof a loop cannot).

**B2 — execution lag: does the engine add a second shift on top of the factor's `shift(1)`?** *DECISION:
YES — exactly one engine-owned execution shift.* The two shifts are DIFFERENT and both necessary: shift
#1 (factor layer) = signal **information-availability** (`factor[t]=raw[t-1]`, uses data ≤ t-1); shift #2
(engine) = trade **execution-realizability** (you observe the signal at the close of t, you can only
trade at the t+1 bar). This is NOT a double-count — it is the standard "observe at close, trade next
bar, hold one bar" daily backtest. *Rejected:* folding both into one shift (trades on the very close
that defined the signal observation — a classic 1-bar look-ahead / impossible simultaneous fill).

**B3 — pnl/return convention.** *DECISION: close-to-close, contemporaneous-return form so every series
is causal.* `realized[t] = position.shift(1)[t] * r_contemp[t] - cost[t]`, `r_contemp = close.pct_change()`
(strictly trailing). Algebraically identical to the forward form `position[t]*r_fwd[t+1]` but keeps NO
forward series in scope, so the causality gate sees only trailing series. *Rejected:* a forward-return
series in author scope (un-causal; only the base may hold the one named sanctioned forward helper, and
Inc-4 pins close-to-close so it needs none).

**B4 — portfolio construction: time-series per-symbol vs cross-sectional.** *DECISION: TIME-SERIES
per-symbol → a simple causal equal-weight portfolio aggregate.* Rationale: the Inc-2 `DataLoader` loads
ONE symbol at a time and the universe is the DEGRADED non-PIT `OperatorFileUniverse`; a cross-symbol
panel re-opens calendar-misalignment AND bakes survivorship into the SIGNAL. *Rejected/DEFERRED:*
cross-sectional rank long-short — deferred until Polygon lifts the degraded universe (the forward path is
a shared-calendar reindex + session-index join, never `iloc`, holes never imputed).

**B5 — ledger-2 high-water-mark (DB-deletion resets `n_trials` to 0).** *DECISION: conscious RE-DEFER to
Inc-5 with hedges + a HARD tripwire (see §8).* Rationale: Inc-4 PRODUCES `n_trials` but is
compute-and-report-only with NO DSR consumer; the consumer (and thus the HWM's natural home) is Inc-5.
Building it now defends a consumer that doesn't exist and adds a stateful corruption surface. *Rejected:*
clear-now (a 30-line `TrialLedger.assert_monotonic` sketch is recorded as a deferred item if overridden).

---

## 2. The FINAL `run()` template (the structural heart) — `backtest/engine.py`

```python
class BacktestEngine(ABC):
    @final
    def run(self, strategy: ResolvedStrategy, panel: SymbolPanel, *,
            as_of: AsOf, ledger: TrialLedger, cost: CostModel,
            folds: WalkForwardConfig) -> BacktestResult:
        # STEP 0  record the trial FIRST (kind='strategy') — no "uncounted" eval path exists
        # STEP 1  resolve & assert: ResolvedStrategy already bound to registered AlphaFactors (no phantom id)
        # STEP 2  signals = factor_matrix(panel)          # each col via AlphaFactor.compute (already shift(1))
        # STEP 3  warmup = registry.max_total_window()    # RE-DERIVED from the live registry (registry-2)
        #         assert frame-adequacy + warmup precede the first test fold (fail-closed FrameAdequacyError)
        # STEP 4  target_w = strategy._target_positions(signals)   # the SOLE untrusted author hook
        # GUARD A bar-alignment: index.equals + len match (the AlphaFactor GUARD-A idiom)
        # GUARD B finiteness: NO inf weight (an inf "max-leverage" bet is the position-layer inf-laundering)
        # STEP 5  position = target_w.shift(1)            # THE single base-owned EXECUTION lag
        # STEP 6  r_contemp = close.pct_change()          # strictly trailing
        # STEP 7  cost_t = cost.per_bar(position)         # turnover-only, trailing (never reads close_t/vol_t)
        # STEP 8  realized = position * r_contemp - cost_t
        # STEP 9  per-fold OOS slice + statistics (compute-and-report; NO threshold applied)
        # STEP 10 stamp spec_hash, n_trials_at_eval (live ledger read), survivorship_biased -> BacktestResult
        return result

    # SOLE author hook — pure, deterministic, prefix-stable; sees ONLY the factor matrix, NEVER prices.
    @abstractmethod
    def _target_positions(self, signals: pd.DataFrame) -> pd.DataFrame: ...
```

The author CANNOT override `run`, cannot touch the return series, cannot touch either lag. `run` takes a
`ResolvedStrategy` (the product of `resolve_spec`) so a spec with a phantom `factor_id` structurally
cannot reach `run`.

### 2.1 Why the off-by-one is the whole ballgame (the alignment proof)

`position[t] = target_w.shift(1)[t] = g(factor[t-1]) = g(raw[t-2])` — depends only on data ≤ t-2. It
multiplies `r_contemp[t] = close[t]/close[t-1]-1`, the move realized **at the close of t**, strictly
after the decision. Equivalently: a signal observed at the close of t-1 (`factor[t]`) is executed at the
close of t and earns close[t]→close[t+1] — the realistic single-execution-bar daily backtest. Using
`position[t]*r_contemp[t]` (no execution lag) would trade on the very close that produced the signal
(1-bar look-ahead). Using `shift(2)` is merely STALE (uses ≤ t-3 — NOT a leak; caught by a per-bar value
test, not prefix-stability, exactly as Inc-3 §2.2 notes for double-shift staleness).

---

## 3. `StrategySpec` + resolution — `backtest/spec.py`

Frozen pydantic v2, the `executor/intent.py` idiom verbatim (`ConfigDict(frozen=True, extra='forbid')`).
**Two-phase validation** so the spec is decoupled from a runtime-built registry:

- **`FactorLeg`** (frozen, `extra='forbid'`): `factor_id: str` (validator: `^[a-z0-9_]+$`),
  `weight: float` (`Field(abs ≤ 1)`), `direction: Direction` (StrEnum `LONG|SHORT`, mirrors `Side`).
- **`StrategySpec`** (frozen, `extra='forbid'`): `name: str` (NFKC canonical validator reused from
  `intent.py`), `legs: tuple[FactorLeg, ...]` (non-empty, unique `factor_id`s),
  `rule: CompositionRule` (StrEnum, ONE member to start: `Z_WEIGHTED_SUM`; new rules are counted trials),
  `composite_scale: float` (`Field(gt=0)`), `spec_version: int`, `cost_model_id: str`.
- **Structurally NO threshold field** (ADR §7 "no field to write 'RSI<30'"): legs operate in the factor's
  already-z-scored `[-3,3]` space; `extra='forbid'` rejects any smuggled `threshold/level/cutoff` key.
- **Phase 1 (construction):** registry-free pydantic validators enforce SHAPE only.
- **Phase 2 (resolution):** `resolve_spec(spec, registry) -> ResolvedStrategy` iterates legs via a NEW
  `FactorRegistry.get(id) -> AlphaFactor` that **RAISES `UnknownFactorError`** (an `ArcaneError`,
  fail-closed) on any unregistered id — never a `KeyError`, never a silent skip. `ResolvedStrategy` binds
  the `AlphaFactor` instances so `factor.compute`'s `shift(1)` stays on the critical path.
- **`spec_hash`** = `"arcane-strategy-" + sha256(canonical_json(field_dict))[:40]`, using the
  **`trial_ledger._canonical` idiom byte-for-byte** (`sort_keys`, compact separators, **NO `default=str`**
  so an un-encodable field RAISES) with float weights serialized **losslessly via `float.hex()`** (the
  `idempotency.client_order_id` idiom). `spec_hash` (not `name`) is the gate identity: any weight,
  direction, rule, factor_id, spec_version, or `cost_model_id` change → new hash → forced Inc-5 re-gate.
- Regime-label references are DEFERRED to Inc-6 (regime + allocator).

---

## 4. The strategy set (4 — ADR §5 "3–5, not 20")

All standard textbook compositions of registered factor_ids in z-space; fixed literal weights (NO grids,
NO orthogonalization — pre-pruning for orthogonality is itself a tuning-toward-profit move ADR §5
forbids); correlated families intentionally retained (Inc-5 prunes; ~2 survivors expected). Each is a
COUNTED trial. Time-series per-symbol → equal-weight portfolio (§B4).

| # | id | factors | weights | mode | rationale |
|---|---|---|---|---|---|
| 1 | `ts_momentum_blend` | mom_21d, mom_63d, mom_126_skip21 | 0.34/0.33/0.33 | long-short | multi-horizon time-series momentum |
| 2 | `ts_meanrev_short` | reversal_5d, close_loc_in_range | 0.6/0.4 | long-short | short-horizon reversal (flips fast → stresses turnover cost) |
| 3 | `trend_location` | sma_ratio_20_50, dist_from_sma_50, mom_63d | 0.4/0.3/0.3 | long-only | trend-location; shares mom_63d with S1 ON PURPOSE so Inc-5 must prune |
| 4 | `lowvol_liquid_tilt` | vol_21d, amihud_illiq_21d, dollar_vol_21d | −0.4/−0.3/0.3 | long-only | low-vol liquidity tilt |

`atr_14`, `hl_range_21d`, `rel_volume_21d` are intentionally unused (using all 13 is not a goal).
**Trial ledger after this run: `n_trials = 17` (13 factors + 4 strategies).**

---

## 5. Cost model (M3 defense) — `backtest/cost_model.py`

Conservative AND standard. Frozen pydantic v2; over-stating cost can only KILL a marginal edge, never
manufacture one (ADR §0). Charged on EVERY fill — no zero-cost fills.

- **Formula:** `cost_t = (commission_bps + half_spread_bps + slippage_bps) * cost_scale *
  abs(position.shift(1) - position.shift(2))_t * gross_capital` (1e-4 per bp). Turnover = |Δ executed
  position| at the execution bar; an unchanged target rides the symbol return at ZERO cost between
  rebalances. The cost series is itself fed through prefix-stability (it reads only trailing positions,
  never `close_t`/`volume_t`).
- **Conservative defaults:** commission 1.0, half_spread 3.0 (top of the 1–3 bp US-equity band),
  slippage 2.0 → ≈ **6 bps one-way**. No field can lower a component below a hardcoded conservative floor
  (the `constants.py` EQUITY_FLOOR idiom — config can only make it STRICTER).
- **`cost_scale: float` (`Field(gt=0)`, default 1.0):** the EXPOSED handle for the Inc-5 2×/3× cost-stress
  veto. Inc-4 ships it but NEVER calls it above 1.0. Structurally cannot produce a zero/negative fill
  (non-negative bps × positive scale × |turnover|; exactly zero only when turnover is zero).
- **Market-impact + adverse-selection are EXCLUDED** — they are the Inc-5 conservative-live-cost VETO
  (ADR §8), not the Inc-4 base model.
- `cost_model_id` is bound into `spec_hash`, so a cost change is a NEW trial.

---

## 6. Walk-forward splitter — `backtest/walk_forward.py`

Standard de Prado **purged + embargoed** walk-forward; a pure function (no registry coupling — keeps it
reusable). ADR §8 "**walk-forward 12/3/3**" = **12-month TRAIN / 3-month TEST(OOS) / 3-month STEP**,
measured in CALENDAR months mapped to sessions via the calendar authority (`calendar.sessions_in_range`),
NEVER raw row counts (a row window silently mis-spans across holidays/halts).

- **purge** = the label/holding horizon `H` (Inc-4 strategies hold 1 bar close-to-close → `H=1`); an
  EXPLICIT arg so a future fitted/Inc-5 consumer passes its real multi-bar horizon and the gap widens
  automatically.
- **embargo** = a small fraction (~1% of the test span, de Prado), floored at `H`, applied AFTER the test
  window before the next train resumes — kills serial-correlation bleed from test residuals into train.
- **ANCHORED / EXPANDING** train (start fixed at history start, end grows) — the more falsifying choice
  (ADR §0): expanding train evaluates OOS against the most-informed in-sample and avoids a tunable window.
- Output: a list of `(train_idx, test_idx)` with DISJOINT index sets and `train_end + purge ≤ test_start`.

**Warmup adequacy (the registry-2 author-trust fix), enforced in the ENGINE not the splitter:** the
engine re-derives `warmup = registry.max_total_window()` from the LIVE resolved registry (currently 169)
and asserts every test fold's factors are fully formed (the panel provides ≥ `warmup` trailing bars
before the first test window) — fail-closed `FrameAdequacyError`. Factors are computed once on the full
panel (automatic warmup, no fold cold-start), then sliced per fold. For Inc-4's NON-fitted deterministic
strategies there is no train→test parameter leakage (nothing is fitted), so purge/embargo are the
standard de Prado scaffolding + forward-compat; the engine causality property (§7) is the real guarantee.
**HARD Inc-5 tripwire:** a FITTED consumer MUST set `purge ≥ registry.max_total_window() + label_horizon`
(re-derived, not author-declared) before it trusts an OOS fold.

---

## 7. Causality property + MUST-FAIL tests (the teeth) — run INSIDE pytest

Reuse `data/prefix_stability.assert_prefix_stable` UNCHANGED via TWO `PrefixComputation` adapters
(mirroring `registry.validate_all`'s `_PrefixView` over `_raw` AND `compute`):

- **`PositionView.compute(df)` = `strategy._target_positions(factor_matrix(df))`** — proves the
  signal→position MAPPING is causal.
- **`RealizedView.compute(df)`** = the pre-cost realized series — proves the position→return JOIN is causal.
- **Splitter property:** `split(prefix)` equals `split(full)` restricted to folds fully within the prefix.
- **Frame-adequacy + value-adequacy** (the registry-1 / failopen-1 lessons): require panel length ≥
  `2*(train+embargo+test) + margin` AND ≥ 1 non-NaN non-zero realized entry, else `FrameAdequacyError`.
  **FULL-panel checks, NO per-fold slice optimization** (`insight-gate-optimization-can-weaken`).

**MUST-FAIL canaries (a green here with the bug present = the gate lost its teeth):**
1. `RealizedView` (prefix-stability) MUST FAIL on an engine variant that reads FUTURE data — a forward
   return (`close.shift(-1)/close-1`), a `signal.shift(-1)` map, or a full-sample normalization.
   **NOTE (red-team F1, empirically verified):** prefix-stability does NOT catch a *dropped execution
   shift* — `target_w * close.pct_change()` (no shift) is still causal (reads only ≤ t), it is merely
   mis-lagged. The dropped-shift off-by-one is caught by canaries (2) and (3), NOT by `RealizedView`.
2. Per-bar value test: `realized[t] == position[t-1]*(close[t]/close[t-1]-1) - cost[t]` at a hand bar
   (catches a wrong shift COUNT — dropped shift or double shift).
3. **Perfect-foresight off-by-one canary:** a contemporaneous-foresight position earns ~flat under the
   correct execution lag and a blatant profit with the shift dropped — the semantic off-by-one check.
4. `PositionView` MUST FAIL for a `signal.shift(-1)` mapping AND for a full-sample-normalized mapping
   (`signal / signal.std(whole frame)`).
5. GUARD-B: a mapping returning an `inf` weight RAISES (not a saturated bet).
6. Splitter with `purge=0` produces an OOS session also present in an adjacent fold (overlap detected).
7. Cost-series prefix-stability MUST FAIL if `cost_t` reads `close_t`/`volume_t`; `net ≤ gross` always;
   2×/3× `cost_scale` monotonically reduces net Sharpe.
8. AST name-ban: `BacktestResult` has NO `verdict/passed/allocated/accept/kill/deflated/dsr/
   reality_check/pbo/psr` symbol anywhere in the package.
9. Survivorship: a `BacktestResult` on the non-PIT operator universe carries `survivorship_biased=True`
   and `survivorship_t2(meta).passed is False`; no public path yields a metric without the universe meta.

---

## 8. Trial-ledger integration — REUSE, no fork — `backtest/ledger_integration.py`

- **REUSE `trading.factors.trial_ledger.TrialLedger` VERBATIM** (no fork, no subclass, no second table —
  a split count re-introduces the M18 under-count). `record(kind="strategy", ref_id=name, params=<the
  full canonical StrategySpec field dict incl. legs/weights/rule/spec_version/cost_model_id>)`.
  `kind="strategy"` partitions cleanly from `kind="factor"` in the SAME `trials` table; `n_trials =
  COUNT(*)` spans BOTH layers (ADR §5 cumulative count).
- The `record` params are the SAME dict `spec_hash` hashes (byte-identical `_canonical`); **a test asserts
  `spec_hash` and the ledger `combo_hash` agree**. An un-encodable param RAISES (no `default=str`).
- **Record BEFORE evaluate:** `run` records the trial before computing any statistic — no uncounted path.
  `INSERT OR IGNORE` makes a re-run of the same spec a no-op (monotonic; never double-counts). N distinct
  specs raise `n_trials` by exactly N. Building the 4 defaults → `n_trials = 17`. (2×/3× cost-stress is
  the SAME strategy under a different cost assumption = an Inc-5 veto computation, NOT a new Inc-4 trial.)
- **ledger-2 HWM: conscious RE-DEFER to Inc-5** (§B5). HEDGES built now: keep the ledger DB on durable
  `state/` storage (asserted at startup) AND stamp `n_trials_at_eval` into every `BacktestResult` so Inc-5
  has an independent append-only floor. **HARD Inc-5 TRIPWIRE (written here so it cannot be lost):** the
  Inc-5 DSR consumer MUST build a persisted monotonic high-water-mark (raise if `COUNT(*)` ever drops
  below it; atomic temp→fsync→`os.replace`, the `kill_switch` idiom) BEFORE its first `n_trials` read.

---

## 9. Statistics output — `backtest/statistics.py` + `BacktestResult`

A FROZEN pure-statistics container per `spec_hash` + fold-set with **NO `passed/accepted/killed/
allocated/verdict` field** (a test asserts no such boolean attribute exists). Compute-and-report ONLY —
Inc-4 does NOT apply any ADR §8 threshold (that is the Inc-5 accept/kill gate).

- `annualized_sharpe = mean(net_r)/std(net_r, ddof=1) * sqrt(252)` (daily, zero rf, stated); NaN (never
  0/inf) on a degenerate zero-variance window.
- `per_fold_oos_sharpe: tuple[float, ...]`, `fraction_folds_positive: float` (REPORTED only, NO 60%
  threshold).
- `total_return`, `annualized_return = (1+total)**(252/n_bars) - 1`.
- `max_drawdown = min_t(equity_t / running_max - 1)`.
- `average_turnover`; gross-vs-net equity (`net_r = gross_r - cost_r`; test asserts `net ≤ gross` always).
- per-symbol pnl + a SIMPLE causal equal-weight portfolio aggregate (cross-sectional ranking/normalization
  DEFERRED — avoids a full-sample-normalization leak).
- `n_trials_at_eval: int` (live fail-closed read from the SHARED ledger — the Inc-5 DSR/M18 input snapshot).
- `spec_hash` + `cost_model_id` + fold geometry (12/3/3, anchored) stamped (ADR §7 binds the stat to the
  exact config).
- `survivorship_biased = True` / `survivorship_unverified = True` propagated from the non-PIT universe
  meta as a REQUIRED field (no public path strips the provenance).
- a min-trade-count flag REPORTED (ADR §8: ratios are noise below a floor) — never silently smoothed,
  never used to gate.

---

## 10. Leak-lint extension + `make inc4`

The runtime engine-causality property is the load-bearing guarantee; leak-lint is the complementary AST
smell-catcher (best-effort, Inc-2/3 posture). The ONLY FIX-NOW leak-lint change is **extending the scan
root to `src/trading/backtest`** (the existing SHIFT_NEG/CENTERED_ROLLING/RESAMPLE/SORT/IMPUTATION/
MODULE_TICKERS rules already apply). `make inc4` MIRRORS `inc3` EXACTLY:

```make
inc4:
	$(PY) ruff check src tests
	$(PY) black --check src tests
	$(PY) python -m trading.data.leak_lint src/trading/data src/trading/factors src/trading/backtest
	$(PY) mypy
	$(PY) pytest --cov=trading --cov-report=term-missing --cov-fail-under=85 -q
	@echo "Increment 4 gate: PASS"
```

`make inc1 && inc2 && inc3 && inc4` must all stay green every commit. The engine causality property +
frame/value-adequacy + the must-fail canaries run INSIDE pytest (`tests/unit/test_backtest_engine.py`).

---

## 11. Build clusters (TDD; each: tests → `inc1 && inc2 && inc3 && inc4` green → commit → push → ff main → STATE+memory)

| C | name | files | key tests (RED-first) |
|---|---|---|---|
| C1 | errors taxonomy | `backtest/errors.py` (`BacktestError(ArcaneError)` sibling root; `StrategySpecError`, `UnknownFactorError`, `WalkForwardError`, `CostModelError`, `BacktestContractError`, `FrameAdequacyError` reuse) | every error is an `ArcaneError`, never mis-bucketed by `except DataError`/`except FactorError` |
| C2 | frozen `StrategySpec` + `spec_hash` | `backtest/spec.py` (`StrategySpec`, `FactorLeg`, `CompositionRule`, `Direction`) | frozen/`extra=forbid` rejects a smuggled threshold key; lossless `float.hex` hash (1e-9 weight diff → different hash; stable across fresh processes; un-encodable field RAISES); shape validators |
| C3 | registry resolution fail-closed | `backtest/spec.py` `resolve_spec` + new `FactorRegistry.get(id)` | `mom_999d` → `UnknownFactorError` (never `KeyError`/silent-skip); `ResolvedStrategy` binds `AlphaFactor` instances |
| C4 | conservative cost model | `backtest/cost_model.py` | Hypothesis `per_bar_cost ≥ 0` always, `== 0` iff `|Δw|==0`; a signed-slippage / `cost_scale=0` mutant FAILS; config cannot lower below the floor |
| C5 | walk-forward splitter | `backtest/walk_forward.py` | disjoint OOS sets; `train_end+purge ≤ test_start`; split-on-prefix stable for past folds; `purge=0` → overlapping OOS (must-fail) |
| C6 | statistics compute-only | `backtest/statistics.py` | NaN (never 0/inf) on zero-variance/empty fold; toy property tests; AST name-ban (no `deflated/dsr/reality_check/pbo/psr/allocated/accept/kill/verdict` symbol) |
| C7 | ledger integration | `backtest/ledger_integration.py` | N distinct specs → `n_trials += N`; same spec is a no-op; 4 defaults → `n_trials = 17`; `spec_hash == combo_hash` byte-for-byte; non-JSON param → `TrialLedgerError`; no stats path without a preceding record |
| C8 | final `BacktestEngine` + causality | `backtest/engine.py` (`@final run`, `_target_positions` hook, `BacktestResult`, `PositionView`/`RealizedView`, warmup/n_trials/survivorship stamping) | `PositionView`/`RealizedView` prefix-stability; per-bar value test; perfect-foresight off-by-one canary (must-fail); GUARD-B inf-weight; `net ≤ gross`; `cost_scale` monotonicity; `survivorship_biased=True` on `OPERATOR_FILE`; `run` rejects a raw unresolved `StrategySpec` at the type level; frame/value adequacy raises on a too-short/all-zero panel |
| C9 | leak_lint + `make inc4` + integration | `Makefile` (`inc4` + widen leak-lint roots), the 4 default strategies | the 4 defaults run end-to-end (mirrors `test_default_registry_validates_clean`); a planted `shift(-1)`/`resample`/`sort_values` in a backtest source file is leak-lint-flagged; a module-scope ticker list trips MODULE_TICKERS |

---

## 12. Non-negotiables + deferred items + checkpoint verdict

**Non-negotiables carried in:** executor stays NO-OP; `LIVE_MODE=false`; the LLM is never in the submit
path. Strategy positions/results are DERIVED/advisory — never gate an order. Every error path fails
CLOSED; an `inf` weight is rejected; NaN is the honest hole. Do NOT tune toward backtest return (ADR §0);
keep the 4 correlated strategies (Inc-5 prunes). Look-ahead is a TEST FAILURE (the engine causality
property), not a review call. **Inc-4 NEVER gates/approves/kills — the Inc-5 bias gate is the HARD
boundary and is NOT pulled forward.**

**Deferred items (carried to the backlog):**
- ledger-2 HWM → Inc-5 (hedges: durable storage + `n_trials_at_eval`; HARD tripwire in §8). Clear-now
  `TrialLedger.assert_monotonic` sketch recorded if overridden.
- Cross-sectional / cross-symbol portfolio construction → after Polygon lifts the degraded universe.
- Next-OPEN execution price convention → Inc-5+ (Inc-4 pins close-to-close, the conservative default).
- Equal-weight aggregate beyond the simple causal sum → later (avoids a full-sample-normalization leak).
- registry-2 residual + leaklint-2 structural (stateful `_raw`) carried from Inc-3 unchanged; the
  engine-level prefix-stability is the runtime backstop.
- leak_lint aliased-bypass stays WON'T-FIX (Inc-2/3 posture); only the scan-root widening is FIX-NOW.

**CHECKPOINT VERDICT — all FOUR operator-decision criteria are FALSE → the lead proceeds autonomously:**
1. cost model nonstandard? **FALSE** — conservative + standard (≈6 bps one-way on turnover, pessimistic,
   no zero/negative fills, market-impact/adverse-selection excluded as the Inc-5 veto).
2. walk-forward nonstandard? **FALSE** — standard de Prado purged + embargoed 12/3/3, anchored/expanding.
3. too many strategies? **FALSE** — exactly 4 (≤5), fixed literal weights, no grids.
4. ADR change / Inc-5 pulled forward? **FALSE** — pure implementations of ADR §5/§7/§8 frozen contracts;
   `BacktestResult` has no verdict field; ledger-2 HWM consciously re-deferred to Inc-5.
