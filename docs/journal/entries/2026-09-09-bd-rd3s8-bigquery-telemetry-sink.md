---
date: 2026-09-09
bead: polyglot-pdf-rd3s8
title: "feat(telemetry): E3.6 BigQuery dataset, logging sink, cost/income views (declarative, operator-run)"
sprint: 22
tags: [conventions, testing]
---

## Trigger

Epic 3 bead 6 (E3.6) of the sprint 22 admin-console program (plan:
`docs/sprint_22_admin-console_plan.md`, "BigQuery" section). The plan calls
for a Cloud Logging -> BigQuery sink and five cost/income views, declarative
and operator-run like the existing `setup-gcp-project.sh` /
`setup-admin-service.sh` scripts -- nothing in this bead touches a live GCP
project. Depends on bd `polyglot-pdf-wio6m` (usage event v2), already closed.

## What shipped

`scripts/setup-telemetry.sh` creates the `polyglot_telemetry` dataset
(`us-central1`), a Cloud Logging sink over both Cloud Run backend services
(`polyglot-backend`, `polyglot-backend-staging`), grants the sink's own
writer identity `roles/bigquery.dataEditor` on the dataset, grants
`admin-backend-sa` `roles/bigquery.jobUser` (project-level) and dataset-scoped
`roles/bigquery.dataViewer`, and applies `sql/telemetry_views.sql`'s five
`CREATE OR REPLACE VIEW` statements via `bq query`.

**The load-bearing finding.** The plan's prose and this bead's own
description both describe the sink filter as "`jsonPayload.event_type` in the
usage / session / ledger_export / error set," as if one field name at one
JSON depth covered every emitter. Tracing the actual emitters found three
genuinely different shapes: usage events (`gemini_api_response`,
`text_ai_usage`, `tts_usage`) go through `StructuredLogger._emit`, which
wraps the whole envelope in a `message` key, so the event type sits at
`jsonPayload.message.event_type`; `ledger_export` goes through
`credit_ledger.py`'s plain `structlog` call with an explicit `event_type=`
kwarg, landing flat at `jsonPayload.event_type`; the two wired session events
(`form_session_started`/`form_session_ended`) go through
`confirmation_logger.py`'s plain `structlog` calls with NO `event_type` kwarg
at all, so `structlog`'s `JSONRenderer` renders the POSITIONAL event name
under the plain key `jsonPayload.event` -- a third shape again. Verified by
capturing real emitted JSON from each path, not by reading the source and
assuming. A filter written as a single `jsonPayload.event_type IN (...)`
clause would have silently dropped every session row (wrong key) and every
usage row (wrong nesting depth) while matching only `ledger_export` -- the
kind of gap where a BigQuery dashboard returns zero rows with no error
anywhere. `scripts/setup-telemetry.sh`'s `SINK_FILTER` ORs across all three
shapes instead, and both `tests/test_setup_telemetry_script.py` and this
journal entry document why a single `IN (...)` clause is deliberately
rejected.

**Views** (`sql/telemetry_views.sql`): `cost_by_firm_month`,
`cost_by_kit_month`, `cost_by_employee_month` (usage-event shape, grouped by
month + the relevant id + `usage_kind`); `hosting_cost_by_service_month`
(Cloud Billing detailed export, filtered to Cloud Run + Firebase Hosting
SKUs, split by `resource.name` so staging and demo Cloud Run cost never mix
-- returns zero rows until the export is enabled, a separate maintainer
console step, Epic 3 bead 7); `income_month` (ledger_export rows, `type IN
('purchase', 'subscription_grant')`, with `firm_kind = 'live'` hard-coded in
the view -- this bead inherits Epic 3's overall exit criterion 5, the
income-filter half). Every view's referenced columns are checked against a
DERIVED allowlist (from `log_schemas.USAGE_CONTEXT_KEYS` and
`credit_ledger.LEDGER_EXPORT_FIELDS`), not a hand-typed list, in
`backend/tests/unit/test_telemetry_views.py`.

