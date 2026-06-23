# Increment 6 — DESIGN OF RECORD: First Paper Submit (Polygon PIT + Murphy Guards + Gate-Gated Record-Only Submit)

**Status:** Adjudicated synthesis of 4 lenses (Polygon-PIT, Executor/Murphy/Abandonment, Risk/Sizing/Idempotency, Adversarial Skeptic). Decision-grade. Build follows this directly via TDD.
**Date:** 2026-06-23
**Binding:** CLAUDE.md §0/§4.3/§5/§7/§8 + ADR-001 §0 (edge-falsification) + PHI1 (deterministic submit path, no LLM) + the cardinal-sin lesson (FC-1: no forgeable T2 pass).
**Locked expected outcome:** With the 4 edgeless toy strategies, **ZERO paper orders** is the CORRECT, EXPECTED result and a locked regression assertion. A non-zero first submit is a RED flag to investigate, never a milestone (ADR §0).

> Skeptic verdict reconciled: **CONDITIONAL — build PART A → PART B → PART C, each gated on the CRITICAL/HIGH structural mitigations below.** The architecture is the right shape; this doc closes the two CRITICAL holes (forgeable grant, global `_PIT_VERIFIER_WIRED` falling back to self-attested flags) and the HIGH holes BY CONSTRUCTION before any submit code is wired.

---

## 0. GROUND-TRUTH RECONCILIATION (verified against the live codebase this session)

These facts override any lens text that conflicts. Where a lens assumed something that the code already does differently, **the code wins** and the lens recommendation is adapted.

| Fact (verified) | Consequence for the spec |
|---|---|
| `data/universe.py` base seam is ALREADY FC-1-hardened: `PITUniverse.as_of_members` is `@final`, BASE owns `is_pit_membership=is_pit(type(self).SOURCE_TIER)`, `UniverseMeta.survivorship_unverified` is a **derived read-only property** (no writable bool), `__post_init__` enforces `is_pit_membership == is_pit(tier)`, PIT⇒vintage, and `vintage <= as_of` (SURV-1). | The Polygon-PIT lens's `MembershipProvenance` hook is correct but NARROWER than sketched: `_members` already returns `(symbols, artifact_hash)`. We thread `membership_vintage` through a new inert provenance hook; we do NOT re-architect the verdict ownership (it is already base-owned). |
| There are **TWO** distinct types: `bias_gate.verdict.GateDecision` (fields `spec_hash, allocated, components, n_trials, reasons`) and `executor.invariants.GateDecision` (fields `accepted, client_order_id, failed_gate`). | The skeptic's type-confusion attack is REAL. AllocationGrant must mint ONLY from the `bias_gate` one, re-running the ALL-of, and the executor chain keeps its own `GateDecision`. Disambiguate by import alias in the build. |
| There are **TWO** T2 surfaces: `universe.survivorship_t2(meta)->BiasTestResult` (pure, `passed=meta.is_pit_membership`) AND `bias_gate/tests_t2.py::t2_survivorship(result)->GateComponent` with module-global `_PIT_VERIFIER_WIRED=False`. The bias_gate one is the GATE component; it currently reads `result.survivorship_biased/unverified` (self-attested) behind the `_PIT_VERIFIER_WIRED` guard. | The skeptic CRITICAL is correct: flipping the global bool re-opens FC-1 because it falls back to self-attested flags. **We DELETE the global-bool-only path** and rewrite `t2_survivorship` to require a per-result hash-bound `MembershipArtifact`. The universe `survivorship_t2` stays as-is (advisory/reporting). |
| `bias_gate.verdict.GateDecision.components` + `combine_member_verdict`-style ALL-of (`bool(components) and all(c.passed ...)`) is the legitimate verdict. `GateDecision` is frozen but does NOT re-validate the ALL-of at construction. | Hand-constructing `GateDecision(allocated=True, components=())` is possible. AllocationGrant.from_decision MUST re-run `bool(components) and all(c.passed)` AND require the full frozen component-name set present AND T2 among them passed. |
| Executor primitives EXIST and are sealed: `kill_switch` (ARMED→TRIPPED→HARD_STOPPED monotonic, fail-safe-to-TRIPPED on corrupt read, `trip`/`hard_stop`/`read`/`is_armed`), `reconciler` (`assess_drift`→`ReconResult{level,require_auto_flat}`, `escalate_kill_switch` ORANGE→trip/RED→hard_stop), `risk/caps` (`check_per_trade_risk`/`check_equity_floor`/`check_total_loss_abandon`/`check_concentration`, all fail-closed on non-finite), `risk/constants` (`MAX_CONSECUTIVE_SCHEDULER_ERRORS=5`, `MAX_BAR_AGE_SECONDS=300`), `invariants.evaluate_pre_submit` (kill→M17→per_trade→daily→equity_floor→total_loss→concentration→idempotency→mistake), `idempotency` (`SqliteIdempotencyStore` with PRIMARY KEY atomic `remember`→bool, `client_order_id(intent)` sha256 over identity), `broker_paper` (`PaperBroker.submit` raises NotImplementedError; `ALPACA_PAPER=True` hardcoded+grep-able; `paper` read-only property), `live_mode` (`is_live`, marker triple-lock, `LIVE_CONFIRM_PHRASE`), `runner.execute_paper` (claim-then-record, submits NOTHING). `src/trading/guards/` is EMPTY. | We REUSE all of these; we do NOT re-encode caps/drift/kill semantics. PART B builds `guards/` from scratch. PART C extends `runner`/`broker_paper` and adds `grant`/`sizing`/`submit`/`reconcile_loop`. |
| `make inc5` already runs ruff+black+mypy --strict + `leak_lint src/trading/{data,factors,backtest,bias_gate,notify}` + `pytest --cov-fail-under=85`. | `make inc6` = inc5 surface **+ leak_lint over `src/trading/guards` and `src/trading/executor`** + the adversarial must-fail gate steps (§6). |

---

## 1. ROADMAP CONFIRMATION

**Inc 6 is re-sequenced to: Polygon-PIT universe + unforgeable T2 (PART A) → Murphy guards G1–G10 + §8 abandonment + §5.2 paging (PART B) → AllocationGrant + sizing + record-only gate-gated paper submit (PART C).** Regime classifier, allocator, slow-loop agents, and dashboard are DEFERRED to later increments.

This is CONFIRMED as coherent and SAFER than the original "Inc 6 = regime + allocator":

1. It front-loads ALL safety infrastructure (guards, §8, kill-switch escalation, idempotency reconciliation) BEFORE any non-deterministic allocator exists. The first time the system can act, ONLY the deterministic gate + deterministic sizer can produce an order — no regime/agent in the loop to violate PHI1. **Deferring the allocator is a feature, not a gap.**
2. Polygon-PIT is the correct prerequisite for acting: you cannot honestly allocate on a survivorship-unverified universe (T2 is the allocation key).
3. The locked ZERO-orders outcome means the missing allocator creates NO real gap — there is nothing to allocate, so the absent allocator can only correctly produce no trade.

### Flagged gaps and how this spec handles them

