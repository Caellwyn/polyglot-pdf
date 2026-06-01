# Stateless architecture

*Last updated: 2026-06-01. See [journal/entries/2026-06-01-bd-gfb.4-rename-section-state-vars-mis-named-part-to.md](../journal/entries/2026-06-01-bd-gfb.4-rename-section-state-vars-mis-named-part-to.md) for closeout details.*

**Tracks:** `backend/services/form_filling_service.py` `backend/routes/websocket_routes.py` `frontend/src/schema-forms/state/schemaFormState.ts` `frontend/src/webFormConnection.ts` `frontend/src/shared/connection.ts`

The load-bearing invariant of polyglot-pdf: **the client is the single source of
truth for form field values; the backend is stateless with respect to them.**
Cross-cutting -- read before adding any server-side storage, cache, or log that
might touch field data. Related: [`hipaa-pii-policy.md`](hipaa-pii-policy.md)
(planned, `polyglot-pdf-b11`), [`terminology.md`](terminology.md) (form-session
vs session).

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
   `fill_language`, the persistent `form_session_id`, and section metadata
   (`section_number`/`section_label`, `total_sections`, `previous_spoken_names`).
   The warm-reconnect frame (`getHandshakePayload`/`getJITHandshakePayload`, sent on
   every connect) stops there; `section_id` and `initial_field_hint` are sent only on
   the explicit section-switch/`startSection` handshake, though the backend reads
   them whenever present.
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
- **Never log field values / PII / PHI server-side.** Log ids, types, counts,
  timings (see [`logging-and-cost.md`](logging-and-cost.md), planned `polyglot-pdf-m8s`).
- **Treat `current_values` as ephemeral context, not storage.** It's an input to
  prompt-building, consumed and dropped within the connection.
- **Clearing state is a client concern.** `SchemaFormStateManager.clear()`
  (`sessionStorage.removeItem("schema_form_state")`) wipes the only durable copy;
  there is nothing server-side to also clear. Note `clear()` does **not** fire the
  `schemaFormStateChange` event that `save()` does -- it's a silent wipe, so any
  clear-on-logout/idle feature must also refresh the UI itself.
