import json
import os

import structlog
from google import genai
from google.genai import types

from backend.ports.text_ai_port import ITextAI


class TextAIGemini(ITextAI):
    """Adapter for cheap text-generation calls via the Gemini API.

    Mirrors LiveAIGemini's constructor convention (same three-way client
    construction: Vertex ADC / AI-Studio api_key / bare test fallback).
    Calls client.aio.models.generate_content (NOT the Live bidi path).

    Caching design: every call is split into a stable_prefix (secretary SI +
    field catalog -- rarely changes, should hit the implicit cache after the
    first call) and a fresh_tail (current values + query -- changes every
    call). The adapter concatenates them internally. Upgrade to explicit
    client.caches.create() caching is contained in _generate() once Gate 2
    (jnjj.27) establishes the token minimum and confirms latency savings.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-2.5-flash-lite",
        vertexai: bool = False,
        project: str | None = None,
        location: str = "us-central1",
    ):
        self._client = None
        self._model_name = model
        self._vertexai = vertexai
        self._project = project
        self._location = location
        self._api_key = api_key

        # Mirror LiveAIGemini: warn loudly on a misconfigured AI Studio path.
        if not vertexai and api_key is None:
            try:
                structlog.get_logger().warning(
                    "text_ai_no_api_key_on_ai_studio_path",
                    detail=(
                        "vertexai=False (AI Studio) but no API key; client will "
                        "fall back to ADC and likely fail. Set GEMINI_API_KEY or "
                        "VERTEXAI=true."
                    ),
                )
            except Exception:
                pass

        try:
            ClientCls = getattr(genai, "Client", None)
            if ClientCls is not None:
                if vertexai:
                    self._client = ClientCls(
                        vertexai=True,
                        project=project or os.getenv("GOOGLE_CLOUD_PROJECT"),
                        location=location,
                    )
                elif api_key is not None:
                    self._client = ClientCls(api_key=api_key)
                else:
                    self._client = ClientCls()
        except Exception:
            self._client = None

        self._log = structlog.get_logger().bind(
            adapter="TextAIGemini",
            model=self._model_name,
            vertexai=self._vertexai,
        )

    # ------------------------------------------------------------------
    # ITextAI implementation
    # ------------------------------------------------------------------

    async def validate(self, payload: dict) -> dict:
        """Run contradiction check via flash-lite.

        payload keys (from validation-delegation.md contract 2):
          stable_prefix: list of str/Part -- secretary SI + field catalog
          fresh_tail:    list of str/Part -- current values + query text

        Returns contract-1 verdict {"conflicts": [...]} or fail-open {"conflicts": []}.
        PII rule: never log payload content, field values, or reason text.
        """
        if self._client is None:
            self._log.warning("text_ai_no_client_validate_fail_open")
            return {"conflicts": []}

        if not isinstance(payload, dict):
            self._log.warning("text_ai_validate_bad_payload_fail_open")
            return {"conflicts": []}

        stable_prefix = payload.get("stable_prefix", [])
        fresh_tail = payload.get("fresh_tail", [])

        raw = ""
        try:
            # Coerce field_count to int inside the guarded block; skip if invalid
            # so a bad optional telemetry value never propagates as an exception.
            raw_field_count = payload.get("field_count", None)
            try:
                field_count = int(raw_field_count) if raw_field_count is not None else None
            except (ValueError, TypeError):
                field_count = None

            raw = await self._generate(
                stable_prefix=stable_prefix,
                fresh_tail=fresh_tail,
                response_mime_type="application/json",
            )
            verdict = json.loads(raw)
            conflicts = verdict.get("conflicts", [])
            if not isinstance(conflicts, list):
                self._log.warning(
                    "text_ai_validate_bad_conflicts_type_fail_open",
                    conflicts_type=type(conflicts).__name__,
                )
                return {"conflicts": []}
            # Shallow per-item check: each conflict must be a dict (B3 enforces
            # the full field_ids/reason shape when consuming the verdict).
            if not all(isinstance(c, dict) for c in conflicts):
                self._log.warning("text_ai_validate_bad_conflict_items_fail_open")
                return {"conflicts": []}
            self._log.info(
                "text_ai_validate_complete",
                conflict_count=len(conflicts),
                field_count=field_count,
            )
            return {"conflicts": conflicts}
        except json.JSONDecodeError:
            self._log.warning(
                "text_ai_validate_parse_error_fail_open",
                raw_length=len(raw) if isinstance(raw, str) else None,
            )
            return {"conflicts": []}
        except Exception as exc:
            self._log.warning(
                "text_ai_validate_error_fail_open",
                exc_type=type(exc).__name__,
            )
            return {"conflicts": []}

    async def ask(self, query: str, context: dict) -> str:
        """Secretary query -- NOT YET IMPLEMENTED (A-pillar secretary bead).

        Stub raises NotImplementedError so callers that attempt to use this
        before the secretary bead ships get a clear failure, not a silent
        no-op. The port contract + fail-open semantics will be wired here.
        """
        raise NotImplementedError(
            "ask() is implemented in the A-pillar secretary bead "
            "(polyglot-pdf-jnjj secretary task); not available yet."
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _generate(
        self,
        stable_prefix: list,
        fresh_tail: list,
        system_instruction: str | None = None,
        response_mime_type: str | None = None,
    ) -> str:
        """Core generate_content call shared by validate() and future ask().

        Concatenates stable_prefix + fresh_tail so the leading token sequence
        is stable across calls -- the precondition for Gemini's implicit cache
        to fire. Logs cached_content_token_count from usage_metadata on every
        call so we can confirm the cache is hitting without flying blind.

        Raises on API error; callers wrap in try/except for fail-open.
        """
        contents = list(stable_prefix) + list(fresh_tail)

        config_kwargs: dict = {}
        if system_instruction is not None:
            config_kwargs["system_instruction"] = system_instruction
        if response_mime_type is not None:
            config_kwargs["response_mime_type"] = response_mime_type

        config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

        call_kwargs: dict = {
            "model": self._model_name,
            "contents": contents,
        }
        if config is not None:
            call_kwargs["config"] = config

        response = await self._client.aio.models.generate_content(**call_kwargs)

        self._log_usage(response.usage_metadata)

        return response.text or ""

    def _log_usage(self, usage_metadata) -> None:
        """Log token counts and cache-hit status. Never logs content."""
        if usage_metadata is None:
            return
        cached_tokens = getattr(usage_metadata, "cached_content_token_count", 0) or 0
        self._log.info(
            "text_ai_usage",
            prompt_tokens=getattr(usage_metadata, "prompt_token_count", None),
            cached_tokens=cached_tokens,
            output_tokens=getattr(usage_metadata, "candidates_token_count", None),
            cache_hit=(cached_tokens > 0),
        )
