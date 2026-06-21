# ADR-001: ARCANE Foundation — Runtime, Data/DB Stack, Dependency Tiering, Safety Spine, Abstraction Contracts, Bias-Gate, and Paper-Only Posture

**Status:** Accepted (binds Increment 1)
**Date:** 2026-06-20
**Context root:** `/Users/maxagent/Trade` (greenfield: only `CLAUDE.md`, `.env`, `.env.example`, `.gitignore`)
**Binding authority:** `CLAUDE.md` v2 axioms (PHI1 = LLM never in submit path), §4.3 (only HARD/STRUCTURED data triggers orders), §5/§6/§7 (Murphy guards / never-do), §8 (abandonment triggers).

---

## 0. The Reframe That Governs Everything (resolves SPEC-ADVERSARY conflict)

The five analyses split on what ARCANE *is for*. The SPEC-ADVERSARY (CRO) verdict is correct and is **adopted as the project's success definition**, overriding the original "force profit" framing.

**DECISION:** ARCANE is an **edge-falsification harness**, not a profit machine. A pre-registered null result (no edge survives costs + the bias gate) is a **project success that stops work**, not a failure. Paper P&L grades its own homework and cannot falsify a missing edge; therefore the **long-history walk-forward backtest is primary evidence** and the $50 / paper period is **plumbing verification only**.

**Rationale:** Alpha decays to zero after costs; paper fills ignore market impact and adverse selection. Treating paper profit as proof is the single most expensive self-deception available to this system.

**Rejected alternative:** "Build it, run paper, if it makes money go live." Rejected because paper profit is non-falsifying and the original framing manufactures false confidence. The 14-day clean-paper requirement (§7) is retained as a *plumbing* gate, not an *edge* gate.

---

## 1. Runtime Pin (resolves TOOLCHAIN vs system-default conflict)

**DECISION:** Pin **CPython 3.13.12** via `uv python pin 3.13.12`; set `requires-python = ">=3.13,<3.14"`.

- **Verified:** 3.13.12 is already on disk (`/opt/homebrew/Cellar/python@3.13`) → **zero download cost**. System default is **3.14.4** (sci-wheel lag). 3.12.13 / 3.11.15 / 3.15.0a7 are download-only (each ~45–55 MB of a disk with **1.2 GiB free** — verified, worse than briefed).
- **Escape hatch:** if `hmmlearn` (the L6 dep most likely to lag a new cpython) resolves **sdist-only** on 3.13 at install time (forcing a C build via Xcode CLT), fall back to `uv python pin 3.12` and accept the ~50 MB download rather than fight a compiler.
- Never inherit the system interpreter. `.python-version` + `uv.lock` (committed, hash-verified) make the pin reproducible without Docker.

**Rejected alternatives:** 3.14.4 (default but unreliable scientific wheels); 3.12 first (marginal safety for a real disk cost we cannot afford up front).

---

## 2. Disk Posture (the load-bearing correction)

**VERIFIED THIS SESSION:** real free space on `/` is **1.2 GiB** (91% used), *tighter than any analysis assumed*. BUT reclaimable, project-independent cache is enormous: `~/.cache/uv/archive-v0` = **27 GB**, `~/.npm` = **11 GB**, `~/Library/Caches` ≈ 4 GB (Google 1.8G, ms-playwright 1.0G, Homebrew 724M). There is **no `.venv` and no `pyproject.toml`** yet, so pruning is safe.

**DECISION:** The disk blocker is an artifact of stale cache, not a hardware ceiling. **Operator-gated cache prune is a hard prerequisite to any env work** (it is a deletion, so it must be operator-approved). Post-prune `df -h /` is the real budget. Keep `make clean-cache` (`uv cache prune`) permanently. Do **not** delete `~/Library/Caches/ms-playwright` if the dashboard E2E plan uses Playwright (it will just re-download).

---

## 3. Data / DB Stack (resolves Postgres-vs-DuckDB + Redis conflict)

**VERIFIED:** Postgres 18.3 is initdb'd at `/opt/homebrew/var/postgresql@18` but **not running** (`pg_isready` → no response). TimescaleDB **absent**. Redis and Docker **absent**.

