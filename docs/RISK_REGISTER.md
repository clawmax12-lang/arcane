# ARCANE Risk Register

_Source: design-hardening workflow wf_8a9cb363-ea3 — 2026-06-20_

## [CRITICAL] Disk exhaustion bricks the box mid-build (verified 1.2 GiB free, far worse than the 2.8/3.0 GiB briefed). Any unbounded Parquet cache, a stray torch pull, or node_modules can fill the volume and cause a self-inflicted Murphy event.

**Mitigation:** Operator-gated cache prune (uv cache prune + npm cache clean --force reclaims ~38 GB) as a HARD prerequisite before env work; re-read df -h / as the real budget. Hard MAX_CACHE_BYTES + LRU eviction in cache.py so the Parquet cache can never fill the disk. Tier B installed one-at-a-time with df re-check between each. Default torch to CPU index URL.

## [CRITICAL] False discovery / overfit: 10-15 factors x 3-5 strategies is still a multiple-testing surface; Deflated Sharpe and Reality-Check are inflated to the point of passing overfit strategies if n_trials is under-reported.

**Mitigation:** Append-only monotonic trial ledger counting EVERY strategy+param combo ever run, fed to DSR/Reality-Check and surfaced on the dashboard. Gate requires ALL of (>=9/12 AND DSR p<0.05 AND PSR>0.95 AND walk-forward), not a vote. Disqualifying veto tests (conservative live cost model + untouched holdout). Allocator asserts status=='ALLOCATED' as a precondition. Expect at most ~2 survivors by design.

## [CRITICAL] Paper P&L cannot falsify a missing edge; paper fills ignore market impact and adverse selection, so the system can look profitable with zero live edge and the operator chases a mirage (or abandons on noise).

**Mitigation:** Reframe as edge-falsification harness: long-history walk-forward is primary evidence, paper is plumbing only. Require edge to survive a conservative live cost model. Minimum-sample floors so calibration/abandonment never fires on noise. A pre-registered null result is a SUCCESS that stops work.

## [CRITICAL] A single bad edit or bug arms live trading or weakens the safety net (loosened cap, flipped LIVE_MODE, re-armed kill switch by an agent).

**Mitigation:** Dual-control everywhere: floor-of-floors constants.py that YAML cannot loosen; triple-lock LIVE_MODE (code AND config AND interactive CLI marker) with paper=True hardcoded in submit; kill switch re-arm only via interactive CLI, never by LLM/agents; handoff unit test fails CI if either LIVE_MODE flag flips; import-guard test forbids LLM imports in the submit path. mypy --strict + hypothesis + >85% cov + zero TODOs on risk/executor/guards.

## [HIGH] Look-ahead / survivorship leaks silently inflate backtest edge (normalization over full series, restatement backfill, same-bar feature/target alignment, today's-survivors universe).

**Mitigation:** DataLoader.load() and AlphaFactor.compute() are FINAL with the dangerous transforms (PIT filter, rolling-z, shift(1)) baked in so authors cannot bypass them. AST lint bans the 7 leak constructs. Universal prefix-stability property test over the whole factor registry. PIT universe is a first-class loader; with Polygon deferred it runs DEGRADED and forces bias-test T2 to fail rather than false-pass.

## [HIGH] hmmlearn (L6) resolves sdist-only on Python 3.13, triggering a from-source C build that needs Xcode CLT and burns scarce disk/time.

**Mitigation:** Verify hmmlearn cp313 wheel at install time; documented one-line fallback to uv python pin 3.12 (accept ~50 MB download) rather than fighting a compiler. Regime ships deterministic+HMM only (torch deferred), so the blast radius is contained to one dep.

## [HIGH] Disaster-recovery paging is mute: no Discord/Telegram webhook present, so Murphy red-guard alerts (5.2) and reconciliation auto-flat pages have no channel before real paper-submit starts.

