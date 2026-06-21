## ARCANE Increment 2 — Data Spine Design (decision-grade, synthesis of 5 specialist tracks + ADR-001)

### 0. Mandate & invariant
Inc-2 builds the **leak-proof-by-construction point-in-time (PIT) data layer** that feeds every downstream factor and backtest. The single load-bearing principle: **PIT/RTH/survivorship correctness is STRUCTURAL, not disciplinary.** `DataLoader.load()` is `@final` and bakes in every guard; subclasses implement only `_fetch`. A buggy or adversarial `_fetch` cannot open a leak because steps (d)–(i) re-derive everything after it returns. A look-ahead leak is a *test failure* (registry-wide prefix-stability), not a code-review judgment call. All five tracks converged on this; it is non-negotiable.

Mirrors verified Inc-1 idioms: `ArcaneError` taxonomy (`risk/errors.py`), fail-closed loader (`risk/loader.py` raises, no partial config), SHA-256 content hashing + atomic `temp→fsync→os.replace` (`idempotency.py`, `kill_switch.py`), grep-able `Final` constants (`broker_paper.ALPACA_PAPER`), idempotent fail-closed boundary (`sanitize.py`), `mypy --strict`, ≥85% cov.

---

### 1. RESOLVED CONFLICTS (decision · rationale · rejected alternative)

**C1 — adjustment default: `ALL` vs `split`.** *DECISION: pin `adjustment=Adjustment.ALL` (split+dividend) as the AlpacaBarLoader default; it is a content-key dimension and forces `requires_pit_ingest_ts` semantics on the cache.* Rationale: for a walk-forward backtest the price series must be PIT-consistent across BOTH splits and dividends; `RAW`/`split`-only injects a fake overnight return at every dividend date that becomes a fabricated factor signal (leak-adversary L7, alpaca-integration §5 — both CRITICAL). The data-contract/planner `split` suggestion under-covers dividends. The known cost of `ALL` (Alpaca *restates* adjusted history after a new corporate action) is handled structurally: `adjustment` is in the cache key AND every row carries `ingest_ts`, so a post-action re-pull yields a NEW cache entry, never a silent overwrite. *Rejected:* `split`-only (leaves dividend leak); `RAW`+client-side adjustment (re-implements vendor corporate-action logic = larger bug surface than the restatement we are mitigating).

