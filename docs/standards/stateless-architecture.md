# Stateless architecture

*Last updated: 2026-08-14 (bd polyglot-pdf-h5v7h: corrected the warm-reconnect
frame claim -- the JIT/DTI builder, the production default, sends
`initial_field_hint` on every connect, not only on a section switch; only the
legacy builder omits it. The `section_id` half of the claim was already
correct and is unchanged. Also current: the client-side two-writer
`fieldValues` reconciliation (React UI + WebFormConnection,
`reconcileFieldValues` in frontend/src/schema-forms/utils/fieldValue.ts, bd
polyglot-pdf-uw3w/3irc/qim7) -- a client-internal consistency mechanism that
does not change the backend-statelessness invariant this doc tracks.)*

**Tracks:** `backend/services/form_filling_service.py` `backend/routes/websocket_routes.py` `frontend/src/schema-forms/state/schemaFormState.ts` `frontend/src/webFormConnection.ts` `frontend/src/shared/connection.ts`

The load-bearing invariant of polyglot-pdf: **the client is the single source of
truth for form field values; the backend is stateless with respect to them.**
Cross-cutting -- read before adding any server-side storage, cache, or log that
might touch field data. Related: [`hipaa-pii-policy.md`](hipaa-pii-policy.md),
[`terminology.md`](terminology.md) (form-session vs session).

## The invariant

Field values, confirmations, and the current/completed **section** state live in
the browser's `sessionStorage` (key `schema_form_state`, managed by
`SchemaFormStateManager` in
`frontend/src/schema-forms/state/schemaFormState.ts`). The backend **never
persists them.** This isn't incidental -- the service says so in its own code:

- `backend/services/form_filling_service.py` says so in its own comments:
  *"current_values: Pre-filled values (**ignored by backend - client is source of
  truth**)"* (in `start_session`) and *"current_values are client-managed, we
  don't store them"* (in `update_schema`). The value dict is used only to build
  Gemini's in-memory context for the live turn, then dropped.

So the only durable copy of a user's answers is in their own browser tab.

**Client-side, `fieldValues` has two writers, reconciled per field.** The
"client is the single source of truth" invariant is about the backend; on the
client itself, `WebFormConnection` holds an in-memory `this.state` across
voice turns while the React UI (`SchemaForm.tsx` `handleFieldChange` /
`handleFieldSkip`) writes straight through `SchemaFormStateManager` to
`sessionStorage` without touching that in-memory copy -- two independent
writers of the same map (bd polyglot-pdf-uw3w / polyglot-pdf-3irc /
polyglot-pdf-qim7). A handler that persists its in-memory copy verbatim would
silently overwrite whatever the UI wrote since the last sync (a value the user
cleared on screen coming back to life, or a deleted `[]`-alias key being
resurrected). `reconcileFieldValues`
(`frontend/src/schema-forms/utils/fieldValue.ts`) is the fix: every
`WebFormConnection` handler that re-derives `this.state` from a freshly-read
`persistedAtEntry` reconciles `fieldValues` per LOGICAL field (collapsing the
`p1_grp` / `p1_grp[]` alias pair into one decision) rather than replacing or
key-unioning the two sides -- the newer `lastModified` stamp wins, ties go to
the persisted side, and an unstamped entry loses to a stamped one. This is a
client-internal consistency mechanism between the UI and the voice-connection
object; it does not change where the durable copy lives (`sessionStorage`) or
who the backend treats as authoritative (still nobody -- the backend stores
none of it either way).

## Why

- **Privacy / HIPAA-PII.** No field values, PII, or PHI at rest server-side means
  the smallest possible blast radius and the simplest compliance story. The
  backend handles values **in memory, in transit** only. (Enforced as policy in
  [`hipaa-pii-policy.md`](hipaa-pii-policy.md); server-side logs carry field
  *ids/types/counts*, never values.)
- **Scale-to-zero economy.** A stateless Cloud Run service can scale to zero
  between sessions with nothing to rehydrate -- cheap for bursty voice traffic.
- **Crash/reconnect resilience.** Because the client owns state, a dropped
  WebSocket or a restarted Gemini session loses nothing: the client re-sends.

## How (re)connect works -- the warm reconnect

There is no server-side session to resume. Every connect, warm or cold, rebuilds
the backend's working context **from the handshake** (`/ws/fill` in
`backend/routes/websocket_routes.py`):

