"""Runtime settings — required credentials fail fast, optional ones degrade (spec F1).

Required keys (the system cannot operate without them) raise on absence; optional keys
(deferred integrations) resolve to None and are reported in ``missing_optional`` so the
system can run degraded rather than crash. Reads from an injected mapping (``os.environ``
by default) so it is fully testable and never silently trusts a half-configured env.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from trading.risk.errors import ArcaneError

_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # .../Trade (repo root; where .env lives)

REQUIRED_KEYS: tuple[str, ...] = (
    "APCA_API_KEY_ID",
    "APCA_API_SECRET_KEY",
    "ANTHROPIC_API_KEY",
)
OPTIONAL_KEYS: tuple[str, ...] = (
    "TAVILY_API_KEY",
    "FIRECRAWL_API_KEY",
    "APIFY_TOKEN",
    "POLYGON_API_KEY",
    "FRED_API_KEY",
    "DISCORD_WEBHOOK_URL",
    "GITHUB_TOKEN",
)


class MissingCredentialError(ArcaneError):
    """Raised when a REQUIRED credential is absent (fail-fast)."""


@dataclass(frozen=True, slots=True)
class Settings:
    required: Mapping[str, str]
    optional: Mapping[str, str | None]
    missing_optional: tuple[str, ...]

    def get(self, key: str) -> str | None:
        if key in self.required:
            return self.required[key]
        return self.optional.get(key)


def read_dotenv(path: str | Path) -> dict[str, str]:
    """Minimal .env parser (KEY=VALUE; ignores comments/blank lines; strips quotes)."""
    result: dict[str, str] = {}
    p = Path(path)
    if not p.exists():
        return result
    for raw_line in p.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        if key:
            result[key] = value
    return result


def load_settings(
    env: Mapping[str, str] | None = None, *, dotenv_path: Path | None = None
) -> Settings:
    """Validate required credentials; report missing optional ones for degraded mode.

    With no explicit ``env``, values come from the process environment LAYERED OVER the project
    ``.env`` (real env vars win), so the documented ``pytest -m live`` / script path authenticates
    from ``.env`` without a manual ``source``. Passing ``env=`` (tests) bypasses ``.env`` entirely.
    """
    src: Mapping[str, str]
    if env is not None:
        src = env
    else:
        path = dotenv_path if dotenv_path is not None else _PROJECT_ROOT / ".env"
        src = {**read_dotenv(path), **os.environ}

    missing_required = [k for k in REQUIRED_KEYS if not src.get(k)]
    if missing_required:
        raise MissingCredentialError("missing required credentials: " + ", ".join(missing_required))

    required = {k: src[k] for k in REQUIRED_KEYS}
    optional: dict[str, str | None] = {k: (src.get(k) or None) for k in OPTIONAL_KEYS}
    missing_optional = tuple(k for k in OPTIONAL_KEYS if optional[k] is None)
    return Settings(required=required, optional=optional, missing_optional=missing_optional)
