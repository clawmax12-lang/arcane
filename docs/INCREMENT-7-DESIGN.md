# Increment 7 — Regime + Allocator + Driver (the FIRST real driver) — Design of Record

**Status:** DRAFT for operator checkpoint. **Branch base:** `99e1819` (Inc-6 SEALED + RE-AUDITED round 2). `make inc1..inc6` → PASS (95.21% cov, mypy --strict, leak-lint clean). **This is the first increment that wires `FamilyMember` → gate → allocator → the record-only executor loop.** It is buildable directly via TDD; every cluster below lists its must-pass/must-fail teeth.

**Reconciliation note.** Where Lens A/B/C and the SKEPTIC conflict, the SAFER choice wins and the rationale says why. The SKEPTIC's verdict is CONDITIONAL with 7 must-fix items; **all 7 are folded in as blocking** (they are correct against the live code — I verified each against ground truth, see §1).

---

## 1. GROUND-TRUTH RECONCILIATION (live code overrides any lens text)

These are facts read off the SHIPPED source at head `99e1819`. They override any lens claim that contradicts them.

| # | Lens claim / assumption | Ground truth (file:line) | Consequence for Inc-7 |
|---|---|---|---|
| GT-1 | Lens A: "widen `_ROOTS` … keep it green" treats the scan as recursive. | `tests/unit/test_phi1_no_llm_in_submit_path.py:39` uses `root.glob("*.py")` — **non-recursive**. | SKEPTIC A1 is REAL. The widening must ALSO switch to `rglob` or a nested `regime/llm/client.py` slips through one hop from the allocator. **Blocking.** |
| GT-2 | Lens C: "allocate → evaluate_family … subtractive filter" assumes the ledger is unaffected by family shape. | `gate.py:277-284`: `evaluate_family` records EVERY member × (`m.cost`, `*_stressed_costs`) to the `TrialLedger` BEFORE `hwm.checked_n_trials(...)` reads N; `NTrialsHighWaterMark` (`high_water_mark.py:46-62`) **never decreases**. | SKEPTIC A3 is REAL. An oversized/duplicated family **permanently inflates `n_trials`** (irreversible gate self-DoS, the M18 vector in reverse). **Family cardinality MUST be bounded and the regime filter MUST run BEFORE `evaluate_family`. Blocking.** |
| GT-3 | Lens A: `_t2_component` reshape. | `gate.py:180`: `index = next(iter(panel.bars.values())).index`. An empty `panel.bars` raises `StopIteration`. | SKEPTIC A2 is REAL. A degenerate panel aborts the WHOLE family eval (a crash tail), not a per-member KILL. **Guard before `next(iter(...))`. Blocking.** |
| GT-4 | Lens A/C: "gate derives binding + loads artifact." | The minter `provenance_binding_from` already requires the base-minted `PITMembershipProof` (`membership_artifact.py:143-151`); `MembershipCache.get` re-hashes on read and self-heals to None (`membership_cache.py:48-54`). | The D1-residual closure is sound AS DESIGNED. The remaining caller object is `FamilyMember.binding`/`.artifact` (`gate.py:102-103`) — **delete both**, carry `universe: UniverseSnapshot | None`. |
| GT-5 | Lens B/C: "regime is DERIVED, type-disjoint from the gate." | `Reliability.DERIVED` already exists read-only (`reliability.py:22`); `require_gateable` fails closed (`reliability.py:32`); `size_order` takes only HARD inputs (`sizing.py:65`); `RiskConfig` is frozen+`extra=forbid` (`schema.py:18`). | The DERIVED-can't-gate boundary is buildable by EXTEND, not rebuild: add NO `RegimeLabel` parameter to any gate/sizing/cap signature → passing one is a mypy `--strict` error. |
| GT-6 | Lens B: "fold `eligible_regimes` into the spec hash now." | `spec.py:18` docstring: "Regime-label references are deferred to Increment 6" — i.e. **now Inc-7**. `StrategySpec` has NO `eligible_regimes` field; `extra="forbid"` rejects a smuggled one. `canonical_params()` (`spec.py:120`) drives `spec_hash`. | Adding the field is in-scope and MUST fold into `canonical_params()` so an affinity edit forces a re-gate (ADR §7). Default = ALL regimes ⇒ the 4 toys' hashes are unchanged. |
| GT-7 | Lens A: GRD-4 "tombstone." | `kill_switch.py:130-137`: a missing json returns fresh `ARMED`; the in-memory latch (`:58`) does not survive restart. `arm()` (`:80-88`) writes ARMED then sets the latch. | The tombstone is sound but `arm()` must delete it; SKEPTIC GRD-4 crash-ordering ("ARMED first, then unlink; valid ARMED json wins over a stale tombstone") is the correct rule. **Blocking ordering.** |
| GT-8 | Lens C: scheduler "no authority to write SUBMIT_GO" is a convention. | `submit.py:60-74` only READS `state/SUBMIT_GO`; nothing structurally stops a new module from WRITING it. | SKEPTIC A5 is REAL. A committed AST/grep test must assert NO module in the submit-path closure writes `state/SUBMIT_GO` or `state/SCHEDULER_ENABLE`. **Blocking.** |
| GT-9 | ADR §5 regime constraint. | `ADR-001 §5` (`:75`): "Ship **regime as deterministic + Markov/HMM only**"; ADR §4 (`:66`): heavy ML behind a `RegimeModel` interface, deterministic+HMM fallback, **no re-architecture**. | Lens B's deterministic tercile-by-trend with a `RegimeModel` Protocol is exactly ADR-compliant. hmmlearn/torch are OUT this increment (operator CHECKPOINT 1). |
| GT-10 | Lens A: `gate.makes_no_network_call` (a HELD invariant, backlog line 76). | Confirmed: gate imports no httpx; only `polygon_universe.py` touches the network. | The driver (NOT the gate) does the Polygon fetch + cache seal; the gate only `cache.get(hash)`. Preserves the HELD invariant. |

