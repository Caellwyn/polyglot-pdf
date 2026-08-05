# WebSocket protocol -- frozen handshake + message-type contract

**Tracks:** backend/routes/websocket_routes.py frontend/src/webFormConnection.ts frontend/src/schema-forms/state/schemaFormState.ts

*Last updated: 2026-08-04 (bd polyglot-pdf-87a9 + n0em -- two same-day entries). bd polyglot-pdf-87a9: the `change_spoken_language` row is corrected -- it is a MISNOMER that RE-ASSERTS the session's PINNED language after a socket teardown, not a language switch (mid-conversation switching is unsupported; see voice-and-vad.md). The stale send-site line number is dropped.) Prior: 2026-08-03 (bd polyglot-pdf-xp4q: new frontend->backend `client_diagnostic` type -- one-way, PII-free, no ack; emitted when the field-1 opener auto-send was expected at session_ready but skipped, carrying the gate booleans so production logs name the failing condition; see the client->backend table row). Prior: 2026-07-16 (bd polyglot-pdf-y25o: new handshake key `spoken_language` -- the app-start language choice, read pre-connect for the ASR transcription language bias; see the handshake key table + [../journal/entries/2026-07-16-bd-yo5t-voice-misfire-batch.md](../journal/entries/2026-07-16-bd-yo5t-voice-misfire-batch.md)). Prior: 2026-07-15 (bd polyglot-pdf-s863: `read_disclaimer` gains an optional `agree_button_label` rider -- the translated on-screen agree-button label the disclaimer prompt now names instead of a hardcoded English 'I Agree'; see the client->backend table row). Prior: 2026-07-13 (bd polyglot-pdf-pr3i (W3, async validator): FINDING-DRIVEN drain. `validation_result` is now REPORT-ONLY (no steer injection; conflicts gain a `field_names` rider); the client enqueues them and sends the new frontend->backend `drain_findings` (carries the queued conflicts), which the backend acks (`drain_findings_ack`) then composes+injects one steer off the receive loop and pushes `drain_findings_result` with the delivered conflicts (client marks steered + consumes the queue). See both tables.). Prior: 2026-07-13 (bd polyglot-pdf-kxkw (W2, async validator): the `validate_windows` FE emitter is now LIVE (webFormConnection.maybeEmitValidateWindows) and PAGE-AGNOSTIC -- a client-side STRIDE window builder keyed on schema field order + settled flags, no pdf_position.page; the doc row + backend comment now describe a stride trigger, not a page-boundary one. Also removed `validate_windows` from the contract test's no-FE-sender exception set. Prior: 2026-07-13 (bd polyglot-pdf-xbl2 (W1, async validator): new frontend->backend `validate_windows` type (async validator trigger, overlapping windows; FE emitter lands in W2) + new backend->frontend `validate_windows_ack`; the validator now runs OFF the receive loop, so `validation_result` is PUSHED from a background task after the boundary's `*_ack` (not before) -- envelope shape unchanged. See both tables.). Prior: 2026-07-11 (bd polyglot-pdf-jnjj.36: new backend->frontend `switch_field` type + frontend->backend `switch_field_response` -- the voice switch_to_field tool jumps focus to one specific field (secretary-directed jumps + corrections); the client resolves whole-schema, pins the field for next-field computation, and acks with the target's hint + DTI schema. See both tables.). Prior: 2026-07-09 (bd polyglot-pdf-7yra: new backend->frontend `skip_field` type + frontend->backend `skip_field_response` -- the voice skip_field tool lets the assistant force-skip a required field the user cannot answer, recorded via markFieldSkipped; same round-trip shape as confirm_field. See both tables.). Prior: 2026-07-07 (bd polyglot-pdf-ppfy: new backend->frontend `gemini_session_dropped` type -- a spontaneous Gemini drop (1011) forwarded so the client reconnects and shows the transient recovery modal; see the backend->frontend table). Prior: 2026-07-06 (bd polyglot-pdf-x8rt: `session_ready` gains a `continuous_session_enabled` key -- see the Handshake acknowledgement table). Prior: 2026-07-05 (bd polyglot-pdf-ezg2: `manual_field_update` gains an optional DTI-mode `next_field_schema` rider -- see the client->backend table row). Also 2026-07-05 (bd polyglot-pdf-mpoe staleness sweep: refreshed all `websocket_routes.py`/`webFormConnection.ts`/`schemaFormState.ts` line-number citations, which had drifted from code growth across several intervening commits -- no wire-type or handshake-key name changed; see [../journal/entries/2026-07-05-bd-mpoe-doc-staleness-sweep.md](../journal/entries/2026-07-05-bd-mpoe-doc-staleness-sweep.md)). Prior: 2026-07-02 (bd polyglot-pdf-ceyt: this doc's message-type union is now pinned by contract tests -- backend/tests/contract/test_websocket_protocol.py diffs these tables against the code, so renaming or dropping a wire type fails a test; also documented the previously-missing `dti_mode_enabled` session_ready key those tests caught). Prior (same day): 2026-08-04 (bd polyglot-pdf-n0em: new manifest-first handshake key `form_number` -- the form IDENTIFIER, distinct from the display-label `form_title`; without it the JIT transport carried no `form_metadata.form_number`, so every confirmation-audit event logged `form_id="unknown"` and the liability record could not name the form; see the manifest-first handshake key table). Prior: 2026-08-03 (bd polyglot-pdf-xp4q: new frontend->backend `client_diagnostic` type -- one-way, PII-free, no ack; emitted when the field-1 opener auto-send was expected at session_ready but skipped, carrying the gate booleans so production logs name the failing condition; see the client->backend table row). Prior: 2026-07-16 (bd polyglot-pdf-y25o: new handshake key `spoken_language` -- the app-start language choice, read pre-connect for the ASR transcription language bias; see the handshake key table + [../journal/entries/2026-07-16-bd-yo5t-voice-misfire-batch.md](../journal/entries/2026-07-16-bd-yo5t-voice-misfire-batch.md)). Prior: 2026-07-15 (bd polyglot-pdf-s863: `read_disclaimer` gains an optional `agree_button_label` rider -- the translated on-screen agree-button label the disclaimer prompt now names instead of a hardcoded English 'I Agree'; see the client->backend table row). Prior: 2026-07-13 (bd polyglot-pdf-pr3i (W3, async validator): FINDING-DRIVEN drain. `validation_result` is now REPORT-ONLY (no steer injection; conflicts gain a `field_names` rider); the client enqueues them and sends the new frontend->backend `drain_findings` (carries the queued conflicts), which the backend acks (`drain_findings_ack`) then composes+injects one steer off the receive loop and pushes `drain_findings_result` with the delivered conflicts (client marks steered + consumes the queue). See both tables.). Prior: 2026-07-13 (bd polyglot-pdf-kxkw (W2, async validator): the `validate_windows` FE emitter is now LIVE (webFormConnection.maybeEmitValidateWindows) and PAGE-AGNOSTIC -- a client-side STRIDE window builder keyed on schema field order + settled flags, no pdf_position.page; the doc row + backend comment now describe a stride trigger, not a page-boundary one. Also removed `validate_windows` from the contract test's no-FE-sender exception set. Prior: 2026-07-13 (bd polyglot-pdf-xbl2 (W1, async validator): new frontend->backend `validate_windows` type (async validator trigger, overlapping windows; FE emitter lands in W2) + new backend->frontend `validate_windows_ack`; the validator now runs OFF the receive loop, so `validation_result` is PUSHED from a background task after the boundary's `*_ack` (not before) -- envelope shape unchanged. See both tables.). Prior: 2026-07-11 (bd polyglot-pdf-jnjj.36: new backend->frontend `switch_field` type + frontend->backend `switch_field_response` -- the voice switch_to_field tool jumps focus to one specific field (secretary-directed jumps + corrections); the client resolves whole-schema, pins the field for next-field computation, and acks with the target's hint + DTI schema. See both tables.). Prior: 2026-07-09 (bd polyglot-pdf-7yra: new backend->frontend `skip_field` type + frontend->backend `skip_field_response` -- the voice skip_field tool lets the assistant force-skip a required field the user cannot answer, recorded via markFieldSkipped; same round-trip shape as confirm_field. See both tables.). Prior: 2026-07-07 (bd polyglot-pdf-ppfy: new backend->frontend `gemini_session_dropped` type -- a spontaneous Gemini drop (1011) forwarded so the client reconnects and shows the transient recovery modal; see the backend->frontend table). Prior: 2026-07-06 (bd polyglot-pdf-x8rt: `session_ready` gains a `continuous_session_enabled` key -- see the Handshake acknowledgement table). Prior: 2026-07-05 (bd polyglot-pdf-ezg2: `manual_field_update` gains an optional DTI-mode `next_field_schema` rider -- see the client->backend table row). Also 2026-07-05 (bd polyglot-pdf-mpoe staleness sweep: refreshed all `websocket_routes.py`/`webFormConnection.ts`/`schemaFormState.ts` line-number citations, which had drifted from code growth across several intervening commits -- no wire-type or handshake-key name changed; see [../journal/entries/2026-07-05-bd-mpoe-doc-staleness-sweep.md](../journal/entries/2026-07-05-bd-mpoe-doc-staleness-sweep.md)). Prior: 2026-07-02 (bd polyglot-pdf-ceyt: this doc's message-type union is now pinned by contract tests -- backend/tests/contract/test_websocket_protocol.py diffs these tables against the code, so renaming or dropping a wire type fails a test; also documented the previously-missing `dti_mode_enabled` session_ready key those tests caught).

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
`backend/routes/websocket_routes.py` (extraction at lines 777-856; dispatched
into `_handle_fill_session` at line 914). It branches on `type` into two
handshake shapes -- the **legacy** full-section-schema handshake and the
**manifest-first transport** (`handshake_jit`: manifest + first field). The
`jit` name is historical; the manifest-first transport is DTI's carrier, not the
removed JIT SI mode (bd polyglot-pdf-en2j).

### Mode selector + shared keys

| Key | Type | Mode | Meaning |
|-----|------|------|---------|
| `type` | `"handshake"` \| `"handshake_jit"` | both | Selects the handshake shape. `handshake_jit` -> the manifest-first transport (DTI's carrier; line 780). Anything else (incl. missing) -> the legacy full-schema handshake. |
| `form_session_id` | string | both | Persistent, frontend-managed ID; survives reconnects. Logging/metrics correlation only -- never used for server-side state (line 783). |
| `current_values` | object (field_id -> FieldValue) | both | Pre-filled values for reconnect; defaults to `{}` (line 830). |
| `full_schema` | object (`{source, fields, sections, parts, ...}`) \| absent | both | The WHOLE form schema (all parts/sections/fields), for the secretary catalog (bd polyglot-pdf-p68s / jnjj.45d). Distinct from `schema`/`manifest`, which carry only the CURRENT section. The backend caches it in-session in `FormFillingService._full_schema` and `handle_ask_secretary` renders the secretary's static catalog from it; preserved across same-form section switches. Schema only -- no PII; rebuilt from this on every (re)connect (stateless invariant). Optional: an older client that omits it makes the secretary fall back to the per-section `schema`. |
| `fill_language` | string | both | Language the AI fills/speaks in; defaults to `"English"` (line 831). |
| `spoken_language` | string \| null | both | The user's app-start SPOKEN-language choice (bd polyglot-pdf-y25o). Read at handshake time -- BEFORE the Gemini connect -- to derive the per-connect ASR transcription `language_codes` bias (the later `change_spoken_language` control message arrives too late for per-connect config). Null/omitted -> no bias change (older clients). |
| `section_number` | int (1-indexed) | both | Current section order (line 846). |
| `section_label` | string | both | Display label for the current section (line 847). |
| `total_sections` | int | both | Section count (line 848). |
| `section_id` | string \| null | both* | Section ID, e.g. `"part_1_2_addresses"` (line 845). Used for the token-log context. *See DRIFT note below -- the primary builder does NOT send it. |
| `previous_spoken_names` | string[] | both | Spoken names from completed sections; defaults to `[]` (line 849). Sent by both builders (the JIT builder since A2). |
| `initial_field_hint` | string \| null | both | First-unfilled-field hint computed by the frontend; `null` when the form is complete (line 852). Sent by both builders (the JIT builder since A2, gap D-hint). |
| `resume` | bool | both | Reconnect flag. Read as `is_reconnect` (line 856); suppresses the greeting/section-intro on a mid-section reconnect (bd polyglot-pdf-vmxx). |

### Legacy-mode keys (`type: "handshake"`)

| Key | Type | Meaning |
|-----|------|---------|
| `schema` | object (`{source, fields, sections, ...}`) | The WHOLE current section's schema. Required; an invalid/missing `schema` closes the socket with `invalid_schema` (lines 822-828). `schema.source` must be `"web"` or `"pdf"` (lines 858-864). |

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
| `form_number` | string \| null | The form's IDENTIFIER (`schema.form_metadata.form_number`, e.g. `"W-7"`), stored into `schema["form_metadata"]["form_number"]`. Deliberately DISTINCT from `form_title` (a human label): this is the value the confirmation audit trail logs as `form_id`, and it also keys the token-cost logging context. Without it the minimal JIT schema had no `form_metadata.form_number`, so every confirmation event recorded `form_id="unknown"` and the liability record could not name the form (bd `polyglot-pdf-n0em`). An older client omitting the key degrades to `"unknown"`; the backend builds `form_metadata` when EITHER key is present. |

With this transport, `schema` is synthesized backend-side from `manifest` +
`first_field_schema` (lines 796-805), so the legacy `schema` key is absent.

### Handshake acknowledgement (backend -> frontend)

The backend replies with `session_ready` (lines 896-911):

| Key | Type | Meaning |
|-----|------|---------|
| `type` | `"session_ready"` | Handshake accepted; session live. |
| `session_id` | string | Ephemeral, connection-scoped (`web_<token>`); logging only, never persisted. |
| `ephemeral` | bool (`true`) | Signals the client the backend is stateless. |
| `jit_mode_enabled` | bool | Mirrors backend `USE_DTI` (the JIT SI mode was removed, bd polyglot-pdf-en2j); names the manifest-first handshake TRANSPORT the client should build next time -- DTI rides it. |
| `dti_mode_enabled` | bool | Mirrors backend `USE_DTI`; consumed by the client's `handleSessionReady` destructure (sent-but-undocumented until the ceyt contract tests caught it). |
| `native_vad` | bool | Mirrors `not DISABLE_GEMINI_VAD`; when true the client streams continuous audio and stops sending manual activity signals (bd polyglot-pdf-333). |
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
`webFormConnection.ts` (lines 526-645).

| Type | Source | Purpose |
|------|--------|---------|
| `session_ready` | websocket_routes.py:898 | Handshake ack (see above). |
| `form_updated` | callback_handler.py:158 | A field value changed; carries `data` payload. |
| `transcript` | callback_handler.py:188 | AI/user transcript text. |
| `turn_complete` | callback_handler.py:195 | Gemini finished speaking; feeds the activity watchdog. Also a safety CLEAR for the thinking indicator. |
| `agent_processing` | callback_handler.py (`_set_processing`) | Thinking-indicator signal (bd polyglot-pdf-wpw.5 / fa4x): carries `processing` (bool). `true` on a real user turn (BOTH VAD modes -- manual rides `send_activity_end`, native rides `input_transcription` -> `on_user_activity`, verified firing on the 2.5 native-audio model at `VAD_START_SENSITIVITY=HIGH`); `false` at the agent's first response audio / turn end. The client shows a calm "thinking" indicator for the gap. PII-free (a bare boolean). |
| `go_away` | callback_handler.py:319 | Gemini Live server will terminate soon; carries `time_left` (bd polyglot-pdf-c5t). Reconnect is wanted. |
| `gemini_session_dropped` | callback_handler.py (`on_session_dropped`) | Gemini session died SPONTANEOUSLY behind the still-open WS (e.g. a 1011 "Input data processing failed") -- the client is otherwise frozen on "connected" (bd polyglot-pdf-ppfy). Drives the same pre-emptive reconnect as `go_away`, but the client surfaces a `reconnecting` status so the transient recovery modal shows. No payload. |
| `idle_timeout` | websocket_routes.py:303 | Backend closing for inactivity; client must NOT auto-reconnect. |
| `section_switched` | form_filling_service.py:1031 | Same-socket section switch completed. |
| `gemini_session_restarted` | websocket_routes.py:576 | Gemini session restarted successfully. |
| `gemini_session_ended` | websocket_routes.py:563 | Gemini session ended. |
| `get_form_state` | request_coordinator.py:173 | Backend asks the client for current form state. |
| `get_next_field_hint` | request_coordinator.py:238 | Backend asks the client to compute the next-field hint. |
| `confirm_field` | request_coordinator.py:315 | Backend asks the client to confirm a field. |
| `skip_field` | request_coordinator.py:391 | Backend asks the client to force-skip a required field the user cannot answer (bd polyglot-pdf-7yra). The client records the skip (markFieldSkipped: empty value + skipped flag) and replies `skip_field_response`. |
| `switch_field` | request_coordinator.py:455 | Backend asks the client to make ONE specific field current (the switch_to_field tool, bd polyglot-pdf-jnjj.36 -- field-level navigation for secretary-directed jumps + corrections). Carries `field` (a field_id or exact spoken name). The client resolves it WHOLE-schema, pins it so computeNextField returns it first (UI focus follows via onNextField), and replies `switch_field_response`. Unlike a section switch (the `switch_section` tool), the Gemini session is NOT restarted. |
| `prepare_section_switch` | request_coordinator.py:513 | Backend asks the client to pre-stage a section switch. |
| `form_state_ack` | websocket_routes.py:366 | Ack of a client `form_state`; carries `applied_fields`. |
| `hint_ack` | websocket_routes.py:379 | Ack of a client `next_field_hint`. |
| `completion_ack` | websocket_routes.py:486 | Ack of a client `completion_message`. |
| `recovery_prompt_ack` | websocket_routes.py:500 | Ack of a client `recovery_prompt`. |
| `section_completed_ack` | websocket_routes.py:646 | Ack of a client `section_completed` (legacy reactive). |
| `section_complete_ack` | websocket_routes.py (section_complete arm) | B / jnjj.16 (B4). Ack of the proactive `section_complete` event. |
| `form_complete_ack` | websocket_routes.py (form_complete arm) | B / jnjj.16 (B4). Ack of the proactive `form_complete` event. |
| `validate_windows_ack` | websocket_routes.py (validate_windows arm) | W1 / bd polyglot-pdf-xbl2. Immediate ack of the async stride `validate_windows` trigger. The validator runs OFF the receive loop (background task); the verdict follows as a separate `validation_result` push when the flash-lite batch lands. |
| `drain_findings_ack` | websocket_routes.py (drain_findings arm) | W3 / bd polyglot-pdf-pr3i. Immediate ack of the client's `drain_findings`. The steer is composed + injected OFF the receive loop (background task); the delivery outcome follows as a separate `drain_findings_result`. |
| `drain_findings_result` | websocket_routes.py (drain_findings background task) | W3 / bd polyglot-pdf-pr3i. `{type, conflicts}` -- the conflicts whose steer ACTUALLY DELIVERED into the live session. The client marks those fields `steered` + CONSUMES them from its validatorFindingsQueue; un-delivered conflicts (dead session) are absent, so the client keeps them queued to retry on a later drain (fail-OPEN). |
| `validation_result` | websocket_routes.py (section_complete / form_complete / validate_windows arms, async) | B / jnjj.17 (B5), async since W1 / bd polyglot-pdf-xbl2, REPORT-ONLY since W3 / bd polyglot-pdf-pr3i. The validator verdict for a boundary: `{type, conflicts}` (clean = `[]`). W3: this is REPORT-ONLY -- it no longer injects a steer; a conflict is a CANDIDATE the client ENQUEUES into its validatorFindingsQueue and drains via `drain_findings`. Each conflict now also carries a `field_names` id->name rider for the drain payload. Pushed from a background task AFTER the boundary's `*_ack`. Payload shape -> [validation-delegation.md](validation-delegation.md) (F3, contract 1). |
| `disclaimer_read_initiated` | websocket_routes.py:470 | Disclaimer read started; carries `language`. |
| `language_changed` | websocket_routes.py:535 | Fill language changed. |
| `spoken_language_changed` | websocket_routes.py | Ack of the re-assertion opener; the language did NOT change (see `change_spoken_language`). |
| `pong` | websocket_routes.py:355 | Liveness reply to a client `ping`; echoes `ts`. |
| `stats` | websocket_routes.py:357 | Reply to a client `stats` request (`{message: "ok"}`). |
| `error` | many sites | Error with `code` (+ `reason`/`message`). |

### Frontend -> backend

Built/sent in `webFormConnection.ts`; dispatched on `obj.get("type")` in
`websocket_routes.py` (lines 352-701).

| Type | Send site | Purpose |
|------|-----------|---------|
| `handshake` / `handshake_jit` | schemaFormState.ts:626 / :681 | Initial + section-switch handshake (see above). |
| `form_state` | webFormConnection.ts:2677 | Push current form state; backend replies `form_state_ack`. |
| `form_state_response` | webFormConnection.ts:1058 | Reply to backend `get_form_state`. Each `field_values[id]` entry carries `{value, confirmed, shown}`. `shown` (bd polyglot-pdf-p68s / jnjj.45d) is the field's current applicability, computed client-side via `shouldShowField` (the backend is stateless and cannot derive it); it feeds the secretary's `shown_map` so a value-bearing-but-now-hidden field is distinguishable from a visible one. An older client that omits `shown` leaves the field out of `shown_map` (renderer default = shown). |
| `next_field_hint` | websocket_routes.py:370 | Client-pushed next-field hint (distinct from the `get_next_field_hint` request/`next_field_hint_response` reply pair). No live FE sender today (the FE only sends `next_field_hint_response`; caught by the ceyt contract tests) -- the arm is retained for back-compat. |
| `next_field_hint_response` | webFormConnection.ts:1103 | Reply to backend `get_next_field_hint`. |
| `read_disclaimer` | websocket_routes.py:594 (sent connection.ts:964) | Client signals the disclaimer is being read; backend replies `disclaimer_read_initiated`. Carries `spoken_language` + `disclaimer_text` + optional `agree_button_label` (bd polyglot-pdf-s863) -- the TRANSLATED on-screen agree-button label (DisclaimerModal BUTTON_TRANSLATIONS), so the voice model names the button the user actually sees; the backend falls back to 'I Agree' when absent (old clients). |
| `restart_gemini_session` | websocket_routes.py:566 (sent connection.ts:479) | Client asks the backend to restart the Gemini session; backend replies `gemini_session_restarted`. |
| `section_completed` | websocket_routes.py:637 | LEGACY reactive section-complete signal; backend replies `section_completed_ack`. No live FE sender today (the FE drives section completion via the confirm handler) -- the arm is retained for back-compat. DISTINCT from the proactive `section_complete` below -- do not conflate. |
| `section_complete` | webFormConnection.ts:1616 (confirm handler) | B / jnjj.16 (B4). Proactive section-complete event: emitted the moment the last field of the current section is confirmed (a next section exists). Carries `section_id` + the contract-2 `fields` payload; backend replies `section_complete_ack`. Payload shape: [validation-delegation.md](validation-delegation.md) contract 4. |
| `form_complete` | webFormConnection.ts:1953 (confirm handler + manual-edit path) | B / jnjj.16 (B4). Proactive form-complete event: emitted once when the whole form is confirmed, re-emitted after a post-completion edit (client-side once-only + dirty guard). Carries the whole-form contract-2 `fields`; backend replies `form_complete_ack`. Payload shape: [validation-delegation.md](validation-delegation.md) contract 4. |
| `validate_windows` | webFormConnection.ts (maybeEmitValidateWindows, on the confirm/skip/edit seams) | W2 / bd polyglot-pdf-kxkw (backend arm W1 / xbl2). Async STRIDE validator trigger: carries `windows` -- a list of overlapping contract-2 field lists (size ~20, stride ~10 over SCHEMA FIELD ORDER). PAGE-AGNOSTIC (report-cadence revision 2026-07-13): the client emits a window once every field it covers is SETTLED (confirmed/skipped/not-applicable), keyed on schema order + the settled flags, NEVER pdf_position.page -- so a source:"web" / pageless form emits identically to a paginated one. Backend acks `validate_windows_ack` immediately and runs every window's flash-lite pass CONCURRENTLY off the receive loop, dedupes conflicts across the batch by field-id set, then pushes one `validation_result` (REPORT-ONLY since W3 -- it does NOT inject a steer; the client enqueues + drains). |
| `drain_findings` | webFormConnection.ts (drainFindings, on a non-empty validatorFindingsQueue) | W3 / bd polyglot-pdf-pr3i. The FINDING-DRIVEN drain: emitted the moment the client's queue is non-empty (a report-only `validation_result` enqueued a conflict) and on reconnect if a queue survived. Carries `conflicts` -- each `{field_ids, reason, field_names}` (field_names = the id->name map the steer composer needs). Backend acks `drain_findings_ack`, composes ONE steer (the oiok navigate/read-back/correct composer) off the receive loop, injects it, and pushes `drain_findings_result` with the delivered conflicts. |
| `client_diagnostic` | webFormConnection.ts (handleSessionReady, field-1 opener skip branch) | bd polyglot-pdf-xp4q. ONE-WAY, PII-free client-side diagnostic (no ack, no reply). Emitted when the field-1 opener auto-send was EXPECTED (a section-switch session_ready -- the post-I-Agree switchToFirstSection path is the primary producer -- or an accepted-disclaimer reconnect) but did NOT fire, naming the failing gate condition. Carries `event` (string token: `field1_opener_skipped`, or `section_switch_watchdog_timeout` when a switch never reached session_ready -- so an ABSENT opener diagnostic plus this token means 'failed before the gate', not 'no bug') + seven booleans: `was_section_switch`, `disclaimer_accepted`, `has_selected_language`, `has_next_field_hint`, `is_form_complete` (disambiguates the benign completed-form reconnect -- nothing left to ask, hint correctly empty -- from a genuinely broken opener), `storage_disclaimer_accepted` (persisted flag alongside the in-memory one the gate read: a divergence names the state-staleness hypothesis in one glance), and `continuous_session` (which scoping applies to the hint: section vs whole-form). Deploy-skew: an OLD backend answers with the `unknown_control` error ack, which the client explicitly tolerates (handleServerError early-out) -- that ack is non-fatal by definition and must never end a session or fail a switch. Backend logs a WHITELISTED `client_diagnostic` warning (never echoes arbitrary payload keys/values) and continues. The very first connect of a session (no switch, disclaimer not yet accepted) is a legitimate skip and emits nothing. |
| `section_info_response` | webFormConnection.ts:1176 (+others) | Reply with section metadata. |
| `confirm_field_response` | webFormConnection.ts:2147 | Reply to backend `confirm_field`. Carries `recorded` (+ optional `reason`), and -- when this confirm completed a section that has a NEXT section to advance to -- an optional `section_complete: true` flag so the backend skips the next-field-hint round-trip that would race the FE's `switchToSection` teardown (bd polyglot-pdf-njvh). This is a SUB-FIELD of the confirm reply, distinct from the SI-reduction epic's planned top-level `section_complete` event (see `section_completed` above + the reserved extension points). |
| `skip_field_response` | webFormConnection.ts:2424 | Reply to backend `skip_field` (bd polyglot-pdf-7yra). Same shape as `confirm_field_response`: `recorded` (+ optional `reason`, e.g. `unknown_field`/`already_filled`), and an optional `section_complete: true` when the skip completed a section with a next one to advance to. A skipped field satisfies the section, so a section-completing skip advances identically to a confirm. |
| `switch_field_response` | webFormConnection.ts:2052 (+failure sites) | Reply to backend `switch_field` (bd polyglot-pdf-jnjj.36). `found` plus outcome keys: success carries `field_id`, `spoken_name`, `next_field_hint`, `already_confirmed`, `has_value` (+ `value` when filled, so the model can read it back -- same Gemini trust boundary as `ask_secretary`; + `next_field_schema` in DTI mode, the guidance/validation source). Failure carries a fixed `reason` token: `unknown_field`, `hidden` (conditionally inactive), or `other_section` (+ `section_label`/`section_order` so the model can `switch_section` first in section-scoped modes). |
| `manual_field_update` | webFormConnection.ts:2468 | User edited a field directly. Carries `next_field_hint` and -- in DTI mode -- an optional `next_field_schema` (the next unconfirmed field's full schema, no user values), so the backend can re-establish the DTI current-field coercion pointer + validation entry that the edit's pointer-clear would otherwise strand (a manual edit skips the `confirm_field` round-trip that normally carries the next schema; bd polyglot-pdf-ezg2). Both computed from the POST-edit persisted state. |
| `manual_section_switch` | webFormConnection.ts:3109 | User-initiated section switch. |
| `completion_message` | webFormConnection.ts:2166 (+others) | Form/section completion message to the AI. |
| `recovery_prompt` | webFormConnection.ts:2574 | Escalating recovery prompt (level 1-3). |
| `change_fill_language` | webFormConnection.ts:2609 | Change the AI fill language. |
| `change_spoken_language` | webFormConnection.ts (session_ready opener) | MISNOMER -- does NOT switch language. The spoken language is PINNED per session; this RE-ASSERTS the same pinned language on a fresh Gemini session after a socket teardown (reconnect / section switch), so the backend re-sends the initiating message. See [voice-and-vad.md](voice-and-vad.md) ("the spoken language is pinned per session"); bd polyglot-pdf-87a9. |
| `vad_activity_start` / `vad_activity_end` | webFormConnection.ts:2510 / :2537 | Manual activity signals (non-native-VAD mode). |
| `clear_thinking` | webFormConnection.ts:2245 / :2768 | Thinking-indicator desync guard (bd polyglot-pdf-wpw.5, Codex PR #273): sent when the client's max-duration safety timer fires or on a server error, so the backend resets its `_processing_active` state too (else it stays stuck True and dedups the next turn's `agent_processing:true`). Backend handler `clear_processing_state` (websocket_routes.py:525); fire-and-forget, no ack. |
| `end_gemini_session` | webFormConnection.ts:2592 | Ask the backend to end the Gemini session. |
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
> is removed. The frontend's default-ignore path (`webFormConnection.ts:642-644`)
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
   (`schemaFormState.ts`) omit it; the backend reads it (`websocket_routes.py:845`)
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
   (`websocket_routes.py:849, 852`) and now stores `form_title` into
   `schema["form_metadata"]`. The legacy builder always sent `previous_spoken_names`
   (`schemaFormState.ts:639`); the JIT builder now matches (`schemaFormState.ts:701`).

3. **`field_update` is a frontend RECEIVE handler with no backend sender.** The
   frontend switches on `case "field_update"` (`webFormConnection.ts:531` ->
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
