---
date: 2026-09-16
bead: polyglot-pdf-oqtm7
title: "chore(deploy): E4.6 deploy-*.sh become thin trigger wrappers; promotion-tiers + config-deployment doctrine rewritten"
sprint: 22
tags: [doctrine, refactor, testing]
---

## Trigger

Epic 4 bead 4.6 of `docs/sprint_22_admin-console_plan.md`. Beads 4.1, 4.2 and
4.4 had already moved every deploy stage into `cloudbuild.yaml` -- the verify
gate, the backend/frontend/editor/kits/rules/admin targets, the reachability
check, the staging-before-demo promotion gate. What remained was two engines
for the same job: the build, and the bash pipeline the wrappers still ran. That
is not merely untidy. The GATES live in the build, so every day the bash path
survived was a day a deploy could route around all of them by choosing a
different script.

## What shipped

**The wrappers.** `deploy-all.sh`, `deploy-staging.sh`, `deploy-demo.sh`,
`deploy-editor.sh`, `deploy-admin.sh`, `deploy-admin-console.sh` and
`backend/deploy-new.sh` no longer build or deploy anything. Each refuses a
dirty or unpushed tree (the 4.1 preflight, now on every wrapper rather than
two), then runs its targets' Cloud Build triggers at `git rev-parse HEAD`,
streams each build's log, and exits non-zero on the first failed build. Flags
and the per-instance-ask doctrine are untouched; only the engine changed.

`scripts/deploy_build_targets.sh` is the whole bash side. Two details are
load-bearing: `run_build_target` reads each build's FINAL STATUS from
`gcloud builds describe` rather than from `gcloud builds log --stream`'s exit
code (the log reader succeeding is not the build succeeding -- that shape is
how a deploy that deployed nothing reports green), and it takes the build id
from `triggers run`'s own `metadata.build.id` rather than "the most recent
build for this trigger", which would be the wrong build the moment two deploys
overlap.

`deploy-all.sh` keeps a LIBRARY half above its sourcing guard, because
`cloudbuild.yaml`'s backend and admin-service steps `source ./deploy-all.sh`
for `read_channel_section` / `read_channel_value`. Deleting those, or moving
them below the guard, breaks every backend and admin deploy at deploy time
with nothing local to catch it, so `test_deploy_channel_parity.py` now pins
exactly that.

**Two behaviours moved rather than being lost.** Deleting an inline stage is
only correct when the build does the same thing, and twice it did not:

- `deploy-demo.sh` shipped Firestore RULES and composite INDEXES as two
  stages; the `firestore-rules` target carried only the rules. Indexes now
  ship from that target too. Without this, `GET /admin/audit`'s four filtered
  queries would have started failing with `FAILED_PRECONDITION` the first time
  an index changed, and no local test could see it (scar #7's shape, applied
  to indexes instead of IAM).
- `deploy-admin.sh` injected `MONTHLY_TOPUP_SCHEDULER_SA_EMAIL`, which
  `deploy/channels/admin.env` did not carry. `--set-env-vars` REPLACES the
  service's whole env block, so a key missing from the channel file is a key
  REMOVED from the running service at the next deploy -- the monthly top-up
  route's OIDC gate would have fail-closed with a 503 and no alert. It moved
  to the channel file, and the guard that pinned it now DERIVES the required
  set from the `*_SA_EMAIL` vars the admin routes actually read, so a fourth
  caller identity is required the day its route reads it rather than the day
  someone remembers.

**The tests.** `tests/test_deploy_wrappers.py` drives the real scripts under
bash against a stubbed `gcloud` in a real clean-and-pushed temporary repo: each
wrapper's trigger sequence in order, both `--sha` and `_SHA` carrying the
current commit, verify running only when the commit has no `build_checks`
record, the first failed build stopping the rest, and -- as a SET over every
wrapper -- no surviving `gcloud run deploy` / `firebase deploy` /
`gcloud builds submit --tag` and no bash copy of the reachability gate.