**DECISION (storage):**
- **Analytical lake + backtests (L1/L4):** **DuckDB + content-addressed Parquet**, in-process, reads Parquet in place — the right engine for vectorized walk-forward. This is the persistence backbone through Increment 7 and removes a running-service dependency from the critical path.
- **State / dossier / ledger / idempotency (L8/L9/L13.5):** **SQLite (stdlib)** as the default, fail-closed, restart-safe store. Postgres 18 is the **documented future upgrade** (start service + add `pgvector` via `brew install pgvector`) recorded for Increment 9; it is **not** on the Inc-1 critical path.
- **Cache / message bus:** **No Redis.** The file-based `state/` JSON bus (CLAUDE.md §1.2, one-writer rule) **is** the message bus; an in-process TTL/LRU cache (or `diskcache`) covers caching; Postgres LISTEN/NOTIFY is the deferred pub/sub path if ever needed.
- **Graceful degradation (spec F1):** `DATABASE_URL` unreachable → SQLite file; Parquet engine missing → DuckDB in-memory. A `docker-compose.yml` (postgres+timescaledb+redis) is written as **documented dead code only**, marked "requires Docker — not present this session."

**Rationale:** Starting a Postgres service and building extensions burns scarce disk and adds a failure mode for a single-operator, single-process, $50 system that DuckDB+SQLite serve fully today.

**Rejected alternative:** native Postgres now (TOOLCHAIN Option A). Deferred, not rejected — correct destination, wrong increment.

---

## 4. Dependency Tiering (TOOLCHAIN + DATA-ABSTRACTIONS, reconciled)

Expressed as `uv` dependency-groups in `pyproject.toml`. Default torch to the **CPU index URL** always (no CUDA on arm64 mac).

- **Tier A — INSTALL NOW (~450–550 MB installed, cp313 arm64 wheels, no compilation):** pydantic v2, pyyaml, structlog, pytest(+cov, hypothesis), alpaca-py, numpy, pandas, **polars**, scipy, scikit-learn, statsmodels, hmmlearn, APScheduler, httpx, duckdb, pyarrow, ruff, black, mypy. **Covers L0–L11.** (The deterministic safety core needs only a subset: pydantic, pyyaml, hypothesis, pytest, alpaca-py — and has **zero** heavy deps.)
- **Tier B — GATED behind the prune, install ONE at a time, re-check `df` between each:** torch CPU (`--index-url .../whl/cpu`, ~600 MB installed; L6 LSTM-AE, L11 EWC) — **but DEFERRED per §6 complexity budget**; faiss-cpu (or skip for DuckDB VSS / numpy cosine at $50 scale); chromadb+onnxruntime (heavy relative to benefit — prefer DuckDB-native).
- **Tier LATER (needs freed disk + a decision):** full Parquet history lake, 100 factors materialized, Next.js `node_modules` (~400–700 MB), event-driven backtest sweeps.

**DECISION:** Heavy ML (torch/faiss/chromadb) lives behind `RegimeModel` and `VectorStore` interfaces with light fallbacks (deterministic+HMM regime; DuckDB/numpy cosine), so the system is fully functional now and the ML tier is a drop-in later with **no re-architecture**.

---

## 5. Complexity Budget & Anti-Overfitting Posture (resolves the core ADVERSARY conflict)

The original spec wants regime + allocator + learning + causal + deep-learning layers. The CRO calls this a false-discovery factory. **The CRO wins on a budget basis.**

**DECISION:**
- **Defer entirely:** causal-inference layer (unsound on confounded market data for trade decisions), deep-learning regime (torch LSTM-AE), online learning/self-distillation. Ship **regime as deterministic + Markov/HMM only**.
- **Start small:** **10–15 factors, not 100; 3–5 strategies, not 20.** Expect **at most ~2 survivors** of the gate, by design.
- **Trial accounting is mandatory:** maintain a **monotonic, append-only trial ledger** (`n_trials` = cumulative count of *every* strategy AND parameter combo ever evaluated) in the strategy registry, surfaced on the dashboard. Deflated Sharpe / Reality-Check are meaningless if trials are under-counted — that is the direct M18 overfit vector.

---

