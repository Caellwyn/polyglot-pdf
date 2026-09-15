---
date: 2026-09-15
bead: polyglot-pdf-ikdnd
title: "chore(security): F1 -- secret + dependency + SAST scanning in CI, dependabot, the requirements split, and a digest-pinned non-root image"
tags: [security-audit, ci, supply-chain, docker, dependencies]
---

## Trigger

Sprint 23 (the security + data-leak audit, epic `polyglot-pdf-uijam`, plan
`docs/sprint_23_security-audit_plan.md`), workstream F1, threat actor T5
(supply chain). Pre-findings PF-7 (no dependency, secret or SAST scanning in
CI; test tooling shipped in the production image; stale pins) and PF-12's
`.gitignore` half. A Sonnet builder ran the tree + history secret sweeps in
an isolated worktree; the orchestrator finished the rest in-session after
the builder's shell commands were found to be opening console windows on
the maintainer's desktop.

## What shipped

- **Secret scan.** `.secrets.baseline` (detect-secrets, all plugins) over the
  tracked tree with the spike data, notebooks, frozen fixtures, archives and
  lockfiles excluded. Zero true positives: the "secrets" are the public
  Firebase web API key (three `.env.*` files), Secret Manager REFERENCES
  (`LINK_TOKEN_SECRET=<name>:latest` in the channel envs), test sentinels
  named `secret`, model ids, and hex/base64 hashes. The history sweep over
  every blob reachable from `git rev-list --all` found no private key or
  live token (entropy false positives and the same public key only).
- **Audits.** pip-audit on the runtime pins; three low-risk bumps taken
  (`python-multipart` 0.0.9 -> 0.0.31 for CVE-2024-53981 and the 2026
  advisories, `requests` 2.33.0, `python-dotenv` 1.2.2). `starlette` 0.48.0
  carries open advisories whose fixes are in the 1.x line, which needs a
  `fastapi` bump alongside -- the same handshake-breaking class as F2's
  uvicorn bump, so it is filed as its own harness-gated bead (`polyglot-pdf-5r456`)
  rather than taken blind here. `uvicorn`/`websockets` stay F2's. bandit (medium+) has
  five findings, all triaged as non-issues: two SHA-1 CONTENT hashes (kit
  schema identity, field identity -- not security), two parameterized
  BigQuery/lint strings built from constant column names, one f-string in a
  lint message. npm audit (production deps) on the three apps: admin-console
  clean; frontend had 2 critical + 1 high, all transitive (protobufjs,
  websocket-driver, grpc-js) and fixed lockfile-only by `npm audit fix
  --package-lock-only`, leaving 2 moderate (react-router-dom 6 -> 7 is a major
  migration; filed as `polyglot-pdf-gdqmr`); schema-editor's 1 critical + 2
  high all hung off the exact `pdfjs-dist` 4.0.379 pin through the Node-only
  `canvas` optional dependency -- pinned to 4.10.38 (the version the frontend
  already ships; no `canvas` in the tree any more), lockfile regenerated,
  clean. The lockfiles were regenerated without installing (no lifecycle
  scripts run on this machine); CI's `npm ci` + typecheck + vitest validate
  them on Linux.
- **Requirements split.** `backend/requirements-dev.txt` (`-r requirements.txt`
  + the three pytest pins); the image installs `requirements.txt` alone;
  every pytest runner (`ci.yml`, `cloudbuild.yaml`, the dev scripts, README)
  installs the dev file. `tests/test_cloudbuild_yaml.py`'s CI-parity
  collector now skips `continue-on-error` steps, since a step CI itself
  tolerates is not part of "CI's green".
- **Image.** `FROM python:3.12-slim@sha256:...` (digest pinned); a non-root
  `app` user (uid 10001) created AFTER every COPY and after `mkdir` + `chown`
  of the two directories the runtime writes under `/app` (`backend/logs`,
  `logs/confirmations`) -- both file loggers `mkdir(parents=True)` at import,
  so a root-owned `/app` would have crashed the service on start. B0's CMD
  line is untouched.
- **CI.** An INFORMATIONAL `security` job in `ci.yml` (pip-audit on the
  runtime pins, npm audit x3 on production deps, detect-secrets-hook on the
  PR's own changed files against the baseline, bandit medium+, semgrep with
  the Python and TypeScript rulesets -- Linux-only, so CI is its home), every step
  `continue-on-error` so one noisy scanner cannot hide the others; matches
  the workflow's non-blocking doctrine. Promoting it to required is G's
  maintainer ask. `.github/dependabot.yml`: pip + the three npm apps +
  actions, weekly, grouped.
- **Hygiene.** `.gitignore` refuses `*.pem`, `*.key`, `*service-account*.json`,
  `*credentials*.json`.