| Gap (flagged by skeptic / lenses) | Handling in this doc |
|---|---|
| **Sizer target position is undefined absent an allocator.** | PINNED to a HARD source for Inc 6: `TargetPosition` is constructed ONLY from broker-authoritative positions or a deterministic constant (flat). It is NEVER an agent/LLM output. A real target generator arrives with the deferred allocator and must stay import-isolated from the submit path (PHI1, enforced by `leak_lint` over `executor`). See §4.2. |
| **14-days-clean-paper precondition for LIVE.** | Untouched. NO LIVE this run. `is_live()` is asserted `False` unconditionally in the submit path AND `PaperBroker.paper` is hardcoded `True`. SUBMIT_GO only flips record-only → real-**paper**-submit, never paper → live. |
| **Wiring real alpaca-py submit (even record-only) crosses from pure-research to acting posture.** | The operator-GO token (`state/SUBMIT_GO`, single-use, phrase+spec-bound) and keep-NO-OP-until-GO discipline are LOAD-BEARING and must not be dropped. See §4.3. |
| **Adding 4 fields to the @final SEALED Inc-4 `BacktestResult`.** | RESOLVED: do NOT mutate the sealed stats container. Introduce a SEPARATE frozen `ProvenanceBinding` (membership_artifact_hash, traded_symbols, window_start, window_end) sourced STRUCTURALLY from the panel, passed ALONGSIDE `BacktestResult`. See §2.4 + §7 OQ-1. |

---

## 2. PART A — Polygon PIT Universe + Unforgeable T2 Verifier

**Goal:** make T2 CAPABLE of passing via a real point-in-time, survivorship-correct membership source, WITHOUT re-opening the FC-1 forge hole and WITHOUT any toy allocating.

### 2.1 Module list

| Path | Action | Purpose |
|---|---|---|
| `src/trading/data/universe.py` | **MODIFY** | Add inert `MembershipProvenance` data hook so PIT subclasses supply a real `(vintage, artifact_hash)` that the `@final` base threads into `UniverseMeta.membership_vintage`. Base still owns the verdict; `__post_init__` SURV-1 unchanged. |
| `src/trading/data/polygon_universe.py` | **NEW** | `PolygonPITUniverse(PITUniverse)`, `SOURCE_TIER=SourceTier.POLYGON_PIT`; queries `/v3/reference/tickers?ticker=SYM&date=as_of`, keeps PIT-active symbols, builds+seals a content-addressed `MembershipArtifact`, supplies provenance. Vendor adapter fails CLOSED to a typed error; NEVER returns a partial/clean member set. |
| `src/trading/data/membership_cache.py` | **NEW** | Content-addressed JSON cache for sealed artifacts, mirroring `ParquetCache` (atomic temp→fsync→`os.replace`, re-validate-on-read self-heal, byte-cap). Corrupt artifact = MISS (fail closed), never served-clean. |
| `src/trading/bias_gate/membership_artifact.py` | **NEW** | `MembershipArtifact`, `SymbolMembership`, `membership_artifact_hash()`, `ProvenanceBinding` (the hash-bind passed to T2). Lives in `bias_gate` because T2 is the only legitimate consumer of the pass decision. |
| `src/trading/bias_gate/tests_t2.py` | **MODIFY** | DELETE the global-bool-only fallback path; rewrite `t2_survivorship(result, binding, artifact)` to require an artifact bound by hash + coverage over every traded symbol across the backtest window. Self-attested flags become AND-ed defense-in-depth only (advisory), never the grant. |
| `docs/INCREMENT-6-DESIGN.md` | this file | design of record. |

`SourceTier.POLYGON_PIT` must exist in `universe.py` with `is_pit(POLYGON_PIT) is True` (it is the FIRST PIT tier; add it to the enum + `is_pit`).

### 2.2 Base-seam contract change (universe.py) — minimal, inert, fail-closed

Add a frozen data hook. The base branches on `is_pit(tier)`; for non-PIT tiers it does NOT call the hook (so `OperatorFileUniverse` is untouched and a non-PIT class physically cannot supply a vintage).

```python
@dataclass(frozen=True, slots=True)
class MembershipProvenance:
    vintage: datetime          # the as-of reconstruction date (vintage == as_of; equality allowed)
    artifact_hash: str         # content-addressed MembershipArtifact hash

class PITUniverse(ABC):
    SOURCE_TIER: ClassVar[SourceTier]

    # base default RAISES — a PIT subclass that forgets to override fails CLOSED, never None-defaults.
    def _membership_provenance(self, as_of: AsOf, session: pd.Timestamp) -> MembershipProvenance:
        raise RestatedMembershipError(
            f"{type(self).__name__} is a PIT tier but did not supply membership provenance"
        )

    @final
    def as_of_members(self, *, as_of: AsOf, session: str = "XNYS") -> UniverseSnapshot:
        sess = calendar.as_of_session(pd.Timestamp(as_of.ts))
        symbols, artifact_hash = self._members(as_of, sess)
        ...  # existing empty/hash/well-formed guards UNCHANGED
        tier = type(self).SOURCE_TIER
        if is_pit(tier):
            prov = self._membership_provenance(as_of, sess)   # may RAISE -> fail closed
            vintage = prov.vintage
            universe_hash = prov.artifact_hash                # the hash IS the provenance for PIT
        else:
            vintage = None
            universe_hash = artifact_hash
        meta = UniverseMeta(
            as_of=as_of.ts, session=sess, source_tier=tier,
            is_pit_membership=is_pit(tier),                   # BASE owns verdict (UNCHANGED)
            member_count=len(symbols), universe_hash=universe_hash,
            membership_vintage=vintage, loader=type(self).__name__,
        )
        return UniverseSnapshot(symbols=frozenset(symbols), meta=meta)
```

**Why this is forge-proof:** the hook returns only DATA (a vintage + a hash). `is_pit_membership` remains a pure function of the class tier — there is no bool to set. `__post_init__` independently re-validates (`vintage <= as_of`, PIT-iff-vintage). A PIT subclass that omits the hook RAISES. This is the Polygon-PIT lens's recommendation, adapted to the verified base (the base already owns the verdict). **REJECTED** (re-opens FC-1): letting the subclass override `as_of_members` or return `is_pit_membership`.

### 2.3 MembershipArtifact shape + content-addressing

```python
@dataclass(frozen=True, slots=True)
class SymbolMembership:
    symbol: str
    active: bool                       # active at the as_of date
    listed_utc: datetime | None        # may be None when API omits it (see OQ rule §2.7)
    delisted_utc: datetime | None      # None or > window_end => interval open through window

@dataclass(frozen=True, slots=True)
class MembershipArtifact:
    schema_version: int
    source_tier: SourceTier            # == POLYGON_PIT
    as_of: datetime
    vintage: datetime                  # reconstruction date (== as_of)
    members: tuple[SymbolMembership, ...]   # sorted by symbol for stable hashing

def membership_artifact_hash(a: MembershipArtifact) -> str:
    # canonical bytes: sort_keys + compact separators + isoformat datetimes (mirror cache_key /
    # OperatorFileUniverse — hash the canonical bytes, NOT the parsed set).
    return sha256(json.dumps(canonical(a), sort_keys=True, separators=(",", ":"),
                             default=lambda d: d.isoformat()).encode()).hexdigest()

@dataclass(frozen=True, slots=True)
class ProvenanceBinding:
    """Passed ALONGSIDE BacktestResult to T2 — the unforgeable pass key. Sourced STRUCTURALLY
    from the panel the engine actually ran (bars.keys() + index), never author-declared."""
    membership_artifact_hash: str
    traded_symbols: tuple[str, ...]    # == sorted(panel.bars.keys())
    window_start: datetime             # == panel index min
    window_end: datetime               # == panel index max
    as_of: datetime
```