**Net:** every SKEPTIC must-fix (A1–A5, GRD-4, Regime/4.3) is corroborated by the live code and is **adopted as blocking**. No lens recommendation that loosens a cap/threshold/gate survives.

---

## 2. ROADMAP CONFIRMATION

- **Inc-7 scope (LOCKED):** the **regime classifier** (Part B) + **allocator** (Part C) + **driver** (Part C) — *the first real driver* that wires strategies → backtest → bias gate → allocation → the (record-only) executor loop. **Part A** hardens the acting surface (the five carried Inc-6 tripwires) because they ARM the instant the driver wires the acting path — they must be closed *with* the driver, *before* any real order.
- **Deferred (NOT this increment):** the multi-agent roster (§1 of CLAUDE.md), the dashboard (Inc-8, the last layer), hmmlearn/torch regime, online learning, the universe-completeness check (panel == full PIT-active set — carried as a HARD tripwire to the first real order), live trading of any kind.
- **LOCKED expected outcome (ADR §0):** with the 4 edgeless toy strategies, the bias gate **KILLS ALL of them on the statistics wall (DSR/PSR/WF/PBO/SPA/enough_samples) even with T2 made CAPABLE** → the allocator allocates **NOBODY** → the driver submits **NOTHING**. **ZERO orders is CORRECT and is the build's acceptance criterion.** The regime/allocator must NEVER be a path to manufacture a trade; the null result must be **regime-invariant** (true under every regime label, including UNKNOWN warmup).

---

## 3. PART A — Acting-Surface Hardening (close the five carried tripwires)

Module-by-module change list. Every change EXTENDS a sealed, fail-closed primitive; none loosens a cap/threshold/gate.

### A.0 — D1-residual closure (the security headline)

**Decision.** Reshape `FamilyMember` (`gate.py:86-103`): **DELETE** both `binding: ProvenanceBinding | None` and `artifact: MembershipArtifact | None`; **ADD** `universe: UniverseSnapshot | None = None`. Inject a `MembershipCache` into the gate: `evaluate_family(..., *, membership_cache: MembershipCache | None = None)`, threaded to `judge_member` → `_t2_component`. The gate becomes the SOLE place the binding is minted and the artifact is fetched:

```
# inside _t2_component, when universe is not None and panel is not None and panel.bars:
binding = provenance_binding_from(
    universe,
    traded_symbols=tuple(sorted(panel.bars.keys())),
    window_start=index.min().to_pydatetime(),
    window_end=index.max().to_pydatetime(),
)                                   # raises ProvenanceBindingError on a non-PIT / proof-less snapshot
artifact = membership_cache.get(universe.meta.universe_hash) if membership_cache else None
# binding-mint failure OR artifact None ⇒ GateComponent(passed=False)  (fail closed)
return t2_survivorship(result, binding, artifact)
```

**Rationale.** This removes the LAST two caller-supplied objects on the trust path. A hand-built `UniverseSnapshot` has no `PITMembershipProof` ⇒ `provenance_binding_from` raises (`membership_artifact.py:143`) BEFORE any hash compare; the artifact can no longer be a caller's hand-built `POLYGON_PIT`-shaped object — it must already be sealed in the content-addressed cache under a hash the real base produced, and `cache.get` re-hashes on read (a tamper is a miss → fail closed). This is the proper closure the backlog DEFER (lines 54-60) named. It does NOT relax the statistical wall: even with T2 CAPABLE the 4 toys still all KILL.

**SKEPTIC A2 fold-in (blocking).** Before `next(iter(panel.bars.values()))`, guard `if not panel.bars or index.empty or window_start == window_end: return GateComponent("T2_survivorship", False, "degenerate/empty panel — fail closed")`. A degenerate member is a per-member KILL, never a `StopIteration` that aborts the family.

**Rejected alternative.** Keep `FamilyMember.binding/.artifact` and add a runtime assert that the binding came from the minter. UNSAFE — it still trusts the caller to PAIR the right cache-sealed artifact and merely RELOCATES the hole one layer up (the exact round-2 D1-REOPEN lesson: *trace the trust chain to its root*). ALSO REJECTED: have the gate re-FETCH from Polygon — that puts a network call + a fail-OPEN ambiguity on the gate path and breaks the HELD "gate makes NO network call" invariant (GT-10). The content-addressed cache + fail-closed-on-miss is strictly safer.

**Files:** `src/trading/bias_gate/gate.py`, `src/trading/bias_gate/__init__.py`, `tests/unit/test_d1_residual_gate_derives_binding.py`, `docs/INC6-HARDENING-BACKLOG.md` (mark D1-residual CLOSED).

### A.1 — GRD-1: arm the §5.2 ladder, idempotent open

**Decision.** In `run_loop_pass`, when a fresh RED disaster is detected this pass (guard RED `auto_flat`, recon RED `require_auto_flat`, or `verdict.triggered`) AND `deps.page_escalation is not None`: call `open_page(page_id, opened_epoch=inputs.now_epoch)` BEFORE the existing `tick(...)`, but ONLY if `not page_escalation.is_open()`. Add `PageEscalation.is_open() -> bool` (returns `self._load() is not None`).

**SKEPTIC A4 fold-in (blocking).** `page_id` = the disaster **EPISODE**, first-write-wins: open only if NO page state exists for ANY page_id (not keyed on a flappable cause string). Keep the first `opened_epoch` until `resolve()`; the cause detail goes in the page TEXT. Otherwise two co-occurring disasters that flip the cause across passes overwrite `opened_epoch` and reset the 60-min terminal clock (`page_escalation.py:62` overwrites unconditionally).

**Rationale.** `open_page` has zero runtime callers today (backlog GRD-1), so `tick`/`apply_escalation` never see an open page and the 15/30/60 ladder + terminal auto-liquidate never fire. The first-write-wins idempotency is load-bearing: `opened_epoch` must be written ONCE at episode onset so `elapsed >= _TERMINAL_60_S` (`page_escalation.py:83`) is reachable while the disaster persists. Authority is the DISK state (`_load()`), never an in-process bool — it must survive the very crash the ladder defends against. `resolve()` clears it on a clean (non-disaster) pass or operator ACK.

