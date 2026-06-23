# Increment 5 — Bias/Kill-Gate + Notifier Red-Team Backlog

**Source:** adversarial red-team Workflow `wf_fa2cf190-080` (6 finder lenses — teeth-tails,
t1-consistency, deflation-ledger, family-composer, notifier-secrets, seal-handoff — → 3 independent
verifiers → synthesis). 2026-06-23.

**Method (honest).** This run was **NOT throttled** — all 6 finders + 3 verifiers + the synthesizer
completed (10 agents) with runnable `uv run python` repros against the SHIPPED public API. The lead
then **independently re-reproduced** every fix-now finding AND every post-fix close with its own
repros before and after remediating (FC-1 forged-flag end-to-end ALLOCATE confirmed, then confirmed
KILLED; TT-1 `spa_pvalue(const)=0.0` confirmed, then confirmed NaN; NOTIFY-1 `InvalidURL` escape
confirmed; FC-3 vacuous `all([])` confirmed). No finding was taken on a lens's word alone.

## Verdict
**The gate's KILL teeth are sound after remediation.** 5 of 6 finder lenses found NO reachable gate
fail-open (T1 consistency, deflation/HWM count, family-composer core, notifier secret-discipline, seal
boundary all HELD under attack). The red-team found **one reachable cardinal-sin fail-open (FC-1)** and
**one teeth-gap (TT-1)**, both empirically reproduced through the shipped public API and both now
**CLOSED + regression-tested**. The gate was already fail-CLOSED in its DEFAULT configuration (all 4
toys correctly KILLED); FC-1 required a non-default forged flag. All fix-now remediated in `1150d30`.

## FIX NOW — DONE (remediated in `1150d30`, TDD + gated; `make inc1..inc5` green, 95.89%)

1. **[CRITICAL, reachable] FC-1 — T2 survivorship KILL was flippable to PASS via a forgeable kwarg.**
   `SymbolPanel(survivorship_unverified=False)` (a bare public field) flows through `engine.run` into
   `BacktestResult` and `t2_survivorship` trusted it → with strong-edge strategies the family went
   `allocated=True` (the cardinal sin: ALLOCATE when it must KILL). Architectural regression from
   Inc-2's `universe.py` (where survivorship is a DERIVED, forge-proof property). **Fix
   (authoritative, gate-side, no Inc-4 reopen):** `tests_t2._PIT_VERIFIER_WIRED = False` — while no
   PIT-universe verifier is wired (Polygon deferred), survivorship is UNVERIFIABLE by any shipped code
   path, so `t2_survivorship` fails CLOSED UNCONDITIONALLY regardless of the flags. The self-attested
   flag can no longer grant a pass. When a real PIT verifier lands, T2 falls back to requiring both
   flags `False`. Regression tests: forged-flag result → T2 KILL; forged-flag family → all KILLED
   end-to-end; the future-wired path passes only with `_PIT_VERIFIER_WIRED=True` AND clean flags.

2. **[HIGH, reachable] TT-1 — `spa_pvalue`/`pbo_fraction` PASSED on a constant-nonzero column.** A
   constant-nonzero OOS column has a NaN per-obs Sharpe, but `np.std` leaves `omega ≈ 1e-16` (not
   bit-zero) so the exact `(omega == 0).any()` guard missed it → `spa_pvalue(const)=0.0` (PASS),
   silently disabling the SPA superiority barrier for the whole family (SPA is a shared component).
   **Fix:** `_matrix_is_admissible` now rejects ANY constant column (`min == max` per column) → NaN →
   KILL the whole family (mirrors the `_moments` constant detector). Closes both SPA and PBO.
   Regression test: `spa_pvalue`/`pbo_fraction` on a pure-const AND a mixed (one-const-sibling) matrix
   are NaN.

3. **[MEDIUM, NOT a gate fail-open] NOTIFY-1 — `page_operator` best-effort contract broke on
   `httpx.InvalidURL`.** `InvalidURL` is NOT an `httpx.HTTPError` subclass, so a control-char-tainted
   token made YELLOW/ORANGE raise (instead of swallow) and RED escape as a non-`NotifierError`. The
   token text did NOT leak (only a char position). **Fix:** both `_httpx_sender` and
   `_httpx_get_updates` now `except Exception` and re-wrap to a token-free `NotifierError`. Regression
   test: the default sender re-wraps a CRLF-tainted-token `InvalidURL` token-free; YELLOW swallows,
   RED re-raises. (Bias gate is fully decoupled from `notify` — this could never make a strategy
   ALLOCATE; fixed for robustness/contract correctness.)

4. **[defense-in-depth, latent] FC-3 — vacuous `all([])` + SPA over S=1.** `combine_member_verdict(())`
   returned `allocated=True` (vacuous truth) and `spa_pvalue` accepted S=1. Neither was reachable via
   `evaluate_family` today (the composer always builds ≥3 components; `_align_family_matrix` returns
   None for S<2), but both are cheap latent fail-opens. **Fix:** `allocated = bool(components) and
   all(...)`; `spa_pvalue` requires `S>=2` (matches `pbo_fraction`). Regression-tested.

## DEFER (real but latent / belongs to a future increment)

- **[FC-2, medium] T1 consistency binds Sharpes + hashes but NOT `fraction_folds_positive` /
  `enough_samples`.** `build_evidence` accepts a forged `fraction_folds_positive=1.0` on the result;
  it does NOT allocate by itself (DSR/PSR/PBO/SPA run on the T1-bound recompute and hold, and T2 now
  unconditionally KILLs), but it widens the attack surface. **DEFER** to a T1-coverage pass: recompute
  `fraction_folds_positive` / `enough_samples` from the gate's own per-fold series and bind them in
  `_assert_consistent`. File: `src/trading/bias_gate/evidence.py`.

