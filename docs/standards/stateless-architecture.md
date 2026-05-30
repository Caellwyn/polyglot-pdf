# Stateless architecture

*Last updated: 2026-05-30. See [journal entries](../journal/entries/) for chronological history.*

**Tracks:** `backend/services/form_filling_service.py` `backend/routes/websocket_routes.py` `frontend/src/schema-forms/state/schemaFormState.ts` `frontend/src/shared/connection.ts`

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

- `backend/services/form_filling_service.py`: *"current_values: Pre-filled values
  (**ignored by backend - client is source of truth**)"* and, repeatedly,
  *"Backend doesn't store current_values"* (the value dict is used only to build
  Gemini's in-memory context for the live turn, then dropped).

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
the backend's working context **from the handshake**:

1. Client opens the WS and sends a `hello`; backend replies `hello_ack`
   (`backend/routes/websocket_routes.py`).
2. Client sends the form **schema**, its current **`current_values`** (the
   `"For reconnect"` payload), the **`fill_language`**, and the persistent
   **`form_session_id`**.
3. Backend calls `update_schema(schema, current_values, fill_language)` purely to
   construct Gemini's context for this connection. The values are **not** stored;
   they shape the live prompt and are discarded.

A reconnect is therefore identical to a first connect with more pre-filled
values -- the backend can't tell (and doesn't need to) whether it has "seen" this
form before. Mid-form section switches reuse the same path (the service rebuilds
context per section from client-supplied `section_values`).

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
- **Clearing state is a client concern.** `sessionStorage.removeItem("schema_form_state")`
  wipes the only durable copy; there is nothing server-side to also clear.