Two test files were deleted because the code they read is gone
(`test_deploy_reachability_gate.py`, `test_deploy_admin_tag_flow.py`), one
cloudbuild test was replaced by its own docstring's instruction, and six more
were repointed at whichever file now holds the property. Nothing was dropped
without naming where the property went.

**Deferred:** three implementations of "is this kit publishable" now coexist
(the deploy-all.sh library, its twin in `scripts/deploy-form-kit.sh`, and
`cloudbuild.yaml`'s inline grep -- the only live one). Filed as bd
`polyglot-pdf-lm9n8` rather than folded in: consolidating them is a change to
the kits path, not to the deploy engine.

### Fresh-eyes round 2 (adopt / reject / defer)

**Adopted -- both rubric gaps, and the set they belonged to.** The reviewer
scored the doc criterion FAIL: `docs/technical_guide.md` still described the
mechanism this same diff deleted, in the Environments section and in Surface
contract 12's body, even though its sibling contracts 22 and 31b had been
rewritten. Both are fixed. Rather than fix the two cited spots, the whole SET
was enumerated first (`grep` for `deploy-all.sh`, `gcloud builds submit --tag`,
`BACKEND_NO_TRAFFIC_TAG`, `BACKEND_EXTRA_ENV`, `DEPLOY_CHANNEL`,
`FRONTEND_BUILD_CMD` across docs, tests and `cloudbuild.yaml`) -- CLAUDE.md scar
#8, and the reviewer's own note that the last two rounds of this bead had the
same shape. That found eight more true-yesterday statements: two env-var table
rows and the admin `/health` row naming `deploy-all.sh`/`deploy-admin.sh` as the
thing that sets or curls them, the `LINK_MINTING_ENABLED` fallback paragraph,
the `BACKEND_URLS_JSON` producer, contract 30's "the wrappers remain the live
deploy path" preamble, contract 29a's bash consumer, and the
`MONTHLY_TOPUP_SCHEDULER_SA_EMAIL` note -- plus six `cloudbuild.yaml` comments
and four test docstrings/messages pointing at the deleted stages. All fixed
together, in one pass.

**Adopted -- the dangling test-name reference.** The reviewer's third finding
(`tests/test_cloudbuild_yaml.py`'s docstring citing
`test_admin_channel_file_matches_the_wrapper`, renamed by this diff) was a
comment-only nit, but it is a member of the same set, so it was fixed with the
rest rather than deferred; the same docstring's claim that `deploy-admin.sh`
folds the live URLs into `BACKEND_EXTRA_ENV` was stale in the same sentence.

**Rejected:** nothing. No finding was refuted.

**Deferred:** the reviewer's own pre-existing find --
`docs/doctrine/promotion-tiers.md`'s stale "both deploy scripts set
`LINK_CHANNEL`" claim, byte-identical on `origin/dev` -- is filed as bd
`polyglot-pdf-4gvsa` and deliberately not fixed here.
`docs/sprint_22_admin-console_plan.md` also still describes the pre-E4.6
mechanism; it is the approved PLAN OF RECORD and is deliberately left as the
historical artifact it is.

No behavioural code changed in this round: docs, comments, docstrings and one
assertion message. The root suite was re-run (1958 passed, 93 skipped).

### Outer cross-surface round 1 (adopt / reject / defer)

The Opus outer review returned `GAPS-FOUND (3)` -- two blockers of the same
kind, one of a different kind, and all three adopted. Nothing was refuted.

**Adopted -- the index deploy is a permission the build identity does not
hold.** The bullet above ("two behaviours moved rather than being lost") moved
`firebase deploy --only firestore:indexes` out of `deploy-demo.sh` and into
the `firestore-rules` Cloud Build target. What it did not ask was who runs it
now. In the script it ran on an OPERATOR's owner-level account; in the build it
runs as `polyglot-cloudbuild-sa`, whose live policy is exactly
`artifactregistry.writer, datastore.user, firebasehosting.admin,
firebaserules.admin, logging.logWriter, run.admin`. `roles/firebaserules.admin`
is rules-only (the setup script's own comment says so), and
`roles/datastore.user` carries `datastore.schemas.list` and none of
`create`/`update`/`delete` -- confirmed against the live role definitions, not
recalled. So the step is a no-op list that passes by luck while
`firestore.indexes.json` is unchanged, and dies with `PERMISSION_DENIED` the
first time an index is added or edited -- taking the whole demo frontend deploy
with it, because `firestore-rules` runs BEFORE `frontend-demo` and the runner
stops at the first failure. `roles/datastore.indexAdmin` is added to
`scripts/setup-cloud-build.sh`'s `PROJECT_ROLES`, to
`test_cloud_build_sa_iam_envelope.py`'s `EXPECTED_BUILD_SA_PROJECT_ROLES`, and
-- found by the suite, not by the diff -- to `scripts/audit/infra_posture.sh`'s
`CLOUD_BUILD_SA_EXPECTED_ROLES`, the third home of the same list.

This is CLAUDE.md scar #7 landing on the bead that moved the call, so the fix
also closes the hole that let it through. The existing role pin is
collusion-proof between the script and the constant but reads NOTHING about
what the build actually calls, so a step added to `cloudbuild.yaml` needing a
role nobody granted keeps every assertion in that file green.
`BUILD_STEP_ROLE_REQUIREMENTS` maps each privileged command text in
`cloudbuild.yaml` to the role it needs, and the new
`test_every_privileged_build_step_has_the_role_it_needs` checks the build
against the grant. Mutation-verified per entry, not once: dropping each of the
four roles from BOTH the script and the constant reddens only the new test,
naming the command and the missing role -- the seven older assertions stay
green, which is the hole this closes.

**Adopted -- two tier-2 docs still naming a deleted code path.**
`docs/technical_guide.md` said the composite indexes were "deployed by
`deploy-demo.sh` (`firebase deploy --only firestore:indexes`)", and
`docs/standards/confirmation-and-audit.md` named `deploy-all.sh`'s
`BACKEND_ENV` as the producer of `CONFIRMATION_FIRESTORE_ENABLED`. Both name a
command that no longer exists anywhere, on the one contract this bead most
changed. The second one is the interesting miss: round 2's enumeration swept
variables a CALLER sets, not values the deleted stage PRODUCED, so the
producer-side moves (`CONFIRMATION_FIRESTORE_ENABLED`, `FIRMS_FIRESTORE_ENABLED`)
were outside the set it drew.

The set was re-enumerated on the producer axis before fixing either -- `grep`
for `firebase deploy` and for `BACKEND_ENV` across every tier-1 and tier-2 doc
-- which found two more of the same shape the reviewer had not cited:
`docs/technical_guide.md`'s `/admin/audit` route row (same indexes claim,
second site) and `docs/components/auth.md`'s deploy note (same claim about the
RULES half). All four fixed together, plus `config-deployment.md`'s build-SA
role list, which is the doc a reader consults before asking the very question
finding 1 asked.

