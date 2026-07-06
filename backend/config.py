from __future__ import annotations

from functools import lru_cache
from pydantic import BaseModel, model_validator
import os
import re
from pathlib import Path


# === Native audio-to-audio model tiers (A/B-able) ===
# Both are full native audio-to-audio Live API models (bidiGenerateContent).
# USE_PREMIUM_MODEL flips between these (defaults FALSE -> standard/2.5):
#   standard -> gemini-2.5-flash-native-audio-preview-12-2025 (DEFAULT; reliably
#               emits the update_form_fields tool call; family 2.5)
#   premium  -> gemini-3.1-flash-live-preview            (opt-in; family 3.1)
# NOTE on 3.1 tool-calling: the historic "3.1 skips update_form_fields ~50%"
# finding (bd polyglot-pdf-5oq) was traced to the update_form_fields `value`
# param being declared with NO type -- under google-genai 2.8.0, 3.1 rejects an
# untyped required param (it verbalizes "I had an issue processing that value").
# With `value` typed as "string" (see TOOL_DECLARATIONS), 3.1 emits the call
# reliably (5/5, 2026-06-11, bd polyglot-pdf-i9q8). 2.5 tolerated the untyped
# param, which is why only 3.1 showed the defect.
# NOTE: Gemini model naming is inconsistent across Google's sources -- the 2.5
# native model also appears as `gemini-live-2.5-flash-preview` (the old MODEL_LIVE
# default), and that exact string 1008'd ("not found for bidiGenerateContent") in
# the contract test. We pin the explicit `-preview-12-2025` string above, which is
# verified to connect and return audio. Don't infer native-vs-cascade from a name;
# verify against the live endpoint. See docs/genai_docs/README.md.
MODEL_NATIVE_PREMIUM = "gemini-3.1-flash-live-preview"
MODEL_NATIVE_STANDARD = "gemini-2.5-flash-native-audio-preview-12-2025"
# Vertex publishes the 2.5 native-audio Live model under a DIFFERENT id than AI
# Studio: the AI Studio id above is NOT available on Vertex in any region (a Live
# bidiGenerateContent connect 1008s), and this Vertex id is not on AI Studio.
# Both are 2.5-family native-audio, so model_family() bills them identically; only
# the service-specific id differs. Verified connecting + returning audio on Vertex
# us-central1 (the adapter's default location), bd polyglot-pdf-a079. _resolve_model
# selects this when VERTEXAI=true and the standard tier is active, so a Vertex
# deploy works WITHOUT having to pin MODEL_NATIVE by hand. There is no Vertex 3.1
# (premium) id yet: 3.1 is AI-Studio-only as of 2026-06, so the premium tier still
# requires VERTEXAI=false.
MODEL_NATIVE_STANDARD_VERTEX = "gemini-live-2.5-flash-native-audio"

# --- DEV FEATURE: model A/B toggle (bd polyglot-pdf-kbf) -----------------------
# To A/B these two models for tool-call reliability (e.g. "does 3.1 emit
# update_form_fields less reliably than 2.5?"), flip USE_PREMIUM_MODEL and
# restart the backend -- each run is one clean sample. Locally, the dev runner
# does this for you:
#     ./scripts/dev-local.ps1                 # standard / 2.5 (default, mirrors prod)
#     ./scripts/dev-local.ps1 -Model premium  # premium / 3.1
# The active model is recorded on every structlog line (bound `model=...`) and on
# every dev I/O capture entry (`model` field in gemini_<date>.jsonl), so a
# captured session is unambiguously attributable to one model. Pricing is
# family-aware (GEMINI_PRICING_BY_FAMILY) so cost tracking stays correct across
# the swap. To pin an exact id instead of the flag, set MODEL_NATIVE in the env.
# ------------------------------------------------------------------------------