## 6. Safety Spine Design Summary (SAFETY-SPINE, adopted verbatim in intent)

The deterministic core (`src/trading/risk`, `src/trading/executor`) is built **FIRST**, before the data lake. Every gate is fail-closed; the kill-switch and LIVE_MODE gate are **dual-control** (config + code) so no single edit arms live trading. PHI1 is structurally enforced: no LLM import anywhere in the submit path.

1. **`risk.yaml` schema (floor-of-floors):** operator-tunable caps in YAML, but hardcoded `constants.py` floors (`EQUITY_FLOOR_USD=20.0`, `TOTAL_LOSS_USD=30.0`) that YAML **cannot loosen**. Frozen Pydantic v2; fail-closed on any validation error → executor refuses all orders.
2. **Kill switch:** persisted state machine `ARMED → TRIPPED → HARD_STOPPED`, atomic write (temp+fsync+`os.replace`), restart-safe, monotonic toward safety. Re-arm only via interactive CLI authority; **LLM/agents can never re-arm** (§7). Corrupt/unreadable state → treated as TRIPPED.
3. **LIVE_MODE gate (triple lock):** `LIVE_MODE_CODE_DEFAULT=False` (code constant, grep-able) **AND** `live_mode: false` (config) **AND** an interactive two-step CLI confirm marker. `is_live()` is True only for `(T,T,T)`; all 7 other combinations → paper. Alpaca client `paper=True` is **hardcoded** in the L9 submit path regardless. A handoff unit test asserts both flags false and fails CI if either flips.
4. **OrderIntent + pre-submit invariant chain:** frozen Pydantic model is the *only* thing the executor accepts; an ordered, fail-closed gate chain (schema → kill-switch → live-mode → data-freshness (M17) → per-trade cap → daily caps → equity floor → total-loss abandon → concentration → idempotency → mistake-check). First failure rejects; nothing reaches the broker on any exception.
5. **Idempotency keys (M10):** deterministic `client_order_id` from intent fields (not wall-clock), atomic check-and-insert in SQLite/Postgres unique constraint before the broker call → at-most-once submit, crash-safe across restarts; broker also receives the id as second-line dedup.
6. **60s reconciliation loop (G3/M11/§8.4):** broker is authoritative; drift timer persists across restarts (from first-seen timestamp). Graduated response Yellow→Orange→Red; **Red (drift > 2 positions for > 600s) ⇒ deterministic auto-flat + HARD_STOP + page operator**. NTP drift > 1s (G6) halts the loop. Reconciliation runs even when TRIPPED.
7. **Pre-trade mistake-check (M1–M20):** deterministic, pure fingerprint matcher consulting *cached* patterns (no live LLM in hot path); expired patterns (90-day) ignored; fail-closed on corrupt patterns file (block, never silent-pass); only HARD/STRUCTURED fields gate. An import-guard test forbids any anthropic/LLM client import in this module — permanently.

**Quality bars (bulletproof set):** mypy `--strict` scoped to `risk/`, `executor/`, `guards/`; hypothesis property tests on all risk/sizing math; **>85% cov** on the spine (above the 70% floor); zero TODO/FIXME in those three packages.

---

## 7. Abstraction Contracts (DATA-ABSTRACTIONS, adopted)

