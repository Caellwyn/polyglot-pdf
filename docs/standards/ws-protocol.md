# WebSocket protocol -- frozen handshake + message-type contract

**Tracks:** backend/routes/websocket_routes.py frontend/src/webFormConnection.ts frontend/src/schema-forms/state/schemaFormState.ts

*Last updated: 2026-06-29. The proactive `section_complete` / `form_complete` events (Pillar B, B4) are now LIVE -- the frontend emits them at section/form boundaries and the backend acks them (`section_complete_ack` / `form_complete_ack`); the validator round-trip on top is B5. See [../journal/entries/2026-06-29-bd-jnjj.16-proactive-complete-events.md](../journal/entries/2026-06-29-bd-jnjj.16-proactive-complete-events.md) for B4 closeout details.*

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
`backend/routes/websocket_routes.py` (extraction at lines 645-700; dispatched
into `_handle_fill_session` at lines 750-767). It branches on `type` into two
modes -- **legacy** (full section schema) and **JIT** (manifest + first field).

### Mode selector + shared keys

| Key | Type | Mode | Meaning |
|-----|------|------|---------|
| `type` | `"handshake"` \| `"handshake_jit"` | both | Selects mode. `handshake_jit` -> JIT mode (line 648). Anything else (incl. missing) -> legacy. |
| `form_session_id` | string | both | Persistent, frontend-managed ID; survives reconnects. Logging/metrics correlation only -- never used for server-side state (line 651). |
| `current_values` | object (field_id -> FieldValue) | both | Pre-filled values for reconnect; defaults to `{}` (line 683). |
| `full_schema` | object (`{source, fields, sections, parts, ...}`) \| absent | both | The WHOLE form schema (all parts/sections/fields), for the secretary catalog (bd polyglot-pdf-p68s / jnjj.45d). Distinct from `schema`/`manifest`, which carry only the CURRENT section. The backend caches it in-session in `FormFillingService._full_schema` and `handle_ask_secretary` renders the secretary's static catalog from it; preserved across same-form section switches. Schema only -- no PII; rebuilt from this on every (re)connect (stateless invariant). Optional: an older client that omits it makes the secretary fall back to the per-section `schema`. |
| `fill_language` | string | both | Language the AI fills/speaks in; defaults to `"English"` (line 684). |
| `section_number` | int (1-indexed) | both | Current section order (line 688). |
| `section_label` | string | both | Display label for the current section (line 689). |
| `total_sections` | int | both | Section count (line 690). |
| `section_id` | string \| null | both* | Section ID, e.g. `"part_1_2_addresses"` (line 687). Used for the token-log context. *See DRIFT note below -- the primary builder does NOT send it. |
| `previous_spoken_names` | string[] | both | Spoken names from completed sections; defaults to `[]` (line 691). Sent by both builders (the JIT builder since A2). |
| `initial_field_hint` | string \| null | both | First-unfilled-field hint computed by the frontend; `null` when the form is complete (line 694). Sent by both builders (the JIT builder since A2, gap D-hint). |
| `resume` | bool | both | Reconnect flag. Read as `is_reconnect` (line 698); suppresses the greeting/section-intro on a mid-section reconnect (bd polyglot-pdf-vmxx). |

### Legacy-mode keys (`type: "handshake"`)

| Key | Type | Meaning |
|-----|------|---------|
| `schema` | object (`{source, fields, sections, ...}`) | The WHOLE current section's schema. Required; an invalid/missing `schema` closes the socket with `invalid_schema` (lines 676-681). `schema.source` must be `"web"` or `"pdf"` (lines 700-706). |

### JIT-mode keys (`type: "handshake_jit"`)

| Key | Type | Meaning |
|-----|------|---------|
| `manifest` | `HandshakeManifest` | The frontend builds it as `{current_section, previous_sections, parts}` (`frontend/src/schema-forms/utils/manifestUtils.ts:35-41`) -- NOT a top-level `fields` array. The backend stores the whole object and (since A2, bd polyglot-pdf-jnjj.9) CONSUMES `manifest.current_section.fields` + `manifest.previous_sections` to build the JIT `{manifest_text}` and progress count, plus `manifest.parts` for the section nav list. Manifest field-entry shape is owned by [si-reduction.md](si-reduction.md). |
| `first_field_schema` | object \| null | Full schema for the FIRST-UNFILLED field of the section (selected via `computeNextField`, A2 gap D), not the positional first field. The backend renders this as `{next_field_schema}` -- in JIT mode it holds no other field's full schema. |
| `loaded_field_ids` | string[] | Field IDs whose full schema the client has already sent to Gemini; defaults to `[]`. The backend seeds its de-dup set from this at session start so schemas are not re-sent across reconnects (A2 gap L). |
| `form_title` | string | The form's display title (`schema.form_metadata.title`). Added by A2 (gap O) so the JIT SI's `{form_title}` is the real form, not the literal "Form"; the backend stores it into `schema["form_metadata"]["title"]`. |

In JIT mode `schema` is synthesized backend-side from `manifest` +
`first_field_schema` (lines 661-669), so the legacy `schema` key is absent.

