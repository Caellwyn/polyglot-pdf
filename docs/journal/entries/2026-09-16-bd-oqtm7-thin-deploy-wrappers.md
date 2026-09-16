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
