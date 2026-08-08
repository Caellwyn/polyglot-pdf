# WebSocket routing

**Tracks:** backend/routes/websocket_routes.py frontend/src/shared/connection.ts frontend/src/webFormConnection.ts

*Last updated: 2026-08-07 (bd polyglot-pdf-22h1f: added the `spellback_response`
row to the control-channel table -- the flag-gated deterministic spell-back
round-trip.)*

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
   - `"handshake_jit"` — the manifest-first TRANSPORT: carries a `manifest` +
     `first_field_schema` + `loaded_field_ids`; the backend builds a minimal schema
     from the manifest. This is DTI's carrier (the JIT SI mode was removed, bd
     polyglot-pdf-en2j). The mode is selected by the handshake `type` and accepted
     **unconditionally** — no backend flag gates acceptance; the backend only
     *reports back* whether to build it via `session_ready.jit_mode_enabled`
     (`= settings.USE_DTI`).
4. The handshake also carries `current_values` (pre-filled answers, used on
   reconnect — **not stored**, see stateless-architecture), `fill_language`, the
   persistent `form_session_id`, section metadata (`section_id`/`section_number`/
   `section_label`, `total_sections`, `previous_spoken_names`),
   `initial_field_hint`, and `resume` (`true` on any reconnect after the
   connection's first successful open (bd polyglot-pdf-vmxx), AND on the FIRST
   handshake after a soft page refresh when the persisted state shows an
   in-progress session — disclaimer accepted plus at least one filled field
   (bd polyglot-pdf-hc4b), since a post-reload `WebFormConnection` has a fresh
   instance-scoped once-flag and would otherwise send `resume:false` mid-form.
   The backend then sends the RESUME initiating message and appends a no-greeting
   override to the system instruction, so a resumed session does not re-greet or
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
`fields[0]`, so it stays correct on a mid-form RECONNECT (field N, not field 1) and
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
| `stats` | → `{"type":"stats","message":"ok"}` (fixed ack, no payload read) |
| `form_state` | apply client field list → `form_state_ack` (backend echoes applied ids only; client owns state) |
| `next_field_hint` | forward a hint to Gemini → `hint_ack` |
| `form_state_response` / `next_field_hint_response` / `section_info_response` / `confirm_field_response` | resolve a pending backend→frontend async request (`confirm_field_response` carries `{recorded, reason}` for the synchronous confirm round-trip, bd polyglot-pdf-wpw.2, plus an optional `section_complete` flag the WS route reads and threads to the confirm handler so it skips the racing next-field-hint at a section boundary, bd njvh -- see ws-protocol.md for the field) |
| `skip_field_response` | resolves a pending `skip_field` request the same way `confirm_field_response` resolves `confirm_field` (`markFieldSkipped`, bd polyglot-pdf-7yra) -- same `{recorded, reason, section_complete}` shape, so a section-completing skip advances too |
| `switch_field_response` | resolves a pending field-level navigation request (`switch_field`, bd polyglot-pdf-jnjj.36) -- the whole payload minus `type`/`request_id` (found + outcome keys: field_id/hint/schema on success, a fixed reason token on failure) rides to the coordinator; values are never logged |
| `spellback_response` | resolves a pending `spellback` request (the flag-gated `name_spellback` tool, bd polyglot-pdf-22h1f) -- the payload minus `type`/`request_id` (`status` delivered/interrupted/error + optional fixed `reason` token and `playback_ms`/`fetch_ms` timings) rides to the coordinator; never carries a field value. The request side is the ONE round-trip that deliberately holds the tool response for the client's blocking clip playback (90s cap) -- see ws-protocol.md |
| `manual_field_update` | user manually edited a field → forwarded to Gemini (keeps context in sync); in DTI mode an optional `next_field_schema` rider re-establishes the current-field pointer + validation entry via `merge_field_schema` (bd polyglot-pdf-ezg2) |
| `read_disclaimer` | send disclaimer initiating message in a language → `disclaimer_read_initiated` |
| `completion_message` | send a prompt that should make Gemini speak → `completion_ack` |
| `recovery_prompt` | level 1/2/3 stall-recovery prompt → `recovery_prompt_ack` |
| `vad_activity_start` / `vad_activity_end` | relay manual VAD signals (see voice-and-vad) |
| `clear_thinking` | client's thinking-indicator max-duration safety timer fired (bd polyglot-pdf-wpw.5) -- fire-and-forget, resets the backend's processing state so it doesn't stay stuck `true` and dedup the next turn's `processing:true` |
| `change_fill_language` | → `language_changed` |
| `change_spoken_language` | MISNOMER (bd polyglot-pdf-87a9) -- the language is PINNED per session; this re-asserts the SAME language on a fresh Gemini session after a teardown: send initiating message → `spoken_language_changed` |
| `end_gemini_session` | close Gemini only, keep WS alive → `gemini_session_ended` |
| `restart_gemini_session` | restart Gemini with existing schema/values → `gemini_session_restarted` |
| `manual_section_switch` | user switched section in the UI → backend restarts Gemini, then emits `section_switched` (see below) |
| `section_completed` | **legacy/backend-only** — handler exists (→ `section_completed_ack`) but no client currently sends it; completion is driven via `manual_section_switch` / `onFormComplete` (see below) |
| `section_complete` | **proactive boundary event** (Pillar B, bd polyglot-pdf-jnjj.16) — sent when the last field of the current section is confirmed (a next section exists); carries `section_id` + the contract-2 field payload. Since W1 (bd polyglot-pdf-xbl2) the arm acks `section_complete_ack` IMMEDIATELY and spins the validator into a background task off the receive loop (a one-window batch), which pushes `validation_result` (below) when it lands. Distinct from the legacy `section_completed` above. |
| `form_complete` | **proactive boundary event** (Pillar B, bd polyglot-pdf-jnjj.16) — sent once when the whole form is confirmed (re-emitted after a post-completion edit; client-side dirty guard); carries the whole-form contract-2 payload. Since W1: acks `form_complete_ack` immediately + runs the full-form pass in the background, which pushes `validation_result`. |
| `validate_windows` | **async STRIDE validator trigger** (Pillar B / W2, bd polyglot-pdf-kxkw; backend arm W1/xbl2) — carries `windows`, a list of overlapping contract-2 field lists (size ~20, stride ~10 over SCHEMA FIELD ORDER). PAGE-AGNOSTIC (report-cadence revision 2026-07-13): the client (webFormConnection.maybeEmitValidateWindows) emits a window once every field it covers is SETTLED (confirmed/skipped/not-applicable), keyed on schema order + settled flags, never pdf_position.page — so a source:"web" / pageless form emits identically to a paginated one. Acks `validate_windows_ack` immediately, then runs every window's flash-lite pass concurrently off the receive loop, dedupes conflicts by field-id set, and pushes one `validation_result` (REPORT-ONLY since W3 — no steer injected). |
| `drain_findings` | **finding-driven drain** (Pillar B / W3, bd polyglot-pdf-pr3i) — the client (webFormConnection.drainFindings) sends this the moment its `validatorFindingsQueue` is non-empty (a report-only `validation_result` enqueued a conflict), and on reconnect if a queue survived. Carries `conflicts`, each `{field_ids, reason, field_names}`. Acks `drain_findings_ack` immediately, then composes ONE steer (the oiok composer) + injects it OFF the receive loop, and pushes `drain_findings_result` with the DELIVERED conflicts. |
| `client_diagnostic` | one-way, PII-free client diagnostic log (bd polyglot-pdf-xp4q) -- `event` is whitelisted to a fixed set of known tokens (anything else logs as `"invalid"`) so a raw client payload can never smuggle PII into the log line; no ack, fire-and-forget |

Unknown types → `{"type":"error","code":"unknown_control"}` (logged).

## Server-initiated messages (backend → client)

Besides replying to the client-sent types above, the backend also PUSHES a few
message types unprompted, forwarding Gemini/session lifecycle events the client
has no way to observe otherwise:

| `type` | When | Client effect |
|--------|------|----------------|
| `interrupted` | Gemini stops generating because the user barged in mid-response (`CallbackHandler.on_interrupted`, bd polyglot-pdf-s7uf). No payload -- the event itself is the signal. | `webFormConnection.ts` clears its staging `audioQueue` + `isProcessingAudio`, then fires `onInterrupted()`, which calls `audioManager.resetPlaybackClock()` to drop the dead generation's unplayed tail without setting `playbackBlocked` (so the model's next generation still plays). |
| `go_away` | The Gemini Live server is about to terminate the connection (`on_go_away`). | Surfaces `time_left` via `onGoAway`, then the client silently pre-emptively reconnects with `resume:true`. Distinct from the "Idle watchdog" below -- this is a Gemini-side lifecycle reset, not a client-inactivity close. |
| `gemini_session_dropped` | Gemini's session died spontaneously behind a still-open WS (e.g. a 1011 error) (`on_session_dropped`). | Same pre-emptive reconnect path as `go_away`, but surfaces a `reconnecting` status so the UI shows a transient-recovery modal. |
| `idle_timeout` | The idle watchdog fires (see below). | Client stops auto-reconnecting and shows a manual Reconnect button. |
| `section_switched` | A `manual_section_switch` completes (DEPRECATED section-reset fallback only -- see below). | Releases the switch guard, settles connection status to `connected`. |

