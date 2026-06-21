"""Tests for the pre-trade mistake-fingerprint check (Increment 1 safety spine)."""

from __future__ import annotations

import json
from pathlib import Path

from trading.executor.intent import OrderIntent
from trading.executor.invariants import AccountSnapshot
from trading.executor.mistake_check import MistakePattern, PatternMistakeChecker

INTENT = OrderIntent(
    strategy_id="orb",
    symbol="AAPL",
    side="buy",
    qty=1.0,
    intended_risk_usd=1.0,
    est_position_value_usd=10.0,
)
SNAP = AccountSnapshot(
    equity_usd=50.0,
    realized_daily_loss_usd=0.0,
    cumulative_loss_usd=0.0,
    data_as_of_epoch=1_000_000.0,
    now_epoch=1_000_000.0,
)


def test_empty_checker_allows() -> None:
    assert PatternMistakeChecker([])(INTENT, SNAP) is None


def test_matching_symbol_blocks() -> None:
    checker = PatternMistakeChecker(
        [
            MistakePattern(
                id="p1",
                category="M7",
                symbol="AAPL",
                reason="news blindspot",
                last_occurrence_epoch=SNAP.now_epoch,
            )
        ]
    )
    result = checker(INTENT, SNAP)
    assert result is not None
    assert "p1" in result and "M7" in result


def test_non_matching_symbol_allows() -> None:
    checker = PatternMistakeChecker(
        [
            MistakePattern(
                id="p1", category="M7", symbol="TSLA", last_occurrence_epoch=SNAP.now_epoch
            )
        ]
    )
    assert checker(INTENT, SNAP) is None


def test_expired_pattern_ignored() -> None:
    old = SNAP.now_epoch - 91 * 86_400.0  # older than the 90-day default expiry
    checker = PatternMistakeChecker(
        [MistakePattern(id="p1", category="M7", symbol="AAPL", last_occurrence_epoch=old)]
    )
    assert checker(INTENT, SNAP) is None


def test_missing_file_is_empty_ledger(tmp_path: Path) -> None:
    checker = PatternMistakeChecker.from_file(tmp_path / "nope.json")
    assert checker(INTENT, SNAP) is None


def test_corrupt_file_fails_closed(tmp_path: Path) -> None:
    p = tmp_path / "patterns.json"
    p.write_text("{ not a list")
    checker = PatternMistakeChecker.from_file(p)
    blocked = checker(INTENT, SNAP)
    assert blocked is not None and "corrupt" in blocked


def test_non_list_json_fails_closed(tmp_path: Path) -> None:
    p = tmp_path / "patterns.json"
    p.write_text(json.dumps({"not": "a list"}))
    assert PatternMistakeChecker.from_file(p)(INTENT, SNAP) is not None


def test_valid_file_round_trip(tmp_path: Path) -> None:
    p = tmp_path / "patterns.json"
    p.write_text(
        json.dumps(
            [
                {
                    "id": "p1",
                    "category": "M7",
                    "symbol": "AAPL",
                    "last_occurrence_epoch": SNAP.now_epoch,
                }
            ]
        )
    )
    assert PatternMistakeChecker.from_file(p)(INTENT, SNAP) is not None
