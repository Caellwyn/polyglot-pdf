---
date: 2026-09-03
bead: polyglot-pdf-pnoik
title: "feat(admin): 1.1 admin_backend package skeleton, runtime APP_MODULE in Dockerfile, admin SA pin test"
sprint: 22
tags: [security, testing, conventions]
---

## Trigger

Sprint 22's admin-console program (plan `docs/sprint_22_admin-console_plan.md`,
Epic 1 "Admin service") needs somewhere to put privileged code. Today there is
nowhere safe: the public backend runs as `polyglot-backend-sa`, whose IAM is
deliberately narrow, and CLAUDE.md scar #7 is the record of what happens when
that envelope is breached — on 2026-08-26 a `check_revoked=True` turned a token
signature check into a user-record fetch needing `firebaseauth.users.get`, and
every deployed connection failed with `INSUFFICIENT_PERMISSION` past 3839 green
tests, green CI, nine fresh-eyes rounds and a cross-surface pass. A mock proves
the code CALLS something; it cannot prove the caller is ALLOWED to.

The console needs to create users, stamp custom claims, trigger builds and read
BigQuery. None of that can live in `backend/` without either widening
`polyglot-backend-sa` (throwing the property away) or adding a permanently
untestable exception. So the plan's first decision was topological: a SEPARATE
Cloud Run service with its own service account, and this bead builds the empty
shell of it.

## What shipped

**`admin_backend/`, a sibling top-level package.** Not a subpackage of
`backend/` — that distinction is the whole mechanism. The existing guard
`backend/tests/unit/test_deployed_iam_envelope.py` derives its scan root as
`parents[2]` of its own file, i.e. `backend/`, and walks everything under it by
EXCLUSION. A subpackage would land inside that walk and every privileged call
the admin service is supposed to make would be flagged as a violation of the
public backend's envelope. As a sibling, the public backend stays pinned at zero
privileged Firebase Auth calls with **no change to that test at all** — verified:
`git diff` on it is empty and it still passes.

At this stage the package is `main.py` (FastAPI app, CORS, `/health`,
`/version`) plus empty `routes/` and `services/`. Routers and
`require_app_admin` are bd `polyglot-pdf-7w17m`.

**One image, two services, chosen at runtime.** The root `Dockerfile` now copies
both packages and reads its ASGI target from an env var:

```
CMD uvicorn ${APP_MODULE:-backend.main:app} --host 0.0.0.0 --port ${PORT}
```

A build ARG was the obvious shape and is wrong here: `deploy-all.sh` builds with
`gcloud builds submit --tag`, which has no way to pass `--build-arg`, so an
`ARG` would freeze at its default in every image while the deploy-time value was
silently ignored. `APP_MODULE` arrives through `gcloud run deploy
--set-env-vars` instead.

Three near-miss shapes, each of which looks equivalent and is not:

- **`ENV APP_MODULE=backend.main:app` alongside the `:-` default.** I wrote this
  first. It makes the fallback dead code, and worse it hides the empty-string
  case: a deploy passing `APP_MODULE=` (a real shape when a bash variable is
  unset inside a `--set-env-vars` block) overrides the ENV with empty, the `:-`
  never fires because the variable IS set, and the container crash-loops.
- **`-` in place of `:-`.** Falls back on unset only, not on empty.
- **Exec form.** `CMD ["uvicorn", "${APP_MODULE:-...}"]` does no shell expansion
  at all; uvicorn gets the literal string.

**The admin SA envelope, pinned offline.** The sibling of the public guard,
asking the same question from the other side. This service is ALLOWED to make
privileged calls, so re-asserting "no privileged calls" would be meaningless.
What is pinned is the envelope: the project-level role list, the bucket-scoped
role list, the roles the plan DEFERS, and the import direction.

The two role lists are pinned separately on purpose. `storage.objectAdmin`
belongs on the form-kits bucket only; folding it into the project array would
keep every name-keyed assertion green while handing the admin service write
access to every bucket in the project. So there is an assertion on the SCOPE —
that `BUCKET_ROLES` is iterated by `gcloud storage buckets
add-iam-policy-binding` and that its members do not appear in `PROJECT_ROLES`.

