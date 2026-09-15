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

**Fresh-eyes fix round 2 (outer cross-surface review, GAPS-FOUND(2)):**

- ADOPT -- `admin_backend/routes/deploy_webhook.py` carried a THIRD,
  unimported, independent copy of the target-family suffix-strip logic
  (`_target_family()`) that round 1's drift-guard fix did not enumerate or
  cover -- exactly the CLAUDE.md scar #8 shape (round 1 already found and
  fixed ONE instance of two independent `target_family` copies with no
  cross-check; a third copy in the webhook's own module went uncaught).
  Fixed by importing `deploy.targets.target_family` directly (matching
  `deploy_routes.py`'s own existing import) and deleting the private
  duplicate, eliminating the drift risk instead of adding a fourth
  cross-check test. Mutation-verified: reverting the call site to return the
  raw (unstripped) target reddens
  `test_a_bash_triggered_build_with_no_existing_row_is_created_external`
  (`target_family` assertion).
- ADOPT -- `docs/technical_guide.md` Surface contract 31c still described
  `promotion_gate.py` as a bead-4.4 PLACEHOLDER with only a future admin-
  route caller, even though this same diff's corrected `promotion_gate.py`
  docstring and new contract 34 both confirm bead 4.3's `POST /admin/deploys`
  is the module's real second caller today. Rewrote 31c to state the current
  two-caller reality and point at contract 34; also fixed an adjacent stale
  future-tense claim in 31a ("bead 4.3's Pub/Sub webhook is what will also
  carry `console`/`cli`") that named `triggered_by` values contract 34 does
  not actually use, replacing it with a pointer to contract 34's real
  producers. Docs-only; no code change.
- REFUTE (not a finding) -- the reviewer's own report already classified the
  webhook test file's pre-existing `sys.path.insert` pattern as consistent
  with the file's established convention, not a new risk; no action needed.
- Not independently re-litigated: the reviewer's PASS verdicts on exit
  criteria 1-3, and the deferred `finishTime`/`createTime` type-consistency
  nit (low-medium confidence, needs a live Cloud Build payload sample to
  confirm) -- filed to the same deferred-nits bead as round 1's items rather
  than opening a new one.

**Fresh-eyes fix round 3 (outer cross-surface review, GAPS-FOUND(1)):**

- ADOPT -- the round 2 entry above's "filed to the same deferred-nits bead
  as round 1's items" claim was WRONG: bd polyglot-pdf-0ovpl's body (as
  actually written) contains only the two round-1 nits (`trigger_id` shape,
  promotion-gate query cap) -- the `finishTime`/`createTime` finding was
  never added to it, dropped silently between rounds. The round-3 reviewer
  independently re-derived the same finding, confirmed it against the
  installed `google-cloud-build` SDK's own `Build` type (its
  `create_time`/`finish_time` fields are `google.protobuf.Timestamp`, whose
  JSON mapping is a documented RFC3339 string, never a bare number -- this
  is a fact about protobuf's canonical JSON encoding, not merely a Cloud
  Build API convention, so it needed no live network call to confirm), and
  filed it as its own bead, bd polyglot-pdf-xqejk, since 0ovpl no longer
  accurately represented "what round 1 deferred." Fixed inline rather than
  re-deferring, since a round-3 reviewer surfacing the SAME finding a
  second time is exactly CLAUDE.md scar #8's "the tell you are in this
  trap" signal (a repeat finding differing only in whether it got tracked):
  added `deploy_webhook.py::_to_epoch()`, a normalizer parsing an RFC3339
  string (including Cloud Build's real up-to-9-fractional-digit
  nanosecond precision, truncated to Python's 6-digit microsecond
  resolution) or passing a bare number through unchanged, always returning
  the same float-epoch type `deploy_routes.py`'s `time.time()` writes use
  for `ts`. Applied at both webhook write sites (`finished_at` on the
  update path, `ts` on the bash-triggered create path). Updated every
  existing test that fed a synthetic int `finishTime`/`createTime` (the
  actual gap the reviewer named: no test had ever driven the webhook with
  a realistic RFC3339-string fixture) to use real RFC3339 strings instead,
  added an explicit float-type assertion on the update path
  (`test_a_console_triggered_build_going_terminal_writes_a_float_finished_at`,
  the UPDATE-path case the CREATE-path test alone did not cover), and added
  a dedicated `TestToEpoch` class pinning the parser's edge cases (bare
  number passthrough, Z-suffix, millisecond and nanosecond fractions,
  negative UTC offset, `None`, and an unparsable string both falling back
  to `time.time()`). Mutation-verified: reverting both `_to_epoch()` call
  sites back to `build.get(...) or time.time()` reddens four tests (the two
  updated existing ones plus the new update-path test), each failing on the
  stored value being the raw RFC3339 string instead of a float. Closes bd
  polyglot-pdf-xqejk.
