---
date: 2026-09-09
bead: polyglot-pdf-x22hm
title: "feat(frontend): C5 firm-console link history page (allowlisted, employee-scoped)"
sprint: 22
tags: [security, testing, doctrine]
---

## Trigger

Epic 2 (admin console) Track C bead C5, plan section "Frontend" (main app,
link history): the last of the three main-app firm-console pages this
sprint (after C0's wiring and beside C4's employees page), so a manager can
see the firm's client-link activity -- status, spend, opened/completed
times -- and revoke a link, while an employee sees only links they sent
themselves.

## What shipped

- `frontend/src/console/LinkHistoryPage.tsx` (NEW), mounted at
  `/console/links/history` (`AppRoutes.tsx`'s new `LINK_HISTORY_PATH`,
  behind `ProtectedRoute`). Uses C0's `adminApi.ts` (`adminFetch`,
  `withChannel`) rather than raw `fetch`, so every request already carries
  the staff Bearer token and the build's channel.
- Role (manager vs. employee) is read from the verified token's OWN custom
  claims via `user.getIdTokenResult()` -- `claims.firm_id` /
  `claims.firm_role`, the same two claims `backend/services/firms.py`'s
  `manager_firm_id` reads server-side. This is a NEW pattern in this repo
  (no prior page called `getIdTokenResult()`); it decides only which UI
  controls render (a manager's filter row and Revoke column) and is never a
  security boundary on its own -- the admin service re-verifies the bearer
  token on every request regardless of what this page shows or hides.
- `GET /admin/firms/{firm_id}/links` -- an employee's request always omits
  `employee_id` (matches the bead's own wording); a manager may add
  `status`/`employee_id` filters. `POST /admin/links/{jti}/revoke` is
  manager-only, fires once per click (disabled while in flight), and on
  success RE-FETCHES the list rather than patching the clicked row's status
  in local state, per the bead's own "one call, re-read" exit criterion.
- Renders only bead B4's allowlisted columns (`jti, kit_id, employee_id,
  status, minted_at, open_deadline, opened_at, completed_at, spend_usd,
  turns, cap_usd, credit_cost`), built by hand from named fields -- never
  `{...row}` -- pinned by a test that plants an extra key on the stubbed
  row and asserts it never reaches the DOM.
- `frontend/src/schema-forms/AppRoutes.test.tsx` (NEW file, named in the
  bead's surfaces -- the existing route-table coverage for `CLIENT_LINK_PATH`
  and `MINT_PATH` stays in `clientRoute.test.tsx`, which keeps its own
  header comment and subject; this file is where `LINK_HISTORY_PATH` gets
  the same "signed-out shows nothing, signed-in mounts the real page, not
  the staff catch-all" pair of tests, mirroring `clientRoute.test.tsx`'s
  mint-route tests exactly).
- `frontend/src/console/styles/console.css` gained `.link-history-filters`
  and `.link-history-table` rules (not a declared surface, but added to
  avoid repeating bd polyglot-pdf-41ay8's exact bug -- a page shipping
  classes with no stylesheet definition).

## Fresh-eyes review round: one blocker found, adopted

The Opus cross-surface review (STATUS: GAPS-FOUND (1)) found one real
blocker: a signed-in user whose token carries no `firm_id` claim (a
dev/app-admin account, or a claims-propagation race right after a role
change) landed on the "Loading..." message forever, with no error and no
way out -- `phase` started at `'loading'` and nothing in the claims-
resolution effect, `buildPath()`, `load()`, or the fetch-triggering effect
ever moved it off that phase when `firmId` stayed `null`. The reviewer
contrasted this with `MintLinkPage.tsx`'s deliberately-chosen "start at
`'idle'`, never claims work is in flight" pattern, which this page did not
replicate for its own new claims-fetch. A related non-blocking sub-point
covered by the same fix: the claims-fetch `catch` block silently swallowed
the actual error, giving no way to tell "you have no firm" from "a request
failed."

**Adopted, fixed inline:** the claims-resolution effect now sets `phase` to
`'error'` with a distinct message on both paths that leave `firmId` null --
a missing/non-string `firm_id` claim gets "Your account is not linked to a
firm," and a `getIdTokenResult()` rejection gets "Could not verify your
account. Please sign in again." Two new tests pin both paths
(`LinkHistoryPage.test.tsx`), mutation-verified by reverting the fix and
confirming both go red (the page hangs on "Loading..." with no alert) before
restoring it. No other findings from the round -- the second exit criterion
(route table test) and every other rubric sub-claim in exit criterion 1
passed as originally shipped; no defer/reject items.

## A gap found while building this, filed rather than fixed here

`admin_backend/routes/link_routes.py`'s `require_app_admin_or_owning_manager`
(bead B4, `polyglot-pdf-jmiys`) has exactly TWO actor kinds -- app admin, or
firm MANAGER. An EMPLOYEE-role account is refused with a flat 403 before the
route's own `employee_id` filtering logic ever runs, so an employee cannot
reach even their own link history against the REAL deployed admin service
today. The plan named two tests for exactly this
(`test_employee_link_listing_response_is_allowlisted`,
`test_employee_history_scoped_to_token`, "an employee never sees another
employee's links; ids come from the token, not the query") that bead B4
never implemented -- confirmed by grep against its shipped test file and its
own closeout journal entry, which lists three cross-surface review findings,
none of them this one.

This is a real, deployed-behavior gap in a DEPENDENCY bead, not a frontend
bug: fixing it means widening `admin_backend`'s gate (surfaces this bead does
not own), and this bead's own exit criteria are frontend-only, pinned against
a mocked API. Per CLAUDE.md's scope-creep rule ("file a bead, don't ask" for
out-of-scope work that is not itself a step-2 decision), filed as
`polyglot-pdf-scaig` (P1, `admin_backend` surfaces) with the two shapes to
weigh (widen the composite gate vs. a narrower employee-only dependency on
just the GET route) left for whoever picks it up, and wired `x22hm BLOCKS
scaig` so it cannot be claimed before this page exists to depend on it. This
page needs no change once `scaig` closes -- an employee simply starts
getting real rows back instead of the `ForbiddenError` message the 403
already surfaces today.

## Lessons

A bead whose own exit criteria are entirely frontend-behavioral (pinned
against a mocked API) can still be fully "done" -- tests green, mutation-
verified -- while depending on a backend route that cannot actually serve
one of the two roles the page is built for. Reading the DEPENDENCY bead's
shipped implementation and its own closeout journal (not just its bead body)
before trusting "the admin service scopes by the token" as already-true is
what surfaced this; the closed bead's cross-surface review round is a good
place to check because it lists exactly what WAS found, making a plan-vs-
shipped gap ("the plan named two employee tests; the shipped test file has
neither") visible by grep rather than by inference.

## Doc freshness

- `docs/technical_guide.md` gained Surface contract 25 (this bead), which
  documents the page, the `getIdTokenResult()` claims read, and the
  `polyglot-pdf-scaig` gap with a forward pointer. No `Last updated:` stamp
  bump -- the file's own header says it has no stamp by design.
- No `docs/components/*.md` Tracks line covers `frontend/src/console/*` or
  `AppRoutes.tsx` today, so none needed a bump.

## Files touched

- `frontend/src/console/LinkHistoryPage.tsx` (new)
- `frontend/src/console/LinkHistoryPage.test.tsx` (new)
- `frontend/src/schema-forms/AppRoutes.tsx` (edit: new route + path constant)
- `frontend/src/schema-forms/AppRoutes.test.tsx` (new)
- `frontend/src/console/styles/console.css` (edit: two new rule blocks)
- `docs/technical_guide.md` (edit: new Surface contract 25)
- `docs/journal/entries/2026-09-09-bd-x22hm-link-history-page.md` (new, this file)

Review outcomes recorded in the closeout ping.
