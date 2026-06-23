"""The deterministic gate-gated paper submit — RECORD-ONLY until a single-use operator GO (Inc-6 C).

``submit_allocated`` is the ONLY caller of ``PaperBroker.submit``, and it REQUIRES an
``AllocationGrant`` as its first, non-defaulted argument — so a killed strategy (which can
never mint a
grant) cannot even reach this function. The body, in order: bind the grant to the target strategy
(confused-deputy guard) → assert ``is_live()`` is False → size within caps → run the full pre-submit
invariant chain (incl. §2.2 mistake check) → branch on submit mode. In RECORD_ONLY (the default) it
journals the would-be intent and submits NOTHING and claims NOTHING. Only LIVE_SUBMIT — gated by a
single-use, phrase-and-spec-bound ``state/SUBMIT_GO`` marker — does CLAIM-THEN-SUBMIT to the paper
broker, then consumes (rotates) the marker. No LLM is imported here (PHI1).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from trading.executor.broker_paper import PaperBroker
from trading.executor.grant import AllocationGrant
from trading.executor.idempotency import IdempotencyStore
from trading.executor.invariants import (
    AccountSnapshot,
    MistakeChecker,
    _no_mistakes,
    evaluate_pre_submit,
)
from trading.executor.kill_switch import KillSwitch
from trading.executor.live_mode import is_live
from trading.executor.sizing import HardQuote, NoTrade, TargetPosition, size_order
from trading.risk.schema import RiskConfig

logger = logging.getLogger(__name__)

#: The exact phrase the operator-GO marker must contain to authorize ONE real paper submit.
GO_PHRASE: Final[str] = "I_AUTHORIZE_ONE_PAPER_ORDER"
DEFAULT_GO_MARKER: Final[Path] = Path("state/SUBMIT_GO")


class SubmitMode(StrEnum):
    RECORD_ONLY = "RECORD_ONLY"  # claim nothing, submit nothing — journal the would-be intent
    LIVE_SUBMIT = "LIVE_SUBMIT"  # claim-then-submit to the PAPER broker (still paper=True)


@dataclass(frozen=True, slots=True)
class SubmitOutcome:
    """Outcome of a gate-gated submit attempt. ``submitted`` is True only after a real broker
    ack."""

    submitted: bool
    mode: SubmitMode
    reason: str
    client_order_id: str | None
    accepted: bool | None  # broker ack acceptance (None unless an actual submit happened)


def submit_mode(
    grant: AllocationGrant, cfg: RiskConfig, *, go_marker_path: Path = DEFAULT_GO_MARKER
) -> SubmitMode:
    """LIVE_SUBMIT only when is_live is False AND the single-use marker authorizes THIS grant."""
    if is_live(cfg.live_mode):  # never act while live is (somehow) armed — this run is NO LIVE
        return SubmitMode.RECORD_ONLY
    try:
        if not go_marker_path.is_file():
            return SubmitMode.RECORD_ONLY
        lines = [ln.strip() for ln in go_marker_path.read_text(encoding="utf-8").splitlines()]
    except OSError:
        return SubmitMode.RECORD_ONLY
    if GO_PHRASE in lines and grant.spec_hash in lines:
        return SubmitMode.LIVE_SUBMIT
    return SubmitMode.RECORD_ONLY


def _consume_marker(go_marker_path: Path, client_order_id: str) -> None:
    """Single-use: rotate the GO marker to a forensic ``.consumed-<coid>`` trail (OQ-3)."""
    try:
        if go_marker_path.is_file():
            go_marker_path.rename(
                go_marker_path.parent / f"{go_marker_path.name}.consumed-{client_order_id}"
            )
    except OSError:  # pragma: no cover - best-effort rotation; a failed rotate never submits twice
        logger.warning("could not rotate SUBMIT_GO marker after consuming it")


def submit_allocated(
    grant: AllocationGrant,
    target: TargetPosition,
    quote: HardQuote,
    snapshot: AccountSnapshot,
    cfg: RiskConfig,
    kill_switch: KillSwitch,
    store: IdempotencyStore,
    broker: PaperBroker,
    *,
    mistake_checker: MistakeChecker = _no_mistakes,
    go_marker_path: Path = DEFAULT_GO_MARKER,
) -> SubmitOutcome:
    """Gate an allocated survivor's target into a paper order. Record-only unless the operator
    GO's."""
    # 0. confused-deputy: the grant must authorize THE strategy this target belongs to.
    if grant.spec_hash != target.spec_hash:
        return SubmitOutcome(
            False,
            SubmitMode.RECORD_ONLY,
            f"grant spec_hash {grant.spec_hash} != target spec_hash {target.spec_hash}",
            None,
            None,
        )
    # 1. is_live MUST be False (unconditional). Refuse to act if live is somehow armed.
    if is_live(cfg.live_mode):
        return SubmitOutcome(
            False,
            SubmitMode.RECORD_ONLY,
            "is_live() is True — refusing to act (NO LIVE)",
            None,
            None,
        )
    # 2. size within the immutable caps (the $1 cap yields NoTrade for any real share).
    sized = size_order(grant, target, quote, snapshot, cfg)
    if isinstance(sized, NoTrade):
        return SubmitOutcome(False, SubmitMode.RECORD_ONLY, f"no trade: {sized.reason}", None, None)
    intent = sized.intent
    # 3. the full ordered, fail-closed pre-submit chain (kill→M17→caps→idempotency-read→mistake).
    decision = evaluate_pre_submit(
        intent, snapshot, cfg, kill_switch, store.seen, mistake_checker=mistake_checker
    )
    coid = decision.client_order_id
    if not decision.accepted:
        return SubmitOutcome(
            False,
            SubmitMode.RECORD_ONLY,
            f"gate rejected at {decision.failed_gate}: {decision.reason}",
            coid,
            None,
        )
    # 4. branch on submit mode. RECORD_ONLY journals + claims/​submits NOTHING.
    mode = submit_mode(grant, cfg, go_marker_path=go_marker_path)
    if mode is SubmitMode.RECORD_ONLY:
        logger.info(
            "order_record_only coid=%s strategy=%s symbol=%s qty=%s (no broker submit)",
            coid,
            intent.strategy_id,
            intent.symbol,
            intent.qty,
        )
        return SubmitOutcome(
            False, SubmitMode.RECORD_ONLY, "record-only: journaled, no broker submit", coid, None
        )
    # 5. LIVE_SUBMIT — CLAIM-THEN-SUBMIT (at-most-once). Claim BEFORE the broker call.
    if not store.remember(coid):
        return SubmitOutcome(
            False, SubmitMode.LIVE_SUBMIT, "lost idempotency race (concurrent submit)", coid, None
        )
    ack = broker.submit(intent, coid)  # real paper submit (paper=True hardcoded in PaperBroker)
    _consume_marker(go_marker_path, coid)  # single-use: one GO authorizes one order
    logger.info("order_submitted coid=%s accepted=%s", coid, ack.accepted)
    return SubmitOutcome(True, SubmitMode.LIVE_SUBMIT, ack.detail, coid, ack.accepted)