- The round-3 reviewer's other findings were non-gaps it explicitly declined
  to act on: the `deploy/targets.py` GATED_TARGETS / `target_family()`
  suffix asymmetry (correct given `record_deployment.py`'s design, flagged
  only as an easy future misreading, no bug); the new
  `google-cloud-build==3.31.3` pin's unverified transitive-dependency
  adjacency in `backend/requirements.txt` (no evidence of an actual
  conflict, needs a `pip check` this offline review could not run); and the
  pre-existing `admin-service.md` "accretive changelog" pattern (already
  tracked by four open beads, not this diff's problem). None of these met
  the bar for a new bead.

**Fresh-eyes fix round 4 (outer cross-surface review, GAPS-FOUND(4)):**

- ADOPT (blocker) -- `cloud_build.py::run_target()`'s `RepoSource` carried
  only `commit_sha`, which is the API equivalent of
  `gcloud builds triggers run --sha=SHA` alone -- it never set the `_SHA`
  substitution `cloudbuild.yaml`'s own step 0 (`require-sha`) requires to be
  non-empty, and every trigger this module runs is provisioned
  (`scripts/setup-cloud-build.sh`) with only `_TARGET`/`_CHANNEL`
  substitutions, no `_SHA`. Every console-triggered build therefore aborted
  at step 0 with "ABORT: _SHA is empty" while the route had already
  returned 200 with a real `build_id` and a `queued` row the webhook then
  flipped to `failure` -- 100% of the time, on every target, invisible to
  the route's own tests (which mock `run_build_trigger` entirely). Fixed by
  adding `substitutions={"_SHA": sha}` to the `RepoSource`. New
  `admin_backend/tests/unit/test_cloud_build.py` exercises `run_target`
  directly against a fake `CloudBuildClient` (the route's own tests never
  reach this code path) and pins the `_SHA` substitution. Mutation-verified:
  reverting the kwarg reddens `test_run_target_passes_the_sha_substitution`.
- ADOPT (blocker) -- `GET /admin/deploys` orders the `deployments`
  collection on `ts`, a field `scripts/record_deployment.py` never wrote
  (it wrote `created_at`, an ISO-8601 string) -- Firestore's `order_by()`
  excludes any document missing the ordered-on field, so every
  staging-success row that script writes (exactly the rows the promotion
  gate reads, and what authorizes a demo promotion) was invisible to the
  console's deploys list on a query ordered by `ts`, even with a green
  build and a passing gate. Fixed by having `record()` also write a `ts`
  float-epoch field (kept alongside `created_at`, which stays as the
  human-readable display value). New `tests/test_record_deployment.py`
  pins this. Mutation-verified: deleting the `ts` key reddens
  `test_record_writes_a_float_ts_field`.
- ADOPT (blocker) -- `scripts/record_deployment.py` blindly created a new
  auto-id document on every call (`collection.document().set(doc)`), but
  for a console-triggered `backend-staging`/`admin-service` build, the
  webhook (`deploy_webhook.py`) already has a row for the SAME `build_id`
  by the time this build step runs (Cloud Build publishes QUEUED/WORKING
  before the build finishes) -- so this script created a SECOND document
  carrying the same `build_id`, and a later Pub/Sub message's own
  `.limit(1)` upsert lookup would pick one of the two non-deterministically,
  leaving the other's status permanently stale. Fixed by having `record()`
  query `deployments` for an existing row with the given `build_id` first
  and `.update()` it in place; only a build with no pre-existing row
  (typically bash-triggered) falls through to creating a new document,
  matching the webhook's own upsert shape. `tests/test_record_deployment.py`
  seeds a pre-existing webhook-style row and asserts exactly one row
  remains after `record()` runs. Mutation-verified: reverting to the blind
  `collection.document().set()` reddens
  `test_record_updates_an_existing_row_for_the_same_build_id_instead_of_duplicating`
  with a 2-row store instead of 1 -- reproducing the exact collision bug.
- ADOPT (blocker) -- `PUBSUB_PUSH_SA_EMAIL` (the webhook's OIDC caller-email
  allowlist) was set by NO deploy path: `scripts/setup-admin-service.sh`
  only printed it as a one-time hand-run NOTE, absent from
  `deploy/channels/admin.env`, `deploy-admin.sh`'s `SWEEP_ENV`, and
  `cloudbuild.yaml`'s admin-service-deploy-tagged step -- and both deploy
  paths use `--set-env-vars`, which REPLACES the entire env block, so even
  a hand-set value would be wiped by the next deploy (the exact incident
  `SWEEP_SCHEDULER_SA_EMAIL` already documents one section up). Every Cloud
  Build status push was therefore rejected, permanently fail-closing
  `POST /api/deploys/webhook` with no test or alert noticing. Fixed by
  adding `PUBSUB_PUSH_SA_EMAIL` (a fixed literal, no gcloud lookup needed --
  `PUBSUB_PUSH_SA_NAME` is fixed in `setup-admin-service.sh`) to BOTH
  `deploy/channels/admin.env`'s `[SET_ENV_VARS]` (which `cloudbuild.yaml`'s
  admin-service target reads via `CHANNEL_ENV`, covering that path with no
  separate cloudbuild.yaml edit) and `deploy-admin.sh`'s `SWEEP_ENV`
  concatenation, mirroring `SWEEP_SCHEDULER_SA_EMAIL`/
  `MONTHLY_TOPUP_SCHEDULER_SA_EMAIL` exactly. Extended
  `test_admin_channel_file_matches_the_wrapper` (parity between the two
  live copies) and added
  `test_pubsub_push_sa_email_is_computed_without_a_gcloud_lookup` /
  `test_pubsub_push_sa_email_reaches_backend_extra_env` to
  `tests/test_deploy_admin_sweep_env_vars.py`, mirroring the existing
  sweep/monthly-topup pair. Mutation-verified three ways: deleting the
  `deploy-admin.sh` assignment, dropping it from the `SWEEP_ENV`
  concatenation, and changing `admin.env`'s value -- each reddens its
  corresponding test.
