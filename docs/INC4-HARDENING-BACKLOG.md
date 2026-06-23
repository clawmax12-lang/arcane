# Increment 4 — Strategy/Backtest-Layer Red-Team Backlog

**Source:** adversarial red-team Workflow `wf_60bf76b3-d42` (6 finder lenses across 2 waves of 3 —
backtest-leak/alignment, cost-realism, ledger-monotonicity, inc5-boundary, false-green-gate,
adversarial-skeptic — all 6 alive; each ran empirical `uv run python` repros). 2026-06-23.

**Method (honest).** Unlike Inc-2/Inc-3, this run was **NOT throttled** — all 6 lenses completed with
runnable repros. The lead then **independently re-verified** every fix-now candidate with its own
repros before remediating (pandas-3 `pct_change` no-pad confirmed; `total_bps` inf→`[inf, nan]`
confirmed; a dropped execution shift confirmed prefix-stable; the headline confirmed full-sample). No
finding was taken on the lens's word alone.

## Verdict
**No reachable LIVE look-ahead leak and no reachable Inc-5 boundary violation in the shipped
Increment-4 system.** Mutation-confirmed: the position→return JOIN is causal, the single execution
shift is load-bearing (removing it turns committed tests RED), the gate has teeth, `BacktestResult`
is verdict-free, the cost model is conservative + monotone-toward-killing-edge, and `n_trials` identity
is field-complete over `StrategySpec`. Every finding is a hardening, an accuracy correction, or a
latent gap unreachable from shipped code.

## FIX NOW — DONE (remediated in `8915ec3`, TDD + gated)
1. **[low] RT03 — `pct_change` leak-safety silently depended on the pandas-3 default.** `close.pct_change()`
   does not pad a NaN hole on the pinned pandas 3.0.3, but a future pandas could reintroduce padding (a
   fabricated cross-hole return). **Fix:** both engine return computations now pass `fill_method=None`
   explicitly; regression test `test_pct_change_does_not_pad_a_price_hole` pins it.
2. **[low] M3-COST-01 — `total_bps` could overflow to `+inf`, then be NaN-masked.** The bps fields are
   individually finite (`allow_inf_nan=False`), but `total_bps` re-multiplies by `cost_scale`; an absurd
   config (~1e308 bps) overflows to `inf`, and the resulting `inf/NaN` cost would be silently dropped by
   `statistics._finite()`. Unreachable on the shipped path (defaults sit at the 6-bps floor,
   `cost_scale=1.0`) and biases AGAINST profit, but **fix:** `per_bar_cost` now raises `CostModelError`
   on a non-finite `total_bps` (fail closed). Test `test_overflowing_total_bps_fails_closed`.
3. **[medium] skeptic-1 — headline Sharpe/return/drawdown were FULL-SAMPLE (train+OOS blended).** Not a
   leak (non-fitted strategies; Inc-4 never gates), but a reader / the Inc-5 consumer could mistake the
   blended headline for OOS, contradicting ADR §0 (walk-forward OOS is the primary edge evidence).
   **Fix:** `BacktestResult` now carries explicit train-free `oos_total_return` / `oos_annualized_sharpe`
   / `oos_max_drawdown` over the concatenated fold test windows; the un-prefixed headline is documented
   FULL-SAMPLE. Tests assert the OOS fields exist and are computed.
4. **[medium] false-green F1 — the design's RealizedView must-fail claim was empirically WRONG.**
   `docs/INCREMENT-4-DESIGN.md` §7 claimed `RealizedView` prefix-stability catches a *dropped execution
   shift*. It does NOT — a dropped shift stays causal (reads only ≤ t, just mis-lagged), so
   prefix-stability passes. The actual teeth are the per-bar value test + the perfect-foresight canary.
   **Fix:** §7 corrected; test `test_dropped_execution_shift_is_prefix_stable_but_caught_by_value_and_canary`
   PINS the true behavior (the gate-optimization-can-weaken lesson: a must-fail claim must be TRUE).

