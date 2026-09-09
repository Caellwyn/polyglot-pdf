---
date: 2026-09-09
bead: polyglot-pdf-z4ljj
title: "feat(frontend): C0 main-app wiring for the admin service (VITE_ADMIN_API_BASE_URL, channel param, mint page 402/403)"
sprint: 22
tags: [conventions, testing]
---

## Trigger

Epic 2 Track C bead C0 (plan: `docs/sprint_22_admin-console_plan.md`,
"Frontend" -- "C0 main-app wiring"). C4 (firm-console employees page) and C5
(link history page) both need to call the admin service from the MAIN voice
app, not the standalone admin console -- and neither has any way to reach it
yet: the main app's build has no admin service URL, no notion of its own
channel, and no generic authenticated-fetch client. Separately, A3
(bd `polyglot-pdf-jecrl`, still an open PR against `dev` at the time of this
work) added two new refusal responses to the mint route -- 402 for
insufficient credits and a second, distinct 403 for a live firm on a
non-demo deployment -- that `MintLinkPage.tsx` did not yet understand.

## What shipped

**Deploy wiring (`deploy-all.sh`).** The frontend stage now resolves a
SECOND live Cloud Run URL alongside `VITE_WS_URL`: `ADMIN_SERVICE_NAME`
(`${ADMIN_SERVICE_NAME:-polyglot-admin}`, matching `deploy-admin.sh`'s own
default, never overridden by either channel wrapper since one admin service
serves both channels) is resolved via `gcloud run services describe` and
exported as `VITE_ADMIN_API_BASE_URL`, mirroring the `VITE_WS_URL` mechanism
almost exactly: a `verify_service_publicly_reachable(..., warn)` reachability
check, and an abort (`exit 1`) when an EXPLICITLY-selected channel's URL
cannot be resolved. Deliberately reuses the SAME `BACKEND_SERVICE_NAME_
EXPLICIT` capture the `VITE_WS_URL` branch already reads, rather than adding
a second explicit-channel flag that could drift out of sync with it.

