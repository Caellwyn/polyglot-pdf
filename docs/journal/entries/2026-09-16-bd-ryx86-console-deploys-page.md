---
date: 2026-09-16
bead: polyglot-pdf-ryx86
title: "feat(admin-console): E4.7 Deploys page -- live SHA per channel, gated trigger form, deployments table with polling"
sprint: 22
tags: [testing, refactor]
---

## Trigger

Epic 4 bead 4.7 of the admin-console program plan
(`docs/sprint_22_admin-console_plan.md`): the last bead in the deploy-control-
plane epic, giving an operator a single console tab that shows what is live
per channel, lets them trigger a Cloud Build for a specific commit with the
staging-before-demo gate enforced up front (not just as a 409 after the
fact), and watch that build's status through to success or failure -- without
switching to the Monitoring tab or reading Cloud Build logs directly.

## What shipped

**Backend (`admin_backend/routes/deploy_routes.py`).** Two new reads, both
registered on the router AHEAD of the existing `GET /admin/deploys/{deploy_id}`
so a bare path parameter cannot swallow a literal `targets`/`promotable`
segment as an attempted id lookup:

- `GET /admin/deploys/targets` -- the closed target set
  (`deploy/targets.py::TARGETS`) restated as `{target, target_family,
  channel, gated}` rows, so the console's picker never hand-copies that
  list.
- `GET /admin/deploys/promotable?target=&sha=` -- a preview of the exact
  `staging_verified()` predicate the trigger route's own early 409 already
  uses, extracted into a shared `_staging_verified_for()` helper so the two
  checks can never drift apart. A target outside `GATED_TARGETS` is
  unconditionally `promotable: true`, matching the trigger route's own
  scope.

Both carry the plain `require_app_admin` gate, same as the rest of
`/admin/deploys*`; being reads, neither carries an audit row.

**Frontend (`admin-console/src/pages/DeploysPage.tsx`, new).** Three
independent sections: a live-SHA panel (per-channel health cards from `GET
/admin/health`, the same route MonitoringPage already reads, next to a
"latest successful deploy per target family" list derived client-side from
one unfiltered `GET /admin/deploys` read); a trigger form (target picker
from `GET /admin/deploys/targets`, a 40-hex sha input with client-side
validation, a promotable check that only fires for a gated target with a
syntactically valid sha, and a confirm dialog that always shows the FULL
40-character sha before POSTing exactly once); and a deployments table
(channel/target filters, a status chip per row, a build-id link to
`log_url`) that polls `GET /admin/deploys` every 15 seconds via a recursive
`setTimeout` while the latest fetched batch has a queued/working row, and
stops scheduling once every row in that batch is terminal.

`adminApi.ts` gains the typed calls (`getDeployTargets`, `getPromotable`,
`listDeploys`, `triggerDeploy`) plus two new closed sets:
`DEPLOY_CHANNELS` (`staging`/`demo`/`admin` -- wider than the existing
`MONITORING_CHANNELS`, since a deploy target can carry the admin service's
own channel) and `DEPLOY_STATUSES` (the server's queued/working/success/
failure/cancelled vocabulary), the latter being what the status-chip
coverage test derives its expected set from rather than a second hand-typed
list.

## Lessons

- **A page reachable only through registration order needs a
  registration-order test, not just a route test.** `GET /admin/deploys/
  targets` and `GET /admin/deploys/promotable` are ordinary routes in
  isolation, but their correctness depends entirely on WHERE they sit
  relative to `GET /admin/deploys/{deploy_id}` on the router. The
  mutation-verified test that moves them after the parameterized route (and
  confirms both 404 as "No such deployment") is the one that actually pins
  the thing that can silently break here -- a route-shape test alone would
  have stayed green.
- **Polling logic is easiest to get right (and prove) as a recursive
  `setTimeout` that re-decides after every fetch, not a `setInterval`.** It
  sidesteps overlapping requests on a slow response and makes "stop once
  terminal" a one-line check on the fresh response rather than a second
  piece of state to keep in sync. `vi.useFakeTimers({ shouldAdvanceTime:
  true })` lets `advanceTimersByTimeAsync` drive the poll deterministically
  while ordinary `findBy`/`waitFor` calls for the async data-loading parts
  still work unmodified -- no precedent for fake timers existed in this
  console's test suite before this bead.
- **A dedup that "keeps the first match" needs a test with TWO candidates
  for the same key, not one.** The initial "latest successful deploy per
  target family" test only had one success per family, which would have
  stayed green even if the dedup silently flipped to keeping the newest-
  SEEN row instead of the newest-BY-ORDER row (rows arrive newest-first, so
  those coincide unless a mutation breaks it) -- adding a second, older
  success for the same family was what actually exercised the dedup rule.

## Doc freshness

`docs/components/admin-service.md` gains a current-state block describing
the Deploys page and the two new routes; its stamp is bumped to 2026-09-16
(it was already flagged stale by an unrelated same-day script edit,
cleared as a side effect). `docs/technical_guide.md`'s Admin service routes
table gains the two new rows (sorted by path then method, per that table's
own pinning test) and Surface contract 35 is updated to describe the
console read path as built.

Reviewed and left as-is (pre-existing staleness from other, unrelated
commits already landed on `dev` before this branch started -- none of these
docs' content is about anything this bead changed): `docs/components/
config-deployment.md` (tracks the broad `admin-console/` glob among many
deploy-script/IAM paths this bead never touched -- the console pages it
lists are not that doc's subject), `context-compression.md`, `jit-schema.md`,
`tool-call-flow.md`, `voice-ai.md`, `websocket-routing.md`, and the several
`docs/standards/*.md` files closeout_prep's own audit flagged (ai-models,
bead-tiers, logging-and-cost, risk-rating, schema-key-visibility,
section-reset-deprecation, si-reduction, stateless-architecture,
terminology, testing, validation-delegation, voice-and-vad, ws-protocol).
`docs/technical_guide.md`'s own top stamp is unchanged by design (no stamp
maintained there per CLAUDE.md).

Two stale-in-progress beads (`polyglot-pdf-0dsv4`, `polyglot-pdf-ih428`)
flagged by closeout_prep's own audit are unrelated to this bead and left
for the orchestrator, per doctrine.

Review outcomes recorded in the closeout ping.

## Files touched

- `admin_backend/routes/deploy_routes.py` -- two new GET routes + shared
  `_staging_verified_for()` helper.
- `admin_backend/tests/unit/test_deploy_routes.py` -- new mutation-verified
  tests for both routes and the registration-order guard.
- `admin_backend/tests/unit/test_admin_route_auth.py` -- route-set pin and
  the deploy gate test extended to the two new routes.
- `admin-console/src/pages/DeploysPage.tsx` (new) -- the Deploys page.
- `admin-console/src/pages/DeploysPage.test.tsx` (new) -- exit-criterion
  tests, mutation-verified.
- `admin-console/src/utils/adminApi.ts` -- typed calls + `DEPLOY_CHANNELS`/
  `DEPLOY_STATUSES`.
- `admin-console/src/App.tsx` -- Deploys tab.
- `admin-console/src/pages/pageIntroCoverage.test.tsx` -- enumeration and
  mocks extended for the new page.
- `docs/components/admin-service.md`, `docs/technical_guide.md` -- doc
  updates described above.
