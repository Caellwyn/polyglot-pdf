---
date: 2026-09-09
bead: polyglot-pdf-krbol
title: "feat(frontend): C4 firm-console employees page (manager only)"
sprint: 22
tags: [testing, conventions]
---

## Trigger

Epic 2 Track C bead C4 (sprint_22_admin-console_plan.md, "Frontend"
section): a firm manages its own staff without an operator in the loop
(bd polyglot-pdf-gob8l's admin-service routes already support this via
`require_app_admin_or_owning_manager`), but the MAIN APP had no page for
a manager to do it from. admin-console's own `UsersPage.tsx` (bd
polyglot-pdf-z4y91) covers the app-admin path; this bead is the
manager's own version, mounted where the manager actually signs in.

## What shipped

`frontend/src/console/EmployeesPage.tsx` at `/console/employees`
(route added to `AppRoutes.tsx`, behind `ProtectedRoute` -- the same
auth-gate shape as the existing mint route). Lists the manager's own
firm's staff, creates a new account by email + role, disables/re-enables,
and changes role. Builds its own typed calls directly on C0's
`adminApi.ts` (`adminFetch`/`errorDetail`) rather than importing
admin-console's app-admin-scoped client -- the two apps deliberately do
not import from each other.

**The firm never comes from this page.** Every request omits `firm_id`
entirely: no query param on the list call, no key at all in any mutation
body (not even `null` -- a present key with ANY value trips
`admin_auth.resolve_target_firm`'s manager refusal, 403, because the rule
is "did you try to name one" not "did you name the right one"). The one
subtlety worth naming: `JSON.stringify` drops an `undefined`-valued key,
which is what actually keeps the wire body key-free -- the create call's
`firm_id` field is simply never written into the object literal at all,
rather than written as `undefined`.

**Manager-only is UX ONLY, not the real gate.** The route itself is
reachable by any signed-in staffer (same as every other console route);
`EmployeesPage` additionally reads the signed-in account's ID-token
claims via Firebase's `getIdTokenResult()` and renders nothing unless
`firm_role === "manager"`. Fails closed on any error or a test double
missing the method. The REAL enforcement is unchanged and lives entirely
server-side in the admin service's composite gate -- this check exists
only so an employee who forces the route open sees nothing rather than a
form that would 403 on submit.

The reset link (mirrors admin-console's `UsersPage`) shows exactly once
right after a successful create and is cleared the moment a new create
starts; no password field or value ever renders anywhere on the page.
Disable and role-change each call their route exactly once and then
re-read the list (mutate-then-re-read, same pattern `ConfigEditorPage`
and `UsersPage` both use), so the screen always reflects what the server
actually stored rather than an optimistic local patch.

`AppRoutes.test.tsx` (renamed from `clientRoute.test.tsx`, which already
covered the route table generally despite its narrower name) gained the
same shape of pin the mint route already had: does NOT mount for a
signed-out visitor, DOES mount (and not the staff catch-all) for a
signed-in one, and the path constant is pinned literally.

## Lessons

`consoleStyles.test.ts` (bd polyglot-pdf-41ay8) hardcoded ONE page file
(`MintLinkPage.tsx`) rather than deriving the set of console pages to
check -- exactly the "typed list" anti-pattern its own header comment
warns against for CLASS names, one level up, for FILES. Generalized to a
`PAGE_FILES` list so `EmployeesPage.tsx` (and the next console page) gets
the same class-coverage guard for free instead of silently going
unchecked. Small scope-adjacent fix, made in this bead's own commit
rather than filed separately, since it is a one-line addition to an
existing loop and directly serves this bead's own new page.

## Doc freshness

`scripts/check_doc_freshness.py` reports every tier-2 doc whose `Tracks:`
line covers a file this bead touched as clean (`admin-service.md`,
`config-deployment.md`, `schema-forms.md` all `OK`) -- none of their
`Tracks:` globs include `frontend/src/console/*` or `AppRoutes.tsx`, so
no doc update was mechanically required. The routing table
(`AppRoutes.tsx`, bd polyglot-pdf-ugm6) still has no dedicated tier-2 doc
of its own; that gap predates this bead and is unchanged by it.

Review outcomes recorded in the closeout ping.

## Files touched

- `frontend/src/console/EmployeesPage.tsx` (new) -- the page.
- `frontend/src/console/EmployeesPage.test.tsx` (new) -- mutation-verified
  wire-shape and UX-gate tests.
- `frontend/src/schema-forms/AppRoutes.tsx` -- new `/console/employees`
  route, `EMPLOYEES_PATH` export.
- `frontend/src/schema-forms/AppRoutes.test.tsx` (renamed from
  `clientRoute.test.tsx`) -- employees-route mount/gate/path-pin tests
  added alongside the existing client and mint ones.
- `frontend/src/console/styles/console.css` -- `.employees-*` rules.
- `frontend/src/console/consoleStyles.test.ts` -- generalized from one
  hardcoded page file to a `PAGE_FILES` list covering both console pages.