**Validator results (backend → client, Pillar B / bd polyglot-pdf-jnjj.17;
async since W1 / bd polyglot-pdf-xbl2; REPORT-ONLY + finding-driven since W3 /
bd polyglot-pdf-pr3i):** for each `section_complete` / `form_complete` /
`validate_windows` boundary the backend pushes a **`validation_result`**
(`{type, conflicts}`; clean = `conflicts:[]`), acked FIRST and PUSHED
asynchronously AFTER the `*_ack` off the receive loop (a slow/hung validator adds
zero voice-turn latency). **W3 made this REPORT-ONLY:** the backend NO LONGER
injects a steer on the result. A conflict is a CANDIDATE the client ENQUEUES into
its `validatorFindingsQueue` (client-owned + persisted; each conflict carries a
`field_names` id→name rider) and then drains IMMEDIATELY via `drain_findings`
(above) — the drain composes + injects the steer and replies `drain_findings_result`
with the delivered conflicts, at which point the client marks those fields `steered`
(max-resteer bound) and CONSUMES them from the queue. A CLEAN result enqueues
nothing and drains nothing (no voice turn on an all-clear). An un-delivered steer
keeps the finding queued to retry. The DEPRECATED section-reset gate (below) still
resolves on an arriving clean result and fails open on the timeout.

