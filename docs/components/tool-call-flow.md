# Tool-call flow (Gemini Live <-> backend <-> frontend)

**Tracks:** backend/adapters/live_ai_gemini.py backend/services/callback_handler.py backend/services/request_coordinator.py backend/config.py

*Last updated: 2026-07-09 (bd polyglot-pdf-7yra: added the seventh tool
`skip_field` to the tool table + count -- a voice skip of a required field the
user cannot answer, distinct from N/A; it mirrors confirm_field's round-trip).
Prior: 2026-07-05 (bd polyglot-pdf-mpoe staleness sweep: added the sixth
tool `ask_secretary` to the tool table and tool count; the rest of the
confirm/update round-trip descriptions verified accurate against current code).
See [../journal/entries/2026-07-05-bd-mpoe-doc-staleness-sweep.md](../journal/entries/2026-07-05-bd-mpoe-doc-staleness-sweep.md).*

Map of what the CODE expects for each Gemini tool call vs. what is actually on
the wire, plus the dev-log `message_type`s that capture each hop. Use this as the
key for reading a captured `backend/logs/gemini_<date>.jsonl` when debugging tool
reliability (e.g. "why didn't `update_form_fields` land?"). The dev capture is
local-only (`.env.DEV`-gated) -- see [voice-ai.md](voice-ai.md) for the adapter
overview and [../standards/hipaa-pii-policy.md](../standards/hipaa-pii-policy.md)
for why full bodies never reach production logs.

## The tools Gemini is given

Declared in `Settings.TOOL_DECLARATIONS` (`backend/config.py`), sent to Gemini at
session setup (`live_ai_gemini.py` "Sending tool declarations"). `get_field_value`
was retired (bd polyglot-pdf-p5h2, epic polyglot-pdf-fc7t): in continuous mode
(the only production path) recall is `ask_secretary`'s job:

| Tool | Purpose | Required args |
|------|---------|---------------|
| `update_form_fields` | Save ONE field's value | `field_id`, `value` |
| `confirm_field` | Mark a filled field confirmed after the user verifies | `field_id`, `confirmation_method` |
| `get_form_status` | Read which fields are filled | `field_ids` |
| `switch_section` | Navigate to another section | `section_identifier` |
| `ask_secretary` | Ask a cheap text-model helper a plain-language question about a past answer or another field (bd polyglot-pdf-jnjj.45) | `query` |
| `skip_field` | Force-skip a required field the user cannot answer, distinct from N/A (bd polyglot-pdf-7yra) | `field_id` |

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
receive paths therefore append a response for any named call (gated on
`tool_name` only), and a callback that returns `None` or *raises* still produces
an empty `{}` ack rather than no response (bd polyglot-pdf-tks). Both paths append
to the SAME per-event `responses` list, which is flushed once; just before the
flush it is deduped by call id (`_dedupe_responses_by_id`, bd polyglot-pdf-ux15) so
a single event that carried the same call on BOTH shapes can never send Gemini two
`FunctionResponse`s for one id. This is defensive: live evidence shows the two
shapes do NOT co-occur, so it is a no-op today and logs a PII-free
`duplicate_tool_response_dropped` (dropped count + the dropped Gemini call ids, which
are model-generated tokens not field values; never the response body) if it ever fires. Every response
**echoes the call's `id`** back (`_build_function_response`): the SDK's AI-Studio
(`VERTEXAI=false`) path REQUIRES the id and crashes the receive loop without it
(bd polyglot-pdf-0ux) -- the model does send one (it is NOT matched by order); the
id is omitted only for a rare genuinely-id-less call (the Vertex path tolerates
that). **`switch_section` delivers its response on the OLD session before
teardown** (bd polyglot-pdf-0c1, which closed y4a): its handler returns the
success payload immediately -- that return value is the `FunctionResponse` the
receive loop flushes via `send_tool_response` -- and only THEN does the loop break
on a cooperative `_close_after_flush` flag. The actual session swap runs on a
detached task that awaits the old loop's `_closed_event` before restarting, so the
response is never orphaned by a self-cancel and no two receive loops ever share
callbacks.

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

**Client-side validation gate (bd polyglot-pdf-wpw.3 / WS-E3).** The frontend
re-validates every AI-applied value in `webFormConnection.handleFieldUpdate` /
`handleFormUpdated` via `validateField` (enum / format / required) *before* it
lands -- the client owns all field state, so an invalid value must never be
stored. A reject SKIPS the apply and routes a corrective `completion_message` back
to the model (the proven in-band channel -- `dependency_error` is not consumed by
the backend) so the model re-asks the user. The prompt carries only the field's
spoken name + the schema constraint, NEVER the rejected value (PII-safe). Those
prompts are rate-limited per field and capped, mirroring the `confirm_field`
loop-breaker below, so a value the model cannot get right does not spin the
session. This is a second, client-authoritative layer in addition to the backend
`validates` step in step 2 above.

## `confirm_field` round-trip (code expectation)

1. Gemini -> `confirm_field(field_id, confirmation_method)`.
2. `_handle_confirm_field_tool` makes confirm a **synchronous round-trip** (bd
   polyglot-pdf-wpw.2 / WS-E2): it calls `request_confirm_field()`
   (`request_coordinator.py`), which sends a `confirm_field` WS message carrying a
   `request_id` and **blocks up to 2s** for the frontend's
   `confirm_field_response`. The frontend owns all field state, so it -- not the
   backend -- is the source of truth for whether the confirm was actually
   recorded. The ack is `{recorded: bool, reason}` (or the
   `CONFIRM_REQUEST_TIMEOUT` sentinel on no answer). Only on a **recorded** ack
   does the handler then request the next-field hint and log the confirmation.
3. The tool response depends on the ack:
   - **recorded** -> `{success: true, field_confirmed, next_field_hint, message}`.
     `request_next_field_hint()` then returns one of three things (bd
     polyglot-pdf-tks), and the message distinguishes all three: a **hint string**
     ("Field confirmed."), **`None`** (form genuinely complete -- "All fields
     confirmed."), or **`HINT_REQUEST_TIMEOUT`** (frontend did not answer in 2s --
     `next_field_hint` goes out as `None` but the message tells Gemini NOT to
     assume completion and to ask for the next field / call `get_form_status`).
     **Section-boundary short-circuit (bd polyglot-pdf-njvh):** if the ack carries
     `section_complete: true` (the confirm completed a section that has a NEXT
     section), the handler SKIPS `request_next_field_hint()` entirely -- that
     request would race the FE's `switchToSection` socket teardown and time out,
     spuriously emitting the "do NOT assume complete" message at the exact moment
     the section is correctly auto-advancing. Instead it returns a clean
     "section advancing" message (`next_field_hint: None`, no timeout text) and logs
     `confirm_section_boundary_skip_hint`. The new section's first-field hint
     arrives via the section-switch flow.
   - **not recorded** (the field has no value -- `reason: "no_value"`) or the
     confirm-ack **timed out** -> `{success: false, ...}` carrying the WS-C2
     error-envelope keys (`status:"error"`, `retryable`, `error`) plus a corrective
     `message`, and the next-field hint is NOT requested (no advance). So 3.1's
     confirm-without-fill skip self-corrects IN-BAND: Gemini reads an actual
     failure and re-asks, instead of the old fire-and-forget that always read as
     success and silently lost the value.
   dev-log: `tool_callback_result` shows the exact response, including
   `success`/`status` and whether `next_field_hint` was null.

**Frontend loop-breaker (bd polyglot-pdf-0y7) + in-band ack (wpw.2).** A
`confirm_field` for a field with no value is a no-op
(`SchemaFormStateManager.confirmField` can't confirm what isn't filled), so
`computeNextField` keeps returning the SAME field.
`webFormConnection.handleConfirmFieldRequest` gates on the field VALUE: when there
is no usable value it sends `confirm_field_response {recorded:false,
reason:"no_value"}` (the in-band signal the backend turns into `success:false`),
AND -- as a client-side belt-and-suspenders -- after 2 consecutive failed confirms
of the same field it re-prompts Gemini via `completion_message` (capped) and
surfaces the stall via `onError`. On a usable value it records the confirm and
sends `{recorded:true}`. The streak resets on a successful confirm, a different
field, or a section switch. `reason` is a fixed category token, never the field
value (PII-safe). (The legacy fire-and-forget shape -- a `confirm_field` with no
`request_id` -- still no-ops the ack for backward compatibility.)

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