**Mitigation:** Make the operator-page sink pluggable with a NoOp/log+console+local-file default so the Red path is fully testable and functional now; operator MUST decide on a paging channel before Increment 5 (first real paper submit). Document that DR paging is degraded until configured.

## [MEDIUM] Node v25.8.2 is non-LTS and ahead of Next.js 14's tested matrix; a Next 14 dashboard build can emit engine/undici/edge-runtime failures, and node_modules (~400-700 MB) competes with heavy ML for scarce disk.

**Mitigation:** For v1 build the dashboard as FastAPI + minimal server-rendered HTML to dodge both the Node/Next mismatch and node_modules disk cost; defer any Next.js to Inc 8/9 post-prune, isolated in a dashboard/ workspace pinned to Node 22 LTS (Volta/.nvmrc) with pnpm via corepack. Dashboard is L15 and never blocks the Python build.

## [MEDIUM] Unsequenced layers stub into plausible fakes the allocator trusts (e.g., a missing executor or gate stubbed as a no-op that silently passes).

**Mitigation:** Build the deterministic executor and bias-gate FIRST; any layer whose dependencies are missing must FAIL LOUD, not stub. Gate each increment behind a mechanical test suite (make incN); do not start increment N+1 with N red. Real paper submit (Inc 5) cannot begin until Inc 1-4 are green.

## [MEDIUM] Effort/expectation mismatch: treating the spec's '6-12h one-shot' as the acceptance frame leads to shipping something untested or declaring false victory.

**Mitigation:** Re-anchor on ~55-90h build for Inc 1-8 plus a hard 14-day paper soak; Inc 9 out of scope for v1. Sequence value early: after Inc 1-2 the operator has a tested safety spine + live Alpaca data as demonstrable progress.

## Increment 1 — immediate next actions

1. STEP 0 (operator-gated, deletions): reclaim disk before any env work. Run `uv cache prune` (~27 GB), `npm cache clean --force` (~11 GB), optionally `brew cleanup -s`. Do NOT delete ms-playwright cache if Playwright E2E is planned. Re-run `df -h /` and treat the post-prune free number as the real budget. (Real free is currently 1.2 GiB.)

2. STEP 1: Pin the runtime. `uv init` is NOT used; create `.python-version` = 3.13.12 via `uv python pin 3.13.12` (zero download — already on disk). Author `pyproject.toml` with `requires-python = '>=3.13,<3.14'`, Tier A deps in [project.dependencies], and ml/vector/rag dependency-groups. `uv sync`; commit `uv.lock`.

3. STEP 2: Scaffold the repo and the single command surface. Create `src/trading/`, `config/`, `state/` (gitignored), `tests/`, and a `Makefile` with targets: setup, clean-cache, db-up (deferred/documented), lint (ruff+black --check), typecheck (mypy --strict on risk/executor/guards), test (pytest --cov fail-under=70), test-prop (hypothesis), check (chained), and per-increment gates make inc1..inc9. Wire LIVE_MODE=false into config/risk.yaml AND a grep-able code constant now.

4. STEP 3: Build the deterministic safety spine FIRST (Increment 1), TDD, in this order: (a) risk/constants.py floor-of-floors + risk/schema.py + risk/loader.py (fail-closed, frozen Pydantic, invariants I1-I8); (b) risk/caps.py PURE cap functions; (c) executor/live_mode.py triple-lock gate + handoff truth-table test; (d) risk/kill_switch.py atomic-persisted state machine + crash-injection test; (e) executor/intent.py OrderIntent + executor/invariants.py ordered fail-closed chain; (f) executor/idempotency.py deterministic client_order_id + SQLite dedup; (g) executor/reconciler.py 60s drift->auto-flat+HARD_STOP with injected clock; (h) risk/mistake_check.py pure M1-M20 matcher + import-guard test (no LLM import); (i) executor/broker_paper.py with paper=True hardcoded; (j) a NO-OP paper executor that validates intents but submits nothing yet.

