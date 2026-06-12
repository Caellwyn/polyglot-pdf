# WebSocket routing

**Tracks:** backend/routes/websocket_routes.py frontend/src/shared/connection.ts frontend/src/webFormConnection.ts

*Last updated: 2026-06-12 (removed dead `request_next_field_hint` branch from handleFormUpdated, bd dlbr; GoAway forward message, bd c5t). See [../journal/entries/2026-06-12-bd-c5t-goaway-handling.md](../journal/entries/2026-06-12-bd-c5t-goaway-handling.md) for the GoAway path, [../journal/entries/2026-06-09-bd-aun-section-switch-durability.md](../journal/entries/2026-06-09-bd-aun-section-switch-durability.md) for the client-side switch-durability guards (re-entrancy + watchdog + error surfacing), [../journal/entries/2026-06-08-bd-g8w-voice-form-fill-e2e-harness.md](../journal/entries/2026-06-08-bd-g8w-voice-form-fill-e2e-harness.md) for the `connection.ts` dev test-injection hook, and [journal/entries/2026-06-04-bd-333-native-vad-smoke-test.md](../journal/entries/2026-06-04-bd-333-native-vad-smoke-test.md) for the session_ready native_vad field.*

The `/ws/fill` endpoint is the spine of the voice form-filler: one WebSocket
carries the handshake, audio frames, and a JSON control channel between the browser
and the backend. This doc covers the protocol; the Gemini adapter behind it is in
[voice-ai.md](voice-ai.md), the stateless contract in
[../standards/stateless-architecture.md](../standards/stateless-architecture.md),
and turn-taking in [../standards/voice-and-vad.md](../standards/voice-and-vad.md).

## Endpoints

`backend/routes/websocket_routes.py` defines three WS routes under `/ws`:

| Route | Purpose |
|-------|---------|
| `/ws/fill` | **The real endpoint.** Auth'd, schema-driven voice form fill. |
| `/ws/echo` | Test/diagnostic. Uses an explicit `hello` → `hello_ack` handshake — this is the ONLY endpoint with that exchange; do not confuse it with `/ws/fill`. |
| `/ws/audio` | Test/diagnostic raw-audio framing (`AFRM` header) probe. |

## /ws/fill handshake

1. Connect with `?token=<auth>` (and optional `?send_transcript=`). The token is
   verified (`verify_token`) **before** `accept()`; failure closes with `1008`.
2. The client's **first frame is the handshake itself** — a single JSON text frame
   (`receive_text()` → `json.loads`). There is no `hello`/`hello_ack` here.
3. `type` selects the mode:
   - `"handshake"` (legacy) — carries the full `schema`.
   - `"handshake_jit"` — carries a `manifest` + `first_field_schema` +
     `loaded_field_ids` for token-lean loading; the backend builds a minimal schema
     from the manifest. The mode is selected by the handshake `type` and accepted
     **unconditionally** — `USE_JIT_SCHEMA` does **not** gate it; that flag is only
     *reported back* in `session_ready.jit_mode_enabled`.
4. The handshake also carries `current_values` (pre-filled answers, used on
   reconnect — **not stored**, see stateless-architecture), `fill_language`, the
   persistent `form_session_id`, section metadata (`section_id`/`section_number`/
   `section_label`, `total_sections`, `previous_spoken_names`),
   `initial_field_hint`, and `resume` (bd polyglot-pdf-vmxx: `true` on any
   reconnect after the connection's first successful open — the backend then
   sends the RESUME initiating message and appends a no-greeting override to the
   system instruction, so a mid-section reconnect does not re-greet or
   re-introduce the section). The legacy payload now also carries
   `type: "handshake"` explicitly (bd wq9y) — the backend always defaulted a
   missing `type` to that, so the wire routing is unchanged.
5. Backend replies `{"type": "session_ready", "session_id": "web_…", "ephemeral":
   true, "jit_mode_enabled": <bool>, "native_vad": <bool>}`. The `session_id` is an
   ephemeral per-connection id for log correlation only — it is **not** the
   `form_session_id`. `native_vad` (= `not DISABLE_GEMINI_VAD`) tells the frontend
   whether Gemini's own VAD is driving turns, so it can suppress manual activity
   signals and stream continuous audio (bd polyglot-pdf-333; see voice-and-vad).

Malformed handshakes close with specific codes: non-text first frame → `1003`;
bad JSON / not-an-object / missing schema → `1007`; bad `source` → `1008`.

## Control-channel message types (client → backend)

After the handshake, the loop in `_handle_fill_session` dispatches binary frames as
audio (`service.stream_audio`) and JSON text frames by `type`:

| `type` | Effect |
|--------|--------|
| `ping` | → `pong` |
| `form_state` | apply client field list → `form_state_ack` (backend echoes applied ids only; client owns state) |
| `next_field_hint` | forward a hint to Gemini → `hint_ack` |
| `form_state_response` / `field_value_response` / `next_field_hint_response` / `section_info_response` / `confirm_field_response` | resolve a pending backend→frontend async request (`confirm_field_response` carries `{recorded, reason}` for the synchronous confirm round-trip, bd polyglot-pdf-wpw.2) |
| `manual_field_update` | user manually edited a field → forwarded to Gemini (keeps context in sync) |
| `read_disclaimer` | send disclaimer initiating message in a language → `disclaimer_read_initiated` |
| `completion_message` | send a prompt that should make Gemini speak → `completion_ack` |
| `recovery_prompt` | level 1/2/3 stall-recovery prompt → `recovery_prompt_ack` |
| `vad_activity_start` / `vad_activity_end` | relay manual VAD signals (see voice-and-vad) |
| `change_fill_language` | → `language_changed` |
| `change_spoken_language` | send initiating message in new spoken language → `spoken_language_changed` |
| `end_gemini_session` | close Gemini only, keep WS alive → `gemini_session_ended` |
| `restart_gemini_session` | restart Gemini with existing schema/values → `gemini_session_restarted` |
| `manual_section_switch` | user switched section in the UI → backend restarts Gemini, then emits `section_switched` (see below) |
| `section_completed` | **legacy/backend-only** — handler exists (→ `section_completed_ack`) but no client currently sends it; completion is driven via `manual_section_switch` / `onFormComplete` (see below) |

Unknown types → `{"type":"error","code":"unknown_control"}` (logged).

## Section-switch flow

There is **no backend `complete_section` tool** — the **frontend drives** section
progression. When the user switches sections, the frontend sends
`manual_section_switch` with the section's schema/values/metadata *embedded* (no
round-trip). The handler sets `drop_audio = True` (discards incoming audio frames
during the switch to avoid backlog), calls the service method
`switch_to_section(...)` — which restarts the Gemini session with the new section's
system instruction — then resets `drop_audio = False` (also on error). On success
the backend emits **`{"type": "section_switched", "section_number": ...,
"total_sections": ..., "section_label": ...}`** to the client (no `section_id`
key); the client-facing message name is `section_switched`, *not*
`switch_to_section` (that's the internal service method). There is no synchronous
ack to the `manual_section_switch` message itself. Section completion is
frontend-driven: when it detects every field in the current section confirmed it
auto-sends `manual_section_switch` to advance, or fires `onFormComplete` on the
last section — it does **not** send `section_completed` (that type has a backend
handler but no current client sender).

**Client-side switch durability** (`webFormConnection.ts`, bd polyglot-pdf-aun):
a switch is gated by a `switchInFlight` re-entrancy guard (distinct from the
`isSectionSwitching` auto-reconnect suppressor), so a second switch — a manual
click during an AI-initiated switch, which the backend also rejects with
`{"type":"error","code":"section_switch_failed"}` post-`0c1` — is dropped rather
than racing a second reconnect. A switch that fails (a server `error`, an
unexpected mid-switch socket close, or a hang caught by a ~15s watchdog) settles
the connection status to **`error`** and fires `onError`, instead of leaving the
UI stuck on `switching_section`; `section_switched` releases the guard and
settles to `connected`.

## Idle watchdog

`_handle_fill_session` runs a watchdog that checks every 5s; after
`WS_IDLE_TIMEOUT_SEC` (config.py) of no received frame it sends
`{"type":"idle_timeout", ...}`, waits 0.5s, then closes with code `1000`. The
frontend uses that message to stop auto-reconnecting and show a Reconnect button.
(`/ws/echo` and `/ws/audio` use a simpler 1s-interval watchdog closing with
`1001`.)

## Reconnect (no page refresh)

Reconnect logic lives in `frontend/src/shared/connection.ts`. Key points verified
against the code:

- The connection manager keeps a single `paused` boolean (exposed as `isPaused()`).
  A documented **bug fix (Nov 10, 2025)** resets `paused = false` on connect, on
  error, on disconnect, and on any non-`connected`/`switching_section` status
  change — without it, after an idle timeout `isPaused()` stayed true and the app
  tried to `resume()` a dead socket instead of `connect()`.
- **Warm path:** if the WebSocket is still connected but Gemini was closed (post-
  Level-3), `connect()` sends `restart_gemini_session` with a freshly computed
  `next_field_hint` rather than a full reconnect.
- **Cold path:** otherwise it dials `wsUrl`, falling back to the cloud URL on
  failure, re-creating the audio + field managers if they were destroyed.

> **Doc-vs-code note:** `RECONNECTION_FLOW_SUMMARY.md` (repo root) is a *design
> proposal* for auto-sending an initiating message on reconnect, not a description
> of shipped behavior — treat it as historical. This doc describes the code as it
> actually runs.
