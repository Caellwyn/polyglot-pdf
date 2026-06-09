# Confirmation & audit trail

**Tracks:** backend/utils/confirmation_logger.py backend/services/callback_handler.py

*Last updated: 2026-06-09*

Every field value that lands on the form is confirmed by the user, and every
confirmation is recorded — by `field_id` and *method*, never by value — for
liability protection and an audit trail.

The privacy rules these logs obey live in [hipaa-pii-policy.md](hipaa-pii-policy.md);
the broader logging/cost picture is in [logging-and-cost.md](logging-and-cost.md).

## The confirmation workflow

A proposed value is not "done" until the user confirms it. Gemini is instructed to
call the `confirm_field` tool after filling each field (the tool is declared in
`backend/config.py`, in the tool-declarations block, with required params `field_id`
+ `confirmation_method`, the latter an enum of exactly two values). `config.py` is
intentionally **not** in this doc's `**Tracks:**` line — it's a large, frequently
churned file (model + pricing config live there too), so tracking it whole flagged
this doc as stale on every unrelated config edit; a real change to the `confirm_field`
tool usually travels with a `callback_handler.py` change (the handler parses its args),
which *is* tracked. **Accepted gap:** the `confirmation_method` enum (`verbal` /
`manual`) is declared *only* in `config.py`'s tool schema, so changing the enum's
allowed values there *without* touching `callback_handler.py` would not re-stamp this
doc (the handler reads the arg without validating against the enum). If you edit that
enum, re-check this section by hand. The two confirmation methods:

- **`verbal`** — the user said "yes" to the proposed value.
- **`manual`** — the user typed/selected the value directly.

`CallbackHandler._handle_confirm_field_tool` (`backend/services/callback_handler.py`)
reads `confirmation_method` from the tool arguments (defaulting to `"verbal"` if
absent), relays a `confirm_field` message to the frontend, and — when a `form_id`
and `form_session_id` are present — calls `log_field_confirmation(...)`.

## What gets recorded

`backend/utils/confirmation_logger.py` — `log_field_confirmation(form_id,
form_session_id, field_id, field_name, confirmation_method)` appends a
`field_confirmed` event to a per-form-session JSONL file and also emits it through
`structlog` (to stdout — this is the third-party `structlog` library, **not** the
project's `StructuredLogger` / the Cloud Run→BigQuery typed-event path described in
[logging-and-cost.md](logging-and-cost.md)). The event:

```json
{
  "timestamp": "<ISO-8601 UTC>",
  "event": "field_confirmed",
  "form_id": "I-90",
  "form_session_id": "fss_abc123_xyz789",
  "field_id": "p1_line1_aliennumber",
  "field_name": "p1_line1_aliennumber",
  "confirmation_method": "verbal"
}
```

Note what is **absent**: the field's value. The module docstring is explicit —
"Only log metadata, NEVER log actual field values or user data." `field_name` is
*meant* to be a human-readable label from the schema (e.g. "Alien Registration
Number"), but the only caller (`_handle_confirm_field_tool`) passes
`field_name=None`, which falls back to the `field_id` — so today the two columns
are always equal (as shown above). Enriching it is a future improvement, not
current behavior.

The `ConfirmationMethod` type is `Literal["verbal", "manual"]`, kept deliberately
in sync with the `confirm_field` tool enum and the values the callback handler
actually writes.

### Other events in the same log

These helpers are **defined but not yet wired** — only `log_field_confirmation`
has a live caller today; the session-lifecycle pair is scaffolding for the
logging roadmap (see [logging-and-cost.md](logging-and-cost.md), Phase 2):

- `log_form_session_start(form_id, form_session_id, section_id=None)` →
  `form_session_started`.
- `log_form_session_end(form_id, form_session_id, completion_status,
  total_fields_confirmed)` → `form_session_ended` with a confirmed-field **count**
  (no values). `completion_status` is one of `completed` / `abandoned` / `error`.
- `read_confirmation_log(form_session_id)` / `get_confirmation_log_path(...)` read
  back a session's events for review or legal purposes.

## Where it's written

One file per form-session: `<dir>/<form_session_id>.jsonl`. The directory is
resolved per-write by `_confirmation_log_dir()`, which reads the
`CONFIRMATION_LOG_DIR` env var (default `logs/confirmations`) and creates it if
needed. Resolving per-call (not at import) lets a test fixture point writes at a
tmp dir.

## Why this exists (liability)

For an immigration-form app, a per-field record of "the user confirmed this field,
by this method, at this time" is the liability-protection trail: it shows each
value was user-approved without ever storing the value itself.

## Audit-log hygiene

The confirmation log directory is **not** committed to git, and tests redirect
their writes via `CONFIRMATION_LOG_DIR` so a test run never dirties the tree.
Audit logs are runtime artifacts, not source — keep them out of version control
(this was the subject of bd `polyglot-pdf-0rx`).

*Last updated: 2026-06-09*
