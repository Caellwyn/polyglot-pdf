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

## What shipped -- fresh-eyes round 1 fixes

The fresh-eyes review found one blocker and two rubric-fails; all three
adopted (fixed in place), one nit filed as a follow-up bead:

- **ADOPTED (blocker):** `admin-service-deploy-tagged` ran `docker build`/
  `docker push` on `gcr.io/google.com/cloudsdktool/cloud-sdk:slim`, which
  does not bundle the Docker CLI -- every other docker build/push pair in
  this file (`backend-build-image`) deliberately runs on the dedicated
  `gcr.io/cloud-builders/docker` image. Split the docker build/push into
  its own new step, `admin-service-build-image`, on the correct image,
  ordered before `admin-service-deploy-tagged`. Without this fix the first
  real `_TARGET=admin-service` build would fail at "docker: command not
  found" and never deploy a tagged candidate revision.
- **ADOPTED (exit criterion 1 fail):** `tests/test_cloudbuild_yaml.py`'s
  `unimplemented-targets` coverage only ever checked the OLD 3-target
  `IMPLEMENTED_TARGETS` list (bead 4.1's `verify`/`backend-staging`/
  `backend-demo`) against the step's implemented pass-through arm; none of
  this bead's 8 new targets were pinned there, so a target silently dropped
  into the catch-all `*) ABORT: unknown target` branch would have passed
  untouched. Added `test_every_ywxoh_target_is_in_the_implemented_pass_
  through_arm`, parametrized over the independently-maintained
  `YWXOH_DEPLOY_TARGETS`, and mutation-verified it (removing `editor` from
  the pass-through arm turns exactly that parametrization red, the other 9
  stay green).
- **ADOPTED (misleading comment):** `staging-verified-gate`'s header comment
  claimed admin-service "is included here... this gate still runs for it
  (case-matched below)", but the case statement two lines later only
  matches `backend-demo|frontend-demo` -- admin-service falls into the
  `*) skip` arm and this step is a pure no-op for it. Code and tests were
  already correct (admin-service's actual demo-side gating is the separate
  `admin-service-staging-gate` step); only the comment's claim about its own
  step was false. Rewrote the comment to state plainly that admin-service is
  NOT case-matched here and point at the step that actually gates it.
- **DEFERRED (nit, filed as bead `polyglot-pdf-yg26r`):** an unused
  `import re` in `scripts/write_kits_manifest.py`, and `form-kits-upload`'s
  Cloud Build port dropping the schema-file-existence check
  `deploy-all.sh`'s bash original performs (a kit marked complete but
  missing its schema file gets uploaded rather than skipped with a
  warning -- a latent, low-severity gap since `write_kits_manifest.py`'s
  `index.json` build excludes it regardless).

Full backend + root suites re-run green after the fixes (1645 root tests
passed / 46 skipped; backend suite re-run in full).

## What shipped -- fresh-eyes round 2 fixes

Round 2 found one blocker and confirmed the other two rubric criteria pass.
Blocker adopted; two nits deferred as one follow-up bead.

- **ADOPTED (blocker, P1): `admin-service-staging-gate` could never be
  satisfied -- every admin-service Cloud Build deploy would fail forever.**
  The gate requires a `deployments` record with `channel=="staging"` for
  this sha/family, but `admin-service-record-deployment` (the only writer)
  used `--channel "${_CHANNEL}"`, and `scripts/setup-cloud-build.sh` fixes
  admin-service's trigger to `_CHANNEL=admin` always ("the admin service has
  no channel of its own"). Worse, the record step ran AFTER the gate check
  and the traffic shift in the SAME single-`_TARGET` build, so no prior
  build could ever have written the row either -- a structural bootstrap
  deadlock, not just a wrong literal. Fixed both halves together: (1)
  `admin-service-record-deployment` now hardcodes `--channel staging`
  (matching its `backend-record-deployment` / `frontend-record-deployment`
  siblings, and matching `record_deployment.py`'s own docstring, which
  already documented admin-service as a staging-channel writer); (2) the
  step now runs immediately after `admin-service-verify-tagged` (the tagged
  candidate's own health check is admin-service's equivalent of a separate
  staging deploy, since there is no separate staging tier for a
  single-instance service) and BEFORE `admin-service-staging-gate`, not
  after `admin-service-shift-traffic`. `docs/technical_guide.md`'s Surface
  contract 31c, which asserted the old (broken) composition as correct, is
  corrected to describe the actual required order and why it is reversed
  from backend/frontend's two-separate-builds shape.
  `tests/test_cloudbuild_yaml.py` gained: a literal-value assertion
  (`--channel staging`, not just "a --channel flag exists" -- the exact gap
  that let the wrong literal ship unpinned) on all three
  STAGING_RECORDING_TARGETS, and an explicit
  `admin-service-record-deployment < admin-service-staging-gate <
  admin-service-shift-traffic` ordering assertion in
  `test_admin_service_traffic_shift_carries_the_staging_gate`. Both
  mutation-verified: reverting the channel literal turns only the
  admin-service parametrization red (the other two stay green); reverting
  the step order turns both new/changed assertions red without touching
  backend-staging/frontend-staging.