**C2 — calendar library: exchange-calendars vs pandas-market-calendars.** *DECISION: exchange-calendars 4.13.2 as the SOLE authority, pinned `side="left"`.* Rationale: `side="left"` STRUCTURALLY enforces the half-open `[open, close)` RTH interval (open IS a trading minute, close is NOT), so the close-bar off-by-one is leak-proof by construction. pandas-market-calendars has no minute-inclusivity control and forces a hand-written interval test = discipline, which the data spine forbids (time-calendar track, CRITICAL). *Rejected:* pandas-market-calendars (drop it from deps entirely — the planner's inclusion of both was a hedge; carrying two calendar libs invites two boundary conventions). Keep a dual-implementation *agreement test* (`opens<=t<closes` vs `is_trading_minute`) as the upgrade tripwire.

**C3 — in-memory form: pandas vs polars.** *DECISION: pandas 3.x only; polars deferred behind the loader contract.* Rationale: alpaca-py and exchange-calendars are pandas-native; the §7 prefix-stability/`shift(1)` contract is most auditable on a pandas time index; two DataFrame dialects on the single highest-leak layer is a red-team liability, not a perf win at IEX/$50 scale (planner). DuckDB reads Parquet in place so polars buys little here. *Rejected:* polars-now (dual copy-semantics model); DuckDB-as-in-memory-form (keep DuckDB for the lake/walk-forward read path only).

**C4 — validation: pandera vs hand-rolled.** *DECISION: pandera 0.32 (`pandera.pandas` API) with `strict=True, coerce=False, ordered=True`, PLUS a separate `np.isfinite` finiteness assertion that runs BEFORE pandera.* Rationale: pandera gives declarative dtype-strictness, the OHLC cross-field invariant, and extra-column rejection for free; `coerce=False` is the fail-closed posture (hand-rolled code drifts toward silent `.astype()`). But pandera `ge=0` admits `inf` and NaN compares False to everything (the Inc-1 `AccountSnapshot` trap), so finiteness is checked independently first. *Rejected:* manual-only validation (silent-coercion drift); pandera-only finiteness (admits inf).

**C5 — module layout: `data/` + `lake/` (planner) vs all-in-`data/` (data-contract).** *DECISION: everything under `src/trading/data/` for Inc-2; the cache/store live in `data/cache.py` + `data/store.py`.* Rationale: keeps the increment's surface in one auditable package, matches data-contract's <400-line file discipline; a separate `lake/` package is premature for a single content-addressed Parquet cache. *Rejected:* separate `lake/` package (extra package boundary with no second consumer yet — revisit in the backtest-sweep increment).

**C6 — `ingest_ts` provenance for HARD bars.** *DECISION: synthesize `ingest_ts = bar_close + PUBLISH_LAG` where `PUBLISH_LAG` is a named conservative `Final` (default = 1 full timeframe), stamped into `BarMeta` for audit.* Rationale: a backtest standing at `as_of = bar.ts` must not see the bar it is standing on (canonical look-ahead). Restated/STRUCTURED sources (`requires_pit_ingest_ts=True`) must supply a REAL per-row `ingest_ts` and are REFUSED if absent — vintage is never synthesized for restated data (data-contract + leak-adversary). *Rejected:* `ingest_ts = now()` (non-deterministic, breaks prefix-stability and cache identity).

---

### 2. The FINAL `load()` template (the structural heart) — `data/loader.py`

```python
class DataLoader(ABC):
    SCHEMA_VERSION: int = 1                  # bump → whole cache invalidates
    requires_pit_ingest_ts: bool = False     # restated sources set True

    @final
    def load(self, *, symbol, timeframe, start, end, as_of: AsOf,
             feed="iex", adjustment="all", session="XNYS") -> LoadResult:
        p      = LoadParams.normalize(...)          # (a) canonicalize + reject tz-naive / future as_of
        key    = self._cache_key(p)                 # (b) SHA-256 over EVERY data-affecting param
        hit    = self._cache.get(key)               # (c) cache READ re-validates (corrupt → MISS)
        if hit is not None: return hit
        raw    = self._fetch(p)                      # (d) ONLY subclass hook: network/IO, no guards
        df     = self._coerce_dtypes(raw, p)         # (e) audited explicit casts (Float64/Int64), NOT in _fetch
        df     = self._stamp_ingest_ts(df, p)        # (f) every row gets ingest_ts (or refuse if requires_pit & absent)
        df     = pit_guard(df, p.as_of)              # (g) DROP rows ingest_ts > as_of  ← look-ahead closed
        calendar.assert_utc(df.index)                # (h) tz-naive/non-UTC → CalendarError
        df     = align_rth(df, p)                    # (i) exchange-calendars [open,close); session stamped
        run_quality_gate(df, p)                      # (j) finiteness → mono → dup → OHLC (fail-closed, raises)
        BarSchema.validate(df, lazy=False)           # (k) pandera strict, coerce=False
        result = LoadResult(frame=ImmutableFrame(df), meta=self._meta(p, df))
        self._cache.put(key, result)                 # (l) atomic, LRU, MAX_CACHE_BYTES ceiling
        return result

    @abstractmethod
    def _fetch(self, p: LoadParams) -> pd.DataFrame: ...
```

`as_of` is a **required kw-only arg with no default** → omitting the PIT clock is a `TypeError`. A test asserts (AST scan) no subclass overrides `load`.

| Leak surface | Closed by |
|---|---|
| Late-arriving / future row | (f)+(g): stamp `ingest_ts`, drop `> as_of`; `@final` so `_fetch` can't bypass |
| Forgotten PIT clock | `as_of` required, no default |
| Restatement (fundamentals) | `requires_pit_ingest_ts` + REFUSE if `_fetch` omits per-row `ingest_ts` |
| Cache cross-serve (IEX vs SIP, raw vs all) | (b) key hashes symbol,timeframe,start,end,**as_of,feed,adjustment,session**,loader class,SCHEMA_VERSION |
| Adjustment non-determinism | forced explicit `all`, stamped; vendor default change → different key |
| Survivorship | Alpaca-only → `survivorship_unverified=True`; bias-test T2 returns `passed=False` |
| RTH/tz mislabel | (h)+(i) trust calendar, never vendor bar tz |
| Dup / out-of-order | (j) strict-monotonic unique; **conflicting value for one ts RAISES** (never silent pick-last) |
| Vendor outage short frame | `_fetch` fails CLOSED (typed `DataFetchError`); not cached as authoritative |

---

### 3. DataLoader contract — `LoadParams`, `AsOf`, `LoadResult`, `BarMeta`

- **`AsOf`** (`data/pit.py`): frozen `{ts: datetime}`; `__post_init__` asserts tz-aware UTC and `ts <= now`. `pit_guard` raises `PitLeakError` if `ingest_ts` absent or any null; else `df.loc[df.ingest_ts <= as_of.ts]`.
- **`LoadResult`** frozen `{frame: ImmutableFrame, meta: BarMeta}`. `ImmutableFrame.df` returns a CoW copy (caller edits never touch cache); `allows_duplicate_labels=False`.
- **`BarMeta`** frozen, travels end-to-end (tags can't be stripped): `symbol, timeframe, feed("iex"), adjustment("all"), reliability(HARD), as_of, survivorship_unverified(True), is_sip_consolidated(False), publish_lag, cache_key, row_count`.

---

### 4. Canonical bar schema — `data/bar_schema.py` (pandas-3-native)

Index: tz-aware UTC `DatetimeIndex` named `ts` (bar OPEN instant, left-labeled — **verified** Alpaca convention), `unique=True`, monotonic checked in quality gate. Columns: `open/high/low/close` `Float64`(ge=0, non-null), `volume`/`trade_count` `Int64`(ge=0), `vwap` `Float64`(nullable), `ingest_ts` `datetime64[ns,UTC]`(non-null). pandera `Config: strict=True, coerce=False, ordered=True` + `@dataframe_check` OHLC consistency (`high>=max(o,c,l)`, `low<=min(o,c)`). **Reliability tokens** are type-level `NewType` phantoms: `GateableFrame = HardFrame | StructuredFrame`; a `TextualFrame`/`DerivedFrame` passed to a runtime gate is a **mypy error** (ADR §4.3 structurally, not by discipline).

---

### 5. alpaca-py integration — `data/alpaca_loader.py` (`_fetch` only, ~40 lines, verified 0.43.4)

Imports (exact paths): `from alpaca.data.historical import StockHistoricalDataClient`; `from alpaca.data.requests import StockBarsRequest`; `from alpaca.data.timeframe import TimeFrame, TimeFrameUnit`; `from alpaca.data.enums import DataFeed, Adjustment, Sort`; `from alpaca.common.exceptions import APIError`.

Client: `StockHistoricalDataClient(api_key=settings.required["APCA_API_KEY_ID"], secret_key=settings.required["APCA_API_SECRET_KEY"], raw_data=False)` — **NO `paper=` param exists on the data client** (market data is gated by data-tier, not paper/live; the `paper=ALPACA_PAPER` constant belongs only to the trading/submit path). Settings injected, not re-read from env. Constructed once, cached on instance.

Request (verified kw-only signature): 
```python
StockBarsRequest(symbol_or_symbols=sym, timeframe=TimeFrame(1, TimeFrameUnit.Day),
                 start=start, end=end, adjustment=Adjustment.ALL,
                 feed=DataFeed.IEX,            # EXPLICIT — never None (None → "best available" → silent SIP escalation)
                 sort=Sort.ASC, limit=None)    # SDK auto-paginates on next_page_token; do NOT hand-roll
```
Call: `client.get_stock_bars(req).df` → MultiIndex `(symbol, timestamp)`, tz-aware UTC, columns `open/high/low/close/volume/trade_count/vwap`. `_fetch` drops the `symbol` level, renames `timestamp→ts`, stamps `feed="iex"`, `reliability=HARD`, `is_sip_consolidated=False`, `survivorship_unverified=True`. Empty df (delisted / no IEX coverage) → fail-closed `DataFetchError` (never a silent empty pass). Clamp `end <= now_utc - 16min` for IEX-toward-now (free-plan 403 foot-gun). Wrap the call: `except (APIError, httpx.HTTPError) → DataFetchError`; do NOT stack a second retry over the SDK's built-in 429/504 `RetryException` loop. Crypto is a **separate sibling** (`CryptoHistoricalDataClient`, no keys, 24/7 calendar) — out of scope for v1.

A contract test pins the exact `(symbol,timestamp)` MultiIndex + column set against a recorded fixture; an import/shape mismatch raises `DataFetchError`.

---

### 6. Calendar / RTH / tz — `data/calendar.py` (single instance)

`XNYS = get_calendar("XNYS", side="left")` constructed once, process-cached; `get_calendar` is grep/AST-banned elsewhere (same enforcement as `broker_paper paper=False`). UTC end-to-end; `assert_utc` rejects tz-naive (fail-closed). Session derived ONLY via `minute_to_session(ts, direction="previous")` — never `.date()`/`.floor("D")`/`.normalize()` (AST-banned). `as_of` → session with `direction="previous"` ALWAYS (never "next" = future leak). Daily bar visible at `as_of` only if `session_close(S) <= as_of`. RTH mask vectorized `opens[S] <= t < closes[S]`; early-closes/half-days/DST come from the calendar, never special-cased. Golden tests pin 2024-07-03 (13:00 ET early close), 2024-11-29, one spring-forward + one fall-back session.

---

### 7. Cache — `data/cache.py` (content-addressed Parquet + LRU byte ceiling)

`MAX_CACHE_BYTES: Final = 512*1024*1024` (config-lowerable only). Key = `"arcane-bars-" + sha256(canonical_json(...))[:40]` over the full param set incl. loader class + `SCHEMA_VERSION`. Atomic write `temp→fsync→os.replace` (mirrors `kill_switch`). SQLite sidecar manifest `(key, bytes, last_access, created)`; `put()` inserts then evicts LRU until `sum(bytes) <= MAX_CACHE_BYTES` in one transaction → cache can never fill disk; single object > ceiling is refused (`CacheTooLargeError`). **Read re-validates** against pandera; corrupt/partial parquet → MISS → re-fetch (never serve garbage). Startup reconcile drops manifest rows whose files are missing and unlinks orphan files (self-heals across restarts). Respects ADR F7: at disk < 1GB, caching pauses and the operator is warned (single-writer per ADR §3 makes true concurrency out of scope).

---

### 8. Quality gate — `data/quality.py` (fail-closed, raises on first failure)
Ordered: **G1** `np.isfinite(OHLCV).all()` (before pandera; inf/NaN → `QualityError`) → **G2** strict-monotonic-increasing unique index → **G3** duplicate-ts with conflicting values RAISES (`DuplicateBarError`) → **G4** gap report → `coverage_degraded` (NEVER ffill/zero-fill; missing stays missing — IEX holes are the CRITICAL fabricated-volume leak). Re-runs on cache read.

---

### 9. Universe / survivorship — `data/universe.py` (DEGRADED by design)
Polygon deferred → PIT universe runs DEGRADED, stamps `survivorship_unverified=True`; survivorship bias-test T2 returns `passed=False, reason="universe unverified (Polygon deferred)"`. A test asserts the degraded path can NEVER emit `passed=True`. No hardcoded symbol lists.

---

### 10. Prefix-stability + leak-lint — `data/prefix_stability.py`, `data/leak_lint.py`
Hypothesis property `compute(df[:k]).equals(compute(df[:k+1]).iloc[:k])` run registry-wide at startup (`registry.validate_all()`). AST leak-lint bans inside `data/`: `resample`, `reindex+ffill/bfill`, `fillna(0)`, full-series rolling/normalization, `dropna` that hides gaps, tz-naive construction, `asof=None`, `.date()`/`.floor("D")`. Both wired into `make inc2`. Written generic over the registry so Increment-3 AlphaFactors are covered with zero rework.

---

### 11. pandas-3 notes
CoW is default+mandatory → chained assignment (`df[mask][col]=v`) silently no-ops; design rule: only `.assign()` / `.loc[...]=` on owned frames, transforms return new frames. `ImmutableFrame.df` returns a CoW copy. Nullable `Float64`/`Int64` pinned in G1/schema (Alpaca may deliver numpy float64+NaN → coerce deterministically in `_coerce_dtypes`, never silently). Explicit one-to-one joins to catch silent index mismatch. Round-trip tests assert a transformed frame actually differs where mutation was intended (catches CoW no-op).

---

### 12. Module layout (`src/trading/data/`, all <400 lines, mypy --strict)
`errors.py` (`DataError(ArcaneError)` + `PitLeakError, SchemaViolationError, CalendarError, FeedMismatchError, DataFetchError, CacheTooLargeError, RestatedSourceError, DuplicateBarError`) · `reliability.py` (tokens) · `bar_schema.py` · `pit.py` · `calendar.py` · `cache.py` · `quality.py` · `loader.py` (FINAL base) · `alpaca_loader.py` · `universe.py` · `prefix_stability.py` · `leak_lint.py`. Plus `tests/conftest.py` (offline fixtures, no network in the gated suite; live Alpaca behind an opt-in marker).