**Rejected alternative.** Open every pass and rely on `tick` to escalate. UNSAFE — resets `opened_epoch` each pass; the terminal liquidate becomes dead code (a silent §5.2 regression).

**Files:** `src/trading/executor/loop.py`, `src/trading/guards/page_escalation.py`, `tests/unit/test_grd1_loop_arms_escalation_ladder.py`.

### A.2 — GRD-2: paging fails CLOSED via the armed ladder + durable tombstone

**Decision.** Compose the dropped-page retry ONTO the GRD-1 ladder (the ladder IS the retry). In `run_loop_pass`, treat `guards.page_error is not None` OR (recon RED `require_auto_flat` AND `not recon.paged`) OR an un-pageable abandonment as "page not confirmed delivered." On that condition for a RED disaster: STILL `open_page(...)` (so even a never-delivered page enters the 15/30/60 ladder → terminal auto-liquidate at 60 min) AND write a durable `state/PAGE_PENDING` tombstone (atomic, `PageEscalation._atomic_write` discipline) stamping `{cause, opened_epoch, page_error}`. Surface `page_undelivered: bool` on `LoopPassResult`.

**SKEPTIC GRD-2 LOW fold-in.** `PAGE_PENDING` is cleared ONLY by an operator ACK (tie to `resolve()`/`acknowledge()`), **never** by `page_error is None` — a non-throwing dead-chat delivery must not clear it.

**Rationale.** `apply_guards`/`reconcile_once` must stay TOTAL (never raise) so a page failure never undoes the already-latched hard_stop (`panel.py:11-13`, `:94`). The correct composition is to make a swallowed page still ARM the ladder (which keeps resending and ultimately liquidates) and leave a forensic artifact a watchdog/morning-report can see. "Page dropped" and "page sent but un-ACKed" become indistinguishable in OUTCOME — both end in the 60-min terminal. That is the fail-closed property.

**Rejected alternative.** Make `_try_page`/`engage_abandonment` re-raise. UNSAFE — a transport failure could propagate out of the applier and risk aborting the durable hard_stop. ALSO REJECTED: an inline retry loop in the pass — it can wedge the bounded deterministic pass on a hung transport; the independent watchdog ladder is the right cadence (it runs even if the scheduler is wedged).

**Files:** `src/trading/executor/loop.py`, `src/trading/guards/page_escalation.py`, `tests/unit/test_grd2_dropped_page_fails_closed.py`.

### A.3 — GRD-3: §8 abandonment auto-flattens (belt-and-suspenders, idempotent)

**Decision.** Do BOTH: (1) give `engage_abandonment` an optional `broker_flat_fn: Callable[[], object] | None = None` (`abandonment.py:119`) and, AFTER the durable `hard_stop`, call it inside `contextlib.suppress(Exception)` (mirrors `reconcile_loop.py:73`); AND (2) in `run_loop_pass`, fold `verdict.triggered` into `auto_flat_needed` (`loop.py:131`) so the loop's own `broker.flat_all()` also fires on abandonment. `PaperBroker.flat_all`/`close_all` MUST be idempotent (closing already-flat positions is a no-op) so a double-flat is harmless.

**Rationale.** §8 abandonment hard-stops but does NOT auto-flatten today (only RED guards/recon do) — combined with an un-armed ladder a position could be left un-managed. Wiring the flat at BOTH levels is defense-in-depth: `engage_abandonment` is a reusable public primitive (a future CLI/agent may call it outside the loop), and the loop flattens regardless of how the engager was invoked. **Ordering:** hard_stop FIRST (durable latch), then flat — so a broker-unreachable flat failure leaves us halted-but-not-yet-flat (which the recon/guard RED path and the §5.2 terminal will also flatten), never un-halted.

**Rejected alternative.** Only fold `verdict.triggered` into the loop and leave `engage_abandonment` flat-less. WEAKER — the reusable engager would leave positions un-managed on any non-loop call path. ALSO REJECTED: flatten before hard_stop — unsafe ordering (a flat failure could leave us un-halted AND un-flat).

**Files:** `src/trading/guards/abandonment.py`, `src/trading/executor/loop.py`, `tests/unit/test_grd3_abandonment_auto_flat.py`.

### A.4 — GRD-4: kill-switch durability (close the single-file attack; scope the rm -rf honestly)

**Decision.** Add a durable `state/HARD_STOP.tombstone`, written (atomic, fsync, `os.replace` — the `KillSwitch._write` idiom) the FIRST time `hard_stop` escalates to HARD_STOPPED. In `KillSwitch._load()`, on `FileNotFoundError` (`:130-137`): tombstone present ⇒ return `(HARD_STOPPED, "hard-stop-tombstone-failsafe")` instead of fresh ARMED. `arm(operator_authority=True)` deletes the tombstone.

**SKEPTIC GRD-4 crash-ordering fold-in (blocking).** `arm()` writes ARMED FIRST, THEN unlinks the tombstone (two non-atomic ops). The resolution rule: **a present, validly-ARMED json WINS over a stale tombstone** (self-heal the stale tombstone); `json-missing + tombstone-present` ⇒ HARD_STOPPED. Pin both crash orderings with teeth. This avoids both failure directions (a stale tombstone silently overriding a real re-arm; or a crash clearing a latched hard-stop).

**Scope (honest).** CLOSE the realistic single-file `kill_switch.json` deletion/corruption (editor, partial cleanup script, targeted unlink). HONESTLY DEFER the `rm -rf state/` whole-dir wipe to operator/Murphy territory — a wiped state dir is indistinguishable from a first-ever boot, and no in-band file can defend it (same class as the HWM `state/` residual already scoped there, `high_water_mark.py:10-13`). Do NOT over-claim "durable across any deletion" (that would repeat the Inc-6 overclaim mistake).