Roles are parsed OUT of `scripts/setup-admin-service.sh` rather than re-typed in
the test (scar #8, one rule one home): the script is what an operator runs, the
constant is what a reviewer reads, and they cannot drift.

**`pytest.ini` gains a third testpath.** `admin_backend/tests` is a sibling
package, so the `backend/tests` path never reaches it. Without the entry the
whole suite would collect zero tests and report green.

Deferred, per the plan, each landing with its first consuming call:
`cloudbuild.builds.editor`, `iam.serviceAccountUser`, `run.admin`,
`firebasehosting.admin` (Epic 4); `bigquery.jobUser`, `bigquery.dataViewer`,
`errorreporting.viewer`, `monitoring.viewer` (Epic 3). Their absence is itself
asserted, so granting one early is a decision made in the open.

## Lessons

**A guard that scans nothing passes every assertion it makes.** The import guard
(`admin_backend/` must never import `backend.routes`) is a "no offenders" shape,
and a "no offenders" shape is vacuous the moment its source walk returns an
empty iterator. Mutating `PACKAGE_ROOT` to point at a directory that does not
exist left the import guard GREEN while it scanned zero files. The fix is a
companion test asserting the walk actually reaches `admin_backend/main.py` and
actually skips the test tree — cheap, and it converts a silent no-op into a
named failure. Any test whose assertion is `assert not offenders` over a derived
file set needs one.

**Pin the SCOPE of an IAM grant, not just its name.** A role name is half the
security property. `roles/storage.objectAdmin` granted on one bucket and the
same role granted project-wide are different capabilities with identical
strings, and every test keyed on the name alone passes both. The same shape as
`docs/standards/testing.md`'s "pin the BEHAVIOR at the gate, not the label".

**A sibling package is a security boundary only if some test says which
direction imports may flow.** `admin_backend/` importing `backend.routes` would
execute the public app's router construction inside the privileged process —
binding handlers written and reviewed against a narrow service account onto a
wide one — and nothing about the directory layout prevents it. The layout
expresses the intent; the test enforces it.

## Doc freshness

- `docs/components/config-deployment.md` — bumped to 2026-09-03. New "One image,
  two services (`APP_MODULE`)" section. Its Cloud Run paragraph also had a stale
  claim: it named `backend/Dockerfile` (gone; the same doc says so 70 lines
  earlier) and a hardcoded `uvicorn backend.main:app`. Both corrected.
- `docs/technical_guide.md` — bumped to 2026-09-03. Two new Surface-contract
  entries: **12** `APP_MODULE` (producer/consumer and the silent-wrong-app
  failure) and **13** the `admin_backend/` -> `backend/` shared-code direction.
  Its `**Tracks:**` line gains `admin_backend/main.py`.
- Every other doc `check_doc_freshness.py` flagged STALE tracks files this
  branch did not touch; the flags are a fresh-worktree mtime artifact, reviewed
  and left alone.
- No CLAUDE.md change.

## Review

Review outcomes recorded in the closeout ping.

## Files touched

- `admin_backend/__init__.py` — new; the package docstring carrying the why.
- `admin_backend/main.py` — new; FastAPI app, CORS off `CORS_EXTRA_ORIGINS`,
  `/health` (reports the live `app_module`), `/version`.
- `admin_backend/routes/__init__.py`, `admin_backend/services/__init__.py` — new; empty.
- `admin_backend/tests/__init__.py`, `admin_backend/tests/unit/__init__.py` — new.
- `admin_backend/tests/unit/test_admin_health.py` — new; criterion 1.
- `admin_backend/tests/unit/test_admin_sa_iam_envelope.py` — new; criterion 2.
- `scripts/setup-admin-service.sh` — new; provisions `admin-backend-sa`.
- `tests/test_dockerfile_app_module.py` — new; criterion 3.
- `Dockerfile` — `COPY admin_backend`, runtime `APP_MODULE` in the CMD.
- `.gcloudignore` — excludes `admin_backend/tests/`.
- `pytest.ini` — `admin_backend/tests` added to `testpaths`.
- `docs/components/config-deployment.md`, `docs/technical_guide.md` — see above.
