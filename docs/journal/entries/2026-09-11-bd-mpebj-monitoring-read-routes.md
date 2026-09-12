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

## Lessons

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
