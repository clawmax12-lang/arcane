# Increment 7 — Regime + Allocator + Driver — Red-Team Backlog

**Source:** adversarial red-team Workflow `wf_066957e9-703` (6 finder lenses, each running its own
`uv run python` repros against the SHIPPED public API → adversarial verify → synth). 2026-06-25.

## Method (honest)

The Workflow was **heavily rate-limited** (server-side, not usage): **5 of 6 finder lenses died**
(`API Error: Server is temporarily limiting requests`) and the verify/synth phases had nothing to run.
Only the `regime-can-gate-or-size` lens completed (8 findings, ALL severity NONE). Per
`insight-autonomous-quality-discipline`, a throttled "0 confirmed" is **NOT a pass**, so the lead
**finished the red-team SINGLE-THREADED**, writing and RUNNING fresh adversarial repros for all five
throttled surfaces (empirical, against the public API). Every claim below was RUN.

## Verdict

**ADR §0 HOLDS. No reachable hole. ZERO orders is the actual outcome; no externally-triggerable order
exists.** With the 4 edgeless toys the gate KILLS all → the allocator allocates NOBODY → the driver
submits NOTHING — through the real `drive_once` and the real `run_scheduled_pass`. **No FIX-NOW.** One
defense-in-depth gap the red-team surfaced was closed proactively (PHI1 dynamic-import, below).

## Surface-by-surface (all SOUND — empirically re-verified by the lead)

1. **driver-grant-forgery — SOUND.** A hand-built / proof-less POLYGON_PIT `UniverseSnapshot` is
   UNBINDABLE (`provenance_binding_from` raises; `_t2_component` fails closed) — **FC-1 holds through
   the live driver**. A killed / `allocated=True`-but-a-component-failed / empty-components
   `GateDecision` all → `AllocationDenied` (no grant; the bool is never trusted). T2 coverage teeth
   bite: a panel that trades a symbol ABSENT from the PIT membership → T2 fails. The ONE accepted
   boundary (a hand-built ALL-pass `GateDecision` mints a grant) is the Inc-6 D3-class trust boundary —
   `GateDecision` is built ONLY in `gate.py`, NEVER deserialized, and `drive_once` computes decisions
   internally via `evaluate_family` (no external injection), so it is **unreachable via any production
   driver argument**.
2. **caps-sizing-bypass — SOUND.** A 40,000-case adversarial sweep of `size_order` (random
   price/equity/per-trade/concentration, incl. penny/huge/NaN/inf/neg/zero/stale prices) produced
   10,954 valid `Sized` orders and **ZERO cap violations** — every order obeys per-trade, concentration,
   equity-floor, integer-share, and `est_position_value == qty × fresh price`. `$1`-cap → `NoTrade` for
   every real share; 1-share-just-over-cap → REJECT (never round-and-submit); all degenerate tails →
   `NoTrade`. `RiskConfig` itself structurally REJECTS `per_trade > 5.0` and `per_trade > max_daily_loss`
   (the cap cannot even be constructed loose).
3. **go-submit-scheduler-bypass — SOUND.** No / wrong-phrase / wrong-spec GO → RECORD_ONLY (zero
   submit). A correct single-use GO authorizes EXACTLY ONE submit, then is consumed (rotated to
   `.consumed-<coid>`); the 2nd pass → RECORD_ONLY. The scheduler SKIPs with no marker / a malformed
   marker / outside RTH / when live; enabled+RTH → `RECORD_ONLY_PASS` but the toys die → zero submit.
   **No submit-path module writes an operator marker** (re-audited: the only marker op is `submit.py`'s
   `rename`-AWAY consume; no `os.open`/`os.replace`/`shutil`/`write_text`/`touch` targets a marker).
4. **regime-can-gate-or-size — SOUND** (the one surviving Workflow lens, lead-confirmed). The DERIVED
   regime reaches allocation ONLY as `RegimePosture.is_eligible` (a pure SUBTRACTIVE filter — drops a
   survivor, never ADDs one; UNKNOWN non-narrowing). No gate/sizing/cap signature accepts a
   regime/label/reliability parameter (runtime signature inspection + AST import-ban). `reliability` is
   an unforgeable read-only DERIVED property. A leaky/lying regime cannot manufacture a gate survivor
   (the verdict is computed with ZERO regime input). Regime affinity leaves the toy `spec_hash`es
   byte-stable.