`ProvenanceBinding` is a SEPARATE frozen DTO — the sealed Inc-4 `BacktestResult` is NOT mutated (resolves OQ-1; avoids an Inc-4 re-seal). The engine populates it from the panel it actually ran, mirroring how `spec_hash` is DERIVED not declared (closes the "window/symbol provenance forgery" HIGH).

### 2.4 The T2 verifier predicate (the legitimate flip)

`t2_survivorship` is rewritten to consume `(result: BacktestResult, binding: ProvenanceBinding, artifact: MembershipArtifact)`. The module global `_PIT_VERIFIER_WIRED` bool-only fallback is **DELETED**. Pass requires ALL (else `passed=False` with reason; any exception → `passed=False` with the error in the reason):

```
passed = (
    tier_ok        # artifact.source_tier == POLYGON_PIT AND is_pit(artifact.source_tier)
  and hash_ok      # membership_artifact_hash(artifact) == binding.membership_artifact_hash
  and vintage_ok   # artifact.vintage <= binding.as_of
  and coverage_ok  # EVERY symbol in binding.traded_symbols has a SymbolMembership whose
                   #   [listed_or_-inf, delisted_or_open) interval COVERS
                   #   [binding.window_start, binding.window_end]  (active across the WHOLE window)
  and no_missing   # no binding.traded_symbol is absent from artifact.members
  and (not result.survivorship_biased)       # defense-in-depth: AND-ed, advisory, NEVER the grant
  and (not result.survivorship_unverified)   # ditto
)
```

- **(coverage_ok) + (no_missing) are the survivorship TEETH.** The bug a flat watchlist commits is dropping SIVB before its delist; coverage-over-window + no-missing catches exactly that.
- **(hash_ok)** prevents swapping in a benign artifact; to forge a pass you would have to produce a Polygon-shaped artifact covering every traded symbol's window whose canonical JSON hashes to the value already bound — i.e. actually do the PIT reconstruction.
- The two self-attested bools are AND-ed in as EXTRA strictness only → the path is strictly STRICTER than today, never looser. **REJECTED** (FC-1 verbatim): keeping T2 reading only `BacktestResult` flags and flipping a bool.

Coverage rule for absent `listed_utc` (OQ-1 resolution, conservative): if `listed_utc is None` but the artifact reports `active is True` at `as_of` and `delisted_utc` is null-or-`> window_end`, treat the start boundary as covered (active-at-window-start is the authority). If `active is False` at `as_of`, the symbol is NOT PIT-active → coverage fails. Granularity: the artifact is built at a single `as_of`; the closed interval is computed from `delisted_utc` — assert `delisted_utc is None OR delisted_utc > window_end` (1 call/symbol, within the 5/min budget). Pinned by the LIVE smoke (§5 LIVE).

### 2.5 Caching, rate-limit, fail-closed behavior

- **Build path (offline, deterministic):** `PolygonPITUniverse` queries `/v3/reference/tickers?ticker=SYM&date=as_of` ONCE per symbol, throttled to ≤5 calls/min via a token-bucket SLEEP (not a fail). A symbol returning `count 0` at `date=as_of` is recorded NOT-active-then (correctly excluded). It seals a `MembershipArtifact` into `MembershipCache` (content-addressed).
- **Gate path:** T2 makes NO network calls. It loads the artifact from the content-addressed cache by hash and re-hashes. (Determinism + the 5/min limit + fail-closed-on-network forbid live re-verify in the gate. **REJECTED:** live re-verify at gate time — non-deterministic survivorship time-bomb, throttle-blowing, and would fail closed anyway.)
- **Fail CLOSED, never to a clean universe:** HTTP 429, network error, timeout, non-200, missing `date` echo, or tier/shape mismatch all raise a typed `PolygonProvenanceError` that **ABORTS** artifact construction. There is NO except-branch returning a "best-effort" member set, and NO partial artifact is ever sealed. Because T2 binds by hash and requires coverage of EVERY traded symbol, a missing/aborted artifact means no hash exists to match → T2 fails closed downstream. Page YELLOW when a rate-limit degrades a scheduled verification.
- **Allowlist semantics (skeptic MEDIUM):** PIT membership is an ALLOWLIST. Include a symbol for an `as_of` ONLY on explicit `active:true` at that date (`count>0`, `delisted_utc` null-or-after-`as_of`). Empty/error/ambiguous → EXCLUDE; a backtested-but-unconfirmed symbol → T2 KILL (no_missing). Default-on-ambiguity is FORBIDDEN.

### 2.6 The must-fail survivorship TEETH test (the load-bearing test)

