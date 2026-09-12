---
date: 2026-09-11
bead: polyglot-pdf-1s3ko
title: "feat(deploy): E4.1 cloudbuild.yaml (verify + backend targets), deploy/channels/*.env, parity test rewrite, preflight refusal, trigger setup script"
sprint: 22
tags: [doctrine, testing, conventions]
---

## Trigger

Epic 4 of the sprint-22 admin-console program plan (`docs/sprint_22_admin-console_plan.md`,
"Cloud Build layout") moves deploys off the maintainer's laptop and into Cloud
Build, so that the human path and the eventual admin-console path drive ONE
engine rather than two that drift. This bead is the first of that epic and
deliberately the declarative half: it builds and tests everything offline and
runs nothing.

It runs nothing because it cannot. Building an arbitrary commit of a PRIVATE
repo needs the 2nd-generation Cloud Build GitHub connection, which is a
one-time interactive OAuth in the Cloud Build console that only the maintainer
can perform. The bead says so explicitly -- declare everything, run nothing --
so the first real build is recorded PENDING-DEPLOY rather than FAIL.

The real blocker this epic exists to remove is subtler than "deploying is
manual." Today five deploy targets for one commit would each re-run the test
suites, and nothing stops a commit whose suites failed from being deployed at
all, because the only gates live in bash wrappers a caller can simply not use.

## What shipped

**The config left bash.** The per-channel Cloud Run settings -- `VERTEXAI`, the
`LINK_*` set, `CORS_EXTRA_ORIGINS`, the Secret Manager binding, the runtime
service account -- existed only as an inline `BACKEND_EXTRA_ENV` string inside
`deploy-staging.sh` and `deploy-demo.sh`. A Cloud Build step cannot read a bash
string. The only way for the build to deploy the same service was to RESTATE
that config, which is precisely the drift `tests/test_deploy_channel_parity.py`
was written to catch, reintroduced at a second site.

They now live in `deploy/channels/<channel>.env` as plain `KEY=value` data
under three section headers (`SET_ENV_VARS`, `SET_SECRETS`, `SERVICE_ACCOUNT`),
each mapped to its own `gcloud run deploy` flag. `deploy-all.sh` gained one
parser selected by a `DEPLOY_CHANNEL` env var, and the `cloudbuild.yaml` backend
step SOURCES `deploy-all.sh` and calls the same two functions rather than
carrying a second copy of the format. `SERVICE_ACCOUNT` is explicit and
versioned for the first time -- it had been an inline `SA_EMAIL` constant.

The three constants that became dead (`SA_NAME`, `SA_EMAIL`,
`BACKEND_SECRETS_COMMON`) were deleted, not left behind. A constant nothing
forwards is the "looks configured, reaches nothing" defect the parity test
exists for; leaving them would have been that bug with a fresh coat of paint.

**The gate moved inside the build.** The `verify` target runs the backend,
frontend and admin-console suites once for a SHA and writes
`build_checks/{sha}`. Every deploy target FIRST step requires that record.
So five targets for one commit pay one test run, and -- the part that matters
-- a commit whose suites failed cannot deploy by ANY route, bash-triggered or
console-triggered, because the gate is not in a wrapper anyone can bypass.
`scripts/record_build_check.py` fails CLOSED: a Firestore read that errors
refuses the deploy, since a gate that waves things through when it cannot check
is not a gate.

**The wrappers refuse a dirty or unpushed tree.** `scripts/deploy_preflight.sh`
runs before anything else in both channel wrappers. Both refusals protect one
claim: a build runs from a COMMIT, and `build_checks/{sha}` says that the suites
for that commit passed. A tarball build of a dirty tree ships uncommitted code
under a SHA the gate vouched for -- the record is not wrong about the commit, it
is about a different tree than the one that shipped. And a SHA that exists on
one laptop can never be rebuilt by the admin service, which triggers by SHA.

**The parity test was rewritten as a diff.** The old version parsed two bash
scripts with regexes and had to track quoting, comment stripping, continuation
lines and transitive variable resolution -- it had paid for a bug in each of
those. The config is now data in two files of identical shape, so the guard is
a diff, which cannot be defeated by rewriting the shell around it.

**Deferred, on purpose.** `deploy/channels/admin.env` ships but is declarative:
two existing guards pin those values inside `deploy-admin.sh`, so switching
that wrapper over belongs with the `admin-service` build target in bead
`polyglot-pdf-ywxoh` (4.2). While both copies exist they are pinned equal, so
they cannot drift in the interval. The remaining build targets are declared as
steps that FAIL with "target not implemented" rather than being absent -- a
target matching no step would build nothing and report SUCCESS, and the console
would record a green deploy that deployed nothing.

## Lessons