`deploy-staging.sh` and `deploy-demo.sh` each now also export
`VITE_APP_CHANNEL` (`staging` / `demo` respectively) on their
`FRONTEND_BUILD_CMD=...` invocation line. This is a NEW signal, not derived
from Vite's own `MODE`: both channel wrappers build with `npm run
build:schema:demo` (mode `demo`, since staging reuses the demo build's
Firebase keys), so `import.meta.env.MODE` cannot distinguish the two
channels -- and every firm-scoped admin-service route requires an explicit
`?channel=` because the admin service itself has no channel identity (it is
one Cloud Run service backing both channels' Firestore data).

**`frontend/src/shared/config.ts`** gains `getAdminApiBaseUrl()` (reads
`VITE_ADMIN_API_BASE_URL`, empty string when unset -- no runtime-detection
fallback chain, unlike `getBackendUrl()`, since a wrong guess here would
point firm-console pages at a plausible-but-wrong URL rather than failing
visibly) and `getAppChannel()` (reads `VITE_APP_CHANNEL`, falling back to
`'demo'` on an unset OR unrecognized value -- the repo-wide "unset means
demo" convention, and a defense against a typo minting a channel value the
admin service's own `KNOWN_CHANNELS` check would 404 on). `APP_CHANNELS =
['demo', 'staging']` mirrors `admin_backend/routes/config_routes.py`'s
`KNOWN_CHANNELS`.

**`frontend/src/console/adminApi.ts`** (new file): a small, generic
authenticated-fetch client -- NOT a route-by-route client like
`admin-console/src/utils/adminApi.ts`. `adminFetch(path, user, init,
fetchImpl)` resolves the caller's Bearer token via `resolveStaffToken`
(never `resolveSessionToken`, for the same client-link-wins reason
`MintLinkPage.tsx` already documents), appends `?channel=<this build's
channel>` via the exported `withChannel()` helper, and classifies a 401 as
`AuthError` / a 403 as `ForbiddenError`. Mirrors the standalone admin
console's identical auth-error shape against the same admin service,
deliberately duplicated rather than imported (no new cross-surface
dependency between `frontend/` and `admin-console/`).

**`MintLinkPage.tsx`** learns the two new A3 responses: a 402 shows "Your
firm does not have enough credits to mint a link" (with the balance appended
if the response body ever carries a numeric `balance` field -- it does not
today, checked defensively so a future backend change needs no frontend
change); a 403 is now split by a substring check on the response `detail`
("live firm") into the ORIGINAL "not attached to a firm" message and a NEW
"this deployment cannot mint links for a live firm" message, since the two
need opposite remedies and the second is not something the signed-in
staffer can fix at all.

**Deferred (out of scope for C0, filed nowhere new -- the plan already lists
them as C4/C5):** no concrete firm-scoped route calls exist in `adminApi.ts`
yet; C4 (`EmployeesPage.tsx`) and C5 (`LinkHistoryPage.tsx`) are its first
real callers.

**Cross-surface review round (fix pass).** The Opus outer review returned
GAPS-FOUND with two rubric items to act on plus nits/refutations:
- ADOPTED (blocker) -- `MintLinkPage.tsx`'s 503 branch enumerated only the
  two config-missing 503s live on `dev` today, and missed the third A3
  (bd `polyglot-pdf-jecrl`, PR #749) adds once it merges: a `LedgerError` ->
  "Link minting is temporarily unavailable" (a deployment/data fault, not a
  missing setting). Split the branch on the response detail so the
  transient case gets its own message instead of being told to check
  `LINK_BASE_URL`/`LINK_TOKEN_SECRET`, which are already correct. New test:
  "does not blame LINK_BASE_URL/LINK_TOKEN_SECRET for a transient 503",
  mutation-verified red/green. Also filed as `polyglot-pdf-i08xi` so it can
  be sequenced with #749 if the orchestrator prefers.
- ADOPTED (nit, fixed inline since it was small and touched the same file) --
  `adminApi.ts`'s 403 branch threw a bare `ForbiddenError` with the server's
  raw detail, including the `NO_ADMIN_ACCESS:` wire marker
  (`admin_auth.NO_ADMIN_ACCESS_PREFIX`) when the gate that marks it
  (`require_app_admin_or_owning_manager`, the route C4 will call) fires --
  the one client of the four that mirror this shape that did not strip it.
  Added `forbiddenFromDetail()` and a `noAdminAccess` flag on
  `ForbiddenError`, matching `admin-console/src/utils/adminApi.ts` and
  `schema-editor/src/utils/remoteKitStore.ts`. New tests in
  `adminApi.test.ts` (both on `adminFetch` and on `forbiddenFromDetail`
  directly), mutation-verified red/green.
- DEFERRED (bead, not this diff's to fix) -- `APP_CHANNELS` mirrors
  `config_routes.py`'s `KNOWN_CHANNELS` but the backend itself holds three
  separate Python copies of that list, not one; filed `polyglot-pdf-lahuf`.
- NOT ACTIONED (doc-sequencing nit, judgment call already surfaced in the
  original merge report) -- Surface contract 22 in `technical_guide.md`
  describes A3's `MintRefused` shape in the present tense while that code is
  still only on PR #749's branch, not `dev`. Accurate against that branch,
  inverted merge order against `dev`; re-check when #749 merges.
- REFUTED (not filed) -- none; every other traced contract in the review
  came back OK.

## Lessons

A3 (bd `polyglot-pdf-jecrl`) was marked CLOSED in beads with its PR (#749)
still open against `dev` -- this bead's dependency on jecrl was therefore on
its CONTENT (the exact 402/403 response shapes), not the merge event. Reading
`link_routes.py` from jecrl's own worktree (mergeable/clean against `dev`,
per `gh pr view`) rather than waiting for the merge kept the work moving
without a blocking question, and the two response shapes read there
(`link_routes.py`'s `MintRefused` class) matched exactly what shipped here.
Worth a general note: a bead's DEPENDS-ON closing does not guarantee its
code is in the worktree's base branch yet -- check the PR state, not just
the bead state, when the dependency's exact wire shape matters.

## Doc freshness

- `docs/components/config-deployment.md` -- bumped (Tracks `deploy-all.sh`,
  `deploy-staging.sh`, `deploy-demo.sh`, `frontend/src/shared/config.ts`):
  new "Frontend" bullets for `VITE_ADMIN_API_BASE_URL`/`VITE_APP_CHANNEL`,
  and a new paragraph in "Frontend -> backend wiring" for the admin service
  as a third destination.
- `docs/technical_guide.md` -- new Surface contract 22 (no freshness stamp
  by design).
- `docs/components/schema-forms.md` -- reviewed; its Tracks list does not
  cover `frontend/src/console/`, so left as-is.
- `docs/components/admin-service.md` -- reviewed; its Tracks list covers
  `admin_backend/`/`admin-console/`, not the main app's `frontend/src/
  console/`, so left as-is.
- `docs/INDEX.md` -- reviewed; no new row needed (no new component doc, no
  new tier-2 file).

Review outcomes recorded in the closeout ping.

## Files touched

- `deploy-all.sh` -- `ADMIN_SERVICE_NAME`, the `VITE_ADMIN_API_BASE_URL`
  resolution block (frontend stage).
- `deploy-staging.sh` -- exports `VITE_APP_CHANNEL="staging"`.
- `deploy-demo.sh` -- exports `VITE_APP_CHANNEL="demo"`.
- `frontend/.env.demo` -- `VITE_ADMIN_API_BASE_URL` fallback literal,
  documented (commented-out) `VITE_APP_CHANNEL` default.
- `frontend/src/shared/config.ts` -- `getAdminApiBaseUrl()`, `getAppChannel()`,
  `APP_CHANNELS`.
- `frontend/src/shared/config.test.ts` -- new.
- `frontend/src/console/adminApi.ts` -- new; fix round adds
  `forbiddenFromDetail()` and `ForbiddenError.noAdminAccess`.
- `frontend/src/console/adminApi.test.ts` -- new; fix round adds tests for
  `forbiddenFromDetail()` and the `NO_ADMIN_ACCESS:` strip in `adminFetch`.
- `frontend/src/console/MintLinkPage.tsx` -- 402 and the second 403 handling;
  fix round splits the 503 branch for A3's new transient LedgerError case.
- `frontend/src/console/MintLinkPage.test.tsx` -- three new tests; fix round
  adds a fourth for the transient 503.
- `tests/test_deploy_admin_url_injection.py` -- new.
- `tests/test_deploy_reachability_gate.py` -- `URL_BAKING_SEVERITY` /
  `GATED_DEPLOY_SEVERITY` updated for `deploy-all.sh`'s new second warn-mode
  gate call.
- `docs/components/config-deployment.md` -- updated, stamp bumped.
- `docs/technical_guide.md` -- new Surface contract 22.