### Handshake acknowledgement (backend -> frontend)

The backend replies with `session_ready` (lines 738-748):

| Key | Type | Meaning |
|-----|------|---------|
| `type` | `"session_ready"` | Handshake accepted; session live. |
| `session_id` | string | Ephemeral, connection-scoped (`web_<token>`); logging only, never persisted. |
| `ephemeral` | bool (`true`) | Signals the client the backend is stateless. |
| `jit_mode_enabled` | bool | Mirrors backend `USE_JIT_SCHEMA`; tells the client which handshake mode to build next time. |
| `native_vad` | bool | Mirrors `not DISABLE_GEMINI_VAD`; when true the client streams continuous audio and stops sending manual activity signals (bd polyglot-pdf-333). |

---

## Current state: the message-type union

After the handshake, control messages flow both ways as JSON objects keyed by
`type`. (Audio is a separate binary framing, not part of this union.)

### Backend -> frontend

Sent via `send_json` in `backend/services/callback_handler.py`,
`backend/services/form_filling_service.py`,
`backend/services/request_coordinator.py`, and
`backend/routes/websocket_routes.py`. The frontend switches on `message.type` in
`webFormConnection.ts` (lines 392-540).

| Type | Source | Purpose |
|------|--------|---------|
| `session_ready` | websocket_routes.py:740 | Handshake ack (see above). |
| `form_updated` | callback_handler.py:106 | A field value changed; carries `data` payload. |
| `transcript` | callback_handler.py:136 | AI/user transcript text. |
| `turn_complete` | callback_handler.py:143 | Gemini finished speaking; feeds the activity watchdog. |
| `go_away` | callback_handler.py:189 | Gemini Live server will terminate soon; carries `time_left` (bd polyglot-pdf-c5t). Reconnect is wanted. |
| `idle_timeout` | websocket_routes.py:241 | Backend closing for inactivity; client must NOT auto-reconnect. |
| `section_switched` | form_filling_service.py:738 | Same-socket section switch completed. |
| `gemini_session_restarted` | websocket_routes.py:490 | Gemini session restarted successfully. |
| `gemini_session_ended` | websocket_routes.py:477 | Gemini session ended. |
| `get_form_state` | request_coordinator.py:165 | Backend asks the client for current form state. |
| `get_next_field_hint` | request_coordinator.py:230 | Backend asks the client to compute the next-field hint. |
| `get_field_value` | request_coordinator.py:373 | Backend asks the client for a field value. |
| `confirm_field` | request_coordinator.py:302 | Backend asks the client to confirm a field. |
| `prepare_section_switch` | request_coordinator.py:445 | Backend asks the client to pre-stage a section switch. |
| `form_state_ack` | websocket_routes.py:296 | Ack of a client `form_state`; carries `applied_fields`. |
| `hint_ack` | websocket_routes.py:309 | Ack of a client `next_field_hint`. |
| `completion_ack` | websocket_routes.py:408 | Ack of a client `completion_message`. |
| `recovery_prompt_ack` | websocket_routes.py:422 | Ack of a client `recovery_prompt`. |
| `section_completed_ack` | websocket_routes.py:560 | Ack of a client `section_completed` (legacy reactive). |
| `section_complete_ack` | websocket_routes.py (section_complete arm) | B / jnjj.16 (B4). Ack of the proactive `section_complete` event. |
| `form_complete_ack` | websocket_routes.py (form_complete arm) | B / jnjj.16 (B4). Ack of the proactive `form_complete` event. |
| `disclaimer_read_initiated` | websocket_routes.py:392 | Disclaimer read started; carries `language`. |
| `language_changed` | websocket_routes.py:449 | Fill language changed. |
| `spoken_language_changed` | websocket_routes.py:464 | Spoken language changed. |
| `pong` | websocket_routes.py:285 | Liveness reply to a client `ping`; echoes `ts`. |
| `stats` | websocket_routes.py:287 | Reply to a client `stats` request (`{message: "ok"}`). |
| `error` | many sites | Error with `code` (+ `reason`/`message`). |

### Frontend -> backend

Built/sent in `webFormConnection.ts`; dispatched on `obj.get("type")` in
`websocket_routes.py` (lines 282-568).