**Rejected:** nothing.

**Deferred:** the reviewer's finding 4 is an explicit non-gap -- whether
`gcloud builds triggers run --substitutions=_SHA=...` MERGES with the trigger's
provisioned `_TARGET`/`_CHANNEL` rather than replacing them. It cannot be
settled without a real (paid, deploying) trigger run, and
`admin_backend/services/cloud_build.py` already committed to the same
assumption in bd `tb3kp`, so it is pre-existing rather than introduced here.
The first staging run confirms it by reading one line: the streamed log's first
line must be `Building target <X> at <sha>`, not `verify` -- filed as bd
`polyglot-pdf-4wk0b` so the check is not lost. Finding 5's three
non-blocking items were filed by the reviewer as bd `polyglot-pdf-q97d8`
(`DEPLOYMENT.md`/`README.md` still document the deleted bash engine), bd
`polyglot-pdf-vnniz` (~14 source comments naming a `deploy-*.sh` stage as an
env producer) and bd `polyglot-pdf-qjjse` (only `deploy-staging.sh` self-heals
a missing `build_checks` record), and are deliberately not fixed here.

**The IAM binding itself is PENDING-DEPLOY.** The code and the pins are
complete, but `roles/datastore.indexAdmin` reaches the live project only when
the maintainer runs `scripts/setup-cloud-build.sh` -- a provisioning run, one
command, gated like any deploy. Until it runs, the `firestore-rules` target
keeps passing on an unchanged `firestore.indexes.json` and would fail on the
first index change.

