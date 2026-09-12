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

**Cross-surface review round 1: one blocker adopted, two nits deferred, nothing
rejected.**

*Adopted (fixed in this branch).* The rewrite had retired a live regression
guard with no replacement. `origin/dev`'s parity test carried
`test_setup_grants_the_role_that_set_secrets_requires`, asserting that
`scripts/setup-gcp-project.sh` grants `roles/secretmanager.secretAccessor` and
that every API-enabling script on the secret-binding path enables
`secretmanager.googleapis.com`. It was deliberately tied to `deploy-all.sh`'s
`SECRETS_FLAG` wiring -- and that wiring is untouched by this bead and still
live, so the dependency went unguarded: a later edit dropping the grant would
have passed the whole suite green and failed only at deploy time on a
freshly-bootstrapped project. Restored, rebuilt on the new file's own
`_live_lines` helper rather than the wrapper parsers that went out with the
rewrite. The discovery helper is the interesting half: it now finds THREE
providers (`deploy-all.sh`, `setup-gcp-project.sh`, `setup-admin-service.sh`)
where the original found two, which is exactly why it discovers rather than
hand-lists. Mutation-verified three ways, one per live dependency: commenting
out the role grant, deleting the API-enable line from the bootstrap, and
deleting it from `deploy-all.sh`'s every-deploy self-healing list -- each red,
each restored. The reviewer had filed this as bead `polyglot-pdf-ewr71`; it is
closed as fixed here, since a blocker belongs in the diff that caused it.

*Deferred (filed as `polyglot-pdf-jrd87`).* Two nits, neither settleable in
this bead. `setup-cloud-build.sh` bakes `--branch=dev` into every manual
trigger at creation -- required by `gcloud` for a 2nd-generation repository,
but its interaction with the intended runtime `--sha` override cannot be
tested without the maintainer's one-time OAuth connection, which is this
bead's declared PENDING-DEPLOY boundary. And `read_channel_section` silently
merges duplicate non-contiguous `[SECTION]` blocks instead of erroring; the
Python-side parser merges identically, so bash and Cloud Build can never
diverge from each other on it -- a format-hygiene footgun, not a correctness
gap.

*Rejected: none.* Every finding was either real or already a pass note.

**Cross-surface review round 2: two blockers adopted, four nits deferred,
nothing rejected.**

*Adopted (F2 -- the verify gate hardcoded the suite roots).* The new
`verify-backend` step ran `pytest backend/tests admin_backend/tests tests`,
which is the exact regression this repo has journaled twice (bd
`polyglot-pdf-3ave`, bd `polyglot-pdf-pnoik`) and that
`tests/test_every_suite_root_is_gated.py` exists to prevent -- and it slipped
past that set pin because the pin only knew about `ci.yml` and
`closeout_prep.py`. Worse, the new `test_every_suite_the_plan_names_runs_in_
the_verify_target` *pinned the anti-pattern*, asserting the three roots by
literal tuple, so a fourth `testpaths` root would have been dropped from the
gate with both tests green. Three fixes, because the instance was not the set:
the step is now a bare `python -m pytest -q -m "not external"`; the
cloudbuild test derives its expectation from `pytest.ini` `testpaths` and
asserts the ABSENCE of suite paths rather than the presence of today's three;
and `test_every_suite_root_is_gated.py` gained `cloudbuild.yaml` as its THIRD
gate alongside CI and closeout_prep. That third gate matters more than the
other two: it is the step that writes `build_checks/{sha}`, the record every
deploy target reads as "this commit's suites passed", so a gate running a
subset makes the record false about the one thing it exists to assert.
Mutation-verified with the mutation the old test could not see -- a fourth
`testpaths` root plus a hardcoded list omitting it: red in both files,
whereas the literal-tuple version stayed green.

Both scans read the pytest invocation LINES only, never `#` comments. The
comment explaining *why* the roots are absent necessarily names them, so a
whole-body scan would have failed on the corrected file and passed once the
comment was deleted -- guarding prose instead of the command.