1. The client's **first frame on the socket is the handshake itself** -- a single
   JSON text frame (`receive_text()` -> `json.loads`). There is no separate
   `hello`/`hello_ack` round-trip on `/ws/fill` (that exchange belongs to the
   `/ws/echo` test endpoint, not this one).
2. The handshake's `type` selects the mode: `"handshake"` (legacy -- carries the
   full `schema`) or `"handshake_jit"` (carries a `manifest` +
   `first_field_schema` + `loaded_field_ids` instead, for token-lean loading). It
   also carries `current_values` (the pre-filled answers, used on reconnect),
   `fill_language`, the persistent `form_session_id`, section metadata
   (`section_number`/`section_label`, `total_sections`, `previous_spoken_names`),
   and `resume: boolean` (bd polyglot-pdf-vmxx: `true` on any reconnect after the
   first successful open -- the backend selects a no-greeting resume prompt; the
   stateless invariant holds, as `resume` is a hint, not persisted state).
   The warm-reconnect frame also carries `initial_field_hint` on the JIT/DTI
   builder (`getJITHandshakePayload`, the production default) -- computed and
   sent on every connect, not only a section switch (bd polyglot-pdf-jnjj.9,
   "gap D-hint"). The LEGACY builder (`getHandshakePayload`) omits it, same as
   `section_id`, which neither builder sends on the warm-reconnect frame --
   both instead ride the section-switch paths: the explicit `startSection`
   handshake (top-level keys) and the auto-advance `manual_section_switch`
   frame (nested under `section_info`) — and the backend reads them whenever
   present.
3. The backend extracts those fields, then `update_schema(schema, current_values,
   fill_language)` stores the **schema** and language on the in-memory service
   (`self._schema = schema`) -- but **explicitly not the values** (*"current_values
   are client-managed, we don't store them"*). A separate
   `build_form_context_message(...)` turns the values into Gemini's prompt
   context for this connection; the value dict itself is never persisted. The
   backend replies `{"type": "session_ready"}`.

A reconnect is therefore identical to a first connect with more pre-filled
values -- the backend can't tell (and doesn't need to) whether it has "seen" this
form before. The schema it holds is in-memory and lives only as long as the
connection. Mid-form section switches reuse the same path (context is rebuilt per
section from client-supplied values).

## form-session vs. WS/Gemini session

The persistence boundary is the **form-session**, not the connection. One
`formSessionId` (`fss_*`, see [`terminology.md`](terminology.md)) spans the whole
fill and **survives reconnects**; a `sessionId`/`session_id` is one WS/Gemini
connection and may be replaced several times within a single form-session. State
durability is a property of the form-session (client-side), never the WS session.

## Rules (what this forbids)

- **Never add server-side persistence of field values** -- no DB row, file, cache,
  or in-memory dict that outlives the request handling. If you need a value later,
  the client re-sends it on the next message.
  (Boundary example: the process-level option-label translation cache,
  `backend/services/option_translation.py` (bd polyglot-pdf-ow1e), stores only
  SCHEMA-derived data -- English option labels and their translations, keyed by
  form + language -- never a user's field values, so it does not breach this
  rule. Anything keyed by or containing a USER'S data would.)
- **Never log field values / PII / PHI server-side.** Log ids, types, counts,
  timings (see [`logging-and-cost.md`](logging-and-cost.md)).
- **Treat `current_values` as ephemeral context, not storage.** It's an input to
  prompt-building, consumed and dropped within the connection.
- **The request-use-discard pattern for any handler that needs current field
  state.** `get_form_status`/`validate` and the secretary
  (`FormFillingService.handle_ask_secretary`) all need a fresh read of field
  values mid-session; none of them cache it. `handle_ask_secretary` calls
  `request_form_state_from_client(...)` per invocation and holds the result in a
  local variable only for the duration of that call (building the secretary's
  `context` dict), never assigning it to `self`; the value is gone once the
  handler returns. Follow this pattern for any new handler that needs field
  state -- ask the client, use it, let it fall out of scope.
- **Clearing state is a client concern.** `SchemaFormStateManager.clear()`
  (`sessionStorage.removeItem("schema_form_state")`) wipes the only durable copy;
  there is nothing server-side to also clear. Note `clear()` does **not** fire the
  `schemaFormStateChange` event that `save()` does -- it's a silent wipe, so any
  clear-on-logout/idle feature must also refresh the UI itself.
