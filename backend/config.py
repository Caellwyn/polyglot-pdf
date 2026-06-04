from __future__ import annotations

from pydantic import BaseModel, model_validator
import os
import re
from pathlib import Path


# === Native audio-to-audio model tiers (A/B-able) ===
# Both are full native audio-to-audio Live API models (bidiGenerateContent).
# USE_PREMIUM_MODEL flips between these (defaults TRUE -> premium/3.1):
#   premium  -> gemini-3.1-flash-live-preview            (DEFAULT; reliable on audio; family 3.1)
#   standard -> gemini-2.5-flash-native-audio-preview-12-2025 (cheaper opt-in; family 2.5;
#               intermittently silent on the audio path -- bd polyglot-pdf-daa)
# NOTE: Gemini model naming is inconsistent across Google's sources — the 2.5
# native model also appears as `gemini-live-2.5-flash-preview` (the old MODEL_LIVE
# default), and that exact string 1008'd ("not found for bidiGenerateContent") in
# the contract test. We pin the explicit `-preview-12-2025` string above, which is
# verified to connect and return audio. Don't infer native-vs-cascade from a name;
# verify against the live endpoint. See docs/genai_docs/README.md.
MODEL_NATIVE_PREMIUM = "gemini-3.1-flash-live-preview"
MODEL_NATIVE_STANDARD = "gemini-2.5-flash-native-audio-preview-12-2025"



