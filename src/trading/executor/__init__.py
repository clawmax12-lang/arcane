"""Deterministic execution core.

PHI1 (CLAUDE.md §0): the LLM is NEVER in the order submit path. No module in this
package may import an LLM/agent client (an import-guard test enforces this in a later
increment). The Alpaca client hardcodes ``paper=True``; the LIVE_MODE triple-lock gate
must be fully open before any live submission is even representable.
"""

from __future__ import annotations
