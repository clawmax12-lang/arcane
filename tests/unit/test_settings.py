"""Tests for runtime settings: required fail-fast, optional graceful degradation."""

from __future__ import annotations

from pathlib import Path

import pytest

from trading.settings import (
    DEFAULT_AGENT_MODEL,
    DEFAULT_CONVERSATION_MODEL,
    OPTIONAL_KEYS,
    MissingCredentialError,
    load_model_settings,
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


def test_load_settings_reads_dotenv_when_no_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No explicit env -> values come from .env (layered under the real environment), so the
    # documented `pytest -m live` path authenticates without a manual `source .env`.
    p = tmp_path / ".env"
    p.write_text("APCA_API_KEY_ID=PKfromfile\nAPCA_API_SECRET_KEY=sec\nANTHROPIC_API_KEY=sk\n")
    for k in ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    s = load_settings(dotenv_path=p)
    assert s.get("APCA_API_KEY_ID") == "PKfromfile"


def test_real_env_overrides_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / ".env"
    p.write_text("APCA_API_KEY_ID=FROMFILE\nAPCA_API_SECRET_KEY=sec\nANTHROPIC_API_KEY=sk\n")
    monkeypatch.setenv("APCA_API_KEY_ID", "FROMENV")  # real export must win over .env
    s = load_settings(dotenv_path=p)
    assert s.get("APCA_API_KEY_ID") == "FROMENV"


# ── Inc-8.5 PART B: model selection (conversation = Sonnet, agents = Haiku; configurable) ──


def test_model_defaults_are_sonnet_conversation_and_haiku_agents() -> None:
    conv, agent = load_model_settings({})  # nothing set -> the Inc-8.5 defaults
    assert conv == DEFAULT_CONVERSATION_MODEL == "claude-sonnet-4-6"
    assert agent == DEFAULT_AGENT_MODEL == "claude-haiku-4-5-20251001"


def test_console_model_id_overrides_conversation_only() -> None:
    conv, agent = load_model_settings({"CONSOLE_MODEL_ID": "claude-opus-4-8"})
    assert conv == "claude-opus-4-8"  # operator opted into Opus for the chat
    assert agent == DEFAULT_AGENT_MODEL  # the cheap structured agents stay Haiku


def test_agent_model_id_overrides_agents_only() -> None:
    conv, agent = load_model_settings({"AGENT_MODEL_ID": "claude-something-cheap"})
    assert conv == DEFAULT_CONVERSATION_MODEL
    assert agent == "claude-something-cheap"


def test_blank_model_ids_fall_back_to_defaults() -> None:
    conv, agent = load_model_settings({"CONSOLE_MODEL_ID": "", "AGENT_MODEL_ID": ""})
    assert (conv, agent) == (DEFAULT_CONVERSATION_MODEL, DEFAULT_AGENT_MODEL)


def test_model_id_keys_are_optional_and_never_fail_fast() -> None:
    # The model knobs degrade to defaults; their absence must not break load_settings.
    assert "CONSOLE_MODEL_ID" in OPTIONAL_KEYS
    assert "AGENT_MODEL_ID" in OPTIONAL_KEYS
    s = load_settings(dict(FULL))  # no model ids provided -> still loads
    assert s.get("CONSOLE_MODEL_ID") is None


def test_model_settings_read_dotenv_layered_under_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / ".env"
    p.write_text("CONSOLE_MODEL_ID=claude-from-file\n")
    monkeypatch.delenv("CONSOLE_MODEL_ID", raising=False)
    conv, _ = load_model_settings(dotenv_path=p)
    assert conv == "claude-from-file"  # .env is read when no explicit env is passed
    monkeypatch.setenv("CONSOLE_MODEL_ID", "claude-from-env")  # real export wins
    conv2, _ = load_model_settings(dotenv_path=p)
    assert conv2 == "claude-from-env"
