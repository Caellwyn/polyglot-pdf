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
  "firm_id": "acme-legal",
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
- **`firm_id`** (bd `polyglot-pdf-xwlt`) -- the CUSTOMER FIRM whose staff ran
  the session, from the `firm_id` custom claim on the verified token (never
  from the handshake, which is client-controlled: a firm id a caller can type
  is not an identity). It names our paying customer so per-firm usage is an
  equality query; it is **not** a client identifier, and the firm tier
  deliberately has none anywhere in this record. `null` for a session with no
  firm claim.

`edition_date` comes from `form_metadata.edition_date`, **never**
`form_metadata.version`: `version` is a schema-AUTHORING field whose values
differ in meaning per kit (`"v9_conformant"` = extraction output format,
`"draft"` = kit status), so recording it would put a version-shaped field with
per-kit semantics into a legal record. Both keys are always written (as `null`
when unavailable) so every record has a uniform shape and a missing value reads
as "not recorded" rather than as a different edition.

**These are established once per form-session and PRESERVED across section
switches.** The internal section-switch restart re-enters `start_session` with
only the new section's schema, so `FormFillingService` keeps `self._kit_id` /
`self._edition_date` / `self._firm_id` rather than re-deriving them (same pattern as
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
3. **A short fingerprint of the kit's answerable shape** -- field ids, types,
   option values (de-duplicated), validation rules, the `required` flag, and
   `pdf_field_name` (bd `polyglot-pdf-8x56`), formatted `sha256:<12 hex>`. It
   deliberately excludes labels and guidance prose, so a copy edit does not
   read as a new revision -- but a tightened/loosened validation rule, a
   flipped `required` flag, adding/removing/retyping a field, changing an
   option value, or remapping which PDF widget a field prints into (the same
   answers now landing on a DIFFERENT printed document) all count as a real
   revision. Not human-readable, but it answers the question a disputed
   filing actually asks: *was this the same version of the form the client
   saw?*

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
refusal -- `kit_has_confirmation_records` raises rather than returning False in
THREE cases:

1. **The sink is disabled** (`CONFIRMATION_FIRESTORE_ENABLED` defaults false).
   The local JSONL fallback dies with the instance, so its silence is not
   evidence of absence -- an author working locally against the shared bucket
   would otherwise read "no records" and destroy the evidence behind real ones.
2. **The query failed.** "Asked and errored" is not "asked and got none".
3. **A record exists that names NO kit** (`kit_id` stored as null). `kit_id` is
   optional end to end, and a Firestore equality filter cannot match a stored
   null -- so a kit-scoped query is BLIND to those records. Reporting "none"
   there would be a silent false safe on a form clients really did confirm
   against. They cannot be attributed to a specific kit, so guessing is
   unavailable and refusing is the honest answer.
4. **A LEGACY record exists that omits `kit_id` entirely.** `IS_NULL` matches a
   stored null, not a MISSING key -- and `field_confirmed` records written
   between the Firestore sink shipping (2026-08-03, bd `polyglot-pdf-z2is`) and
   `kit_id` joining the event dict (2026-08-05, bd `polyglot-pdf-47r3`) have no
   such key. Cases 1-3 all skip them, so a kit whose only records are that
   vintage would report "verified: no records" and be hard-deleted WITH its
   archive.

   **EVERY query in this guard is scoped to `event == "field_confirmed"`**,
   and that scoping is load-bearing. It has to be: since bd
   `polyglot-pdf-xwlt` the session-lifecycle events are live on every voice
   session AND carry a `kit_id`, so an unscoped kit query matches them. When
   only the legacy scan was scoped, a single voice session made its kit
   permanently undeletable, and one session whose `kit_id` was null made
   EVERY kit unverifiable (the stored-null branch fired for any kit id) --
   found and reproduced by the outer cross-surface review, bd
   `polyglot-pdf-68s2q`.

   Three checks, and the first two are **EXHAUSTIVE**: a chained
   `kit_id == <kit> AND event == "field_confirmed"` with `limit(1)`, then the
   same pair with `kit_id == None` for a real confirmation naming no kit.
   Two EQUALITY filters need no composite index -- Firestore serves them by
   merging auto-created single-field indexes (composites are for
   equality+range/order_by) -- and `limit(1)` bounds the RESULT, not the
   search, so neither can miss a record for sitting far down the collection.
   Only the third check, the pre-47r3 MISSING-key sweep, is a bounded sample
   (`_LEGACY_SCAN_LIMIT`), because Firestore cannot query for a missing key
   at all; sampling is defensible there and only there, since that cohort is
   CLOSED -- nothing writes that shape any more.

   An intermediate version of this fix bounded the whole guard and made the
   positive check a 50-document sample, so a busy collection could answer
   "no records" for a kit that had them -- a hard delete of the evidence the
   archive exists to preserve. That is bd `polyglot-pdf-u66ka`, and
   `test_a_confirmation_BEYOND_the_scan_window_is_still_found` is its pin.

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

The session-lifecycle pair is **wired** as of bd `polyglot-pdf-xwlt` — the WS
route (`_handle_fill_session`) is their first and only caller. (They
previously raised a latent `TypeError` on every call — `**event` collided
with structlog's positional event name; fixed under bd polyglot-pdf-z2is.)

- `log_form_session_start(form_id, form_session_id, section_id=None,
  firm_id=None, kit_id=None)` → `form_session_started`, logged once per
  session after the Gemini session starts. A **reconnect does not re-log**:
  `form_session_id` survives reconnects, so re-logging would inflate a
  per-firm session count with what is one session to the user.
- `log_form_session_end(form_id, form_session_id, completion_status,
  total_fields_confirmed, firm_id=None, kit_id=None)` → `form_session_ended`
  with a confirmed-field **count** (no values), logged in the handler's
  `finally` so it records however the socket died. `completion_status` is
  `completed` only when the client sent `form_complete`; otherwise
  `abandoned` (we cannot know the user finished). `error` remains available
  for callers that can distinguish it.

  **ONE ROW PER CONNECTION, not per session** -- unlike the start event, this
  is NOT suppressed on a reconnect. At teardown the backend cannot tell a
  mid-form reconnect from a real exit (the protocol has no terminal-close
  signal), and gating on the resume flag both dropped the real end record for
  any reconnecting session and emitted a false `abandoned` for the connection
  about to resume. So the row is per-connection and **a per-firm SESSION
  count is a DISTINCT count over `form_session_id`** (which survives
  reconnects), never a row count. The decision lives in the named predicates
  `should_log_session_start` / `should_log_session_end`
  (`backend/routes/websocket_routes.py`), whose whole truth table is pinned
  by `test_session_logging_decisions`.
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

## The deployment invariant: DRAFT app, no self-filing, outside reviewer

**This is project-level context, not a footnote.** Three parts, all load-bearing:

1. **This app produces a DRAFT.** It is not a filing tool and does not submit
   anything to any agency.
2. **It is sold to a legal entity** that pre-prepares first drafts for its
   clients. It is **never** used for self-filing.
3. **An outside qualified human reviews the form before it is filed.** Customer
   contracts require it. *That reviewer makes the legal determinations -- the app
   never does.*

### Shipped behavior that DEPENDS on this

This is a deployment precondition, not an aspiration: real behavior is built on
top of it, and would become wrong if it stopped holding.

- **The hedge-and-defer answer policy** (bd `polyglot-pdf-rdsl`). The voice SI's
  ANSWERING QUESTIONS block (`backend/config.py`) tells the model to answer an
  eligibility-shaped question with official text plus its conditions, then close
  by deferring to "the firm or professional reviewing their form." **If the
  product were ever opened to self-filers, demoed to a prospect with no reviewing
  staff, or sold direct-to-consumer, that deferral would point at a person who
  does not exist** -- in every supported language -- and a careful hedge becomes a
  dead end. Nothing in the codebase would object.
- **The user-facing disclaimer** (`DisclaimerModal.tsx`) and its spoken
  counterpart, which set the applicant's expectations about what the draft is.
- **The certification-block position** -- what the app will and will not fill on
  a preparer/interpreter certification.

### The register distinction (do not collapse this)

**The internal invariant and what the app TELLS the applicant are different
statements, deliberately.**

**What SHIPS today -- both user-facing surfaces state the UNDERTAKING, and
they are the same text** (bd `polyglot-pdf-nsb4y`). The modal renders
`intro_script.json`'s paragraphs, and the Live model reads those same
paragraphs joined (`VoiceOverlay.tsx` -> `readDisclaimer` -> the
`read_disclaimer` WS message -> `websocket_routes.py`), so the spoken and
written disclaimers cannot differ: both say *"you agree to review the
completed document yourself and with a certified professional before
filing."* The applicant is asked to undertake that review, and the Agree click
records consent to it.

| Register | Status | Where | Wording |
|---|---|---|---|
| **Required** (internal) | live, contractual | customer contracts | review is an obligation on the customer; this is what makes the SI's deferral coherent |
| **Advised** (we recommend) | **RETIRED** | `DisclaimerModal.tsx` `p1`/`p2`/`p3`/`fullText` -- no longer rendered or spoken (bd `polyglot-pdf-nsb4y`) | "We **strongly advise** you to have a qualified professional check your final form before you submit it" |
| **Undertaken** (they agree) | **LIVE -- both surfaces** | `intro_script.json`, 18 languages: rendered by the modal AND spoken, from ONE source | "you **agree to** review the completed document yourself and with a certified professional before filing" |

**The Undertaken register is LIVE, on both surfaces, on the default
deployment** (bd `polyglot-pdf-nsb4y`, maintainer decision 2026-08-19). What
the modal RENDERS and what the model SPEAKS both come from
`intro_script.json` via `renderIntroParagraphs`, unconditionally -- so a
reader and a listener accept the SAME terms behind the same Agree button.

That was NOT true before `nsb4y`. Both overlays gated the shared paragraphs on
`introEnabled`, which tied the WRITTEN legal text to whether AUDIO plays: a
reader got `DisclaimerModal`'s own `p2` ("we strongly advise" -- advice) while
a listener got the script ("you agree to review" -- an undertaking). Two legal
registers, one button, and `script_version` hashed only the spoken side, so
the audit record named text a reader never saw.

**The `introEnabled` flag pair still gates the AUDIO CLIP** (`INTRO_TTS_ENABLED`
backend, `VITE_INTRO_CLIP_ENABLED` frontend, both default false; flipping them
is bd `polyglot-pdf-vr5bj`, gated on counsel review). It does NOT gate the
text. Keep that separation: a flag may decide whether Sol SPEAKS, never which
terms the applicant ACCEPTS.

`DisclaimerModal`'s `DISCLAIMER_TRANSLATIONS` survives only as the modal TITLE
source and as a fallback for a caller that passes no `introParagraphs`; no app
code renders or speaks its body text, and a test pins that set.

The HARD INVARIANT asserted in `intro_script.json` and `intro_tts.py` -- "the
modal renders exactly these paragraphs -- one source, no separate fullText" --
is now TRUE of shipped behavior and may be cited as current.

**The acceptance record now names WHICH text was agreed to.** `POST
/api/disclaimer-acceptance` logs `script_version` (bd
`polyglot-pdf-s1iex.7`) -- the hash of the exact per-language script, taken
from the intro route's `X-Intro-Script-Version` response header so the backend
stays the single source of it. That is what turns the epic's determinism into
EVIDENCE: without it the record proves someone clicked Agree but not what they
were told.

**The acceptance record is DURABLE** (bd `polyglot-pdf-0dsv4`). It goes to the
same sink the field confirmations use -- the `confirmation_events` Firestore
collection AND the per-session JSONL file -- keyed on `form_session_id`, so
`read_confirmation_log(form_session_id)` returns the acceptance and the field
confirmations as ONE timestamp-ordered session record: *this session accepted
this exact text, then confirmed these fields*.

It was a structlog line and nothing else until then, which meant the record
that a user accepted the LEGAL TERMS aged out with the Cloud Run log bucket
while the record of what they TYPED was durable -- backwards for an evidence
trail.

The write is FAIL-OPEN: a sink outage logs and continues rather than failing
the request. Losing one audit record is bad; blocking every user from starting
their form is worse, and the structlog line still records the acceptance
either way. A signature mismatch logs distinctly
(`disclaimer_acceptance_wiring_error`) from a transient failure
(`disclaimer_acceptance_durable_write_failed`), because the former fails on
EVERY request and must not hide inside degradation noise.

**`firm_id` is written as `None` today, deliberately.** This route carries no
auth token -- Agree fires before any authenticated session exists -- so the
firm cannot be read here. The key is written anyway so the collection has ONE
shape and needs no migration when firm auth reaches this route (maintainer
decision 2026-08-20). Until then `firm_of_events()` recovers the firm from the
session's OTHER records, which do carry it; a session that accepted and
abandoned before confirming any field has no firm anywhere and correctly
reports `None` rather than guessing, as do records that DISAGREE.

**KNOWN GAP as of bd `polyglot-pdf-nsb4y`: on the DEFAULT deployment the
record still logs `None`.** That clause used to read "the legacy model-read
path has no deterministic text to name", and that was true when it was
written. It is not true now: since `nsb4y` the modal renders the scripted
text unconditionally, so a user on the default deployment READS deterministic
text, clicks Agree, and the record names nothing. The reason is mechanical --
`script_version` is read from the intro PLAYER
(`introPlayerRef.current?.scriptVersion()`), and the player is only
constructed when `introEnabled` is true (`VoiceOverlay.tsx`), so with the
audio flags off the value is `undefined` and the key is dropped.

Closing it is NOT a one-line change: the hash currently comes from the intro
route's response header precisely so the backend stays its single source, and
having the client compute it instead would reintroduce the drift risk bd
`s1iex.7` was designed to avoid. Tracked as bd `polyglot-pdf-pyebx`.

**The register question is SETTLED; the flags no longer bear on it.** Whether
the written modal should adopt the spoken undertaking -- so both surfaces stay
in one register -- was the legal/product decision tracked in bd
`polyglot-pdf-nsb4y`, and the maintainer settled it on 2026-08-19: ONE SOURCE,
the modal shows the spoken script. Both surfaces now state the undertaking
regardless of the audio flags, so flipping them cannot create a
listened-vs-read split. What the flags still change is only whether Sol SPEAKS
the clip or the Live model reads the same text aloud.

A counsel pass on the frozen script is still outstanding (noted in
`intro_script.json`), and remains a gate on the flag flip (bd
`polyglot-pdf-vr5bj`) -- but it no longer gates the register, which is live
today.

**The SI must never promise a review WILL happen**, even though the applicant
now undertakes to obtain one: *"Do not promise the user that a review WILL
happen -- the disclaimer has them AGREE to obtain review, which is their
commitment, not our guarantee that it occurred."* This is the register
distinction that survives bd `polyglot-pdf-nsb4y`: what the APPLICANT commits
to changed; what WE guarantee did not. An undertaking by the user is not a
guarantee by us, and the model cannot know whether it was honoured.
Strengthening this text re-introduces the exact bd `rdsl` bug: the SI once
PROMISED review ("Every form drafted here is reviewed...") where the disclaimer
only advised it, and that survived the author, the tests, and two review rounds
-- caught only because one reviewer read the disclaimer beside the prompt.

### What would invalidate this

Any move toward self-filing, direct-to-consumer sale, or a deployment without a
contracted reviewing professional. Any of those requires revisiting the deferral
language, the disclaimer, and the certification-block position **together** --
they are one posture, not three independent choices.

## Audit-log hygiene

The confirmation log directory is **not** committed to git, and tests redirect
their writes via `CONFIRMATION_LOG_DIR` so a test run never dirties the tree.
Audit logs are runtime artifacts, not source — keep them out of version control
(this was the subject of bd `polyglot-pdf-0rx`).

*Last updated: 2026-08-22 (bd polyglot-pdf-0dsv4: the disclaimer acceptance is now DURABLE -- same sink as the field confirmations, joined on form_session_id, with firm_id written as None until firm auth reaches that unauthenticated route. Also bd polyglot-pdf-xwlt: `firm_id` joins the confirmation record and the session-lifecycle pair is WIRED -- see [the xwlt journal entry](../journal/entries/2026-08-20-bd-xwlt-firm-telemetry.md). Previously bd polyglot-pdf-1dt9b: the Undertaken-register
reachability claim was stale -- the frontend intro-clip player shipped in bd
s1iex.5, so the real gate is now both flags defaulting off, not "no player
exists").*