- DEFER (nit) -- `POST /admin/deploys`' audit row computed `channel` but
  never passed it as the top-level `channel=` kwarg `record_pending`
  accepts and `GET /admin/audit?channel=` filters on (the webhook's own
  sibling audit calls DO pass it) -- filed as bd `polyglot-pdf-g8uzb`
  rather than fixed here (nit, pre-filed by the reviewer).
- DEFER (nit) -- `docs/technical_guide.md` Surface contract 34's producers
  bullet claimed the webhook and `record_deployment.py` are "a second,
  independent writer of the same document," which was wrong before this
  round's fixes (the script minted a new document every time) and is now
  actually TRUE after the build_id-upsert fix above -- filed as bd
  `polyglot-pdf-mb4p0` by the reviewer; added a note to that bead recording
  that its own premise changed mid-review (the doc fix should describe the
  bead's CURRENT post-fix code, not what the reviewer originally observed)
  so whoever picks it up re-verifies against live code rather than trusting
  the bead's original description.

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
  fresh-eyes fix round; `_to_epoch()` timestamp normalizer added, fresh-eyes
  fix round 3)
- admin_backend/tests/unit/test_deploy_webhook.py (RFC3339-string fixtures +
  `TestToEpoch` unit coverage, fresh-eyes fix round 3)
- docs/components/admin-service.md
- docs/technical_guide.md
- admin_backend/services/cloud_build.py (fresh-eyes fix round 4: `_SHA`
  substitution added to the RepoSource)
- admin_backend/tests/unit/test_cloud_build.py (new, fresh-eyes fix round 4)
- scripts/record_deployment.py (fresh-eyes fix round 4: writes `ts`,
  upserts by `build_id` instead of blindly creating)
- tests/test_record_deployment.py (new, fresh-eyes fix round 4)
- deploy-admin.sh (fresh-eyes fix round 4: `PUBSUB_PUSH_SA_EMAIL` added)
- deploy/channels/admin.env (fresh-eyes fix round 4: `PUBSUB_PUSH_SA_EMAIL`
  added to `[SET_ENV_VARS]`)
- tests/test_deploy_admin_sweep_env_vars.py (fresh-eyes fix round 4: two
  new tests for `PUBSUB_PUSH_SA_EMAIL`)
- tests/test_cloudbuild_yaml.py (fresh-eyes fix round 4: parity test
  extended to `PUBSUB_PUSH_SA_EMAIL`)
