# ARCANE — Current State & Resume Pointer

> **If you (a future/compacted session) remember nothing else, read this file, then
> `docs/adr/ADR-001-foundation.md`, then run `make inc1`.** This is the canonical,
> version-controlled state so the process is never lost to a context compaction.

**As of:** 2026-06-27 · **Branch:** `build/increment-8-agents-console` — pushed; `main` ff'd.
**Head/main:** `8db37b4` (Inc-8.5 SEALED + RED-TEAMED) · **`make inc1..inc8` → ALL EIGHT PASS** (95.42%
cov, `mypy --strict`, leak-lint clean; full boundary suite green).
**✅ INCREMENT 8.5 SEALED + RED-TEAMED — THE CONVERSATIONAL CONSOLE.** The two-way Telegram trader now
TALKS like a real warm assistant (the operator was disappointed it gave stiff, hardcoded, report-only
answers and often didn't reply). A TONE+REACH fix INSIDE the sealed Inc-8 topology — **safety is
topology, not tone; the LLM still can never reach the broker.** Design panel `wf_906b4845-a0e`;
operator checkpoint (`AskUserQuestion`): conversation model = **Sonnet** (`claude-sonnet-4-6`). Built in
5 TDD clusters + 1 red-team hardening, each gated + committed + pushed + ff-main:
- **C1 `e1f149a`** — PART A: rewrote `console/responder.py` SYSTEM_PROMPT from report-only/short into a
  warm, natural Swedish trader-assistant (kept grounding + never-invent-a-number + refuse-trade +
  injection-resistance; dropped the "ENBART rapporterande/KORT/BARA utifrån briefing" straitjacket).
- **C2 `fc2550c`** — PART B: `settings.load_model_settings` → conversation=Sonnet, agents stay Haiku;
  `CONSOLE_MODEL_ID`/`AGENT_MODEL_ID` configurable; Opus one env-flip away. Thin httpx client unchanged.
- **C3 `a08f456`** — PART D: widened `state_reader` briefing (om_arcane static context, gate verdict +
  why, HONEST equity non-answer (no fake number), agent health, n_trials HWM, PRESENCE-ONLY posture
  markers whose contents never reach the prompt) — all sanitized, read-only, fail-closed; +/halsa,/trials.
- **C4 `90ba40f`** — PART C: NEW `console/run.py` + `make console` — the always-on listener
  (`run_forever`: capped exponential backoff, fail-closed, token-free; cold-start backlog discard via the
  durable offset; requires an explicit operator `TELEGRAM_CHAT_ID`, never auto-resolved).
- **C5 `3540575`** — RUNTIME no-leak proof (subprocess: importing the submit path leaks ZERO
  console/slowloop/anthropic into sys.modules, with teeth) + a Sonnet conversation live smoke.
- **C6 `8db37b4`** — red-team verdict + closed a LATENT (unreachable) authz None==None fail-open
  (`extract_authorized` now `str | None`, fails closed on an unconfigured operator / missing chat.id).

**RED-TEAM ✅ (`wf_7187a5bb-d22`, 5 lenses, all SINGLE-THREADED with runnable repros, none throttled).**
Verdict: **ADR §0 / PHI1 HOLD — the warmer + always-on console STILL holds the boundary; ZERO confirmed
reachable issues; no FIX-NOW.** phi1-boundary · jailbreak-act (a `/flatta`-emitting reply → zero
kill_switch calls, inert text) · always-on-listener (chat_id-only auth, backlog discard, capped backoff,
no scheduler/SUBMIT_GO writes) · secret-leak (key in header only, type-only error re-wrap, token-free
logs) · grounding-honesty (trade-intent refused pre-LLM, subtractive sanitize, stale→otillgänglig,
equity honest). Triage + DEFERs: `docs/INC8.5-HARDENING-BACKLOG.md`. Design: `docs/INCREMENT-8.5-DESIGN.md`.

**LIVE PROOF (delivered to the operator's phone):** three natural questions ("hur går det?", "vad tror
du om dagen?", "förklara vad gaten gör") answered via the REAL Sonnet pipeline in 7–14 s — warm,
grounded, honest, and it REFUSED to invent market data (said regime/news unavailable rather than
fabricating, §9). The always-on listener (`make console`) booted (`model_id=claude-sonnet-4-6`),
discarded the cold-start backlog (no stale replay), and is polling — the operator's own typed messages
are now answered within seconds. **Executor untouched; ZERO orders.** For a DURABLE always-on, the
operator runs `make console` in a terminal/tmux/nohup he leaves open (the one I started lives with this
session).

**NEXT (a future run, NOT started): the live dashboard (the LAST layer) OR more of the §1.1 agent
roster.** Increment 8.5 is sealed; do not reopen without cause.

## ✅ Increment 8 — slow-loop agents + two-way Telegram console (SEALED + RED-TEAMED)
> Superseded as the resume pointer by Inc-8.5 above; the Inc-8 detail is retained here for history.
> (Prior head `a155d7a`; the Inc-8 seal commit `f5987dd`.)

Design panel `wf_7e98b8c9-e4e` → `docs/INCREMENT-8-DESIGN.md`; operator checkpoint (`AskUserQuestion`)
confirmed all 3 recommended (report-only advisory; news+regime-synth+daily-report; full Swedish
console). Built in 6 TDD clusters, each gated + committed + pushed + ff-main:
- **C1 `a5ecd6f`** — `slowloop/contract.py` (`AgentArtifact`, frozen pydantic v2; §4.3 in the TYPE —
  `reliability` is `Literal["textual","derived"]`, so an agent cannot mint a gateable artifact;
  discriminated payload union; the regime-advisory label ⊆ the existing `RegimeLabel`) + `store.py`
  (atomic temp→fsync→os.replace; `read_artifact` fails CLOSED to `None`) + `make inc8` (mirrors inc7;
  leak-lint scope FROZEN — slowloop/console are outside the submit path).
- **C2 `3e47f96`** — `slowloop/llm/anthropic_client.py` (thin httpx `Responder`, injectable `post`,
  token-free error re-wrap, no new heavy dep) + `orchestrator.py` (run agent → validate → DISCARD on
  exception/uncertain/below-floor, keep last-known-good byte-identical, ORANGE page at N=3).
- **C3 `e79cdd5`** — `console/{authz,commands,poller}.py`: auth to the operator chat_id + update-shape
  whitelist (forwarded/edited/channel/group/non-text dropped); deterministic command allow-list keyed
  on a literal leading slash (escalate-only kill_switch, NO arm); refuse-trade-order; durable-offset
  long-poll with cold-start backlog discard; the LLM reply is never re-dispatched.
- **C4 `e85fbcd`** — `console/{state_reader,responder,app}.py`: a sanitized, staleness-guarded (18h)
  briefing (kill-switch + RECORD-ONLY invariant + news + the REPORT-ONLY advisory regime); a Swedish
  report-only Q&A responder grounded ONLY in the briefing (never invents numbers, §9); the full wiring
  (`ConsoleKillSwitch` protocol has NO arm; getUpdates fetcher; token in a non-logged URL).
- **C5 `65b9e53`** — `slowloop/agents/{news,regime_synth,daily_report}.py`: each sanitizes external
  text BEFORE the LLM, parses the reply fail-closed, emits a §4.3-tagged artifact. regime_synth is
  REPORT-ONLY + label ⊆ RegimeLabel (an out-of-space label FAILS CLOSED).
- **C6 `a155d7a`** — `tests/unit/test_inc8_boundary.py`: the PHI1 boundary proof by EXPLICIT
  package-identity import-graph walk (not the substring scan) — no acting module imports slowloop/
  console (static + dynamic), with planted-import teeth; no broker from the LLM packages; console
  imports only `executor.kill_switch`; the acting path never names the advisory artifact. **BUILD
  COMPLETE, all eight gates green.**

**RED-TEAM ✅ (`wf_5f80b480-871`, throttled → lead finished single-threaded).** 7 surfaces RUN against
the shipped API: RT-1 phi1-runtime-leak (93 modules, zero leak) · RT-2 broker/re-arm (none) · RT-3
advisory-poison + §4.3 (acting path reads nothing; forged `hard` rejected) · RT-4 schema-fail-open
(corrupt→None; discard+keep-good+ORANGE@3) · RT-5 secret-leak (transports token-free) · RT-6
console-injection+auth (foreign/forwarded dropped; injection→sanitized Q&A, no arm; jailbroken reply
not re-dispatched) · RT-7 tails (cold-start discards stale control; no wedge; staleness guard). Two
workflow finders independently confirmed RT-1 + RT-6. **Verdict: ADR §0 + PHI1 HOLD, no reachable hole,
ZERO orders.** No FIX-NOW. DEFERs (live Tavily/Apify data adapters; advisory Model B disarmed; dormant
orchestrator/poller) in `docs/INC8-HARDENING-BACKLOG.md`.

**The slow loop is DORMANT** (no scheduler/poller wired to run unattended); the executor stays
RECORD-ONLY behind the per-order GO. The LLM lives entirely OUTSIDE the deterministic submit path.

## ✅ Increment 7 — regime + allocator + driver (SEALED + RED-TEAMED)

**PART A — acting-surface hardening: ✅ COMPLETE (C1–C3).** All five carried Inc-6 tripwires + the 7
skeptic must-fix closed, each TDD + gated + committed + pushed + ff-main:
- **C1 `359a989`** — D1-residual: `FamilyMember` carries the proof-bearing `UniverseSnapshot` only; the
  GATE derives the `ProvenanceBinding` (`provenance_binding_from`, requires the base-minted
  `PITMembershipProof`) + LOADS the artifact from the content-addressed `MembershipCache` by
  `meta.universe_hash`. A forged/hand-built universe is UNREPRESENTABLE end-to-end (unbindable → T2
  fails closed); cache miss → fail closed; **A2** degenerate-panel guard (per-member KILL, no
  `StopIteration`). Re-confirmed: even with T2 CAPABLE the 4 toys STILL all KILL → zero grants.
- **C2 `60474af`** — **PHI1-3/A1**: AST scan now RECURSIVE (`rglob`) + widened to the full submit-path
  closure (executor/guards/bias_gate/data/notify/backtest/factors/risk + new regime/allocator/driver/
  scheduler), nested-import must-fail teeth; created the 4 package skeletons. **GRD-4**: durable
  `state/HARD_STOP.tombstone` closes the single-file `kill_switch.json` deletion (missing json + present
  tombstone → HARD_STOPPED); `arm()` writes ARMED-json-first-then-unlinks, a valid ARMED json wins over
  a stale tombstone; `rm -rf state/` is the documented operator/Murphy residual.
- **C3 `c16ca2b`** — **GRD-1** (loop arms the §5.2 ladder, idempotent first-write-wins so the 60-min
  terminal clock never resets — skeptic A4), **GRD-2** (a dropped RED page fails CLOSED: still enters
  the armed ladder + leaves a durable `PAGE_PENDING` tombstone cleared only by operator ACK;
  `engage_abandonment` reports paging delivery; `LoopPassResult.page_undelivered`), **GRD-3** (§8
  abandonment auto-flattens — `engage_abandonment` gains `broker_flat_fn` + the loop folds
  `verdict.triggered` into `auto_flat_needed`; hard_stop FIRST then flat).

**PART B — the regime classifier: ✅ COMPLETE (C4–C5).**
- **C4 `8aac0af`** — `src/trading/regime/{labels,model}.py`: a lean DETERMINISTIC 6-label vol×trend
  (causal expanding-quantile edges × trailing SMA, `shift(1)`-published) + UNKNOWN warmup + the
  `RegimeModel` Protocol (HMM drop-in later, ADR §4/§5). Leak-free PROVEN via `prefix_stability` over
  normal + degenerate frames with a must-FAIL full-sample-edge canary; pure-deterministic; no
  random/time import.
- **C5 `44134aa`** — `regime/posture.py` + the DERIVED-can't-gate boundary: `RegimeAssessment.reliability`
  read-only = DERIVED; proven type-disjoint THREE ways (mypy `--strict` subprocess rejects a regime as a
  gate/sizing input; AST ban — no bias_gate/executor/risk module imports `regime`; `require_gateable`
  raises). The posture is SUBTRACTIVE-only (no add/size/grant surface); UNKNOWN is non-narrowing.

**PART C — allocator + driver + scheduler: ✅ COMPLETE (C6–C8).**
- **C6 `3869ff8`** — `allocator/allocate.py` (survivors-only via `from_decision`; subtractive regime
  filter; confused-deputy; output ⊆ input; null-result regime-invariant) + `MAX_FAMILY_SIZE=16`
  (skeptic A3: oversized/dup family → zero ledger writes, zero grants) + `StrategySpec.eligible_regimes`
  (STRUCTURED, folded into `spec_hash` only when declared → toy hashes unchanged).
- **C7 `10a668d`** — `driver/run_once.py` (`drive_once`: PIT-universe→backtest→gate→allocator→
  `run_loop_pass`, RECORD-ONLY, fail-closed, safety still runs on assembly error) + `scheduler/loop.py`
  (OFF by default, `SCHEDULER_ENABLE`-gated, RECORD_ONLY, dormant; A5: no submit-path module writes an
  operator marker) + a live driver smoke (real Polygon → toys still all KILLED → zero).
- **C8** — `make inc7` (mirrors inc6 + leak-lint over the 4 new packages). **`make inc1..inc7` ALL PASS.**

**PART D — adversarial RED-TEAM: ✅ DONE (`wf_066957e9-703`).** 6 finder lenses; 5 throttled by a
server-side rate limit → the lead finished SINGLE-THREADED with own `uv run python` repros (per
`insight-autonomous-quality-discipline`: a throttled "0 confirmed" is NOT a pass). **Verdict: ADR §0
HOLDS — no reachable hole; ZERO orders is the actual outcome through the real `drive_once` /
`run_scheduled_pass`.** All 6 surfaces SOUND (FC-1 holds through the driver; 40k-case caps sweep zero
violations; GO single-use; tombstone durable; §8 auto-flats; family bound holds via the driver with zero
ledger writes; regime type-disjoint+subtractive). **One defense-in-depth HARDEN-NOW closed:** the PHI1
AST scan now also bans the dynamic-import/exec/shell surface (`importlib`/`__import__`/`exec`/
`subprocess`/`os.system`) so a future dynamic LLM load cannot slip the static scan. Accepted boundaries
(D3-class `GateDecision`, unreachable via driver) + carried HARD tripwires (universe-completeness; the
per-order GO; the `rm -rf state/` GRD-4 residual) in `docs/INC7-HARDENING-BACKLOG.md`.

**NEXT (a FUTURE run — NOT started): the slow-loop AGENTS increment.** The agent-fed regime synthesis
(news/macro/sentiment, §1 of CLAUDE.md) was DEFERRED here. Any LLM-advisory regime lives in a SLOW-LOOP
package OUTSIDE the submit-path AST roots, consumed via a sanitized `regime.json` — never imported into
the acting path. The acting surface is RECORD-ONLY; no order has been submitted. Increment 7 is sealed;
do not reopen without cause.

---

## ✅ Increment 6 — FIRST paper submit (SEALED + RE-AUDITED round 2)

Sealed at `99e1819`/`3769e38` (`make inc1..inc6` PASS). The FIRST paper-submit machinery (Polygon PIT +
unforgeable hash-bound T2 + Murphy guards G1–G10 + §8 abandonment + §5.2 paging + gate-gated RECORD-ONLY
submit), design-panel-driven, red-team-hardened across TWO independent rounds. **The 4 toys: ALL KILLED
even with T2 CAPABLE** (ADR §0). **ZERO paper orders** — Inc-7 is the first real driver (still record-only).

## ✅ Increment 6 — FIRST paper submit (Polygon PIT + Murphy guards + gate-gated record-only submit) — SEALED

Design panel `wf_3ad27bf2-439` (4 lenses + skeptic + synth) → `docs/INCREMENT-6-DESIGN.md`. Built in 3
parts, 14 TDD clusters, each gated + committed + pushed + ff-main:
- **PART A (C1–C4, `545c5aa`)** — Polygon PIT universe + UNFORGEABLE T2. Checkpoint GREEN (verified live:
  `/v3/reference/tickers?ticker=&date=` reconstructs membership as a true interval — SIVB/SBNY active
  ONLY within their real trading life). Base-seam `MembershipProvenance` hook (inert data; base still
  owns the verdict). `data/membership_artifact.py` (content-addressed) + `membership_cache.py` +
  `polygon_universe.py` (allowlist, abort-never-partial, token never logged). **DELETED the forgeable
  global `_PIT_VERIFIER_WIRED` bool**; `tests_t2.py` now binds a POLYGON_PIT artifact BY HASH + window
  coverage + no-missing (self-attested flags AND-ed advisory only). Survivorship TEETH: dropping SIVB
  before its delist, or a mid-window delist, FAILS T2.
- **PART B (C5–C8, `3072b11`)** — Murphy guards G1–G10 + §8 abandonment + §5.2 paging. New
  `src/trading/guards/` package, all pure deterministic over injected HARD/STRUCTURED state. `apply_guards`
  = the SINGLE kill-switch mutator (RED hard_stop latched BEFORE the page); only GATING guards mutate
  the switch — G5/G9/G10 (DERIVED/TEXTUAL) ONLY page (§4.3 teeth). §8 reuses the sealed caps (property
  test: abandonment AGREES with the pre-submit cap). §5.2 ladder: RED protective action at t=0, the
  15/30/60 ladder is notification-only on an independent watchdog; TERMINAL does flat+hard_stop+page;
  survives restart. `make inc6` = inc5 surface + leak-lint over guards + executor + adversarial teeth.
- **PART C (C9–C14, `39f381e`)** — the gate-gated RECORD-ONLY submit. `AllocationGrant` mintable ONLY by
  re-running the ALL-of (closes the type-confusion CRITICAL; killed → no grant → submit UNREPRESENTABLE).
  `sizing.py` integer-share within caps (the $1 cap → NoTrade for any real share; property-tested).
  `submit_allocated` = the ONLY broker.submit caller, requires a grant, RECORD_ONLY unless a single-use
  phrase+spec-bound `state/SUBMIT_GO`; CLAIM-THEN-SUBMIT. Real alpaca PAPER submit behind an injected
  client (paper hardcoded, token never logged). `run_loop_pass`: recon→guards→§8→page BEFORE any submit
  (a disaster pass auto-flats + submits ZERO even with a grant present); fail-closed on a pass exception.
  PHI1 AST teeth (no LLM/agent import in executor+guards). **C14 end-to-end null (ADR §0): with T2 made
  CAPABLE of passing, the 4 toys are STILL all KILLED by the statistical wall → ZERO grants → ZERO
  orders.** LIVE smokes (excluded from gate) green vs real Polygon + Alpaca paper (read-only, NO submit).

**RED-TEAM COMPLETE + REMEDIATED** (`673dc9a`). Workflow `wf_28153c97-0bc` (6 finder lenses + verifiers
+ synth; lead independently re-reproduced D1 before AND after the fix). **Verdict: ADR §0 holds — zero
allocations/zero orders is the ACTUAL outcome; zero production callers of the acting path, so no
externally-triggerable order exists.** Closed (TDD, gated): **D1 [HIGH, latent FC-1]** — T2 trusted a
caller-supplied artifact↔binding hash loop; `ProvenanceBinding` is now TOKEN-GATED (only
`provenance_binding_from` from a real POLYGON_PIT snapshot mints it) + a gate-side panel cross-check;
**D2 [MED]** — single-use GO now consumed BEFORE `broker.submit` + fail-closed; **D5/D3/D4** — empty-set
guard, `GateDecision` no-deserialization pin test, honest docstrings. Full triage + DEFERs + first-order
tripwires: `docs/INC6-HARDENING-BACKLOG.md`.

**RED-TEAM ROUND 2 — independent re-audit + REMEDIATED** (`99e1819`). A fresh acting-surface Workflow
(`wf_eb53b8c9-d48`, 6 lenses) re-audited the seal. Finders ran (25 findings) but Verify/Synth were 100%
rate-limited → I verified the CRITICAL single-threaded with my own repro. **FC1-D1-REOPEN [CRITICAL,
reachable] — the round-1 D1 fix was INCOMPLETE.** `ProvenanceBinding` was token-gated, but
`UniverseMeta.universe_hash` is a plain caller-settable field, so a hand-built POLYGON_PIT
`UniverseSnapshot` carrying a forged hash minted a real binding and PASSED T2 with NO Polygon fetch —
the FC-1 cardinal sin re-opened (latent: zero production callers). **Fixed**: the `@final as_of_members`
base now mints an unforgeable `PITMembershipProof`; `provenance_binding_from` REQUIRES it + an exact
hash match, so a hand-built snapshot is structurally unbindable (the overclaimed "not author-declarable"
docstrings were corrected). Verified end-to-end: the exact forge now raises `ProvenanceBindingError`.
DEFERRED to the driver increment (operator-approved, MED/latent — they only bite once a driver acts):
GRD-1 §5.2 ladder never armed, GRD-2 paging fails-open silently, GRD-3 §8 doesn't auto-flatten, GRD-4
kill-switch not durable across `state/` deletion, PHI1-3 AST scan covers only executor/+guards/+risk/
(not the full submit-path closure). See `docs/INC6-HARDENING-BACKLOG.md` → "Red-team ROUND 2".

**The executor is wired but the FIRST real order is DEFERRED to an explicit per-order operator GO**
(the Inc-6 hard stop). Nothing has touched a broker beyond read-only connectivity. Operator open
questions resolved to the recommended defaults (`docs/INCREMENT-6-DESIGN.md` §7); operator may override
before any real GO.

---

## ✅ Increment 5 — ALL-of bias/kill gate + Telegram notifier (SEALED)

**Head:** `1150d30` (Inc-5 red-team remediation) · `make inc1..inc5` PASS. **✅ INC 2/3/4 SEALED.**
**✅ INCREMENT 5 SEALED** — the ALL-of bias/kill gate (DSR/PSR/PBO/SPA + WF-OOS, accept-or-KILL) + the 4
carried tripwires + a Telegram notifier (live-verified), design-panel-driven, red-team-hardened (1
critical + 1 high + 2 latent fail-opens found AND closed; `wf_fa2cf190-080`, not throttled). **The
gate's verdict on the 4 toys: ALL KILLED** (ADR §0 success). T2 fail-closed lifted in Inc-6 PART A.

## ✅ Increment 5 — ALL-of bias/kill gate + Telegram notifier (SEALED)

Design panel `wf_e2d07d5c-8e3` (4 lenses + skeptic + synth) → `docs/INCREMENT-5-DESIGN.md`; **operator
checkpoint signed all conservative**: threshold table verbatim (DSR>0.95, PSR>0.95, PBO<0.5, SPA p<0.05,
WF OOS-Sharpe>0 & ≥60% folds, cost-stress 2×/3×, enough_samples≥60); DSR = strict single-statistic;
family min 2 (a lone candidate is structurally un-allocatable); BUILD gate+notifier, DEFER the submit.
No ADR change, no Inc-4 reopen, no new dep (pure-numpy erf/Acklam; scipy absent). New pkgs
`src/trading/bias_gate/` + `src/trading/notify/`. 10 TDD clusters, all green + committed:
- C1 `a54e501` — errors + pure-numpy normals (erf CDF + Acklam PPF, fail-closed) + frozen thresholds.
- C2 `f1f695e` — tripwire A1: `eval_trial_params` folds cost numerics + WF geometry into the trial
  identity (M18 under-count fix); reflective-completeness tests.
- C3 `1b28ea7` — tripwire A2: `NTrialsHighWaterMark` (atomic kill-switch idiom; RAISES on a count
  regression — DB-deletion-proof).
- C4 `8613b1d` — tripwire A3 (`required_purge_bars` = `strategy_warmup + label_horizon`, re-derived) +
  A4 (`t2_survivorship` passes only on dual-False) + `verdict.py` GateComponent/GateDecision.
- C5 `383c7e6` — evidence assembler: recompute OOS net series via Inc-4 PUBLIC primitives + the STRICT
  T1 consistency guard (per-fold 1e-9 AND concat AND hashes; both-NaN agree, NaN-vs-finite KILLs).
- C6 `bab8b04` — PSR + DSR + cross-trial V (per-obs SR, population skew/kurt; deflation via
  expected-max-of-N; fail-closed NaN on every degenerate tail).
- C7 `3e7a949` — PBO (CSCV) + conservative SPA (Hansen stationary bootstrap, least-favorable
  recentering = harder-to-pass = safe for a KILL-gate).
- C8 `7728d96` — WF criterion + the ALL-of composer `evaluate_family` (records every eval's identity
  BEFORE reading N via HWM; PBO/SPA shared family components; ALL-of accept-or-KILL). **The 4 toys are
  KILLED end-to-end** (T2 + stats). Decomposed must-PASS proves the gate CAN allocate.
- C9 `145bf6f` — Telegram notifier (sanitize-before-send, RED page RE-RAISES, token never logged, grep
  test). **LIVE ping to operator's phone verified 2xx.**
- C10 `6f0f591` — `make inc5` + seal-boundary teeth (backtest stays verdict-free; bias_gate uses the
  vocabulary) + handoff invariant (NO submit call site in bias_gate) + leak-lint over the new packages.

**THE GATE'S VERDICT ON THE 4 TOYS: all KILLED** (ADR §0 success — no edge survives on a
survivorship-unverified universe; T2 alone forces it, the statistics gate is the independent 2nd wall).

**RED-TEAM COMPLETE + REMEDIATED** (`1150d30`). Workflow `wf_fa2cf190-080` (6 finder lenses + 3
verifiers + synth, **NOT throttled**; lead independently re-reproduced every fix-now AND every close).
5 of 6 lenses found no reachable fail-open. **4 fix-now closed** (TDD + gated): **FC-1 [CRITICAL]** —
T2 survivorship was flippable to PASS via the forgeable `SymbolPanel(survivorship_unverified=False)`
kwarg → full ALLOCATE (the cardinal sin); fixed by making T2 fail CLOSED unconditionally while no PIT
verifier is wired (`_PIT_VERIFIER_WIRED=False`). **TT-1 [HIGH]** — a constant-nonzero column slipped
the exact `omega==0` guard → SPA/PBO PASS; fixed by rejecting any constant column in
`_matrix_is_admissible`. **NOTIFY-1 [MED]** — `httpx.InvalidURL` (not an HTTPError) escaped the catch;
fixed by re-wrapping ANY exception token-free. **FC-3** — vacuous `all([])` + SPA S=1; hardened. Full
triage + DEFERs + carried submit-tripwires: `docs/INC5-HARDENING-BACKLOG.md`.

---


## ✅ Increment 4 — strategies + walk-forward backtest (SEALED)

Design panel `wf_6158e014-a7e` (4 lenses + synthesis) → `docs/INCREMENT-4-DESIGN.md`; **checkpoint all 4
operator criteria FALSE → autonomous** (conservative/standard cost; standard de-Prado purged+embargoed
12/3/3 anchored; 4 strategies; no ADR change / Inc-5 NOT pulled). New sibling pkg `src/trading/backtest/`.
TDD build, 9 clusters green + committed, then red-team + remediate + seal:
1. C1 `06d3ed1` — `errors.py` (`BacktestError`(ArcaneError) sibling) + `make inc4` gate.
2. C2 `984c3fc` — frozen `StrategySpec`/`FactorLeg`; `spec_hash` = SHA-256 over canonical JSON with
   lossless `float.hex()`; structurally no threshold field (`extra=forbid`).
3. C3 `ff1b4f4` — `resolve_spec` + `FactorRegistry.get` fail-closed (`UnknownFactorError`); phantom
   `factor_id` can't reach `run`.
4. C4 `bff19b6`/`0eeae7f` — conservative `CostModel` (~6 bps floor, `cost_scale≥1`, turnover-driven,
   no zero/neg fill; the M3 defense).
5. C5 `bc94f28` — `walk_forward.py` purged+embargoed 12/3/3 anchored splitter (prefix-stable, disjoint OOS).
6. C6 `a928562` — compute-only `statistics.py` + `BacktestResult` (NO verdict field) + AST verdict name-ban.
7. C7 `f44e035` — `ledger_integration.py` (REUSE `TrialLedger`, kind=strategy, `n_trials` 13→17) + the 4
   default strategies + `PositionMode`.
8. C8 `dbcd1af` — `@final BacktestEngine.run()`: ONE execution `shift(1)` + factor `shift(1)`, pnl
   `position.shift(1)*close.pct_change()-cost` (all trailing); GUARD A/B, warmup+value adequacy, as_of
   PIT re-check, net≤gross; `PositionView`/`RealizedView` causality adapters + perfect-foresight off-by-one
   MUST-FAIL canary.
9. C9 `dc2a08e`/`d49411e` — 4-strategy end-to-end integration + leak_lint backtest-root teeth; engine 100%.

**RED-TEAM COMPLETE + REMEDIATED** (`8915ec3`). Workflow `wf_60bf76b3-d42` (6 finder lenses / 2 waves of 3,
all alive, empirical repros; **not throttled** this run). **Verdict: no reachable look-ahead leak and no
reachable Inc-5 boundary violation** — the off-by-one is load-bearing (mutation-confirmed), join causal,
`BacktestResult` verdict-free, cost conservative+monotone, `n_trials` identity field-complete. **4 fix-now
remediated** (lead-verified by own repros, TDD+gated): RT03 `pct_change(fill_method=None)`; M3-COST-01
`total_bps` non-finite fails closed; skeptic-1 explicit train-free `oos_*` stats (headline documented
full-sample); F1 corrected design §7 (prefix-stability does NOT catch a dropped exec shift — the
value-test + canary do). Full triage + DEFER (Inc-5 tripwires) / WON'T-FIX: `docs/INC4-HARDENING-BACKLOG.md`.

**RED-TEAM ROUND 2 — independent re-audit + REMEDIATED** (`b5739e5`). On operator request, a fresh 6-lens
Workflow `wf_618edde8-565` re-audited the seal. Finders ran (25 findings) but **Verify/Synth were 100%
rate-limited** (infra) — so material findings were verified single-threaded with own repros (NOT treated
as a clean pass; `insight-autonomous-quality-discipline`). **3 reachable fix-now remediated** (TDD+gated):
NUM-2 `annualized_sharpe` scored a WIPED fold (`net ≤ -1.0`, reachable on a short into a >100% bar) as a
strong POSITIVE; NUM-1/3 `max_drawdown` reported a false `0.0` on ruin; WF-1 `step_months < test_months`
double-counted overlapped OOS sessions. Fix: ruin-aware stats (Sharpe/CAGR→NaN, total/max_dd→`-1.0`,
never a win) + `WalkForwardConfig` rejects `step < test`. Nil practical impact on the shipped large-cap
config, but these are the exact stats Inc-5's gate consumes (ADR §0). Lead's own deterministic probes
(ledger=17, cost floor/monotone, verdict-free, causal-join teeth, end-to-end honest noise-Sharpes)
re-confirmed clean. See `docs/INC4-HARDENING-BACKLOG.md` → "Red-team ROUND 2".

**NEXT (a FUTURE run — NOT started): Increment 5 — the ALL-of bias/kill gate + FIRST paper submit.** The
Inc-4 DEFERs Inc-5 must clear FIRST: (1) fold cost/fold-geometry into the trial identity before the DSR
consumer reads `n_trials` (M18); (2) build the monotonic ledger high-water-mark before the first
`n_trials` DSR read; (3) a FITTED consumer must set `purge ≥ max_total_window + label_horizon`; (4) T2
must read `survivorship_biased` (never a clean pass). Discord paging webhook is also a prerequisite for
the first paper submit. Increment 4 is sealed; do not reopen without cause.

## ✅ Increment 3 — alpha factors (SEALED)

Design panel `wf_03e33f11-392` → `docs/INCREMENT-3-DESIGN.md` (WITHIN ADR §5 lean scope, no ADR
change). TDD build, all 5 clusters green + committed; then red-team + remediate + seal:
1. STEP 1 (`f69c905`) — FINAL `AlphaFactor` base (compute() @final, STEP 0–10 + GUARD A–E:
   inf-on-_raw rejected before z, std==0⇒NaN explicit, the one mandatory shift(1)); `factors/errors.py`
   roots at `risk.errors.ArcaneError`; reliability=DERIVED read-only (§4.3).
2. STEP 2 (`5fa9d55`) — SQLite `TrialLedger` (INSERT OR IGNORE PK, structurally monotonic,
   fail-closed on corrupt/missing — the M18 defense; mirrors `executor/idempotency.py`).
3. STEP 3 (`bbb317a`) — the lean **13** standard factors (momentum: mom_21d/mom_63d/mom_126_skip21;
   meanrev: reversal_5d; volatility: vol_21d/atr_14; volume: dollar_vol_21d/rel_volume_21d/
   amihud_illiq_21d; range: hl_range_21d/close_loc_in_range/dist_from_sma_50/sma_ratio_20_50), each
   one NaN-guarded `_raw` (`.where(denom>0)`, `log_safe`); correlated families KEPT (no
   orthogonalization — bias gate prunes). **Trial ledger n_trials = 13.**
4. STEP 4 (`2ec7f9a`) — `FactorRegistry` + `default_registry`; `validate_all` runs prefix-stability
   on BOTH `_raw` AND `compute()` (a power-of-2 future-scale leak is bit-exactly masked on compute()
   yet caught on _raw — proven) + frame-adequacy; forge-proof register (dup/non-DERIVED rejected);
   seeds the ledger with 13 idempotently.
5. STEP 5 (`51faaac`) — `leak_lint` + SHIFT_NEG/CENTERED_ROLLING/RESAMPLE/SORT/interpolate, scan
   widened to factors/; `make inc3` gate created.

**RED-TEAM COMPLETE + REMEDIATED** (`9914b86`). Workflow `wf_5b8d385e-493` (6 finder lenses/2 waves,
all alive, 13 findings); the VERIFY+SYNTH phases were throttled by a transient server-side rate limit
(NOT quota), so the fix-driving findings were verified **single-threaded** in the main loop with
empirical repros (per insight-autonomous-quality-discipline). **Verdict: no confirmed live leak** —
the 13 factors are prefix-stable on _raw AND compute. **8 fix-now hardenings remediated** (TDD,
gated): validate_all now checks the FULL frame (not a depth-slice — closed a length-dependent leak
hole) + absolute-min floor + value-adequacy; GUARD A rejects off-contract dtypes; ledger None-guard;
leak_lint +diff/pct_change-neg, +.floor(freq=kw), +dict-tickers; `_raw` purity documented. Full
triage + DEFER/WON'T-FIX: `docs/INC3-HARDENING-BACKLOG.md`.

**NEXT (a FUTURE run — NOT started): Increment 4 — strategies + backtest.** Increment 3 is sealed; do
not reopen without cause. When Inc 4 starts: `StrategySpec` (frozen, YAML, references only registered
`factor_id`s + regime labels + z-crossings — structurally no hand-coded thresholds); the walk-forward
backtest; bump `n_trials` in the ledger for every factor/param/strategy combo evaluated. The Inc-3
DEFERs to clear: ledger DB-deletion high-water-mark (before the DSR consumer wires n_trials), the
registry-2 author-trust residual, stateful-_raw structural enforcement.

---

### (archived) Increment 3 build pointer — superseded by the seal above
Build complete at `51faaac` (clusters 1–5); red-team + remediation + seal followed.

### (archived) Increment 2 seal pointer
**Head:** `22cc76f` · `make inc1` AND `make inc2` → PASS. **✅ INCREMENT 2 SEALED** — all STEPs 0–8 done, live-proven, comprehensive sealing red-team complete (no confirmed live leak), all fix-now remediated.

---

## 🌙 Autonomous overnight run — ✅ COMPLETE 2026-06-22 (scope: "Finish Increment 2" — DONE; STOPPED as instructed)

All four phases done; Increment 2 is SEALED. The run STOPPED here — Increment 3 was NOT started.

1. ✅ **STEP 8 DONE** (commit `8d213bf`) — `data/prefix_stability.py` (registry-wide
   `compute(df[:k]) == compute(df[:k+1])[:k]`, fail-closed, proven to CATCH leaky factors) +
   `data/leak_lint.py` (AST ban-list: DATE_TRUNC `.date()`/`.normalize()`/`.floor(freq)`,
   GET_CALENDAR outside `calendar.py`, IMPUTATION `.fillna/.ffill/.bfill`, MODULE_TICKERS; AST not
   substring; **whitelists** `session_label_for_daily_bar`/`daily_bar_instant`). `leak-lint` wired
   as an explicit `make inc2` step; prefix-stability runs in the gated pytest suite.
2. ✅ **Comprehensive sealing red-team DONE** — Workflow `wf_84eb8983-25d` was throttled by a
   transient server-side rate limit (NOT a usage limit); SURV lens completed with 2 findings, both
   confirmed by 2 independent adversarial verifiers; remaining lenses finished by single-threaded
   main-loop review of the new STEP-7/8 surface; unchanged files already certified by
   `wf_d4deb502-ad8`. **Verdict: no confirmed live leak.** Full triage: `docs/INC2-HARDENING-BACKLOG.md`.
3. ✅ **Remediated all fix-now** (commit `45d292a`): SURV-1 `membership_vintage<=as_of` guard +
   T2-evidence auditability; LEAKLINT-WL calendar-scoped DATE_TRUNC whitelist. Both TDD, gated.
4. ✅ **Increment 2 SEALED.** STOPPED. Increment 3 NOT started (per the run's hard stop).

Discipline held EVERY step: TDD → `make inc1 && make inc2` green → commit → push → fast-forward
`main` → update this file + project memory.

---

## Where we are

```
✅ Onboarding   5 keys verified (Alpaca paper, Anthropic, Tavily, Firecrawl+MCP, Apify)
✅ ADR-001      architecture decided (edge-falsification harness; paper-only; lean scope)
✅ Inc 1        SAFETY SPINE — built, TDD, and CERTIFIED by 3 adversarial red-team passes
✅ Inc 2        Alpaca data spine — STEPs 0–8 DONE, live-proven, sealing red-team complete, SEALED
✅ Inc 3        Factors (lean 13) — built, red-team-hardened, SEALED (`2512d3f`)
✅ Inc 4        Strategies (4) + walk-forward backtest — built, red-team-hardened, SEALED (`8915ec3`)
⬜ Inc 5        Bias-gate + FIRST paper submit   ← NEXT (a future run; NOT started; needs Discord webhook)
⬜ Inc 6        Regime + allocator
⬜ Inc 7        Agents + orchestration
⬜ Inc 8        Dashboard (Layer 15 — the LAST layer; a real UI needs the engine first)
```

Honest scope (ADR-001): Inc 1–8 ≈ 55–90 focused build+test hours + a mandatory 14-day paper soak.
**The executor is currently a NO-OP** — `broker_paper.submit()` raises NotImplementedError; nothing trades.

## Increment 2 — SEALED (what's done); Increment 3 is the next run (NOT started)

**RED-TEAM COMPLETE** (`wf_d4deb502-ad8`, 9 lenses → adversarial verify → synth; 28 findings → ~9
issues; core PIT/leak guarantees were sound, no finding was a live leak). **All 8 `fix_now` items
REMEDIATED, gated, committed:** ALPACA-001 transport (`requests`, not httpx — was an uncaught
network-failure hole) · midnight-ET fail-closed session assertion via `calendar.session_label_for_daily_bar`
(replaced silent session-filtering) · empty/non-session fail-closed · `assert_utc` before stamping ·
feed/SIP provenance pinned (`SUPPORTED_FEEDS` + `IS_SIP_CONSOLIDATED`) · cache ADR-F7 disk-low pause +
`.parquet.tmp` cleanup · `read_dotenv` wired into `load_settings` (live auth works) · doc honesty
(G4 not wired; design §6 daily-label correction). Full triage + DEFER / WON'T-FIX: `docs/INC2-HARDENING-BACKLOG.md`.

**STEP 7 DONE** (design panel `wf_cf814eed-72a` → build, commits `12ce785`/`f032218`).
`data/universe.py` + `universe_sources.py`: PIT universe with survivorship-cleanliness STRUCTURALLY
UNREACHABLE (`SourceTier`+`TIER_IS_PIT` authority; forge-proof derived `survivorship_unverified`;
`@final as_of_members` derives the verdict from the subclass tier; `survivorship_t2` always
`passed=False`; no-hardcoded-list AST guard + content-hash). `OperatorFileUniverse` reads
content-hashed `config/universe.yaml` (honest non-PIT). `expected_grid` wired the deferred **G4**
coverage report (PIT-honest, DST-correct). Observability via stdlib logging. 40+ invariant tests.

**STEP 8 DONE** (commit `8d213bf`). `data/prefix_stability.py`: registry-generic look-ahead
property `compute(df[:k]) == compute(df[:k+1])[:k]`, pure/typed/fail-closed (raise·length·type·
index·dtype divergence ⇒ VIOLATION), generic over any iterable of computations so Inc-3
`AlphaFactor` plugs in with zero rework (`validate_all()` calls `check_registry`); tests prove
TEETH (full-series-z / centered-window / future-shift / normalize-by-last all CAUGHT).
`data/leak_lint.py`: AST ban-list over `data/` — DATE_TRUNC (`.date()`/`.normalize()` 0-arg,
`.floor(freq)`), GET_CALENDAR (outside `calendar.py`), IMPUTATION (`.fillna/.ffill/.bfill`),
MODULE_TICKERS (≥3 ticker-shaped literals); AST not substring (proven NOT to trip on
`schema.validate(df)`, `unicodedata.normalize(form,s)`, `np.floor(arr)`); whitelists
`session_label_for_daily_bar`/`daily_bar_instant`. `leak-lint` is an explicit `make inc2` step;
prefix-stability runs in the gated pytest suite.

**SEALING RED-TEAM COMPLETE + REMEDIATED** (commit `45d292a`). Comprehensive adversarial pass over
the whole layer incl. universe + STEP 8 (Workflow `wf_84eb8983-25d` was throttled by a transient
server-side rate limit, NOT a usage limit; SURV lens completed with 2 findings confirmed by 2
independent verifiers; the rest finished by single-threaded main-loop review of the new STEP-7/8
surface; unchanged files already certified by `wf_d4deb502-ad8`). **Verdict: no confirmed live
leak.** Two cheap in-scope hardenings of existing guards remediated (TDD, gated): **SURV-1**
`UniverseMeta` now rejects a `membership_vintage` after `as_of` (mirrors `pit_guard`/`AsOf`) + T2
records the vintage in evidence; **LEAKLINT-WL** the DATE_TRUNC whitelist is now scoped to
`calendar.py` only. Everything else deferred to the Polygon/Inc-3 increment or documented WON'T-FIX.
Full triage: `docs/INC2-HARDENING-BACKLOG.md`.

Full design + build plan: `docs/INCREMENT-2-DESIGN.md`. DONE & committed: STEP 0 deps+gate ·
STEP 1 reliability+errors · STEP 2 bar schema+BarMeta+IEX stamp · STEP 3 calendar(side='left'
half-open RTH)+quality gate · STEP 4 PIT guard + content-addressed Parquet cache · STEP 5 FINAL
`@final` `DataLoader` · STEP 6 `AlpacaBarLoader` (real IEX daily `_fetch` + contract tests,
network faked; one `live` smoke behind `pytest -m live`).

⚠️ FIXED THIS SESSION (commit `d917b25`): `.gitignore` line 19 was an UNANCHORED `data/` that
matched `src/trading/data/` and silently UNTRACKED the entire data layer — the STEP 2–5
`feat(data)` commits contained ONLY test files, zero implementation. A `git clean -fdx` or a
fresh clone would have destroyed all of Inc-2 while `make inc2` stayed green on the on-disk
files. Now anchored to `/data/` + `/logs/`; all 11 `src/trading/data/*.py` (incl. the Inc-1
`sanitize.py`) are tracked (rescue `d917b25`, STEP 6 tests `945557c`). **If you ever see a green
gate but `git ls-files` is missing a source dir again — this is the footgun; check `.gitignore`.**

**NEXT (a FUTURE run — NOT started this session): Increment 3 — factors (10–15, lean).** Increment 2
is sealed; do not reopen it without cause. When you start Inc 3: the `AlphaFactor` base registers
its factors with `prefix_stability.check_registry` (zero rework), extend `leak_lint` to scan the
factor layer (and add `.shift(<neg>)`/`.rolling(center=True)`/`.resample()` bans there), and clear
the Inc-3-targeted DEFERs in `docs/INC2-HARDENING-BACKLOG.md` (SURV-2 vintage-threading, real
PolygonUniverse, prefix-stability frame-adequacy contract).

Carried DEFER (recorded in `docs/INC2-HARDENING-BACKLOG.md`):
- alpaca-py `StockBarsRequest` STRIPS tzinfo (stores naive UTC wall-clock). `_fetch` passes UTC
  today so it is safe, but a non-UTC tz-aware `start`/`end` would be silently mis-clamped.
  Consider asserting/converting the window to UTC in `LoadParams.build` or `_fetch`.

## Non-negotiable invariants (do not regress)

- `LIVE_MODE = false` in config AND code; `paper=True` hardcoded; the LLM is never in the submit path.
- Config can only make risk limits STRICTER than the floor-of-floors (equity $20 / total-loss $30).
- Every error path fails CLOSED; non-finite inputs are rejected at construction.
- Red-team any safety/money-path code until an adjudicator certifies no reachable fail-open.

## Where the detail lives

- `docs/adr/ADR-001-foundation.md` — binding architecture decisions + rationale.
- `docs/RISK_REGISTER.md` — risk register from the design workflow.
- `CLAUDE.md` — governance (axioms, mistake taxonomy, never-do list, abandonment triggers).
- Project memory (`~/.claude/projects/-Users-maxagent-Trade/memory/`) — status + the hard-won
  insights (`insight-adversarial-self-review`, `insight-fail-open-patterns`, build conventions,
  operator working style). Loaded automatically each session.
- Session log: `~/.claude/session-data/2026-06-21-arcane-inc1-session.tmp`.
