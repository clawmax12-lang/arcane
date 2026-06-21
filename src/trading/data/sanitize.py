"""§4.2 sanitization — the M13 prompt-injection defense for ALL external text.

Hardened across two red-team passes (wf_453c8909-dd7, wf_ca053231-9e9). It:
  * strips the FULL invisible/format class (every Unicode category Cf + known fillers)
    so split-by-invisible attacks collapse back to the keyword;
  * removes HTML comments with an EMPTY replacement (so they cannot create a split);
  * matches role markers tolerant of interstitial characters, anchored to line starts so
    a benign mid-sentence "the new system:" is not redacted;
  * folds Cyrillic/Greek homoglyphs to Latin before the collapsed-form check, defeating
    confusable evasion ("prеvious");
  * requires an imperative injection verb to co-occur with an instruction signature
    before redacting via the collapsed path, so benign prose ("previous instructions from
    the board were unclear") is not over-redacted.

Guarantees relied on downstream (re-verified by tests):
  * Idempotent: ``sanitize(sanitize(x)) == sanitize(x)``.
  * Fail-closed: any exception yields ``""``.

This is DEFENSE IN DEPTH, not a guarantee. Per ADR-001 §4.3, only HARD/STRUCTURED data
may trigger a runtime gate; sanitized free text is treated as evidence, never as a command.
"""

from __future__ import annotations

import re
import unicodedata

MAX_LEN = 10_000
_REDACTED = "[REDACTED]"
_TRUNCATED_SUFFIX = " [TRUNCATED]"

# Invisible/format characters NFKC does not remove, beyond category Cf (joiners, fillers).
_EXTRA_INVISIBLE: frozenset[int] = frozenset(
    {0x034F, 0x115F, 0x1160, 0x17B4, 0x17B5, 0x180E, 0x3164, 0xFFA0}
)

# Latin look-alikes of Cyrillic/Greek letters, folded before the collapsed-form check so a
# confusable inside a keyword cannot evade the signature detector.
_HOMOGLYPHS = str.maketrans(
    {
        "а": "a",
        "е": "e",
        "о": "o",
        "р": "p",
        "с": "c",
        "у": "y",
        "х": "x",
        "і": "i",
        "ј": "j",
        "ѕ": "s",
        "ԁ": "d",
        "һ": "h",
        "ο": "o",
        "α": "a",
        "ε": "e",
        "ρ": "p",
        "ι": "i",
        "ν": "v",
        "υ": "u",
        "κ": "k",
        "τ": "t",
        "χ": "x",
        "օ": "o",  # Armenian small oh (best-effort; a full TR39 confusables table is future work)
    }
)

# Leetspeak digit/symbol folds — applied ONLY inside the collapse path (not passthrough text).
_LEET = str.maketrans(
    {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"}
)

_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"ignore\s+(all\s+|the\s+|any\s+)?(previous|prior|above|earlier)\s+"
        r"(instructions|messages|prompts)",
        re.I,
    ),
    re.compile(
        r"disregard\s+(all\s+|the\s+)?(previous|prior|above)\s+(instructions|messages)",
        re.I,
    ),
    re.compile(r"<\|[^>]*\|>"),
    # Tightened: bare verbs require an injection-context object to avoid benign matches
    # ("act as though", "pretend nothing happened").
    re.compile(
        r"\b(?:role[\s_-]?play\s+as"
        r"|pretend\s+(?:to\s+be|you(?:'re|\s+are)|that\s+you)"
        r"|act\s+as\s+(?:an?\s+)?(?:ai|assistant|model|bot|system|dan|admin|root|developer"
        r"|expert|language\s+model)"
        r"|you\s+are\s+now\s+(?:an?\s+|the\s+)?(?:ai|assistant|model|bot|dan|admin|root))\b",
        re.I,
    ),
    re.compile(
        r"(ignorera|bortse\s+från)\s+(alla\s+|de\s+)?(tidigare|föregående|ovanstående)\s+"
        r"(instruktioner|meddelanden)",
        re.I,
    ),
    re.compile(
        r"(låtsas\s+(?:att\s+du|du)|agera\s+som\s+(?:en\s+|ett\s+)?(?:ai|assistent|system)"
        r"|du\s+är\s+nu\s+(?:en\s+|ett\s+)?(?:ai|assistent))",
        re.I,
    ),
)

_SEP = r"[ \t._\-]*"


def _spaced(word: str) -> str:
    return _SEP.join(re.escape(ch) for ch in word)


# Role markers tolerant of interstitial chars, anchored to a line start (avoids redacting a
# benign mid-sentence label like "the new system: a faster engine").
_ROLE_SPACED = re.compile(
    r"(?m)^[ \t>*\-]*(?:"
    + "|".join(_spaced(w) for w in ("system", "assistant", "user"))
    + r")[ \t]*:",
    re.I,
)
_URL = re.compile(r"https?://\S+", re.I)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_LONG_BLOB = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")
_LONG_HEX = re.compile(r"[0-9a-fA-F]{40,}")
_WHITESPACE = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

# An instruction signature only redacts via the collapsed path when an imperative
# injection verb also appears, so benign mentions of "previous instructions" are kept.
_COLLAPSED_SIGNATURES: tuple[str, ...] = (
    "previousinstruction",
    "priorinstruction",
    "earlierinstruction",
    "aboveinstruction",
    "tidigareinstruktion",
    "foregaendeinstruktion",
    "ovanstaendeinstruktion",
)
_IMPERATIVE_INJECTION: tuple[str, ...] = (
    "ignore",
    "disregard",
    "forget",
    "override",
    "bypass",
    "ignorera",
    "bortse",
    "strunta",
    "forbiga",
)


def _strip_invisibles(s: str) -> str:
    return "".join(
        ch for ch in s if unicodedata.category(ch) != "Cf" and ord(ch) not in _EXTRA_INVISIBLE
    )


def _ascii_collapse(s: str) -> str:
    folded = unicodedata.normalize("NFKD", s)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    folded = folded.lower().translate(_HOMOGLYPHS).translate(_LEET)
    return _NON_ALNUM.sub("", folded)


def sanitize(text: str) -> str:
    """Return a sanitized, injection-neutralized version of ``text`` (fail-closed)."""
    try:
        s = unicodedata.normalize("NFKC", text)
        s = _strip_invisibles(s)
        s = _HTML_COMMENT.sub("", s)  # empty: must not create a split
        s = _URL.sub("[URL]", s)
        s = _LONG_BLOB.sub("[BLOB]", s)
        s = _LONG_HEX.sub("[HEX]", s)
        s = _ROLE_SPACED.sub(_REDACTED, s)
        for pattern in _INJECTION_PATTERNS:
            s = pattern.sub(_REDACTED, s)
        # Defense in depth: catch split/homoglyph-evaded phrases via the collapsed form,
        # but only when an imperative injection verb co-occurs (avoids over-redaction).
        if _REDACTED not in s:
            collapsed = _ascii_collapse(s)
            if any(sig in collapsed for sig in _COLLAPSED_SIGNATURES) and any(
                verb in collapsed for verb in _IMPERATIVE_INJECTION
            ):
                s = f"{s} {_REDACTED}"
        s = _WHITESPACE.sub(" ", s).strip()
        if len(s) > MAX_LEN:
            s = s[: MAX_LEN - len(_TRUNCATED_SUFFIX)] + _TRUNCATED_SUFFIX
        return s
    except Exception:
        return ""