**Rationale.** A latched HARD_STOP is not durable across `kill_switch.json` deletion today (the in-memory latch dies on restart). The tombstone makes the terminal state durable against the realistic single-file case while resolving an AMBIGUOUS missing-json-with-tombstone toward SAFETY (mirrors the existing corrupt⇒TRIPPED philosophy, `:139,145`).

**Rejected alternative.** Treat ANY missing json as HARD_STOPPED (no tombstone). UNSAFE in the other direction — a genuine first boot could never arm. The tombstone is exactly the bit that distinguishes "was hard-stopped" from "never ran."

**Files:** `src/trading/executor/kill_switch.py`, `tests/unit/test_grd4_hard_stop_tombstone_durability.py`, `docs/INC6-HARDENING-BACKLOG.md`.

### A.5 — PHI1-3: widen the AST scan to the full submit-path closure AND make it recursive

**Decision.** In `tests/unit/test_phi1_no_llm_in_submit_path.py`: (1) **switch `root.glob("*.py")` → `root.rglob("*.py")`** (SKEPTIC A1 — blocking); (2) widen `_ROOTS` to the full closure: `executor, guards, bias_gate, data, notify, backtest, factors, risk`, PLUS the new Inc-7 roots `regime, allocator, driver, scheduler`; (3) keep `_BANNED_TOP`/`_BANNED_SUBSTR`; (4) extend the non-empty-scan teeth test (`:49`) so each widened root exists and contributes ≥1 scanned file (a moved/renamed package cannot silently empty the scan). **Naming rule (structural):** any LLM-advisory regime code lives in a SLOW-LOOP package that is NOT a `_ROOT` and is consumed by the driver via a sanitized `regime.json` file — never imported into the acting path (§4.3: DERIVED advises, never gates).

**Verification (ground truth):** I read `data` (imports only pandas/httpx), `notify` (errors.py/telegram.py), `bias_gate`/`backtest`/`factors`/`risk` — **zero** banned imports or banned-substring module names exist today, so the widened+recursive scan stays GREEN. The non-empty-scan teeth test guarantees the roots are actually exercised.

**Rationale.** The submit-path runtime closure reaches `bias_gate/data/notify/backtest/factors` (backlog PHI1-3), and Inc-7 ADDS the very packages where an LLM regime classifier is tempting. A non-recursive glob would let `regime/llm/client.py` slip through one hop from the allocator (SKEPTIC A1). Widening + `rglob` makes PHI1 structural across the new code.

**Rejected alternative.** Scan the ENTIRE `src/trading` tree. OVER-BROAD — it would pull in slow-loop/agent packages that LEGITIMATELY import anthropic/openai (the §1 roster, by design), failing PHI1 on correctly-off-path code. ALSO REJECTED: drop `'agent'`/`'llm'` from `_BANNED_SUBSTR`. UNSAFE — keep the strict banlist and place LLM code OUTSIDE the scanned roots by package design.

**Files:** `tests/unit/test_phi1_no_llm_in_submit_path.py`, `docs/INC6-HARDENING-BACKLOG.md`.

---

## 4. PART B — The Regime Classifier (lean, deterministic, advisory DERIVED)

### B.1 — The model: deterministic tercile-by-trend, NOT hmmlearn

**Decision.** `src/trading/regime/labels.py` defines a frozen `RegimeLabel(StrEnum)`: a small product space of **volatility tercile (low/mid/high) × trend sign (up/down)** = 6 product labels + **`UNKNOWN`** (warmup). `src/trading/regime/model.py` computes the label series: vol-tercile edges from a STRICTLY trailing/expanding window; trend = sign of a trailing SMA cross; ALL inputs trailing and `shift(1)` so the label at a bar uses ONLY earlier bars (the `AlphaFactor` one-shift idiom). Window params (vol lookback ≈ 63 bars, SMA length, tercile window) are **frozen module constants — no YAML, no per-run tuning** (mirrors `AlphaFactor` `z_window`; §7 forbids tuning during a live day; not a parameter-drift vector). Expose a `RegimeModel` Protocol (`label_series(panel) -> Series[RegimeLabel]` + a stable `model_id`) so an HMM model registers as a drop-in later (ADR §4, no re-architecture).

**Rationale.** ADR §5 mandates "deterministic + Markov/HMM only"; operator CHECKPOINT 1 caps this at a lean advisory DERIVED label. Deterministic tercile-by-trend needs only numpy/pandas, has ZERO fit/seed surface, and reuses the proven causal idiom. The interface keeps HMM a documented later swap.

**Rejected alternative.** Fit a Gaussian HMM now. Trips CHECKPOINT 1, violates ADR §5, adds the hmmlearn cpython-lag risk (Trade env constraints), is seed/convergence non-deterministic (breaks the purity proof), and a naive full-sequence decode is acausal (a look-ahead leak). ALSO REJECTED: no `UNKNOWN` warmup state (fabricates a confident regime during warmup — the `AlphaFactor` GUARD B analogue).

### B.2 — The DERIVED-can't-gate structural boundary (type-disjoint + AST ban)

**Decision.** `RegimeLabel` lives in a frozen `RegimeAssessment` whose `reliability` is a read-only property returning `Reliability.DERIVED` (no settable field to forge — mirrors `AlphaFactor` reliability and `UniverseMeta.survivorship_unverified`), plus a `confidence: float` in `[0,1]`. Add NO `RegimeLabel`/`RegimeAssessment` parameter to `judge_member`/`evaluate_family` (`gate.py`), `size_order` (`sizing.py`), `AllocationGrant.from_decision` (`grant.py`), or `RiskConfig` (`schema.py`) — so passing one is a **mypy `--strict` error**. Add a committed AST import-ban: no module in `bias_gate`/`executor`(sizing/grant)/`risk` imports the `regime` package. Reuse `require_gateable` (`reliability.py:32`) as a runtime fail-closed backstop.