- **DEFERRED (nits, filed as bead `polyglot-pdf-8ft81`):** the ported
  `verify_service_publicly_reachable()` wrapper loses the colored
  `[WARN]`/`[ERROR]` terminal output the prior extraction was specifically
  reviewed to preserve (cosmetic only -- message content and exit codes are
  unaffected); `scripts/write_kits_manifest.py`'s multi-PDF fallback
  selection changed from filesystem (`ls`) order to `sorted()` alphabetical
  order (deterministic is arguably better, and no kit in the current
  form-kits tree has more than one non-`form.pdf` PDF to exercise the
  difference).
- **NOTED, not scored as a gap:** whether `admin-console` (the live console
  site) should carry a staging-success gate the way
  `backend-demo`/`frontend-demo`/admin-service's traffic-shift do is a
  genuine pre-existing plan ambiguity (the "Admin-tier targets" bullet
  describes only a candidate-then-live sequence with no Firestore check),
  not something this diff introduced -- left as-is per the reviewer's own
  read, flagged here in case the maintainer wants `admin-console` gated too
  in a future bead.

Full backend suite (3825 passed / 67 skipped / 3 deselected / 1 xfailed) and
root suite (1645 passed / 46 skipped) re-run green after the round-2 fix,
from the worktree with `PYTHONPATH` set to it.

## What shipped -- cross-surface review round fixes

The Opus-5 outer cross-surface review found three BLOCKERs, all in
`cloudbuild.yaml` steps no unit test executes at runtime -- each adopted
(fixed in place, with a new mutation-verified runtime test); the pre-existing
`grep`-vs-JSON-parse divergence and the missing `kit_schema_file` check in
`form-kits-upload` were refuted as pre-existing/harmless per the review's own
trace, not fixed. One nit filed as a follow-up bead.

- **ADOPTED (blocker): `staging-verified-gate`'s `TARGET_FAMILY` derivation
  crashed with "`_TARGET`: unbound variable" on every `backend-demo`/
  `frontend-demo` build.** `TARGET_FAMILY="$${_TARGET%-demo}"` applies a bash
  suffix-strip directly to the literal substitution token `_TARGET` --
  Cloud Build substitutions are not bash variables, and `$$` defers the
  expression to bash verbatim, so under `set -euo pipefail` this failed
  before ever reaching `promotion_gate.py`. The staging-before-demo gate
  therefore never actually ran; it failed CLOSED (nothing unsafe shipped),
  but the gate the bead exists to add was not in force. Fixed by assigning
  the substitution to a real bash variable first (`TGT="${_TARGET}"`) and
  stripping the suffix off `TGT`. New test
  `test_staging_verified_gate_actually_evaluates_at_runtime` renders the
  step's script with Cloud Build's own substitution pass simulated
  textually and actually EXECUTES it under bash with a stubbed `python`/
  `pip`, asserting the stub is reached with the right `--target-family` --
  closing the gap the existing substring-matching test
  (`test_demo_side_targets_carry_the_staging_success_gate`) could not see
  (syntax-valid and pattern-matching text is not the same as a script that
  runs). Mutation-verified: reverting to the un-assigned `$${_TARGET%-demo}`
  reproduces the exact `_TARGET: unbound variable` crash.
