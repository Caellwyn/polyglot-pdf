# WebSocket protocol -- frozen handshake + message-type contract

**Tracks:** backend/routes/websocket_routes.py frontend/src/webFormConnection.ts frontend/src/schema-forms/state/schemaFormState.ts

*Last updated: 2026-09-03 (bd polyglot-pdf-5ovod: `switch_field_response`'s `has_value` and `already_confirmed` no longer report a whitespace-only field as holding an answer -- the backend's guidance keyed on them, so the model was told to read back a blank; the row's citation is re-anchored to the symbol. bd polyglot-pdf-wurj8: added the `voice_mode` / `voice_mode_ack` pair.)*

This is the FROZEN wire contract for the `/ws/fill` WebSocket: the handshake
schema the backend reads on every (re)connect, plus the `{"type": "..."}`
message-type union exchanged in both directions. It exists so the three epic
pillars -- **A** (SI-reduction), **B** (cheap-model validator), **C**
(restart-cadence) -- can each add handshake keys and message types to the same
wire WITHOUT colliding. Every new key/type below is tagged with its owning
pillar (A/B/C) and the bead that introduces it.

The backend is stateless by design: it rebuilds all context from this handshake
on every connect, and the client owns all field state. This doc owns the WIRE
shape; the SI template shape it feeds lives in
[si-reduction.md](si-reduction.md) (the manifest/placeholder contract), and the
validator message shapes (Pillar B) are designed in F3,
[validation-delegation.md](validation-delegation.md) (this doc RESERVES the wire
type names; F3 owns their payload shapes).

---

## Current state: the `/ws/fill` handshake

The first text frame on `/ws/fill` is a JSON object. The backend reads it in
`backend/routes/websocket_routes.py`'s `fill_form_from_schema` handler
(`handshake = json.loads(first_frame)` onward), which dispatches into
`_handle_fill_session`. It branches on `type` into two
handshake shapes -- the **legacy** full-section-schema handshake and the
**manifest-first transport** (`handshake_jit`: manifest + first field). The
`jit` name is historical; the manifest-first transport is DTI's carrier, not the
removed JIT SI mode (bd polyglot-pdf-en2j).

### Mode selector + shared keys

| Key | Type | Mode | Meaning |
|-----|------|------|---------|
| `type` | `"handshake"` \| `"handshake_jit"` | both | Selects the handshake shape. `handshake_jit` -> the manifest-first transport (DTI's carrier; the `is_jit_mode = handshake_type == "handshake_jit"` check). Anything else (incl. missing) -> the legacy full-schema handshake. |
| `form_session_id` | string | both | Persistent, frontend-managed ID; survives reconnects. Logging/metrics correlation only -- never used for server-side state (the `form_session_id = handshake.get(...)` read). |
| `current_values` | object (field_id -> FieldValue) | both | Pre-filled values for reconnect; defaults to `{}` (the `current_values` read, right after the legacy/JIT schema branch). |
| `full_schema` | object (`{source, fields, sections, parts, ...}`) \| absent | both | The WHOLE form schema (all parts/sections/fields), for the secretary catalog (bd polyglot-pdf-p68s / jnjj.45d). Distinct from `schema`/`manifest`, which carry only the CURRENT section. The backend caches it in-session in `FormFillingService._full_schema` and `handle_ask_secretary` renders the secretary's static catalog from it; preserved across same-form section switches. Schema only -- no PII; rebuilt from this on every (re)connect (stateless invariant). Optional: an older client that omits it makes the secretary fall back to the per-section `schema`. |
| `fill_language` | string | both | Language the AI fills/speaks in; defaults to `"English"` (the `fill_language` read, immediately after `current_values`). |
| `spoken_language` | string \| null | both | The user's app-start SPOKEN-language choice (bd polyglot-pdf-y25o). Read at handshake time -- BEFORE the Gemini connect -- to derive the per-connect ASR transcription `language_codes` bias (the later `change_spoken_language` control message arrives too late for per-connect config). Null/omitted -> no bias change (older clients). |
| `section_number` | int (1-indexed) | both | Current section order (the `section_number` read, in the section-metadata extraction block). |
| `section_label` | string | both | Display label for the current section (the `section_label` read, same block). |
| `total_sections` | int | both | Section count (the `total_sections` read, same block). |
| `section_id` | string \| null | both* | Section ID, e.g. `"part_1_2_addresses"` (the `section_id` read, same block). Used for the token-log context. *See DRIFT note below -- the primary builder does NOT send it. |
| `previous_spoken_names` | string[] | both | Spoken names from completed sections; defaults to `[]` (the `previous_spoken_names` read, same block). Sent by both builders (the JIT builder since A2). |
| `initial_field_hint` | string \| null | both* | First-unfilled-field hint computed by the frontend; `null` when the form is complete (the `initial_field_hint` read, just after the section-metadata block). *Only the JIT builder sends it (since A2, gap D-hint) -- `getHandshakePayload` (legacy) omits it, the same asymmetry as `section_id` elsewhere in this table (`kit_id` no longer belongs on that list -- bd `polyglot-pdf-s1iex.6` closed it for both builders). It reaches the backend on a section switch via `webFormConnection.ts`, but not on the legacy builder's initial connect. |
| `resume` | bool | both | Reconnect flag. Read as `is_reconnect` (the `is_reconnect = bool(handshake.get("resume", False))` read); suppresses the greeting/section-intro on a mid-section reconnect (bd polyglot-pdf-vmxx). |
| `kit_id` | string \| null | both | The KIT identifier (e.g. `"w7"`) -- the catalogue key the user selected, read from `onboardingStorage`. Recorded in the confirmation audit trail because `form_number` is **not unique**: two kits can share one (a standard W-7 and a firm-specific variant, which the firm-tier epic anticipates), and only `kit_id` tells them apart in a liability record (bd `polyglot-pdf-47r3`). Read at the SHARED handshake scope -- it names the kit, not the form, so it is NOT a `form_metadata` key and is threaded as its own argument through `start_session` -> `CallbackHandler`. **BOTH `getHandshakePayload` builders send it** -- the JIT one since bd `polyglot-pdf-47r3`, the legacy one since bd `polyglot-pdf-s1iex.6` (before that, a session whose FIRST handshake took the legacy branch recorded `kit_id=None` for every confirmation; harmless while a second, JIT handshake always followed, and silent audit-trail loss once the intro path made Agree's connect the only one). The hand-rolled section-switch handshake in `webFormConnection.ts` (DEPRECATED path) still omits it -- bd `polyglot-pdf-d95y` criterion 2. Null on an older client. |

### Legacy-mode keys (`type: "handshake"`)

| Key | Type | Meaning |
|-----|------|---------|
| `schema` | object (`{source, fields, sections, ...}`) | The WHOLE current section's schema. Required; an invalid/missing `schema` closes the socket with `invalid_schema` (the legacy-branch `schema_required` error send). `schema.source` must be `"web"` or `"pdf"` (the `source_must_be_web_or_pdf` error send). |

### Manifest-first transport keys (`type: "handshake_jit"`)

This is the manifest-first handshake TRANSPORT -- DTI's carrier. The `jit` name is
historical; the JIT SI mode was removed (bd polyglot-pdf-en2j), but the transport
survives and DTI rides it. The backend synthesizes a minimal per-section `schema`
from these keys and ai_context renders the DTI static SI (or the legacy full-SI
when `USE_DTI` is off) from it.

| Key | Type | Meaning |
|-----|------|---------|
| `manifest` | `HandshakeManifest` | The frontend builds it as `{current_section, previous_sections, parts}` (`frontend/src/schema-forms/utils/manifestUtils.ts:35-41`) -- NOT a top-level `fields` array. The backend stores the whole object; it consumes `manifest.current_section.fields` + `manifest.previous_sections` for progress/section context and `manifest.parts` for the section nav list. Manifest field-entry shape is owned by [si-reduction.md](si-reduction.md). |
| `first_field_schema` | object \| null | Full schema for the FIRST-UNFILLED field of the section (selected via `computeNextField`), not the positional first field. The backend stores it as the section's single `schema["fields"]` entry; DTI's per-field guidance for field 1 is derived from it. |
| `loaded_field_ids` | string[] | Field IDs whose full schema the client has already sent to Gemini; defaults to `[]`. Part of the transport contract (the backend no longer de-dups on it since the JIT drip was removed, but the key is still sent). |
| `form_title` | string | The form's display title (`schema.form_metadata.title`), so `{form_title}` in the legacy SI is the real form, not the literal "Form"; the backend stores it into `schema["form_metadata"]["title"]`. |
| `form_number` | string \| null | The form's IDENTIFIER (`schema.form_metadata.form_number`, e.g. `"W-7"`), stored into `schema["form_metadata"]["form_number"]`. Deliberately DISTINCT from `form_title` (a human label): this is the value the confirmation audit trail logs as `form_id`, and it also keys the token-cost logging context. Without it the minimal JIT schema had no `form_metadata.form_number`, so every confirmation event recorded `form_id="unknown"` and the liability record could not name the form (bd `polyglot-pdf-n0em`). An older client omitting the key degrades to `"unknown"`; the backend builds `form_metadata` when ANY of `form_title` / `form_number` / `edition_date` is present. |
| `edition_date` | string \| null | The form's GOVERNMENT EDITION (`schema.form_metadata.edition_date`, e.g. `"12/2024"`), stored into `schema["form_metadata"]["edition_date"]`. Agencies revise forms and enforce edition dates, so a disputed filing must be able to answer "which edition did the client confirm against?" (bd `polyglot-pdf-47r3`). Sourced from `edition_date`, **never** `form_metadata.version` -- `version` is a schema-AUTHORING field whose values differ in meaning per kit (`"v9_conformant"`, `"draft"`) and would put a version-shaped field with per-kit semantics into a legal record. Null when the kit has no government edition (a custom form) or on an older client -- the backend then records a content fingerprint of the kit's answerable shape instead, so a revision is always pinned (see [confirmation-and-audit.md](confirmation-and-audit.md)). |

With this transport, `schema` is synthesized backend-side from `manifest` +
`first_field_schema` (websocket_routes.py's JIT handshake branch), so the
legacy `schema` key is absent.

### Handshake acknowledgement (backend -> frontend)

The backend replies with `session_ready` (websocket_routes.py, the
`session_ready` payload send):

| Key | Type | Meaning |
|-----|------|---------|
| `type` | `"session_ready"` | Handshake accepted; session live. |
| `session_id` | string | Ephemeral, connection-scoped (`web_<token>`); logging only, never persisted. |
| `ephemeral` | bool (`true`) | Signals the client the backend is stateless. |
| `jit_mode_enabled` | bool | Mirrors backend `USE_DTI` (the JIT SI mode was removed, bd polyglot-pdf-en2j); names the manifest-first handshake TRANSPORT the client should build next time -- DTI rides it. |
| `dti_mode_enabled` | bool | Mirrors backend `USE_DTI`; consumed by the client's `handleSessionReady` destructure (sent-but-undocumented until the ceyt contract tests caught it). |
| `continuous_session_enabled` | bool | Mirrors backend `CONTINUOUS_SESSION`; when true the client builds a single whole-form handshake and stops advancing sections, so the whole form runs as one compression-bounded session (bd polyglot-pdf-x8rt). |

---

## Current state: the message-type union

After the handshake, control messages flow both ways as JSON objects keyed by
`type`. (Audio is a separate binary framing, not part of this union.)

### Backend -> frontend

Sent via `send_json` in `backend/services/callback_handler.py`,
`backend/services/form_filling_service.py`,
`backend/services/request_coordinator.py`, and
`backend/routes/websocket_routes.py`. The frontend switches on `message.type` in
`webFormConnection.ts` (lines 659-854).

| Type | Source | Purpose |
|------|--------|---------|
| `session_ready` | websocket_routes.py (session_ready payload send) | Handshake ack (see above). |
| `form_updated` | callback_handler.py's `send_form_update` | A field value changed; carries `data` payload. |
| `transcript` | callback_handler.py's `on_transcript` | AI/user transcript text. |
| `turn_complete` | callback_handler.py's `on_transcript` | Gemini finished speaking; feeds the activity watchdog. Also a safety CLEAR for the thinking indicator. |
| `agent_processing` | callback_handler.py (`_set_processing`) | Thinking-indicator signal (bd polyglot-pdf-wpw.5 / fa4x): carries `processing` (bool). `true` on a real user turn -- it rides `send_activity_end`, the PTT release, which is the only turn signal (bd polyglot-pdf-v1m8g; the `input_transcription` -> `on_user_activity` path served the retired native-VAD mode); `false` at the agent's first response audio / turn end. The client shows a calm "thinking" indicator for the gap. PII-free (a bare boolean). |
| `go_away` | callback_handler.py's `on_go_away` | Gemini Live server will terminate soon; carries `time_left` (bd polyglot-pdf-c5t). Reconnect is wanted. |
| `interrupted` | callback_handler.py (`on_interrupted`) | Gemini stopped the current generation because the user barged in (bd polyglot-pdf-s7uf). The client drains BOTH its audio holds (staging queue + scheduled playback via `resetPlaybackClock`) so the dead generation's tail stops playing; without this, barge-in leaves seconds of stale audio playing behind the model's next generation. No payload; the connection stays live. |
| `gemini_session_dropped` | callback_handler.py (`on_session_dropped`) | Gemini session died SPONTANEOUSLY behind the still-open WS (e.g. a 1011 "Input data processing failed") -- the client is otherwise frozen on "connected" (bd polyglot-pdf-ppfy). Drives the same pre-emptive reconnect as `go_away`, but the client surfaces a `reconnecting` status so the transient recovery modal shows. No payload. |
| `idle_timeout` | websocket_routes.py (`_handle_fill_session`'s `watchdog_task` -- NOT the same-named closures in `ws_echo`/`ws_audio`) | Backend closing for inactivity; client must NOT auto-reconnect. |
| `section_switched` | form_filling_service.py:1446 | Same-socket section switch completed. |
| `gemini_session_ended` | websocket_routes.py (end_gemini_session arm) | Gemini session ended. |
| `gemini_session_restarted` | websocket_routes.py (restart_gemini_session arm) | Gemini session restarted successfully. |
| `get_form_state` | request_coordinator.py:173 | Backend asks the client for current form state. |
| `get_next_field_hint` | request_coordinator.py:238 | Backend asks the client to compute the next-field hint. |
| `confirm_field` | request_coordinator.py:315 | Backend asks the client to confirm a field. |
| `skip_field` | request_coordinator.py:391 | Backend asks the client to force-skip a required field the user cannot answer (bd polyglot-pdf-7yra). The client records the skip (markFieldSkipped: empty value + skipped flag) and replies `skip_field_response`. |
| `spellback` | request_coordinator.py:541 | Backend asks the client to play the deterministic spell-back clip for the CURRENT field (the `name_spellback` tool, bd polyglot-pdf-22h1f). Carries ONLY `request_id` -- no field id (the client resolves the current field itself with the pin-aware NEXT-FIELD computation, `computeNextField` -- a client-only resolution, distinct from `confirm_field`'s backend-supplied-and-coerced `field_id`) and never a value. The client reads the stored value, fetches the Cloud TTS clip from `/api/tts/spellback` (POSTing the value + the session's spoken-language name, bd polyglot-pdf-44ywm -- the clip speaks the user's language and carries the whole verification question), mutes the mic, plays it BLOCKING, and replies `spellback_response`. Unlike every other round-trip this one deliberately holds the tool response for the playback duration (90s coordinator cap) -- the model must stay parked until the clip ends. |
| `switch_field` | request_coordinator.py:455 | Backend asks the client to make ONE specific field current (the switch_to_field tool, bd polyglot-pdf-jnjj.36 -- field-level navigation for secretary-directed jumps + corrections). Carries `field` (a field_id or exact spoken name). The client resolves it WHOLE-schema, pins it so computeNextField returns it first (UI focus follows via onNextField), and replies `switch_field_response`. Unlike a section switch (the `switch_section` tool), the Gemini session is NOT restarted. |
| `prepare_section_switch` | request_coordinator.py:612 | Backend asks the client to pre-stage a section switch. |
| `form_state_ack` | websocket_routes.py (form_state arm) | Ack of a client `form_state`; carries `applied_fields`. |
| `hint_ack` | websocket_routes.py (next_field_hint arm) | Ack of a client `next_field_hint`. |
| `completion_ack` | websocket_routes.py (completion_message arm) | Ack of a client `completion_message`. |
| `recovery_prompt_ack` | websocket_routes.py (recovery_prompt arm) | Ack of a client `recovery_prompt`. |
| `voice_mode_ack` | websocket_routes.py (voice_mode arm) | Ack of a client `voice_mode`, echoing the mode now in force. |
| `section_completed_ack` | websocket_routes.py (section_completed arm) | Ack of a client `section_completed` (legacy reactive). |
| `section_complete_ack` | websocket_routes.py (section_complete arm) | B / jnjj.16 (B4). Ack of the proactive `section_complete` event. |
| `form_complete_ack` | websocket_routes.py (form_complete arm) | B / jnjj.16 (B4). Ack of the proactive `form_complete` event. |
| `validate_windows_ack` | websocket_routes.py (validate_windows arm) | W1 / bd polyglot-pdf-xbl2. Immediate ack of the async stride `validate_windows` trigger. The validator runs OFF the receive loop (background task); the verdict follows as a separate `validation_result` push when the flash-lite batch lands. |
| `drain_findings_ack` | websocket_routes.py (drain_findings arm) | W3 / bd polyglot-pdf-pr3i. Immediate ack of the client's `drain_findings`. The steer is composed + injected OFF the receive loop (background task); the delivery outcome follows as a separate `drain_findings_result`. |
| `drain_findings_result` | websocket_routes.py (drain_findings background task) | W3 / bd polyglot-pdf-pr3i. `{type, conflicts}` -- the conflicts whose steer ACTUALLY DELIVERED into the live session. The client marks those fields `steered` + CONSUMES them from its validatorFindingsQueue; un-delivered conflicts (dead session) are absent, so the client keeps them queued to retry on a later drain (fail-OPEN). |
| `validation_result` | websocket_routes.py (section_complete / form_complete / validate_windows arms, async) | B / jnjj.17 (B5), async since W1 / bd polyglot-pdf-xbl2, REPORT-ONLY since W3 / bd polyglot-pdf-pr3i. The validator verdict for a boundary: `{type, conflicts}` (clean = `[]`). W3: this is REPORT-ONLY -- it no longer injects a steer; a conflict is a CANDIDATE the client ENQUEUES into its validatorFindingsQueue and drains via `drain_findings`. Each conflict now also carries a `field_names` id->name rider for the drain payload. Pushed from a background task AFTER the boundary's `*_ack`. Payload shape -> [validation-delegation.md](validation-delegation.md) (F3, contract 1). |
| `disclaimer_read_initiated` | websocket_routes.py (read_disclaimer arm) | Disclaimer read started; carries `language`. |
| `language_changed` | websocket_routes.py (change_fill_language arm) | Fill language changed. |
| `spoken_language_changed` | websocket_routes.py | Ack of the re-assertion opener; the language did NOT change (see `change_spoken_language`). |
| `pong` | websocket_routes.py (`_handle_fill_session`'s `ping` arm -- NOT the same-named arms in the dev-only `ws_echo`/`ws_audio` sockets) | Liveness reply to a client `ping`; echoes `ts`. |
| `stats` | websocket_routes.py (`_handle_fill_session`'s `stats` arm -- NOT `ws_audio`'s differently-shaped `stats` reply) | Reply to a client `stats` request (`{message: "ok"}`). |
| `error` | many sites | Error with `code` (+ `reason`/`message`). |

### Frontend -> backend

Built/sent in `webFormConnection.ts`; dispatched on `obj.get("type")` in
`websocket_routes.py`'s `if mtype == ...` receive-loop switch.

| Type | Send site | Purpose |
|------|-----------|---------|
| `handshake` / `handshake_jit` | schemaFormState.ts's `getHandshakePayload` / `getJITHandshakePayload` | Initial + section-switch handshake (see above). |
| `form_state` | webFormConnection.ts:4097 | Push current form state; backend replies `form_state_ack`. |
| `form_state_response` | webFormConnection.ts:1479 | Reply to backend `get_form_state`. Each `field_values[id]` entry carries `{value, confirmed, shown}`. `shown` (bd polyglot-pdf-p68s / jnjj.45d) is the field's current applicability, computed client-side via `shouldShowField` (the backend is stateless and cannot derive it); it feeds the secretary's `shown_map` so a value-bearing-but-now-hidden field is distinguishable from a visible one. An older client that omits `shown` leaves the field out of `shown_map` (renderer default = shown). |
| `next_field_hint` | websocket_routes.py (next_field_hint arm) | Client-pushed next-field hint (distinct from the `get_next_field_hint` request/`next_field_hint_response` reply pair). No live FE sender today (the FE only sends `next_field_hint_response`; caught by the ceyt contract tests) -- the arm is retained for back-compat. |
| `next_field_hint_response` | webFormConnection.ts:1545 | Reply to backend `get_next_field_hint`. |
| `read_disclaimer` | websocket_routes.py (read_disclaimer arm; sent connection.ts:1129) | Client signals the disclaimer is being read; backend replies `disclaimer_read_initiated`. Carries `spoken_language` + `disclaimer_text` + optional `agree_button_label` (bd polyglot-pdf-s863) -- the TRANSLATED on-screen agree-button label (DisclaimerModal BUTTON_TRANSLATIONS), so the voice model names the button the user actually sees; the backend falls back to 'I Agree' when absent (old clients). |
| `restart_gemini_session` | websocket_routes.py (restart_gemini_session arm; sent connection.ts:658) | Client asks the backend to restart the Gemini session; backend replies `gemini_session_restarted`. |
| `section_completed` | websocket_routes.py (section_completed arm) | LEGACY reactive section-complete signal; backend replies `section_completed_ack`. No live FE sender today (the FE drives section completion via the confirm handler) -- the arm is retained for back-compat. DISTINCT from the proactive `section_complete` below -- do not conflate. |
| `section_complete` | webFormConnection.ts:2148 (confirm handler) / :2349 (skip handler) | B / jnjj.16 (B4). Proactive section-complete event: emitted the moment the last field of the current section is confirmed (a next section exists). Carries `section_id` + the contract-2 `fields` payload; backend replies `section_complete_ack`. Payload shape: [validation-delegation.md](validation-delegation.md) contract 4. |
| `form_complete` | webFormConnection.ts:2938 (confirm handler + manual-edit path) | B / jnjj.16 (B4). Proactive form-complete event: emitted once when the whole form is confirmed, re-emitted after a post-completion edit (client-side once-only + dirty guard). Carries the whole-form contract-2 `fields`; backend replies `form_complete_ack`. Payload shape: [validation-delegation.md](validation-delegation.md) contract 4. |
| `validate_windows` | webFormConnection.ts (maybeEmitValidateWindows, on the confirm/skip/edit seams) | W2 / bd polyglot-pdf-kxkw (backend arm W1 / xbl2). Async STRIDE validator trigger: carries `windows` -- a list of overlapping contract-2 field lists (size ~20, stride ~10 over SCHEMA FIELD ORDER). PAGE-AGNOSTIC (report-cadence revision 2026-07-13): the client emits a window once every field it covers is SETTLED (confirmed/skipped/not-applicable), keyed on schema order + the settled flags, NEVER pdf_position.page -- so a source:"web" / pageless form emits identically to a paginated one. Backend acks `validate_windows_ack` immediately and runs every window's flash-lite pass CONCURRENTLY off the receive loop, dedupes conflicts across the batch by field-id set, then pushes one `validation_result` (REPORT-ONLY since W3 -- it does NOT inject a steer; the client enqueues + drains). |
| `drain_findings` | webFormConnection.ts (drainFindings, on a non-empty validatorFindingsQueue) | W3 / bd polyglot-pdf-pr3i. The FINDING-DRIVEN drain: emitted the moment the client's queue is non-empty (a report-only `validation_result` enqueued a conflict) and on reconnect if a queue survived. Carries `conflicts` -- each `{field_ids, reason, field_names}` (field_names = the id->name map the steer composer needs). Backend acks `drain_findings_ack`, composes ONE steer (the oiok navigate/read-back/correct composer) off the receive loop, injects it, and pushes `drain_findings_result` with the delivered conflicts. |
| `client_diagnostic` | webFormConnection.ts (handleSessionReady, field-1 opener skip branch) | bd polyglot-pdf-xp4q. ONE-WAY, PII-free client-side diagnostic (no ack, no reply). Emitted when the field-1 opener auto-send was EXPECTED (a section-switch session_ready -- the post-I-Agree switchToFirstSection path is the primary producer -- or an accepted-disclaimer reconnect) but did NOT fire, naming the failing gate condition. Carries `event` (string token: `field1_opener_skipped`, or `section_switch_watchdog_timeout` when a switch never reached session_ready -- so an ABSENT opener diagnostic plus this token means 'failed before the gate', not 'no bug') + seven booleans: `was_section_switch`, `disclaimer_accepted`, `has_selected_language`, `has_next_field_hint`, `is_form_complete` (disambiguates the benign completed-form reconnect -- nothing left to ask, hint correctly empty -- from a genuinely broken opener), `storage_disclaimer_accepted` (persisted flag alongside the in-memory one the gate read: a divergence names the state-staleness hypothesis in one glance), and `continuous_session` (which scoping applies to the hint: section vs whole-form). Deploy-skew: an OLD backend answers with the `unknown_control` error ack, which the client explicitly tolerates (handleServerError early-out) -- that ack is non-fatal by definition and must never end a session or fail a switch. Backend logs a WHITELISTED `client_diagnostic` warning (never echoes arbitrary payload keys/values) and continues. The very first connect of a session (no switch, disclaimer not yet accepted) is a legitimate skip and emits nothing. |
| `section_info_response` | webFormConnection.ts:1655 (+others) | Reply with section metadata. |
| `confirm_field_response` | webFormConnection.ts:3207 | Reply to backend `confirm_field`. Carries `recorded` (+ optional `reason`), and -- when this confirm completed a section that has a NEXT section to advance to -- an optional `section_complete: true` flag so the backend skips the next-field-hint round-trip that would race the FE's `switchToSection` teardown (bd polyglot-pdf-njvh). This is a SUB-FIELD of the confirm reply, distinct from the SI-reduction epic's planned top-level `section_complete` event (see `section_completed` above + the reserved extension points). |
| `skip_field_response` | webFormConnection.ts:3328 | Reply to backend `skip_field` (bd polyglot-pdf-7yra). Same shape as `confirm_field_response`: `recorded` (+ optional `reason`, e.g. `unknown_field`/`already_filled`), and an optional `section_complete: true` when the skip completed a section with a next one to advance to. A skipped field satisfies the section, so a section-completing skip advances identically to a confirm. |
| `spellback_response` | webFormConnection.ts:3303 | Reply to backend `spellback` (bd polyglot-pdf-22h1f). Carries `status` (`delivered` = the user HAS heard this spelling and was asked to confirm -- a full clip playback, or a stale-arrival dedup ack for a value delivered within the last ~3s (bd polyglot-pdf-kvrfq), the latter with NO timing fields; `interrupted` = the user's speech takes precedence -- a PTT press during the round-trip, or an instant guard refusal of a request arriving while PTT is held / within the ~5s post-interrupt cooldown (bd kvrfq), again timing-field-free -- PTT-ONLY today: in open-mic native-VAD mode the mic hold means voice alone cannot barge into a clip, so the press-driven variant is unreachable there (bd polyglot-pdf-flnz1); `error` = nothing played), an optional fixed `reason` token (`no_value`, `no_current_field`, `no_playback_path`, `playback_exception`, `no_audio_manager`, `value_too_long`, `cancelled`, `tts_fetch_failed`, `tts_http_<code>`), and optional `playback_ms`/`fetch_ms` timings (the bead's latency measurement). NEVER carries the field value. |
| `switch_field_response` | webFormConnection.ts `sendSwitchFieldResponse` (called from `handleSwitchFieldRequest`, success + failure sites) | Reply to backend `switch_field` (bd polyglot-pdf-jnjj.36). `found` plus outcome keys: success carries `field_id`, `spoken_name`, `next_field_hint`, `already_confirmed`, `has_value` (+ `value` when filled, so the model can read it back -- same Gemini trust boundary as `ask_secretary`; + `next_field_schema` in DTI mode, the guidance/validation source). Failure carries a fixed `reason` token: `unknown_field`, `hidden` (conditionally inactive), or `other_section` (+ `section_label`/`section_order` so the model can `switch_section` first in section-scoped modes). |
| `manual_field_update` | webFormConnection.ts:3848 | User edited a field directly. Carries `next_field_hint` and -- in DTI mode -- an optional `next_field_schema` (the next unconfirmed field's full schema, no user values), so the backend can re-establish the DTI current-field coercion pointer + validation entry that the edit's pointer-clear would otherwise strand (a manual edit skips the `confirm_field` round-trip that normally carries the next schema; bd polyglot-pdf-ezg2). Both computed from the POST-edit persisted state. |
| `manual_section_switch` | webFormConnection.ts:4630 | User-initiated section switch. |
| `completion_message` | webFormConnection.ts:1227 (+others) | Form/section completion message to the AI. |
| `recovery_prompt` | webFormConnection.ts:3953 | Escalating recovery prompt (level 1-3). |
| `change_fill_language` | webFormConnection.ts:3988 | Change the AI fill language. |
| `change_spoken_language` | webFormConnection.ts (session_ready opener) | MISNOMER -- does NOT switch language. The spoken language is PINNED per session; this RE-ASSERTS the same pinned language on a fresh Gemini session after a socket teardown (reconnect / section switch), so the backend re-sends the initiating message. See [voice-and-vad.md](voice-and-vad.md) ("the spoken language is pinned per session"); bd polyglot-pdf-87a9. |
| `vad_activity_start` / `vad_activity_end` | webFormConnection.ts `sendActivityStart` / `sendActivityEnd` | PTT press/release. The ONLY turn signal -- Gemini's own detection is disabled (bd polyglot-pdf-v1m8g). `vad_activity_start` also leaves manual mode (bd polyglot-pdf-wurj8). |
| `voice_mode` | webFormConnection.ts `setVoiceMode` | Manual/voice mode toggle (bd polyglot-pdf-wurj8). `mode` is `manual` or `voice`; `manual` suppresses the model's proactive speech while the session stays live. Re-sent on every (re)connect -- the backend is stateless. An unrecognised `mode` is rejected rather than defaulted to manual. |
| `clear_thinking` | webFormConnection.ts:3435 / :4220 | Thinking-indicator desync guard (bd polyglot-pdf-wpw.5, Codex PR #273): sent when the client's max-duration safety timer fires or on a server error, so the backend resets its `_processing_active` state too (else it stays stuck True and dedups the next turn's `agent_processing:true`). Backend handler `clear_processing_state` (the `clear_thinking` arm calls `service.clear_processing_state()`); fire-and-forget, no ack. |
| `end_gemini_session` | webFormConnection.ts:3971 | Ask the backend to end the Gemini session. |
| `ping` | -- | Liveness; backend replies `pong` (echoing `ts`). |
| `stats` | -- | Stats/health probe; backend replies `stats` (`{message: "ok"}`). |

---

## Frozen extension points (the epic's reserved additions)

These names are RESERVED here so the pillars do not collide. Shapes are designed
in the cited beads/docs, not here.

### Pillar B -- cheap-model validator

Pillar B makes completion PROACTIVE and adds a validator round-trip. The proactive
events have LANDED (B4); the validator verdict is still reserved (B5):

| Type | Direction | Pillar / bead | Notes |
|------|-----------|---------------|-------|
| `section_complete` | frontend -> backend | B / bd polyglot-pdf-jnjj.16 (B4) | SHIPPED. Proactive section-complete event. Now LIVE in the frontend->backend table above (emitted by the confirm handler; backend acks `section_complete_ack`). |
| `form_complete` | frontend -> backend | B / bd polyglot-pdf-jnjj.16 (B4) | SHIPPED. Proactive form-complete event. Now LIVE in the frontend->backend table above (acks `form_complete_ack`). |
| `validation_result` | backend -> frontend | B / bd polyglot-pdf-jnjj.17 (B5) | SHIPPED. Now LIVE in the backend->frontend table above (pushed by the section_complete / form_complete arms every boundary; the FE gates the section switch on it). Full envelope (`{type, conflicts}`) -> [validation-delegation.md](validation-delegation.md) (F3). |

> **The validator STEER is NOT a WS message type.** When a conflict is found, the
> correction directive is injected **backend -> Gemini Live session** as a text turn
> (the live model voices it), NOT sent to the browser -- see
> [validation-delegation.md](validation-delegation.md) (F3, "Steering directive").
> An earlier draft wrongly reserved a `validator_steer` backend->frontend type; it
> is removed. The frontend's default-ignore path (`webFormConnection.ts:851-853`)
> would silently drop such a message, so a steer routed to the client would never be
> voiced. Only `validation_result` (above) is a real wire message in B.

Payload shapes are designed in F3
([validation-delegation.md](validation-delegation.md)), not here.
(`section_complete`/`form_complete` are NOT the existing
`section_completed`/`completion_message` control messages -- those are the legacy
reactive acks; the proactive pair B4 shipped are the entries in the
frontend->backend table above.) The validator STEER is deliberately absent from
this registry -- it is a backend->Gemini Live injection, not a wire message (see
the callout above).

### Pillar C -- restart cadence

| Handshake key | Type | Pillar / bead | Notes |
|---------------|------|---------------|-------|
| `session_resumption_handle` | string \| null | C / bd polyglot-pdf-jnjj.19 (C2) | Gemini Live session-resumption handle carried on the handshake so a backend-driven restart can resume mid-session rather than cold-starting. RESERVED key; shape + lifecycle owned by the C beads. |

### Pillar A -- SI reduction

Pillar A's wire surface already exists: the manifest-first transport's `manifest`
+ `loaded_field_ids` handshake keys above. A may EXTEND the `manifest` shape, but
that shape is owned by [si-reduction.md](si-reduction.md) (the F1 contract) --
reference it, do not redefine the manifest here. No new top-level handshake key
or message type is reserved for A beyond the existing manifest-first transport keys.

---

## DRIFT flags (frontend/backend name verification)

Exit-criterion 3 requires confirming the frontend and backend field names match.
They match on every key the backend reads, with these real gaps found while
verifying:

1. **`section_id` is read by the backend but NOT sent by the primary handshake
   builders.** `getHandshakePayload` / `getJITHandshakePayload`
   (`schemaFormState.ts`) omit it; the backend reads it
   (`handshake.get("section_id")` in websocket_routes.py's handshake handling)
   and falls back to `None`. It IS sent by the section-switch handshakes
   (`webFormConnection.ts`), so the backend sees it on a switch but not the initial
   connect. Benign today (the backend tolerates `None`); a pillar that depends on
   `section_id` on first connect must close this gap. (`initial_field_hint` was in
   this same flag -- now RESOLVED for the JIT builder, see below.)

2. **RESOLVED (A2, bd polyglot-pdf-jnjj.9): the JIT builder now sends
   `previous_spoken_names`, `initial_field_hint`, and `form_title`.** These three
   were previously omitted by `getJITHandshakePayload`, leaving the JIT SI's
   `{previous_spoken_names}`, `{next_field_hint}`, and `{form_title}` wrong (gaps
   M/D-hint/O in [../components/jit-schema.md](../components/jit-schema.md)). A2
   added them to the JIT handshake; the backend already read the first two
   (`previous_spoken_names` / `initial_field_hint` reads in websocket_routes.py's
   handshake handling) and now stores `form_title` into
   `schema["form_metadata"]`. The legacy builder always sent `previous_spoken_names`
   (`schemaFormState.ts` `getHandshakePayload`); the JIT builder now matches
   (`getJITHandshakePayload`, which sends `previous_spoken_names` and `form_title`
   in the same payload). Anchored to the SYMBOLS rather than line numbers: these
   citations drifted once already when the builders moved down the file.

3. **`field_update` is a frontend RECEIVE handler with no backend sender.** The
   frontend switches on `case "field_update"` (in `webFormConnection.ts`'s message switch ->
   `handleFieldUpdate`), but no backend `send_json` ever emits that type -- the
   live single-field push the backend actually sends is `form_updated`. So
   `field_update` is a dead/legacy receive path on the client; it is NOT in the
   backend->frontend table above. Left as-is (cleanup is out of scope for this
   doc-only bead).

4. **No other drift.** All other keys the backend reads (`type`,
   `form_session_id`, `manifest`, `first_field_schema`, `loaded_field_ids`,
   `schema`, `full_schema`, `current_values`, `fill_language`, `section_number`,
   `section_label`, `total_sections`, `resume`) are produced verbatim by the
   frontend builders, and every backend->frontend type in the table above has a
   matching backend `send_json`.
