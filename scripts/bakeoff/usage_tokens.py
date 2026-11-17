"""Gemini usage -> the bake-off's token record (bd polyglot-pdf-nwnys).

Gemini reports THINKING tokens in `thoughts_token_count`, OUTSIDE
`candidates_token_count`, and bills them at the OUTPUT rate. The authoring-time
extraction arms run on gemini-2.5-pro, which cannot disable thinking, so a
record built from candidates_token_count alone under-states output (and so
cost). Every Gemini usage record in scripts/bakeoff goes through this one
function; backend/tests/unit/test_bakeoff_usage_tokens.py pins both the folding
and that no other bake-off module reads candidates_token_count directly.
"""

from __future__ import annotations


def gemini_usage_tokens(usage) -> dict:
    """Return {"input", "output", "thoughts"} from a usage_metadata object.

    "output" is the BILLED output: answer tokens + thinking tokens. "thoughts"
    keeps the split visible. A missing count reads as None for input and 0 for
    the output parts; if the answer count is missing the output is None too
    (an unknown, not a fabricated zero)."""
    answer = getattr(usage, "candidates_token_count", None)
    thoughts = getattr(usage, "thoughts_token_count", None) or 0
    return {
        "input": getattr(usage, "prompt_token_count", None),
        "output": None if answer is None else answer + thoughts,
        "thoughts": thoughts,
    }