**Rationale.** This reuses the §4.3 primitives (the gateable set excludes DERIVED; `apply_guards` already proves DERIVED guards only page). A structural boundary where no parameter of the regime TYPE exists on any gate/sizing/cap signature is strictly stronger than a runtime check — the same class as `AllocationGrant` making a killed submit unrepresentable. The AST ban is the durability mechanism the project already trusts (PHI1, leak_lint).

**Rejected alternative.** Pass the regime into the gate/sizing and add a branch that skips a guard (e.g. "skip cost-stress in low vol"). UNSAFE — makes DERIVED a runtime decision input (a direct §4.3 violation), a fail-open the moment the condition inverts, and re-creates the FC-1 "forgeable flag flips a gate" bug.

### B.3 — Leak-freedom proof + determinism (reuse prefix_stability + leak_lint)

**Decision.** Make the regime compute satisfy the prefix-computation protocol and register it into `prefix_stability.check_registry` over a panel that includes the tercile-edge logic + degenerate frames (flat/zero-variance windows, all-NaN warmup), PLUS a **must-fail canary** using full-sample tercile edges or an SMA without a shift. Extend `leak_lint` to scan `regime/` as a new gate step. Add a determinism test (compute twice is bit-identical) and an AST assertion that the regime package imports NO wall-clock / RNG module.

**Rationale.** Reuses the machinery the 13 factors already pass (ADR §7: prefix-stability is a look-ahead leak by construction). Memory insights *optimizing a gate can weaken it* and *probe the tails* mandate the must-fail canary + degenerate-frame stress — a full-sample tercile quantile is value-plausible yet acausal (uses the FUTURE vol distribution to bucket the present), the exact slice-hidden-leak class the Inc-3/Inc-4 red-teams caught.

**Rejected alternative.** Trust the trailing-window discipline by code review + one happy-path test. Project history (Inc-3 slice-hidden leak, Inc-4 dropped shift) shows review-only misses these.

### B.4 — The "regime only subtracts" invariant + UNKNOWN warmup

**Decision.** The regime is consumed by the allocator (Part C) ONLY as a subtractive consideration filter (a survivor may be DROPPED, never added/up-weighted) or a veto-to-flat for the whole pass. **SKEPTIC LOW fold-in:** `UNKNOWN` warmup is **non-narrowing** (eligible-for-all), so a warmup pass's zero-grant outcome is attributable to the GATE's KILL, not to "regime not warmed up" — keeping the ADR §0 null-result signal clean. Record WHY a family was empty (gate-killed vs regime-vetoed) for the journal.

**Rationale.** ADR §0 / §9: zero trades is success, so the regime must never manufacture a trade and must not pollute the null signal. Subtractive-only is monotone toward more conservative; treating UNKNOWN as non-narrowing keeps the gate as the sole cause of a warmup zero.

---

## 5. PART C — Allocator + Driver + Scheduler + make inc7

### C.1 — Allocator (survivors-only, caps, regime advisory-only)

**Decision.** `src/trading/allocator/allocate.py`: a PURE projection `allocate(decisions, universe_artifact_hash, targets, quotes, posture) -> tuple[SubmitCandidate, ...]`. Mint each candidate via `AllocationGrant.from_decision` inside `try/except AllocationDenied` (a killed/forged decision → NO candidate). Require `target.spec_hash == grant.spec_hash`. Emit only if `posture.is_eligible(target)` (the subtractive regime filter). The allocator NEVER builds an `OrderIntent`, touches a cap, or calls the broker; zero survivors → empty tuple.

**SKEPTIC A3 fold-in (blocking).** Bound the family at a frozen `MAX_FAMILY_SIZE` (module constant, law). The driver REJECTS an oversize/duplicate family **fail-closed with ZERO ledger writes and ZERO grants** BEFORE `evaluate_family`. The regime subtractive filter runs BEFORE `evaluate_family` and a property test proves the set reaching the monotonic-HWM ledger only SHRINKS — so the regime can never inflate `n_trials` (GT-2).

**Rationale.** `from_decision` + the `_MINT` token (`grant.py:35,78`) is the single chokepoint making a non-survivor unrepresentable. No broker/cap access means no surface to exceed a cap or fund a killed strategy; the $1 cap forces `size_order` → `NoTrade` downstream (`sizing.py:96`). The subtractive filter is monotone and provably cannot inject a gate component, mint a grant, widen a budget, or loosen a cap. Strategy regime affinity is STRUCTURED metadata on the spec (GT-6) folded into `spec_hash` so an affinity change forces a re-gate (ADR §7).

**Rejected alternative.** An allocator that computes weights/sizes and emits `OrderIntent`s directly. Duplicates cap logic outside the pre-submit chain (drift) and takes sizing authority reserved for the deterministic executor. ALSO REJECTED: any additive/up-weight/re-include path — DERIVED creating/enlarging a position (the cardinal §4.3 sin, an ADR §0 trade-manufacturing path, and it lets a killed strategy re-enter).

**Files:** `src/trading/allocator/allocate.py`, `src/trading/regime/posture.py`, `src/trading/backtest/spec.py` (add `eligible_regimes`, default ALL, folded into `canonical_params()`).

### C.2 — Driver (the first real caller, record-only, toys → zero)

**Decision.** `src/trading/driver/run_once.py::drive_once(...)`: per strategy run `BacktestEngine.run`; the driver fetches/seals the PIT universe via `PolygonPITUniverse` + `MembershipCache` (the network call lives HERE, not the gate — GT-10); build `FamilyMember`s carrying the proof-bearing `UniverseSnapshot` (Part A.0); bound + dedupe the family (`MAX_FAMILY_SIZE`); apply the regime subtractive filter; `evaluate_family(..., membership_cache=...)`; `allocate(...)`; `run_loop_pass(...)`. Any error / cache-miss / `PolygonProvenanceError` / unbindable universe ABORTS the pass with zero candidates and zero submits — **never partial**. No LLM import (PHI1). RECORD_ONLY (the driver never writes `state/SUBMIT_GO`).