**IAM housekeeping.** `admin_backend/tests/unit/test_admin_sa_iam_envelope.py`
had `roles/bigquery.jobUser` and `roles/bigquery.dataViewer` in its
`DEFERRED_ROLES` set (Epic 1 deliberately left them ungranted until this
bead). Moved both into `EXPECTED_ADMIN_SA_ROLES`, with a new
`TELEMETRY_GRANTED_ROLES` constant marking that `setup-telemetry.sh`, not
`setup-admin-service.sh`'s `PROJECT_ROLES` array, is what grants them -- the
existing project-role-pin test subtracts that constant out before comparing
against `setup-admin-service.sh` alone, and two new tests read
`setup-telemetry.sh` directly for the grants and their scope.

**Exit criterion 3** ("the ledger_export log line carries every field
income_month reads") needed no production code change --
`credit_ledger.py`'s two `_log.info(LEDGER_EXPORT_EVENT, ...)` call sites
already emit exactly `LEDGER_EXPORT_FIELDS`, which is a superset of what
`income_month` reads. Added
`test_export_line_carries_every_column_income_month_reads` to
`backend/tests/unit/test_credit_ledger.py`, which parses `income_month`'s
actual SQL and checks its referenced columns against both the static
`LEDGER_EXPORT_FIELDS` pin and a live emitted payload, so the view and the
emitter cannot silently drift apart in either direction.

All new tests were mutation-verified: the production behavior (or script
text) each test pins was reverted, the test observed to fail, then restored.

**Cross-surface review, round 1 (2026-09-09) -- 2 adopted, 1 deferred to a
filed bead.** The outer review found the sink filter's THREE key shapes
were correct but traced one layer beneath them: the same filter matches
TWO different Cloud Run log STREAMS (usage events print directly to
stdout; `ledger_export` and the two session events go through plain
`structlog`, which reaches stdlib logging's default stream --
`backend/utils/logging.py`'s `configure_logging()` never overrides it to
stdout, so it stays stderr). A Cloud Logging -> BigQuery sink names one
destination table per log stream, so the sink actually writes TWO tables,
and the script's original `bq ls | head -1` picked exactly one, silently
leaving either the three cost views or `income_month` permanently empty.
**Adopted (blocker):** filed as bd `polyglot-pdf-ih428`; fixed by splitting
the single `${TELEMETRY_TABLE}` SQL placeholder into
`${TELEMETRY_TABLE_STDOUT}` (the three usage-shape cost views) and
`${TELEMETRY_TABLE_STDERR}` (`income_month`), having
`scripts/setup-telemetry.sh` discover and substitute both independently
(requiring both to exist before applying any view), and adding five new
tests across `backend/tests/unit/test_telemetry_views.py` and
`tests/test_setup_telemetry_script.py` -- including a headline
"do-not-share-a-placeholder" pin -- all mutation-verified. The three docs
that inherited the same single-table assumption
(`sql/telemetry_views.sql`'s header, `scripts/setup-telemetry.sh`'s own
comments, `docs/technical_guide.md`'s Surface contract 22, and
`docs/standards/logging-and-cost.md`'s BigQuery section) were corrected in
the same pass, including the header's incorrect claim that the table name
comes from `gcloud logging sinks describe` (it comes from `bq ls`).
**Adopted (blocker):** `docs/components/admin-service.md` still listed
`roles/bigquery.jobUser` + dataset-scoped `roles/bigquery.dataViewer` as
"deferred, deliberately absent" -- true on `origin/dev`, but this bead moved
both roles into `EXPECTED_ADMIN_SA_ROLES` and granted them from
`setup-telemetry.sh`. Fixed by adding both roles as their own rows in the
roles table (noting they're granted by `setup-telemetry.sh`, not this
script) and removing them from the deferred list. **Deferred (nit, filed
as its own bead):** `scripts/setup-telemetry.sh`'s two usage strings
document only the required `PROJECT_ID` argument, not the optional second
`BILLING_EXPORT_TABLE` argument the script silently skips view creation
without -- filed as bd `polyglot-pdf-un0es` rather than fixed inline, since
the reviewer classified it a nit (cosmetic usage-string gap, not a
behavioral break) and the fix rules reserve inline fixes for
rubric-fails/blockers.

## Lessons

A plan or bead description that names a single log field as a filter target
is not itself proof that every relevant emitter actually produces that field
at that JSON depth -- `structlog`'s `JSONRenderer` renders a POSITIONAL
event name differently depending on whether the caller also binds an
explicit `event_type` kwarg, and `StructuredLogger._emit`'s `message`
wrapper is a second, independent source of shape divergence. When wiring a
sink or filter against several existing emitters, capture and diff their
REAL emitted JSON rather than trusting a shared field name in prose or a
docstring. Added to `docs/standards/logging-and-cost.md`'s new "BigQuery
telemetry sink" section as a documented table of the three shapes, so the
next emitter added to this sink starts from the real picture instead of
re-deriving it.

## Doc freshness

`docs/standards/logging-and-cost.md`: new "BigQuery telemetry sink +
cost/income views" section; Tracks line extended with
`scripts/setup-telemetry.sh`, `sql/telemetry_views.sql`,
`backend/services/credit_ledger.py`; Last-updated annotation extended.

`docs/technical_guide.md`: new Surface contract 22 (the BigQuery sink +
views); top-of-file changelog annotation extended.

## Files touched

- `scripts/setup-telemetry.sh` (new) -- the operator-run provisioning script.
- `sql/telemetry_views.sql` (new) -- the five view definitions.
- `tests/test_setup_telemetry_script.py` (new) -- pins the script's dataset
  name/location, sink filter (all three shapes), and IAM grants.
- `backend/tests/unit/test_telemetry_views.py` (new) -- pins the SQL's
  income filter and derived column provenance.
- `admin_backend/tests/unit/test_admin_sa_iam_envelope.py` -- moves the two
  BigQuery roles out of `DEFERRED_ROLES`, adds `TELEMETRY_GRANTED_ROLES` and
  two new tests reading `setup-telemetry.sh`.
- `scripts/setup-admin-service.sh` -- comment update only (no role change):
  the two BigQuery roles are no longer described as deferred to "Epic 3" in
  the abstract; they are granted by a different script now.
- `backend/tests/unit/test_credit_ledger.py` -- adds
  `test_export_line_carries_every_column_income_month_reads` (exit
  criterion 3).
- `docs/standards/logging-and-cost.md`, `docs/technical_guide.md` -- see Doc
  freshness above.

**Review round 1 fixes (bd `polyglot-pdf-ih428`, blocker; plus the
`docs/components/admin-service.md` doc fix, blocker):**

- `sql/telemetry_views.sql` -- splits `${TELEMETRY_TABLE}` into
  `${TELEMETRY_TABLE_STDOUT}` (the three cost views) and
  `${TELEMETRY_TABLE_STDERR}` (`income_month`); rewrites the header comment
  to describe the two-table split and the `bq ls` discovery mechanism.
- `scripts/setup-telemetry.sh` -- discovers and substitutes both table
  names independently, requiring both before applying any view; rewrites
  the section-6 comment.
- `backend/tests/unit/test_telemetry_views.py` -- replaces the single-table
  pin with `test_usage_views_read_the_stdout_table_not_the_stderr_table`,
  `test_income_month_reads_the_stderr_table_not_the_stdout_table`, and the
  headline `test_usage_views_and_income_month_do_not_share_a_table_placeholder`.
- `tests/test_setup_telemetry_script.py` -- adds three tests pinning the
  script's dual-table discovery, the independent sed substitutions, and the
  both-tables-required guard.
- `docs/technical_guide.md`, `docs/standards/logging-and-cost.md` -- Surface
  contract 22 / the BigQuery telemetry section updated for the two-table
  split.
- `docs/components/admin-service.md` -- `roles/bigquery.jobUser` +
  dataset-scoped `roles/bigquery.dataViewer` moved from the deferred-roles
  list into their own rows in the roles table.
- `polyglot-pdf-un0es` filed (nit, not fixed here): the script's usage
  strings do not name the optional `BILLING_EXPORT_TABLE` argument.

Review outcomes recorded in the closeout ping.