| Type | Send site | Purpose |
|------|-----------|---------|
| `handshake` / `handshake_jit` | schemaFormState.ts:604 / :636 | Initial + section-switch handshake (see above). |
| `form_state` | webFormConnection.ts:2018 | Push current form state; backend replies `form_state_ack`. |
| `form_state_response` | webFormConnection.ts:812 | Reply to backend `get_form_state`. Each `field_values[id]` entry carries `{value, confirmed, shown}`. `shown` (bd polyglot-pdf-p68s / jnjj.45d) is the field's current applicability, computed client-side via `shouldShowField` (the backend is stateless and cannot derive it); it feeds the secretary's `shown_map` so a value-bearing-but-now-hidden field is distinguishable from a visible one. An older client that omits `shown` leaves the field out of `shown_map` (renderer default = shown). |
| `next_field_hint` | websocket_routes.py:300 | Client-pushed next-field hint (distinct from the `get_next_field_hint` request/`next_field_hint_response` reply pair). |
| `next_field_hint_response` | webFormConnection.ts:835 | Reply to backend `get_next_field_hint`. |
| `read_disclaimer` | websocket_routes.py:377 (sent connection.ts:844) | Client signals the disclaimer is being read; backend replies `disclaimer_read_initiated`. |
| `restart_gemini_session` | websocket_routes.py:480 (sent connection.ts:464) | Client asks the backend to restart the Gemini session; backend replies `gemini_session_restarted`. |
| `section_completed` | websocket_routes.py:619 | LEGACY reactive section-complete signal; backend replies `section_completed_ack`. No live FE sender today (the FE drives section completion via the confirm handler) -- the arm is retained for back-compat. DISTINCT from the proactive `section_complete` below -- do not conflate. |
| `section_complete` | webFormConnection.ts (confirm handler) | B / jnjj.16 (B4). Proactive section-complete event: emitted the moment the last field of the current section is confirmed (a next section exists). Carries `section_id` + the contract-2 `fields` payload; backend replies `section_complete_ack`. Payload shape: [validation-delegation.md](validation-delegation.md) contract 4. |
| `form_complete` | webFormConnection.ts (confirm handler + manual-edit path) | B / jnjj.16 (B4). Proactive form-complete event: emitted once when the whole form is confirmed, re-emitted after a post-completion edit (client-side once-only + dirty guard). Carries the whole-form contract-2 `fields`; backend replies `form_complete_ack`. Payload shape: [validation-delegation.md](validation-delegation.md) contract 4. |
| `section_info_response` | webFormConnection.ts:907 (+others) | Reply with section metadata. |
| `field_value_response` | webFormConnection.ts:1147 | Reply to backend `get_field_value`. |
| `confirm_field_response` | webFormConnection.ts:1536 | Reply to backend `confirm_field`. Carries `recorded` (+ optional `reason`), and -- when this confirm completed a section that has a NEXT section to advance to -- an optional `section_complete: true` flag so the backend skips the next-field-hint round-trip that would race the FE's `switchToSection` teardown (bd polyglot-pdf-njvh). This is a SUB-FIELD of the confirm reply, distinct from the SI-reduction epic's planned top-level `section_complete` event (see `section_completed` above + the reserved extension points). |
| `manual_field_update` | webFormConnection.ts:1828 | User edited a field directly. |
| `manual_section_switch` | webFormConnection.ts:2375 | User-initiated section switch. |
| `completion_message` | webFormConnection.ts:655 (+others) | Form/section completion message to the AI. |
| `recovery_prompt` | webFormConnection.ts:1915 | Escalating recovery prompt (level 1-3). |
| `change_fill_language` | webFormConnection.ts:1950 | Change the AI fill language. |
| `change_spoken_language` | webFormConnection.ts:540 | Change the disclaimer/spoken language. |
| `vad_activity_start` / `vad_activity_end` | webFormConnection.ts:1851 / :1878 | Manual activity signals (non-native-VAD mode). |
| `end_gemini_session` | webFormConnection.ts:1933 | Ask the backend to end the Gemini session. |
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
| `validation_result` | backend -> frontend | B / bd polyglot-pdf-jnjj.17 (B5) | RESERVED. Cheap-model validator verdict pushed to the client (for UI surfacing). Full envelope (`{type, conflicts}`) -> [validation-delegation.md](validation-delegation.md) (F3). |

> **The validator STEER is NOT a WS message type.** When a conflict is found, the
> correction directive is injected **backend -> Gemini Live session** as a text turn
> (the live model voices it), NOT sent to the browser -- see
> [validation-delegation.md](validation-delegation.md) (F3, "Steering directive").
> An earlier draft wrongly reserved a `validator_steer` backend->frontend type; it
> is removed. The frontend's default-ignore path (`webFormConnection.ts:489-491`)
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

Pillar A's wire surface already exists: the JIT-mode `manifest` +
`loaded_field_ids` handshake keys above. A may EXTEND the `manifest` shape, but
that shape is owned by [si-reduction.md](si-reduction.md) (the F1 contract) --
reference it, do not redefine the manifest here. No new top-level handshake key
or message type is reserved for A beyond the existing JIT keys.

---

## DRIFT flags (frontend/backend name verification)

Exit-criterion 3 requires confirming the frontend and backend field names match.
They match on every key the backend reads, with these real gaps found while
verifying:

1. **`section_id` is read by the backend but NOT sent by the primary handshake
   builders.** `getHandshakePayload` / `getJITHandshakePayload`
   (`schemaFormState.ts`) omit it; the backend reads it (`websocket_routes.py:687`)
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
   (`websocket_routes.py:691, 694`) and now stores `form_title` into
   `schema["form_metadata"]`. The legacy builder always sent `previous_spoken_names`
   (`schemaFormState.ts:611`); the JIT builder now matches.

3. **`field_update` is a frontend RECEIVE handler with no backend sender.** The
   frontend switches on `case "field_update"` (`webFormConnection.ts:397` ->
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