class Settings(BaseModel):
	# === Model selection (env-swappable for A/B testing without redeploy) ===
	# We run native audio-to-audio Live models only (no cascade/half-cascade).
	# USE_PREMIUM_MODEL flips between the two tiers above; MODEL_NATIVE is the
	# RESOLVED active model (derived below), kept as a field so /health, pricing,
	# and dependencies can read the single source of truth. Set MODEL_NATIVE
	# directly via env to pin an exact model string (overrides the flag).
	# MODEL_LABELING: Model for field labeling/normalization (normalizer currently
	#   deprecated; kept as an env-swappable knob and surfaced on /health).
	# Default TRUE -> 3.1 (gemini-3.1-flash-live-preview). The 2.5 native-audio
	# preview is intermittently silent on the AUDIO path (no-audio turns / 1011 —
	# bd polyglot-pdf-daa), so 3.1 is the reliable default; 2.5 is the cheaper
	# opt-in via USE_PREMIUM_MODEL=false. (3.1 is only modestly pricier — text-out
	# 4.50 vs 2.00/1M; audio in/out identical — see GEMINI_PRICING_BY_FAMILY.)
	USE_PREMIUM_MODEL: bool = os.getenv("USE_PREMIUM_MODEL", "true").lower() == "true"
	MODEL_NATIVE: str = os.getenv("MODEL_NATIVE", "")  # resolved in _resolve_model if unset
	MODEL_LABELING: str = os.getenv("MODEL_LABELING", "gemini-2.5-flash")
	VERTEXAI: bool = True # Whether to use Vertex AI for LLM and embedding operations.
	DISABLE_GEMINI_VAD: bool = True  # CRITICAL: Disable Gemini's VAD when using manual activity_start/end signals
	GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
	PROACTIVE_AUDIO: bool = False  # HALLUCINATION_REDUCTION (Oct 30, 2025): Enable to ignore dirty/choppy audio DEPRECATED: gemini doesn't use tools when this is True.
	
	# Audio settings
	AUDIO_IN_RATE: int = 16000
	AUDIO_OUT_RATE: int = 24000
	MAX_UPLOAD_MB: int = 5
	WS_CHUNK_MS: int = 20
	WS_PING_INTERVAL_SEC: int = 15
	WS_IDLE_TIMEOUT_SEC: int = 120  # Close WebSocket after 120s of no received message (audio/ping/control)
	WS_MAX_OUTBOX: int = 100
	WS_MAX_AUDIO_FRAME_BYTES: int = 32000  # ~1s at 16kHz mono PCM16 (2 bytes/sample)

	# === JIT (Just-In-Time) Schema Loading Settings ===
	# Token Reduction: Send manifests instead of full schemas
	# Full schema loaded on-demand per field as needed
	USE_JIT_SCHEMA: bool = os.getenv("USE_JIT_SCHEMA", "false").lower() == "true"  # Feature flag: enable JIT schema loading

	# === VAD (Voice Activity Detection) Settings ===
	# Gemini Live API automatic activity detection sensitivity
	# START_SENSITIVITY: How quickly Gemini detects speech start
	#   - LOW: More conservative, fewer false positives, might miss quiet speech
	#   - HIGH: More aggressive, catches quiet speech, more false positives
	# END_SENSITIVITY: How quickly Gemini detects speech end
	#   - LOW: Waits longer for silence, reduces choppy cutoffs
	#   - HIGH: Ends faster, more responsive but may cut off pauses
	VAD_START_SENSITIVITY: str = "LOW"  # Options: "LOW", "HIGH", "UNSPECIFIED"
	VAD_END_SENSITIVITY: str = "LOW"    # Options: "LOW", "HIGH", "UNSPECIFIED"
	VAD_PREFIX_PADDING_MS: int | None = 500  # Milliseconds of audio before speech start to include
	VAD_SILENCE_DURATION_MS: int | None = 500  # Milliseconds of silence before ending speech

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
	CONTEXT_COMPRESSION_TRIGGER_TOKENS: int = int(os.getenv("CONTEXT_COMPRESSION_TRIGGER_TOKENS", "5000"))
	CONTEXT_COMPRESSION_WINDOW_TOKENS: int = int(os.getenv("CONTEXT_COMPRESSION_WINDOW_TOKENS", "3000"))

	@model_validator(mode="after")
	def _resolve_model(self) -> "Settings":
		# Resolve the active native-audio model from USE_PREMIUM_MODEL unless an
		# explicit MODEL_NATIVE was pinned via env (non-empty wins).
		if not self.MODEL_NATIVE:
			self.MODEL_NATIVE = (
				MODEL_NATIVE_PREMIUM if self.USE_PREMIUM_MODEL else MODEL_NATIVE_STANDARD
			)
		# The Live API requires target_tokens (window) < trigger_tokens. If a misconfig
		# inverts them, clamp the window below the trigger rather than send a config the
		# API rejects. (Only matters when compression is enabled.)
		if self.CONTEXT_COMPRESSION_WINDOW_TOKENS >= self.CONTEXT_COMPRESSION_TRIGGER_TOKENS:
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
						"description": 'For radio/select: exact "value" from option object. For checkbox: boolean. For text: string.'
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
		}
	]

	# Form kit storage (schema/PDF pairs)
	FORM_KITS_MODE: str = os.getenv("FORM_KITS_MODE", "local")
	FORM_KITS_LOCAL_ROOT: str = os.getenv(
		"FORM_KITS_LOCAL_ROOT",
		str(Path(__file__).resolve().parents[1] / "form-kits")
	)
	FORM_KITS_GCS_BUCKET: str | None = os.getenv("FORM_KITS_GCS_BUCKET")
	FORM_KITS_REMOTE_BASE_URL: str | None = os.getenv("FORM_KITS_REMOTE_BASE_URL")
	FORM_KITS_REMOTE_PREFIX: str = os.getenv("FORM_KITS_REMOTE_PREFIX", "form-kits")
	FORM_KITS_REMOTE_TIMEOUT_SEC: float = float(os.getenv("FORM_KITS_REMOTE_TIMEOUT_SEC", "30"))


	# Bump this when parser behavior/logic changes in a breaking way so
	# sessions can be re-parsed automatically when code updates.
	PARSER_VERSION: str = "v2"

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
    "2. User answers → IMMEDIATELY call update_form_fields with ONE field\n"
    "3. Always read back user provided value and ask 'Is that correct?'\n"
    "4. Wait for verbal confirmation (yes/correct/that's right)\n"
    "5. Call confirm_field tool with confirmation_method='verbal'\n"
    "6. Move to next field (hint provided in confirm_field response)\n"
    "If user says no/incorrect: ask for correct value and repeat from step 2\n"
    "CRITICAL: Fields filled by you (AI) are NOT confirmed until user explicitly says yes. "
    "Never skip confirmation. Never move to next field without calling confirm_field. "
    "Only manual edits by user are auto-confirmed.\n\n"

    "TOOLS:\n"
    "• update_form_fields: Fill ONE field. Returns success or validation error.\n"
    "• confirm_field: REQUIRED after filling field. Params: field_id, confirmation_method='verbal'. Returns next_field_hint.\n"
    "• get_form_status: Returns 'field_id:value:confirmed|field_id:value:unconfirmed'. Only filled fields included. Omitted = empty. Use when user asks 'what have I filled?'\n"
    "• get_field_value: Retrieve value from previous section by EXACT spoken name\n"
    "• switch_section: Navigate to different section using ORDER number from AVAILABLE SECTIONS\n"
    "• Current section only - for previous sections tell user to switch first\n\n"

    "MATCHING:\n"
    "• Options must match EXACTLY from schema (punctuation matters)\n"
    "• Translate user response to {fill_language} options\n"
    "• Multiple checkboxes: comma-separated exact values\n"
    "• Validation error → retry with correct option or ask user to clarify\n"
    "• Never proceed until field updates successfully\n\n"

    "CONSTRAINTS:\n"
    "• Follow format requirements (e.g., yyyy-MM-dd for dates)\n"
    "• Sanity check dates/phones/ZIP codes\n"
    "• Greet warmly in user's language, mention form/section, ask for: {next_field_hint}\n\n"

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
    "2. User answers → IMMEDIATELY call update_form_fields with ONE field\n"
    "3. Read back value → Ask 'Is that correct?'\n"
    "4. Wait for verbal confirmation (yes/correct/that's right)\n"
    "5. Call confirm_field tool with confirmation_method='verbal'\n"
    "6. Next field schema loaded automatically (use next_field_hint from confirm_field response)\n"
    "If user says no/incorrect: ask for correct value and repeat from step 2\n"
    "CRITICAL: Fields filled by you (AI) are NOT confirmed until user explicitly says yes. "
    "Never skip confirmation. Never move to next field without calling confirm_field. "
    "Only manual edits by user are auto-confirmed.\n\n"

    "TOOLS:\n"
    "• update_form_fields: Fill ONE field. Returns success or validation error.\n"
    "• confirm_field: REQUIRED after filling field. Params: field_id, confirmation_method='verbal'. Returns next_field_hint and loads next field schema.\n"
    "• get_form_status: Returns compact format 'field_id:value:status|...' where status: ✓=confirmed, ✗=unconfirmed, −=empty. Use when user asks 'what have I filled?'\n"
    "• get_field_value: Retrieve value from previous section by EXACT spoken name\n"
    "• switch_section: Navigate to different section using ORDER number from AVAILABLE SECTIONS\n"
    "• Current section only - for previous sections tell user to switch first\n\n"

    "MATCHING:\n"
    "• Options must match EXACTLY from schema (punctuation matters)\n"
    "• Translate user response to {fill_language} options\n"
    "• Multiple checkboxes: comma-separated exact values\n"
    "• Validation error → retry with correct option or ask user to clarify\n"
    "• Never proceed until field updates successfully\n\n"

    "CONSTRAINTS:\n"
    "• Never read field IDs aloud (use spoken names only)\n"
    "• Never abbreviate spoken names (use full name from schema)\n"
    "• When asking for a field, use natural phrasing without mentioning 'field' or IDs\n"
    "• For required fields: Ask naturally without pressuring (user may skip with 'next')\n"
    "• Keep interactions conversational and empathetic - this is a medical form\n\n"

    "END-OF-SECTION CONFIRMATION:\n"
    "{confirmation_policy}"
)

	# === INITIATING MESSAGE TEMPLATE ===
	# Used to prompt Gemini to initiate conversation in a specific language
	# Triggered by: language selection change, section switching
	# Placeholders: {spoken_language}, {next_field_hint}
	INITIATING_MESSAGE: str = (
		"Speak {spoken_language}. Greet user warmly, state section name, immediately ask for {next_field_hint}. DO NOT verify previous fields - move directly to asking for the next field."
	)
	# === DISCLAIMER INITIATING MESSAGE ===
	# Used when user first selects language - reads disclaimer before starting form
	# Placeholders: {spoken_language}
	DISCLAIMER_INITIATING_MESSAGE: str = (
		"Speak {spoken_language}. Read this disclaimer aloud verbatim: '{disclaimer_text}'. After reading, tell user to click 'I Agree' button to continue."
	)

