"""Deploy-faithful text-model probe adapter (bd polyglot-pdf-u0kcc).

The secretary/validator probes historically called `generate_content` directly
with their OWN copy of the prompt. Those copies drift from production (the
secretary probe's SECRETARY_PROMPT predates the kind-A/B/C rubric in
backend/adapters/text_ai_gemini.py::SECRETARY_SI), so their verdicts describe a
different system. This module lets a probe drive the REAL production call --
`TextAIGemini.ask()` / `.validate()` with the shipped prompt, the shipped
stable-prefix + fresh-tail content order, and the shipped generate config (no
thinking_config on the lite path, so the model's API-default thinking applies)
-- while still recording what a probe needs and the adapter deliberately hides:

  - wall-clock latency of the model call (the adapter's _generate, not the
    caller's fail-open wrapper),
  - the raw response text (so a probe can tell a JSON-format failure from an
    honest empty verdict -- the adapter fail-opens both to the same value),
  - the transport error type, if any,
  - the usage counts, INCLUDING thoughts_token_count (thinking tokens bill at
    the OUTPUT rate but sit outside candidates_token_count) and
    cached_content_token_count (implicit-cache hits).

Usage (one record per call; safe under asyncio.gather because the record rides
a ContextVar, and every gathered coroutine runs in its own task context):

    ai = RecordingTextAI("gemini-3.1-flash-lite")
    rec = new_record()
    verdict = await ai.validate(payload)
    rec["latency_s"], rec["usage"]["thoughts"], rec["raw"], rec["error"]

The fallback chain is EMPTY on purpose: a probe measures ONE model, and a
silent fallback to a sibling would attribute the sibling's behavior to it.
"""

from __future__ import annotations

import contextvars
import math
import os
import time

from backend.adapters.text_ai_gemini import TextAIGemini

_CURRENT: contextvars.ContextVar = contextvars.ContextVar("lite_probe_record", default=None)

USAGE_KEYS = {
    "prompt": "prompt_token_count",
    "cached": "cached_content_token_count",
    "output": "candidates_token_count",
    "thoughts": "thoughts_token_count",
    "total": "total_token_count",
}


def new_record() -> dict:
    """Start a fresh per-call record in the CURRENT task context and return it.
    Call it immediately before the adapter call it describes."""
    rec = {"latency_s": None, "raw": None, "error": None, "usage": None, "model": None}
    _CURRENT.set(rec)
    return rec


def usage_dict(usage_metadata) -> dict:
    """Flatten the usage fields a cost/caching analysis needs (None -> 0)."""
    return {k: int(getattr(usage_metadata, attr, 0) or 0) for k, attr in USAGE_KEYS.items()}


class RecordingTextAI(TextAIGemini):
    """TextAIGemini on Vertex with an empty fallback chain that records each
    call into the current task's record (see new_record)."""

    def __init__(self, model: str, location: str | None = None):
        super().__init__(
            model=model,
            vertexai=True,
            project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
            location=location or os.environ.get("VERTEX_LOCATION",
                                                TextAIGemini.DEFAULT_VERTEX_LOCATION),
            fallback_models=(),
        )

    async def _generate(self, *args, **kwargs):
        rec = _CURRENT.get()
        t0 = time.perf_counter()
        try:
            raw = await super()._generate(*args, **kwargs)
            if rec is not None:
                rec["raw"] = raw
            return raw
        except Exception as exc:  # noqa: BLE001 -- recorded, then re-raised
            if rec is not None:
                rec["error"] = type(exc).__name__
                rec["error_code"] = getattr(exc, "code", None)
            raise
        finally:
            if rec is not None:
                rec["latency_s"] = time.perf_counter() - t0

    def _log_usage(self, usage_metadata, model=None, **kwargs):
        rec = _CURRENT.get()
        if rec is not None and usage_metadata is not None:
            rec["usage"] = usage_dict(usage_metadata)
            rec["model"] = model or self._model_name
        return super()._log_usage(usage_metadata, model=model, **kwargs)


def pct(values: list, p: float):
    """Nearest-rank percentile (p in 0..100) of a non-empty list, else None."""
    xs = sorted(v for v in values if v is not None)
    if not xs:
        return None
    k = max(0, min(len(xs) - 1, math.ceil(p / 100.0 * len(xs)) - 1))
    return xs[k]