**Mutation testing found two weak assertions that review would have cost a
round each.** `assert "exit 1" in body` passed with the not-implemented arm
flipped to `exit 0`, because a DIFFERENT arm in the same step supplied the
literal. And a whole-file `--region=` check passed with the flag deleted from
the trigger-create invocation, because the closing echo that tells the operator
how to RUN a trigger still mentioned it -- a region in the instructions and
none in the creation. Both are the same shape: a substring that is present for
a reason unrelated to the property under test. The fix in both cases was to
read the specific arm, or the parsed invocation, rather than the file. This is
the containment-vs-proximity lesson this repo has paid for before, and it only
surfaced because the mutations were actually run.

**A guard on a gate must pin POSITION, not existence.** The build_checks gate
entire protection is that it runs before the deploy. Asserting that a gate step
exists passes with that step moved to the end of the build, where it gates
nothing. The test walks the step list and requires the gate index to be lower
than every step that runs `gcloud run deploy`, `docker push` or `firebase
deploy` -- and it asserts that at least one such step was FOUND, so a drifted
extractor fails loudly instead of passing vacuously. Verified by moving the
gate, not only by deleting it.

**`shutil.which("bash")`, never a bare `"bash"`.** On this Windows box a bare
name resolves to the WSL bash, which cannot see the Git-Bash filesystem and
fails every script with a relay error that reads exactly like a syntax error.
The repo already knew this (`tests/test_deploy_reachability_gate.py` carries
the comment); I rediscovered it the expensive way when ten step scripts
"failed" a bash syntax check that they in fact pass.

**Check the CI dependency before importing a test-only package.** PyYAML is
present locally via jupyter, and `backend/requirements.txt` does not name it --
which would normally mean a CI-red import. It is safe only because
`uvicorn[standard]==0.24.0`, which IS pinned there, requires `pyyaml>=5.1`
transitively. Two minutes of checking, rather than a red CI run to find out.

**The doc-freshness same-day artifact has a sanctioned answer.** A doc updated
in the same commit series as the files it tracks is flagged stale, because the
stamp is date-only and the commits carry a time. `docs/freshness/*.ack` is the
mechanism for exactly that, and two prior beads had already used it -- worth
looking for the existing escape hatch before assuming a check is wrong.

## Doc freshness

- `docs/components/config-deployment.md` -- rewrote the Backend section around
  the two-layer env assembly, the channel-file format and parity rule, the
  empty-section refusal, and the preflight; added every new file to
  **Tracks:**; corrected three now-wrong references (`BACKEND_SECRETS_COMMON`
  and two `BACKEND_EXTRA_ENV` mentions) whose named constants no longer exist.
  Stamped 2026-09-11, plus a `docs/freshness/` ack for the same-day artifact.
- `docs/doctrine/promotion-tiers.md` -- new sections for the preflight refusal
  and for the Cloud Build pipeline, both stating plainly that no build has run
  and bash is still the deploy path; two rows added to the channel table.
  Stamped 2026-09-11.
- `docs/technical_guide.md` -- Surface contract 29 in two halves: the channel
  file (format, both consumers, what pins it) and the `build_checks/{sha}` gate
  (producer, consumer, why it keys on `_SHA` rather than `COMMIT_SHA`, and that
  it is NOT the deploy audit trail -- `deployments/{id}` is). No stamp by
  design.
- Other docs flagged stale by `check_doc_freshness.py` track files this bead
  did not touch; left alone.
- No CLAUDE.md change.

Review outcomes recorded in the closeout ping.

## Files touched

- `cloudbuild.yaml` (new) -- one build definition, `_TARGET`/`_CHANNEL`/`_SHA`.
- `deploy/channels/staging.env`, `demo.env`, `admin.env`, `README.md` (new).
- `deploy-all.sh` -- `read_channel_section` / `read_channel_value`; the backend
  stage reads the channel file instead of building the env block inline.
- `deploy-staging.sh`, `deploy-demo.sh` -- pass `DEPLOY_CHANNEL`; source and
  call the preflight; dead constants removed.
- `scripts/deploy_preflight.sh` (new) -- dirty / unpushed refusal.
- `scripts/record_build_check.py` (new) -- `record` and `require`, fail-closed.
- `scripts/setup-cloud-build.sh` (new) -- operator-run trigger provisioning.
- `tests/test_cloudbuild_yaml.py` (new) -- 20 tests.
- `tests/test_deploy_preflight.py` (new) -- 14 tests, run under real bash.
- `tests/test_deploy_channel_parity.py` -- rewritten as a file diff, 25 tests.
- `docs/components/config-deployment.md`, `docs/doctrine/promotion-tiers.md`,
  `docs/technical_guide.md`, and the new `docs/freshness/` ack.