5. STEP 4: Build config loaders with graceful degradation for the verified env: required keys (Alpaca APCA_*, ANTHROPIC_API_KEY) fail-fast if absent; optional keys (Polygon/FRED/Discord/GitHub) must NOT hard-fail — degrade per spec F1. Make the operator-page sink pluggable (NoOp/log/console/local-file default) so the reconciler Red path is testable before any webhook exists.

6. STEP 5: Wire the harden the §4.2 sanitizer as a standalone, security-critical, tested unit (NFKC + zero-width/bidi strip + base64/hex neutralize + non-English/Swedish corpus + HTML/markdown strip; idempotency property test sanitize(sanitize(x))==sanitize(x); fail-closed drop-on-exception). It is the M13 defense and is needed before any TEXTUAL source enters in Increment 2.

7. STEP 6: Run the Increment 1 gate (make inc1): ruff+black clean; mypy --strict green on risk/executor/guards; pytest >85% on the spine; hypothesis proves caps can never be exceeded and LIVE_MODE=false blocks every submit path; each abandonment trigger fires at its exact threshold ($30 total loss, $20 equity floor, 5 consecutive errors); grep proves zero TODO/FIXME in risk/executor/guards; LIVE_MODE=false verified in BOTH config and code. Do not begin Increment 2 (Alpaca data spine) until this gate is green.

## Open decisions for operator

- APPROVE THE CACHE PRUNE (blocking): `uv cache prune` + `npm cache clean --force` are deletions and require your go-ahead. They reclaim ~38 GB of project-independent cache; without them the build cannot proceed on 1.2 GiB free. Confirm it is safe to also clear ~/Library/Caches/Google (1.8G) and Homebrew (724M); keep ms-playwright if you want Playwright E2E.

- PAGING CHANNEL (blocking before Increment 5 / first real paper submit): choose Discord webhook, Telegram, or SMS for Murphy red-guard and reconciliation auto-flat paging. Until configured, disaster-recovery paging degrades to local-file + console only — acceptable for Inc 1-4, NOT acceptable once orders flow. Provide DISCORD_WEBHOOK_URL (or equivalent) when ready.

- DASHBOARD STACK: confirm v1 dashboard is FastAPI + server-rendered HTML (recommended — dodges Node v25/Next 14 mismatch and ~400-700 MB node_modules) versus Next.js 15 on pinned Node 22 LTS deferred to Inc 8/9 post-prune. Dashboard is L15 and never blocks the Python build either way.

- DEFERRED CREDENTIALS: confirm you accept graceful degradation (Alpaca-only data, no Macro/FRED agent, no Polygon survivorship map -> bias-test T2 runs DEGRADED/fail-closed) until you decide to add Polygon / FRED / GitHub tokens. None are on the Increment 1-7 critical path.

- SUCCESS DEFINITION SIGN-OFF: confirm you accept the reframe that ARCANE is an edge-falsification harness and that a pre-registered NULL result (no edge survives costs + the gate) is a project SUCCESS that stops work — not a failure. This governs the whole build and the gate's veto tests.

- SCOPE & TIMELINE: confirm acceptance of ~55-90h build for Increments 1-8 plus a mandatory 14-day paper soak (3-5 week calendar), with Increment 9 (torch/faiss/chromadb, 100 factors, full data lake, RAG) explicitly OUT of scope for v1. Reject the '6-12h one-shot' frame.

- POSTGRES TIMING: confirm Postgres 18 stays OFF the critical path (DuckDB+SQLite+Parquet for Inc 1-7) and is a documented Inc-9 upgrade (start service + brew install pgvector). Flag now if you specifically want the L13.5 Postgres jsonb dossier earlier.

- HMMLEARN FALLBACK PRE-AUTH: pre-authorize the documented fallback to `uv python pin 3.12` (one ~50 MB download) IF hmmlearn resolves sdist-only on 3.13 at install time, so the build is not blocked waiting on a decision.