Suites re-run after the fixes: backend 3818 passed / 195 skipped,
admin_backend 706 passed, root 1958 passed / 93 skipped.

### Outer cross-surface round 2 (adopt / reject / defer)

`GAPS-FOUND (2)`. Both adopted; nothing refuted.

**Adopted -- the deleted form-kits stage took a live safety assertion with it,
and CI went red.** `tests/test_deploy_all_kit_gates.sh`'s
`assert_gated "deploy-all.sh"` greps that script for the guard CALL
(`if ! kit_is_complete "..."`), which vanished with the inline upload loop. The
harness exits 1 and `tests/test_deploy_all_kit_gates_wrapper.py` asserts exit 0
-- green on this Windows box only because the wrapper SKIPS when `bash` resolves
to the WSL shim, which is exactly the hole the wrapper's own docstring warns
about ("CI is ubuntu-latest, where bash runs natively"). Reproduced against Git
Bash directly: `REAL_EXIT=1`, one FAIL row.

Deleting the row was the wrong fix: it was the only thing pinning "every path
that uploads form kits guards each upload against a draft kit", and after this
diff `cloudbuild.yaml`'s `form-kits-upload` step is the SOLE publisher in the
deployed flow while carrying its own hand-inlined copies of the status-complete
grep and the two underscore skips, which nothing pinned at all.

