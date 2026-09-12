---
date: 2026-09-12
bead: polyglot-pdf-ywxoh
title: "feat(deploy): E4.2 remaining Cloud Build targets, in-build gates, staging success row, ONE reachability gate module"
sprint: 22
tags: [testing, refactor, conventions]
---

## Trigger

Bead `polyglot-pdf-ywxoh` is Epic 4 bead 4.2 of the sprint-22 admin-console
plan (`docs/sprint_22_admin-console_plan.md`, "Epic 4 -- Deploy control
plane"). Bead 4.1 (`polyglot-pdf-1s3ko`) shipped `cloudbuild.yaml` with the
`verify` and `backend-<channel>` targets working end to end, and declared
every other named target (`frontend-<channel>`, `editor`, `form-kits`,
`firestore-rules`, `admin-service`, `admin-console-candidate`,
`admin-console`) as a step that fails loudly with "target not implemented"
rather than silently succeeding. This bead fills those in, moves the
staging-before-demo gate into the build itself, and ports the Cloud Run
reachability check -- previously four byte-identical bash function copies --
to one python module both bash and the build call.

## What shipped

**The remaining `cloudbuild.yaml` targets.** Each does what the matching
`deploy-all.sh`/`deploy-editor.sh`/`deploy-admin-console.sh`/`deploy-admin.sh`
stage does today: `frontend-<channel>` resolves the live backend and admin
service URLs in an earlier step, hands them forward through the shared
`/workspace` (Cloud Build substitutions are fixed at trigger time, so a later
step cannot re-resolve a "live" value), then builds and deploys the channel's
Hosting target; `editor` and `admin-console-candidate`/`admin-console` mirror
their bash equivalents' build-then-deploy sequence; `form-kits` uploads the
status-complete kits and a generated manifest; `firestore-rules` runs
`firebase deploy --only firestore:rules` (a demo action regardless of which
channel invoked it, since rules are project-wide); `admin-service` deploys a
tagged no-traffic revision, verifies it at its own stable tag URL, checks the
staging gate, then shifts traffic -- `deploy-admin.sh`'s sequence moved into
the build. `landing` stays a named-but-failing step: the plan leaves it an
open maintainer call, not an oversight.

**In-build gates.** `staging-verified-gate` runs for `backend-demo` and
`frontend-demo`; `admin-service-staging-gate` runs for the admin service's
traffic-shift half only (its tagged-candidate deploy is its own staging
tier, verified independently). Both call the new `scripts/promotion_gate.py`,
a thin CLI over a placeholder pure predicate,
`admin_backend/services/promotion_gate.py::staging_verified(target_family,
sha, deployments)` -- a demo build for `(family, sha)` is allowed only if a
successful staging `deployments` record exists for the SAME family and sha,
with NO recency rule (an older verified sha is not invalidated by a newer
staging deploy of a different sha; that is the deliberate rollback case).
This module is a placeholder bead `polyglot-pdf-tb3kp` (4.4) EXTENDS with an
admin route and a richer test suite, not a throwaway this bead will replace --
one function, two eventual callers, so the build gate and the future route
can never disagree about what "verified" means.

Each staging target's LAST step (`backend-record-deployment`,
`frontend-record-deployment`, `admin-service-record-deployment`) writes its
own `deployments/{auto}` row via the new `scripts/record_deployment.py`, so a
bash-triggered build's own success is durable the moment the build finishes
without racing bead 4.3's future Pub/Sub webhook.

`require-connected-source-for-site-targets` refuses an empty `COMMIT_SHA` for
every site target -- `.gcloudignore` now also excludes `admin-console/`
alongside `frontend/`/`schema-editor/`/`landing/`, so a tarball build cannot
see those directories at all, and this turns that into an early, loud
refusal instead of a confusing mid-build failure well after the tree upload.

