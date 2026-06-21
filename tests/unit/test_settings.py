"""Tests for runtime settings: required fail-fast, optional graceful degradation."""

from __future__ import annotations

from pathlib import Path

import pytest

from trading.settings import (
    OPTIONAL_KEYS,
    MissingCredentialError,
    load_settings,
    read_dotenv,
)

FULL = {
    "APCA_API_KEY_ID": "PKxxx",
    "APCA_API_SECRET_KEY": "secret",
    "ANTHROPIC_API_KEY": "sk-ant-xxx",
}


def test_required_present_loads() -> None:
    s = load_settings(dict(FULL))
    assert s.get("APCA_API_KEY_ID") == "PKxxx"
    assert set(s.missing_optional) == set(OPTIONAL_KEYS)  # none provided -> all degraded


def test_missing_required_raises() -> None:
    with pytest.raises(MissingCredentialError):
        load_settings({"APCA_API_KEY_ID": "x"})


def test_empty_required_value_treated_as_missing() -> None:
    with pytest.raises(MissingCredentialError):
        load_settings({**FULL, "ANTHROPIC_API_KEY": ""})


def test_optional_present_not_in_missing() -> None:
    s = load_settings({**FULL, "TAVILY_API_KEY": "tvly-x"})
    assert "TAVILY_API_KEY" not in s.missing_optional
    assert s.get("TAVILY_API_KEY") == "tvly-x"
    assert s.get("POLYGON_API_KEY") is None


def test_read_dotenv(tmp_path: Path) -> None:
    p = tmp_path / ".env"
    p.write_text(
        "# comment\n" "APCA_API_KEY_ID=PKabc\n" 'QUOTED="hello"\n' "BLANK=\n" "\n" "NOEQUALSLINE\n"
    )
    d = read_dotenv(p)
    assert d["APCA_API_KEY_ID"] == "PKabc"
    assert d["QUOTED"] == "hello"
    assert d["BLANK"] == ""
    assert "NOEQUALSLINE" not in d


def test_read_dotenv_missing_file(tmp_path: Path) -> None:
    assert read_dotenv(tmp_path / "nope.env") == {}


def test_dotenv_then_load(tmp_path: Path) -> None:
    p = tmp_path / ".env"
    p.write_text("APCA_API_KEY_ID=PK\nAPCA_API_SECRET_KEY=sec\nANTHROPIC_API_KEY=sk\n")
    s = load_settings(read_dotenv(p))
    assert s.get("APCA_API_SECRET_KEY") == "sec"