## DEFER (real but latent / belongs to the consumer) — with HARD Inc-5 tripwires
- **[ledger F1, medium] Cost-model numbers + walk-forward fold geometry are NOT in the trial identity.**
  `cost_model_id` and `WalkForwardConfig` are not in `spec_hash`/`combo_hash`, so a future consumer that
  SWEEPS cost assumptions or fold geometry while keeping the same `cost_model_id` label would collapse
  distinct evaluations to one trial → `n_trials` under-counts → DSR under-deflates (the M18 vector). Not
  reachable in Inc-4 (fixed `conservative_v1`, no sweep). **HARD Inc-5 TRIPWIRE:** before the DSR
  consumer reads `n_trials`, fold the swept cost/fold degrees of freedom into the trial identity (a
  richer `cost_model_id`, or the cost/fold params in the recorded `params`).
- **[ledger-2, carried from Inc-3] DB-file-deletion resets `n_trials` to 0 (no high-water-mark).**
  Consciously RE-DEFERRED to Inc-5 (the DSR consumer's natural home; building it now defends a consumer
  that does not exist). HEDGES live now: the ledger sits on durable storage and every `BacktestResult`
  stamps `n_trials_at_eval`. **HARD Inc-5 TRIPWIRE:** the DSR consumer MUST persist a monotonic
  high-water-mark (raise if `COUNT(*)` drops below it; atomic temp→fsync→`os.replace`, the kill-switch
  idiom) BEFORE its first `n_trials` read.
- **[false-green F3] Anchored/expanding train re-absorbs a prior fold's OOS window into the next train.**
  Harmless in Inc-4 (nothing is fitted, so train composition cannot leak into a parameter). **HARD Inc-5
  TRIPWIRE (already in design §6/§8):** a FITTED consumer MUST set `purge ≥ registry.max_total_window() +
  label_horizon` (re-derived, not author-declared).
- **[false-green F4 / skeptic] `survivorship_unverified` has no structural floor.** A caller may pass
  `survivorship_unverified=False`; the default is the honest `True` and Inc-4 never gates, so no Inc-4
  leak. **HARD Inc-5 TRIPWIRE (design §9):** the Inc-5 T2 survivorship test MUST read
  `survivorship_biased`/`survivorship_unverified` and return `passed=False` while degraded — never a
  clean pass.
- **[skeptic INC4-RT-02] `composite_scale` is unbounded.** A very large scale collapses the z-composite
  to a `sign()` rule (an implicit zero-threshold), eroding the "no hand-coded threshold" intent — but it
  is prefix-stable, manufactures no profit, and M18 still counts it (a new `spec_hash`). DEFER: bound the
  scale (or move to a saturation-free position map) when the strategy-authoring surface opens (Inc-5/6).
- **[skeptic INC4-RT-03 / backtest RT04] Cross-symbol robustness.** A mid-series NaN in `close` is
  tolerated (the bar drops; not a leak — the factor base treats NaN as the honest hole) and the
  equal-weight `mean(axis=1)` reweights onto present symbols on such a bar. The Inc-2 loader's quality
  gate rejects NaN OHLCV, so a loader-produced panel cannot hit this; the engine requires a shared
  session index (cross-calendar fails closed). DEFER cross-sectional/cross-symbol construction until
  Polygon lifts the degraded universe (design §B4): the forward path is a shared-calendar reindex +
  session-index join, never `iloc`, holes never imputed.
- **[false-green F2 / skeptic INC4-RT-04, carried from Inc-3] Runtime prefix-stability is test-only and
  `@final` is mypy-static.** Correct by design (look-ahead is a DEV/gate-time check; the committed
  engine + integration tests run the property over the fixed Z_WEIGHTED_SUM mapping on full panels, and
  a length-dependent leak IS caught by `first_violation`). A future custom composition rule must be added
  to the gated tests. Same layered posture as the Inc-2 `DataLoader` / Inc-3 `AlphaFactor`.

## WON'T FIX (by design / documented posture)
- **[inc5-boundary INC4-RT-01] The AST verdict name-ban is an 11-symbol denylist (smell-catcher, not a
  structural guarantee).** None of the banned symbols exist in the shipped backtest package (grep + AST
  confirmed); the load-bearing boundary guarantee is the **verdict-free `BacktestResult` dataclass**
  (a test asserts no accept/kill/allocated/verdict field). The denylist is the complementary static net,
  exactly as `leak_lint` is for look-ahead.
- **[inc5-boundary INC4-RT-02] Position-layer GUARD-B (no-inf) runs after the clip and is effectively
  vacuous on the shipped path.** An `inf` can only enter `compose_positions` via a factor's `compute()`,
  and `AlphaFactor.compute` is `@final` and raises on any `inf` (base GUARD B); `composite_scale`/weights
  are `allow_inf_nan=False`. So `target_w` is provably finite. GUARD-B remains as tested defense-in-depth
  (the unit test exercises it directly with an injected `inf`).
