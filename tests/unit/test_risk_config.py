"""Tests for the floor-of-floors risk configuration (Increment 1 safety spine).

These tests assert the central safety property: configuration can make the limits
*stricter* but can NEVER loosen a hard floor. Property-based tests prove this holds
across the whole invalid range, not just hand-picked examples.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from trading.risk import constants as C
from trading.risk.errors import RiskConfigError
from trading.risk.loader import load_risk_config
from trading.risk.schema import RiskConfig

REPO_ROOT = Path(__file__).resolve().parents[2]

VALID: dict[str, Any] = {
    "live_mode": False,
    "per_trade_risk_usd": 1.0,
    "max_daily_loss_usd": 5.0,
    "equity_floor_usd": 20.0,
    "total_loss_abandon_usd": 30.0,
    "max_position_concentration_pct": 30.0,
    "max_consecutive_errors": 5,
}


def test_valid_config_constructs() -> None:
    cfg = RiskConfig(**VALID)
    assert cfg.live_mode is False
    assert cfg.equity_floor_usd == C.EQUITY_FLOOR_USD


def test_repo_risk_yaml_loads_and_is_paper() -> None:
    cfg = load_risk_config(REPO_ROOT / "config" / "risk.yaml")
    assert cfg.live_mode is False
    assert cfg.equity_floor_usd >= C.EQUITY_FLOOR_USD
    assert cfg.total_loss_abandon_usd <= C.TOTAL_LOSS_ABANDON_USD


def test_equity_floor_below_hard_floor_rejected() -> None:
    with pytest.raises(ValidationError):
        RiskConfig(**{**VALID, "equity_floor_usd": 10.0})


def test_total_loss_above_hard_cap_rejected() -> None:
    with pytest.raises(ValidationError):
        RiskConfig(**{**VALID, "total_loss_abandon_usd": 50.0})


def test_per_trade_above_ceiling_rejected() -> None:
    with pytest.raises(ValidationError):
        RiskConfig(**{**VALID, "per_trade_risk_usd": 8.0, "max_daily_loss_usd": 9.0})


def test_daily_above_ceiling_rejected() -> None:
    with pytest.raises(ValidationError):
        RiskConfig(**{**VALID, "max_daily_loss_usd": 20.0})


def test_per_trade_exceeds_daily_rejected() -> None:
    # 4 <= ceiling(5) and 3 <= ceiling(15), so only the per_trade>daily invariant fires.
    with pytest.raises(ValidationError):
        RiskConfig(**{**VALID, "per_trade_risk_usd": 4.0, "max_daily_loss_usd": 3.0})


def test_config_is_frozen() -> None:
    cfg = RiskConfig(**VALID)
    with pytest.raises(ValidationError):
        cfg.live_mode = True  # type: ignore[misc]


def test_extra_field_forbidden() -> None:
    with pytest.raises(ValidationError):
        RiskConfig(**{**VALID, "sneaky_override": 1})


def test_loader_rejects_non_mapping(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("- just\n- a\n- list\n")
    with pytest.raises(RiskConfigError):
        load_risk_config(p)


def test_loader_rejects_invalid_values(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text(
        "live_mode: false\n"
        "per_trade_risk_usd: 1.0\n"
        "max_daily_loss_usd: 5.0\n"
        "equity_floor_usd: 5.0\n"  # below the hard floor -> must fail closed
        "total_loss_abandon_usd: 30.0\n"
        "max_position_concentration_pct: 30.0\n"
        "max_consecutive_errors: 5\n"
    )
    with pytest.raises(RiskConfigError):
        load_risk_config(p)


def test_loader_missing_file(tmp_path: Path) -> None:
    with pytest.raises(RiskConfigError):
        load_risk_config(tmp_path / "does_not_exist.yaml")


def test_loader_rejects_malformed_yaml(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("per_trade_risk_usd: [1, 2\n")  # unclosed flow sequence -> YAMLError
    with pytest.raises(RiskConfigError):
        load_risk_config(p)


# --- Property-based proofs: the floor can never be loosened, for ANY value ---


@given(equity_floor=st.floats(min_value=0.01, max_value=C.EQUITY_FLOOR_USD - 0.01))
def test_property_equity_floor_below_hard_floor_always_rejected(equity_floor: float) -> None:
    with pytest.raises(ValidationError):
        RiskConfig(**{**VALID, "equity_floor_usd": equity_floor})


@given(total_loss=st.floats(min_value=C.TOTAL_LOSS_ABANDON_USD + 0.01, max_value=1e6))
def test_property_total_loss_above_cap_always_rejected(total_loss: float) -> None:
    with pytest.raises(ValidationError):
        RiskConfig(**{**VALID, "total_loss_abandon_usd": total_loss})


@given(per_trade=st.floats(min_value=C.PER_TRADE_RISK_USD_CEILING + 0.01, max_value=1e6))
def test_property_per_trade_above_ceiling_always_rejected(per_trade: float) -> None:
    with pytest.raises(ValidationError):
        RiskConfig(**{**VALID, "per_trade_risk_usd": per_trade, "max_daily_loss_usd": 1e9})