*Adopted (F1 -- the empty-channel-env refusal reached only one consumer).*
`deploy-all.sh` refuses a channel file whose `[SET_ENV_VARS]` section is
present but empty, because `--set-env-vars` REPLACES the service's whole env
block: deploying from one would strip `VERTEXAI`, every `LINK_*` key and
`CORS_EXTRA_ORIGINS` off the running service. The `cloudbuild.yaml`
`backend-deploy` step read the SAME file through the SAME sourced parser and
carried no such check -- it went straight to the append, exiting 0 with a
trailing comma. (The missing-FILE case was already safe: `read_channel_section`
exits 1 inside a command substitution and `set -e` propagates it. Only the
empty-SECTION case diverged.) The refusal now travels with the parser, and a
new test pins it three ways -- present, exits non-zero, and precedes the
append. It pins the ARM rather than the file, which the round-1 lesson had
already made necessary: the step carries six `exit 1` occurrences, so a
whole-body `assert "exit 1" in body` would have survived flipping this one.
Verified against the real parser and a real empty channel file outside the
repo, and both shipped channel files still pass through unchanged.

*Deferred (filed by the reviewer as `polyglot-pdf-75twv`,
`polyglot-pdf-vr84l`, `polyglot-pdf-ueazi`, `polyglot-pdf-4wh0x`).*
`record_build_check.py`'s fail-closed `require()` has no behavioural test;
the `--allow-unauthenticated` set pin globs `*.sh` and cannot see the new
`cloudbuild.yaml` call site; `build_checks/{sha}` is a new Admin-SDK-only
collection with no explicit deny block; and a stale `deploy-editor.sh`
comment plus an unbumped `technical_guide.md` stamp. None is a live hole
today -- the first two are missing guards over correct behaviour, the third
is covered by Firestore's implicit default deny, the fourth is prose.

*Rejected: none.*

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

**Cross-surface review round 3: four adopted, three deferred, nothing rejected.**

*Adopted 1 -- the build file's bash variables were being blanked before bash
ran.* Cloud Build substitutes over `cloudbuild.yaml` BEFORE handing a step's
script to the shell, and it resolves every bare `$NAME`. A name that is neither
a built-in nor declared under `substitutions:` is an unmatched reference, which
normally errors -- but a TRIGGER-invoked build sets `ALLOW_LOOSE` by default
and cannot turn it off, and every build here is trigger-invoked. So all nine
bash variables in the two backend steps (`SERVICE`, `BACKEND_ENV`,
`CHANNEL_ENV`, `CHANNEL_FILE`, `CHANNEL_SA`, `CHANNEL_SECRETS`, `SA_FLAG`,
`SECRETS_FLAG`) were silently replaced with the EMPTY STRING. `gcloud run
deploy "$SERVICE" --set-env-vars="$BACKEND_ENV"` would have reached gcloud as
`gcloud run deploy "" --set-env-vars=""` -- the exact "config silently emptied"
failure the channel files were introduced to prevent. Both implemented deploy
targets were non-functional.

What kept it from firing was an accident, not a guard: the empty-`[SET_ENV_VARS]`
refusal also degraded to `if [ -z "" ]` and aborted, so the build failed safe
with the misleading message `ABORT:  has no [SET_ENV_VARS] entries.` The
reachability step had no such luck -- blanked, it called
`verify_service_publicly_reachable ""`, whose IAM read fails, and
`deploy-all.sh` deliberately treats a failed read as INCONCLUSIVE: it warns and
returns 0. Bead `polyglot-pdf-pidtg`'s gate was a no-op.