**Rationale.** The driver is the first production caller of `from_decision`/`run_loop_pass` and the home for the D1-residual: a base-minted-proof snapshot makes a forged universe unbindable and a cache miss fails T2 closed; the 4 toys → gate kills all → zero grants → zero submits (ADR §0) through real wiring.

**Rejected alternative.** A driver taking caller-built `ProvenanceBinding`/`MembershipArtifact` (the forgeable last input). ALSO REJECTED: a driver writing `SUBMIT_GO` (operator-reserved, single-use; bypasses the per-order human gate — SKEPTIC A5).

**Files:** `src/trading/driver/run_once.py`, `tests/unit/test_driver_*`.

### C.3 — Scheduler (OFF by default, explicit-enable, RECORD_ONLY, never unattended)

**Decision.** `src/trading/scheduler/loop.py`: a THIN deterministic loop (NOT APScheduler/cron). `tick(now_epoch) -> SchedulerAction.SKIP` UNLESS an operator-written `state/SCHEDULER_ENABLE` marker (phrase-bound) is present AND the injected clock is in RTH per `trading.data.calendar` AND `submit_mode` is still RECORD_ONLY. When enabled it calls `drive_once` RECORD_ONLY. It has NO authority to write `SUBMIT_GO`, NO path to live_mode, and ships DORMANT (no real cron registered). A one-pass unit test with a fake clock+broker asserts `submitted_count == 0`.

**Two independent operator gates (orthogonal, both OFF):** `SCHEDULER_ENABLE` (may-RUN) and `SUBMIT_GO` (may-SUBMIT). Arming the scheduler unattended trips CHECKPOINT 3 / a STOP — it must not move toward a real order before the per-order GO and before GRD-1/2/3 are closed (which this increment does).

**SKEPTIC A5 fold-in (blocking).** A committed AST/grep test asserts NO module under `executor/regime/allocator/driver/scheduler` writes `state/SUBMIT_GO` or `state/SCHEDULER_ENABLE`; only an operator CLI OUTSIDE the closure may.

**Rejected alternative.** Wire APScheduler with an RTH cron auto-run now. Unattended autonomy toward a real order before the per-order GO (CHECKPOINT 3 / STOP). ALSO REJECTED: a scheduler with its own submit toggle (collapses the two orthogonal gates).

**Files:** `src/trading/scheduler/loop.py`, `tests/unit/test_scheduler_*`.

### C.4 — make inc7

**Decision.** Add `inc7` mirroring `inc6` (ruff/black/mypy/pytest cov ≥85%) + extend `leak-lint` roots with `src/trading/regime`, `allocator`, `driver`, `scheduler` + run the widened/recursive PHI1 scan (A.5) + the new must-fail teeth as first-class pytest steps. Bump the `TrialLedger` `n_trials` only if Inc-7 adds evaluated combos (the toys are unchanged, so no bump from them).

**Rationale.** The regime classifier is the first place an LLM could be imported, so PHI1 must cover it; leak-lint over the new packages keeps them under the AST look-ahead ban; mirroring inc6 keeps the gate monotone (a strictly-stricter floor).

---

## 6. TDD CLUSTER PLAN (ordered, test-first)

Build order: **Part A closures → regime → allocator → driver/scheduler → gate `make inc7`.** Each cluster: write the must-fail/must-pass teeth FIRST (RED), implement minimally (GREEN), refactor, then `make inc1..inc7` green → commit → push → ff-main → update STATE.

