---
date: 2026-09-13
bead: polyglot-pdf-p4ale
title: "chore(iam): E4.5 dedicated Cloud Build service account, role pin, actAs bindings, deploy-plane IAM in one pin"
sprint: 22
tags: [security, testing, conventions]
---

## Trigger

Epic 4 (deploy control plane on Cloud Build from git, plan:
`docs/sprint_22_admin-console_plan.md`) bead 4.5. Bead 4.1
(`polyglot-pdf-1s3ko`) and 4.2 (`polyglot-pdf-ywxoh`) had already declared
`scripts/setup-cloud-build.sh`'s trigger-creation logic and every
`cloudbuild.yaml` target, but every trigger's `--service-account` flag
pointed at `polyglot-cloudbuild-sa` as a bare string -- nothing actually
created that service account or granted it a single role. A build run
against that trigger would fail at the very first `gcloud run deploy`
step with `PERMISSION_DENIED`, the exact CLAUDE.md scar #7 shape ("a mock
cannot tell you the real dependency is forbidden") on the deploy-plane
side rather than the request-handling side. This bead closes that gap and
pins it the same way the public backend's and admin service's own IAM
envelopes are already pinned.

## What shipped

`scripts/setup-cloud-build.sh` now provisions the build's own identity in
full: idempotent SA creation, a `PROJECT_ROLES` array (`run.admin`,
`firebasehosting.admin`, `firebaserules.admin`, `artifactregistry.writer`,
`logging.logWriter`, `datastore.user`) granted project-wide, a
`BUCKET_ROLES` array (`storage.objectAdmin`) scoped to the form-kits
bucket only, and an `ACTAS_TARGETS` loop granting resource-scoped
`roles/iam.serviceAccountUser` on BOTH `polyglot-backend-sa` and
`admin-backend-sa` -- deploying a Cloud Run revision that runs as a given
SA is itself a privileged act on that SA, distinct from `run.admin`
itself. The same script grants the Pub/Sub service agent
(`service-<PROJECT_NUMBER>@gcp-sa-pubsub.iam.gserviceaccount.com`)
`roles/iam.serviceAccountTokenCreator`, needed for the OIDC token bead
4.3's future build-status webhook subscription will mint -- folded in here
per the bead's own framing ("the whole deploy-plane IAM is in one pin")
even though bead 4.3 has not landed yet.

`scripts/setup-admin-service.sh` gains the mirror-image grant: a new
`CLOUD_BUILD_SA_ROLES` array grants `admin-backend-sa` actAs on
`polyglot-cloudbuild-sa` ONLY (resource-scoped), so the admin service's
future trigger route (bead 4.3, `admin_backend/services/cloud_build.py`)
can submit a build that runs as the build identity. `DEFERRED_ROLES`
shrinks from four entries to one: `roles/iam.serviceAccountUser` moved out
(now granted, as above); `roles/run.admin` and `roles/firebasehosting.
admin` are DELETED entirely rather than left deferred, because the admin
service never deploys anything itself -- Cloud Build does the deploying --
so neither role has a future consumer, and a deferred role with no
consumer is a dead expectation the pin test could never satisfy. Only
`roles/cloudbuild.builds.editor` (the `builds.create` call itself) still
awaits bead 4.3.

