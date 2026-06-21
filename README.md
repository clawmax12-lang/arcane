# ARCANE

**Autonomous Reasoning, Calibration, And Network-orchestrated Execution** — a solo-operated,
multi-agent, continuously-calibrating research platform for systematic trading.

> **What it is:** an **edge-falsification harness**, not a profit machine. A pre-registered
> null result (no edge survives realistic costs + the bias gate) is a project **success that
> stops work**, not a failure. Long-history walk-forward backtests are the primary evidence;
> the paper account is plumbing verification only. See [`docs/adr/ADR-001-foundation.md`](docs/adr/ADR-001-foundation.md).

**Mode:** paper-only. `LIVE_MODE = false` in both config and code. No real order can route.
**Operator:** William Svanq · **Governance:** [`CLAUDE.md`](CLAUDE.md) (binding rules).

---

## Status

| Increment | Scope | State |
|---|---|---|
| **1 — Safety spine** | Deterministic risk core that every order must pass | ✅ built, hardened, red-team-verified |
| 2 — Alpaca data spine | alpaca-py paper client + cached/staleness-checked market data | ⬜ next |
| 3–8 | Factors → strategies → backtest → bias-gate → regime → allocator → agents | ⬜ planned |
| — | 14-day paper soak (mandatory before any live consideration) | ⬜ |

The Increment-1 spine is built test-first and was put through two adversarial red-team
passes; six confirmed fail-open holes were found and fixed (see `tests/unit/test_redteam_fixes.py`
and the git history). **Honest scope:** Increments 1–8 ≈ 55–90 focused build+test hours plus
a 14-day soak — not a one-shot build.

## Safety model (the part that must be bulletproof)

- **Floor-of-floors** ([`risk/constants.py`](src/trading/risk/constants.py)) — hardcoded limits
  (equity floor $20, total-loss abandon $30) that `config/risk.yaml` can only make *stricter*.
- **LIVE_MODE triple-lock** ([`executor/live_mode.py`](src/trading/executor/live_mode.py)) — live
  requires a code constant **and** config **and** an interactive CLI marker; default is paper.
- **Kill switch** ([`executor/kill_switch.py`](src/trading/executor/kill_switch.py)) — atomic,
  monotonic ARMED→TRIPPED→HARD_STOPPED, operator-only re-arm, fail-safe on corruption/symlink/
  write-failure.
- **Pre-submit invariant chain** ([`executor/invariants.py`](src/trading/executor/invariants.py))
  — ordered, fail-closed: kill-switch → data-freshness → caps → concentration → idempotency →
  mistake-check. No order bypasses a gate.
- **PHI1** — the LLM is **never** in the submit path; an import-guard test enforces it.

## Develop

Requires [`uv`](https://docs.astral.sh/uv/). Python is pinned to 3.13.12 via `.python-version`.

```bash
make setup       # uv sync (creates the env)
make inc1        # the Increment-1 gate: ruff + black + mypy --strict + pytest >=85% cov
make check       # lint + typecheck + tests
make test-cov    # tests with coverage report
make format      # ruff --fix + black
```

`make inc1` is the contract for the safety spine and must stay green.

## Layout

```text
config/        risk.yaml (operator-tunable within the floor-of-floors)
docs/adr/      ADR-001 (binding architecture decisions) · docs/RISK_REGISTER.md
src/trading/
  risk/        constants, schema, loader, caps   (deterministic; no LLM imports)
  executor/    live_mode, kill_switch, intent, idempotency, invariants,
               mistake_check, reconciler, broker_paper (paper=True), runner
  data/        sanitize.py (§4.2 prompt-injection guard)
  settings.py  required creds fail-fast, optional creds degrade
tests/unit/    unit + hypothesis property tests + red-team regressions
```

## Posture reminders

- Heavy ML (torch/faiss/chromadb), Postgres, and the dashboard are deferred behind interfaces;
  the spine and lake run on stdlib + DuckDB/Parquet/SQLite.
- A paging channel (Discord webhook) is required before Increment 5 (first real paper submit);
  until then disaster-recovery paging degrades to local-file + console.