- **[FC-1-boundary, medium] The Inc-4 `SymbolPanel.survivorship_unverified` is a bare forgeable
  field.** The authoritative fix lives at the gate (T2 unconditional). Defense-in-depth at the Inc-4
  boundary (make the flag a DERIVED property off an attached PIT `UniverseSnapshot`/`SourceTier`, or a
  `__post_init__` that rejects `False` without a verified PIT artifact — mirroring Inc-2
  `universe.py`) would close the seam at the source too, but reopens a sealed increment. **DEFER** to
  the increment that wires the Polygon PIT universe (which is also when `_PIT_VERIFIER_WIRED` legally
  flips to True). Until then the gate-side fix is sufficient (forged flag cannot allocate).

- **[TT-1b, low] Near-constant (tiny-noise) column.** The `min == max` guard catches the exact-constant
  case (the reproduced fail). A column that is constant-plus-1e-12-noise has `min != max` so passes
  admissibility but yields a tiny `omega`. Per-member PSR/DSR already KILL such a member (the
  `_moments` constant guard / huge-Sharpe path), so it cannot allocate. **DEFER** a relative-tolerance
  `omega` studentization floor (`omega <= tol*(|d_bar|+scale)`) — it is a judgment call that risks
  rejecting legitimate low-vol strategies, so it is held until a real low-vol strategy exists.

- **[SEAL-1, low] `bias_gate/evidence.py` imports the underscore-private `_executed` from
  `trading.backtest.engine`.** A documentation-vs-code deviation (the docstring says "public Inc-4
  surfaces only"), NOT a fail-open — the gate adds no field to / does not mutate `BacktestResult` (all
  backtest source sha256-unchanged after a full `evaluate_family` run; the seal-boundary lens
  confirmed). **DEFER:** either promote `_executed` to a documented public helper in `engine.__all__`,
  or add a committed teeth test banning underscore-imports from `trading.backtest.*` in `bias_gate`.

## WON'T-FIX / NOT-A-BUG (the gate correctly KILLED — verified PASS)

- **T1 consistency guard:** HELD. ~25 tampered `BacktestResult` variants (wrong/sign-cancelling
  per-fold Sharpe, concat→NaN/inf, extra/missing fold, spec_hash, cost_model_id, 3× cost_scale,
  panel/strategy swap) ALL raised `EvidenceConsistencyError`. Both-NaN path cannot cloak a finite
  forgery.
- **Deflation / HWM:** HELD. Every cost/fold knob is a distinct ledger row (no collapse dimension);
  deleted/lowered/corrupt/negative HWM all RAISE; DSR strictly monotone-decreasing in N; the DSR path
  reads N ONLY through `hwm.checked_n_trials`, never `result.n_trials_at_eval`; DSR/PSR use the per-obs
  recompute, never the ×√252 annualized field. Mark-reset only via filesystem tampering = the
  documented Murphy residual (simultaneous `.db` + HWM deletion).
- **Family composer core:** HELD. S=1 → all KILLED; PBO/SPA NaN/None for S<2/misaligned/ruin/NaN; ANY
  failing component blocks allocation; HWM regression raises; cost-stress re-runs have teeth; no-edge
  random-walk family killed by all judges; all 4 real toys KILLED end-to-end.
- **Teeth-tails (9 of 10 panels):** HELD. Every degenerate input (ruin, all-NaN, T<60, std==0, N=0/1,
  V=0, single-lucky-fold) → NaN → KILL via positive-form thresholds; unit-confusion correctly uses
  per-obs Sharpe (annualized-1.5 / per-obs-0.094 does NOT pass PSR). Only TT-1 broke (now fixed).
- **Notifier secret-discipline:** HELD. No reachable path surfaces token text (`InvalidURL` carried
  only a char position; logs carry only `type(exc).__name__`); RED re-raise / YELLOW-ORANGE swallow /
  sanitize-before-build / fail-closed construction all held; grep finds no token-shaped literal in src/.
- **Seal boundary:** HELD. `backtest` package verdict-symbol-free (AST scan empty); `bias_gate` has NO
  broker/submit/network call site; `leak_lint` clean over `bias_gate`+`notify` yet still flags planted
  `shift(-1)`/sort/resample; sealed `BacktestResult` byte-identical and all backtest source
  sha256-unchanged after `evaluate_family`.

## HARD tripwires carried to the increment that wires the FIRST PAPER SUBMIT (next run task #1)

The paper submit was DEFERRED (operator-approved 2026-06-23). Before any order:
1. **Murphy guards G1–G10** wired AND each unit-tested with a yellow/orange/red graduated-response
   assertion (the notifier `page_operator(Severity)` is the transport; it is live + verified).
2. **§8 abandonment triggers** (total-loss>$30, equity<$20, 5 consec errors, recon-drift>2 for >10min,
   LLM-fail>30%/24h, mistake-cat ×3/7d, calib>30% ×2wk, `make abandon`) wired into the runner loop AND
   tested.
3. **Executor NO-OP → gate-gated submit**, structurally UNREACHABLE unless `gate.allocated is True`
   AND `evaluate_pre_submit` accepted AND `is_live() is False`. (The handoff invariant — no submit
   call site in `bias_gate` — is already enforced by a committed test.)
4. **Polygon PIT universe** wired so `_PIT_VERIFIER_WIRED` can legally flip to True (the ONLY
   legitimate way for T2 to pass) + the FC-1-boundary `SymbolPanel` hardening (defense-in-depth).
5. size strictly within `config/risk.yaml` caps; idempotent `client_order_id` (already deterministic);
   an explicit operator GO before the first order.
