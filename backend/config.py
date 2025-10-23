from __future__ import annotations

from pydantic import BaseModel
import os


class Settings(BaseModel):
	MODEL_LIVE: str = "gemini-live-2.5-flash-preview"
	MODEL_NATIVE: str = "gemini-live-2.5-flash-preview-native-audio-09-2025"
	# Whether to use Vertex AI for LLM and embedding operations.
	VERTEXAI: bool = True
	USE_NATIVE_AUDIO: bool = True
	DISABLE_GEMINI_VAD: bool = True  # CRITICAL: Disable Gemini's VAD when using manual activity_start/end signals
	# LLM normalizer settings
	ENABLE_LLM_FIELD_NORMALIZATION: bool = True
	LLM_NORMALIZER_MODEL: str = "gemini-2.5-flash-lite"
	LLM_NORMALIZER_MAX_FIELDS: int = 120
	LLM_NORMALIZER_NEAR_TEXT_RADIUS: int = 36
	LLM_NORMALIZER_TEMPERATURE: float = 0.2
	AUDIO_IN_RATE: int = 16000
	AUDIO_OUT_RATE: int = 24000
	MAX_UPLOAD_MB: int = 5
	WS_CHUNK_MS: int = 20
	WS_PING_INTERVAL_SEC: int = 15
	WS_IDLE_TIMEOUT_SEC: int = 60  # Close WebSocket after 60s of no activity (saves resources)
	WS_MAX_OUTBOX: int = 100
	WS_MAX_AUDIO_FRAME_BYTES: int = 32000  # ~1s at 16kHz mono PCM16 (2 bytes/sample)
	GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
	PROACTIVE_AUDIO: bool = False  # Gemini proactivity setting for live sessions
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
		{
			"name": "update_form_fields",
			# "behavior": "NON_BLOCKING",
			# 'scheduling': 'WHEN_IDLE',
			"description": (
				"Update one or more form fields with values the user provides in response to your questions. "
				"CRITICAL: Call this IMMEDIATELY when user answers your question, even if conversational. "
				'Always fill field values in English. Translate from user if necessary. '
				'User answering your question = providing a value. Examples:\n'
				'  You ask: "What are your strengths?" → User: "I\'m confident" → Call tool with {{"strengths": "confident"}}\n'
				'  You ask: "Phone number?" → User: "555-1234" → Call tool with {{"phone": "555-1234"}}\n'
				"For single checkbox: send boolean True/False (not strings). "
				"For radio/select/grouped checkboxes: use an allowed_value exactly as shown. "
				"Batch multiple fields only if the user clearly supplied them together in one statement. "
				"IMPORTANT: This tool updates fields in CURRENT SECTION ONLY. "
				"For fields in previous sections, tell user to switch_section first."
			),
			"parameters": {
				"type": "object",
				"properties": {
					"updates": {
						"type": "object",
						"description": (
							'Dictionary mapping field IDs to values. Use the exact field "id" from schema as keys. '
							'Examples: {"firstName": "Alice", "reason[]": "Annual Checkup, Cancer Screening"}'
						),
					}
				},
				"required": ["updates"]
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
				"Navigate to a different section by number (1-8) or name. "
				"Use when user says 'go to section X', 'skip this section', 'go back to [section name]', or similar navigation requests. "
				"Examples: 'go to section 3', 'skip to relationships', 'go back to client information'."
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
    
    "TOOL USAGE:\n"
    "• Speak field 'Name' to user (e.g., 'Phone Number')\n"
    "• Use exact 'ID' in tools (include brackets: reason[], items[0][name])\n"
    "• Syntax: update_form_fields({{'updates': {{'firstName': 'John', 'reason[]': 'Checkup'}}}}\n\n"
    
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
    
    "RULES:\n"
    "• Warmly greet user in THEIR LANGUAGE, mention form title/section, ask for: {next_field_hint}\n"
    "• Don't ask if you can help, just introduce the form and section and direct them to the next field\n"
    "• CRITICAL: When you ask for a field and user responds, IMMEDIATELY call update_form_fields and confirm response\n"
    "  - User answering your question = they are providing the value\n"
    "  - Do NOT just converse or acknowledge - CAPTURE FIRST with tool call\n"
    "  - Then confirm after tool succeeds: **ALWAYS CONFIRM USER RESPONSE BEFORE MOVING TO THE NEXT FIELD**\n"
    "• NEVER call update_form_fields with empty updates {{}} - ask for clarification instead\n"
    "• Skip Filled=True fields\n"
    "• Ask ONE field at a time\n"
    "• ALWAYS call update_form_fields when user gives a value (use 'NA' if not applicable)\n"
    "• Follow all provided constraints in field updates (e.g., if date formate is yyyy-MM-dd, convert 'October 27, 1984' -> '1984-10-27')\n"
    "• Sanity check dates/phones/ZIP codes - ask user if something seems wrong\n"
    "• Never guess field values - ask user if unsure\n"
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
    
    "WORKFLOW EXAMPLE:\n"
    "You: 'What are your strengths?'\n"
    "User: 'Confidence and empathy'\n"
    "You: [IMMEDIATELY call update_form_fields({{'strengths': 'Confidence and empathy'}})] \n"
    "If Tool Response Received: {{success: true}}:\n"
    "You: 'Got it, I've recorded confidence and empathy as your strengths. [Ask next field]'\n\n"
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

