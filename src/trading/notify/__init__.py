"""Operator notifications — the §5 Murphy pager + §1.1 daily-report transport (Telegram).

This is ARCANE's disaster-recovery channel: a RED Murphy page that cannot be delivered RE-RAISES
rather than failing silently. All outbound text is §4.2-sanitized and the bot token is never logged.
See ``docs/INCREMENT-5-DESIGN.md`` §C.1.
"""

from __future__ import annotations

from trading.notify.errors import NotifierError, NotifierMisconfiguredError
from trading.notify.telegram import (
    Severity,
    TelegramNotifier,
    build_notifier,
    resolve_chat_id,
)

__all__ = [
    "NotifierError",
    "NotifierMisconfiguredError",
    "Severity",
    "TelegramNotifier",
    "build_notifier",
    "resolve_chat_id",
]