| C | Cluster | Must-FAIL teeth (RED first) | Must-PASS teeth |
|---|---------|------------------------------|-----------------|
| **C1** | A.0 D1-residual reshape + A.2 degenerate-panel guard | `test_hand_built_pit_snapshot_unbindable_through_the_gate` (forged POLYGON_PIT + forged hash + `pit_proof=None` ⇒ T2 `passed=False`, member KILLED, no grant); `test_cache_miss_or_corrupt_artifact_fails_T2_closed` (genuine snapshot, empty/tampered/None cache ⇒ `passed=False`); `test_empty_or_degenerate_panel_kills_member_not_crashes` (empty `panel.bars` ⇒ per-member KILL, NO StopIteration) | `test_toys_all_killed_even_with_T2_capable` (real proof-bearing PIT + sealed cache ⇒ T2 CAPABLE, yet all 4 toys KILL on DSR/PSR/WF/PBO/SPA, `from_decision` raises `AllocationDenied` each ⇒ zero grants) |
| **C2** | A.5 PHI1 widen+rglob; A.4 GRD-4 | `test_phi1_widened_scan_catches_a_planted_llm_import_in_a_new_root` (a synthetic `regime/llm/_probe.py` with `from langchain.agents import Foo` makes the scan FAIL — proves rglob has teeth in a NESTED dir); `test_phi1_scan_is_recursive_and_catches_nested_llm_import` | `test_phi1_widened_scan_green_and_non_empty` (every root exists, ≥1 file each, zero offenders); `test_hard_stop_survives_kill_switch_json_deletion`; `test_rearm_wins_over_stale_tombstone` |
| **C3** | A.1 GRD-1; A.2 GRD-2; A.3 GRD-3 ladder/flat | `test_dropped_red_page_still_enters_ladder_and_leaves_tombstone`; `test_page_pending_cleared_only_by_operator_ack` | `test_loop_arms_ladder_once_and_terminal_liquidate_fires` (persistent disaster at t=0/+16m/+61m ⇒ `open_page` called ONCE, terminal flat+hard_stop at +61m); `test_ladder_clock_monotonic_across_cause_change` (second co-occurring disaster does NOT reset the clock); `test_abandonment_auto_flattens_positions` (hard_stop FIRST then flat; flat failure does not undo HARD_STOPPED; double-flat is a no-op) |
| **C4** | B.1/B.3 regime model + leak-freedom | `test_regime_prefix_stable_catches_full_sample_tercile_leak` (leaky full-sample-edge / no-shift variant FLAGGED by `check_registry`) | `test_regime_is_pure_deterministic_function_of_past_bars` (compute twice bit-identical; no wall-clock/RNG import; label unchanged when later bars appended); `test_regime_emits_unknown_during_warmup_never_confident` |
| **C5** | B.2/B.4 DERIVED-can't-gate boundary | `test_regime_label_is_not_an_accepted_gate_or_sizing_or_cap_input` (mypy `--strict` subprocess: passing a `RegimeAssessment` into `size_order`/`judge_member`/`evaluate_family`/`RiskConfig` FAILS type-check; AST: no gate/sizing/grant/risk module imports `regime`); `test_regime_high_confidence_cannot_add_killed_strategy_or_raise_size` | `test_regime_assessment_reliability_is_derived_and_unforgeable` (read-only DERIVED, no ctor field, `require_gateable` raises); `test_unknown_regime_does_not_narrow_and_zero_is_gate_attributed` |
| **C6** | C.1 allocator + A3 family bound + spec affinity | `test_killed_decision_yields_no_candidate`; `test_regime_cannot_manufacture_a_grant`; `test_family_size_bounded_and_ledger_not_inflated_by_regime` (oversize/dup family ⇒ zero ledger writes, zero grants; regime filter only shrinks the recorded set) | `test_allocator_regime_filter_subset_only_and_null_result_invariant` (hypothesis: output ⊆ input, len no greater; every regime label ⇒ zero grants with the toys); `test_allocation_never_exceeds_caps_dollar_one` (`size_order` at $1 ⇒ `NoTrade`); `test_spec_eligible_regimes_change_changes_spec_hash` |
| **C7** | C.2 driver + C.3 scheduler | `test_driver_forged_universe_is_unbindable`; `test_no_submit_path_module_writes_operator_markers` (A5: no closure module writes `SUBMIT_GO`/`SCHEDULER_ENABLE`); `test_phi1_no_llm_in_full_submit_closure` | `test_driver_four_toys_zero_submits_end_to_end` (drive_once over 4 toys, faked fetch + cache ⇒ `submitted_count == 0`); `test_driver_failclosed_on_cache_miss_or_polygon_error` (abort, zero candidates, never partial); `test_scheduler_off_by_default_skips`; `test_scheduler_enabled_pass_is_record_only_zero_submit` (broker.submit never called) |
| **C8** | `make inc7` seal + leak-lint roots + STATE/backlog | — | `make inc1..inc7` green ≥85% cov; leak-lint scans regime/allocator/driver/scheduler; backlog marks D1-residual/GRD-1..4/PHI1-3 CLOSED; end-to-end `drive_once` null result confirmed |

---

## 7. SKEPTIC ATTACK → STRUCTURAL MITIGATION → TEETH TEST

| Sev | Attack | Structural mitigation (safer choice; why it wins) | Teeth |
|-----|--------|--------------------------------------------------|-------|
| HIGH | PHI1 `glob('*.py')` is non-recursive; `regime/llm/client.py` slips through (GT-1). | **`rglob`** + widened roots + the LLM advisor lives OUTSIDE the submit-path roots, consumed via a sanitized `regime.json`. Beats "add roots only" because a nested module is the realistic LLM home. | `test_phi1_scan_is_recursive_and_catches_nested_llm_import` |
| HIGH | An oversized/duplicated family permanently inflates `n_trials` via the monotonic HWM (GT-2) — irreversible gate self-DoS. | Frozen `MAX_FAMILY_SIZE`; oversize/dup family REJECTED fail-closed with ZERO ledger writes + ZERO grants; regime filter runs BEFORE `evaluate_family` and only shrinks the recorded set. Beats "trust the caller" because the HWM never decreases. | `test_family_size_bounded_and_ledger_not_inflated_by_regime` |
| MED | Empty `panel.bars` ⇒ `next(iter(...))` `StopIteration` aborts the whole family (GT-3). | Guard empty/degenerate panel before `next(iter(...))` ⇒ per-member KILL. Beats a crash tail that masks sibling KILLs. | `test_empty_or_degenerate_panel_kills_member_not_crashes` |
| MED | Two co-occurring disasters flip the cause across passes ⇒ `open_page` overwrites `opened_epoch` ⇒ resets the 60-min clock (GT-7). | First-write-wins per disaster EPISODE: open only if NO page state exists; keep the first `opened_epoch` until `resolve()`; cause detail in page text. Beats per-cause keying. | `test_ladder_clock_monotonic_across_cause_change` |
| MED | A new driver/scheduler module WRITES `state/SUBMIT_GO` or `SCHEDULER_ENABLE` ⇒ flips RECORD_ONLY to a real submit (GT-8). | Committed AST/grep test: no module in `executor/regime/allocator/driver/scheduler` writes those markers; only an operator CLI may. | `test_no_submit_path_module_writes_operator_markers` |
| MED | GRD-4 `arm()` ARMED-write + tombstone-unlink is non-atomic; a crash between leaves a stale tombstone overriding a re-arm, or clears a latched hard-stop. | ARMED FIRST then unlink; a present validly-ARMED json WINS over a stale tombstone (self-heal); `json-missing + tombstone` ⇒ HARD_STOPPED. Pin both orderings. | `test_rearm_wins_over_stale_tombstone` |
| LOW | `PAGE_PENDING` cleared on `page_error is None` ⇒ a non-throwing dead-chat delivery clears it with nobody paged. | Clear `PAGE_PENDING` ONLY by operator ACK (tie to `resolve()`/`acknowledge()`); the ladder is the real fail-closed path. | `test_page_pending_cleared_only_by_operator_ack` |
| LOW | `UNKNOWN` warmup as "eligible for nothing" empties the family ⇒ conflates gate-KILL (ADR §0) with regime-not-warmed. | Treat `UNKNOWN` as non-narrowing so the gate's KILL is the sole reason for zero; record why a family was empty. | `test_unknown_regime_does_not_narrow_and_zero_is_gate_attributed` |
| HIGH (carried) | T2 verifies traded symbols were PIT-active, not that the universe SELECTION was survivor-unbiased. | DEFER as a HARD tripwire to the first real order (a panel-from-full-PIT-active-set check); operator-reserved scope. Documented, not silently dropped. | (carried) |