Every bash variable is now written `$$NAME`. The regression guard is DERIVED,
not a list: `test_every_bare_dollar_reference_is_a_real_substitution` computes
the legal set as Cloud Build's built-ins plus whatever the file itself declares
under `substitutions:`, so adding a substitution widens it automatically while
adding a bash variable does not (scar #8). Verified by simulating the
substitution pass and EXECUTING the resulting script against a stubbed
`gcloud`: before the fix the invocation carried an empty service name and empty
env; after it, the full service name, env block, service account and secrets.

*Adopted 2 -- the verify gate meant less than CI's green.* The `build_checks`
record's whole meaning is "this commit's suites passed", but the two node steps
ran `npm test` where `.github/workflows/ci.yml` runs `npm run test:run`, and
neither ran `npm run typecheck` at all. `npm test` maps to bare `vitest`, whose
watch mode resolves to `!isCI && process.stdin.isTTY` -- it does not hang today
only because a build step has no TTY, which is the runner's accident rather
than the command's contract, and a hung verify would block every deploy for
that SHA until the 3600s timeout. The missing typecheck was the substantive
half: vitest is transpile-only, so a commit failing `tsc --noEmit` still earned
a success record, which is the regression beads `polyglot-pdf-1rgr` and
`polyglot-pdf-b6943` added those CI steps to stop. Both steps now run ci.yml's
commands, and the expectation is READ FROM `ci.yml` rather than transcribed, so
the two cannot drift in either direction.

*Adopted 3 -- `pip install` on the cloud-sdk image is refused by PEP 668.* The
`cloud-sdk:slim` image is Debian-based, and Debian has shipped the
EXTERNALLY-MANAGED marker since bookworm, under which a bare `pip install` into
the system interpreter exits non-zero. Under `set -euo pipefail` that fails the
step -- and `gate-build-checks` is the FIRST step of every deploy target, so
the whole gating mechanism would have been inert. The reviewer could not
execute the image and flagged it medium-confidence; rather than leave a
maybe-broken gate, the two affected steps moved to `python:3.12`, which they
should have been on anyway: both need only pip and `google-cloud-firestore`,
and `record_build_check.py` invokes no gcloud at all. That removes the risk
instead of papering over it with `--break-system-packages`. Pinned as a
PROPERTY of the file (no step may combine `pip install` with a PEP 668 image)
plus a positive assertion that the two gate steps still install the client they
import -- so deleting the pip line, which would satisfy the property alone,
still fails.

*Adopted 4 -- a tier-2 doc named a deleted constant.*
`docs/doctrine/promotion-tiers.md` still said both channels bind
`LINK_TOKEN_SECRET` via `BACKEND_SECRETS_COMMON`, which this bead deleted. The
DECISION it records is still true and now test-enforced by
`test_both_channels_bind_the_same_secrets`; only the mechanism was stale. It
now names the real path: `[SET_SECRETS]` in the channel files, reaching gcloud
through `read_channel_section`. Enumerating the rest of the set found
`technical_guide.md`'s reference already correct -- it calls the constant
"formerly ... now deleted" -- so this was the only live one.

*Deferred.* The `technical_guide.md` `Last updated:` stamp (bd
`polyglot-pdf-cyk64`), plus the two out-of-scope items the reviewer filed:
duplicate Epic 4 beads (`polyglot-pdf-48ktz`) and the uncreated build service
account (`polyglot-pdf-w5jzk`). Beads `polyglot-pdf-j2cby` and
`polyglot-pdf-6jqsd` were filed as routing records for findings fixed here.

*Rejected.* None.

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
- `tests/test_cloudbuild_yaml.py` (new) -- 27 tests (20, plus seven from
  review round 3: the derived bare-`$NAME` guard, the backend step's
  escaping, ci.yml npm parity for both apps, and the two PEP 668 guards).
- `tests/test_deploy_preflight.py` (new) -- 14 tests, run under real bash.
- `tests/test_deploy_channel_parity.py` -- rewritten as a file diff, 26 tests
  (25 plus the restored `secretAccessor` / API-enable guard, review round 1).
- `docs/components/config-deployment.md`, `docs/doctrine/promotion-tiers.md`,
  `docs/technical_guide.md`, and the new `docs/freshness/` ack.
