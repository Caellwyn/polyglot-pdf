# Confirmation & audit trail

**Tracks:** backend/utils/confirmation_logger.py backend/services/callback_handler.py

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
absent) and makes a **synchronous** confirm round-trip to the frontend (bd
polyglot-pdf-wpw.2): the frontend acks whether it actually recorded the
confirmation. `log_field_confirmation(...)` is called **only on a recorded ack**
(and only when a `form_id` and `form_session_id` are present) — a confirm that did
not take (empty field, or a client timeout) is NOT logged, since no confirmation
happened. See [tool-call-flow.md](../components/tool-call-flow.md) for the full
ack flow.

In DTI mode (`USE_DTI`, bd polyglot-pdf-h1bn), the `field_id` used for the confirm
round-trip and the logged event is not always the raw tool argument: if the model
confirms a hallucinated, drifted, or empty id, the handler coerces it onto the
service's current-field pointer before doing anything else with it, mirroring the
same coercion `update_form_fields` applies. The coerced, schema-validated id is
what gets logged — never the raw model-supplied id, which is untrusted tool input
that can carry the user's spoken answer if the model swaps arguments.

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
  "kit_id": "i-90",
  "edition_date": "01/20/25",
  "form_session_id": "fss_abc123_xyz789",
  "field_id": "p1_line1_aliennumber",
  "field_name": "p1_line1_aliennumber",
  "confirmation_method": "verbal"
}
```

**Why three identity fields, not one** (bd `polyglot-pdf-47r3`). `form_id` is a
form NUMBER and identifies neither of the things a liability record needs:

- **`kit_id`** -- `form_number` is **not unique**. Two kits can carry the same
  one (a standard W-7 and a firm-specific variant, which the firm-tier epic
  anticipates via per-firm proprietary forms), so only the kit key distinguishes
  them.
- **`edition_date`** -- agencies revise forms and enforce edition dates. Without
  it, a form filled against the 12/2024 W-7 and one filled after a later
  revision read identically, and a disputed filing cannot answer "which edition
  did the client confirm against?".

`edition_date` comes from `form_metadata.edition_date`, **never**
`form_metadata.version`: `version` is a schema-AUTHORING field whose values
differ in meaning per kit (`"v9_conformant"` = extraction output format,
`"draft"` = kit status), so recording it would put a version-shaped field with
per-kit semantics into a legal record. Both keys are always written (as `null`
when unavailable) so every record has a uniform shape and a missing value reads
as "not recorded" rather than as a different edition.

**Both are established once per form-session and PRESERVED across section
switches.** The internal section-switch restart re-enters `start_session` with
only the new section's schema, so `FormFillingService` keeps `self._kit_id` /
`self._edition_date` rather than re-deriving them (same pattern as
`_form_session_id` and `_full_schema`). Without that, `kit_id` reset to `null`
after section 1 and the fingerprint was recomputed from a single-section schema
-- so the "pinned" marker changed mid-session, which is the opposite of pinning
(caught in review on bd `polyglot-pdf-47r3`; pinned by
`test_switch_to_section_preserves_kit_id_and_edition_in_callback_handler`).

### Kits with no government edition

A **custom form** -- a firm's own intake sheet, which the firm-tier epic
(`polyglot-pdf-02ye`) exists to support -- has no government edition date, so
requiring one would make the product unusable for those customers.

`resolve_edition_marker` (`backend/utils/confirmation_logger.py`) resolves the
marker in **three** ranks, best source first:

1. **`form_metadata.edition_date`** -- the government's own marker
   (`"12/2024"`). The only one an agency recognizes, so it always wins.
2. **`form_metadata.author_version`** -- what the kit author typed when
   publishing a form that has no government edition (bd `polyglot-pdf-xzw5`),
   e.g. `"2026-08-07"`. Human-readable, which is the whole reason it outranks
   the fingerprint below. Never invented: it is recorded only when an author
   actually supplied one.
3. **A short fingerprint of the kit's answerable shape** -- field ids + types +
   option values, formatted `sha256:<12 hex>`. It deliberately excludes labels
   and guidance prose, so a copy edit does not read as a new revision while
   adding/removing/retyping a field or changing an option value does. Not
   human-readable, but it answers the question a disputed filing actually asks:
   *was this the same version of the form the client saw?*

Two properties of `author_version` matter for the audit trail:

- **It is required to publish a kit that has no `edition_date`.** The publish
  gate refuses with an `AUTHOR_VERSION_REQUIRED:`-prefixed 422, which the editor
  keys on to open its version dialog (the catalogue listing does not read kit
  schemas, so the server is what knows a version is needed).
- **It is immutable once published.** It is what existing confirmation records
  name, so changing it would silently re-point them at a revision those clients
  never saw -- the same hazard the retired-kit write-lock exists to prevent
  (bd `polyglot-pdf-6dz0`). A republish keeps the original; a changed value is a
  409. A new revision gets a new version.

**Deleting a kit is guarded by these records** (bd `polyglot-pdf-6x1j`).
`DELETE /api/editor/kits/{kit_id}` is author-only and removes the kit *and its
revision archive*, so it asks first: any confirmation event naming the kit ->
409 offering unpublish instead. Crucially, a check that CANNOT RUN is also a
refusal -- `kit_has_confirmation_records` raises rather than returning False
when the Firestore sink is disabled or its query fails, because the local JSONL
fallback dies with the instance and its silence is not evidence of absence. An
author working locally against the shared bucket would otherwise read "no
records" and destroy the evidence behind real ones.

`author_version` is NOT `form_metadata.version`, which is auto-extracted display
text and frequently meaningless for this purpose (real shipped values include
`"draft"` and `"v9_conformant"`).

Schema-lint emits `audit-identity-no-edition` as a **WARNING, never an ERROR**,
and it is resolved by EITHER an `edition_date` or an `author_version` -- the
finding is about falling back to an unreadable fingerprint, not about the
government field specifically. The publish gate, not the lint rule, is what
actually requires the version.

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
logging roadmap (see [logging-and-cost.md](logging-and-cost.md), Phase 2).
(The pair previously raised a latent `TypeError` on every call — `**event`
collided with structlog's positional event name; fixed under bd
polyglot-pdf-z2is when the sink tests gave them their first caller, so wiring
them is now safe.)

- `log_form_session_start(form_id, form_session_id, section_id=None)` →
  `form_session_started`.
- `log_form_session_end(form_id, form_session_id, completion_status,
  total_fields_confirmed)` → `form_session_ended` with a confirmed-field **count**
  (no values). `completion_status` is one of `completed` / `abandoned` / `error`.
- `read_confirmation_log(form_session_id)` / `get_confirmation_log_path(...)` read
  back a session's events for review or legal purposes. The operational entry
  point is **`scripts/read_confirmations.py <form_session_id>`** (bd z2is) --
  no HTTP route exposes the trail (deliberate: it needs no unauthenticated
  surface, and the reader needs ADC anyway for the Firestore sink).

## Where it's written

Two sinks (bd polyglot-pdf-z2is):

- **Local JSONL (dev).** One file per form-session:
  `<dir>/<form_session_id>.jsonl`. The directory is resolved per-write by
  `_confirmation_log_dir()`, which reads the `CONFIRMATION_LOG_DIR` env var
  (default `logs/confirmations`) and creates it if needed. Resolving per-call
  (not at import) lets a test fixture point writes at a tmp dir. On Cloud Run
  this file lives on ephemeral tmpfs and dies with the instance — it is a dev
  convenience, **not** the durable record.
- **Firestore mirror (deployed).** When `CONFIRMATION_FIRESTORE_ENABLED=true`
  (set in `deploy-all.sh`'s `BACKEND_ENV`), every event is also written to the
  `confirmation_events` Firestore collection by a fire-and-forget background
  writer (single worker thread; the voice hot path never blocks on the network
  write; failures log `confirmation_firestore_write_failed` at error level —
  loud, never raised). `read_confirmation_log(form_session_id)` prefers
  Firestore when enabled (equality query, sorted client-side — no composite
  index needed) and falls back to the file. If `CONFIRMATION_RETENTION_DAYS`
  is set, each document carries an `expire_at` timestamp for a Firestore TTL
  policy; activating the policy is a deploy-time decision gated on counsel's
  retention answer (bd polyglot-pdf-pol2). `flush_confirmation_sink()` drains
  the queue (wired as a FastAPI shutdown handler in `backend/main.py`).
  Firestore security rules never expose the collection (no matching rule =
  client deny; the backend writes via the Admin SDK, which bypasses rules).

## Why this exists (liability)

For an immigration-form app, a per-field record of "the user confirmed this field,
by this method, at this time" is the liability-protection trail: it shows each
value was user-approved without ever storing the value itself.

## Audit-log hygiene

The confirmation log directory is **not** committed to git, and tests redirect
their writes via `CONFIRMATION_LOG_DIR` so a test run never dirties the tree.
Audit logs are runtime artifacts, not source — keep them out of version control
(this was the subject of bd `polyglot-pdf-0rx`).

*Last updated: 2026-08-07 (bd polyglot-pdf-xzw5: the revision marker gained a
THIRD rank -- an author-supplied `form_metadata.author_version` between the
government `edition_date` and the shape fingerprint, required to publish a kit
that has neither and immutable once published. The "a better fallback is
coming" paragraph described exactly this and is now the shipped behavior above.
Earlier, 2026-08-06: post-merge freshness check against
backend/services/callback_handler.py -- `_handle_confirm_field_tool` (default
`confirmation_method="verbal"`), the `recorded`-guard, and the
`log_field_confirmation(...)` call site (gated on `self._form_id and
self._form_session_id`, carrying `kit_id`/`edition_date`) all re-verified
line-for-line, no drift found).*