- **ADOPTED (blocker): `frontend-*` builds never set `VITE_APP_CHANNEL`,
  so a staging build would silently claim the demo channel and touch the
  demo's Firestore data.** Both channels build the identical Vite mode
  (`build:schema:demo`), so `import.meta.env.MODE` cannot distinguish them;
  `frontend/src/shared/config.ts::getAppChannel()` reads `VITE_APP_CHANNEL`
  and falls back to `'demo'` when unset, and that value is appended as
  `?channel=` on every firm-scoped admin-service call. `deploy-staging.sh`/
  `deploy-demo.sh` both export it explicitly for exactly this reason (bd
  polyglot-pdf-z4ljj); the build step never did. Fixed by exporting
  `VITE_APP_CHANNEL="${_CHANNEL}"` in `frontend-build-deploy` before the
  build runs. Second half of the same finding: `frontend-resolve-urls`
  already aborted when the live BACKEND URL could not be resolved, but
  silently fell through when the ADMIN service URL could not be resolved,
  and `frontend-build-deploy` then exported that empty value
  UNCONDITIONALLY -- overriding the committed `frontend/.env.demo` fallback
  and leaving `getAdminApiBaseUrl()` returning `''`, so firm-console calls
  would become relative paths Hosting's `/api/**` rewrite routes to the
  VOICE backend instead of the admin service. Fixed both ends: added the
  same ABORT-on-unresolved behavior for the admin URL (matching
  `deploy-all.sh:885-892`'s "an explicit channel was selected -> abort"
  rule, which always applies here since Cloud Build's `_CHANNEL` is never
  unset), and additionally guarded the export in `frontend-build-deploy`
  itself (matching `editor-build-deploy`'s existing `if [ -n "$$..." ]`
  pattern) as defense in depth. Four new tests, two static (the export/abort
  text is present) and two that actually RUN the rendered scripts under bash
  with stubbed `npm`/`gcloud` to prove the environment `npm` sees actually
  contains the right `VITE_APP_CHANNEL` and `VITE_ADMIN_API_BASE_URL`
  values. Mutation-verified against the pre-fix step bodies.
- **ADOPTED (blocker): a `form-kits` build sourced from a tarball would
  silently overwrite the demo's live form list with an EMPTY manifest and
  exit 0.** `.gcloudignore` excludes `form-kits/`, and `form-kits` was not
  in `require-connected-source-for-site-targets`'s case list; a tarball
  build therefore proceeded with `form-kits/` absent, and
  `write_kits_manifest.py`'s `build_manifest()` treats a missing directory
  as "zero kits" by design (a deliberately lenient, already-pinned
  library-level contract for legitimate early-bring-up states) -- so the
  manifest step wrote `{"forms": []}` and the upload step happily shipped
  it over the real one. Two independent fixes, both applied: (1) added
  `form-kits` to `require-connected-source-for-site-targets`'s case arm, so
  a tarball-sourced `form-kits` build now refuses for the same reason the
  site targets do; (2) `write_kits_manifest.py`'s CLI `main()` now refuses
  outright (exit 1, no file written) when `--form-kits-dir` does not exist
  at all, as a second independent layer for any OTHER caller -- WITHOUT
  changing `build_manifest()`'s own pure-function contract, which stays
  lenient on a missing directory (pinned by the pre-existing
  `test_nonexistent_form_kits_dir_produces_an_empty_manifest`) since an
  EXISTING-but-empty/all-draft directory is a legitimate state during
  initial setup. New tests: a connected-source-gate test using a case-arm-
  anchored regex (not a bare substring match, which a stray comment mention
  of "form-kits" would have satisfied even with the case arm itself
  unfixed -- caught by hand while writing the mutation-verify pass) and two
  CLI-level tests (refuses a missing directory; still succeeds on an
  existing empty one). Mutation-verified all three.
