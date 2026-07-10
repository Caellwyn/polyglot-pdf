# WebSocket protocol -- frozen handshake + message-type contract

**Tracks:** backend/routes/websocket_routes.py frontend/src/webFormConnection.ts frontend/src/schema-forms/state/schemaFormState.ts

*Last updated: 2026-07-09 (bd polyglot-pdf-7yra: new backend->frontend `skip_field` type + frontend->backend `skip_field_response` -- the voice skip_field tool lets the assistant force-skip a required field the user cannot answer, recorded via markFieldSkipped; same round-trip shape as confirm_field. See both tables.). Prior: 2026-07-07 (bd polyglot-pdf-ppfy: new backend->frontend `gemini_session_dropped` type -- a spontaneous Gemini drop (1011) forwarded so the client reconnects and shows the transient recovery modal; see the backend->frontend table). Prior: 2026-07-06 (bd polyglot-pdf-x8rt: `session_ready` gains a `continuous_session_enabled` key -- see the Handshake acknowledgement table). Prior: 2026-07-05 (bd polyglot-pdf-ezg2: `manual_field_update` gains an optional DTI-mode `next_field_schema` rider -- see the client->backend table row). Also 2026-07-05 (bd polyglot-pdf-mpoe staleness sweep: refreshed all `websocket_routes.py`/`webFormConnection.ts`/`schemaFormState.ts` line-number citations, which had drifted from code growth across several intervening commits -- no wire-type or handshake-key name changed; see [../journal/entries/2026-07-05-bd-mpoe-doc-staleness-sweep.md](../journal/entries/2026-07-05-bd-mpoe-doc-staleness-sweep.md)). Prior: 2026-07-02 (bd polyglot-pdf-ceyt: this doc's message-type union is now pinned by contract tests -- backend/tests/contract/test_websocket_protocol.py diffs these tables against the code, so renaming or dropping a wire type fails a test; also documented the previously-missing `dti_mode_enabled` session_ready key those tests caught).*

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
modes -- **legacy** (full section schema) and **JIT** (manifest + first field).

### Mode selector + shared keys

| Key | Type | Mode | Meaning |
|-----|------|------|---------|
| `type` | `"handshake"` \| `"handshake_jit"` | both | Selects mode. `handshake_jit` -> JIT mode (line 780). Anything else (incl. missing) -> legacy. |
| `form_session_id` | string | both | Persistent, frontend-managed ID; survives reconnects. Logging/metrics correlation only -- never used for server-side state (line 783). |
| `current_values` | object (field_id -> FieldValue) | both | Pre-filled values for reconnect; defaults to `{}` (line 830). |
| `full_schema` | object (`{source, fields, sections, parts, ...}`) \| absent | both | The WHOLE form schema (all parts/sections/fields), for the secretary catalog (bd polyglot-pdf-p68s / jnjj.45d). Distinct from `schema`/`manifest`, which carry only the CURRENT section. The backend caches it in-session in `FormFillingService._full_schema` and `handle_ask_secretary` renders the secretary's static catalog from it; preserved across same-form section switches. Schema only -- no PII; rebuilt from this on every (re)connect (stateless invariant). Optional: an older client that omits it makes the secretary fall back to the per-section `schema`. |
| `fill_language` | string | both | Language the AI fills/speaks in; defaults to `"English"` (line 831). |
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

### JIT-mode keys (`type: "handshake_jit"`)

| Key | Type | Meaning |
|-----|------|---------|
| `manifest` | `HandshakeManifest` | The frontend builds it as `{current_section, previous_sections, parts}` (`frontend/src/schema-forms/utils/manifestUtils.ts:35-41`) -- NOT a top-level `fields` array. The backend stores the whole object and (since A2, bd polyglot-pdf-jnjj.9) CONSUMES `manifest.current_section.fields` + `manifest.previous_sections` to build the JIT `{manifest_text}` and progress count, plus `manifest.parts` for the section nav list. Manifest field-entry shape is owned by [si-reduction.md](si-reduction.md). |
| `first_field_schema` | object \| null | Full schema for the FIRST-UNFILLED field of the section (selected via `computeNextField`, A2 gap D), not the positional first field. The backend renders this as `{next_field_schema}` -- in JIT mode it holds no other field's full schema. |
| `loaded_field_ids` | string[] | Field IDs whose full schema the client has already sent to Gemini; defaults to `[]`. The backend seeds its de-dup set from this at session start so schemas are not re-sent across reconnects (A2 gap L). |
| `form_title` | string | The form's display title (`schema.form_metadata.title`). Added by A2 (gap O) so the JIT SI's `{form_title}` is the real form, not the literal "Form"; the backend stores it into `schema["form_metadata"]["title"]`. |

In JIT mode `schema` is synthesized backend-side from `manifest` +
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
| `get_field_value` | request_coordinator.py:386 | Backend asks the client for a field value. |
| `confirm_field` | request_coordinator.py:315 | Backend asks the client to confirm a field. |
| `skip_field` | request_coordinator.py:391 | Backend asks the client to force-skip a required field the user cannot answer (bd polyglot-pdf-7yra). The client records the skip (markFieldSkipped: empty value + skipped flag) and replies `skip_field_response`. |
| `prepare_section_switch` | request_coordinator.py:458 | Backend asks the client to pre-stage a section switch. |
| `form_state_ack` | websocket_routes.py:366 | Ack of a client `form_state`; carries `applied_fields`. |
| `hint_ack` | websocket_routes.py:379 | Ack of a client `next_field_hint`. |
| `completion_ack` | websocket_routes.py:486 | Ack of a client `completion_message`. |
| `recovery_prompt_ack` | websocket_routes.py:500 | Ack of a client `recovery_prompt`. |
| `section_completed_ack` | websocket_routes.py:646 | Ack of a client `section_completed` (legacy reactive). |
| `section_complete_ack` | websocket_routes.py (section_complete arm) | B / jnjj.16 (B4). Ack of the proactive `section_complete` event. |
| `form_complete_ack` | websocket_routes.py (form_complete arm) | B / jnjj.16 (B4). Ack of the proactive `form_complete` event. |
| `validation_result` | websocket_routes.py (section_complete / form_complete arms) | B / jnjj.17 (B5). The validator verdict for the just-emitted boundary: `{type, conflicts}` (conflicts spread at top level; clean = `[]`). Sent for EVERY validated boundary -- the FE's deterministic clean->resume signal for the gated section switch. Payload shape -> [validation-delegation.md](validation-delegation.md) (F3, contract 1). |
| `disclaimer_read_initiated` | websocket_routes.py:470 | Disclaimer read started; carries `language`. |
| `language_changed` | websocket_routes.py:535 | Fill language changed. |
| `spoken_language_changed` | websocket_routes.py:550 | Spoken language changed. |
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
| `read_disclaimer` | websocket_routes.py:455 (sent connection.ts:881) | Client signals the disclaimer is being read; backend replies `disclaimer_read_initiated`. |
| `restart_gemini_session` | websocket_routes.py:566 (sent connection.ts:479) | Client asks the backend to restart the Gemini session; backend replies `gemini_session_restarted`. |
| `section_completed` | websocket_routes.py:637 | LEGACY reactive section-complete signal; backend replies `section_completed_ack`. No live FE sender today (the FE drives section completion via the confirm handler) -- the arm is retained for back-compat. DISTINCT from the proactive `section_complete` below -- do not conflate. |
| `section_complete` | webFormConnection.ts:1616 (confirm handler) | B / jnjj.16 (B4). Proactive section-complete event: emitted the moment the last field of the current section is confirmed (a next section exists). Carries `section_id` + the contract-2 `fields` payload; backend replies `section_complete_ack`. Payload shape: [validation-delegation.md](validation-delegation.md) contract 4. |
| `form_complete` | webFormConnection.ts:1953 (confirm handler + manual-edit path) | B / jnjj.16 (B4). Proactive form-complete event: emitted once when the whole form is confirmed, re-emitted after a post-completion edit (client-side once-only + dirty guard). Carries the whole-form contract-2 `fields`; backend replies `form_complete_ack`. Payload shape: [validation-delegation.md](validation-delegation.md) contract 4. |
| `section_info_response` | webFormConnection.ts:1176 (+others) | Reply with section metadata. |
| `field_value_response` | webFormConnection.ts:1429 | Reply to backend `get_field_value`. |
| `confirm_field_response` | webFormConnection.ts:2147 | Reply to backend `confirm_field`. Carries `recorded` (+ optional `reason`), and -- when this confirm completed a section that has a NEXT section to advance to -- an optional `section_complete: true` flag so the backend skips the next-field-hint round-trip that would race the FE's `switchToSection` teardown (bd polyglot-pdf-njvh). This is a SUB-FIELD of the confirm reply, distinct from the SI-reduction epic's planned top-level `section_complete` event (see `section_completed` above + the reserved extension points). |
| `skip_field_response` | webFormConnection.ts:2424 | Reply to backend `skip_field` (bd polyglot-pdf-7yra). Same shape as `confirm_field_response`: `recorded` (+ optional `reason`, e.g. `unknown_field`/`already_filled`), and an optional `section_complete: true` when the skip completed a section with a next one to advance to. A skipped field satisfies the section, so a section-completing skip advances identically to a confirm. |
| `manual_field_update` | webFormConnection.ts:2468 | User edited a field directly. Carries `next_field_hint` and -- in DTI mode -- an optional `next_field_schema` (the next unconfirmed field's full schema, no user values), so the backend can re-establish the DTI current-field coercion pointer + validation entry that the edit's pointer-clear would otherwise strand (a manual edit skips the `confirm_field` round-trip that normally carries the next schema; bd polyglot-pdf-ezg2). Both computed from the POST-edit persisted state. |
| `manual_section_switch` | webFormConnection.ts:3109 | User-initiated section switch. |
| `completion_message` | webFormConnection.ts:2166 (+others) | Form/section completion message to the AI. |
| `recovery_prompt` | webFormConnection.ts:2574 | Escalating recovery prompt (level 1-3). |
| `change_fill_language` | webFormConnection.ts:2609 | Change the AI fill language. |
| `change_spoken_language` | webFormConnection.ts:701 | Change the disclaimer/spoken language. |
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
