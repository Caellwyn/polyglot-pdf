# WebSocket routing

**Tracks:** backend/routes/websocket_routes.py frontend/src/shared/connection.ts frontend/src/webFormConnection.ts

*Last updated: 2026-07-05 (bd polyglot-pdf-mpoe staleness sweep: folded the `confirm_field_response.section_complete` sub-flag (bd njvh) into the control-channel table; verified accurate against current code otherwise). See [../journal/entries/2026-07-05-bd-mpoe-doc-staleness-sweep.md](../journal/entries/2026-07-05-bd-mpoe-doc-staleness-sweep.md).*

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
| `/ws/fill` | **The real endpoint.** Auth'd, schema-driven voice form fill. Never gated. |
| `/ws/echo` | Test/diagnostic. **Dev-only**: rejects the handshake (close 1008 pre-accept) unless the `backend/.env.DEV` marker exists (bd polyglot-pdf-puu8). Uses an explicit `hello` → `hello_ack` handshake — this is the ONLY endpoint with that exchange; do not confuse it with `/ws/fill`. |
| `/ws/audio` | Test/diagnostic raw-audio framing (`AFRM` header) probe. **Dev-only**, same `.env.DEV` gate as `/ws/echo`. |

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

**DTI current-field guidance rides the initiating message (`USE_DTI` only).** In
DTI mode the system instruction is fully static and carries no field data, so the
current field's full guidance (its exact `field_id`, instructions, format, options)
must reach Gemini via the **initiating message** (`send_initiating_message`) —
fields 2..N otherwise arrive in the `confirm_field` tool response (epic
polyglot-pdf-13w7, bd polyglot-pdf-j748). The opener is **client-driven**, not a
server-side trigger in the handshake path: after the disclaimer the client
re-handshakes (`switchToFirstSection` → `startSection`) and `handleSessionReady`
auto-sends `change_spoken_language` with the user's spoken language + the
`computeNextField`-selected hint, which calls `send_initiating_message`. That method
resolves the field to render from the `field_id` embedded in the hint (looked up in
the handshake schema + the recorded later-field schemas), NOT from a positional
`fields[0]`, so it stays correct on a mid-form spoken-language change (field N) and
on a full-section handshake (where `fields[0]` is not the next field). If the hint
resolves to no known field, no guidance block is sent (the spoken hint + static SI
still let the model proceed). A server-side trigger was deliberately NOT added: it
would fire before the disclaimer is read on the initial connect and double up with
the client opener on reconnect (Codex PR #254). Legacy/JIT carry the field catalog
in the SI, so their initiating message has no guidance block (DTI-gated).

## Control-channel message types (client → backend)

After the handshake, the loop in `_handle_fill_session` dispatches binary frames as
audio (`service.stream_audio`) and JSON text frames by `type`:

| `type` | Effect |
|--------|--------|
| `ping` | → `pong` |
| `form_state` | apply client field list → `form_state_ack` (backend echoes applied ids only; client owns state) |
| `next_field_hint` | forward a hint to Gemini → `hint_ack` |
| `form_state_response` / `field_value_response` / `next_field_hint_response` / `section_info_response` / `confirm_field_response` | resolve a pending backend→frontend async request (`confirm_field_response` carries `{recorded, reason}` for the synchronous confirm round-trip, bd polyglot-pdf-wpw.2, plus an optional `section_complete` flag the WS route reads and threads to the confirm handler so it skips the racing next-field-hint at a section boundary, bd njvh -- see ws-protocol.md for the field) |
| `manual_field_update` | user manually edited a field → forwarded to Gemini (keeps context in sync); in DTI mode an optional `next_field_schema` rider re-establishes the current-field pointer + validation entry via `merge_field_schema` (bd polyglot-pdf-ezg2) |
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
| `section_complete` | **proactive boundary event** (Pillar B, bd polyglot-pdf-jnjj.16) — sent when the last field of the current section is confirmed (a next section exists); carries `section_id` + the contract-2 field payload. Since B5 (jnjj.17) the arm runs the validator (`service.handle_validation_boundary`), pushes a `validation_result` (below), then acks `section_complete_ack`. Distinct from the legacy `section_completed` above. |
| `form_complete` | **proactive boundary event** (Pillar B, bd polyglot-pdf-jnjj.16) — sent once when the whole form is confirmed (re-emitted after a post-completion edit; client-side dirty guard); carries the whole-form contract-2 payload. Since B5: runs the full-form validator pass, pushes `validation_result`, then acks `form_complete_ack`. |

Unknown types → `{"type":"error","code":"unknown_control"}` (logged).

**Validator results (backend → client, Pillar B / bd polyglot-pdf-jnjj.17):** after
each `section_complete` / `form_complete`, the backend pushes a
**`validation_result`** (`{type, conflicts}`; clean = `conflicts:[]`) for EVERY
boundary — the client's deterministic clean→resume signal for the gated section
switch. On a conflict the client marks the named fields `steered` (sessionStorage,
so the next payload carries it for the max-resteer bound) and **holds** in-section;
the correction is voiced by the live model, which the backend steers via a
Gemini Live text turn (NOT a client message). The section auto-switch is now
**gated** on this result: clean → switch proceeds; conflict → switch held; no result
within the fail-open window → switch proceeds unchecked.

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
last section — it does **not** send the legacy `section_completed` (that type has a
backend handler but no current client sender). It DOES, since bd
polyglot-pdf-jnjj.16, additionally emit the proactive `section_complete` /
`form_complete` boundary events (above) at those same moments, to feed the
cheap-model validator (Pillar B); those are fire-and-forget and do not gate the
switch in B4.

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
`WS_IDLE_TIMEOUT_SEC` (config.py) of no **meaningful activity** it sends
`{"type":"idle_timeout", ...}`, waits 0.5s, then closes with code `1000`. The
frontend uses that message to stop auto-reconnecting and show a Reconnect button.
(`/ws/echo` and `/ws/audio` use a simpler 1s-interval watchdog closing with
`1001`.)

**"Meaningful activity" excludes raw inbound audio frames (bd polyglot-pdf-l3a.4).**
In native VAD mode the client streams continuous audio incl. silence, so counting
audio bytes as activity made the timeout un-fireable when a user walked away with
the mic open (the session then burned Gemini's 15-min audio cap at ~$0.0045/min).
The idle clock now resets only on: (a) a real user turn -- the adapter's
`on_user_activity` callback, fired when Gemini's native VAD produces an
`input_transcription` (background noise/silence do NOT produce one); and (b)
non-audio control/text messages (ping, form_state, hint). Gemini's OUTPUT audio
(model speaking) does not count. Server-side only; no client-side VAD, no new
per-session server state.

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

## Terminal reconnect failure (connection-timeout modal)

An unexpected drop triggers silent auto-reconnect with exponential backoff (up to
`maxReconnectAttempts` in `webFormConnection.ts`). When every attempt is exhausted,
`handleClose` sets the distinct **`reconnect_failed`** `ConnectionStatus` (separate
from the generic `disconnected`, which also covers intentional teardown) — the
explicit "auto-recovery gave up, the user must act" signal. Both voice overlays
render a translated **connection-timeout modal** (`ConnectionTimeoutModal`) on that
status; its reconnect button re-runs the same `handleConnect`/restore path, and a
"not now" dismissal is reset once the connection leaves `reconnect_failed`. A
transient blip that still has attempts left stays on `reconnecting` and never
surfaces the modal. (bd polyglot-pdf-jf6w.)

> **Doc-vs-code note:** `RECONNECTION_FLOW_SUMMARY.md` (repo root) is a *design
> proposal* for auto-sending an initiating message on reconnect, not a description
> of shipped behavior — treat it as historical. This doc describes the code as it
> actually runs.
