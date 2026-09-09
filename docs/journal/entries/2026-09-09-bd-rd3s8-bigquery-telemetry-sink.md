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

Review outcomes recorded in the closeout ping.
