---
date: 2026-09-15
bead: polyglot-pdf-tb3kp
title: "feat(admin): E4.3 deploy trigger route, Pub/Sub build-status webhook, deployments collection"
sprint: 22
tags: [testing, security]
---

## Trigger

Epic 4 bead 4.3 of docs/sprint_22_admin-console_plan.md ("Triggering and
status from the admin service"). The bead was PAUSED 2026-09-14 while the
maintainer decided between two Cloud Build deploy paths (manual triggers vs.
a read-only deployments view); UNPAUSED the same window once the maintainer
chose option 1 (manual triggers for both paths), so this bead is built
exactly as its body describes. Depends on bead ywxoh (E4.2, the remaining
Cloud Build targets and in-build gates) and is a prerequisite for bead
jub5f (E4.4, the richer promotion-gate test suite) and ryx86 (E4.7, the
console Deploys page).

## What shipped

Three admin routes and one webhook, all new surface on the admin service:

- `admin_backend/services/cloud_build.py::run_target(target, sha,
  project_id=...)` -- runs the "polyglot-<target>" Cloud Build trigger at an
  explicit commit via `CloudBuildClient.run_build_trigger` (NOT
  `create_build`: `Build.build_trigger_id` is output-only, so `create_build`
  cannot address an existing trigger without respecifying its whole config).
  The `RepoSource` carries only `commit_sha`, matching the proven
  `gcloud builds triggers run TRIGGER --sha=SHA` CLI shape rather than
  guessing at `repo_name`'s requirement for a 2nd-generation trigger. Returns
  `{build_id, log_url}` read off the long-running operation's metadata
  (populated the moment the build is enqueued) without waiting on
  `operation.result()`, which would block for the whole build duration.
- `POST /admin/deploys` -- validates `target` against the new
  `deploy/targets.py::TARGETS` (422 on an unknown value) and `sha` as
  exactly 40 lowercase hex characters. For a target in `GATED_TARGETS`
  (`backend-demo`, `frontend-demo`, `admin-service`), refuses early with 409
  via `promotion_gate.staging_verified()` before ever touching Cloud Build.
  Write order: `deployments/{id}` (status `queued`, no `build_id`) FIRST,
  then a pending audit row (an EXTERNAL-form audit: the mutation is a Cloud
  Build API call, not a Firestore write), then the Cloud Build call. On
  failure, the audit row is marked failed and the deployment row's status is
  corrected to `failure` with no `build_id` -- the row is never erased, but
  it can never be mistaken for a running build.
- `GET /admin/deploys` / `GET /admin/deploys/{id}` -- newest-first,
  client-side filtered on channel/target (the collection is low-volume,
  avoiding a composite index per filter), explicit response-key allowlist.
- `POST /api/deploys/webhook` -- the Pub/Sub push endpoint for the
  `cloud-builds` topic, gated by `require_google_oidc` (its second consuming
  route after the sweep route) with a new `PUBSUB_PUSH_SA_EMAIL` env var
  pinning the push subscription's own caller identity. Decodes the base64
  Cloud Build message, upserts `deployments/{id}` BY `build_id` (never by
  document id) inside one `@firestore.transactional` body with an
  in-transaction audit row. A console-triggered build's row updates in
  place; a bash-triggered build with no pre-existing row gets one created
  with `triggered_by: "external"`. Idempotent (a plain field-value
  overwrite, not an increment), always 204 on a well-formed message so
  Pub/Sub's retry policy leaves it alone; a message that cannot even be
  parsed is 400.
- `deploy/targets.py` -- the one closed `TARGETS` list, replacing what were
  three independent copies (cloudbuild.yaml's comment,
  scripts/setup-cloud-build.sh's own array, and this bead's route). Also
  carries `CHANNEL_BY_TARGET`, `target_family()`, and the hand-listed
  `GATED_TARGETS` subset.
- `scripts/setup-admin-service.sh` -- enables `pubsub.googleapis.com`,
  creates the `cloud-builds` topic if absent, and declares a NEW dedicated
  `admin-pubsub-push-sa` service account as the push subscription's own
  caller identity (a third identity, distinct from both `admin-backend-sa`
  and `polyglot-cloudbuild-sa` -- reusing either would collapse
  `require_google_oidc`'s two-factor check to "any Google-signed token").
  The actual `gcloud pubsub subscriptions create` command is a printed NOTE,
  not executed, since it needs the admin service's own Cloud Run URL from
  its first deploy. `admin-backend-sa` gains `roles/cloudbuild.builds.editor`,
  moved out of `DEFERRED_ROLES` (now empty) into `EXPECTED_ADMIN_SA_ROLES` in
  the same commit as its first real caller.
- `promotion_gate.py` docstring corrected: an earlier version mis-labeled
  this bead as "4.4" -- the real 4.4 is bd jub5f. No behavior change; this
  module was already a working predicate from bead ywxoh, and this bead is
  its second real caller (the route's early, friendly 409), not its author.



**Fresh-eyes fix round (cross-surface review, GAPS-FOUND(2)):**

- ADOPT -- `deploy/targets.py`'s module docstring cited a drift-guard test
  (`test_target_family_matches_record_deployment_helper`) against
  `scripts/record_deployment.py`'s own `target_family()` copy that did not
  exist -- the claimed safety net was fictional. Wrote the real cross-check
  test in `tests/test_cloudbuild_yaml.py` (enumerates every `TARGETS` entry,
  asserts both copies agree) plus a new dedicated `tests/test_deploy_targets.py`
  covering the module's own invariants directly (every target has a channel,
  no orphan `CHANNEL_BY_TARGET` keys, no duplicates, `GATED_TARGETS` is
  exactly the three the plan names, `landing` stays excluded). Mutation-
  verified all three shapes of drift (a suffix dropped, a `GATED_TARGETS`
  entry dropped, a `CHANNEL_BY_TARGET` entry dropped) -- each goes red.
- ADOPT -- `admin_backend/routes/deploy_webhook.py`'s upsert-by-`build_id`
  had no defense against Pub/Sub's documented lack of delivery ORDER
  guarantee (only against duplicate delivery): a stale `WORKING` message
  arriving after a `SUCCESS` one would regress a terminal row back to
  "still running" with `finished_at` cleared. Added a one-directional guard
  (never overwrite `status`/`finished_at` on an existing TERMINAL row with a
  NON-terminal incoming status; `log_url` still refreshes; a second terminal
  message still applies) plus two new tests
  (`test_out_of_order_working_after_success_does_not_regress_status`,
  `test_a_second_terminal_status_still_applies_over_the_first`).
  Mutation-verified: disabling the guard reddens the first test.
- DEFER -- two low-confidence nits (whether `cloud_build.py::run_target`'s
  `trigger_id` shape is the live SDK's expected type -- undetectable
  offline; and the early promotion-gate Firestore query's lack of `.limit()`
  next to the sibling list route's explicit cap) filed as bd
  polyglot-pdf-0ovpl rather than fixed here, since both are genuinely
  unverifiable without a live deploy or are asymmetries the reviewer itself
  rated "very likely intentional."

Found this worktree with the implementation already substantially drafted
(a prior session's work, interrupted before a checkpoint commit -- the
bead's own PAUSED/UNPAUSED history suggests why). Verified it against the
bead contract and the current codebase, checkpointed it, merged in
`origin/dev` (13 commits, including the ywxoh and p4ale beads this work
depends on), resolved two doc conflicts, then reviewed, mutation-tested,
and finished it rather than rewriting from scratch.

## Lessons

Mutation-testing the failure-handling in `_do_trigger_deploy` (reverting
the status-correction so a failed trigger could still be mistaken for a
queued build with a fake `build_id`) and the webhook's upsert-by-`build_id`
lookup (defeating it so a repeated Pub/Sub message or a console-triggered
build's own status update created a second row instead of updating in
place) both went red as expected -- the exit-criterion assertions are load-
bearing, not vacuous. No new generalizable lesson beyond what CLAUDE.md's
"test the tests" scar tissue already covers.

## Doc freshness

- `docs/components/admin-service.md` -- bumped (Tracks line gained the five
  new files; new dated entry for this bead).
- `docs/technical_guide.md` -- the admin routes table gained the three
  `/admin/deploys*` rows and `/api/deploys/webhook` (this doc carries no
  Last-updated stamp by design).
- Other docs the freshness checker flagged as stale (si-reduction,
  stateless-architecture, terminology, testing, validation-delegation,
  voice-and-vad, ws-protocol) track files this bead did not touch --
  reviewed and left for whichever bead owns those changes.

## Files touched

- admin_backend/services/cloud_build.py (new)
- admin_backend/routes/deploy_routes.py (new)
- admin_backend/routes/deploy_webhook.py (new)
- deploy/targets.py (new)
- admin_backend/services/promotion_gate.py (docstring correction only)
- admin_backend/main.py (registers the two new routers)
- admin_backend/tests/unit/test_deploy_routes.py (new)
- admin_backend/tests/unit/test_deploy_webhook.py (new; extended in the
  fresh-eyes fix round with the out-of-order-delivery regression tests)
- admin_backend/tests/unit/test_admin_route_auth.py (four new routes pinned)
- admin_backend/tests/unit/test_admin_audit_coverage.py (two new mutation
  kinds pinned)
- admin_backend/tests/unit/test_admin_sa_iam_envelope.py
  (cloudbuild.builds.editor moved from deferred to expected)
- backend/requirements.txt (google-cloud-build==3.31.3)
- scripts/setup-admin-service.sh (Pub/Sub topic + push-caller SA)
- tests/test_setup_admin_service_pubsub.py (new)
- tests/test_deploy_targets.py (new, fresh-eyes fix round)
- tests/test_cloudbuild_yaml.py (real drift-guard test added, fresh-eyes fix round)
- admin_backend/routes/deploy_webhook.py (out-of-order-delivery guard added,
  fresh-eyes fix round)
- docs/components/admin-service.md
- docs/technical_guide.md
