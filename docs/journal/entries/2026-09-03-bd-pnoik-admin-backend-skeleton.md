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

**`pytest.ini` gains a third testpath — and the GATES had to be taught to read
it.** `admin_backend/tests` is a sibling package, so the `backend/tests` path
never reaches it. Without the entry the whole suite would collect zero tests and
report green.

Adding the entry turned out to be half the job, and the cross-surface review
found the other half. Both gates named their suite paths by hand and so never
saw the new root: `.github/workflows/ci.yml` ran `pytest backend/tests tests`
and `closeout_prep.check_tests()` ran `WT/backend/tests`. Measured on this
branch, CI's exact command collected **4591 tests and zero** of the 12 in
`admin_backend/tests` — including the admin SA role pin and the import-direction
guard, i.e. exactly the two tests criterion 2 exists for. This repo had already
journaled the same failure once (bd `polyglot-pdf-3ave`: "CI runs `pytest
backend/tests tests`, so the PR would have merged CI-red").

Both gates now run a **bare** `pytest` and inherit `testpaths`, so a future
suite is gated the day it is added rather than the day someone remembers to edit
two files. Pinned as a set by `tests/test_every_suite_root_is_gated.py`, which
derives the roots from `pytest.ini` and fails if either gate names a suite path.

Deferred, per the plan, each landing with its first consuming call:
`cloudbuild.builds.editor`, `iam.serviceAccountUser`, `run.admin`,
`firebasehosting.admin` (Epic 4); `bigquery.jobUser`, `bigquery.dataViewer`,
`errorreporting.viewer`, `monitoring.viewer` (Epic 3). Their absence is itself
asserted, so granting one early is a decision made in the open.

### Outer-review round: the same miss, one layer up

The Opus cross-surface review returned GAPS-FOUND (1) on the section above, and
the finding was the section's own lesson applied to itself. Fixing `ci.yml` and
`closeout_prep.py` fixed the *code* gates. It did not fix the **prose** gates --
and prose is what an agent actually copies when it re-runs the suite after a
review fix. `.claude/skills/closeout/SKILL.md` had FOUR statements of the
recipe; the diff updated one. The operative one, at line 246, still read
`pytest "$WT/backend/tests/"` -- the command an agent runs after an outer-review
or fresh-eyes code fix, scoped to skip the very suite this bead added.

**Adopt (1):** the blocker. Fixed all three remaining SKILL.md instances, then
enumerated the rest of the set rather than stopping at the three the reviewer
named (scar #8 -- the reviewer finding instances one per round IS the trap). The
full set turned out to be nine statements across five files: three more in
`docs/standards/testing.md` (including a "run BOTH roots" that was numerically
wrong once a third root existed), a stale "All tests" recipe and a contributor-
workflow step in `README.md`, a coverage recipe in `.coveragerc`, and a "two
REAL suites" comment in `pytest.ini` itself.

**Reject (0).** **Defer (2):** the `check_tests` 600s timeout, already measured
and filed by the reviewer as bd `polyglot-pdf-c411r` (pre-existing on
`origin/dev`, and it fails loudly rather than silently); and two tier-2 docs
describing the admin deploy in the present tense before any deploy path exists,
filed as bd `polyglot-pdf-2qw3o` (the reviewer's report cited an id that was not
in the tracker).

**The set-pin had the same blind spot as the fix.**
`tests/test_every_suite_root_is_gated.py` scanned only `ci.yml` and
`closeout_prep.py`, which is why the SKILL.md instances shipped past it. It now
scans the prose files too -- and writing that extension reproduced the trap a
third time. The first version used the existing `(?<![\w/-])` lookbehind, and
its mutation test **passed on the reviewer's exact blocker line**: the recipe
writes `"$WT/backend/tests/"`, and the `$WT/` prefix defeated the lookbehind. A
guard that goes green on the one line you wrote it for is worse than none (scar
#9). The pattern now allows a shell-variable prefix while still requiring the
root to END the argument, so a deliberately narrow run (`backend/tests/unit`, a
single file) stays legal. Mutation-verified per root, not once: reverting the
recipe reddens it for `backend/tests`, `admin_backend/tests`, AND `tests`, with
two negative controls (a narrow run stays green; removing a citation marker goes
red).

The two lines that legitimately NAME the anti-pattern in order to warn against
it carry an explicit `suite-path-citation` marker, so the pin stays an allowlist
of sanctioned exceptions rather than a keyword ban that cannot tell a warning
from the thing it warns about.

And the trap fired a FOURTH time, in the fix for the third. The prose pin reads
a hand-listed `PROSE_GATE_FILES` tuple -- the same hand-listed-vocabulary shape
this entry's Lessons already name twice (`_DEPLOYED_PACKAGES`,
`_REPO_TOP_LEVEL_DIRS`). Mutating it confirmed the defect: deleting the
`SKILL.md` entry AND reintroducing the reviewer's exact blocker line left all
six tests **green**, because the entry that would have caught it was removed in
the same edit. The required set is now DERIVED from the repo -- any agent-facing
doc under `.claude/skills/`, `docs/standards/`, or `docs/doctrine/` (plus
`AGENTS.md` and `README.md`) whose text contains a pytest invocation carrying
pytest's own flags must be under the pin -- with a companion test rejecting dead
entries. Mutation-verified per entry: dropping any one of the four goes red.

### Review round 2 (cross-surface, Opus): 4 findings, 4 adopted, 0 rejected, 0 deferred

Round 1 widened both test gates to inherit `testpaths`. Round 2 found that
widening the SCOPE of a gate without widening its TIMEOUT un-gates it, plus
three cases of a claim outrunning the code. All four adopted.

**1 (blocker) — the pre-PR test gate died on its own timeout.** `check_tests`
went from `backend/tests` (measured 590s) to every `testpaths` root (measured
706s) while keeping `timeout=600`. Worse than a slow gate: `TimeoutExpired`
subclasses `SubprocessError`, so the existing `except` arm rendered the kill as
`PREP-ERROR — a check could not run`, a tooling error an orchestrator reads
past. The gate would have reported *nothing* on every closeout while looking
like it ran. Fixed both halves — the ceiling is now a named `_TESTS_TIMEOUT_S`
(1800s, real headroom rather than a number sitting just above today's
measurement), and a dedicated `TimeoutExpired` arm ordered *before* the broad
one reports "no verdict" as its own outcome. Both pinned, including the
except-ordering (a later specific arm is dead code).

**2 — the routes-table set pin was blind to the second app.** It derived
shipped routes from `backend.main` alone, so the admin service's `/health` and
`/version` were invisible to it and shipped undocumented with the suite green.
This is the same hand-scoped-vocabulary trap this bead already fixed twice in
round 1 (`_DEPLOYED_PACKAGES`, `_REPO_TOP_LEVEL_DIRS`) — the routes-table pin
was simply not enumerated as a member of that set (scar #8). The complication:
both apps declare `/health` and `/version`, so a single `(path, method)` key
would let each app's rows "document" the other's. Fixed by giving each app its
own table section and parametrizing all four checks over an `_APPS` tuple —
and, because that tuple is itself hand-listed, deriving the *required* set from
the `Dockerfile`'s `COPY <pkg> /app/<pkg>` lines, so a third service cannot
ship without a table.

**3 — the Surface-contracts map named a producer that sets nothing.** The
`APP_MODULE` entry cited `deploy-all.sh`'s `--set-env-vars` block as the
producer; `grep APP_MODULE deploy-*.sh backend/deploy-new.sh` returns nothing.
The producer legitimately belongs to plan bead 1.3 — only the present tense was
wrong, in a section that declares itself derived from code and is the
blast-radius map a reviewer is told to trace from. Enumerated every site making
the claim rather than fixing the one cited: `docs/technical_guide.md`,
`admin_backend/__init__.py`, `Dockerfile`, and this bead's own
`tests/test_dockerfile_app_module.py` docstring all asserted it;
`docs/components/config-deployment.md` was already correctly hedged. Pinned as
an AGREEMENT, not an answer: while no deploy script assigns `APP_MODULE` no doc
may claim one does, and the day bead 1.3's script lands the test flips and
requires the docs to name the real producer. Mutation-verified in both
directions.

**4 — the new suite was protected only by a sibling's conftest.**
`admin_backend/main.py` calls `get_settings()` at module scope, and
`backend/config.py` fails closed on `K_SERVICE` + `VFF_DISABLE_AUTH=true`, so
`K_SERVICE=x pytest admin_backend/tests/unit --co` aborted at COLLECTION —
reproduced. It looked green in the gates only incidentally: a bare `pytest`
imports `backend/tests/conftest.py` first, and that sibling's module-level pop
cleaned the environment for everyone. So the suite broke under exactly the
narrow per-suite recipe `docs/standards/testing.md` prescribes. Added
`admin_backend/tests/conftest.py` with the same import-time guard the other two
roots carry, and pinned it as a SET derived from `testpaths` — a fourth root
added without its own guard fails immediately rather than the next time someone
runs one suite alone. Mutation-verified three ways: pop deleted, conftest
deleted, and pop demoted out of module scope into a function.

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

**A vacuity guard that iterates the same constant as the scan shrinks WITH
it.** Widening the cwd-independence walk to `_DEPLOYED_PACKAGES = (BACKEND,
ADMIN)`, I wrote a companion test looping over `_DEPLOYED_PACKAGES` asserting
each contributes files. It looked like the vacuity guard this entry already
recommends. Then the mutation — narrow the constant back to `(BACKEND,)` —
**passed**: deleting an entry removed it from the scan and from its own check
in one edit. The property is not "every listed package is scanned" (trivially
true) but "every package that SHIPS is scanned", so the required set has to be
derived from the repo — a top-level dir whose `main.py` builds a FastAPI app.
Same trap for `_REPO_TOP_LEVEL_DIRS`: dropping `admin_backend` from that
hand-listed vocabulary silently disabled bare-literal detection with all 30
tests green, because nothing pinned the vocabulary against what actually ships.
This is `bd memories guard-the-property-not-the-code-shape` hit twice in one
file, and both times the *first* fix was correct and its *guard* was not.

**A `git checkout --` to undo a mutation reverts the real edit too.** Restoring
a mutated file with `git checkout -- <file>` threw away the whole widening I had
just written, not the one-line mutation — the file was untracked-clean
afterward, so nothing looked wrong. `bd memories mutation-restore-can-revert-real-edits`
warns about exactly this; the working habit is a `cp` backup taken immediately
before each mutation and restored from that, never from git.

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

**Round 1 — Opus cross-surface review: GAPS-FOUND (7 findings, 1 blocker).**
Adopted 5, deferred 2 to their own beads.

*Adopted (fixed on this branch):*

1. **BLOCKER — the whole `admin_backend/tests` suite ran in neither gate.**
   Fixed in `ci.yml` + `closeout_prep.py` (both now inherit `testpaths`), doc
   updated in `docs/standards/testing.md`, and pinned as a set by the new
   `tests/test_every_suite_root_is_gated.py`. Details above.
2. **Nothing pinned that `backend/` never imports `admin_backend`** — the
   direction that actually defeats the scar-#7 guard, and newly reachable
   because the package did not exist before this branch. Added
   `test_the_public_backend_never_imports_the_admin_package` (plus a
   matching-rule test and a vacuity guard) to
   `backend/tests/unit/test_deployed_iam_envelope.py`. `docs/technical_guide.md`
   had asserted this invariant was already pinned when it was not; corrected.
6. **The cwd-independence guard was anchored on `backend/` only.** Widened
   `test_runtime_paths_are_cwd_independent.py` to walk every deployed package
   and added `admin_backend` to the bare-literal vocabulary. Fixed together with
   finding 2 as one enumerated set (scar #8): both are the same shape — an
   existing guard whose scan root a *sibling* package silently escapes.
3. **Two docstrings claimed `deploy-all.sh`'s gate calls `/health`.** It reads
   the Cloud Run IAM policy and issues no HTTP request at all. Corrected in
   `admin_backend/main.py` and `test_admin_health.py`, both now stating plainly
   that `/health` has NO deploy-time behavioral coverage — the test docstring
   mattered most, since it was justifying the tests' existence and would have
   told a future session a real probe was unnecessary.
4. **`APP_MODULE` empty-string divergence.** `os.getenv(name, default)` returns
   `''` where the Dockerfile's `${APP_MODULE:-...}` falls back. Routed through
   one `_active_app_module()` helper and pinned across all three env states
   (unset / empty / set) against a model of the shell expansion.

*Deferred (filed, latent, and they bite in a later bead — not this one):*

- **Finding 5 — the routes-table set pin derives from `backend.main` only**
  (bd `polyglot-pdf-nn4ei`). Green today by coincidence: the admin app's
  `/health` and `/version` collide with the public backend's documented paths.
  It bites at bd `polyglot-pdf-7w17m`, when the admin routers actually land.
- **Finding 7 — `CORS_EXTRA_ORIGINS` now feeds two services from one var name**
  (bd `polyglot-pdf-jv5s1`). Nothing is broken while the admin service is
  undeployed; the risk is `deploy-admin.sh` inheriting the schema-editor origins,
  so it belongs to the deploy bead that writes that script.

A note on process: verifying these fixes cost three failed mutations before the
tests were honest. See Lessons.

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
- `.github/workflows/ci.yml`, `scripts/closeout_prep.py` — review round 1: both
  gates now run a bare `pytest` and inherit `testpaths` instead of hardcoding
  suite paths.
- `tests/test_every_suite_root_is_gated.py` — new; the set pin for "every
  collected suite actually runs in both gates".
- `backend/tests/unit/test_deployed_iam_envelope.py` — review round 1: pins the
  reverse import direction (`backend/` -/-> `admin_backend`).
- `backend/tests/unit/test_runtime_paths_are_cwd_independent.py` — review round
  1: scan widened to every deployed package, vocabulary and coverage both
  derived from the repo.
- `docs/components/config-deployment.md`, `docs/technical_guide.md`,
  `docs/standards/testing.md` — see above.
- `admin_backend/tests/conftest.py` — new; review round 2: the import-time
  `K_SERVICE` guard the other two suite roots already carry.
- `tests/test_technical_guide_routes_table.py` — review round 2: checks
  parametrized over every ASGI app the `Dockerfile` ships, with the app set
  derived from its `COPY` lines.
- `tests/conftest.py` — review round 2: stale "two testpaths" comment.
