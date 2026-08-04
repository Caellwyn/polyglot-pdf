> [!WARNING]
> **Preview:** The Live API is in preview.

> SDK version documented: `google-genai` 2.8.0 (verified 2026-06-11).

This guide covers best practices you can follow to
optimize your use of the Live API.
See [Get started with Live API](https://ai.google.dev/gemini-api/docs/live)
page for an overview and sample code for common use cases.

## Design clear system instructions

To get the best performance out of Live API, we recommend having a
clearly-defined set of system instructions (SIs) that defines the agent persona,
conversational rules, and guardrails, in this order.

For best results, separate each agent into a distinct SI.

1. **Specify the agent persona:** Provide detail on the agent's name, role, and
   any preferred characteristics. If you want to specify the accent, be sure to
   also specify the preferred output language (such as a British accent for an
   English speaker).

2. **Specify the conversational rules:** Put these rules in the order you expect
   the model to follow. Delineate between one-time elements of the conversation
   and conversational loops. For example:

   - **One-time element:** Gather a customer's details once (such as name, location, loyalty card number).
   - **Conversational loop:** The user can discuss recommendations, pricing, returns, and delivery, and may want to go from topic to topic. Let the model know that it's OK to engage in this conversational loop for as long as the user wants.
3. **Specify tool calls within a flow in distinct sentences:** For example, if a
   one-time step to gather a customer's details requires invoking a `get_user_info`
   function, you might say: *Your first step is to gather user information. First,
   ask the user to provide their name, location, and loyalty card number. Then
   invoke `get_user_info` with these details.*

4. **Add any necessary guardrails:** Provide any general conversational
   guardrails you don't want the model to do. Feel free to provide specific
   examples of if *x* happens, you want the model to do *y* . If you're still not
   getting the preferred level of precision, use the word
   *unmistakably* to guide the model to be precise.

## Define tools precisely

When using tools with Live API, be specific in your tool definitions.
Be sure to tell Gemini under what conditions a tool call should be
invoked. For more details, see [Tool definitions](https://ai.google.dev/gemini-api/docs/live-api/best-practices#tool-definitions-example) in
the example section.

## Craft effective prompts

- **Use clear prompts:** Provide examples of what the models should and shouldn't do in the prompts, and try to limit prompts to one prompt per persona or role at a time. Instead of lengthy, multi-page prompts, consider using prompt chaining instead. The model performs best on tasks with single function calls.
- **Provide starting commands and information:** Live API expects user input before it responds. To have Live API initiate the conversation, include a prompt asking it to greet the user or begin the conversation. Include information about the user to have Live API personalize that greeting.

## Specify language

For optimal performance on Live API cascaded `gemini-live-2.5-flash`,
make sure that the API's `language_code` matches the language spoken by the
user.

If the expectation is for the model to respond in a non-English language,
include the following as part of your system instructions:

    RESPOND IN {OUTPUT_LANGUAGE}. YOU MUST RESPOND UNMISTAKABLY IN {OUTPUT_LANGUAGE}.

> **Endpoint-verified in this repo (bd polyglot-pdf-m1lg, 2026-07-22):** the
> Live connect config accepts `speech_config` in dict form on the Vertex
> native-audio tier: `config["speech_config"] = {"language_code": "es-US"}`
> (SDK type `types.SpeechConfig`: fields `language_code`, `voice_config`,
> `multi_speaker_voice_config`). The adapter sets it from the session's
> BCP-47 bias code behind `SPEECH_LANGUAGE_CODE_ENABLED`. NOT verified on the
> premium AI-Studio 3.1 tier (same caveat as the transcription
> `language_codes` hint).

## Streaming

When implementing real-time audio, follow these best practices:

- **Chunk Size and Latency**: Send audio in chunks of 20ms to 40ms.
- **Interruption Handling** : When the user speaks while the model is replying, the server sends a `server_content` message with `"interrupted": true`. You must immediately discard your client-side audio buffer to prevent the agent from continuing to talk over the user.

## Context management

Use `ContextWindowCompressionConfig` for long sessions, as native audio tokens
accumulate rapidly (approximately 25 tokens per sec of audio).

**DEAD END for native-audio models (verified 2026-06-04, bd polyglot-pdf-l3a.1):**
`ContextWindowCompressionConfig` is an unreleased/unsupported stub on native-audio
Live models. The SDK type exists and the config serializes without error, but the
server NEVER evicts tokens -- prompt tokens compound past the trigger exactly as
with compression off. Keep `CONTEXT_COMPRESSION_ENABLED=False` for native-audio
models; do not re-investigate unless Google announces support. See
`docs/genai_docs/README.md` hard-won facts for full detail.

## Client buffering

Don't buffer input audio significantly (such as 1 second) before sending. Send
small chunks (20ms - 100ms) to minimize latency.

## Resampling

Ensure your client application resamples microphone input (often 44.1kHz or
48kHz) to 16kHz before transmission.

## Session management

Follow these guidelines to handle session lifecycle and ensure a reliable user
experience:

- **Enable context window compression:** Audio tokens accumulate at approximately 25 tokens per second. Without compression, audio-only sessions are limited to 15 minutes and audio-video sessions to 2 minutes. Enable [context window compression](https://ai.google.dev/gemini-api/docs/live-api/session-management#context-window-compression) to extend sessions to an unlimited duration.
- **Implement session resumption:** The server may periodically reset the WebSocket connection. Use [session resumption](https://ai.google.dev/gemini-api/docs/live-api/session-management#session-resumption) to seamlessly reconnect without losing context. Retain the latest resumption token from `SessionResumptionUpdate` messages and pass it as the handle when reconnecting. Resumption tokens are valid for 2 hours after the last session terminates.
- **Handle GoAway messages:** The server sends a [GoAway](https://ai.google.dev/gemini-api/docs/live-api/session-management#goaway-message) message before terminating a connection. Listen for this message and use the `timeLeft` field to gracefully wrap up or reconnect before the connection closes.
- **Handle generationComplete signals:** Use the [`generationComplete`](https://ai.google.dev/gemini-api/docs/live-api/session-management#generation-complete-message) message to know when the model has finished generating a response, so your application can update its UI or proceed with the next action.

For implementation details, see
[Session management](https://ai.google.dev/gemini-api/docs/live-api/session-management).

## Additive 2.8.0 features relevant to voice work

The following types and fields were added between 1.38.0 and 2.8.0. They are
present in the installed SDK and their shapes are verified by inspection.
**They are NOT yet endpoint-verified on our native-audio models** -- per the
hard-won rule in `docs/genai_docs/README.md`, type existence is not availability.
Do not use any of these in production code without a connect-and-probe first.

### Explicit VAD signal (available as of 2.8.0, NOT yet endpoint-verified)

`LiveConnectConfig` gained `explicit_vad_signal` (bool). When set, the server
emits `LiveServerMessage.voice_activity_detection_signal` events for explicit
VAD start/end signals alongside the existing `voice_activity` field.
`LiveServerMessage` now has both `voice_activity` and
`voice_activity_detection_signal` fields (verified present in 2.8.0 type).
These are intended to replace manual `activity_start`/`activity_end` signaling
for VAD-aware clients; our current VAD path (via `DISABLE_GEMINI_VAD` and
`activity_start`/`activity_end`) remains the only endpoint-verified approach.

### Transcription language codes (available as of 2.8.0, endpoint-verified on the default tier 2026-07-16)

`AudioTranscriptionConfig` gained `language_codes` (list of BCP-47 strings,
e.g. `["en-US", "es-MX"]`). Pass via `LiveConnectConfig.input_audio_transcription`
or `output_audio_transcription`. This allows hinting the transcription language
for multilingual sessions, which is directly relevant to the polyglot-pdf use
case. Endpoint behavior: **VERIFIED ACCEPTED** on the production default tier
(`gemini-live-2.5-flash-native-audio`, Vertex) with the full deploy config --
connect + audio reply, no 1007 (bd polyglot-pdf-y25o;
`scripts/spikes/transcription_lang_codes_findings.md`). Shipped as the ASR
language bias behind `TRANSCRIPTION_LANGUAGE_HINT_ENABLED` (default true).
Premium tier (AI Studio 3.1) remains unverified -- 3.1 does not exist on
Vertex, so USE_PREMIUM_MODEL=true is LOCAL-ONLY (a deployed service resolves an
id Vertex does not publish and 1008s at connect; see
`../standards/ai-models.md` and bd polyglot-pdf-llva). Verify this behavior
locally before 3.1 is ever deployed.

### Translation config (available as of 2.8.0, NOT yet endpoint-verified)

`LiveConnectConfig` gained `translation_config` (`TranslationConfig`). Intended
to enable real-time speech translation. Not explored for this repo yet.

### History config (available as of 2.8.0, NOT yet endpoint-verified)

`LiveConnectConfig` gained `history_config` (`HistoryConfig`). Related to the
1.67 `initial_history_in_client_content` feature for pre-seeding session context.

### Thinking config in LiveConnectConfig (available as of 2.8.0)

`LiveConnectConfig` gained `thinking_config`. This is the same
`ThinkingConfig` type used in `GenerateContentConfig`. Whether it does anything
on native-audio Live models is unverified.

### Session ID and setup_complete on AsyncSession (available as of 2.8.0)

`AsyncSession` now exposes two instance attributes set at construction time:
- `session.session_id` -- the server-assigned session ID (may be `None` until
  setup_complete arrives).
- `session.setup_complete` -- the `LiveServerSetupComplete` message object
  (`None` until received). Also present as `LiveServerMessage.setup_complete`.

## Examples

This example combines both the best practices and
[guidelines for system instruction design](https://ai.google.dev/gemini-api/docs/live-api/best-practices#system-instruction-guidelines) to
guide the model's performance as a career coach.

    **Persona:**
    You are Laura, a career coach from Brooklyn, NY. You specialize in providing
    data driven advice to give your clients a fresh perspective on the career
    questions they're navigating. Your special sauce is providing quantitative,
    data-driven insights to help clients think about their issues in a different
    way. You leverage statistics, research, and psychology as much as possible.
    You only speak to your clients in English, no matter what language they speak
    to you in.

    **Conversational Rules:**

    1. **Introduce yourself:** Warmly greet the client.

    2. **Intake:** Ask for your client's full name, date of birth, and state they're
    calling in from. Call `create_client_profile` to create a new patient profile.

    3. **Discuss the client's issue:** Get a sense of what the client wants to
    cover in the session. DO NOT repeat what the client is saying back to them in
    your response. Don't ask more than a few questions here.

    4. **Reframe the client's issue with real data:** NO PLATITUDES. Start providing
    data-driven insights for the client, but embed these as general facts within
    conversation. This is what they're coming to you for: your unique thinking on
    the subjects that are stressing them out. Show them a new way of thinking about
    something. Let this step go on for as long as the client wants. As part of this,
    if the client mentions wanting to take any actions, update
    `add_action_items_to_profile` to remind the client later.

    5. **Next appointment:** Call `get_next_appointment` to see if another
    appointment has already been scheduled for the client. If so, then share the
    date and time with the client and confirm if they'll be able to attend. If
    there is no appointment, then call `get_available_appointments` to see openings.
    Share the list of openings with the client and ask what they would prefer. Save
    their preference with `schedule_appointment`. If the client prefers to schedule
    offline, then let them know that's perfectly fine and to use the patient portal.

    **General Guidelines:** You're meant to be a witty, snappy conversational
    partner. Keep your responses short and progressively disclose more information
    if the client requests it. Don't repeat back what the client says back to them.
    Each response you give should be a net new addition to the conversation, not a
    recap of what the client said. Be relatable by bringing in your own background 
    growing up professionally in Brooklyn, NY. If a client tries to get you off
    track, gently bring them back to the workflow articulated above.

    **Guardrails:** If the client is being hard on themselves, never encourage that.
    Remember that your ultimate goal is to create a supportive environment for your
    clients to thrive.

### Tool definitions

This JSON defines the relevant functions called in the career coach example.
For best results when defining functions, include their names, descriptions,
parameters, and invocation conditions.

    [
     {
       "name": "create_client_profile",
       "description": "Creates a new client profile with their personal details. Returns a unique client ID. \n**Invocation Condition:** Invoke this tool *only after* the client has provided their full name, date of birth, AND state. This should only be called once at the beginning of the 'Intake' step.",
       "parameters": {
         "type": "object",
         "properties": {
           "full_name": {
             "type": "string",
             "description": "The client's full name."
           },
           "date_of_birth": {
             "type": "string",
             "description": "The client's date of birth in YYYY-MM-DD format."
           },
           "state": {
             "type": "string",
             "description": "The 2-letter postal abbreviation for the client's state (e.g., 'NY', 'CA')."
           }
         },
         "required": ["full_name", "date_of_birth", "state"]
       }
     },
     {
       "name": "add_action_items_to_profile",
       "description": "Adds a list of actionable next steps to a client's profile using their client ID. \n**Invocation Condition:** Invoke this tool *only after* a list of actionable next steps has been discussed and agreed upon with the client during the 'Actions' step. Requires the `client_id` obtained from the start of the session.",
       "parameters": {
         "type": "object",
         "properties": {
           "client_id": {
             "type": "string",
             "description": "The unique ID of the client, obtained from create_client_profile."
           },
           "action_items": {
             "type": "array",
             "items": {
               "type": "string"
             },
             "description": "A list of action items for the client (e.g., ['Update resume', 'Research three companies'])."
           }
         },
         "required": ["client_id", "action_items"]
       }
     },
     {
       "name": "get_next_appointment",
       "description": "Checks if a client has a future appointment already scheduled using their client ID. Returns the appointment details or null. \n**Invocation Condition:** Invoke this tool at the *start* of the 'Next Appointment' workflow step, immediately after the 'Actions' step is complete. This is used to check if an appointment *already exists*.",
       "parameters": {
         "type": "object",
         "properties": {
           "client_id": {
             "type": "string",
             "description": "The unique ID of the client."
           }
         },
         "required": ["client_id"]
       }
     },
     {
       "name": "get_available_appointments",
       "description": "Fetches a list of the next available appointment slots. \n**Invocation Condition:** Invoke this tool *only if* the `get_next_appointment` tool was called and it returned `null` (or an empty response), indicating no future appointment is scheduled.",
       "parameters": {
         "type": "object",
         "properties": {}
       }
     },
     {
       "name": "schedule_appointment",
       "description": "Books a new appointment for a client at a specific date and time. \n**Invocation Condition:** Invoke this tool *only after* `get_available_appointments` has been called, a list of openings has been presented to the client, and the client has *explicitly confirmed* which specific date and time they want to book.",
       "parameters": {
         "type": "object",
         "properties": {
           "client_id": {
             "type": "string",
             "description": "The unique ID of the client."
           },
           "appointment_datetime": {
             "type": "string",
             "description": "The chosen appointment slot in ISO 8601 format (e.g., '2025-10-30T14:30:00')."
           }
         },
         "required": ["client_id", "appointment_datetime"]
       }
     }
    ]

## Pricing and billing

The Gemini Live API bills strictly by token usage. Because the Live API maintains a persistent WebSocket session, billing follows a compounding model based on the active context window.

### The session context window (compounding costs)

The API charges you per turn for all tokens present in the session context window. A "turn" is defined as one user input and the model's corresponding response.

- **Accumulation:** The context window includes new tokens from the current turn plus all accumulated tokens from previous turns.
- **Re-billing:** Past tokens are re-processed and accounted for in each new turn, up to your configured context window size. As a session lengthens, the cost per turn increases because the conversational history is re-processed.

### Audio tokens and transcriptions

The Live API is natively multimodal. It retains conversational history as raw audio tokens to preserve acoustic nuance and tone.

- **Audio billing:** The API bills you for the accumulated native audio tokens at the standard audio input rate on every turn.
- **Transcription surcharge:** When audio-to-text transcription is enabled (`inputAudioTranscription` or `outputAudioTranscription`), the API charges for all text tokens generated for transcription at the text token output rate in addition to the standard audio token costs.

### Managing costs with context limits

To prevent unbounded cost growth in long sessions, configure your context window size using `contextWindowCompression`.

By setting a compression trigger (e.g., 25,000 tokens) and a sliding window (e.g., 8,000 tokens), the API automatically evicts older tokens once the threshold is reached. The API then bills subsequent turns only for the retained history plus any new tokens.

### Proactive audio mode

When Proactive Audio Mode is enabled, input tokens are charged the entire time the Live API is listening, while output tokens are only charged when the API responds.

- **Note for Gemini 3.1:** Proactive Audio Mode is not supported in `gemini-3.1-flash-live-preview`. For this model, you are only billed for audio when actively streaming input.

For detailed pricing information, see the [Gemini API pricing page](https://ai.google.dev/gemini-api/docs/pricing).