def get_settings() -> Settings:
	"""Load and return validated settings.

	In later phases we can load .env via python-dotenv and add validation.
	"""
	return Settings()


# ============================================================================
# Gemini Pricing for Token Tracking (per-token rates, keyed by model family)
# ============================================================================
# Rates are per-1M list prices from https://ai.google.dev/gemini-api/docs/pricing,
# divided to per-token here. Output rates include thinking tokens. Keyed by model
# FAMILY so the active model (MODEL_NATIVE, set by USE_PREMIUM_MODEL) selects the
# right row — this is what makes a 2.5 -> 3.1 A/B comparable on cost.
# Verified against ai.google.dev/gemini-api/docs/pricing on 2026-05-30 for
# gemini-2.5-flash-native-audio-preview-12-2025 and gemini-3.1-flash-live-preview.
# Updated: 2026-05-30.
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

# Family used when a model name doesn't match any known family — a safe
# fall-back for unrecognized/unspecified model strings (bills at the cheaper
# 2.5 rate). NOTE: this is the pricing fallback for UNKNOWN names, NOT the
# runtime default model — the active default is 3.1 (USE_PREMIUM_MODEL=true).
DEFAULT_PRICING_FAMILY = "2.5"


def model_family(model_name: str | None) -> str:
	"""Map a Gemini model name to a pricing family key in GEMINI_PRICING_BY_FAMILY.

	Matches the version number as a whole token, NOT a bare substring, so
	'gemini-3.10-flash' does not match family '3.1' and 'gemini-12.5-...' does
	not match '2.5'. The version must be bounded by a non-version character (or
	the start/end of the string) on each side — i.e. not preceded by a digit/dot
	and not followed by a digit/dot. Falls back to DEFAULT_PRICING_FAMILY for
	empty/unrecognized names so cost tracking never crashes on a new preview
	model — it just bills at the default until a row is added here.
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
# A COPY, not the live inner dict — a stray mutation of GEMINI_PRICING must not
# corrupt GEMINI_PRICING_BY_FAMILY for everyone else in the process.
GEMINI_PRICING = dict(GEMINI_PRICING_BY_FAMILY[DEFAULT_PRICING_FAMILY])

