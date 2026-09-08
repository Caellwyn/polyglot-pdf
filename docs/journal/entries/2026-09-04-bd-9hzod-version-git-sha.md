---
date: 2026-09-04
bead: polyglot-pdf-9hzod
title: "feat(backend): 1.6 /version returns the git SHA on the public backend and the admin service"
sprint: 22
tags: [testing, conventions]
---

## Trigger

Epic 1 child 1.6 of the admin-console program
(`docs/sprint_22_admin-console_plan.md`): every later "what is live per
channel" view in the console (bead 1.7 and beyond) needs a way to ask a
running service which commit it is serving. `GET /version` on both
`backend/main.py` and `admin_backend/main.py` returned only
`{"version": app.version}` -- a constant baked at code-review time, not a
per-deploy fact -- so neither service could answer that question.

## What shipped

- `backend/main.py`'s `/version` and `admin_backend/main.py`'s `/version`
  both now return `{"version": app.version, "git_sha": ...}`. `git_sha`
  reads the `GIT_SHA` runtime env var with `os.getenv("GIT_SHA") or
  "unknown"` -- the `or` form, not a plain getenv default, so an env var
  that is SET but EMPTY (a real `--set-env-vars` shape) also falls back to
  `"unknown"` instead of reporting a blank string. This mirrors the exact
  guard `admin_backend/main.py`'s `_active_app_module()` already applies to
  `APP_MODULE`, for the same reason.
- The deploy-side wiring that actually SETS `GIT_SHA`
  (`--set-env-vars GIT_SHA=$(git rev-parse HEAD)` in the deploy bridge) is
  bead 1.3, not this one -- until it lands, every deployed `/version` on
  both services reports `"unknown"`. The console's Vite define consuming
  the same value is bead 1.7. This bead is deliberately just the route
  contract both of those build on.
- `backend/tests/unit/test_version_route.py` (new) and
  `admin_backend/tests/unit/test_version_route.py` (new): three cases each
  (set, unset, empty), plus a distinct-app guard on the admin side mirroring
  `test_admin_health.py`'s existing pattern (an `from backend.main import
  app` re-export would otherwise satisfy the same assertions while serving
  the wrong app.version).
- `admin_backend/tests/unit/test_admin_health.py`'s pre-existing
  `test_version_answers` asserted the OLD exact body shape
  (`{"version": app.version}`), which the new field would have broken;
  narrowed it to check the `version` key alone (still valid, now redundant
  with but not superseded by the new file) and pointed its docstring at the
  new file for the git_sha cases.
- No change to `admin_backend/tests/unit/test_admin_route_auth.py`:
  `/version` was already in `_UNGATED_PATHS` before this bead and stays
  there -- an unauthenticated identity probe, not a business route.

## Lessons

Nothing new generalizes beyond CLAUDE.md's existing scar tissue (#9
test-the-tests: both new test files were mutation-verified by reverting
each route to its pre-bead body and confirming all three new cases per
file go red, then restoring and re-confirming green). The empty-string
fallback shape is a direct reuse of the `APP_MODULE` precedent already
documented in `docs/components/config-deployment.md` -- worth calling out
because it is easy to write a plain `os.getenv(name, "unknown")` here,
which passes every test that only exercises the unset case and silently
mishandles the equally-real empty-set-env-vars case; the test file for
this bead include that case explicitly for exactly that reason.

## Doc freshness

`docs/components/config-deployment.md` bumped: `Last updated` stamp, and a
new paragraph under "One image, two services" documenting the `GIT_SHA` env
var, its fallback behavior, and that the deploy-side wiring is bead 1.3
(its Tracks line already covered both `backend/main.py` and
`admin_backend/main.py`, so no Tracks-line change was needed).
`docs/technical_guide.md`'s two `/version` routes-table rows (public
backend and admin service) updated to name the new `git_sha` field --
`technical_guide.md` carries no `Last updated` stamp by design.
`scripts/check_doc_freshness.py` flags `docs/standards/voice-and-vad.md`
as stale against this branch because its Tracks line includes
`backend/main.py` and this bead touched that file -- but only the
unrelated `/version` route and one import line, not anything
voice/VAD-related that doc covers; left as-is, noted here per the
triage rule for a tracked-but-not-actually-affected file. Every other
STALE doc in the freshness report predates this bead and is unrelated to
its surfaces.

## Files touched

- `backend/main.py` (`/version` route)
- `backend/tests/unit/test_version_route.py` (new)
- `admin_backend/main.py` (`/version` route)
- `admin_backend/tests/unit/test_version_route.py` (new)
- `admin_backend/tests/unit/test_admin_health.py` (narrowed pre-existing pin)
- `docs/components/config-deployment.md` (new section, stamp bumped)
- `docs/technical_guide.md` (two routes-table rows)
- `docs/journal/entries/2026-09-04-bd-9hzod-version-git-sha.md` (this entry)

Review outcomes recorded in the closeout ping.