5. **guards-abandonment-killswitch — SOUND.** The HARD_STOP tombstone survives deletion of
   `kill_switch.json` (fresh process → HARD_STOPPED). A loop exception fails CLOSED (zero submit,
   `scheduler_error` flagged). §8 abandonment through `drive_once` auto-flattens (GRD-3) + hard_stops +
   zero submit. The §5.2 ladder's first-write-wins idempotency holds (the terminal clock is never
   reset). A dropped RED page sets `page_undelivered` + a `PAGE_PENDING` tombstone on every path
   (guard / recon / abandonment).
6. **phi1-leak-family-tails — SOUND.** No dynamic-import / exec / shell surface exists in the closure
   (so the static AST scan has nothing to miss). The recursive PHI1 scan CATCHES a planted nested
   `langchain.agents` import. An oversized DISTINCT family (17) through the DRIVER → `DriverError` →
   zero candidates, zero submit, **`n_trials` UNCHANGED** (zero ledger writes — the A3 close holds via
   the production caller). The regime leak canary (full-sample edges) is caught by prefix-stability.
   Every degenerate tail through `drive_once` (empty strategies, empty panel, NaN bars, panel≠universe,
   cache-miss) fails CLOSED → zero candidates, zero submit, no crash that submits.

## HARDEN-NOW — DONE (defense-in-depth, closed this increment)

- **[PHI1 dynamic-import gap] CLOSED.** The PHI1 AST scan caught only STATIC LLM imports; a dynamic
  `importlib.import_module("anthropic")` / `__import__` / `exec` / `subprocess` / `os.system` would
  evade it. No such surface exists in the closure today, but a FUTURE one would slip. **Fix:** the PHI1
  test now also bans the dynamic-import/exec/shell surface across the whole submit-path closure, with a
  teeth test that a planted dynamic `importlib`/`__import__`/`exec` LLM load IS caught
  (`test_no_dynamic_import_or_exec_surface_in_submit_path`,
  `test_dynamic_import_scan_catches_a_planted_importlib_llm_load`). `make inc7` green, 95.37%.

## ACCEPTED boundaries / DEFER (documented, not silently dropped)

- **[D3-class trust boundary, ACCEPTED]** A hand-built ALL-pass `bias_gate` `GateDecision` mints a
  grant via `from_decision` (it re-runs the ALL-of over `components`, but `GateComponent.passed` is as
  hand-buildable as `allocated`). Reachability: NONE through a production caller — `GateDecision` is
  built ONLY inside `gate.py`, is NEVER deserialized (an Inc-6 pin test guards that), and `drive_once`
  computes decisions internally. Lying inside trusted in-process gate output is equivalent to importing
  the broker directly. If `GateDecision` ever becomes persistable, `from_decision` MUST become a
  recompute-from-sealed-evidence. (Carried verbatim from Inc-6 D3.)
- **[universe-completeness, DEFER → HARD tripwire to the first real order]** T2 verifies the symbols you
  TRADED were PIT-active across the window; it does NOT verify the strategy's universe SELECTION wasn't
  survivor-biased (a strategy may legitimately trade a subset of survivors). A panel that trades ONLY
  survivors passes T2. A "panel == full PIT-active set" construction check belongs with the FIRST REAL
  ORDER (it is moot under the record-only zero-order outcome). (Carried from Inc-6.)
- **[GRD-4 `rm -rf state/` residual, DEFER → operator/Murphy]** The HARD_STOP tombstone closes the
  single-file `kill_switch.json` deletion; a whole-dir wipe is indistinguishable from a first-ever boot
  (no in-band file can defend it). Operator-approved scope.

## HARD tripwires carried to the FIRST REAL ORDER (the driver is RECORD-ONLY; nothing has submitted)

1. Universe-completeness (panel == full PIT-active set) — the above DEFER.
2. The Inc-6 first-order prereqs STILL bind: an explicit per-order operator GO (`state/SUBMIT_GO`,
   single-use, phrase+spec-bound) AND the smallest-possible first order under observation AND a live
   Telegram pager AND every Murphy guard / §8 trigger armed+tested (all done). With the `$1` cap and
   real share prices, sizing yields ZERO shares — the expected outcome under a GO is STILL `NoTrade`.
3. Enabling the scheduler to run unattended is a SEPARATE operator decision (a `state/SCHEDULER_ENABLE`
   marker) AND remains RECORD_ONLY — it is NOT a submit authorization.