- **REFUTED (per the review's own trace, not fixed):** the review noted two
  findings and explicitly classified both as pre-existing or harmless
  rather than gaps to close, and this round agrees: `form-kits-upload`'s
  inline `grep -Eq '"status".*"complete"'` is byte-faithful to
  `deploy-all.sh`'s own `kit_is_complete`, so the grep-vs-JSON-parse
  divergence between the upload loop and the manifest builder already
  ships in bash today -- this diff does not worsen it. Separately, the
  upload loop's omission of the `kit_schema_file` check the manifest
  builder applies only means a schema-less kit's FILES get uploaded to GCS
  while its manifest entry stays absent (unreachable, not broken) -- also
  not a regression this diff introduces. Neither required a code change.
- **DEFERRED (nit, filed as bead `polyglot-pdf-ucyw0`):** `docs/technical_
  guide.md`'s `Last updated` stamp was not bumped despite the ~145 lines
  this bead added (Surface contract 31), and `scripts/setup-cloud-build.sh`'s
  TARGETS comment still says "the ones ... has not implemented yet" (plural)
  when only `landing` remains unimplemented. Neither affects behavior.

Full backend suite (3825 passed / 67 skipped / 3 deselected / 1 xfailed,
matching the review's own baseline exactly), admin_backend suite (515
passed, likewise matching), and root suite (1654 passed / 46 skipped -- the
review's 1645 baseline plus the 9 new tests this round added: 2 for the
`staging-verified-gate` fix, 4 for the `VITE_APP_CHANNEL`/admin-URL fix, 3
for the `form-kits` connected-source fix) re-run green from the worktree
with `PYTHONPATH` set to it.

## What shipped -- cross-surface review round 2 fixes

The Opus-5 outer cross-surface review found three more BLOCKERs, all again
in `cloudbuild.yaml` paths no test executed at runtime -- all three adopted
(fixed in place, each with a new mutation-verified test); the one non-
blocker finding (`admin-service-staging-gate` is tautological within its
own build) was filed as its own bead rather than fixed here, per the
review's own read that the fix is a design call overlapping bead
`polyglot-pdf-tb3kp`'s territory.

- **ADOPTED (blocker): `scripts/promotion_gate.py` could not import its own
  predicate under its REAL invocation, so every gated build step
  (`backend-demo`, `frontend-demo`, `admin-service`) died with a raw
  `ModuleNotFoundError` traceback instead of returning a 0/1 verdict.**
  `cloudbuild.yaml` invokes it as `python scripts/promotion_gate.py` from
  `/workspace`, which puts `/workspace/scripts` (this file's own directory),
  not `/workspace`, on `sys.path[0]` -- and `admin_backend` is a repo-root
  package, so the module-scope `from admin_backend... import
  staging_verified` raised before `argparse` ever ran. The prior round's
  test (`test_promotion_gate_module_and_cli_agree_on_the_predicate`) only
  substring-matched the import line, and the one test that DID execute a
  build step (`test_staging_verified_gate_actually_evaluates_at_runtime`)
  stubbed out the `python` binary entirely, so neither could see this.
  Fixed with a `sys.path.insert(0, <repo root>)` before the import, matching
  the convention already used by ~14 other `scripts/*.py` files that import
  repo-root packages (`scripts/read_confirmations.py`,
  `scripts/bootstrap_admin_user.py:110`). New test
  `test_promotion_gate_cli_actually_imports_under_its_real_invocation`
  spawns the REAL interpreter (not a stub) against the real file, cwd'd at
  the repo root exactly as Cloud Build does, with `PYTHONPATH` explicitly
  stripped from the child's environment -- this repo's own pytest-running
  convention (`PYTHONPATH=<worktree>`) would otherwise put the repo root on
  `sys.path` FOR the test and hide the exact bug it exists to catch (a real
  trap this round found while writing the test: the first version of the
  test passed against the UNFIXED module because it inherited the test
  runner's own `PYTHONPATH`). Mutation-verified against the pre-fix module
  with `PYTHONPATH` unset.
- **ADOPTED (blocker): `admin-service-deploy-tagged`'s `--set-env-vars`
  omitted `ADMIN_SERVICE_URL` and `BACKEND_URLS_JSON`, silently wiping both
  on every Cloud Build admin-service deploy.** `--set-env-vars` REPLACES the
  service's entire env block (the exact incident `deploy-admin.sh`'s own
  comment records), and `admin.env` deliberately excludes both keys because
  each needs a live `gcloud run services describe` lookup at deploy time --
  `deploy-admin.sh` resolves them inline, but the Cloud Build step built its
  env from only the channel file's three static keys. Consequence in
  untouched files: `admin_backend/routes/sweep_routes.py`'s `_audience()`
  returns `""` with no `ADMIN_SERVICE_URL`, so the refund sweep's OIDC gate
  503s; `admin_backend/routes/ops_routes.py`'s `_backend_urls()` returns
  `{}`, so `GET /admin/health` reports every channel `configured: false`.
  The existing `test_admin_channel_file_matches_the_wrapper` could not see
  this -- it only pins the three keys admin.env DOES declare. Fixed by
  porting `deploy-admin.sh`'s exact live-lookup logic (three `gcloud run
  services describe` calls, the same `2>/dev/null || true` not-yet-deployed
  fallback, the same `demo=<url>;staging=<url>` wire format for
  `BACKEND_URLS_JSON`) into the Cloud Build step before its `gcloud run
  deploy` call. Two new tests: one pins the COMPLETE env var set as a
  property (not the three admin.env already covers, per CLAUDE.md scar #8),
  the other actually EXECUTES the rendered step under bash with a stubbed
  `gcloud` and asserts the live-resolved URLs reach the final `gcloud run
  deploy` invocation's `--set-env-vars` string. Writing that second test
  surfaced a Windows/Git-Bash-specific trap: a `tmp_path.as_posix()` PATH
  entry (`C:/Users/...`) is not resolved by Git Bash's PATH lookup AT ALL --
  not a stub-vs-real conflict, the lookup silently falls through to
  whatever real binary of that name is on the system PATH with no error.
  (This nearly hung the test on the REAL `gcloud`'s interactive
  API-not-enabled prompt against a fake project, and on inspection affects
  at least one PRE-EXISTING test in this same file the same way --
  `test_staging_verified_gate_actually_evaluates_at_runtime`'s `python`/
  `pip` stubs are never actually reached either, though its assertions
  happen to still pass against the real interpreter; not touched here since
  it is out of this round's scope -- filed as bead `polyglot-pdf-ym9gl`.)
  Fixed for the new test by
  asking bash itself for `tmp_path`'s mount-mapped POSIX path
  (`subprocess.run([bash, "-c", "pwd"], cwd=tmp_path)`) rather than trusting
  `pathlib`'s own slash-flipping. Both new tests mutation-verified against
  the pre-fix step body.
- **ADOPTED (blocker): `firestore-rules-deploy` ran `npx firebase-tools` on
  `gcr.io/google.com/cloudsdktool/cloud-sdk:slim`, which ships no Node/npx
  at all.** It was the only one of six `npx`/`npm` steps in the file not on
  `node:22`; the target fails outright with "npx: command not found" on its
  first real run, and `firestore-rules` is the target that ships this
  bead's own new `deployments`/`build_checks` deny blocks, so the rules stay
  unprotected until someone deploys them by the old bash path. Fixed by
  moving the step to `node:22` (no gcloud call is needed in this step, so
  unlike `admin-console-resolve-url` it needs no separate cloud-sdk step
  split out). New test `test_no_step_runs_npx_or_npm_on_a_non_node_image`
  pins this as a PROPERTY of the whole file (no step may combine `npx`/`npm`
  with a non-node image), mirroring
  `test_no_step_pip_installs_into_an_externally_managed_interpreter`'s
  existing shape for the analogous pip/PEP-668 image split, so a future
  step reintroducing this mistake fails here too regardless of which step
  it is. Mutation-verified: reverting the image to `cloud-sdk:slim` turns
  exactly this test red, naming `firestore-rules-deploy`.
- **FILED AS A BEAD, not fixed here (`polyglot-pdf-xa4kx`):**
  `admin-service-staging-gate` reads a `deployments` row that
  `admin-service-record-deployment` unconditionally wrote three steps
  earlier in the SAME build, so the gate can never fail -- the traffic
  shift IS genuinely gated, but by `admin-service-verify-tagged`'s `/health`
  probe, not by the promotion gate the step's own comment and
  `docs/technical_guide.md` contract 31c both claim. Left as a bead rather
  than fixed inline because the fix is a design call (drop the step, or
  split the target into two builds so the row and the gate live in
  different builds the way backend/frontend already do) that overlaps bead
  `polyglot-pdf-tb3kp`'s (4.3/4.4) territory.

Full backend suite (3825 passed / 67 skipped / 3 deselected / 1 xfailed,
matching the prior round's baseline exactly), admin_backend suite (515
passed, likewise matching), and root suite (1658 passed / 46 skipped -- the
prior round's 1654 baseline plus the 4 new tests this round added) re-run
green from the worktree with `PYTHONPATH` set to it.

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
