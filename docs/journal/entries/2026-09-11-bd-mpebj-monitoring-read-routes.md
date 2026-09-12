---
date: 2026-09-11
bead: polyglot-pdf-mpebj
title: "feat(admin): E3.11a monitoring read routes -- usage rollups, BigQuery cost/income reports, alerts list + acknowledge, error stats, health fan-out"
sprint: 22
tags: [security, testing]
---

## Trigger

Epic 3 bead 11a (plan: `docs/sprint_22_admin-console_plan.md`, "Console
views"). The admin-console monitoring page (bead i6dlb, blocked on this one)
needs one place to read everything Epic 3's earlier beads have been
writing: per-firm/kit usage rollups (E3.4, bd w828m), BigQuery cost/income
views (E3.6, bd rd3s8), telemetry alert docs (E3.5, bd bo95a), and the
error/close event shape (E3.8, bd e4dt8). None of those had a console-side
reader yet.

## What shipped

Eight new GET routes plus one PATCH across four new route modules, all on
the admin service:

- `admin_backend/routes/usage_routes.py` -- `GET
  /admin/firms/{firm_id}/usage` (`require_app_admin_or_owning_manager`,
  404-not-403 for another firm) and `GET /admin/kits/{kit_id}/usage`
  (`require_app_admin`). Both read the E3.4 rollup docs under an explicit
  key allowlist; `?month=`/`?channel=` are required, and a missing rollup
  doc reads as an empty month, never a 404.
- `admin_backend/services/bigquery_reports.py` +
  `admin_backend/routes/report_routes.py` -- `GET /admin/reports/cost`
  and `GET /admin/reports/income`, parameterised BigQuery reads over the
  E3.6 views. Every caller value (`from`, `to`, `channel`) is bound as a
  `bigquery.ScalarQueryParameter`; `group_by` selects the view through a
  closed dict, never a string reaching SQL. A range over 12 months is a
  422; every response carries `delayed: true` plus a sink-lag note.
- `admin_backend/routes/alert_routes.py` -- `GET /admin/alerts` (list,
  filterable) and `PATCH /admin/alerts/{id}/acknowledge`, the bead's one
  mutation: sets `acknowledged_by`/`acknowledged_at` in one Firestore
  transaction with its audit row (mirrors `firm_routes.py`'s
  `_apply_firm_patch` shape); acknowledging twice is a 409.
- `admin_backend/services/error_stats.py` +
  `admin_backend/routes/ops_routes.py` -- `GET /admin/errors` (Cloud Error
  Reporting `groupStats`, type + top frame only, message body never read)
  and `GET /admin/health` (fans out to a channel's public backend
  `/health` + `/version`, partial result on an unreachable channel,
  `reachable` requires both calls to succeed).

New admin-service env var `BACKEND_URLS_JSON`, resolved by
`deploy-admin.sh` via `gcloud run services describe` on both public
backends. Its WIRE FORMAT is `"channel=url;channel=url"`, not literal
JSON despite the name: the value rides inside `deploy-all.sh`'s
comma-joined `--set-env-vars` block, and a real JSON object's comma would
be split apart there (the same reason `CORS_EXTRA_ORIGINS` is
semicolon-separated). This was a deliberate, decided-by-default deviation
from the bead's own `{"demo": url, ...}` prose -- the bead named the
SHAPE, not a literal wire contract nothing else consumes, and the
established in-repo mechanism for a compound value riding this same env
block is semicolons.

No new IAM grant: `admin-backend-sa` already holds `bigquery.jobUser` +
dataset `bigquery.dataViewer` (bd rd3s8) and `errorreporting.viewer` (bd
e4dt8) from earlier beads in this epic.

### Cross-surface review round -- adopt/reject/defer

The Opus outer cross-surface review returned `GAPS-FOUND (3)`. Breakdown:

- **ADOPTED (blocker, code fix):** `GET /admin/reports/income?channel=`
  could never return a real answer for any channel value -- `income_month`
  rows are always `channel IS NULL` (the admin service writing
  purchase/subscription_grant ledger entries has no channel of its own;
  `sql/telemetry_views.sql`'s own view comment already said so), so a
  `channel = @channel` filter silently returned zero rows for the one
  route whose job is reporting real money. Fixed by refusing `?channel=`
  outright (422, new `_validated_income_channel`) and removing the dead
  `channel` parameter from `bigquery_reports.query_income_report` entirely
  (CLAUDE.md scar #7: remove the parameter, don't default it off). The
  flagged test (`test_report_routes.py:173`) mocked `_run_query`, so it
  proved the parameter was BOUND but could never prove the query would
  MATCH a row -- same "mock proves the call, not the answer" shape as scar
  #7, applied to data instead of IAM. Replaced with a parametrized test
  (`test_income_report_refuses_any_channel_value`, over `demo`/`staging`/
  an unrecognized value -- ALL 422) plus
  `test_income_report_has_no_channel_parameter`; mutation-verified by
  reverting the guard and confirming all three parametrizations go red.
- **ADOPTED (blocker, doc fix):** `docs/technical_guide.md`'s `/admin/errors`
  routes-table row named the wrong exception (`BigQueryUnavailable`,
  copy-pasted from the cost-report row above it) for the 503 mapping;
  the real exception is `ErrorReportingUnavailable`. Fixed.
- **ADOPTED (blocker, doc fix):** Surface contract 28a's Consumers section
  still read "(a later bead)" for the errors-per-channel console view this
  bead ships. Fixed -- and, since this is the enumerate-the-set trap
  (CLAUDE.md scar #8), also swept for and fixed the SAME stale "later
  bead" / "none yet in this bead" pattern on contract 21 (alerts) and
  contract 25 (cost/income views) and the `acknowledged_by`/
  `acknowledged_at` field note -- all four were the identical unaddressed
  consumer this bead adds, left unupdated everywhere except contract 26
  (which the original diff DID update).
- **DEFERRED (pre-existing, filed as beads, not fixed here):** the four
  stacked `*Last updated:` stamps in `docs/components/admin-service.md`
  (bd `polyglot-pdf-u5l0f` -- pre-existing at three, this bead's own stamp
  made it four) and the bare `import requests` outside its try/except in
  `ops_routes.py`/`error_stats.py`, unguarded unlike
  `bigquery_reports.py`'s sibling import (bd `polyglot-pdf-c92sa` --
  currently unreachable since `requests` is pinned into the shared image,
  but inconsistent with the established pattern).
- **NOT FLAGGED, reviewed and confirmed correct:** `_rollup_doc_id`'s
  mirrored-not-imported duplication of `usage_rollups._month_key` (traced
  both, they agree exactly including the default channel constant);
  `bigquery.Client()`'s implicit location resolution against the
  regional dataset (resolves via the dataset reference, not flaggable
  without a live query); the alerts list's full-collection Python-side
  filtering (deliberate, documented, TTL- and page-capped).

### Cross-surface review round 2 -- adopt/reject/defer

A second Opus outer cross-surface review returned `GAPS-FOUND (1)`. Breakdown:

- **ADOPTED (blocker, code + doc fix):** `admin_backend/services/error_stats.py`'s
  `_public_group_view` read `representative.get("type")` for `GET
  /admin/errors`'s `error_type` field -- a field the Cloud Error Reporting
  API does not have. Verified against the live v1beta1 discovery document
  (`ErrorEvent`'s complete property set is `context`/`serviceContext`/
  `message`/`eventTime` -- no schema in the API defines `type`,
  `errorType`, or `exceptionType`), this meant `error_type` would read
  `null` on every real response while the unit test stayed green, because
  the test fixture was hand-authored with a `"type"` key the real API
  never sends -- the same "a mock cannot tell you the real dependency is
  forbidden" shape as CLAUDE.md scar #7, here applied to a response FIELD
  instead of an IAM permission. Fixed by recovering the type from
  `representative.message`'s own terminating line instead (new
  `_error_type_from_message`): E3.8's write-side PII rule
  (`pii_safe_exception_info`) already guarantees that field, once it
  reaches Error Reporting as `representative.message`, ends each rendered
  block with the bare exception type name and nothing else in this
  repo's own error paths, so reading it back is safe -- but the parser is
  deliberately narrow (rejects any line with a space or a colon, returning
  `None` rather than guessing) so a message this module does not recognize
  as type-only degrades to "unknown" instead of parsing further into it or
  leaking. Updated the test fixture in `test_ops_routes.py` to the REAL
  API shape (no `"type"` key; `"message"` shaped like this repo's actual
  `pii_safe_exception_info` output, sentinel embedded in a frame line to
  keep exercising a real leak shape) and added a new test pinning the
  narrow-parse guard (`test_error_type_recovery_rejects_anything_not_a_
  bare_type_token`, covering a real "Type: message" rendering and an empty
  message). Both new/changed tests mutation-verified: reverting to
  `representative.get("type")` against the corrected fixture reddens the
  first; relaxing the space/colon guard reddens the second. Corrected the
  same stale "`representative.type`" claim everywhere it appeared:
  `docs/technical_guide.md` (the `/admin/errors` routes-table row, Surface
  contract 28a's Consumers section, and contract 29's own error-stats
  bullet) and `docs/components/admin-service.md` (the bead-19 narrative
  paragraph and the admin routes table row).
- **DEFERRED (pre-existing, filed as beads, not fixed here):**
  `admin_backend/routes/alert_routes.py`'s "explicit key allowlist" review
  gate does not actually gate anything, because `_ALERT_RESPONSE_KEYS` is
  derived from `alerts.ALERT_FIELDS` rather than hand-listed the way
  `usage_routes.py`'s allowlists are (bd `polyglot-pdf-927u5`); the
  `timeRange.period` comment in `error_stats.py` names a `PERIOD_1_MONTH`
  enum value the real API does not define (bd `polyglot-pdf-ez6ed`); and
  `bigquery_reports.py`'s `_run_query` builds its client with no explicit
  `location=` against a regional (`us-central1`) BigQuery dataset -- most
  likely fine via BigQuery's own location inference, but unverified
  against a live project since the unit tests monkeypatch `_run_query`
  entirely (bd `polyglot-pdf-4sc22`).

## Lessons

- When a route's job is to shape a THIRD-PARTY API's response, verify the
  field names against that API's own schema (a discovery document, an
  OpenAPI spec) before writing the hand-authored test fixture -- a fixture
  written from the same (wrong) assumption as the code it tests will stay
  green forever. Here the fixture invented a `"type"` key that
  `groupStats.representative` (an `ErrorEvent`) does not have, so the test
  proved nothing about the real field (`representative.message`) the API
  actually returns.
- The bead's own prose for an env var's VALUE shape is not always its
  final WIRE format when that value has to ride inside an existing
  comma-joined assembly mechanism -- check how the value actually reaches
  its destination (here, `deploy-all.sh`'s `--set-env-vars` string) before
  assuming a literal reading of the bead text is safe to ship.
- Every new mutating route needs three coordinated test-suite touches, not
  one: the route's own atomicity test, `test_admin_route_auth.py`'s
  registered-route-set + gate-specificity pins, and
  `test_admin_audit_coverage.py`'s `MUTATION_KINDS` declaration + its
  synthetic-check tie-back. Missing any one leaves the coverage gate
  vacuous for that route specifically while the suite stays green.

## Doc freshness

- `docs/components/admin-service.md` -- bumped, new routes table rows,
  new IAM role rows (also fixed pre-existing staleness: `errorreporting.
  viewer`/`monitoring.viewer` were still listed "Deferred ... not yet
  built" though bd e4dt8 already granted both), new Testing section
  paragraph.
- `docs/technical_guide.md` -- no stamp by design (CLAUDE.md). Extended
  Surface contract 26 with its first real reader; added new Surface
  contract 29 for this bead's own cross-cutting rules (parameterised SQL,
  the alert-acknowledge transaction shape, the error-stats message-never-
  read rule, the `BACKEND_URLS_JSON` wire format, the health route's
  AND-not-OR reachability rule). Admin service routes table grew by eight
  rows, kept in (path, method) sort order per
  `tests/test_technical_guide_routes_table.py`.
- Several `docs/standards/*.md` files were flagged STALE by
  `scripts/check_doc_freshness.py` against files this bead did not touch
  (voice/VAD, SI-reduction, schema-key-visibility, terminology, and
  others) -- pre-existing staleness from unrelated work, left as-is per
  the closeout triage rule (leave what this bead did not touch).
- Review outcomes recorded in the closeout ping.

## Files touched

- `admin_backend/routes/usage_routes.py` (new)
- `admin_backend/routes/report_routes.py` (new)
- `admin_backend/routes/alert_routes.py` (new)
- `admin_backend/routes/ops_routes.py` (new)
- `admin_backend/services/bigquery_reports.py` (new)
- `admin_backend/services/error_stats.py` (new)
- `admin_backend/main.py` -- wired the four new routers
- `admin_backend/tests/unit/test_usage_routes.py` (new)
- `admin_backend/tests/unit/test_report_routes.py` (new)
- `admin_backend/tests/unit/test_alert_routes.py` (new)
- `admin_backend/tests/unit/test_ops_routes.py` (new)
- `admin_backend/tests/unit/test_admin_route_auth.py` -- registered-route
  set + two new gate-specificity tests
- `admin_backend/tests/unit/test_admin_audit_coverage.py` -- the one new
  mutating route's `MUTATION_KINDS` entry + synthetic-check tie-back
- `backend/requirements.txt` -- pinned `google-cloud-bigquery` (already a
  transitive dependency) and `requests` explicitly
- `deploy-admin.sh` -- resolves and folds `BACKEND_URLS_JSON` into
  `BACKEND_EXTRA_ENV` on every run
- `tests/test_deploy_admin_backend_urls.py` (new)
- `docs/components/admin-service.md`, `docs/technical_guide.md`
