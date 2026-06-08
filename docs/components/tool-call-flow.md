# Tool-call flow (Gemini Live <-> backend <-> frontend)

**Tracks:** backend/adapters/live_ai_gemini.py backend/services/callback_handler.py backend/services/request_coordinator.py backend/config.py

*Last updated: 2026-06-08. See [../journal/entries/2026-06-07-bd-0y7-confirm-loop-breaker.md](../journal/entries/2026-06-07-bd-0y7-confirm-loop-breaker.md) for the confirm-loop breaker, and [../journal/entries/2026-06-07-bd-kbf-gemini-io-logging.md](../journal/entries/2026-06-07-bd-kbf-gemini-io-logging.md) for the Gemini I/O logging.*

Map of what the CODE expects for each Gemini tool call vs. what is actually on
the wire, plus the dev-log `message_type`s that capture each hop. Use this as the
key for reading a captured `backend/logs/gemini_<date>.jsonl` when debugging tool
reliability (e.g. "why didn't `update_form_fields` land?"). The dev capture is
local-only (`.env.DEV`-gated) -- see [voice-ai.md](voice-ai.md) for the adapter
overview and [../standards/hipaa-pii-policy.md](../standards/hipaa-pii-policy.md)
for why full bodies never reach production logs.

## The five tools Gemini is given

Declared in `Settings.TOOL_DECLARATIONS` (`backend/config.py`), sent to Gemini at
session setup (`live_ai_gemini.py` "Sending tool declarations"):

| Tool | Purpose | Required args |
|------|---------|---------------|
| `update_form_fields` | Save ONE field's value | `field_id`, `value` |
| `confirm_field` | Mark a filled field confirmed after the user verifies | `field_id`, `confirmation_method` |
| `get_form_status` | Read which fields are filled | `field_ids` |
| `get_field_value` | Look up one field by spoken name | `spoken_name` |
| `switch_section` | Navigate to another section | `section_identifier` |

## Inbound: how a tool call reaches the backend

Gemini emits a tool call one of two ways; the adapter handles BOTH:

1. **`server_content.model_turn.parts[].function_call`** (primary path) --
   `live_ai_gemini.py`, the `for part in parts:` loop. dev-log: `tool_call` with
   `path="model_turn.parts"`.
2. **`event.tool_call.function_calls`** (alternate path) -- the
   `if getattr(event, "tool_call", ...)` block. dev-log: `tool_call` with
   `path="event.tool_call"`.

Both parse `function_call.arguments` (JSON string or dict) into
`parsed_arguments`, then invoke the registered callback
`CallbackHandler.on_tool_call(tool_name, arguments)`
(`backend/services/callback_handler.py`). The callback's return value becomes the
**tool response** sent back to Gemini.

**Response invariant (every call gets a response).** Gemini Live BLOCKS until
each function call it issues receives a `FunctionResponse`; an unanswered call
hangs the session -- including the very first tool-call/response loop. Both
receive paths therefore append a response for any named call: gated on
`tool_name` only (the `id` is included when present, omitted otherwise -- the SDK
matches responses to calls by order), and a callback that returns `None` or
*raises* still produces an empty `{}` ack rather than no response
(bd polyglot-pdf-tks). The one tool that can still orphan its response is
`switch_section`, because its handler tears down the receive task before the
response is flushed -- tracked separately in `polyglot-pdf-y4a`.

**Failure points visible in the dev log:**
- An **empty** `parsed_arguments` after parsing -> `invalid_tool_call` (the model
  emitted the call name but no/blank args). Hypothesis: tool-def/example mismatch.
- A tool call canceled by **barge-in** -> `interrupted` with
  `canceled_tool_names` listing e.g. `update_form_fields`. Hypothesis: the user
  spoke over the call before it completed.
- No `tool_call` entry at all for a turn where the user gave a value -> Gemini
  never emitted the call. Hypothesis: model not following the system instruction.

## `update_form_fields` round-trip (code expectation)

1. Gemini -> `update_form_fields(field_id, value)`.
2. `on_tool_call` routes to `_handle_update_form_fields_tool`
   (`callback_handler.py`): normalizes, validates, applies; then calls
   `send_form_update(...)` which emits a **`form_updated`** WS message to the
   frontend (value lands as `confirmed:false`).
3. The callback returns a tool response (applied/unknown/validation result). The
   adapter sends it back via `send_tool_response`. dev-log: `tool_callback_result`
   (the body the callback produced) then `tool_response` (the body actually sent
   on the wire).
4. Gemini reads it back to the user and asks "Is that correct?"

**Note:** `update_form_fields` deliberately does NOT fetch the next-field hint
(that is deferred to `confirm_field`) to save a round-trip.

## `confirm_field` round-trip (code expectation)

1. Gemini -> `confirm_field(field_id, confirmation_method)`.
2. `_handle_confirm_field_tool`: emits a **`confirm_field`** WS message to the
   frontend, then **blocks up to 2s** on `request_next_field_hint()`
   (`request_coordinator.py`), which asks the FRONTEND for the next field
   (`get_next_field_hint` -> `next_field_hint_response`).
3. The tool response returns `{success, field_confirmed, next_field_hint,
   message}`. `request_next_field_hint()` returns one of three things, and the
   tool response distinguishes all three (bd polyglot-pdf-tks):
   - a **hint string** -> there is a next field; `message` is just
     "Field confirmed."
   - **`None`** -> the frontend answered and the form is genuinely complete;
     `message` says "All fields confirmed."
   - **`HINT_REQUEST_TIMEOUT`** (the coordinator sentinel) -> the frontend did
     NOT answer within 2s. `next_field_hint` is sent as `None` (the sentinel
     never reaches the wire) but `message` explicitly tells Gemini NOT to assume
     completion and to ask for the next field / call `get_form_status`.
     Previously a timeout collapsed to `None` and read as "All fields confirmed",
     letting a slow round-trip make Gemini wrap the form up early.
   dev-log: `tool_callback_result` shows the exact response, including whether
   `next_field_hint` was null.

**Frontend loop-breaker (bd polyglot-pdf-0y7).** A `confirm_field` for a field
with no value is a no-op (`SchemaFormStateManager.confirmField` can't confirm what
isn't filled), so `computeNextField` keeps returning the SAME field and the
backend can re-request `confirm_field` for it indefinitely while Gemini stalls.
`webFormConnection.handleConfirmFieldRequest` guards this: it checks whether the
field actually became confirmed and, after 2 consecutive failed confirms of the
same field, breaks the spin. It surfaces the stall via `onError` (works today) and
also attempts a level-1 `recovery_prompt` -- the latter is currently inert because
`RECOVERY_PROMPT_LEVEL_*` are missing from `Settings` (`polyglot-pdf-zy3`) and
becomes the spoken Gemini re-prompt once that is fixed. The streak resets on a
successful confirm, a different field, or a section switch. The no-op also logs a
console warning so the stall is diagnosable.

## Wire reality vs. expectation -- what to check

When reading a captured session, line the dev-log `seq` order up against this map:

- Did a `tool_call` for `update_form_fields` appear at all after the user spoke?
- Were its `parsed_arguments` well-formed (`field_id` + `value`), or empty?
- Did `tool_response` carry a validation error (hypothesis: validation block) or
  a clean apply?
- For `confirm_field`, did `next_field_hint` come back non-null within 2s?
- Did an `interrupted` entry cancel a form-fill call?

The active `model` is stamped on every entry, so a 3.1-vs-2.5 A/B
(`USE_PREMIUM_MODEL`, see [config dev-feature block](../../backend/config.py))
shows side by side which model emits the calls reliably.