---

## 8. OPEN QUESTIONS FOR THE OPERATOR (genuinely operator-reserved; defaults recommended)

1. **Regime label granularity.** Ship the 6-label vol×trend space + `UNKNOWN`, or a leaner vol-state-only (3 labels) + `UNKNOWN` to shrink the overfit surface (ADR §5)? **Recommend: 6-label** — still tiny, and the subtractive-only filter neutralizes overfit risk.
2. **Window params config-tunability.** Pin the vol lookback (~63), SMA length, tercile window as FROZEN module constants (no YAML), mirroring `AlphaFactor z_window` (so the regime cannot be tuned during a live day, §7)? **Recommend: YES, frozen constants** — confirm you do not want them config-tunable.
3. **`eligible_regimes` placement.** Add the optional STRUCTURED field on `StrategySpec` NOW (default = ALL regimes, folded into `spec_hash`), but wire the allocator's USE of it behind the same per-order operator GO as the first submit? **Recommend: YES** — puts the spec-hash re-gate discipline in place now (GT-6) while keeping the acting use gated.
4. **GRD-4 scope.** Confirm: CLOSE the single-file `kill_switch.json` deletion (tombstone) and DEFER the `rm -rf state/` whole-dir wipe to operator/Murphy territory — or do you want stronger out-of-state-dir durability (a tombstone under a separate, harder-to-wipe path)? **Recommend: single-file CLOSE + honest DEFER.**
5. **Scheduler dormancy (CHECKPOINT 3).** Confirm: ship the scheduler DORMANT (OFF behind `state/SCHEDULER_ENABLE`, RECORD_ONLY even when enabled, NO real cron) this increment? **Recommend: YES, dormant.**
6. **`PaperBroker` idempotent flat.** Does `PaperBroker` already expose an idempotent `flat_all`/`close_all` (no-op when already flat) for GRD-3's double-flat safety, or should the loop dedupe before calling? **Recommend: make/confirm `flat_all` idempotent** (the redundancy is then free).
7. **Universe-completeness check.** Build the "panel == full PIT-active set" check now, or DEFER it as a HARD tripwire before the first real order (T2 verifies traded symbols were PIT-active, not that the SELECTION was survivor-unbiased)? **Recommend: DEFER as a HARD tripwire** — it belongs with the first real order, not the record-only driver.

---

**Bottom line.** Inc-7 EXTENDS the sealed Inc-6 acting path with ZERO new authority: Part A closes all five carried tripwires (recursive+widened PHI1, armed/fail-closed paging ladder, §8 auto-flatten, durable hard-stop, and the D1-residual that makes a forged universe structurally unrepresentable end-to-end); Part B adds a deterministic, leak-proof, type-disjoint DERIVED regime that can only SUBTRACT; Part C wires the first real driver (record-only, family-bounded, $1-capped) and a dormant scheduler behind two orthogonal operator gates. With the 4 edgeless toys the gate kills all → the allocator allocates nobody → the driver submits nothing — the null result is regime-invariant, which is the build's acceptance criterion (ADR §0). No cap, threshold, or gate is loosened anywhere.

**Files referenced (absolute):** `/Users/maxagent/Trade/src/trading/bias_gate/gate.py`, `/Users/maxagent/Trade/src/trading/bias_gate/tests_t2.py`, `/Users/maxagent/Trade/src/trading/data/universe.py`, `/Users/maxagent/Trade/src/trading/data/membership_artifact.py`, `/Users/maxagent/Trade/src/trading/data/membership_cache.py`, `/Users/maxagent/Trade/src/trading/data/polygon_universe.py`, `/Users/maxagent/Trade/src/trading/executor/loop.py`, `/Users/maxagent/Trade/src/trading/executor/grant.py`, `/Users/maxagent/Trade/src/trading/executor/sizing.py`, `/Users/maxagent/Trade/src/trading/executor/submit.py`, `/Users/maxagent/Trade/src/trading/executor/kill_switch.py`, `/Users/maxagent/Trade/src/trading/executor/reconcile_loop.py`, `/Users/maxagent/Trade/src/trading/guards/panel.py`, `/Users/maxagent/Trade/src/trading/guards/abandonment.py`, `/Users/maxagent/Trade/src/trading/guards/page_escalation.py`, `/Users/maxagent/Trade/src/trading/guards/checks.py`, `/Users/maxagent/Trade/src/trading/bias_gate/high_water_mark.py`, `/Users/maxagent/Trade/src/trading/backtest/spec.py`, `/Users/maxagent/Trade/src/trading/data/reliability.py`, `/Users/maxagent/Trade/src/trading/risk/schema.py`, `/Users/maxagent/Trade/src/trading/risk/constants.py`, `/Users/maxagent/Trade/tests/unit/test_phi1_no_llm_in_submit_path.py`, `/Users/maxagent/Trade/docs/INC6-HARDENING-BACKLOG.md`, `/Users/maxagent/Trade/docs/STATE.md`, `/Users/maxagent/Trade/docs/adr/ADR-001-foundation.md`, `/Users/maxagent/Trade/Makefile`. New: `/Users/maxagent/Trade/src/trading/regime/{labels,model,posture}.py`, `/Users/maxagent/Trade/src/trading/allocator/allocate.py`, `/Users/maxagent/Trade/src/trading/driver/run_once.py`, `/Users/maxagent/Trade/src/trading/scheduler/loop.py`, `/Users/maxagent/Trade/docs/INCREMENT-7-DESIGN.md`.