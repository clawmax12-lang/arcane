# Increment 6 — First Paper Submit Red-Team Backlog

**Source:** adversarial red-team Workflow `wf_28153c97-0bc` (6 finder lenses — grant-forgery,
t2-survivorship-forgery, caps-sizing-bypass, idempotency-crash, guards-abandonment-killswitch,
phi1-loop-ordering-polygon → batched verifiers → synthesis). 2026-06-23.

**Method (honest).** 9 agents (6 finders + verify batches + synth) ran with runnable `uv run python`
repros against the SHIPPED public API; the lead then **independently re-reproduced** D1 (the forged
POLYGON_PIT artifact passing T2) before AND after remediation. No finding was taken on a lens's word.

## Verdict

**ADR §0 holds for the running system: zero allocations, zero orders is the correct and ACTUAL
outcome.** No externally-triggerable order can be produced — there are **zero production callers** of
`from_decision` / `submit_allocated` / `FamilyMember(...)` (`LoopInputs.candidates` defaults to `()`),
and there was no production producer of `ProvenanceBinding` at all. So **no finding was a live
exploit**; all are latent / defense-in-depth contract gaps that would arm the instant a future driver
wires the acting path. The lead nonetheless **closed the HIGH latent FC-1 re-opening now** (it is the
increment's headline guarantee), plus the MED/LOW hardenings — NEVER loosening a cap/threshold/gate.

## FIX-NOW (closed in `673dc9a`, TDD + gated; `make inc1..inc6` green, 95.26%)

1. **[HIGH, latent FC-1 cardinal sin] D1 — T2 trusted a caller-supplied artifact↔binding hash loop.**
   `t2_survivorship` verified only `membership_artifact_hash(artifact) == binding.hash`; both came via
   `FamilyMember.binding/.artifact` (untrusted gate-API inputs), so a hand-built `POLYGON_PIT` artifact
   (delisted name dropped) + a matching `ProvenanceBinding` passed T2 → allocate → grant
   (lead-reproduced). The design's "binding sourced STRUCTURALLY from the panel" producer never
   existed. **Fix:** `ProvenanceBinding` is now TOKEN-GATED (private `_BIND_MINT`; mirrors
   `AllocationGrant`) — constructible ONLY via `provenance_binding_from(snapshot, …)`, which takes the
   hash from a real `POLYGON_PIT` snapshot's **base-owned** `universe_hash` (never a caller string) and
   refuses a non-PIT snapshot. So a forged-hash binding is unrepresentable and T2's artifact must hash
   to a REAL value. PLUS a gate-side panel cross-check (`gate.py::_t2_component`): the binding's
   traded-set/window MUST equal the panel the engine ran (a driver cannot bind a survivor-subset).
   Regression: hand-built binding raises; non-PIT snapshot raises; forged-subset rejected; forged
   artifact fails on hash; the empty set fails closed.
2. **[MEDIUM] D2 — single-use GO consumed AFTER `broker.submit`.** A crash between the durable claim
   and the marker rotate (or a swallowed rename `OSError`) left the GO valid; a distinct candidate for
   the same `spec_hash` got a distinct coid (not deduped) and could submit a 2nd real paper order
   (reproduced). **Fix:** consume the marker BEFORE the irreversible broker call and FAIL CLOSED if it
   cannot be durably retired — a crash now at-worst LOSES the order, never doubles. Regression: the GO
   is gone by the time `broker.submit` runs; an un-consumable GO → no submit.
3. **[LOW] D5 — T2 passed vacuously on empty `traded_symbols`.** **Fix:** explicit fail-closed guard +
   the producer rejects an empty set.
4. **[MEDIUM, accepted trust boundary] D3 — `from_decision` is a STRUCTURAL re-check, not a
   recompute.** `GateComponent.passed` is as hand-buildable as the `allocated` bool, so a forged
   all-pass `GateDecision` would mint a grant. **Reachability: NONE** — `GateDecision` is built only
   inside `gate.py` and is NEVER deserialized. **Fix:** honest docstring + a committed pin test that
   `GateDecision` has no `from_json`/`load`/`model_validate` path (the boundary is safe ONLY while it
   is never deserialized). **D4 [LOW]:** documented `grant.universe_artifact_hash` as recorded
   provenance — the survivorship gate is T2 itself, upstream; the field is not re-checked downstream.

## DEFER (real but latent / belongs to the driver increment)

- **[D1-residual] The gate should DERIVE binding + artifact from a sealed snapshot/cache, not accept
  `FamilyMember.artifact`.** The token-gate makes the binding's HASH unforgeable and the panel
  cross-check pins the traded-set, so a forged artifact fails on hash today. The gold-plated version —
  the gate loading the artifact from the content-addressed `MembershipCache` by
  `snapshot.meta.universe_hash` and deriving the binding itself — removes the last caller-supplied
  object. **DEFER** to the increment that wires the first real `FamilyMember` (the driver), which is
  also where `FamilyMember` should carry the `UniverseSnapshot` instead of a `binding`.
- **[D3-deep] Recompute-from-evidence in `from_decision`.** If `GateDecision` ever becomes persistable
  (it is not), `from_decision` must recompute the ALL-of from the sealed OOS evidence (the Inc-4 public
  fns the gate already uses) rather than trust component bools. The pin test guards the precondition.
- **[universe completeness] "Panel == full PIT universe" (not just a subset of active names).** T2
  verifies the symbols you TRADED were PIT-active; it does not verify the strategy's universe SELECTION
  wasn't survivor-biased (a strategy may legitimately trade a subset). A future universe-construction
  check (panel built from the full PIT-active set) belongs with the allocator/regime increment.

## HELD invariants (PASSES — reproduced or read off live source)

Killed/un-allocated → submit UNREPRESENTABLE (grant `_MINT` gate); `allocated` bool not trusted
(`from_decision` re-derives); the **$1 cap yields NoTrade for any real share** (integer-share floor,
property-tested); at-most-once per coid (claim-then-submit + SQLite PK); **disaster ⇒ ZERO submits**
(`run_loop_pass` escalates before the candidate loop; auto-flat precedes submit; a pass exception fails
closed); non-gating guards page but never mutate the kill switch (§4.3); **PHI1** — no LLM/agent import
in executor+guards; Polygon failures fail closed and the gate makes NO network call; `PaperBroker` is
paper-only (worst-case blast radius is a paper order); ADR §0 — the system is not coaxed into trading.

## HARD tripwires carried to the FIRST REAL ORDER (the driver/allocator increment)

The executor is wired but DEFERRED from submitting; before any real paper order:
1. **D1-residual:** wire `FamilyMember` to carry a real `UniverseSnapshot` and have the GATE derive the
   binding + load the artifact from the cache (remove the last caller-supplied artifact).
2. **Operator GO:** an explicit per-order operator GO (`state/SUBMIT_GO`, single-use, phrase+spec
   bound) is required AND the first order is the SMALLEST possible, under observation.
3. **All four prereqs (Inc-6 hard stop) must hold:** Polygon PIT wired (done), every Murphy guard + §8
   trigger tested green (done), a live Telegram pager (done), AND the per-order GO. With the $1 cap and
   real share prices, sizing yields ZERO shares — the expected outcome under a GO is STILL NoTrade.

---

# Red-team ROUND 2 — independent re-audit (`wf_eb53b8c9-d48`, 2026-06-23)

**Why:** the operator asked for an independent re-check of the seal. A fresh 6-lens acting-surface
red-team ran on `a523ec0`. **Method (honest):** finders completed (25 findings) but the Verify +
Synthesize phases were 100% rate-limited (infra). Per `insight-autonomous-quality-discipline` a throttled
"0 confirmed" is NOT a pass, so the lead verified the CRITICAL single-threaded with an own repro. Lenses
that came back CLEAN match round 1: grant-forgery (token gate holds), submit-authorization (no SUBMIT_GO
⇒ RECORD_ONLY; D2 closed; caps inviolable), PHI1 (no LLM in the runtime submit closure today),
zero-order-invariant (structural, not incidental).

## FIX-NOW — DONE (remediated in `99e1819`, TDD + gated; `make inc1..inc6` green, 95.21%)
- **[CRITICAL, reachable] FC1-D1-REOPEN — the round-1 D1 fix was INCOMPLETE.** `ProvenanceBinding` was
  token-gated, but `provenance_binding_from` trusted any POLYGON_PIT `UniverseSnapshot`, and
  `UniverseMeta.universe_hash` is a **plain caller-settable field**. So a hand-built POLYGON_PIT snapshot
  carrying a forged hash minted a real binding and PASSED T2 with NO Polygon fetch — the FC-1 cardinal
  sin re-opened. Lead-verified end-to-end (forged universe → `passed=True`). LATENT (zero production
  callers; even past T2 the submit path is RECORD_ONLY + $1 cap), but the seal had OVERCLAIMED it
  "unrepresentable". **Fix:** the `@final as_of_members` base mints an unforgeable `PITMembershipProof`
  (PIT tiers only, module-private `_PIT_PROOF_MINT`); `provenance_binding_from` now requires it AND that
  it carries the snapshot's exact `universe_hash`. A hand-built snapshot has no proof ⇒ structurally
  unbindable; a genuine proof cannot be spliced onto a forged meta. Overclaimed docstrings corrected.
  Tests: `test_hand_built_pit_snapshot_is_unbindable_fc1_d1_reopen` + a proof-splice must-fail.

## DEFER to the driver/allocator increment (operator-approved; MED/latent — only bite once a driver acts)
- **GRD-1 [MED]** §5.2 escalation ladder is wired-but-never-armed: `open_page()` has no runtime caller,
  so the 15/30/60-min resend + terminal auto-liquidate never fire in the wired loop.
- **GRD-2 [MED]** operator paging fails OPEN silently: a re-raised RED `NotifierError` is swallowed by
  every consumer; nothing retries.
- **GRD-3 [MED]** §8 abandonment hard-stops but does NOT auto-flatten open positions (only RED guards /
  recon do); combined with GRD-1 a position could be left un-managed.
- **GRD-4 [MED]** a latched HARD_STOP is not durable across deletion of `state/kill_switch.json`
  (same class as the ledger-deletion residual — operator/Murphy territory).
- **PHI1-3 [MED, reach=false today]** the PHI1 AST tests scan only `executor/+guards/+risk/`, but the
  submit-path runtime closure also reaches `bias_gate/data/notify/backtest/factors`; widen the scan so a
  future banned import there is caught. (No LLM import exists today.)
These were red-team-reported and are consistent with the code read; the driver increment that wires the
acting loop (and arms paging/abandonment auto-flat) is their natural home — fix them there with the
driver, before any real order.

---

# Increment 7 PART A — carried tripwires CLOSED (2026-06-25)

The driver increment (Inc-7) closes ALL of the carried Inc-6 tripwires as PART A, BEFORE wiring the
first real driver — each TDD + gated (`make inc1..inc6` green) + committed. See
`docs/INCREMENT-7-DESIGN.md` (panel `wf_66ff5e4b-832`, CONDITIONAL + 7 skeptic must-fix folded in).

- **D1-residual — CLOSED (C1 `359a989`).** `FamilyMember` no longer carries a caller-supplied
  `binding`/`artifact`; it carries the proof-bearing `UniverseSnapshot` only. `evaluate_family`/
  `_t2_component` DERIVE the `ProvenanceBinding` (`provenance_binding_from`, which requires the
  base-minted `PITMembershipProof`) and LOAD the artifact from the content-addressed `MembershipCache`
  by `snapshot.meta.universe_hash`. A hand-built/proof-less POLYGON_PIT snapshot is UNBINDABLE → T2
  fails closed before any hash compare; a cache miss/tamper self-heals to None → fail closed. The gate
  makes NO network call (HELD invariant preserved — the driver fetches/seals, the gate only reads).
  Also closed **skeptic A2**: empty/degenerate panel guarded before `next(iter(panel.bars))` ⇒ a
  per-member KILL, never a `StopIteration` aborting the family.
- **PHI1-3 — CLOSED (C2 `60474af`).** The PHI1 AST scan is now RECURSIVE (`rglob`, closing **skeptic
  A1**: a nested `regime/llm/client.py` can no longer slip a non-recursive glob) and covers the full
  submit-path closure (executor/guards/bias_gate/data/notify/backtest/factors/risk + the new Inc-7
  packages regime/allocator/driver/scheduler). A planted-nested-import must-fail test proves the teeth;
  a roots-exist+non-empty test stops a moved package silently emptying the scan. Verified ZERO banned
  imports in the widened closure today.
- **GRD-4 — CLOSED for the single-file attack (C2 `60474af`).** A durable `state/HARD_STOP.tombstone`
  makes a latched HARD_STOP survive deletion of `state/kill_switch.json` alone (missing json + present
  tombstone ⇒ HARD_STOPPED). Crash-ordering pinned both directions: `arm()` writes the ARMED json FIRST
  then unlinks the tombstone, and a present validly-ARMED json WINS over a stale tombstone (`_load`
  consults the tombstone only when the json is missing). **DOCUMENTED RESIDUAL (operator/Murphy):** a
  whole-dir `rm -rf state/` wipe is indistinguishable from a first-ever boot — no in-band file can
  defend it (same class as the ledger-deletion residual). Operator-approved scope.
- **GRD-1 — CLOSED (C3 `c16ca2b`).** `run_loop_pass` ARMS the §5.2 ladder (`open_page`) on a RED
  disaster so the 15/30/60-min resend + 60-min terminal auto-liquidate fire. Idempotent first-write-wins
  (**skeptic A4**): opens ONLY if no episode is open, so a co-occurring second disaster cannot reset
  `opened_epoch` and starve the terminal clock; a persistent un-ACKed halt ticks every pass; a
  recovered + re-armed pass resolves the episode.
- **GRD-2 — CLOSED (C3 `c16ca2b`).** A RED page NOT confirmed delivered fails CLOSED: it still enters
  the armed ladder (the retry) AND leaves a durable `state/PAGE_PENDING` tombstone, cleared ONLY by an
  operator ACK/resolve (never by a later non-throwing dead-chat delivery). `engage_abandonment` now
  reports paging delivery; `LoopPassResult.page_undelivered` surfaces it.
- **GRD-3 — CLOSED (C3 `c16ca2b`).** §8 abandonment auto-flattens open positions: `engage_abandonment`
  gains an optional `broker_flat_fn` (out-of-loop callers) AND the loop folds `verdict.triggered` into
  `auto_flat_needed`. Ordering pinned: hard_stop latched FIRST, then the flat (a flat failure never
  un-halts), `close_all` idempotent.

The remaining Inc-6 DEFERs that belong to a LATER increment (universe-completeness "panel == full
PIT-active set"; D3-deep recompute-from-evidence if `GateDecision` ever becomes persistable) are carried
forward as HARD tripwires to the first REAL order (NOT this record-only increment).