Two new/extended test files pin the whole envelope: new
`admin_backend/tests/unit/test_cloud_build_sa_iam_envelope.py` (the
sibling of `test_admin_sa_iam_envelope.py`, parsing
`setup-cloud-build.sh`'s own arrays so a role added to the script without
updating the pin fails CI -- exact role set, bucket-only scope, both actAs
bindings' scope, and the Pub/Sub grant), and new
`tests/test_setup_cloud_build_script.py` (script-text tests covering the
trigger side: every target names `polyglot-cloudbuild-sa` via the shared
`$BUILD_SA` variable -- exit criterion 3 -- plus idempotency and
dry-run-safety checks). `test_admin_sa_iam_envelope.py` itself gains the
actAs role in its envelope and two new scope-pinning tests mirroring its
existing bucket-scope pair.

### Fresh-eyes review round 1 -- adopt/reject/defer

The pre-PR fresh-eyes review (bd polyglot-pdf-p4ale) returned GAPS-FOUND
with four findings; here is what happened to each:

- **ADOPTED (blocker-class, fixed):**
  `test_dry_run_never_calls_gcloud`'s 20-line backward-lookback guard
  detection could match an unrelated, already-closed `if [ "$DRY_RUN" =
  false ]` block for a gcloud call placed shortly AFTER it rather than
  inside it -- reviewer mutation-verified this by inserting an ungated
  `gcloud ... --role="roles/owner"` right after the Pub/Sub block's `fi`;
  the old test passed when it should have failed. Replaced the fixed-
  window text search with a real if/else/fi nesting-depth stack
  (`_iam_section_gcloud_gate_violations` in
  `tests/test_setup_cloud_build_script.py`) so a call is only "gated"
  when it lexically sits inside its own governing `if`'s still-open
  branch. Mutation-verified against both the reviewer's exact
  reproduction and the second instance the reviewer predicted (an
  ungated call dropped between the PROJECT_ROLES and BUCKET_ROLES
  loops) -- both now correctly fail; the unmodified script still passes
  cleanly (22/22).
- **ADOPTED (blocker-class, fixed):** `EXPECTED_ACTAS_TARGETS` in
  `admin_backend/tests/unit/test_cloud_build_sa_iam_envelope.py` was
  declared and never consulted -- `test_build_sa_has_actas_bindings_on_
  both_runtime_sas` hardcoded the two SA variable names as literals
  instead. Rewrote the test to derive both the expected SA-variable
  names and the ACTAS_TARGETS array membership check from the constant
  itself (new `_named_array_block` helper alongside the file's existing
  `_named_array`). Mutation-verified two ways: removing one target from
  the script's `ACTAS_TARGETS` array now fails the test, and adding a
  bogus entry to `EXPECTED_ACTAS_TARGETS` itself now also fails it --
  the constant is genuinely load-bearing now, not decorative.
- **DEFERRED (nit, not fixed here):** `roles/run.admin` is granted
  project-wide even though the section's own comments argue against
  project-wide grants elsewhere -- the reviewer flagged this as a
  comment-completeness gap, not a functional bug or a rubric-fail (Cloud
  Run has no narrower built-in role for cross-service revision
  management, and this shape is inherited unchanged from
  `setup-gcp-project.sh`, not introduced by this diff). Filed as
  polyglot-pdf-nacfo.1 ("chore(nits): deferred review nits from
  polyglot-pdf-p4ale") rather than touched inline.
- **NOTED, no bead needed:** the reviewer's fourth item (the same
  20-line-lookback root cause could also misfire between the
  PROJECT_ROLES/BUCKET_ROLES/ACTAS_TARGETS loops themselves) is not a
  separate defect -- it is covered by the same structural fix above and
  was mutation-verified as part of that fix rather than filed
  separately.

## Lessons

The "deferred vs. deleted" distinction (scar #8's enumerate-the-set
discipline, applied to a shrinking set rather than a growing one) is
worth naming explicitly: a role that will NEVER be granted to a given SA
is a different fact from a role whose grant is merely postponed, and
conflating them leaves a dead expectation in `DEFERRED_ROLES` that a
future reviewer has to re-investigate from scratch. Deleting with a
comment saying why is cheaper than leaving it deferred forever.

## Doc freshness

`docs/components/config-deployment.md` (Tracks `scripts/setup-cloud-build.sh`)
and `docs/components/admin-service.md` (Tracks `scripts/setup-admin-service.sh`)
both bumped to 2026-09-13 with the new IAM detail. `docs/doctrine/
promotion-tiers.md` (no `Tracks:` line -- a doctrine doc, correctly skipped
by `check_doc_freshness.py`) updated in place since the bead named it
directly. Review outcomes recorded in the closeout ping.

## Files touched

- `scripts/setup-cloud-build.sh` -- provisions `polyglot-cloudbuild-sa`,
  its roles, its two actAs bindings, and the Pub/Sub service agent grant.
- `scripts/setup-admin-service.sh` -- `admin-backend-sa` actAs on the
  build SA; `DEFERRED_ROLES` shrunk to `cloudbuild.builds.editor` only.
- `admin_backend/tests/unit/test_admin_sa_iam_envelope.py` -- envelope,
  deferral, and new scope-pinning tests updated/added.
- `admin_backend/tests/unit/test_cloud_build_sa_iam_envelope.py` -- new.
- `tests/test_setup_cloud_build_script.py` -- new.
- `docs/components/config-deployment.md`, `docs/components/admin-service.md`,
  `docs/doctrine/promotion-tiers.md` -- IAM detail added, stamps bumped.
