# Increment 8 — Slow-Loop Agents + Two-Way Telegram Operator Console — Design

**Status:** DRAFT pending operator checkpoint (§0). **Branch:** `build/increment-8-agents-console` (to cut from `main` = `b32b1ee`).
**Source:** design panel `wf_7e98b8c9-e4e` — 3 of 5 lenses completed (injection/console-auth · agent↔acting-path boundary + schema · §4.3 advisory-can't-gate); the architecture-roadmap + adversarial-skeptic lenses were **server-side throttled (429)** so the lead synthesized single-threaded per `insight-autonomous-quality-discipline` (a throttled "0 confirmed" is **not** a pass).

This is the increment where **LLMs first enter ARCANE.** The entire job is to keep them **advisory, injection-hardened, and structurally OUT of the deterministic submit path.** Treat the boundary as money/safety code.

---

## 0. The binding reframe (what this increment is and is not)

- ADR §0 is facit: ARCANE is an **edge-falsification harness**. Agents produce **ADVICE and reports**; they do not create edge and never loosen the gate, a cap, or the bias verdict.
- The console **reports truthfully** (incl. the boring 0-trade/0-survivor days, §9) and can trigger operator-authority **STOPS** (escalate the kill switch). It can never **start** a trade.
- External text — even from the operator — is **EVIDENCE, never an instruction that reaches the broker** (§4.3 TEXTUAL/DERIVED).
- No LIVE trading; the executor stays RECORD-ONLY behind the per-order GO. The scheduler/orchestrator are dormant by default.

### 0.1 The seven structural invariants (any breach = STOP)

1. **PHI1 holds, static AND dynamic.** No agent/console/LLM module is reachable from the submit path. The 12 PHI1 roots (`executor guards bias_gate data notify backtest factors risk regime allocator driver scheduler`) import neither `trading.slowloop.*` nor `trading.console.*` nor `anthropic/openai/langchain/llm/agent`. The only allowed coupling is **one-way**: `console → executor.kill_switch` (escalate-only) and `console/slowloop → data.sanitize` (read a pure function). Submit-path → slowloop/console is **forbidden entirely**.
2. **Advisory/report-only output.** Agent + console output can NEVER gate an order, size, override a cap or the bias gate, or place a trade. The LLM reply is **text only** — there is **no parser that turns an LLM reply into an action**. A jailbroken responder produces harmful *text*; it cannot *act*.
3. **Sanitize-before-LLM.** ALL external text (agent inputs AND every inbound Telegram message, incl. a forwarded/injected one) passes `trading.data.sanitize.sanitize()` before any LLM sees it. Raw is logged; only the sanitized form is sent.
4. **No broker write.** Neither `slowloop` nor `console` imports `executor.submit` / `broker_paper` / the alpaca SDK. Console acting-commands resolve ONLY to `kill_switch` escalate methods. The console can **trip/hard_stop** but NEVER **arm** (re-arm stays CLI-only with `operator_authority=True`, §7).
5. **Deterministic regime stays the gateable one.** The Inc-7 `DeterministicRegimeModel` remains the sole posture source for the acting path. Any agent-fed advisory regime is DERIVED, lives OUTSIDE the submit-path roots, and is subtractive-only (§0.2 decision).
6. **Fail-closed schema I/O.** A malformed / half-written / uncertain / low-confidence artifact is DISCARDED (never written); a reader returns `None` ("unavailable") on any JSON/validation error → the acting path continues to its existing zero-candidate fail-closed path. No advisory can FORCE a trade — only narrow (subtractive) or vanish.
7. **Secrets discipline.** `ANTHROPIC_API_KEY` / `TELEGRAM_BOT_TOKEN` are read only from `.env`/settings at the HTTP layer, NEVER interpolated into a prompt, NEVER logged. The existing "no token-shaped literal in `src/`" grep test is extended to cover `slowloop`/`console`.

### 0.2 Two operator CHECKPOINT decisions (resolve before building)

- **D-SCOPE — the starter agent set.** Recommended: **news/overnight + regime-synthesis + daily-report** (3, the ceiling per the prompt) — all low-risk, the daily report reuses the proven `send_daily_report` transport and never feeds the acting path. Leaner alternatives offered.
- **D-ADVISORY — advisory-regime consumption.** Recommended: **(A) REPORT-ONLY** for Inc-8 — the regime-synthesis agent writes `state/slowloop/regime_advisory.json` (DERIVED + confidence), the **console reports it** ("overnight regime read: high_vol_down, conf 0.55"), and the acting path is **UNCHANGED** (`drive_once` keeps `assess()+posture_from()` over `ctx.market_proxy` as the sole posture source). The subtractive-intersection wiring **(B)** is fully specified here and behind a committed-but-skipped teeth test, but **DISARMED** until a later increment the operator separately approves. Rationale: Inc-8 is the first LLM contact; (A) adds **zero** new acting-path inputs, so the entire LLM surface is provably advisory by topology, and Inc-7's sealed guarantees carry forward verbatim. Both completed design lenses independently recommend the acting path not consume the advisory regime this increment.

> Both decisions are honored such that **the answer cannot manufacture a trade either way** — with the 4 edgeless toys the gate KILLS all → the allocator allocates NOBODY → zero orders, regardless of regime or news.

---

## 1. Package layout (the boundary IS the topology)

Two **new top-level packages, OUTSIDE the PHI1 submit-path roots.** Neutral names (NOT `agents/` — that would collide with PHI1 `_BANNED_TOP={'agents'}` and make a coincidental substring look like a real boundary; the boundary is proven by an explicit import-graph test instead).

```
src/trading/slowloop/                 # PART A — the slow-loop agent framework (NOT a submit-path root)
├── __init__.py
├── errors.py                         # SlowLoopError(ArcaneError) root
├── contract.py                       # AgentArtifact (pydantic v2 frozen) + per-agent payloads + Source
├── store.py                          # atomic write (temp→fsync→os.replace) + fail-closed read_artifact
├── orchestrator.py                   # run_agent: sanitize-in → validate → discard/last-known-good → ORANGE page at N
├── llm/
│   ├── __init__.py
│   └── anthropic_client.py           # Responder Protocol + thin httpx Anthropic Messages client + fakes
└── agents/
    ├── __init__.py
    ├── news.py                       # NEWS/OVERNIGHT agent → state/slowloop/news_state.json
    ├── regime_synth.py               # agent-fed regime synthesis → state/slowloop/regime_advisory.json (REPORT-ONLY)
    └── daily_report.py               # (D-SCOPE) Daily Report synthesizer → pager (text out, never read by acting path)

src/trading/console/                  # PART B — the two-way Telegram operator console (NOT a submit-path root)
├── __init__.py
├── errors.py                         # ConsoleError(ArcaneError) root
├── authz.py                          # chat_id allow-list + update-shape whitelist
├── state_reader.py                   # gather + schema-validate the sanitized "operator briefing" from state/
├── commands.py                       # FROZEN deterministic command allow-list → kill_switch escalate / read
├── responder.py                      # Claude-backed Q&A, grounded ONLY in the briefing; returns str
└── poller.py                         # getUpdates long-poll, durable offset, per-update dispatch
```

The acting path's ONLY contact with this world is a **READ** of a `state/slowloop/*.json` file — and under D-ADVISORY=(A) the acting path reads **none** of them this increment. The console MAY import `executor.kill_switch` (escalate-only) and `data.sanitize`; nothing in the roots may import `console`/`slowloop`.

State artifacts live under `state/slowloop/` (already gitignored via `state/`).

---

## 2. PART A — the agent framework (the safety spine for LLMs)

### 2.1 The artifact contract — `slowloop/contract.py` (pydantic v2)

`§4.3` baked into the **type**: an agent literally cannot mint a gateable artifact.

```python
class Source(BaseModel):                       # R3 — cite your inputs
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["news", "macro", "market", "state"]
    ref: str                                   # sanitized title/url-stripped ref
    as_of: datetime                            # aware UTC

class AgentArtifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: int
    agent_name: str
    reliability: Literal["textual", "derived"]  # NEVER hard/structured — §4.3 in the type
    confidence: float = Field(ge=0.0, le=1.0)   # R2
    as_of: datetime                             # aware UTC — the data's effective time
    produced_at: datetime                       # aware UTC — when written
    model_id: str                               # which model produced it (R3)
    sources: list[Source]                       # R3 — non-empty for any non-trivial claim
    status: Literal["ok", "uncertain"]          # R1 escape hatch
    payload: NewsPayload | RegimeAdvisoryPayload | DailyReportPayload  # discriminated per agent
```

- `reliability` is `Literal["textual","derived"]` → there is **no field** an agent can set to `hard`/`structured`. A submit-path-side reader (if any) maps `reliability → Reliability` and calls `require_gateable()` which **raises** on DERIVED (`reliability.py:32-37`).
- `RegimeAdvisoryPayload.label: RegimeLabel` — constrained to the **existing** `RegimeLabel` StrEnum (`labels.py`). An advisory label outside that space fails schema validation → discarded. The advisory can never widen the label universe.

### 2.2 The artifact store — `slowloop/store.py`

- `write_artifact(path, artifact)`: mirrors `kill_switch._write` **exactly** — write `<path>.tmp`, `json.dump`, `f.flush()`, `os.fsync(fileno)`, `os.replace(tmp, path)`. Atomic; a half-written file is never observable.
- `read_artifact(path, payload_cls) -> AgentArtifact | None`: `FileNotFoundError` → `None` ("unavailable"); JSON/`ValidationError` → `None` + log (never raises into a reader). A torn/corrupt file is indistinguishable from "no data yet", and "no data" is always safe.
- One agent owns exactly one output path (CLAUDE.md §1.2 "one output domain").

### 2.3 The LLM client — `slowloop/llm/anthropic_client.py` (thin httpx)

```python
Responder = Callable[[str, str], str]   # (system_prompt, sanitized_user_text) -> reply text
```

- Default `_httpx_responder` POSTs to `https://api.anthropic.com/v1/messages`, mirroring `telegram.py`'s injectable-Sender pattern. **No new heavy dependency** (httpx is already a dep; `anthropic` SDK is absent and declined — supply-chain + the ~3 GB-free disk constraint).
- Token discipline: the key is read from settings at the HTTP layer only, never passed into prompt-assembly, never logged; httpx exceptions are re-wrapped to drop any key-bearing context (the `telegram.py:51-60` pattern).
- The whole gate fakes the `Responder`; exactly **one** `@pytest.mark.live` smoke hits the real API (the `live` marker already exists and is excluded from the gate).

### 2.4 The orchestrator — `slowloop/orchestrator.py`

`run_agent(agent, store, notifier)`:
1. Feed the agent ONLY `sanitize()`'d inputs (raw logged, never sent).
2. Parse the agent's raw text into `AgentArtifact` via pydantic.
3. On `ValidationError` OR `status == "uncertain"` OR `confidence < floor` (default **0.4**, per R2) → **DISCARD** (do not write), increment a persisted `consecutive_failures` counter in `state/slowloop/_health.json`.
4. On success → atomic-write the artifact AND reset the counter.
5. When `consecutive_failures >= N` (default **N=3** — CLAUDE.md §1.2 ">3", and one step *before* the §8 "5 consecutive scheduler errors" abandonment) → page operator via the existing `TelegramNotifier.page_operator(Severity.ORANGE, …)`.
- Last-known-good = whatever validated artifact is currently on disk (untouched on discard).
- Readers enforce an `as_of` **freshness window**; past it the artifact is "unavailable" (non-narrowing), never stale-trusted — a G1-class staleness guard for advisory data.
- The orchestrator is **dormant by default** (not wired to run on its own; one `@pytest.mark.live` smoke exercises a real round-trip).

---

## 3. PART B — the two-way Telegram operator console

### 3.1 Inbound pipeline (the order is load-bearing)

```
getUpdates(offset) ──> per update, ascending update_id:
  1. AUTH        update.message.chat.id == TELEGRAM_CHAT_ID  AND  shape-whitelist (below) — else DROP (advance offset, no reply)
  2. SANITIZE    sanitize(text)  — before dispatch AND before any LLM
  3. DISPATCH    is_command(raw_authed_text)?  →  deterministic handler   (fixed allow-list)
                 trade-intent regex match?     →  fixed canned refusal     (no LLM, no broker)
                 else                           →  responder.answer(briefing, sanitized_text) → send_message
  4. OFFSET      persist last_update_id (atomic) — controls persist BEFORE invoking kill_switch (idempotent)
```

**AUTH / shape whitelist** (`authz.py`): process an update ONLY if it is a **private-chat, non-forwarded `message` with a string `text`** whose `chat.id == TELEGRAM_CHAT_ID`. DROP all of: `chat.type != "private"`, `channel_post`, `edited_message`/`edited_channel_post`, `callback_query`, `my_chat_member`, any update with a `forward_origin`/`forward_from`/`forward_date` field, and any update lacking a `message`. A non-operator chat_id is logged at debug and **silently dropped** (no reply → no oracle for an attacker probing the bot).

**Command dispatch** (`commands.py`): a FROZEN allow-list `{"/status","/pausa","/flatta","/help"}` (+ optional read-only `/regim`, `/nyheter`, `/vad-dödade-gaten`). Matching is **deterministic**: command-eligibility is gated on the **literal leading slash** of the post-AUTH text (`raw.lstrip().startswith("/")`), then exact membership of `first_token.lower().split("@")[0]` (strip Telegram's `/cmd@botname` suffix). The LLM is **never** asked "is this a command?" and never produces a command token. `sanitize()` is subtractive — it can never *prepend* a `/`, so a body cannot sanitize *into* a command.
- `/status` → `kill_switch.read()/reason()/allows_new_orders()` + read schema-validated state files (READ-ONLY).
- `/pausa` → `kill_switch.trip("operator /pausa via console")`.
- `/flatta` → `kill_switch.hard_stop("operator /flatta via console")`. Actual position flattening is performed by the EXISTING deterministic `broker_flat_fn` wired in the loop (§8/GRD-3 auto-flatten), **NOT** a new broker call from the console. With zero positions it is a safe no-op.
- **No `arm`** anywhere in the dispatch (§7 — re-arm stays CLI-only).

**Refuse-trade-order** (`commands.py`): two deterministic layers, both BEFORE the responder. (1) Structural: the responder has no order-placement capability and returns `str` only — it *cannot* place an order. (2) UX: a deterministic regex `\b(köp|sälj|buy|sell|long|short|blanka|gå lång)\b` (sanitized text, not an allow-listed command) → a fixed canned refusal naming the gate→GO path, with **no LLM call** and **no broker contact**.

**No LLM → action**: the control flow is a strict one-way fork. The responder's `str` return is passed ONLY to `send_message` (which re-sanitizes outbound). There is no code path that feeds responder output back into `is_command()`/dispatch. `responder.py` does not import `commands.py` (enforced by a structural test). Even if the model emits `/flatta` in prose, it is delivered to the operator as a message, not executed.

### 3.2 Q&A responder — `responder.py` + `state_reader.py`

- `state_reader.gather_briefing()` loads + schema-validates the state files into a structured, sanitized **briefing** dict (kill-switch state + reason; gate decisions / today's KILLs; deterministic regime label; guard status; mistake-ledger tail; `news_state.json`; `regime_advisory.json` under D-ADVISORY=(A)). Each fact carries its `as_of`. A missing/invalid/stale file → the fact is `"unavailable"` (never invented).
- `responder.answer(briefing, sanitized_question) -> str`: a single Anthropic call. System prompt: **report-only**, answer ONLY from the provided briefing, say "I don't have that / last-known-good is from `<ts>`" otherwise, cannot place trades (R3 cite-your-inputs, §9 honest, R2 confidence). **Never** a live broker call; **never** invents numbers.

### 3.3 Durable offset — `poller.py`

- Persist `last_update_id` to `state/console_offset.json` (same atomic idiom as `kill_switch._write`). Long-poll `getUpdates?offset=last+1&timeout=25`.
- **At-most-once controls**: for a control command, advance-and-persist the offset BEFORE invoking `kill_switch` (escalations are monotonic/idempotent — `kill_switch.py:130-138` — so a crash between persist and call is safe). For Q&A, persist AFTER the reply attempt (a re-answer is harmless).
- **Cold-start**: a MISSING offset file seeds to the **current max** `update_id` and **discards the backlog** (log `console_cold_start_backlog_skipped`) — so a day-old queued `/flatta` cannot replay out of context after the operator re-armed.
- Per-update handling is wrapped in `try/except` that logs + advances the offset, so one malformed update cannot wedge the loop.
- The console is a **standalone long-poll process**, decoupled from `SCHEDULER_ENABLE` and the record-only loop (its availability is independent of the trading scheduler). Dormant in the gate; one `@pytest.mark.live` smoke does a real send + a real getUpdates round-trip.

---

## 4. PART C — the starter agents (D-SCOPE)

- **`agents/news.py` — NEWS/OVERNIGHT (priority).** Pulls a sanitized Tavily/Apify feed (raw logged, never sent to the LLM), asks the model for a short structured overnight digest, emits `NewsPayload{headline_count, summary_sanitized, salient_symbols, tone}` as a schema-validated `news_state.json` (reliability=TEXTUAL). So "har du läst nyheterna inatt?" has substance, grounded + cited.
- **`agents/regime_synth.py` — agent-fed regime synthesis.** Synthesizes a DERIVED `RegimeAdvisoryPayload{label∈RegimeLabel, confidence, rationale_sanitized}` → `regime_advisory.json`. **D-ADVISORY=(A): REPORT-ONLY** — the console reports it; the acting path does NOT read it. (B) below is spec'd-but-disarmed.
- **`agents/daily_report.py` — Daily Report synthesizer (D-SCOPE).** Composes an HONEST §9 report from the day's state files (incl. the boring "0 trades, 0 survivors, gate killed all 4 toys" days) → `TelegramNotifier.send_daily_report`. Lowest-risk LLM use (text out, never read by the acting path).

### 4.1 The DISARMED subtractive-intersection (D-ADVISORY=(B), spec only)

If ever armed in a later increment: `drive_once` computes the deterministic posture, then loads a **sanitized + schema-validated** `regime_advisory.json` and intersects per-strategy eligibility — `effective = det_eligible & advisory_eligible` (pure `frozenset` AND). Because `A & B ⊆ A`, `|candidates|` can only **DROP**; missing/UNKNOWN/malformed/stale advisory → identity (no narrowing). There is no field/branch by which the advisory ADDS a strategy, raises a size, mints a grant, or flips a KILL. Arming requires: load through the same `sanitize.py` + strict schema; the intersection implemented as a pure set AND (structurally impossible to add); a G1-style staleness guard; the teeth test `test_advisory_can_only_subtract_never_add`; and an explicit operator checkpoint. **Not built into the driver this increment.**

---

## 5. PART D — the boundary proof + `make inc8`

### 5.1 The boundary tests (`tests/unit/test_inc8_boundary.py`)

1. **`test_no_submit_path_module_imports_slowloop_or_console`** — for each module under the 12 PHI1 roots, AST-parse imports and assert NONE resolve to `trading.slowloop.*` or `trading.console.*` (by **explicit top-level package identity**, not the `agent` substring coincidence). Teeth: a planted `from trading.slowloop.orchestrator import run_agent` in a tmp submit-path tree MUST be flagged; the real roots flag zero.
2. **`test_phi1_roots_do_not_include_slowloop_or_console`** — assert PHI1 `_ROOT_NAMES` contains neither, so they stay slow-loop-only (guards against "root creep").
3. **`test_dynamic_surface_still_green_after_inc8`** — the existing `test_no_dynamic_import_or_exec_surface_in_submit_path` stays green: any acting-path reader of advisory files uses `json.loads` + pydantic, never `importlib`/`__import__`/`exec`. Teeth: planting `importlib.import_module('trading.slowloop.llm.anthropic_client')` into a driver reader is caught.
4. **`test_console_is_escalate_only_never_rearm`** — `commands.py` has no `arm`/re-arm entry; reaching `kill_switch.arm` from the console raises `KillSwitchAuthorityError` (no `operator_authority=True`).
5. **`test_no_broker_symbol_reachable_from_slowloop_or_console`** — neither package imports `executor.submit`/`broker_paper`/`alpaca`.
6. The console/auth/dispatch/refusal/offset teeth from §3 (non-operator dropped; forwarded `/flatta` dropped; injection routes to Q&A sanitized; responder output not re-dispatched; `köp AAPL` refused; offset durable + cold-start skip).
7. The schema teeth: `AgentArtifact(reliability="hard")` → `ValidationError`; a DERIVED file → submit-path reader `require_gateable` raises; orchestrator discards invalid 3× + ORANGE page; atomic store never yields a partial read.
8. **`test_token_never_logged_slowloop_console`** — extend the existing grep test over `slowloop`/`console`.

### 5.2 `make inc8`

Mirrors `inc7` (ruff/black → leak-lint over the **frozen submit-path scope** → mypy `--strict` → pytest `--cov-fail-under=85`), **plus** the §5.1 boundary teeth as first-class pytest steps. **leak-lint scope is UNCHANGED** — it does NOT scan `slowloop`/`console` (those legitimately use LLM/network primitives the submit-path bans). mypy `files=["src/trading"]` already type-checks the new packages. A Makefile comment freezes the acting-path leak-lint scope so a future contributor cannot "add slowloop for completeness."

---

## 6. Build-cluster sequence (TDD; each cluster: tests → `make inc1..inc8` green → commit → push → ff main → STATE+memory)

- **C1** — `slowloop/errors.py` + `contract.py` (AgentArtifact + payloads; reliability-Literal teeth) + `store.py` (atomic write / fail-closed read; partial-read teeth). `make inc8` target created (mirrors inc7).
- **C2** — `slowloop/llm/anthropic_client.py` (Responder Protocol + thin httpx client + fakes; token-never-logged) + `orchestrator.py` (sanitize-in → validate → discard/last-known-good → ORANGE page at N=3; staleness→unavailable).
- **C3** — `console/authz.py` + `commands.py` + `poller.py` (auth/shape-whitelist; deterministic command allow-list → kill_switch escalate-only; durable offset + cold-start backlog discard; refuse-trade-order). The console boundary teeth (auth, forwarded, injection→Q&A, no-rearm, no-broker).
- **C4** — `console/state_reader.py` + `responder.py` (briefing from sanitized state; report-only grounded Q&A; no-invented-numbers; responder-output-not-re-dispatched).
- **C5** — `agents/news.py` + `agents/regime_synth.py` (+ `agents/daily_report.py` per D-SCOPE); schemas + per-agent fakes; the advisory REPORT-ONLY teeth (`test_deterministic_posture_is_sole_source_when_B_disarmed`).
- **C6** — `tests/unit/test_inc8_boundary.py` (the full §5.1 PHI1 import-graph proof, static + dynamic) + wire `make inc8` boundary steps. **All eight gates green.**
- Then: a live two-way Telegram smoke (`@pytest.mark.live`, excluded from the gate) + the operator round-trip deliverable.

---

## 7. Risk register (folded from all 3 completed lenses + lead skeptic)

| # | Risk | Sev | Structural mitigation |
|---|------|-----|-----------------------|
| R1 | `console`/`slowloop` accidentally added to PHI1 `_ROOTS`, or a submit-path module imports `console` → the whole closure pulls in `anthropic` and PHI1 collapses. | **CRITICAL** | Keep them out of `_ROOTS`; explicit import-graph boundary test (§5.1.1-2) with teeth; one-way coupling enforced. |
| R2 | A future "improvement" makes the advisory regime ADDITIVE (union/replace instead of intersection), or `posture` gains an add method. | **CRITICAL** | D-ADVISORY=(A) report-only ships zero acting-path read; `posture` stays subtractive-only; (B) is set-AND only, behind `test_advisory_can_only_subtract_never_add` + a checkpoint. |
| R3 | A jailbroken responder emits "I bought AAPL" → operator misled / an action. | HIGH | No code path from responder text to a broker; responder returns `str`; deterministic dispatch is independent of model output; teeth `test_responder_output_emitting_slash_flatta_is_not_dispatched`. |
| R4 | Non-operator / forwarded / edited / channel message steers a command. | HIGH | Auth on `chat.id == TELEGRAM_CHAT_ID` + shape-whitelist; forwarded/edited/channel dropped; teeth tests. |
| R5 | Cold-start backlog replays a stale `/flatta`. | HIGH | Durable offset; cold-start seeds to max + discards backlog; controls idempotent. |
| R6 | Forged `reliability:"hard"` smuggles a DERIVED advisory past §4.3. | HIGH | `reliability` is `Literal["textual","derived"]`; submit-path reader calls `require_gateable` (raises on DERIVED); teeth. |
| R7 | Anthropic key / Telegram token leaks via a prompt, error, or log. | HIGH | Keys read only at the HTTP layer; never in prompt-assembly; httpx exceptions re-wrapped; grep test over `slowloop`/`console`. |
| R8 | Schema validation fails OPEN (accepts a partial/None artifact). | HIGH | `extra="forbid"` + frozen + Literal/`ge`/`le`; reader returns `None` on any error; orchestrator discards + reuses last-known-good. |
| R9 | A stale advisory freezes into the acting path. | MED | Reader freshness window → "unavailable" (non-narrowing); orchestrator N=3 ORANGE page surfaces a dead agent. |
| R10 | Responder invents equity/P&L because a state file is missing (§9 integrity). | MED | Briefing is schema-validated facts only, each with `as_of`; missing → "unavailable"; system prompt forbids invention; no live broker call. |
| R11 | Injection in overnight news steers the regime synthesis. | MED | `sanitize()` before the LLM; schema-bound output (label∈RegimeLabel, conf∈[0,1]); structural floor: subtraction can only reduce survivors, and the toys yield zero survivors regardless. |
| R12 | pydantic v2 disk cost on a ~3 GB-free disk. | MED | pydantic v2 is already a dep (`pydantic-core` single wheel); no new install. |

---

## 8. What stays NO-OP / advisory vs live

- **NO-OP/dormant in the gate:** the orchestrator and the console poller do not run on their own; every LLM/Telegram call is faked. The executor stays RECORD-ONLY behind the per-order GO; the scheduler stays `SCHEDULER_ENABLE`-gated.
- **Advisory/report-only:** news_state.json, regime_advisory.json, the console's Q&A answers, the daily report — none can gate/size/override/place a trade.
- **Live (excluded from the gate, operator-aware):** one `@pytest.mark.live` Anthropic smoke; one `@pytest.mark.live` Telegram two-way round-trip (the deliverable). No trading.

---

## 9. Roadmap confirmation

Inc-8 = the slow-loop **agents + two-way console** (this doc). The **live dashboard is the LAST layer, LATER** (ADR roadmap Inc-8→ renumbered; a real UI needs the engine first) — **NOT built here.** The rest of the §1.1 roster (macro/social/on-chain/filings/adversarial-reviewer/post-trade/mistake-tracker/calibration/hypothesis/weekly-review) is FUTURE.