So the set was enumerated before anything was fixed (scar #8). Every non-comment
`gcloud storage`/`gsutil` `cp`/`rsync` in a tracked `.sh`/`.yaml`:
`cloudbuild.yaml` (the build's kit upload and its manifest upload),
`scripts/deploy-form-kit.sh` (the hand-run publisher),
`scripts/pull-form-kits.sh` (a DOWNLOAD -- bucket to local, not a publisher)
and the harness itself. Two publishers, therefore two gate checks:

- The hand-run one keeps its existing `assert_gated` row, unchanged.
- The build step gets a NEW check that RUNS it rather than grepping it. Its
  script body is extracted from `cloudbuild.yaml`, the `$$` yaml escape is
  resolved, `PROJECT_ID`/`_TARGET` are supplied as env vars, `gcloud` is
  shadowed by a recording stub, and the body is executed against a synthetic
  kit tree holding one kit of each shape (complete, draft, no status field, no
  `metadata.json`, a top-level `_` kit, and a complete kit carrying `_drafts/`
  and `_archive/` rings). Eight assertions read the stub's log. This is the
  same extract-and-run pattern the harness already uses for
  `deploy-form-kit.sh`'s own helper copy, and for the same reason: a grep stays
  green through a reformat that breaks the filter.
- The no-bypass rows are now ENUMERATED from `git ls-files -- 'deploy-*.sh'
  'scripts/deploy-*.sh'` instead of hand-listing two wrappers. That widened the
  check from `deploy-demo.sh`/`deploy-production.sh` to all seven, and a new
  `deploy-*.sh` that starts uploading kits now fails here instead of being
  invisible because nobody remembered the literal list. `git ls-files`, not a
  directory scan -- tracked is what CI sees.
- `deploy-all.sh` drops out of the raw-glob loop, because it no longer uploads;
  its library half (the helpers the harness sources, and the channel parser
  `cloudbuild.yaml` sources) is untouched.

Mutation-verified per assertion, against the real `cloudbuild.yaml`, restoring
from git between runs: dropping the status-complete grep reddens exactly the
draft and no-status rows; dropping the top-level `_` skip reddens only the
`_scratchkit` row; NARROWING the child skip from `_*` to `_drafts)` reddens only
the `_archive` row (the general underscore rule, not one instance); renaming the
build step reddens the extraction guard plus both "did upload" rows; replacing
the upload with `true` reddens both "did upload" rows, proving they are not
vacuous; and adding a kit upload to `deploy-admin-console.sh` -- a wrapper the
old literal list did not cover -- reddens its new no-bypass row. Harness: 25 ->
38 assertions, `REAL_EXIT=0`.

One honest negative: deleting `[ -f "$meta" ] || continue` from the build step
leaves every row green, because `grep` on a missing file fails too and the
`|| continue` catches it. The line is a redundant fast path, not a guard, and
the test comment says so rather than letting the row be read as pinning it.

**Adopted -- a tier-2 doc naming a function this diff deleted repo-wide.**
`docs/components/config-deployment.md` asserted what
`verify_service_publicly_reachable()` does; that bash function is gone from
every file. The behaviour is still true of `scripts/verify_service_reachable.py`,
so only the symbol changed. The stale-symbol set was enumerated rather than
fixing the one cited line: outside the journal (the chronological record, which
keeps its own history), the live hits are `admin_backend/main.py`,
`admin_backend/tests/unit/test_admin_health.py`,
`backend/tests/unit/test_deploy_channel_isolation.py` and this doc. The three
CODE comments are already filed as bd `polyglot-pdf-h6kct` by the reviewer and
are deliberately left to it; the tier-2 doc is fixed here because it is
surface-authoritative and current-state-only.
`tests/test_deploy_wrappers.py`'s use of the name is a guard that the bash copy
stays deleted -- correct as written, untouched.

**Rejected:** nothing.

**Deferred:** the reviewer's finding 3 is four beads it filed itself --
`polyglot-pdf-68xz3` (stale citations to the deleted
`tests/test_deploy_reachability_gate.py` in six untouched files),
`polyglot-pdf-h6kct` (eleven untouched files describing the deleted bash engine
as live), `polyglot-pdf-qwxy1` (`DEPLOYMENT.md`/`README.md` documenting commands
that now refuse) and `polyglot-pdf-vus05` (only `deploy-staging.sh` self-serves
the `verify` record) -- none fixed here. Finding 4 is
`Dockerfile.oqtm7.bak`, an untracked mutation-test backup left in the MAIN
checkout, not in this worktree; this worktree's tree is clean and nothing is
committed from main, so it is reported rather than deleted from under whichever
session owns it -- filed as bd `polyglot-pdf-qk2pf`, which also notes the two
sibling strays (`grant_credits.bak.py`, `prep-3l2vp-deploy-admin-tag-flow.txt`)
already sitting there from earlier beads. Checked before filing: main's
`Dockerfile` is clean and byte-identical to the `.bak`, so no mutation is live. The two unverified items stay PENDING-DEPLOY by design: that
`gcloud builds triggers run` returns a build id (bd `polyglot-pdf-4wk0b` reads
it from the first staging run) and that `roles/datastore.indexAdmin` alone
suffices for `firebase deploy --only firestore:indexes`.

Suites re-run after the fixes: backend 3818 passed / 195 skipped, admin_backend
706 passed, root 1958 passed / 93 skipped, kit-gate harness 38 passed / 0
failed.

## Lessons

**Deleting a stage is a migration, not a deletion.** Both behaviour losses
here (indexes, the top-up identity) looked like ordinary lines in a script
being removed with the rest. Neither had a test on the build side, so both
would have shipped green. The check that found them was mechanical and cheap:
enumerate what the old stage SET or RAN, then look for each item on the new
side -- not "does the new side look equivalent".

**A substring guard over a whole file matches the comment.** Two assertions
went green under a mutation because the wrappers explain their targets in
prose: `"firestore-rules" in deploy_demo` passed after the target was deleted
from the list, and `'demo) SERVICE="polyglot-backend"' in build` passed after
a rename, because a SECOND arm elsewhere still matched. Both were fixed by
scanning code lines only and by checking EVERY occurrence rather than the
first. A first-match assertion is a set-guard that forgot it was one.

**Mutation-verify the mutation that matters.** The unknown-argument guard
survived deleting its own `case` arm entirely, because a separate
"nothing selected to deploy" backstop also exits non-zero with no triggers
run. The test was true, just not about the thing it named. Asserting that the
refusal NAMES the offending argument separated them.

## Doc freshness

- `docs/doctrine/promotion-tiers.md` -- "Deploy is moving into Cloud Build"
  rewritten as "Deploy runs on Cloud Build, from a pushed commit"; the
  promotion gate's "nothing deploys through this yet" caveat retired; the
  preflight, reachability, admin-tier and channel-specifics sections updated.
  Stamped.
- `docs/components/config-deployment.md` -- the Deployment section leads with
  the one engine and a per-wrapper target table; the four-bash-callers
  reachability paragraph and the two completeness sets are gone; every
  "local/manual, no CI deploy" claim removed. Stamped, and
  `scripts/deploy_build_targets.sh` added to **Tracks:**.
- `docs/components/admin-service.md` -- the deploy section plus four other
  places that described the old inline env assembly. Stamped.
- `docs/technical_guide.md` -- contracts 12, 22, 29a, 30 and 31b updated; NEW
  contract 36 records the `polyglot-<target>` trigger-name contract from the
  wrappers' side; the Environments section, two env-var rows, the admin
  `/health` row, the `LINK_MINTING_ENABLED` fallback, the `BACKEND_URLS_JSON`
  producer and the `MONTHLY_TOPUP_SCHEDULER_SA_EMAIL` note all repointed at the
  build (the second half of that list came out of the fresh-eyes round-2
  enumeration above). Stamped twice (it tracks the deploy scripts, and was
  already stale).
- `CLAUDE.md` -- the one-line "Deploy is local/manual" claim and the
  "Deployment / promotion" flow bullet.
- The other docs `check_doc_freshness.py` still reports STALE track files this
  bead never touched (`context-compression`, `jit-schema`, `tool-call-flow`,
  `voice-ai`, `websocket-routing`, and nine `standards/*`): reviewed the list,
  left alone -- none of their tracked files is in this diff.

- `docs/components/config-deployment.md` -- re-stamped in outer round 2: the
  post-deploy reachability check is named by its module
  (`scripts/verify_service_reachable.py`), not by the deleted
  `verify_service_publicly_reachable()` bash function.

Review outcomes recorded in the closeout ping.

## Files touched

- `scripts/deploy_build_targets.sh` -- NEW: the shared trigger runner.
- `deploy-all.sh` -- library half kept, inline stages deleted, thin
  channel-agnostic wrapper added.
- `deploy-staging.sh`, `deploy-demo.sh`, `deploy-editor.sh`,
  `deploy-admin.sh`, `deploy-admin-console.sh`, `backend/deploy-new.sh` --
  thin wrappers.
- `cloudbuild.yaml` -- the `firestore-rules` target ships the indexes too.
- `deploy/channels/admin.env` -- gains `MONTHLY_TOPUP_SCHEDULER_SA_EMAIL`;
  header rewritten as the only copy.
- `tests/test_deploy_wrappers.py` -- NEW.
- `tests/test_deploy_all_kit_gates.sh` -- the gate row that pointed at
  `deploy-all.sh`'s deleted upload loop now RUNS `cloudbuild.yaml`'s
  `form-kits-upload` step; the no-bypass wrapper set is enumerated from
  `git ls-files` (outer round 2).
- `tests/test_deploy_reachability_gate.py`, `tests/test_deploy_admin_tag_flow.py`
  -- DELETED.
- `tests/test_deploy_admin_sweep_env_vars.py`,
  `tests/test_deploy_admin_cors_origins.py`,
  `tests/test_deploy_admin_backend_urls.py`,
  `tests/test_deploy_admin_url_injection.py`,
  `tests/test_deploy_channel_parity.py`, `tests/test_cloudbuild_yaml.py`,
  `tests/test_setup_monitoring_script.py`,
  `backend/tests/unit/test_deploy_channel_isolation.py`,
  `admin_backend/tests/unit/test_firestore_indexes.py` -- repointed.
- `docs/doctrine/promotion-tiers.md`, `docs/components/config-deployment.md`,
  `docs/components/admin-service.md`, `docs/technical_guide.md`, `CLAUDE.md`.
