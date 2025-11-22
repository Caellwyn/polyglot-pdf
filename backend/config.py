from __future__ import annotations

from pydantic import BaseModel
import os
from pathlib import Path



class Settings(BaseModel):
	MODEL_LIVE: str = "gemini-live-2.5-flash"
	MODEL_NATIVE: str = "gemini-live-2.5-flash-preview-native-audio-09-2025"
	MODEL_LABELING: str | None = None
	VERTEXAI: bool = True # Whether to use Vertex AI for LLM and embedding operations.
	USE_NATIVE_AUDIO: bool = True  # Use Gemini's native audio generation (vs. cascade)
	DISABLE_GEMINI_VAD: bool = True  # CRITICAL: Disable Gemini's VAD when using manual activity_start/end signals
	GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
	PROACTIVE_AUDIO: bool = False  # HALLUCINATION_REDUCTION (Oct 30, 2025): Enable to ignore dirty/choppy audio
	
	# Audio settings
	AUDIO_IN_RATE: int = 16000
	AUDIO_OUT_RATE: int = 24000
	MAX_UPLOAD_MB: int = 5
	WS_CHUNK_MS: int = 20
	WS_PING_INTERVAL_SEC: int = 15
	WS_IDLE_TIMEOUT_SEC: int = 60  # Close WebSocket after 60s of no activity (saves resources)
	WS_MAX_OUTBOX: int = 100
	WS_MAX_AUDIO_FRAME_BYTES: int = 32000  # ~1s at 16kHz mono PCM16 (2 bytes/sample)
	
	# LLM normalizer settings
	ENABLE_LLM_FIELD_NORMALIZATION: bool = True
	LLM_NORMALIZER_MODEL: str = "gemini-2.5-pro"
	LLM_NORMALIZER_MAX_FIELDS: int = 120
	LLM_NORMALIZER_NEAR_TEXT_RADIUS: int = 36
	LLM_NORMALIZER_TEMPERATURE: float = 0.2

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
    "3. Read back value → Ask 'Is that correct?'\n"
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
		"Speak {spoken_language}. Read this disclaimer aloud: 'This tool helps you fill out your form, but it does not provide legal advice. Please review all information carefully before submitting. For complex cases, consult an immigration attorney.' After reading, tell user to click 'I Agree' button to continue."
	)

def get_settings() -> Settings:
	"""Load and return validated settings.

	In later phases we can load .env via python-dotenv and add validation.
	"""
	return Settings()


# (LLM normalizer settings live on Settings; no module-level duplicates.)

# ============================================================================
# Gemini Pricing for Token Tracking
# ============================================================================
# Pricing for Gemini 2.0 Flash (per token, converted from per-million rates)
# Source: https://ai.google.dev/pricing
# Updated: October 2025
GEMINI_PRICING = {
	# Input pricing (per token)
	"text_input": 0.50 / 1_000_000,      # $0.50 per million = $0.0000005 per token
	"audio_input": 3.00 / 1_000_000,     # $3.00 per million = $0.000003 per token

	# Output pricing (per token, includes thinking tokens)
	"text_output": 2.00 / 1_000_000,     # $2.00 per million = $0.000002 per token
	"audio_output": 12.00 / 1_000_000,   # $12.00 per million = $0.000012 per token
}

