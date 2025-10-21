"""Helpers to recover JSON objects embedded in model response parts.

The live AI adapter discovered many shapes where the model returned JSON
inside code fences or inside attributes such as `executable_code` or
`code_execution_result`. This module provides a shared, well-tested helper
that attempts a few heuristics to extract a JSON object from a string or
arbitrary object with textual attributes.
"""
from __future__ import annotations

from typing import Any, Optional
import json
import re


def extract_json_from_part(part: Any) -> Optional[dict]:
    """Attempt to extract a JSON object (dict) from `part`.

    Heuristics used (in order):
    - If `part` is a string, try to parse it directly or strip code fences.
    - If `part` is an object, look for common attributes: 'executable_code',
      'code_execution_result', 'code', 'execution', 'output', 'result', 'text',
      'display_text', 'response', 'arguments'. For each attribute, try to get
      a textual representation and parse JSON from it.
    - If a JSON substring exists (first '{' .. last '}'), attempt to decode that.

    Returns the parsed dict on success, otherwise None.
    """
    if part is None:
        return None

    candidate_attrs = [
        "executable_code",
        "code_execution_result",
        "code",
        "execution",
        "output",
        "result",
        "text",
        "display_text",
        "response",
        "arguments",
    ]

    def _try_parse_text(text: str) -> Optional[dict]:
        if not text or not isinstance(text, str):
            return None
        t = text.strip()
        # If wrapped in a code fence, extract the inner content
        m = re.search(r"```(?:[\w+-]*)\n([\s\S]*?)\n```", t)
        if m:
            candidate = m.group(1).strip()
        else:
            # fallback: substring from first '{' to last '}'
            start = t.find("{")
            end = t.rfind("}")
            if start != -1 and end != -1 and end > start:
                candidate = t[start : end + 1]
            else:
                candidate = t

        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return None
        return None

    # If passed a plain string, try that first
    if isinstance(part, str):
        return _try_parse_text(part)

    # If object-like, try candidate attributes
    for attr in candidate_attrs:
        try:
            v = getattr(part, attr, None)
        except Exception:
            v = None
        if not v:
            continue
        if isinstance(v, str):
            parsed = _try_parse_text(v)
            if parsed:
                return parsed
        else:
            # For non-str, try to get textual 'text' attribute or str()
            text = getattr(v, "text", None) or str(v)
            parsed = _try_parse_text(text)
            if parsed:
                return parsed

    # As a last-ditch, try stringifying the whole part
    try:
        s = str(part)
        return _try_parse_text(s)
    except Exception:
        return None