## Section-switch flow (DEPRECATED section-reset fallback)

> **This whole flow is the DEPRECATED section-reset fallback** (bd
> polyglot-pdf-55jg; see [../standards/section-reset-deprecation.md](../standards/section-reset-deprecation.md)).
> In production continuous mode (`continuous_session_enabled=true` in the
> handshake ack -- see [../standards/ws-protocol.md](../standards/ws-protocol.md))
> the whole form runs as ONE session: the frontend builds a single whole-form
> handshake and STOPS advancing sections, so `manual_section_switch` / the
> `switch_section` tool / `section_switched` are never sent. The mechanics below
> apply only when the flags route to the fallback.

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

## Soft page refresh (reload rehydration)

A soft page refresh (F5/reload) during an active session is distinct from the
in-memory reconnect above: the whole SPA re-mounts, so the connection is rebuilt
from scratch and the UI step must be re-derived from persisted state. Two
invariants keep the resumed session consistent with the client (bd
polyglot-pdf-fn1m):

- **UI step restore.** Both voice overlays' mount auto-connect effect reconnects
  to resume the session, but the disclaimer/agree step is gated on the persisted
  `disclaimerAccepted` (in `schema_form_state`) — an already-accepted session
  reconnects **without** re-showing or re-reading the disclaimer, so the agree
  screen never re-appears while the agent is mid-section.
- **Fresh handshake state.** `webFormConnection.handleOpen` calls `reloadState()`
  (re-read `schema_form_state` into `this.state`) **before** building the
  handshake, so `current_values` + `section_id` reflect the client's actual
  current field state — not the constructor's `init()` snapshot, which on a
  refresh can predate the latest save (which would let the resumed backend assert
  a stale previous-section value).

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
