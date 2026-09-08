"""Privileged ADMIN service (Cloud Run service polyglot-admin).

A sibling top-level package to backend/, deliberately NOT a subpackage of it.
Sprint 22 Epic 1, plan docs/sprint_22_admin-console_plan.md ("Admin service").

WHY A SEPARATE PACKAGE. The public backend runs as polyglot-backend-sa, whose
IAM is deliberately narrow (CLAUDE.md scar #7). Every privileged call --
Firebase Auth admin operations, Cloud Build, BigQuery, Firestore writes on
behalf of an operator -- lives ONLY under this package, which runs as its own
service account (admin-backend-sa) on its own Cloud Run service. The guard
backend/tests/unit/test_deployed_iam_envelope.py walks backend/ only (its root
is parents[2] of that test file), so the public backend stays pinned at zero
privileged Firebase Auth calls with no change to it, and the sibling guard
admin_backend/tests/unit/test_admin_sa_iam_envelope.py pins THIS service's
role list.

WHAT IT SHARES. backend.services.* (firms, link_tokens, kit_gates, the
Firestore client) and backend.config. It must NEVER import backend.routes:
the two services share business logic, not HTTP surface. That direction is
pinned by test.

ONE IMAGE, TWO SERVICES. The root Dockerfile copies both packages and reads
the ASGI target from the runtime env var APP_MODULE (default
backend.main:app). deploy-all.sh's backend stage sets APP_MODULE (plus
GIT_SHA) as runtime env on every backend deploy, defaulting to
backend.main:app when a caller sets nothing -- every public channel
(deploy-staging.sh, deploy-demo.sh) does exactly that, so this is a config
addition with no behavior change for them. deploy-admin.sh (bd
polyglot-pdf-3l2vp, sprint-22 plan bead 1.3) is the one caller that overrides
it, exporting APP_MODULE=admin_backend.main:app ahead of the same
deploy-all.sh --backend invocation, and additionally deploys the admin
service as a no-traffic tagged revision verified at its own health endpoint
before traffic shifts -- the control plane's own staging tier, since one
admin service backs both channels' data.
"""