**ONE reachability gate module.** `scripts/verify_service_reachable.py`
ports the IAM-policy reachability check (the `get-iam-policy --flatten
--filter` query, the exact `roles/run.invoker` match, warn-vs-fatal
severity) out of four byte-identical bash function bodies
(`deploy-all.sh`, `backend/deploy-new.sh`, `deploy-editor.sh`,
`deploy-admin-console.sh`) into one python module, with an injectable
`gcloud_runner` for direct unit testing with no subprocess/gcloud stub
needed. All four bash functions are now thin wrappers: resolve a python
interpreter (the same `find_manifest_python`-style fallback used elsewhere
in this repo), resolve the module's path relative to the wrapper's own file
(two candidate depths, since `backend/deploy-new.sh` sits one directory
below the other three), shell out, and `exit 1` on a non-zero return so the
calling script still terminates -- the bare-command-shape requirement from
the original reachability-gate beads carries over unchanged. Three
`cloudbuild.yaml` steps (`backend-reachability-gate`,
`editor-reachability-warn`, `admin-console-reachability-warn`) call the same
module directly on `cloud-sdk:slim` (which bundles its own `python3` for
gcloud's internal use -- `python:3.12` has no `gcloud` binary on PATH for
the module's default `gcloud_runner` to shell out to).

**`scripts/write_kits_manifest.py`** ports `deploy-all.sh`'s inline bash
manifest-generation loop (the complete-gate, the `_`-prefix skip, custom-
schema-filename resolution, label/PDF precedence) to python, built as a
dict and `json.dumps`'d so an invalid-JSON manifest is structurally
unreachable rather than merely validated after the fact. `deploy-all.sh`'s
form-kits stage now calls it instead of the ~70-line inline loop.

**Firestore rules.** `deployments` and `build_checks` both gain full client
deny blocks -- neither has a legitimate browser caller, and a client-SDK
write to either could forge a gate result (a fake successful staging deploy,
or a fake passing test run).

## Lessons

Building the new `cloudbuild.yaml` steps surfaced the SAME ordering bug
twice, independently, in the same development session: a gate step
(`staging-verified-gate`, then separately
`require-connected-source-for-site-targets`) was written correctly in
isolation but placed AFTER the steps it was meant to guard, because Cloud
Build's step list has no structural nesting to make "this guards that" a
compiler-checked property -- only step ORDER does. Both were caught by
tests that assert POSITION (the gate's index versus the guarded step's
index), not merely PRESENCE (the gate step exists and mentions the right
target). A presence-only test would have stayed green through both bugs.
This generalizes the existing lesson from bead 1s3ko's own
`test_the_build_checks_gate_precedes_every_deploy_step` (which this bead's
new tests follow the same shape as) -- worth restating here because it
recurred even with that precedent already in the file: in a step-list build
definition, EVERY new gate needs an explicit ordering test from day one, not
just a "the gate step exists" test, because writing the step correctly and
placing it correctly are two independent mistakes.

## Doc freshness

`docs/components/config-deployment.md`: the reachability-gate section
rewritten from "THREE byte-identical bash copies" to the one-module/four-
wrapper/three-build-step shape; `URL_BAKING_SCRIPTS` gains
`deploy-admin-console.sh`; the `admin.env` "declarative today" note
corrected now that `cloudbuild.yaml`'s `admin-service` target reads it
directly. Tracks line extended with every new script/module; Last updated
bumped to 2026-09-12.

`docs/technical_guide.md` Surface contracts gains entry 31 (the
`deployments/{id}` audit row, the reachability module's four-caller/three-
build-step shape, the staging-before-demo gate's build-side wiring, the
site-target connected-source requirement). Contract 30's stale note about
bead `polyglot-pdf-ywxoh` (this bead) "switching the wrapper over" is
corrected to name the actual remaining bead (`polyglot-pdf-oqtm7`, 4.6),
since this bead only made the build ALSO read `admin.env` -- `deploy-admin.sh`
itself is unchanged.

`docs/sprint_22_admin-console_plan.md` was read but not edited -- the plan
document has no per-bead status markers; `bd` is the system of record for
bead state.

Review outcomes recorded in the closeout ping.

## Files touched

- `scripts/verify_service_reachable.py` (new) -- the ONE reachability gate module
- `tests/test_verify_service_reachable.py` (new) -- direct unit tests via dependency injection
- `deploy-all.sh`, `backend/deploy-new.sh`, `deploy-editor.sh`, `deploy-admin-console.sh` -- gate function now a thin wrapper; `deploy-all.sh`'s manifest loop now calls `write_kits_manifest.py`
- `tests/test_deploy_reachability_gate.py` -- rewritten to prove the four wrappers are thin calls, executed end to end
- `admin_backend/services/promotion_gate.py` (new) -- the pure staging-before-demo predicate
- `admin_backend/tests/unit/test_promotion_gate.py` (new)
- `scripts/promotion_gate.py` (new) -- the build-side CLI over the predicate
- `scripts/record_deployment.py` (new) -- writes `deployments/{auto}` rows
- `scripts/write_kits_manifest.py` (new) -- ports the manifest-generation loop
- `tests/test_write_kits_manifest.py` (new)
- `cloudbuild.yaml` -- every remaining target + gate implemented
- `.gcloudignore` -- excludes `admin-console/`
- `scripts/setup-cloud-build.sh` -- trigger entry for `admin-console-candidate`
- `tests/test_cloudbuild_yaml.py` -- extended per exit criterion 1
- `firestore.rules` -- deny blocks for `deployments` and `build_checks`
- `backend/tests/unit/test_firestore_rules_text.py` -- both collections added to the enumerated set
- `docs/components/config-deployment.md`, `docs/technical_guide.md` -- updated
