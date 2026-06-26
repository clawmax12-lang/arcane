"""Console INBOUND AUTH + update-shape whitelist (Inc-8 PART B).

``extract_authorized`` returns the operator's message text iff the update is a private-chat,
NON-forwarded ``message`` with a string ``text`` whose ``chat.id`` equals the operator's
``TELEGRAM_CHAT_ID``; otherwise ``None`` (dropped). This is the single auth gate — a non-operator,
a forwarded message, an ``edited_message``/``channel_post``/``callback_query``, a group chat, or a
non-text/shapeless update never reaches sanitize, the LLM, or a command. A foreign chat is never
replied to (no oracle for a prober).
"""

from __future__ import annotations

from dataclasses import dataclass

#: Fields whose presence marks a message as forwarded — operator intent must be FIRST-PARTY.
_FORWARD_MARKERS = ("forward_origin", "forward_from", "forward_date", "forward_sender_name")


@dataclass(frozen=True, slots=True)
class InboundMessage:
    """An authenticated first-party operator message: its update_id + RAW (pre-sanitize) text."""

    update_id: int
    text: str


def extract_authorized(update: dict[str, object], operator_chat_id: str) -> InboundMessage | None:
    """Return the operator's first-party private text message, or ``None`` (dropped)."""
    update_id = update.get("update_id")
    if not isinstance(update_id, int):
        return None
    # ONLY a top-level ``message`` — never edited_message / channel_post / callback_query / etc.
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    # Forwarded content is not operator intent — drop it.
    if any(marker in message for marker in _FORWARD_MARKERS):
        return None
    chat = message.get("chat")
    if not isinstance(chat, dict):
        return None
    if chat.get("type") != "private":
        return None
    if str(chat.get("id")) != str(operator_chat_id):
        return None
    text = message.get("text")
    if not isinstance(text, str):
        return None
    return InboundMessage(update_id=update_id, text=text)