- **`DataLoader.load()` is FINAL** (subclasses implement only `_fetch`): bakes in content-addressed Parquet cache, schema validation, exchange-calendar tz/RTH alignment, NaN/monotonicity quality gate, and the **PIT leak guard** (`ingest_ts <= as_of.ts`). Restated sources (FRED, fundamentals) must declare `requires_pit_ingest_ts=True` or the source is refused. **Sanitization is enforced at the loader boundary**, not at the agent: TEXTUAL-reliability sources return only a `sanitized_text` column + a `raw_text_ref` pointer; the §4.2 regex is hardened (NFKC normalize, strip zero-width/bidi, neutralize base64/hex blobs, non-English corpus incl. Swedish, strip HTML comments/markdown). Reliability tags travel end-to-end; **only HARD/STRUCTURED can reach a runtime gate (§4.3)** — enforced at the type level so a TEXTUAL/DERIVED value is a mypy error if passed as a gate input.
- **`AlphaFactor.compute()` is FINAL:** authors write only `_raw`; the base owns rolling-z (strictly trailing), cap [-3,3], and a mandatory `shift(1)`. Seven leak surfaces (full-series normalization, centered windows, resample/label, restatement, target/feature alignment, survivorship, bfill) are banned via AST lint. A **universal prefix-stability property test** (`compute(df[:k]) == compute(df[:k+1])[:k]`) runs over the whole registry — failing it *is* a look-ahead leak by construction.
- **Strategy-as-composition:** frozen, hashable `StrategySpec` (YAML) can reference only registered `factor_id`s, regime labels, and z-crossings — **structurally eliminating hand-coded thresholds** (no field exists to write "RSI<30"). `spec_hash` binds every backtest/gate artifact to the exact config; any weight change → new hash → forced re-gate.
- **PIT universe + survivorship** is a first-class loader feeding both factors and bias-test T2; with Polygon deferred, it runs **DEGRADED** (stamps `survivorship_unverified=True`, T2 returns `passed=False` with reason rather than a false pass — fail-closed).
- **Shared Registry** (sources/factors/strategies) runs `validate_all()` at startup: unique ids, resolvable deps, and the **silent-mutation detector** (an ALLOCATED strategy whose stored `spec_hash` ≠ current → hard fail).

---

## 8. The Anti-Overfitting Bias-Gate (resolves "9/12 vote is meaningless" conflict)

The CRO is right that "9 of 12 is a meaningless vote." **DECISION:** the gate is a deterministic `CANDIDATE → ALLOCATED` state machine requiring **ALL of** (not a vote):

- **≥ 9 / 12 bias tests pass** (look-ahead reproducibility, survivorship, White Reality Check / Hansen SPA, Bonferroni + BH-FDR, curve-fit perturbation, 2× and 3× cost stress, regime split, time split, calendar split, adversarial windows 2018/2020/2022, block-bootstrap Sharpe CI), **AND**
- **Deflated Sharpe** > 0 with p < 0.05 using the **full** `n_trials` from the ledger, **AND**
- **PSR > 0.95**, **AND**
- **walk-forward 12/3/3** OOS Sharpe > 0 with ≥ 60% folds positive.

Plus **disqualifying veto tests** (any one fails ⇒ reject regardless of the rest): edge must survive a **conservative live cost model** (market impact + adverse selection, since paper fills don't model these), and an **untouched holdout** must never be examined until final sign-off. The allocator calls `assert registry.status(id, spec_hash)=='ALLOCATED'` as a **precondition** — no LLM and no bug can route capital to an un-gated or silently-mutated strategy. Post-deploy, the gate re-runs on schedule and auto-PAUSEs (§3.2 / abandonment trigger 6) any strategy whose live DSR degrades.

**Minimum-sample floors (CRO):** below a trade-count floor, ratios are noise — the calibration/abandonment trigger must **not** fire on noise alone, and small samples cannot promote CANDIDATE → ALLOCATED.

---

## 9. Paper-Only / LIVE_MODE Posture (handoff invariant)

`LIVE_MODE=false` asserted in **both** `config/risk.yaml` **and** a grep-able code constant; a startup assertion requires both to agree, and a unit test fails if either flips. Alpaca `paper=True` is hardcoded in the L9 submit path independent of LIVE_MODE. Going live is forbidden before **14 days clean paper** (§7) — and per §0, paper is plumbing evidence, not edge evidence. Discord/Telegram paging is **safety-relevant** (§5.2 red-guard paging has no channel without it) and must degrade to local-file + console until a webhook exists; the operator must understand disaster-recovery paging is degraded until then.

---

## 10. Effort Reframe (ROADMAP, adopted)

The spec's "6–12h one-shot" is **rejected** as the acceptance frame — it contradicts CLAUDE.md §7's own 14-day clean-paper requirement and undercounts the test code for the bulletproof set. Honest effort for Increments 1–8 is **~55–90 focused build+test hours**, then a **mandatory 14-day paper soak** — a 3–5 week calendar to a trustworthy paper system. Increment 9 (heavy ML / full lake / 100 factors / RAG) is explicitly out of scope for v1 and may never be reached in the $50 experiment — which is fine.