`test_t2_drops_SIVB_before_delist_fails`: take a VALID artifact whose backtest window spans 2023-03-28 (SIVB's delist), DROP SIVB from `artifact.members` (the survivorship sin), keep `binding.traded_symbols` including SIVB → assert `t2_survivorship(...).passed is False` with a coverage/no-missing reason. Variant: SIVB PRESENT but `delisted_utc` mid-window (interval does not cover `window_end`) → `passed is False`. These prove the teeth bite.

### 2.7 Does wiring Polygon let a toy allocate? — REFUTED, proven by decomposition (ADR §0)

Wiring Polygon removes ONE of the ALL-of components from the blocked list. The statistical wall (DSR>0.95, PSR>0.95, PBO<0.5, SPA p<0.05, WF-OOS Sharpe>0, enough_samples) is INDEPENDENT and the 4 toys have no edge → they remain KILLED. Capability is proven by decomposition, NEVER by allocation:
- **(a) must-PASS in isolation:** a synthetic sealed artifact over a known continuously-PIT-active set with matching hash → `t2_survivorship` returns `passed=True`.
- **(b) must-FAIL teeth:** §2.6.
- **(c) hash-mismatch:** swapped artifact → `passed=False`.
- **(d) end-to-end null:** `evaluate_family` over the 4 toys with T2 CAPABLE → `allocated=False` for ALL FOUR, with the failing reasons coming from the STATISTICAL components (DSR/PSR/PBO/SPA/WF), proving T2 is no longer the sole blocker yet zero orders result.

---

## 3. PART B — Murphy Guards G1–G10 + §8 Abandonment + §5.2 Paging Escalation

**Goal:** ship the §5 Murphy guards, the §8 abandonment evaluator, and the §5.2 paging-latency ladder as PURE deterministic functions over injected HARD/STRUCTURED state, composing with the EXISTING kill_switch + reconciler + notifier, with NO duplication of caps/drift/kill semantics.

### 3.1 Module list (all NEW under `src/trading/guards/`)

| Path | Purpose |
|---|---|
| `guards/levels.py` | `GuardLevel(StrEnum) GREEN/YELLOW/ORANGE/RED`; `GuardResult(frozen,slots){guard_id,level,reason,gates_orders:bool}`; `worst_level(results)->GuardLevel`; `recon_to_guard(ReconLevel)->GuardLevel` (OK→GREEN, RED→RED). |
| `guards/inputs.py` | Frozen, finite-guarded injected HARD/STRUCTURED DTOs (no I/O). `GuardState` + `AbandonmentState` + page-ladder inputs. `__post_init__` rejects non-finite (mirrors `AccountSnapshot`). |
| `guards/checks.py` | G1–G10 as pure fns over `GuardState`; each fails CLOSED (missing/non-finite → RED, or ORANGE for advisory). G3 DELEGATES to reconciler. Thresholds are module-level constants (law, like `risk/constants.py`), NOT YAML-tunable. |
| `guards/panel.py` | `GuardPanel.assess(state)->tuple[GuardResult,...]`; `apply_guards(results, kill_switch, notifier)->GuardApplication{worst,auto_flat,paged}`. The ONLY guard code that mutates kill_switch. Reuses `reconciler.escalate_kill_switch` for G3. |
| `guards/abandonment.py` | `AbandonmentState`; `evaluate_abandonment(state,cfg)->AbandonmentVerdict{triggered,trigger_id,reason}`; `engage_abandonment(verdict,kill_switch,notifier)` (idempotent hard_stop + RED page). Reuses `check_total_loss_abandon`/`check_equity_floor`. |
| `guards/page_escalation.py` | `PageState`/`EscalationAction(NONE/RESEND_15/RESEND_30/TERMINAL_LIQUIDATE)`; `PageEscalation(path){open_page,acknowledge,tick(now)}`; `apply_escalation(action,kill_switch,notifier,broker_flat_fn)`. Clock-injected, disk-persisted. |
| `guards/__init__.py` | minimal exports (leak_lint target). |

### 3.2 GuardLevel graduated mapping (mirrors ReconLevel; one applier owns kill_switch)

| Level | Meaning | Action (centralized in `apply_guards`) |
|---|---|---|
| GREEN | guard healthy (ReconLevel.OK maps here) | noop + log |
| YELLOW | dashboard banner | `structlog.info`; NO kill action |
| ORANGE | pause new orders | `kill_switch.trip(reason)` (existing chain blocks when not ARMED) |
| RED | disaster | `kill_switch.hard_stop(reason)` **at t=0** + `notifier.page_operator(Severity.RED, reason)` + set `auto_flat=True` |

**Skeptic HIGH (RED ladder stall) resolved:** RED takes the protective action (`hard_stop` + `auto_flat`) IMMEDIATELY, NOT after a 60-min ack ladder. The 15/30/60 ladder (§3.5) escalates NOTIFICATION only. A RED page that raises on delivery MUST NOT prevent the already-issued `hard_stop` (caught at the loop boundary; `kill_switch` is latched durably first). Centralizing kill_switch mutation in ONE applier prevents a guard forgetting to page on RED (NOTIFY-class fail-open). **REJECTED:** per-guard `escalate()` methods (scatters trip/hard_stop/page policy across 10 modules).

### 3.3 Live-fed vs structurally-present; order-gating vs loop-only (§4.3 enforced)

| Guard | Fed | Gates an ORDER? | Notes |
|---|---|---|---|
| G1 data-staleness | LIVE (`now - data_as_of`, same M17 input) | YES | escalating ORANGE/RED by age; age<0 (future bar) → RED |
| G2 fill-delay | LIVE the moment PART C submits (injected pending-order age) | YES | |
| G3 recon-drift | LIVE (reconciler) | YES | DELEGATES to `assess_drift`/`escalate_kill_switch` — no duplication |
| G4 broker-heartbeat | LIVE (last successful broker-API epoch) | YES | |
| G6 time-drift | LIVE (injected NTP offset) | YES | `|offset|>1s` → RED; `ntp_offset_s is None` → **RED** (fail-closed, NTP-unavailable must NOT read GREEN) |
| G7 equity-velocity | LIVE (consecutive `AccountSnapshot.equity_usd` + epochs) | YES | single sample / zero dt → fail-closed RED (no div-by-zero) |
| G8 order-frequency | LIVE (submitted-coid count in rolling window) | YES | `>3× baseline` → ORANGE; baseline≤0/non-finite → RED |
| G5 LLM-heartbeat | structural (injected `last_llm_ok_epoch`) | **NO** (DERIVED §4.3) | RED pages + can hard_stop the LOOP, but EXCLUDED from the pre-submit ARMED decision |
| G9 correlation-spike | structural (injected signed exposures) | **NO** | structural until >1 live strategy |
| G10 prompt-injection | structural (injected sanitizer flag-count/24h) | **NO** (TEXTUAL §4.3) | |

`gates_orders=False` is STRUCTURAL on G5/G9/G10, with a TEETH test asserting they can NEVER appear in the order-gating subset. They may hard_stop the LOOP on RED but their result is excluded from the pre-submit ARMED decision (§4.3: DERIVED/TEXTUAL data can advise, never trigger/block an order). Structurally-present guards ship NOW (tested with injected fakes) so the applier+loop contract is exercised; flipping them live later is data-plumbing, not a safety redesign. **Skeptic §4.3 HIGH resolved by this structural split + teeth test.**

### 3.4 §8 Abandonment predicates (all 8 terminal = hard_stop; reuse caps, no re-encode)

`evaluate_abandonment(state, cfg)` — pure over injected state. EXACT predicates (boundary table in tests):

1. total loss > $30: REUSE `check_total_loss_abandon(cfg, state.cumulative_loss_usd).ok is False` (NO re-encoded constant).
2. equity floor < $20: REUSE `check_equity_floor(cfg, state.equity_usd).ok is False`.
3. 5 consecutive scheduler errors: `state.consecutive_scheduler_errors >= C.MAX_CONSECUTIVE_SCHEDULER_ERRORS`.
4. recon drift >2 for >10min: `state.recon_red is True` (thread the SINGLE live `ReconResult` in; do NOT recompute — OQ-resolved).
5. LLM-fail >30%/24h: `calls>0 and failures/calls > 0.30`; fail-closed: `calls==0` with a recorded failure → triggered; non-finite → triggered.
6. mistake category ≥3 in 7d: `max(counts_7d.values(), default=0) >= 3`.
7. calibration error >30% for 2 consecutive weeks: `state.calib_weeks_over_30pct >= 2`.
8. operator `make abandon`: presence of `state/ABANDON` marker (mirrors live-mode marker pattern).

`engage_abandonment(verdict, kill_switch, notifier)`: `kill_switch.hard_stop(reason)` + `notifier.page_operator(Severity.RED, reason)`, idempotent (hard_stop monotonic). Triggers 1,2,3,8 LIVE now; 4 live via reconciler; 5,6,7 structurally-present (injected ledger counters, safe no-op until fed — an unfed counter cannot MASK a trip). **Restart-safety:** verdict is pure; the hard_stop it engages is the persisted monotonic kill_switch; on restart `preflight` + `kill_switch.read()` re-derive HARD_STOPPED from disk; volatile counters (3,5,6,7) are re-fed by the orchestrator from on-disk ledgers. **REJECTED (cardinal duplication):** re-encode $30/$20/5 as fresh comparisons (two definitions can diverge — the M-class drift the floor-of-floors exists to prevent). A property test asserts abandonment and the pre-submit cap AGREE on the same loss/equity inputs.

### 3.5 §5.2 Paging escalation state machine (NOTIFICATION ladder only; terminal liquidate unconditional)

Clock-injected, disk-persisted ladder over `state/page_ack.json`. States: `PENDING_ACK → NOTIFIED_15 → NOTIFIED_30 → LIQUIDATE_60 → RESOLVED`. `tick(now) -> EscalationAction` is a PURE transition:

| Elapsed since `opened_epoch` (acked False) | Action |
|---|---|
| acked OR no open page | `NONE` |
| `[900, 1800)` s | `RESEND_15` (tagged `[NO ACK 15m]` Telegram resend; Twilio SMS absent → tagged resend, DEFER) |
| `[1800, 3600)` s | `RESEND_30` (tagged `[NO ACK 30m — would call]`) |
| `>= 3600` s | `TERMINAL_LIQUIDATE` |

`apply_escalation(TERMINAL_LIQUIDATE, ...)` MUST: emit auto-flat (close-all) + `kill_switch.hard_stop("§5.2 60-min no-ack auto-liquidate")` + final RED page — all three. ACK = operator writes `state/PAGE_ACK` marker containing the open page id (deterministic, testable; a future Telegram callback replaces it without changing `tick`). `opened_epoch` persisted → a crash at minute 40 still liquidates at minute 60. **Critically:** this ladder runs on an INDEPENDENT watchdog cadence, NOT the trading scheduler, AND the protective RED action for a guard already happened at t=0 in §3.2 — the ladder is purely the operator-notification escalation, so a wedged trading scheduler cannot prevent the disaster response.

### 3.6 Runner-loop ordered steps — see PART C §4.5 (the loop composes A+B+C). Listed there because the submit body is PART C.

---

## 4. PART C — Gate-Gated Record-Only Paper Submit

**Goal:** the deterministic submit path. An order can be produced ONLY for a `bias_gate` `GateDecision` with `allocated=True`; sized within immutable caps; record-only until a single-use operator-GO; idempotent claim-then-submit; real alpaca-py paper submit behind a live smoke. NO LLM import (PHI1).

### 4.1 Module list

| Path | Action | Purpose |
|---|---|---|
| `executor/grant.py` | NEW | `AllocationGrant` capability token, mintable ONLY from a `bias_gate.verdict.GateDecision` with `allocated=True` re-checked. |
| `executor/sizing.py` | NEW | `size_order(...)->Sized|NoTrade`; conservative integer-share flooring within caps; fail-closed. |
| `executor/submit.py` | NEW | `submit_allocated(grant, ...)`; requires an `AllocationGrant` (never a bool/GateDecision); RECORD_ONLY vs single-use operator-GO LIVE_SUBMIT. |
| `executor/reconcile_loop.py` | NEW | post-submit + cadence reconciliation; on RED auto-flat (cancel+close-all) + hard_stop + RED page. Wraps sealed `reconciler.py`. |
| `executor/loop.py` | NEW | `run_loop_pass(ctx)`: the single restart-safe, fail-closed per-pass orchestrator (recon→guards→abandonment→page-tick→auto_flat-or-submit). NO LLM import. |
| `executor/broker_paper.py` | MODIFY | wire `PaperBroker.submit(coid)` to real alpaca-py `TradingClient(paper=ALPACA_PAPER)` via an INJECTED client factory; broad `except Exception` → `BrokerOrderAck(accepted=False)`; token never logged. |
| `executor/runner.py` | MODIFY | route through grant+sizing+submit; record-only unchanged as the default. |

### 4.2 AllocationGrant unforgeability contract (closes the CRITICAL FC-1-at-executor hole)

```python
_MINT = object()   # module-private sentinel

@dataclass(frozen=True, slots=True)
class AllocationGrant:
    spec_hash: str
    universe_artifact_hash: str       # binds to the exact PIT membership T2 passed against
    n_trials: int
    decision_id: str                  # sha256 over the canonical GateDecision (replay key)

    def __init__(self, *args, _token=None, **kw):
        if _token is not _MINT:
            raise AllocationDenied("AllocationGrant is constructible only via from_decision")
        ...  # object.__setattr__ for frozen

    @classmethod
    def from_decision(cls, d: BiasGateDecision, *, universe_artifact_hash: str) -> "AllocationGrant":
        # RE-RUN the ALL-of — do NOT trust d.allocated alone (a hand-built
        # GateDecision(allocated=True, components=()) must NOT mint).
        names = {c.name for c in d.components}
        if not (d.allocated
                and bool(d.components)
                and all(c.passed for c in d.components)
                and FROZEN_COMPONENT_NAMES <= names         # every ALL-of member present
                and "T2_survivorship" in names              # T2 explicitly among the passed
                and d.spec_hash):
            raise AllocationDenied(f"not allocatable: {d.reasons or 'vacuous/incomplete components'}")
        return cls(spec_hash=d.spec_hash, universe_artifact_hash=universe_artifact_hash,
                   n_trials=d.n_trials, decision_id=_decision_id(d), _token=_MINT)
```

- The submit entrypoint signature is `submit_allocated(grant: AllocationGrant, target, quote, snapshot, cfg, kill_switch, store, broker, *, ...) -> ExecutionResult` and **NEVER** accepts a bool or a `GateDecision`. Omission is a `TypeError` (grant is a required, non-defaulted, first positional param — gate 0). A killed strategy has `allocated=False`, so `from_decision` raises before any `OrderIntent` exists — the killed path is UNREPRESENTABLE, not merely guarded by an `if`.
- **Binds BOTH `spec_hash` AND `universe_artifact_hash`** → non-replayable for a different/forged strategy AND tied to the exact verified PIT membership set T2 passed against (a grant minted under PIT cannot be replayed under a flat/forged watchlist). `submit_allocated` asserts `grant.spec_hash == intent's strategy spec_hash` and aborts on mismatch (confused-deputy).
- **Grep-ban `GateDecision(allocated=True)` outside `combine_member_verdict`** (extend leak_lint). **REJECTED:** passing the `GateDecision`/bool into submit and checking `if decision.allocated:` (FC-1 shape — forgeable in-band field, killed path reachable-but-rejected, one bad refactor re-opens it).

### 4.3 Sizing within caps (closes the self-reported-notional HIGH; ADR §0 honored)

`size_order(grant, target: TargetPosition, quote: HardQuote, account: AccountSnapshot, cfg, *, max_quote_age_s=C.MAX_BAR_AGE_SECONDS) -> Sized(intent) | NoTrade(reason)`. Fail-closed by construction (no order is the default).

- **HARD inputs only (§4.3), finite-checked at top; any missing/non-finite/non-positive/stale → NoTrade:** `quote.price` (with `quote.as_of_epoch` staleness reusing `MAX_BAR_AGE_SECONDS`), `account.equity_usd`. `TargetPosition` is built ONLY from broker-authoritative positions or a deterministic flat constant — NEVER an agent output (PHI1).
- **Algorithm (immutable, integer-share, conservative):**
  1. `budget = min(cfg.per_trade_risk_usd, cfg.max_position_concentration_pct/100 * equity, equity - cfg.equity_floor_usd)`; `budget <= 0` → NoTrade.
  2. `qty = floor(budget / price)`. Because `per_trade=$1` and one share of any real symbol >> $1, `qty == 0` for essentially every real symbol → `NoTrade("budget $1.00 buys 0 whole shares of SYM @ $X")`. **This is the EXPECTED, correct outcome.**
  3. If `qty >= 1`: `intended_risk_usd = qty*price` (WHOLE notional at-risk — conservative, no protective stop exists this increment), `est_position_value_usd = qty*price` — consistent with `qty × the FRESH HARD quote` (closes the self-reported-notional attack).
  4. Strict-inequality safety margin: require `intended_risk <= per_trade` AND `est/equity*100 <= concentration` AND `equity - est >= equity_floor`; any failure → NoTrade. **If 1-share notional exceeds per_trade, REJECT — never round qty to 0-and-submit, never loosen the cap.**
- The sized intent is STILL re-validated independently by `evaluate_pre_submit` (the same numbers checked twice by different code — caps are the wall, sizing is the funnel).
- **REJECTED (ADR §0 violation):** fractional shares + modeled stop-distance risk to make $1 "fit" — the exact lever to manufacture an order, and it understates risk vs whole-notional. Integer-share + whole-notional is the safe floor; a property test asserts `NoTrade` at $1 caps for any `price>1`.

### 4.4 NO-OP-until-operator-GO (single-use, spec-bound, phrase-protected)

`submit_mode(grant, *, go_marker_path=Path("state/SUBMIT_GO")) -> RECORD_ONLY | LIVE_SUBMIT`:
- **LIVE_SUBMIT requires** (a) `state/SUBMIT_GO` exists containing the exact phrase `I_AUTHORIZE_ONE_PAPER_ORDER` AND `grant.spec_hash` on its own line (authorizes ONE specific strategy's first order); single-use — the runner consumes/rotates the marker after one consumed submit; AND (b) `is_live(cfg.live_mode) is False` (asserted UNCONDITIONALLY regardless).
- **Default (no marker) → RECORD_ONLY:** runs the FULL gate chain + claims idempotency + writes a journal record of the would-be intent, submits NOTHING (today's `runner` behavior, extended to log the intent).
- `is_live()` is asserted `False` in-path AND `PaperBroker.paper` is hardcoded `True` → paper even under LIVE_SUBMIT. SUBMIT_GO flips record-only → real-PAPER-submit, never paper → live. This run is NO LIVE.
- **REJECTED:** a standing `SUBMIT_ENABLED=True` flag (replayable, not single-use, not spec-bound — one bad merge turns the pool live-submitting). The single-use spec-bound marker mirrors the proven `LIVE_MARKER` triple-lock; it must be a DISTINCT marker from live-mode (OQ-2 → recommend distinct, non-live marker so "allow real paper submits" is independent of "go live").

### 4.5 Idempotency + reconciliation ordering, and the restart-safe loop

**CLAIM-THEN-SUBMIT (at-most-once), with broker `client_order_id` as second line of defense** (mirrors the verified `runner.execute_paper`):
1. `evaluate_pre_submit` (incl. idempotency `seen()` read + all caps + mistake check).
2. `newly = store.remember(coid)` — atomic INSERT under `SqliteIdempotencyStore` PRIMARY KEY; `not newly` → abort "lost idempotency race", submit NOTHING.
3. ONLY THEN `broker.submit(coid)` passing `coid` as the Alpaca `client_order_id`.
4. record the `BrokerOrderAck` to the journal regardless of accepted/rejected.

A crash between (2) and (3): on restart `coid` is already `seen()` → `evaluate_pre_submit` rejects the retry at the idempotency gate (at-most-once; NEVER double-submit). A possibly-orphaned claim surfaces as broker-vs-local DRIFT and is resolved by reconciliation, NOT a blind retry. **Startup reconciliation** of claimed-but-unconfirmed keys queries Alpaca `get_order_by_client_id` and records the ACK or marks abandoned (closes the crash-window MEDIUM). `client_order_id` identity includes a session/bar-timestamp so two legitimate same-shape orders differ while staying crash-deterministic within an attempt. **REJECTED:** submit-then-claim (a crash after broker-accept but before claim re-submits a duplicate — M10, the cardinal idempotency failure).

**`run_loop_pass(ctx) -> LoopPassResult` ordered, fail-closed, each step short-circuiting:**
0. PREFLIGHT (once at process start): `preflight(kill_switch, cfg.live_mode)`.
1. read kill_switch; if not ARMED, skip to manage/reconcile-only BUT still run recon+guards+abandonment (a TRIPPED loop must still escalate to hard_stop).
2. `assess_drift(...)` → `escalate_kill_switch` (reconciler, reused).
3. `GuardPanel.assess(state)` → `apply_guards(...)` (ORANGE trips, RED hard_stops + pages + `auto_flat`).
4. `evaluate_abandonment(...)` → if triggered `engage_abandonment` (hard_stop + RED page).
5. `tick`/`apply_escalation` for any open operator page.
6. if any RED `auto_flat` OR recon `require_auto_flat` OR abandonment triggered → broker close-all (deterministic), then RETURN (no submits this pass).
7. ONLY if `kill_switch.read()` is ARMED and no auto_flat: for each `AllocationGrant` (mintable only from `allocated=True` — toys yield ZERO, so this body is empty this run): `size_order` → `evaluate_pre_submit` (incl. M17 + §2.2 mistake check) → assert `is_live(cfg.live_mode) is False` → claim idempotency → `submit_mode` → `PaperBroker.submit` (NO-OP/record-only until operator-GO) → reconcile the ack.

Running recon+guards+abandonment BEFORE and INDEPENDENT of the submit decision means the loop can always escalate even when already TRIPPED, and auto_flat strictly precedes any submit (a RED pass never also submits). Any exception in steps 2–5 increments `consecutive_scheduler_errors` (feeds §8 trigger 3) and the pass returns WITHOUT submitting — an exception never reaches the submit path with ARMED still true (closes the stale-snapshot/ordering-race HIGH; bound `AccountSnapshot` freshness → stale equity/loss = KILL). **REJECTED:** running the submit decision first and only checking guards if an order is pending (a quiet disaster pass would skip escalation).

### 4.6 Real alpaca paper submit behind a live smoke (hermetic gate)

`PaperBroker` takes an INJECTED client factory; unit tests pass a fake (built from real vendor behavior per fakes-must-mirror-reality). The real `TradingClient(paper=ALPACA_PAPER)` is constructed ONLY inside `tests/live/test_paper_submit_live.py` (`@pytest.mark.live`, EXCLUDED from `make inc6`) against `.env` APCA paper keys. A broker exception → `BrokerOrderAck(accepted=False)` (broad-catch fail-closed); token never appears in logs. Note: with $1 caps, sizing yields zero shares even under an operator GO, so the expected outcome under GO is STILL NoTrade/zero orders — the GO proves the WIRING, the gate+sizing prove the discipline.

---

## 5. TDD CLUSTER PLAN (ordered, test-first; each cluster ships RED→GREEN with its teeth)

> Convention: `make incN`-style — write the must-fail/must-pass teeth FIRST, watch it fail, implement minimally, watch it pass. Coverage stays ≥85. Phases map to PART A (C1–C4), PART B (C5–C8), PART C (C9–C13), gate (C14).

**PART A — Polygon PIT + unforgeable T2**

- **C1 — base-seam provenance hook.** MUST-PASS: a `PolygonPITUniverse` supplying `vintage<=as_of`+hash builds a valid `POLYGON_PIT` `UniverseMeta` with `is_pit_membership=True`, `survivorship_unverified is False`. MUST-FAIL: a PIT subclass NOT overriding `_membership_provenance` raises `RestatedMembershipError`; `POLYGON_PIT` meta with `membership_vintage=None` raises; vintage `> as_of` raises (SURV-1 unchanged). FORGE-CLOSED: no writable field sets `is_pit_membership` independent of tier; a hand-built `MembershipProvenance` cannot make a non-PIT class report clean.
- **C2 — MembershipArtifact content-addressing.** MUST-PASS: same artifact → same hash; round-trips stable across runs (sort_keys+separators+isoformat). MUST-FAIL: any single field change (drop a symbol / change `delisted_utc` / change vintage) → DIFFERENT hash.
- **C3 — MembershipCache + Polygon adapter fail-closed.** MUST-FAIL (teeth): mock 429 / network error / timeout / non-200 / missing-date-echo each raise `PolygonProvenanceError` and ABORT — assert NO partial artifact written. MUST-PASS: cache self-heal — corrupt/truncated cached artifact is a MISS (returns None), atomic write leaves no orphan on simulated crash.
- **C4 — T2 verifier flip (the legitimate close of FC-1).** MUST-PASS (capability, no allocation): synthetic sealed artifact over a continuously-PIT-active set with matching `binding.membership_artifact_hash` → `t2_survivorship(...).passed is True`. **MUST-FAIL (the load-bearing teeth):** drop SIVB before 2023-03-28 with window spanning the delist → `passed is False` (coverage/no-missing reason); variant SIVB delisted mid-window → `passed is False`. MUST-FAIL: hash-mismatch / wrong-tier (OPERATOR_FILE) / `vintage>as_of` → `passed is False`. MUST-FAIL: any I/O exception inside T2 → `passed is False` with the error in the reason. ASSERT the global-bool-only fallback path is DELETED (grep).

**PART B — Murphy guards + §8 + §5.2**

- **C5 — levels.** `worst_level` folds GREEN<YELLOW<ORANGE<RED; `recon_to_guard` parity table (OK→GREEN, RED→RED).
- **C6 — checks G1–G10.** Per-guard boundary + fail-closed: G1 age<0→RED, non-finite epoch rejected at `GuardState` construction; G6 `ntp_offset_s=None`→RED; G7 zero-dt→RED; G8 baseline≤0→RED. **TEETH:** G5/G9/G10 have `gates_orders is False` on EVERY result and can NEVER appear in the order-gating subset; RED still pages; missing input → ORANGE/RED not GREEN.
- **C7 — panel.apply_guards.** ORANGE → `kill_switch.trip` exactly once; RED → `hard_stop` AND `page_operator(Severity.RED)` AND `auto_flat=True` (spy kill_switch); GREEN/YELLOW → no kill_switch mutation. TEETH: a RED guard whose notifier `page` raises STILL hard_stops (latched first).
- **C8 — abandonment + page_escalation.** Boundary table: each of 8 triggers fires at the boundary (loss=30.01, equity=19.99, errors=5, recon_red=True, llm 31/100, mistake=3, calib=2, marker present); just-inside does NOT (30.0, 20.0, 4, 29%). REUSE proof: spy/property test that triggers 1/2 call through `check_total_loss_abandon`/`check_equity_floor` and AGREE with the pre-submit cap on the same inputs. Fail-closed: `llm_calls=0`+recorded failure → triggered; `engage_abandonment` idempotent. Ladder tick table: +0→NONE, +901→RESEND_15, +1801→RESEND_30, +3601→TERMINAL_LIQUIDATE; after `acknowledge()`→NONE; restart reload at +3601 still TERMINAL_LIQUIDATE. TERMINAL → `broker_flat_fn` AND `hard_stop` AND final RED page (all three).

**PART C — grant + sizing + submit + loop**

- **C9 — AllocationGrant unforgeability.** MUST-FAIL: `from_decision` raises `AllocationDenied` for each of the 4 killed toys (`allocated=False`); for `allocated=True` but a component `passed=False`; for `components=()`; for blank `spec_hash`; for missing `FROZEN_COMPONENT_NAMES`/T2. MUST-FAIL: direct `AllocationGrant(...)` without `_MINT` raises. **MUST-PASS (capability, no allocation):** a decomposed `GateDecision(allocated=True, all components passed incl T2)` mints. REPLAY: a grant for spec A cannot drive a submit for spec B (`submit_allocated` asserts + aborts).
- **C10 — sizing.** MUST-PASS (the expected null): property test over random finite `price>1` → ALWAYS `NoTrade` at $1 cap (`floor==0`). FAIL-CLOSED: NaN/inf/≤0 price → NoTrade; stale quote (age>max) → NoTrade; equity<floor → NoTrade; budget≤0 → NoTrade. **MUST-FAIL teeth:** an understated `est_position_value_usd` with real `qty×price` above the per-trade cap → REJECT (never round-to-0-and-submit). When a `Sized` occurs it satisfies all three caps AND is re-accepted by `evaluate_pre_submit`.
- **C11 — submit mode + is_live invariant.** No `SUBMIT_GO` → RECORD_ONLY (records journal + claims idempotency, submits nothing). Correct phrase + matching `spec_hash` → LIVE_SUBMIT; wrong phrase / missing spec line / mismatched spec_hash → RECORD_ONLY (fail-closed). Single-use: consumed after one submit, second pass → RECORD_ONLY. `submit_allocated` asserts `is_live(cfg.live_mode) is False` on EVERY path; `PaperBroker.paper is True`; grep-test forbids `paper=False` literal across executor.
- **C12 — idempotency claim-then-submit + reconcile_loop.** First call claims coid + calls `broker.submit`; SECOND identical call → rejected at idempotency gate, `broker.submit` NOT called (assert call count). Crash-sim (claim recorded, no submit) → retry rejected (at-most-once). Race: two concurrent passes, exactly one `remember` True; loser `failed_gate='idempotency'`. Reconcile: local==broker→OK; 3-position drift >600s → RED → `auto_flat` (cancel_all+close_all) + `hard_stop` + `page_operator(RED)`; ORANGE → trip, no auto-flat; a broker-fetch/state-write OSError does not crash the loop. Startup reconciliation queries `get_order_by_client_id` for orphaned claims.
- **C13 — run_loop_pass composition + PHI1.** Ordering: a pass with recon RED performs auto-flat and submits ZERO even if an `AllocationGrant` is present (auto_flat precedes submit). A TRIPPED kill_switch still runs recon+guards+abandonment (a RED guard during TRIPPED → HARD_STOPPED). PHI1 teeth: leak_lint/AST scan over `executor`+`guards` finds NO anthropic/LLM/agent import; `loop.py`/`submit.py`/`sizing.py` import no agent module. Fail-closed: an injected adapter raising in steps 2–5 increments `consecutive_scheduler_errors`, returns without submitting, never leaves ARMED+submit reachable in the same pass.

**Gate**

- **C14 — make inc6 + the end-to-end null (ADR §0).** INTEGRATION: drive all 4 toys through `evaluate_family` with T2 CAPABLE (real artifact wired) → `allocated=False` for ALL FOUR → `from_decision` raises for all → ZERO grants → ZERO `OrderIntent`s → ZERO orders submitted; assert the failing reasons are STATISTICAL (DSR/PSR/PBO/SPA/WF), proving T2 is no longer the sole blocker yet zero orders result. `make inc6` mirrors inc5 + leak_lint over `guards`+`executor` + the §6 adversarial must-fail steps as first-class gate steps; ruff/black/mypy --strict green; coverage ≥85. LIVE (`@pytest.mark.live`, excluded): real `GET /v3/reference/tickers?ticker=SIVB&date=2023-02-15` asserts `active:true/delisted_utc:null` (PIT reconstruction) and `date=2023-09-01` asserts `count 0` (interval closed) — pins the ground-truth checkpoint; plus a real alpaca paper submit + close-all smoke.

---

## 6. SKEPTIC CRITICAL/HIGH ATTACKS → EXACT STRUCTURAL MITIGATION

| # | Sev | Attack | Structural mitigation (where) | Teeth test |
|---|---|---|---|---|
| 1 | **CRIT** | Type-confusion / hand-built `GateDecision(allocated=True, components=())` mints a grant. | `AllocationGrant.from_decision` re-runs `bool(components) and all(c.passed)` AND requires `FROZEN_COMPONENT_NAMES ⊆ names` AND `T2_survivorship` passed AND non-blank `spec_hash`; constructor token-guarded; grep-ban `GateDecision(allocated=True)` outside `combine_member_verdict`. (§4.2) | C9 |
| 2 | **CRIT** | Flipping global `_PIT_VERIFIER_WIRED` falls back to self-attested survivorship flags (FC-1). | DELETE the bool-only path; `t2_survivorship` requires `(BacktestResult, ProvenanceBinding, MembershipArtifact)`, binds by hash + coverage-over-window + no-missing; self-attested bools AND-ed as advisory only. (§2.4) | C4 (both flags False + no bound artifact → KILL) |
| 3 | HIGH | Grant requirement not in the unskippable chain (bypass-by-omission). | `submit_allocated`'s first positional param is `grant: AllocationGrant`, non-defaulted → omission is `TypeError`; it is gate 0 before kill_switch; `PaperBroker.submit` has exactly one caller and that caller requires a grant. (§4.2/§4.5) | C9 handoff + mypy --strict |
| 4 | HIGH | Polygon rate-limit/network fail-OPEN at gate time. | Membership resolved OFFLINE into a sealed artifact; gate makes NO network call; 429/timeout/non-200/empty/wrong-tier raise `PolygonProvenanceError` ABORTING construction → no hash → T2 fails closed; abort-never-partial. (§2.5) | C3 |
| 5 | HIGH | Sizing exceeds caps via self-reported `est_position_value_usd`. | `est_position_value_usd` consistent with `qty × FRESH HARD quote` (M17 staleness on the sizing price); 1-share notional over per_trade → REJECT (never round to 0-and-submit); `evaluate_pre_submit` re-checks independently. (§4.3) | C10 (understated notional above cap → REJECT) |
| 6 | HIGH | Order submitted AFTER an abandonment/RED via ordering/stale-snapshot race. | recon+guards+§8 run SYNCHRONOUSLY at the TOP of every pass, before `evaluate_pre_submit` reads kill_switch; auto_flat/abandonment strictly precede any submit; bound `AccountSnapshot` freshness → stale = KILL; unfed §8 counters are safe no-ops that cannot mask a trip. (§3.4/§4.5) | C13 ordering + fail-closed |
| 7 | HIGH | RED guard's protective action stalls behind a 60-min ack ladder / wedged scheduler. | RED `hard_stop`+`auto_flat` at t=0 (§3.2), NOT after the ladder; the 15/30/60 ladder is NOTIFICATION-only on an INDEPENDENT watchdog; RED-page re-raise caught at loop boundary so it cannot abort the issued hard_stop. (§3.2/§3.5) | C7 (page raises → still hard_stops) |
| 8 | HIGH | Idempotency crash window / deterministic-id collision for legit repeated intents. | claim-BEFORE-submit (at-most-once); startup reconcile of claimed-but-unconfirmed via `get_order_by_client_id`; session/bar-timestamp in `client_order_id` identity. (§4.5) | C12 (crash-sim both directions) |
| 9 | HIGH | Stale/forged `MembershipArtifact` reused across a different as_of. | `ProvenanceBinding` (traded_symbols, window, as_of) sourced STRUCTURALLY from the panel; T2 recomputes coverage from `binding` + requires byte-equal hash; reject any traded symbol absent. (§2.3/§2.4) | C4 |
| — | MED (tracked) | Coax a toy to allocate (ADR §0); thresholds tunable; PHI1 import; default-on-ambiguity; GO replay. | Freeze `thresholds.py`/guard constants behind weekly-review (law, not Inc-6 edit); regression test toys STILL ALL KILL after Polygon; leak_lint PHI1 over executor+guards; PIT allowlist (include only on explicit `active:true`); single-use spec-bound GO marker. (§2.5/§2.7/§3.3/§4.4/§6 below) | C13 PHI1; C14 toys-still-KILL |

`make inc6` runs these adversarial must-FAIL cases (forged grant → reject; forged/dropped survivorship → KILL; Polygon 429 → KILL; stale/understated sizing → reject; RED → synchronous hard_stop; toys-after-Polygon → still ALL KILL) as FIRST-CLASS gate steps, not just coverage 85.

---

## 7. OPEN QUESTIONS FOR THE OPERATOR (not the builder)

These are decisions the builder should NOT make unilaterally; defaults are recommended so the build is unblocked, but the operator confirms.

1. **OQ-1 (RESOLVED in-spec, confirm):** Provenance fields go on a SEPARATE frozen `ProvenanceBinding` passed alongside `BacktestResult`, NOT on the @final SEALED Inc-4 `BacktestResult` (avoids an Inc-4 re-seal). **Confirm** this is acceptable vs. an explicit Inc-4 re-seal note. *Recommended: separate binding.*
2. **OQ-2 (operator preference):** The single-use operator-GO marker is `state/SUBMIT_GO`, DISTINCT from the live-mode marker (`state/LIVE_MODE_CONFIRMED`). Confirm "allow real paper submits" must be independent of "go live" (recommended), and the exact authorization phrase `I_AUTHORIZE_ONE_PAPER_ORDER`.
3. **OQ-3 (audit preference):** After one consumed submit, should `state/SUBMIT_GO` be DELETED or ROTATED to `state/SUBMIT_GO.consumed-<coid>` for a forensic trail? *Recommended: rotate (audit trail).*
4. **OQ-4 (first-order policy):** For the very first authorized paper order, MARKET vs marketable-limit (limit at NBBO + small buffer to bound slippage M3/M9)? Sizing currently emits MARKET. *Recommended: marketable-limit with a fresh NBBO quote for the first authorized order; default MARKET acceptable for record-only.* (Moot this run — sizing yields zero shares at $1 caps.)
5. **OQ-5 (Polygon as-of granularity, confirm via LIVE smoke):** T2 closes the interval from a SINGLE as_of query reading `delisted_utc` (1 call/symbol, within 5/min). Confirm `delisted_utc` on the as-of record is reliable for window-end closure; if not, fall back to a 2-point (window_start + window_end) query. The LIVE smoke (C14) pins this; operator confirms acceptable Polygon-budget cost for the small ARCANE candidate set.
6. **OQ-6 (reconciliation scope, recommended):** In a record-only run, reconcile ONLY actually-submitted (LIVE_SUBMIT) orders; record-only journal entries are EXCLUDED from the local position map (avoids phantom drift vs the empty broker). *Recommended: yes.*

---

**This document is the design of record for Increment 6.** Build order: PART A (C1–C4) → PART B (C5–C8) → PART C (C9–C13) → gate (C14), each gated on its §6 CRITICAL/HIGH mitigations. The locked, correct, expected first-submit outcome is **ZERO paper orders**.