- **[skeptic INC4-RT-05] Engine panel tz check is `tz is None` (weaker than the factor base's `== UTC`).**
  Fails closed either way: a non-UTC panel raises (`AlphaFactor._assert_bar_frame` enforces `== UTC`
  downstream when `compute` runs), so only the error TYPE differs. Documented; not worth a duplicate check.

---

# Red-team ROUND 2 — independent re-audit (`wf_618edde8-565`, 2026-06-23)

**Why a second round:** the operator asked for an independent re-check of the seal. A fresh 6-lens
red-team Workflow ran on `e1c73f4`. **Method (honest):** the 6 finder lenses completed (25 raw
findings) but the **Verify + Synthesize phases were 100% rate-limited** (infra throttle — "not your
usage limit"). Per `insight-autonomous-quality-discipline` a throttled "0 confirmed" is NOT a clean
pass, so the lead **verified every material finding single-threaded** with its own `uv run python`
repros. (Lenses confirmed CLEAN, matching the round-1 verdict: cost-realism 5×INFO, Inc-5 boundary
5×INFO, ledger/M18 TL-1/TL-2 positive confirmations.)

## FIX NOW — DONE (remediated in `b5739e5`, TDD + gated; `make inc1..inc4` green, 97.67%)
1. **[CRITICAL-class, reachable] NUM-2 — `annualized_sharpe` scored a WIPED fold as a strong positive.**
   A per-bar realized return `<= -1.0` (RUIN; reachable on a short into a >100% single-bar up-move —
   confirmed: `gross_returns(short=-1, +150% bar) = -1.5`) gives the mean/std (compounding-blind)
   Sharpe a large POSITIVE while the account is at zero, and `fraction_folds_positive` counted it as a
   winner — fabricated edge (ADR §0). **Fix:** a ruin fold → `annualized_sharpe` / `annualized_return`
   = `NaN` (never a win; drops out of `fraction_positive`).
2. **[reachable] NUM-1/NUM-3 — `max_drawdown` reported a false 0.0 on ruin.** Once equity crosses zero
   the `equity/running_max` ratio sign-flips and `.min()` returns `0.0` (zero drawdown on a blowout);
   the exact `-1.0` boundary returned `NaN`+warning. **Fix:** a ruin fold → `max_drawdown` /
   `total_return` = `-1.0` (an honest total loss; also closes the even-count `[-2,-2] → prod>0`
   fabrication in `total_return`/`annualized_return`).
3. **[MED, reachable] WF-1 — `step_months < test_months` overlapped OOS test windows.** The engine
   concatenates each `fold.test` into the OOS index → overlapped sessions are double-counted →
   inflated OOS magnitude (e.g. `test=6,step=3` → 2804 rows / 1434 unique). **Fix:** new
   `WalkForwardConfig` `model_validator` rejects `step < test`. The 12/3/3 default (`step == test`)
   is unaffected.

Honest reachability note: the shipped 4 strategies on the large-cap operator universe never produce a
>100% single-bar move, so NUM-1/2 had ~nil practical impact today — fixed because the reductions are
general and **Inc-5's bias/kill gate reads these exact stats** (`per_fold_oos_sharpe`,
`fraction_folds_positive`, `oos_*`); a stat that can call a wipeout a win is a latent landmine there.

## DEFER / accepted (round 2)
- **[WF-2, LOW] `step_months > test_months` silently drops OOS sessions** (e.g. `test=1,step=6` skips
  83%). This is honest sub-sampling (it does NOT inflate/fabricate a number), so it is ALLOWED as a
  deliberate caller choice; only the overlap (`step < test`) double-count is rejected. The 12/3/3
  default is full coverage. DEFER a coverage-report field to Inc-5/6 if sub-sampled geometries get used.
- **[ENGINE-NO-RUNTIME-FACTOR-GATE-1, MED] = the existing `INC4-RT-04` DEFER.** A sanctioned leaky
  `_raw` reaches the engine (no runtime `validate_all`), but it IS caught at gate-time by the registry's
  `validate_all` prefix-stability check (independently re-confirmed: a future-peek `_raw` raises
  `PrefixStabilityError` at k=1). Runtime re-gating stays test-only by design (same layered posture as
  Inc-2/Inc-3). No change.
