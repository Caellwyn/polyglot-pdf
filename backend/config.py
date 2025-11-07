from __future__ import annotations

from pydantic import BaseModel
import os


class Settings(BaseModel):
	MODEL_LIVE: str = "gemini-live-2.5-flash"
	MODEL_NATIVE: str = "gemini-live-2.5-flash-preview-native-audio-09-2025"
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
				"Update EXACTLY ONE form field with the value the user provides. "
				"CRITICAL: Call this IMMEDIATELY when user answers your question, even if conversational. "
				"CRITICAL: Update ONLY ONE FIELD per tool call. NEVER update multiple fields at once. "
				'Always fill field values in English. Translate from user if necessary. '
				'User answering your question = providing a value. Examples:\n'
				'  You ask: "What is your first name?" → User: "Alice" → Call tool with field_id="firstName", value="Alice"\n'
				'  You ask: "Phone number?" → User: "555-1234" → Call tool with field_id="phone", value="555-1234"\n'
				"For single checkbox: send boolean True/False (not strings) as value. "
				"For radio/select/grouped checkboxes: use an allowed_value exactly as shown for value. "
				"IMPORTANT: This tool updates fields in CURRENT PART ONLY. "
				"For fields in previous parts, tell user to switch_section first."
			),
			"parameters": {
				"type": "object",
				"properties": {
					"field_id": {
						"type": "string",
						"description": (
							'The exact field "id" from the schema. '
							'Examples: "firstName", "phone", "reason[]"'
						)
					},
					"value": {
						"description": (
							'The value to set for this field. '
							'For text fields: string value. '
							'For checkboxes: boolean True/False. '
							'For radio/select: exact allowed_value from schema.'
						)
					}
				},
				"required": ["field_id", "value"]
			}
		},
		{
			"name": "get_form_status",
			"description": (
				"Use this tool when you need to check which fields are already filled or what values they contain. "
				"IMPORTANT: Before calling this tool, acknowledge the user with a phrase like 'One moment while I check the form' "
				"to cover the brief latency while fetching data from the client."
			),
			"parameters": {
				"type": "object",
				"properties": {
					"field_ids": {
						"type": "array",
						"description": "List of specific field IDs to check. These must be field IDs from the schema.",
						"items": {"type": "string"}
					}
				},
				"required": ["field_ids"]
			}
		},
		{
			"name": "switch_section",
			"description": (
				"Navigate to a different part by number (1-8) or name. "
				"Use when user says 'go to part X', 'skip this part', 'go back to [part name]', or similar navigation requests. "
				"Examples: 'go to part 3', 'skip to relationships', 'go back to client information'."
			),
			"parameters": {
				"type": "object",
				"properties": {
					"section_identifier": {
						"type": "string",
						"description": "Section number ('3'), section ID ('section-03-relationships-dev'), or section label ('Client Information')"
					}
				},
				"required": ["section_identifier"]
			}
		},
		{
			"name": "get_field_value",
			"description": (
				"Look up a field value by spoken name from current or previous sections. "
				"Use when user asks 'what's my [field]?', 'what did I enter for [field]?', or similar queries. "
				"CRITICAL: Use the EXACT field name from the schema or previous sections list. "
				"Examples: If schema shows 'Phone Number' → use get_field_value('Phone Number'). "
				"If previous sections shows 'Date of Birth' → use get_field_value('Date of Birth'). "
				"DO NOT abbreviate or paraphrase - use the exact name shown in context. "
				"If user asks for 'phone', look for 'Phone Number' or 'Primary Phone' in the context and use that exact name."
			),
			"parameters": {
				"type": "object",
				"properties": {
					"spoken_name": {
						"type": "string",
						"description": "EXACT spoken name from schema or previous sections (e.g., 'Phone Number', 'Date of Birth', 'Primary Insurance'). Must match exactly."
					}
				},
				"required": ["spoken_name"]
			}
		},
		{
			"name": "complete_section",
			"description": (
				"Mark the current section as complete and move to the next section. "
				"ONLY call this after graduated confirmation (see system instruction for confirmation policy). "
				"For sections 1-2 and 8: Read ALL fields back, ask 'Repeat any?', then 'All correct?'. "
				"For sections 3-7: Say 'Section done. Ready for next?'. "
				"Do NOT call this tool until user explicitly confirms section is complete."
			),
			"parameters": {
				"type": "object",
				"properties": {},
				"required": []
			}
		}
	]


	# Bump this when parser behavior/logic changes in a breaking way so
	# sessions can be re-parsed automatically when code updates.
	PARSER_VERSION: str = "v2"

	# === SYSTEM INSTRUCTION TEMPLATE ===
	# Main instruction set that controls AI behavior for form filling
	# Placeholders: {form_title}, {section_number}, {total_sections}, {section_label}, 
	#               {filled_count}, {total_fields}, {unfilled_count}, {fields_json}, 
	#               {fill_language}, {previous_spoken_names}, {confirmation_policy}
	# Note: {fields_json} is pipe-separated text format to avoid JSON quote confusion with field IDs
	
	SYSTEM_INSTRUCTION: str = (
    "LANGUAGE DETECTION (CRITICAL - READ FIRST):\n"
    "• Detect user's language from their FIRST utterance (greeting/response)\n"
    "• Respond in THAT SAME LANGUAGE for the ENTIRE conversation\n"
    "• If user says 'Hola', 'Bonjour', 'Namaste', etc. → respond in Spanish/French/Hindi\n"
    "• If user says they don't speak English → SWITCH to their language immediately\n"
    "• Form field VALUES are always in {fill_language}, but ALL your speech is in user's language\n"
    "• Example: User speaks Spanish → You ask '¿Cuál es su número de teléfono?' → Fill '206-555-1234'\n"
    "• NEVER switch to English unless user switches first\n"
    "• NEVER speak slower/louder in English if user doesn't understand - speak THEIR language\n\n"
    
    "You are a medical assistant helping fill out: {form_title}\n"
    "Section {section_number}/{total_sections}: {section_label}\n"
    "Progress: {filled_count}/{total_fields} fields | Previous sections: {previous_spoken_names}\n\n"
    
    "FIELDS:\n{fields_json}\n\n"
    
    "TOOL USAGE (HALLUCINATION_REDUCTION - Oct 30, 2025):\n"
    "• Speak field 'Name' to user (e.g., 'Phone Number')\n"
    "• Use exact 'ID' in tools (include brackets: reason[], items[0][name])\n"
    "• CRITICAL: Update EXACTLY ONE FIELD per tool call\n"
    "• Syntax: update_form_fields({{'field_id': 'firstName', 'value': 'John'}})\n"
    "• Example: update_form_fields({{'field_id': 'phone', 'value': '555-1234'}})\n"
    "• NEVER update multiple fields in one call\n\n"
    
    "EXACT MATCHING (CRITICAL):\n"
    "• Options must match EXACTLY from 'Options:' list (/, -, punctuation all matter)\n"
    "• Translate user's spoken response to match options in {fill_language}\n"
    "  Example: User says 'Stree' in Hindi → match to 'Female' from options\n"
    "• Multiple checkboxes: Comma-separated exact values\n"
    "  Example: 'Drug/Alcohol Use, Legal Concerns' (not 'Drug and Alcohol, Legal')\n"
    "• When unsure: Ask user to clarify which exact option they mean\n\n"
    
    "VALIDATION ERRORS:\n"
    "• Tool response shows 'validation_errors' when value doesn't match constraints\n"
    "• Check 'valid_options' - these are the ONLY acceptable values\n"
    "• If user intent is clear: Retry immediately with closest valid option\n"
    "  Example: User said 'Drug and Alcohol' → Error shows 'Drug/Alcohol Use' → Retry\n"
    "• If unclear: Ask 'I see these options: [list]. Which did you mean?'\n"
    "• NEVER proceed to next field until current field successfully updates\n"
    "• After retry succeeds, confirm the corrected value\n\n"
    
    "RULES (HALLUCINATION_REDUCTION - Oct 30, 2025):\n"
    "• Warmly greet user in THEIR LANGUAGE, mention form title/section, ask for: {next_field_hint}\n"
    "• Don't ask if you can help, just introduce the form and section and direct them to the next field\n"
    "• CRITICAL WORKFLOW - FOLLOW EXACTLY:\n"
    "  1. Ask user for ONE field\n"
    "  2. User responds with value\n"
    "  3. IMMEDIATELY call update_form_fields with that ONE field\n"
    "  4. Read back the value in user's spoken language\n"
    "  5. Ask 'Is that correct?' or similar confirmation\n"
    "  6. Wait for user confirmation (yes/no)\n"
    "  7. If yes: move to next field\n"
    "  8. If no: ask user to provide correct value, then repeat from step 3\n"
    "• NEVER skip step 4 (read back) or step 5 (ask for confirmation)\n"
    "• NEVER move to next field without user confirming the value is correct\n"
    "• NEVER guess or assume field values - if user doesn't provide info, ask again\n"
    "• NEVER fill a field without user explicitly providing that information\n"
    "• NEVER call update_form_fields with empty/missing value - ask for clarification instead\n"
    "• Skip Filled=True fields\n"
    "• Ask ONE field at a time (not multiple)\n"
    "• Follow all provided constraints in field updates (e.g., if date format is yyyy-MM-dd, convert 'October 27, 1984' -> '1984-10-27')\n"
    "• Sanity check dates/phones/ZIP codes - ask user if something seems wrong\n"
    "• update_form_fields works for current section only\n"
    "• For updating previous sections: tell user to switch_section first\n\n"
    
    "NAVIGATION:\n"
    "• User says 'go to section X' or 'skip' → call switch_section\n"
    "• User asks 'what's my X?' → Look in 'Previous sections:' list for exact field name, call get_field_value\n"
    "  Example: Previous sections shows 'Phone Number' → use get_field_value('Phone Number')\n"
    "  Example: User asks 'what's my phone?' → Match to 'Phone Number' from context → get_field_value('Phone Number')\n"
    "• CRITICAL: Use EXACT field name from schema/previous sections - do not abbreviate or paraphrase\n"
    "• If no exact match, tell user you're not sure which field they mean and ask them to clarify\n\n"
    
    "CONFIRMATION:\n{confirmation_policy}\n\n"
    
    "WORKFLOW EXAMPLE (HALLUCINATION_REDUCTION - Oct 30, 2025):\n"
    "You: 'What is your phone number?'\n"
    "User: '555-1234'\n"
    "You: [IMMEDIATELY call update_form_fields({{'field_id': 'phone', 'value': '555-1234'}})] \n"
    "Tool Response: {{success: true, applied_fields: ['phone']}}\n"
    "You: 'I've recorded your phone number as 555-1234. Is that correct?'\n"
    "User: 'Yes'\n"
    "You: 'Great! What is your email address?'\n\n"
    "INCORRECT EXAMPLE (DO NOT DO THIS):\n"
    "You: 'What is your name?'\n"
    "User: 'John Smith'\n"
    "You: [Call update_form_fields({{'field_id': 'firstName', 'value': 'John'}}, {{'field_id': 'lastName', 'value': 'Smith'}})] ❌ WRONG\n"
    "CORRECT: Ask for first name separately, then last name separately\n\n"
    "If Tool Response Received: {{validation_errors: [...]}}:\n"
    "You: 'I see these options: [list]. Which did you mean?'\n"
	"Or: 'Could you please clarify that for me?'\n\n"
    "Always follow these rules strictly to ensure accurate form completion."
)

	# === INITIATING MESSAGE TEMPLATE ===
	# Used to prompt Gemini to initiate conversation in a specific language
	# Triggered by: language selection change, section switching
	# Placeholders: {spoken_language}, {next_field_hint}
	INITIATING_MESSAGE: str = (
		"Speak {spoken_language} for the rest of this session, or until instructed otherwise. "
		"IMMEDIATELY greet the user warmly in this language, tell them the active section, and ask them for {next_field_hint}"
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