class Settings(BaseModel):
	# === Model selection (env-swappable for A/B testing without redeploy) ===
	# We run native audio-to-audio Live models only (no cascade/half-cascade).
	# USE_PREMIUM_MODEL flips between the two tiers above; MODEL_NATIVE is the
	# RESOLVED active model (derived below), kept as a field so /health, pricing,
	# and dependencies can read the single source of truth. Set MODEL_NATIVE
	# directly via env to pin an exact model string (overrides the flag).
	# MODEL_LABELING: Model for field labeling/normalization (normalizer currently
	#   deprecated; kept as an env-swappable knob and surfaced on /health).
	# Default FALSE -> 2.5 (gemini-2.5-flash-native-audio-preview). BOTH families
	# now emit update_form_fields reliably: the historic "3.1 only calls the tool
	# ~50% of the time and confabulates a 'trouble saving' message" defect (bd
	# polyglot-pdf-5oq, probe_tool_call.py 2026-06-07) was the UNTYPED `value`
	# param, not the model -- under google-genai 2.8.0 3.1 rejected the untyped
	# required param; typing it "string" restored the call 5/5 (bd
	# polyglot-pdf-i9q8, 2026-06-11). 2.5 remains the default for its audio-path
	# behavior, not its tool-calling. 2.5's known tradeoff is intermittent silence
	# on the AUDIO path (no-audio turns / 1011 -- bd polyglot-pdf-daa), mitigated
	# separately. (3.1 is modestly pricier -- text-out 4.50 vs 2.00/1M; audio
	# in/out identical -- see GEMINI_PRICING_BY_FAMILY.)
	USE_PREMIUM_MODEL: bool = os.getenv("USE_PREMIUM_MODEL", "false").lower() == "true"
	MODEL_NATIVE: str = os.getenv("MODEL_NATIVE", "")  # resolved in _resolve_model if unset
	MODEL_LABELING: str = os.getenv("MODEL_LABELING", "gemini-2.5-flash")
	# Secretary tail-latency guard (bd polyglot-pdf-jnjj.43). The ask_secretary call
	# is BLOCKING (the live "principal" model waits on the tool result mid-turn);
	# Gate 2 (jnjj.27) measured a heavy tail (median ~1s but spikes to 8.5s / 20s).
	# Two bounds:
	#
	# SECRETARY_DEADLINE_S -- how long the SYNCHRONOUS tool call waits before it stops
	#   blocking and returns a "pending" tool result so the principal's turn is not
	#   held open for the tail. The still-running lookup is detached; when it lands the
	#   answer is DELIVERED on a follow-up turn (send_client_content) and the principal
	#   voices it. The "I'm working" UX is the gap-based thinking indicator (bd wpw.5),
	#   which spans user-turn-end -> first-response-audio and so covers this wait for
	#   free -- NO spoken live-model filler turn is spent here (cost lever, maintainer
	#   2026-06-29). Tune against live UX; ~2.5s keeps the median (~1s) lookup on the
	#   fast synchronous path while bounding how long the principal's turn blocks.
	# SECRETARY_TIMEOUT_S -- the HARD CAP on the model call itself (both the sync wait
	#   and the detached background lookup are bounded by it), so a 20s spike or a
	#   stalled call never runs unbounded. The preceding client form-state round-trip
	#   has its own ~5s coordinator timeout (separate from these).
	SECRETARY_DEADLINE_S: float = float(os.getenv("SECRETARY_DEADLINE_S", "2.5"))
	SECRETARY_TIMEOUT_S: float = float(os.getenv("SECRETARY_TIMEOUT_S", "8.0"))
	# Whether to use Vertex AI (now "AI Agent Platform") for LLM operations.
	# True (DEFAULT) -> Vertex via service-account ADC + GOOGLE_CLOUD_PROJECT
	#   (compliance-friendly; required for prod). Vertex preview-model access is
	#   gated per-project: as of 2026-06, gemini-3.1-flash-live-preview is NOT yet
	#   available on Vertex, so it 1008s ("policy violation") under this path.
	# False -> Gemini Developer API (AI Studio) via GEMINI_API_KEY, which DOES
	#   have 3.1. Set VERTEXAI=false (with USE_PREMIUM_MODEL=true) on the demo
	#   service to run 3.1 until Vertex ships it. Env-overridable so demo/prod can
	#   flip without a code edit; mirrors USE_PREMIUM_MODEL / DISABLE_GEMINI_VAD.
	VERTEXAI: bool = os.getenv("VERTEXAI", "true").lower() == "true"
	# CRITICAL VAD MODE TOGGLE (bd polyglot-pdf-333).
	#   False (DEFAULT) -> NATIVE mode: Gemini's own automatic VAD drives turn
	#     detection. The adapter sends the VAD_* sensitivity knobs below; the
	#     frontend stops sending manual activity_start/end and streams continuous
	#     audio (incl. silence) so Gemini's VAD has a stream to detect on.
	#   True -> MANUAL mode: Gemini's VAD is off ({'disabled': True}); turn-taking
	#     is driven by frontend client-side (Silero) VAD via manual activity
	#     signals. This is the single revert switch.
	# Env-overridable so demo/prod can flip without a code edit. See
	# docs/standards/voice-and-vad.md.
	DISABLE_GEMINI_VAD: bool = os.getenv("DISABLE_GEMINI_VAD", "false").lower() == "true"
	GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")

	# Audio settings
	AUDIO_IN_RATE: int = 16000
	AUDIO_OUT_RATE: int = 24000
	MAX_UPLOAD_MB: int = 5
	WS_CHUNK_MS: int = 20
	WS_PING_INTERVAL_SEC: int = 15
	WS_IDLE_TIMEOUT_SEC: int = 120  # Close WebSocket after 120s of no received message (audio/ping/control)
	# B5 (bd polyglot-pdf-jnjj.17): backend-side fail-OPEN bound for the boundary
	# validator. The validate() call runs INLINE in the WS receive loop, so a hang
	# would block the loop and starve the client's own fail-OPEN. Kept comfortably
	# UNDER the frontend's VALIDATOR_GATE_TIMEOUT_MS (6s) so the backend frees the loop
	# and returns clean before the client's gate gives up.
	VALIDATOR_TIMEOUT_SEC: float = 4.0
	WS_MAX_AUDIO_FRAME_BYTES: int = 32000  # ~1s at 16kHz mono PCM16 (2 bytes/sample)

	# === JIT (Just-In-Time) Schema Loading Settings ===
	# Token Reduction: Send manifests instead of full schemas
	# Full schema loaded on-demand per field as needed
	USE_JIT_SCHEMA: bool = os.getenv("USE_JIT_SCHEMA", "false").lower() == "true"  # Feature flag: enable JIT schema loading

	# === DTI (Dynamic Turn Injection) Settings ===
	# The thin-principal arm (bd polyglot-pdf-jnjj.22): the system instruction
	# carries ONLY the static behavioral backbone plus the CURRENT field's guidance;
	# each next field's guidance rides the confirm_field tool response (the same
	# vehicle JIT's next_field_schema uses today). No whole-form field dump and no
	# manifest. Mutually exclusive with USE_JIT_SCHEMA at the SI level (DTI takes
	# precedence) but reuses JIT's confirm_field plumbing. Env-gated, default off.
	USE_DTI: bool = os.getenv("USE_DTI", "false").lower() == "true"

	# === VAD (Voice Activity Detection) Settings ===
	# Gemini Live API automatic activity detection sensitivity
	# START_SENSITIVITY: How quickly Gemini detects speech start
	#   - LOW: More conservative, fewer false positives, might miss quiet speech
	#   - HIGH: More aggressive, catches quiet speech, more false positives
	# END_SENSITIVITY: How quickly Gemini detects speech end
	#   - LOW: Waits longer for silence, reduces choppy cutoffs
	#   - HIGH: Ends faster, more responsive but may cut off pauses
	# Env-overridable (bd polyglot-pdf-4sv7: these were hard-coded literals, so
	# the deploy env could not tune Gemini-side VAD at all). Default START=HIGH:
	# measured on the audio path 2026-06-11, START_SENSITIVITY_LOW dropped 6/20
	# turns (incl. the short "yes" confirmations the demo kept missing) while
	# HIGH registered 20/20 -- see docs/standards/voice-and-vad.md.
	VAD_START_SENSITIVITY: str = os.getenv("VAD_START_SENSITIVITY", "HIGH")  # Options: "LOW", "HIGH", "UNSPECIFIED"
	VAD_END_SENSITIVITY: str = os.getenv("VAD_END_SENSITIVITY", "LOW")    # Options: "LOW", "HIGH", "UNSPECIFIED"
	VAD_PREFIX_PADDING_MS: int | None = int(os.getenv("VAD_PREFIX_PADDING_MS") or "500")  # Milliseconds of audio before speech start to include
	VAD_SILENCE_DURATION_MS: int | None = int(os.getenv("VAD_SILENCE_DURATION_MS") or "500")  # Milliseconds of silence before ending speech

	# === Context-window compression (Gemini Live) ===
	# Server-side ContextWindowCompressionConfig: a sliding window bounds the live
	# context so per-turn re-billing stops compounding (quadratic -> linear cumulative
	# cost) and audio sessions can run past the 15-min cap. Design + cost model:
	# docs/components/context-compression.md (epic polyglot-pdf-l3a, bead -45o).
	# All three are tuning knobs, not load-bearing constants: ENABLED gates the whole
	# feature (default off until validated). TRIGGER = tokens before a turn that fire
	# compression; WINDOW = target_tokens to retain (must be < trigger). Our sessions
	# peak near ~9k tokens, so the trigger must be low (~5k) to ever fire -- the docs'
	# 25k example would be inert here.
	CONTEXT_COMPRESSION_ENABLED: bool = os.getenv("CONTEXT_COMPRESSION_ENABLED", "false").lower() == "true"
	# `... or "default"` guards an EMPTY-STRING env value: os.getenv(key, default)
	# only returns the default when the var is UNSET; if it is set-but-empty (e.g.
	# CONTEXT_COMPRESSION_TRIGGER_TOKENS= in a deploy env file) it returns "", and
	# int("") raises ValueError at import -> the backend will not boot. Same hazard
	# class the VAD_*_MS knobs were hardened against (bd polyglot-pdf-46bu).
	CONTEXT_COMPRESSION_TRIGGER_TOKENS: int = int(os.getenv("CONTEXT_COMPRESSION_TRIGGER_TOKENS") or "5000")
	CONTEXT_COMPRESSION_WINDOW_TOKENS: int = int(os.getenv("CONTEXT_COMPRESSION_WINDOW_TOKENS") or "3000")

	# --- Per-form window derivation (bd polyglot-pdf-jnjj.35 / A6) ---
	# The jnjj.25 cost measurement proved DTI + CALIBRATED eviction is the win
	# (-21% on the unhappy path), and the calibration is LOAD-BEARING and
	# FORM-SPECIFIC: the sliding window must sit JUST ABOVE the unevictable SI+tools
	# floor. Too loose -> Gemini barely evicts (l3a) -> no win; too tight (<= floor)
	# -> compression fires turn 1 and evicts ALL conversation. A FIXED constant (the
	# TRIGGER/WINDOW above) is therefore wrong for any form whose floor differs from
	# the one it was tuned for. When this flag is on (the default), the adapter
	# DERIVES the window/trigger per-form from the rendered DTI SI floor:
	#   window  = floor_tokens + WINDOW_HEADROOM_TOKENS   (room for a couple fields'
	#                                                       guidance to accumulate)
	#   trigger = window       + TRIGGER_MARGIN_TOKENS    (pile-up before eviction)
	# The static TRIGGER/WINDOW above stay as the explicit OVERRIDE used when this is
	# off (or when the floor is unknown -- e.g. a non-DTI SI). Findings:
	# scripts/spikes/jnjj_25_dti_cost_findings.md (the production-wiring note).
	#
	# CALIBRATING THE HEADROOM (the load-bearing number). The floor estimator is a
	# coarse chars/4 of the SI+tools TEXT, which UNDERSHOOTS the floor Gemini
	# actually bills: on the measured I-90 DTI run the rendered SI is 3786 chars
	# (-> ~946 est. tok) + ~655 tok tools = ~1601 ESTIMATED floor, but the live
	# eviction landing zone was ~1978-2034 tokens (the meta.json eviction_drops) --
	# a ~377-tok undershoot, because Gemini's tokenizer + conversation framing bill
	# more than chars/4 of the raw text. So the headroom must clear the REAL billed
	# floor, not the estimate: 599 lifts the ~1601 estimate to the validated ~2200
	# window (which sits just above the ~1978 real floor). Margin 600 -> ~2800
	# trigger. (Anchored to the one form with measured eviction data; the estimator's
	# undershoot scales loosely with content, so re-measure the headroom when a
	# second form's eviction floor is known. Strictly safer than the old 222, which
	# derived a 1823 window -- BELOW the 1978 real floor -> turn-1 eviction.)
	CONTEXT_COMPRESSION_DERIVE_FROM_SI_FLOOR: bool = (
		os.getenv("CONTEXT_COMPRESSION_DERIVE_FROM_SI_FLOOR", "true").lower() == "true"
	)
	CONTEXT_COMPRESSION_WINDOW_HEADROOM_TOKENS: int = int(
		os.getenv("CONTEXT_COMPRESSION_WINDOW_HEADROOM_TOKENS") or "599"
	)
	CONTEXT_COMPRESSION_TRIGGER_MARGIN_TOKENS: int = int(
		os.getenv("CONTEXT_COMPRESSION_TRIGGER_MARGIN_TOKENS") or "600"
	)

	@model_validator(mode="after")
	def _resolve_model(self) -> "Settings":
		# Resolve the active native-audio model from USE_PREMIUM_MODEL unless an
		# explicit MODEL_NATIVE was pinned via env (non-empty wins). The standard
		# (2.5) tier is BACKEND-AWARE: the native-audio Live model has a different id
		# on Vertex than on AI Studio (see MODEL_NATIVE_STANDARD_VERTEX), and the
		# AI Studio id 1008s on Vertex. So when VERTEXAI=true and no explicit pin is
		# set, resolve to the Vertex id -- this makes ANY Vertex deploy work without
		# hand-pinning MODEL_NATIVE (bd polyglot-pdf-a079). The premium (3.1) tier is
		# AI-Studio-only as of 2026-06, so it is unaffected; USE_PREMIUM_MODEL=true on
		# the Vertex path will 1008 until Vertex ships 3.1 (an explicit, documented
		# limitation, not this resolver's concern).
		if not self.MODEL_NATIVE:
			if self.USE_PREMIUM_MODEL:
				self.MODEL_NATIVE = MODEL_NATIVE_PREMIUM
			elif self.VERTEXAI:
				self.MODEL_NATIVE = MODEL_NATIVE_STANDARD_VERTEX
			else:
				self.MODEL_NATIVE = MODEL_NATIVE_STANDARD
		# The Live API requires target_tokens (window) < trigger_tokens. If a misconfig
		# inverts them, clamp the window below the trigger rather than send a config the
		# API rejects. Only clamp when compression is ENABLED: otherwise the values are
		# inert and silently rewriting them would surprise an operator pre-staging values
		# before flipping the flag. (fresh-eyes PR #76.)
		if (self.CONTEXT_COMPRESSION_ENABLED
				and self.CONTEXT_COMPRESSION_WINDOW_TOKENS >= self.CONTEXT_COMPRESSION_TRIGGER_TOKENS):
			self.CONTEXT_COMPRESSION_WINDOW_TOKENS = max(1, self.CONTEXT_COMPRESSION_TRIGGER_TOKENS // 2)
		return self

	# Tool declarations for web forms (stateless, client-managed)
	# Note: get_next_field is NOT included - client handles field navigation
	TOOL_DECLARATIONS: list[dict] = [
		# HALLUCINATION_REDUCTION (Oct 30, 2025): Changed to single-field updates only
		# Multi-field updates caused higher hallucination rates
		{
			"name": "update_form_fields",
			"description": (
				"Update ONE field with user's provided value. Call immediately when user answers. "
				"Translate values to English. Use exact field_id from schema (with brackets if present). "
				"For radio/select fields: Use the 'value' from the option object shown in schema "
				"(e.g., if option shows '\"Yes\" (use value: P1_checkbox4[0])', send value: \"P1_checkbox4[0]\"'). "
				"For checkboxes: boolean (true/false). For text fields: string. Current section only."
			),
			"parameters": {
				"type": "object",
				"properties": {
					"field_id": {
						"type": "string",
						"description": 'Exact field "id" from schema (e.g., "firstName", "p1_checkbox4")'
					},
					"value": {
						# Declared "string" deliberately: under google-genai 2.8.0 a
						# REQUIRED param with no type makes gemini-3.1 reject the call
						# (it verbalizes "I had an issue processing that value" and never
						# fills) -- 2.5 tolerated the untyped param, 3.1 does not (bd
						# polyglot-pdf-i9q8). The model already sends radio/select and
						# checkbox values as the option-value STRING shown in the schema
						# (e.g. "P1_checkbox4[0]"), and the frontend owns boolean coercion,
						# so a string type matches real usage without losing information.
						"type": "string",
						"description": 'For radio/select: exact "value" from option object. For checkbox: the option value (or "true"/"false"). For text: string.'
					}
				},
				"required": ["field_id", "value"]
			}
		},
		{
			"name": "get_form_status",
			"description": (
				"Check which fields are filled and their values. "
				"Acknowledge user first ('One moment while I check the form')."
			),
			"parameters": {
				"type": "object",
				"properties": {
					"field_ids": {
						"type": "array",
						"description": "Field IDs to check",
						"items": {"type": "string"}
					}
				},
				"required": ["field_ids"]
			}
		},
		{
			"name": "switch_section",
			"description": "Navigate to a different section/part. Use the section NUMBER only (e.g., '2' for Section 2).",
			"parameters": {
				"type": "object",
				"properties": {
					"section_identifier": {
						"type": "string",
						"description": "Section number as a string (e.g., '1', '2', '3'). ALWAYS use numbers, not labels."
					}
				},
				"required": ["section_identifier"]
			}
		},
		{
			"name": "get_field_value",
			"description": (
				"Look up field value by EXACT spoken name from schema or previous sections. "
				"Match exact name shown in context - do not abbreviate."
			),
			"parameters": {
				"type": "object",
				"properties": {
					"spoken_name": {
						"type": "string",
						"description": "Exact field name from context"
					}
				},
				"required": ["spoken_name"]
			}
		},
		# REMOVED: complete_section tool (optimization - frontend auto-detects completion)
		# Section completion is now triggered automatically when all fields are confirmed
		{
			"name": "confirm_field",
			"description": (
				"Confirm that a field value is correct after user verification. "
				"MUST be called before moving to next field. After filling a field with update_form_fields, "
				"ask user 'Is that correct?' and wait for confirmation (yes/correct/that's right). "
				"If confirmed, call this tool. If user says no/incorrect, ask for correct value."
			),
			"parameters": {
				"type": "object",
				"properties": {
					"field_id": {
						"type": "string",
						"description": "ID of the field being confirmed"
					},
					"confirmation_method": {
						"type": "string",
						"enum": ["verbal", "manual"],
						"description": "How the field was confirmed (verbal: user said yes/correct, manual: user edited field)"
					}
				},
				"required": ["field_id", "confirmation_method"]
			}
		},
		{
			# The secretary (bd polyglot-pdf-jnjj.45): a cheap text-model helper
			# that holds the WHOLE form catalog + the applicant's current answers
			# and answers prose questions about them. The principal asks in plain
			# language and gets back a prose answer -- it does NOT need the field
			# catalog in its own (expensive) context. Use this for "what did they
			# say for X?", "have we answered Y?", "which field is Z?" -- anything
			# about a PAST answer or a field other than the current one.
			"name": "ask_secretary",
			"description": (
				"Ask the secretary a plain-language question about the form -- a "
				"past answer, whether something has been filled, or which field "
				"covers a topic (e.g. 'what previous name did they give?', 'have "
				"we got their date of birth yet?'). The secretary holds the whole "
				"form and the applicant's current answers and replies in prose. "
				"Use this instead of trying to remember other fields yourself."
			),
			"parameters": {
				"type": "object",
				"properties": {
					"query": {
						"type": "string",
						"description": (
							"The plain-language question about the form or a past "
							"answer (e.g. 'what is their mailing zip code?')."
						)
					}
				},
				"required": ["query"]
			}
		}
	]

	# Hosted schema-editor access (bd polyglot-pdf-92qe.1). Two shared-secret
	# tiers checked by the /api/editor/* routes: EDITOR (polish provided kits:
	# list/read drafts, save schemas, flip status) and AUTHOR (editor + onboard
	# PDFs + run hosted extraction). Unset -> the editor surface is disabled
	# (routes fail closed with 503). On Cloud Run these arrive via Secret
	# Manager (--set-secrets), never plaintext env.
	SCHEMA_EDITOR_TOKEN: str | None = os.getenv("SCHEMA_EDITOR_TOKEN")
	SCHEMA_AUTHOR_TOKEN: str | None = os.getenv("SCHEMA_AUTHOR_TOKEN")
	# Extra CORS origins (comma-separated), e.g. the hosted schema-editor site.
	# The editor calls Cloud Run directly (not via the Hosting /api rewrite,
	# whose 60s cap would kill minutes-long extraction), so its origin must be
	# allowed here.
	CORS_EXTRA_ORIGINS: str = os.getenv("CORS_EXTRA_ORIGINS", "")
	# Hosted PDF->schema extraction (bd polyglot-pdf-92qe.3, author tier).
	# EXTRACTOR_MODEL must be a gemini-* model on Cloud Run: the extraction
	# script's default (the local `claude` CLI) does not exist in the container.
	# gemini-2.5-pro over flash on purpose: authoring is a ONE-OFF per form, so
	# quality beats per-call cost (the runtime token economy does not apply --
	# bd 7a9 doctrine). Swap by env without a redeploy of code.
	EXTRACTOR_MODEL: str = os.getenv("EXTRACTOR_MODEL", "gemini-2.5-pro")
	# Wall-clock cap for one extraction subprocess. Well under Cloud Run's
	# --timeout=3600 so the HTTP request outlives the subprocess kill.
	EXTRACTOR_TIMEOUT_SEC: float = float(os.getenv("EXTRACTOR_TIMEOUT_SEC", "1500"))
	# Upload cap for the onboarding PDF (MB). Government form PDFs run 1-15 MB.
	EXTRACTOR_MAX_PDF_MB: float = float(os.getenv("EXTRACTOR_MAX_PDF_MB", "25"))

	# Form kit storage (schema/PDF pairs)
	FORM_KITS_MODE: str = os.getenv("FORM_KITS_MODE", "local")
	FORM_KITS_LOCAL_ROOT: str = os.getenv(
		"FORM_KITS_LOCAL_ROOT",
		str(Path(__file__).resolve().parents[1] / "form-kits")
	)
	FORM_KITS_GCS_BUCKET: str | None = os.getenv("FORM_KITS_GCS_BUCKET")
	FORM_KITS_REMOTE_PREFIX: str = os.getenv("FORM_KITS_REMOTE_PREFIX", "form-kits")

	# === SYSTEM INSTRUCTION TEMPLATE ===
	# Main instruction set that controls AI behavior for form filling
	# Placeholders: {form_title}, {section_number}, {total_sections}, {section_label},
	#               {filled_count}, {total_fields}, {unfilled_count}, {fields_json},
	#               {fill_language}, {previous_spoken_names}, {confirmation_policy}, {section_list}
	# Note: {fields_json} is pipe-separated text format to avoid JSON quote confusion with field IDs

	SYSTEM_INSTRUCTION: str = (
    "LANGUAGE: Detect user's language from first utterance. Respond in THAT language for entire conversation. "
    "Field VALUES in {fill_language}, but YOUR SPEECH in user's language. Never switch to English unless user does.\n\n"

    "Medical assistant: {form_title} | Section {section_number}/{total_sections}: {section_label}\n"
    "Progress: {filled_count}/{total_fields} | Previous: {previous_spoken_names}\n\n"

    "AVAILABLE SECTIONS:\n{section_list}\n\n"

    "FIELDS:\n{fields_json}\n\n"

    "WORKFLOW:\n"
    "1. Ask for ONE field (skip Filled=True)\n"
    "2. User answers -> IMMEDIATELY call update_form_fields with ONE field\n"
    "3. Always read back user provided value and ask 'Is that correct?'\n"
    "4. Wait for verbal confirmation (yes/correct/that's right)\n"
    "5. Call confirm_field tool with confirmation_method='verbal'\n"
    "6. Move to next field (hint provided in confirm_field response)\n"
    "If user says no/incorrect: ask for correct value and repeat from step 2\n"
    "CRITICAL: Fields filled by you (AI) are NOT confirmed until user explicitly says yes. "
    "Never skip confirmation. Never move to next field without calling confirm_field. "
    "Only manual edits by user are auto-confirmed.\n\n"

    "TOOLS:\n"
    "- update_form_fields: Fill ONE field. Returns success or validation error.\n"
    "- confirm_field: REQUIRED after filling field. Params: field_id, confirmation_method='verbal'. Returns next_field_hint.\n"
    "- get_form_status: Returns 'field_id:value:confirmed|field_id:value:unconfirmed'. Only filled fields included. Omitted = empty. Use when user asks 'what have I filled?'\n"
    "- get_field_value: Retrieve value from previous section by EXACT spoken name\n"
    "- switch_section: Navigate to different section using ORDER number from AVAILABLE SECTIONS\n"
    "- Current section only - for previous sections tell user to switch first\n\n"

    "MATCHING:\n"
    "- Options must match EXACTLY from schema (punctuation matters)\n"
    "- Translate user response to {fill_language} options\n"
    "- Multiple checkboxes: comma-separated exact values\n"
    "- Validation error -> retry with correct option or ask user to clarify\n"
    "- Never proceed until field updates successfully\n\n"

    "CONSTRAINTS:\n"
    "- Never read field IDs aloud (use spoken names only)\n"
    "- When asking for a field, use natural phrasing without saying 'field' or IDs\n"
    "- When a field carries a Note (or the next-field hint carries context to convey), "
    "briefly convey that context in your own words WHILE asking -- one short sentence, "
    "not a lecture. It is the fine print the user needs to answer accurately; "
    "never ask a qualified question as if it were unqualified.\n"
    "- Follow format requirements (e.g., yyyy-MM-dd for dates)\n"
    "- Sanity check dates/phones/ZIP codes\n"
    "- Optional field does not apply (e.g. no middle name) or user wants to clear a field: call update_form_fields with value \"\" then confirm_field normally.\n"
    "- Greet warmly in user's language, mention form/section, ask for: {next_field_hint}\n\n"

    "ADDRESS CONSISTENCY:\n"
    "After filling any address-cluster field (state, zip, province, country), "
    "check coherence with other address fields already filled using world knowledge "
    "(zip-to-state, US state vs. foreign province, country vs. state/province). "
    "If a conflict exists, name both fields and ask the user to verify: e.g. "
    "'You said West Virginia but that zip code is in Iowa -- are both correct?' "
    "Accept the user's answer if they confirm.\n\n"

    "CONFIRMATION:\n{confirmation_policy}"
)

	# === JIT SYSTEM INSTRUCTION TEMPLATE ===
	# Just-In-Time schema loading - uses manifest instead of full field list
	# Placeholders: {form_title}, {section_number}, {total_sections}, {section_label}, {section_list},
	#               {filled_count}, {total_fields}, {manifest_text}, {fill_language},
	#               {previous_spoken_names}, {next_field_hint}, {next_field_schema}, {confirmation_policy}
	JIT_SYSTEM_INSTRUCTION: str = (
    "LANGUAGE: Detect user's language from first utterance. Respond in THAT language for entire conversation. "
    "Field VALUES in {fill_language}, but YOUR SPEECH in user's language. Never switch to English unless user does.\n\n"

    "Medical assistant: {form_title} | Section {section_number}/{total_sections}: {section_label}\n"
    "Progress: {filled_count}/{total_fields} | Previous: {previous_spoken_names}\n\n"

    "AVAILABLE SECTIONS:\n{section_list}\n\n"

    "CURRENT FIELD:\n{next_field_schema}\n\n"

    "FIELD MANIFEST (field_id|spoken_name pairs - full schemas loaded on-demand):\n{manifest_text}\n\n"

    "WORKFLOW:\n"
    "1. Ask for: {next_field_hint}\n"
    "2. User answers -> IMMEDIATELY call update_form_fields with ONE field\n"
    "3. Read back value -> Ask 'Is that correct?'\n"
    "4. Wait for verbal confirmation (yes/correct/that's right)\n"
    "5. Call confirm_field tool with confirmation_method='verbal'\n"
    "6. Next field schema loaded automatically (use next_field_hint from confirm_field response)\n"
    "If user says no/incorrect: ask for correct value and repeat from step 2\n"
    "CRITICAL: Fields filled by you (AI) are NOT confirmed until user explicitly says yes. "
    "Never skip confirmation. Never move to next field without calling confirm_field. "
    "Only manual edits by user are auto-confirmed.\n\n"

    "TOOLS:\n"
    "- update_form_fields: Fill ONE field. Returns success or validation error.\n"
    "- confirm_field: REQUIRED after filling field. Params: field_id, confirmation_method='verbal'. Returns next_field_hint and loads next field schema.\n"
    "- get_form_status: Returns compact format 'field_id:value:status|...' where status is 'confirmed' or 'unconfirmed' (empty fields are omitted). Use when user asks 'what have I filled?'\n"
    "- get_field_value: Retrieve value from previous section by EXACT spoken name\n"
    "- switch_section: Navigate to different section using ORDER number from AVAILABLE SECTIONS\n"
    "- Current section only - for previous sections tell user to switch first\n\n"

    "MATCHING:\n"
    "- Options must match EXACTLY from schema (punctuation matters)\n"
    "- Translate user response to {fill_language} options\n"
    "- Multiple checkboxes: comma-separated exact values\n"
    "- Validation error -> retry with correct option or ask user to clarify\n"
    "- Never proceed until field updates successfully\n\n"

    "CONSTRAINTS:\n"
    "- Never read field IDs aloud (use spoken names only)\n"
    "- Never abbreviate spoken names (use full name from schema)\n"
    "- When asking for a field, use natural phrasing without mentioning 'field' or IDs\n"
    "- When the current field's schema or hint carries instructions/context to convey, "
    "briefly convey that context in your own words WHILE asking -- one short sentence, "
    "not a lecture. It is the fine print the user needs to answer accurately; "
    "never ask a qualified question as if it were unqualified.\n"
    "- For required fields: Ask naturally without pressuring (user may skip with 'next')\n"
    "- Optional field does not apply (e.g. no middle name) or user wants to clear a field: call update_form_fields with value \"\" then confirm_field normally.\n"
    "- Keep interactions conversational and empathetic - this is a medical form\n\n"

    "ADDRESS CONSISTENCY:\n"
    "After filling any address-cluster field (state, zip, province, country), "
    "check coherence with other address fields already filled using world knowledge "
    "(zip-to-state, US state vs. foreign province, country vs. state/province). "
    "If a conflict exists, name both fields and ask the user to verify: e.g. "
    "'You said West Virginia but that zip code is in Iowa -- are both correct?' "
    "Accept the user's answer if they confirm.\n\n"

    "END-OF-SECTION CONFIRMATION:\n"
    "{confirmation_policy}"
)

	# DTI_SYSTEM_INSTRUCTION (bd polyglot-pdf-1ac3, epic polyglot-pdf-13w7): the
	# FULLY STATIC thin-principal backbone -- zero placeholders. It carries NO
	# form/session state and NO field guidance. Every field's guidance (incl.
	# field 1) reaches the model via the dynamic injection: the initiating message
	# at session/section start, then next_field_guidance after each confirm. The
	# model acts on the LATEST injected guidance block and copies its field_id
	# verbatim. The tool prose is protocol-only (no per-tool catalog), so adding a
	# tool needs no SI edit -- tool names/params/returns live in the tool
	# declarations the SDK sends. Form/section metadata moves onto the injection in
	# a later epic child; the constant itself stays state-free.
	DTI_SYSTEM_INSTRUCTION: str = (
    "LANGUAGE: Detect the user's language from their first utterance. Respond in THAT language "
    "for the entire conversation. Speak in the user's language, but fill field VALUES in the fill "
    "language named in the current field's guidance. Never switch to English unless the user does.\n\n"

    "ROLE: You are a warm, empathetic medical-form assistant filling one form field at a time by voice.\n\n"

    "CURRENT FIELD -- READ THIS FIRST:\n"
    "The field you are filling RIGHT NOW -- including its EXACT field_id, spoken name, instructions, "
    "format, and options -- is ALWAYS provided in the most recent injected guidance block: the "
    "initiating message at the start of a session or section, and the next-field guidance returned "
    "after each confirmation. ALWAYS act on the LATEST guidance block and ignore guidance from "
    "earlier blocks. When you fill or confirm a field, COPY its field_id VERBATIM from that latest "
    "guidance block -- character for character. NEVER invent, reconstruct, guess, abbreviate, or "
    "pattern-match a field_id from another field's id. If you have no current guidance block (e.g. "
    "after a reconnect), request the current form status or ask the user, rather than guessing.\n\n"

    "WORKFLOW:\n"
    "1. Ask for the current field (from the latest guidance block) using natural phrasing.\n"
    "2. User answers -> IMMEDIATELY fill that ONE field, using its exact field_id from the guidance.\n"
    "3. Read the value back -> ask 'Is that correct?'\n"
    "4. Wait for verbal confirmation (yes/correct/that's right).\n"
    "5. Confirm the field with confirmation_method='verbal'.\n"
    "6. The confirmation returns the NEXT field's guidance. Ask for THAT field next, following its "
    "instructions/format/options, and copy ITS field_id verbatim when you fill it.\n"
    "If the user says no/incorrect: ask for the correct value and repeat from step 2.\n"
    "CRITICAL: Fields you (the AI) fill are NOT confirmed until the user explicitly says yes. "
    "Never skip confirmation. Never move to the next field without confirming the current one. "
    "Only manual edits by the user are auto-confirmed.\n\n"

    "TOOL PROTOCOL:\n"
    "- Use the tools provided to you; their names, parameters, and return shapes are defined in the "
    "tool declarations. Use the tool whose declared purpose matches your intent.\n"
    "- Fill exactly ONE field per fill call. Always confirm a filled field before advancing.\n"
    "- Pass arguments exactly as declared; use the field_id verbatim from the latest guidance.\n"
    "- Act on what each tool returns: a validation error means retry with a corrected value or ask "
    "the user to clarify; never proceed until the field updates successfully.\n"
    "- You operate on the current section only. To reach a field in another section, navigate to "
    "that section first (or, for a read-only lookup, use the appropriate retrieval tool).\n\n"

    "MATCHING:\n"
    "- Options must match EXACTLY from the field's guidance (punctuation matters).\n"
    "- Translate the user's response to the options in the field's fill language.\n"
    "- Multiple checkboxes: comma-separated exact values.\n"
    "- Validation error -> retry with the correct option or ask the user to clarify.\n"
    "- Never proceed until the field updates successfully.\n\n"

    "CONSTRAINTS:\n"
    "- Never read field IDs aloud (use spoken names only).\n"
    "- Never abbreviate spoken names (use the full name from the guidance).\n"
    "- When asking for a field, use natural phrasing without mentioning 'field' or IDs.\n"
    "- For required fields: ask naturally without pressuring (the user may skip with 'next').\n"
    "- Optional field does not apply (e.g. no middle name) or user wants to clear a field: fill it "
    "with value \"\" then confirm normally.\n"
    "- Keep interactions conversational and empathetic - this is a medical form.\n\n"

    "ADDRESS CONSISTENCY:\n"
    "After filling any address-cluster field (state, zip, province, country), "
    "check coherence with other address fields already filled using world knowledge "
    "(zip-to-state, US state vs. foreign province, country vs. state/province). "
    "If a conflict exists, name both fields and ask the user to verify: e.g. "
    "'You said West Virginia but that zip code is in Iowa -- are both correct?' "
    "Accept the user's answer if they confirm."
)

	# === INITIATING MESSAGE TEMPLATE ===
	# Used to prompt Gemini to initiate conversation in a specific language
	# Triggered by: session start (DTI), language selection change, section switching
	# Placeholders: {spoken_language}, {next_field_hint}, {current_field_guidance}
	# {current_field_guidance} is the DTI injection channel for field 1 (epic
	# polyglot-pdf-13w7, bd polyglot-pdf-j748): the static SI carries no field
	# data, so field 1's exact field_id + guidance ride here, rendered by the
	# same render_field_guidance() that delivers fields 2..N in the confirm_field
	# response. The caller passes "" in non-DTI mode (legacy/JIT still carry field
	# data in the SI), so this suffix is a no-op there.
	# The re-verify carve-out names ALREADY-CONFIRMED fields specifically, and the
	# first field is explicitly pinned to the normal per-field workflow: the old
	# "DO NOT verify previous fields - move directly to asking for the next field"
	# wording let the model read field 1 (no previous fields exist) as exempt from
	# the read-back + 'Is that correct?' step, so it auto-confirmed field 1 without
	# re-asking (bd polyglot-pdf-choa).
	INITIATING_MESSAGE: str = (
		"Speak {spoken_language}. Greet user warmly, state section name, immediately ask for {next_field_hint}. "
		"Do NOT re-verify fields that were already confirmed earlier - start by asking for this field. "
		"This field follows the normal workflow like every other: after the user answers, fill it, "
		"read the value back, ask 'Is that correct?', and confirm only after the user says yes.{current_field_guidance}"
	)

	# === RESUME INITIATING MESSAGE TEMPLATE ===
	# Used instead of INITIATING_MESSAGE when the handshake carries resume:true.
	# The user is already mid-section; skip greeting and section re-introduction.
	# Placeholders: {spoken_language}, {next_field_hint}, {current_field_guidance}
	# ({current_field_guidance} as in INITIATING_MESSAGE: the DTI field-1 channel,
	# "" in non-DTI mode.)
	RESUME_INITIATING_MESSAGE: str = (
		"Speak {spoken_language}. Do NOT greet the user. Do NOT introduce the form or section. "
		"Simply ask for {next_field_hint} in one short sentence, as if continuing naturally.{current_field_guidance}"
	)

	# === DISCLAIMER INITIATING MESSAGE ===
	# Used when user first selects language - reads disclaimer before starting form
	# Placeholders: {spoken_language}
	DISCLAIMER_INITIATING_MESSAGE: str = (
		"Speak {spoken_language}. Read this disclaimer aloud verbatim: '{disclaimer_text}'. After reading, tell user to click 'I Agree' button to continue."
	)

	# === RECOVERY PROMPTS (Activity Watchdog) ===
	# Sent by the frontend watchdog when the conversation stalls (bd zy3).
	# Consumed by FormFillingService.send_recovery_prompt -- levels escalate.
	# These are SCRIPTS/instructions for Gemini to act on aloud, not user turns.
	# ASCII-only (scar #6).

	# Level 1: Re-prompt for the current field
	RECOVERY_PROMPT_LEVEL_1: str = (
		"The user seems to have paused. Please re-ask them for the same field you just asked for."
	)

	# Level 2: "Are you still there?"
	RECOVERY_PROMPT_LEVEL_2: str = (
		'Say to the user: "Hello, are you still there? If you need me to repeat the question, just let me know."'
	)

	# Level 3: Farewell before the session closes.
	# Single double-quoted literal: the inner speech quotes are escaped (\"),
	# apostrophes stay bare -- no single/double-quote mixing to break on edit (bd bpm7).
	RECOVERY_PROMPT_LEVEL_3: str = (
		"Say to the user: \"I haven't heard from you in a while, so I'm going to close this session. "
		"Don't worry, your progress is saved. Just start the voice assistant again when you're ready to continue.\""
	)

@lru_cache(maxsize=1)
def get_settings() -> Settings:
	"""Load and return validated settings.

	Cached: Settings is static process-config built from os.environ, and several
	hot-ish paths read it per call (e.g. the native-VAD guard fires get_settings()
	per manual activity signal -- bd polyglot-pdf-efd), each previously
	constructing a fresh Settings model. lru_cache returns one shared instance.
	Tests that need a different config monkeypatch the module attribute
	(monkeypatch.setattr(config, "get_settings", lambda: ...)), which replaces the
	function and so bypasses the cache; a test that mutates os.environ and expects
	a fresh read should call get_settings.cache_clear() first.

	In later phases we can load .env via python-dotenv and add validation.
	"""
	return Settings()


def parse_extra_origins(raw: str | None) -> list[str]:
	"""Split CORS_EXTRA_ORIGINS ("https://a.web.app, https://a.firebaseapp.com")
	into a clean origin list. Empty/None -> [] (no extra origins). Used by
	main.py to extend the hardcoded localhost CORS list with the hosted
	schema-editor's origin(s) without a code change per deploy
	(bd polyglot-pdf-92qe.1).

	Accepts SEMICOLONS as well as commas (bd 92qe.4): the value reaches Cloud
	Run inside `gcloud run deploy --set-env-vars=A=1,B=2,...`, where commas are
	the PAIR separator -- a multi-origin value must therefore use semicolons in
	the deploy scripts ("https://a.web.app;https://a.firebaseapp.com")."""
	return [o.strip() for o in re.split(r"[,;]", raw or "") if o.strip()]


# ============================================================================
# Gemini Pricing for Token Tracking (per-token rates, keyed by model family)
# ============================================================================
# Rates are per-1M list prices from https://ai.google.dev/gemini-api/docs/pricing,
# divided to per-token here. Output rates include thinking tokens. Keyed by model
# FAMILY so the active model (MODEL_NATIVE, set by USE_PREMIUM_MODEL) selects the
# right row -- this is what makes a 2.5 -> 3.1 A/B comparable on cost.
# Verified against ai.google.dev/gemini-api/docs/pricing on 2026-06-12 (bd
# polyglot-pdf-4loz): BOTH rows match the published page exactly (no drift) --
# 2.5 native-audio, and 3.1 flash-live at the page's
# #gemini-3.1-flash-live-preview anchor (text in 0.75 / audio in 3.00 / text
# out 4.50 / audio out 12.00, output incl. thinking tokens).
# Updated: 2026-06-12.
#
# Columns: text_input / audio_input / text_output / audio_output (USD per 1M).
#   2.5 (native-audio):  0.50 / 3.00 / 2.00 / 12.00
#   3.1 (live preview):  0.75 / 3.00 / 4.50 / 12.00
# Note: a bare "gemini-3-flash-*" (no ".1") is NOT a Live/native-audio model per
# Google's docs, so it won't reach this adapter; model_family() bills it at the
# 2.5 default if it ever does. Add a "3" row here if that changes.
_PER_1M = 1_000_000

GEMINI_PRICING_BY_FAMILY: dict[str, dict[str, float]] = {
	"2.5": {
		"text_input": 0.50 / _PER_1M,
		"audio_input": 3.00 / _PER_1M,
		"text_output": 2.00 / _PER_1M,
		"audio_output": 12.00 / _PER_1M,
	},
	"3.1": {
		"text_input": 0.75 / _PER_1M,
		"audio_input": 3.00 / _PER_1M,
		"text_output": 4.50 / _PER_1M,
		"audio_output": 12.00 / _PER_1M,
	},
}

# Family used when a model name doesn't match any known family -- a safe
# fall-back for unrecognized/unspecified model strings (bills at the cheaper
# 2.5 rate). NOTE: this is the pricing fallback for UNKNOWN names. It happens to
# coincide with the runtime default model family (2.5, USE_PREMIUM_MODEL=false --
# bd polyglot-pdf-5oq), but the two are independent knobs.
DEFAULT_PRICING_FAMILY = "2.5"


def model_family(model_name: str | None) -> str:
	"""Map a Gemini model name to a pricing family key in GEMINI_PRICING_BY_FAMILY.

	Matches the version number as a whole token, NOT a bare substring, so
	'gemini-3.10-flash' does not match family '3.1' and 'gemini-12.5-...' does
	not match '2.5'. The version must be bounded by a non-version character (or
	the start/end of the string) on each side -- i.e. not preceded by a digit/dot
	and not followed by a digit/dot. Falls back to DEFAULT_PRICING_FAMILY for
	empty/unrecognized names so cost tracking never crashes on a new preview
	model -- it just bills at the default until a row is added here.
	"""
	name = (model_name or "").lower()
	for family in GEMINI_PRICING_BY_FAMILY:
		# (?<![\d.]) / (?![\d.]) reject a digit or dot abutting the version,
		# so '3.1' matches in 'gemini-3.1-flash' but not in 'gemini-3.10-flash'.
		if re.search(r"(?<![\d.])" + re.escape(family) + r"(?![\d.])", name):
			return family
	return DEFAULT_PRICING_FAMILY


def get_pricing_for_model(model_name: str | None) -> dict[str, float]:
	"""Return the per-token rate row for the given model's family."""
	return GEMINI_PRICING_BY_FAMILY[model_family(model_name)]


# Backward-compatible alias: the old flat dict was the 2.5 rates. Anything still
# importing GEMINI_PRICING keeps working (it gets the default family's rates).
# A COPY, not the live inner dict -- a stray mutation of GEMINI_PRICING must not
# corrupt GEMINI_PRICING_BY_FAMILY for everyone else in the process.
GEMINI_PRICING = dict(GEMINI_PRICING_BY_FAMILY[DEFAULT_PRICING_FAMILY])

