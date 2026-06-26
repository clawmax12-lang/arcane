"""C3 — console INBOUND AUTH + update-shape whitelist (Inc-8 PART B).

The console processes an inbound update ONLY if it is a private-chat, NON-forwarded ``message`` with
a string ``text`` whose ``chat.id`` equals the operator's ``TELEGRAM_CHAT_ID``. Everything else — a
foreign chat_id, a forwarded message, an ``edited_message`` / ``channel_post`` / ``callback_query``,
a group chat, a non-text message, a shapeless update — is DROPPED (returns ``None``), before
sanitize, before the LLM, before any command. A non-operator is never replied to (no prober oracle).
"""

from __future__ import annotations

from trading.console.authz import extract_authorized

_OP = "123456789"


def _update(uid: int, **msg: object) -> dict[str, object]:
    base: dict[str, object] = {"chat": {"id": int(_OP), "type": "private"}, "text": "hej"}
    base.update(msg)
    return {"update_id": uid, "message": base}


def test_operator_private_text_message_is_accepted() -> None:
    got = extract_authorized(_update(10), _OP)
    assert got is not None
    assert got.update_id == 10
    assert got.text == "hej"


def test_foreign_chat_id_is_dropped() -> None:
    u = {"update_id": 11, "message": {"chat": {"id": 999, "type": "private"}, "text": "/flatta"}}
    assert extract_authorized(u, _OP) is None


def test_forwarded_message_is_dropped() -> None:
    for fwd in ("forward_origin", "forward_from", "forward_date", "forward_sender_name"):
        u = _update(12, **{fwd: "x", "text": "/flatta"})
        assert extract_authorized(u, _OP) is None, f"{fwd} must drop the message"


def test_non_message_update_types_are_dropped() -> None:
    for key in ("edited_message", "channel_post", "edited_channel_post", "callback_query"):
        u = {"update_id": 13, key: {"chat": {"id": int(_OP), "type": "private"}, "text": "/flatta"}}
        assert extract_authorized(u, _OP) is None


def test_group_or_channel_chat_is_dropped() -> None:
    for ctype in ("group", "supergroup", "channel"):
        u = {"update_id": 14, "message": {"chat": {"id": int(_OP), "type": ctype}, "text": "hi"}}
        assert extract_authorized(u, _OP) is None


def test_non_text_message_is_dropped() -> None:
    u = {"update_id": 15, "message": {"chat": {"id": int(_OP), "type": "private"}, "photo": [{}]}}
    assert extract_authorized(u, _OP) is None


def test_message_with_a_non_dict_chat_is_dropped() -> None:
    u = {"update_id": 17, "message": {"chat": "not-an-object", "text": "/flatta"}}
    assert extract_authorized(u, _OP) is None


def test_shapeless_or_missing_update_id_is_dropped() -> None:
    assert extract_authorized({}, _OP) is None
    assert extract_authorized({"message": {"chat": {"id": int(_OP)}}}, _OP) is None  # no update_id
    assert extract_authorized({"update_id": "x", "message": {}}, _OP) is None  # non-int update_id


def test_chat_id_compared_as_string_so_int_or_str_config_both_work() -> None:
    # operator id configured as a string; telegram returns an int — must still match.
    assert extract_authorized(_update(16), "123456789") is not None