- **Pins.** `tests/test_ci_security_job.py` (the job, its tools, the three
  npm apps, the dev-requirements install in both runners, dependabot's
  ecosystems, the gitignore patterns, the requirements split, the
  python-multipart floor) and five new cases in
  `tests/test_dockerfile_app_module.py` (digest pin, no literal backslash-n,
  USER after COPY + chown, runtime requirements only, and the line-joiner
  ignoring comments that end in a backslash).

## Verification

- Full backend suite on the bumped pins (installed into the venv), run in
  two hidden halves so nothing opened a console on the maintainer's desk:
  5543 passed / 282 skipped (every file that does not spawn a process) and
  518 passed / 5 skipped (the twelve files that run scripts through
  `sys.executable`, with every child forced to `CREATE_NO_WINDOW`). Targeted:
  `test_ci_security_job.py` + `test_dockerfile_app_module.py` +
  `test_cloudbuild_yaml.py`, 90 passed.
- Scar #9: fifteen one-line mutations, each against the real file, each RED
  (exit code 1, not merely non-zero -- the first driver had counted a
  missing test id as red) on exactly its pin then restored: `USER app`
  deleted; the `chown` dropped; the continuation turned into a literal
  backslash-n; the digest broken;
  the image told to install the dev file; the bandit step removed; the CI
  install pointed back at `requirements.txt`; the job renamed off
  "(informational)"; the actions ecosystem dropped from dependabot; `*.pem`
  dropped from `.gitignore`; `pytest` put back in the runtime pins;
  `python-multipart` set back to 0.0.9; the semgrep step removed; the
  line-joiner's comment skip removed (that one in its own process: a helper
  inside an already-imported test module is invisible to a second
  `pytest.main` in the same interpreter); the parity collector's
  `continue-on-error` skip removed (the two parity cases had ALSO been red
  before that skip existed, against the real `npm audit` steps).
- Scanners (each once, single process): pip-audit `--no-deps` on the runtime
  pins -- after the three bumps the only remaining advisories are
  `starlette` 0.48.0's (filed); bandit medium+ -- the five findings triaged
  above; detect-secrets over the tree -- the baseline's 58 entries in 38
  files reviewed by type and location, none a live secret.

## Review record

REVIEW_RECORD

Fresh-eyes round 1 found the two defects worth recording: the Dockerfile's
new RUN carried the two characters backslash + n instead of a real line
continuation (the image could not have built -- the shell would have seen a
stray `n` argument to `useradd`), and the three Dockerfile tests the comments
cited had never been appended, so the mutation driver had reported a
non-existent test id as "red". Both came from the same tool defect (a
heredoc that halves backslashes); the block and the tests were rewritten
from snippet files, a `no literal backslash-n` pin was added, and the driver
now accepts only exit code 1 as red.

Fresh-eyes round 2 found that the three npm audits had never actually been
run (the job existed; the criterion asks for their result) and that the
line-joiner would have swallowed a line after a comment ending in a
backslash. Both fixed above; semgrep, named in the plan, was added to the
job in the same round.

## Lessons

- **A non-root image must own what the app writes at import time.** Two
  loggers create directories under `/app` on import; `USER` before the
  `chown` would have been a service that never starts.
- **Derived parity tests widen when CI widens.** Adding `npm audit` steps
  with a `working-directory` made the Cloud Build parity test demand them of
  the verify target; the collector needed the "CI itself does not gate on
  this" exclusion, not a hand-edit of the expected list.
- **Scanners fork.** detect-secrets uses a worker pool and pip-audit builds
  a venv unless told `--no-deps`; on this machine each child is a console
  window when the maintainer is at the desk.

## Doc freshness

Bumped: `docs/standards/testing.md` (pins location, the security job),
`docs/components/config-deployment.md` (the image lines).

## Files touched

- .github/workflows/ci.yml -- dev-requirements install; the security job
- .github/dependabot.yml -- new
- .secrets.baseline -- new
- .gitignore -- key-material patterns
- Dockerfile -- digest pin; non-root user
- backend/requirements.txt -- test tooling removed; three pins bumped
- backend/requirements-dev.txt -- new
- cloudbuild.yaml, scripts/start_backend.sh, scripts/fix_venv.sh, scripts/dev_env.ps1, scripts/dev-local.ps1, scripts/dev-local.sh, scripts/run-schema-editor.sh, README.md, scripts/README.md -- install the dev file
- tests/test_ci_security_job.py -- new
- tests/test_dockerfile_app_module.py -- three new pins
- tests/test_cloudbuild_yaml.py -- parity collector skips continue-on-error steps
- docs/standards/testing.md, docs/components/config-deployment.md -- stamps + prose
- docs/journal/entries/2026-09-15-bd-ikdnd-security-scanning.md -- this entry
