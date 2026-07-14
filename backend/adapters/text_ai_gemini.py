import json
import os

import structlog
from google import genai
from google.genai import types

from backend.ports.text_ai_port import ITextAI
from backend.services.secretary_context import (
    render_static_catalog,
    render_values_tail,
)

# Secretary system instruction -- the "find relevant fields -> copy values ->
# answer in prose" structure validated by the Gate-1 RECALL probe
# (backend/scripts/probe_secretary_recall.py SECRETARY_PROMPT) and reused by the
# Gate-2 latency probe. Kept here as a module constant so it is BYTE-STABLE: it
# leads the cacheable stable_prefix in ask(), and any per-call variation would
# break Gemini's implicit cache (bd polyglot-pdf-jnjj.45, maintainer 2026-06-27).
# The form catalog + the prose question are appended by ask(); this is the
# behavioral rubric only (no form data), so it never changes within a session.
SECRETARY_SI = (
    "You are the SECRETARY for a USCIS immigration form-filling assistant. A "
    "colleague (the voice assistant talking to the applicant) asks you prose "
    "questions about the form. You hold the form's fields and the applicant's "
    "current answers below.\n\n"
    "Each field shows: its id, spoken name, type, current value (or <empty>), and "
    "whether it is shown (applicable) to this applicant. A field can be shown but "
    "<empty> (applicable, not answered yet) OR not shown (not applicable to this "
    "applicant) -- treat these as DIFFERENT.\n\n"
    "Answer the colleague's question. Work in this order:\n"
    "1. Find ALL fields relevant to the question (there may be several).\n"
    "2. Copy their current values.\n"
    "3. Answer in natural, brief prose using ONLY those values. If a relevant "
    "field is <empty> but applicable, say it has not been answered yet. If it is "
    "not applicable to this applicant, say so. If the question is genuinely "
    "ambiguous across several fields, either answer for all of them and name each, "
    "or ask a short clarifying question. NEVER invent a value that is not shown.\n\n"
    "Return JSON ONLY, no other text:\n"
    '{"answer": "<your prose answer>", "sourced_from": ["<field_id>", ...]}\n'
    "Put in sourced_from the exact field ids you used to answer (the fields whose "
    "values your answer is grounded in). Use ids exactly as shown."
)


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

    Model-fallback resilience (jnjj.42): a single cheap model can have a
    sustained outage (gemini-2.5-flash-lite was 503 UNAVAILABLE for 1hr+ on
    2026-06-25 while gemini-3.1-flash-lite answered fine). _generate() walks an
    ordered fallback chain -- the configured model, then DEFAULT_FALLBACK_MODELS
    -- on a transient AVAILABILITY error (5xx, or 404/429), so a single-model
    outage degrades to a sibling instead of failing the call. The chain stays
    WITHIN THE LITE TIER on purpose (cost discipline -- the full gemini-flash
    model is far pricier and is NOT an acceptable fallback for this cheap path);
    if the whole lite chain is exhausted the error is LOGGED and re-raised for the
    caller's fail-open, never escalated to a pricier model (maintainer 2026-06-27).
    All chain members are Gemini, so the BAA constraint (Gemini-only) holds.
    Non-transient errors (auth/config 4xx) are logged (PII-free) and fail fast --
    NOT masked. The model that served the call is logged (model=, is_fallback=).
    """

    # Ordered fallback models tried after the configured one. LITE TIER ONLY (cost
    # discipline -- never gemini-flash-latest / full Flash). gemini-3.1-flash-lite
    # is a real, valid model id; gemini-flash-lite-latest was REMOVED (2026-06-27)
    # -- it is NOT a valid model string (the only `-latest` rolling aliases are
    # gemini-flash-latest / gemini-pro-latest, neither of which is the lite tier),
    # so it would 404 if ever reached.
    DEFAULT_FALLBACK_MODELS = (
        "gemini-3.1-flash-lite",
    )

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-2.5-flash-lite",
        vertexai: bool = False,
        project: str | None = None,
        location: str = "us-central1",
        fallback_models: tuple | list | None = None,
        thinking_budget: int | None = None,
    ):
        self._client = None
        self._model_name = model
        self._vertexai = vertexai
        self._project = project
        self._location = location
        self._api_key = api_key
        # W6 (bd polyglot-pdf-gbus): an optional bounded thinking budget for the
        # 2.5-pro whole-form validator. None (the lite-tier default) sends NO
        # thinking_config, so the lite path is byte-for-byte unchanged (its
        # implicit-cache prefix stays stable). A set budget wires a
        # types.ThinkingConfig(thinking_budget=N) into the generate config -- the
        # W5-measured shape (budget 512; 2.5-pro cannot disable thinking).
        self._thinking_budget = thinking_budget

        # Ordered, de-duplicated model chain: configured model first, then the
        # fallbacks (defaults if not overridden), dropping the configured model
        # if it reappears in the fallback list.
        fb = list(self.DEFAULT_FALLBACK_MODELS if fallback_models is None
                  else fallback_models)
        self._model_chain = [model] + [m for m in fb if m != model]

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

    async def ask(self, query: str, context: dict) -> tuple[str, list[dict]]:
        """Secretary query (bd polyglot-pdf-jnjj.45b): map a prose question about
        the form to a prose answer, using the cheap text model.

        context (assembled by the ask_secretary handler, jnjj.45c):
          schema:       full form schema (the whole form catalog, supplied by the
                        client at handshake and cached in-session)
          field_values: flat {field_id: value | {value, confirmed}} current state
          shown_map:    {field_id: bool} applicability (SEPARATE from value)

        Request shape (maintainer 2026-06-27): the secretary is the TEXT model --
        every call resends the FULL SI + context (no server-side memory). The
        request is built so Gemini's implicit cache (~1/10 rate) fires:
          stable_prefix = [SECRETARY_SI + render_static_catalog(schema)]
                          -- BYTE-STABLE within a session (never mutated); the
                          cacheable prefix.
          fresh_tail    = [render_values_tail(...) + the prose query]
                          -- small, fresh, APPEND-ONLY. _generate concatenates
                          prefix + tail, so the leading bytes stay identical
                          call-to-call even as values change.

        Returns (answer, sources): `answer` is the secretary's PROSE answer; `sources`
        is a list of {"field_id", "spoken_name"} dicts resolved from the model's
        `sourced_from` field-id list against the schema (bd polyglot-pdf-2af7/3vby --
        lets the voice model hand an EXACT field id to switch_to_field instead of
        guessing from memory). Ids not present in the schema are dropped; the list is
        de-duped (order preserved) and capped at 8 entries. Fail-open: on missing
        client / bad context / API or parse error, returns ("", []) so the principal
        asks the user directly (ITextAI.ask contract).

        PII: logs field ids/counts/model only -- NEVER the query, the rendered
        context/values, the answer prose, or spoken names (callback_handler PII
        discipline; validation-delegation contract 6).
        """
        if self._client is None:
            self._log.warning("text_ai_no_client_ask_fail_open")
            return "", []

        if not isinstance(context, dict):
            self._log.warning("text_ai_ask_bad_context_fail_open")
            return "", []

        schema = context.get("schema")
        if not isinstance(schema, dict) or not schema.get("fields"):
            # No catalog to ground the answer in -- cannot retrieve; fail open.
            self._log.warning("text_ai_ask_no_schema_fail_open")
            return "", []

        field_values = context.get("field_values") or {}
        shown_map = context.get("shown_map") or {}

        raw = ""
        try:
            # stable_prefix: SECRETARY_SI + value-free catalog. Kept byte-stable so
            # implicit caching keys on it (the maintainer's append-only invariant).
            stable_prefix = [
                SECRETARY_SI
                + "\n\n"
                + render_static_catalog(schema)
            ]
            # fresh_tail: current values + applicability, then the prose query,
            # APPENDED after the stable prefix.
            fresh_tail = [
                render_values_tail(schema, field_values, shown_map)
                + "\n\nQUESTION: "
                + str(query)
            ]

            raw = await self._generate(
                stable_prefix=stable_prefix,
                fresh_tail=fresh_tail,
                response_mime_type="application/json",
            )
            verdict = json.loads(raw)
            answer = verdict.get("answer", "")
            sourced = verdict.get("sourced_from", [])
            if not isinstance(answer, str):
                answer = str(answer)
            sources = self._resolve_sources(schema, sourced)
            self._log.info(
                "text_ai_ask_complete",
                # ids/counts only -- never the query/answer/values/spoken names.
                sourced_field_ids=[str(x) for x in sourced][:10]
                if isinstance(sourced, list) else [],
                sourced_count=len(sourced) if isinstance(sourced, list) else 0,
                resolved_source_count=len(sources),
                answer_len=len(answer),
            )
            return answer, sources
        except json.JSONDecodeError:
            self._log.warning(
                "text_ai_ask_parse_error_fail_open",
                raw_length=len(raw) if isinstance(raw, str) else None,
            )
            return "", []
        except Exception as exc:  # noqa: BLE001
            self._log.warning(
                "text_ai_ask_error_fail_open",
                exc_type=type(exc).__name__,
            )
            return "", []

    @staticmethod
    def _resolve_sources(schema: dict, sourced_from) -> list[dict]:
        """Resolve the model's sourced_from field-id list against the schema.

        Returns a list of {"field_id": <str>, "spoken_name": <str>} for each id
        that exists in schema["fields"] (matched by field["id"]); ids not found
        in the schema are dropped. De-duped by field_id (first occurrence wins,
        order preserved), capped at 8 entries.
        """
        if not isinstance(sourced_from, list):
            return []

        by_id = {}
        for field in schema.get("fields", []):
            if isinstance(field, dict) and field.get("id") is not None:
                by_id[str(field["id"])] = field

        sources: list[dict] = []
        seen: set = set()
        for raw_id in sourced_from:
            field_id = str(raw_id)
            if field_id in seen:
                continue
            field = by_id.get(field_id)
            if field is None:
                continue
            spoken_name = field.get("spoken_name") or field.get("name") or field_id
            sources.append({"field_id": field_id, "spoken_name": spoken_name})
            seen.add(field_id)
            if len(sources) >= 8:
                break
        return sources

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

        Walks the model-fallback chain (jnjj.42): on a transient AVAILABILITY
        error (5xx ServerError, or 404/429 ClientError) it tries the next model;
        a non-transient error (auth/config 4xx, or the last model failing) is
        re-raised so callers' fail-open path handles it. Logs which model served.

        Raises on API error; callers wrap in try/except for fail-open.
        """
        contents = list(stable_prefix) + list(fresh_tail)

        config_kwargs: dict = {}
        if system_instruction is not None:
            config_kwargs["system_instruction"] = system_instruction
        if response_mime_type is not None:
            config_kwargs["response_mime_type"] = response_mime_type
        # W6 (bd polyglot-pdf-gbus): bounded thinking for the 2.5-pro whole-form
        # validator (W5 config). None (the lite default) sends no thinking_config,
        # leaving the lite path unchanged. Applies to every model in the chain, but
        # the pro validator is constructed with an EMPTY fallback chain, so this only
        # ever configures the single pro model.
        if self._thinking_budget is not None:
            config_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_budget=self._thinking_budget
            )

        config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

        last_exc: Exception | None = None
        for i, model_name in enumerate(self._model_chain):
            call_kwargs: dict = {"model": model_name, "contents": contents}
            if config is not None:
                call_kwargs["config"] = config
            try:
                response = await self._client.aio.models.generate_content(**call_kwargs)
                if i > 0:
                    self._log.warning(
                        "text_ai_used_fallback_model",
                        model=model_name,
                        is_fallback=True,
                        requested=self._model_name,
                    )
                self._log_usage(response.usage_metadata, model=model_name,
                                is_fallback=(i > 0))
                return response.text or ""
            except Exception as exc:  # noqa: BLE001
                if self._is_transient_availability(exc) and i < len(self._model_chain) - 1:
                    self._log.warning(
                        "text_ai_model_unavailable_trying_fallback",
                        model=model_name,
                        exc_type=type(exc).__name__,
                    )
                    last_exc = exc
                    continue
                # Non-transient (auth/config 4xx) OR the LITE chain is exhausted.
                # Log it explicitly (PII-free: type + status code + model only, never
                # content) so an internal error -- a bad 4xx OR a full lite-tier
                # outage -- is VISIBLE to us before the caller fail-opens. We do NOT
                # escalate to a pricier model (cost discipline); we re-raise and the
                # caller's fail-open path serves the user-facing apology.
                code = getattr(exc, "code", None)
                self._log.error(
                    "text_ai_generate_failed",
                    model=model_name,
                    exc_type=type(exc).__name__,
                    status_code=code,
                    chain_exhausted=(i == len(self._model_chain) - 1),
                    transient=self._is_transient_availability(exc),
                )
                raise
        # Unreachable (the loop returns or raises), but satisfies type-checkers.
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("text_ai_generate_no_model_attempted")

    @staticmethod
    def _is_transient_availability(exc: Exception) -> bool:
        """True for errors that warrant trying the next model: 5xx ServerError
        (overload/outage) and 404/429 ClientError (model-not-found / rate-quota).
        False for auth/config 4xx (401/403/400) -- those must NOT be masked by a
        fallback, since every model would fail the same way."""
        if isinstance(exc, genai.errors.ServerError):
            return True
        if isinstance(exc, genai.errors.ClientError):
            # google-genai APIError always sets .code to the HTTP status int.
            code = getattr(exc, "code", None)
            return code in (404, 429)
        return False

    def _log_usage(self, usage_metadata, model: str | None = None,
                   is_fallback: bool = False) -> None:
        """Log token counts and cache-hit status. Never logs content."""
        if usage_metadata is None:
            return
        cached_tokens = getattr(usage_metadata, "cached_content_token_count", 0) or 0
        self._log.info(
            "text_ai_usage",
            model=model or self._model_name,
            is_fallback=is_fallback,
            prompt_tokens=getattr(usage_metadata, "prompt_token_count", None),
            cached_tokens=cached_tokens,
            output_tokens=getattr(usage_metadata, "candidates_token_count", None),
            cache_hit=(cached_tokens > 0),
        )
