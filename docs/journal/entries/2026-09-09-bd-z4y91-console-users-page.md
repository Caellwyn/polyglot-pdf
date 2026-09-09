---
date: 2026-09-09
bead: polyglot-pdf-z4y91
title: "feat(console): C3 users page (create with reset link, disable, role)"
sprint: 22
tags: [testing, conventions]
---

## Trigger

Epic 2 Track C bead C3 of the admin-console program (plan:
`docs/sprint_22_admin-console_plan.md`, "Frontend" -- "commercials, C2 firms
+ ledger, C3 users, C4 firm-console employees, C5 link history"). Bead
`polyglot-pdf-dmjl5` had already shipped the four staff-account routes on
the admin service (create, disable, role, list) behind the composite
`require_app_admin_or_owning_manager` gate, but nothing in the console could
call any of them -- an operator would have needed curl and a bearer token.
This bead builds the console page.

## What shipped

`admin-console/src/pages/UsersPage.tsx`: list a firm's staff (`GET
/admin/users?firm_id=`), create an account by email + firm + role (`POST
/admin/users`) showing the returned password-reset link exactly once with a
copy button (no outbound email -- the operator delivers the link
out-of-band), disable/re-enable (`PATCH .../disable`), and change role
(`PATCH .../role`). Both mutations re-read the firm's list afterward, the
same round-trip pattern `ConfigEditorPage` established: the screen always
reflects what the server actually stored, never an optimistic local patch.

`adminApi.ts` gains `listUsers`, `createUser`, `setUserDisabled`,
`setUserRole` plus their wire types (`AdminUserRow`, `UsersPage`,
`CreateUserResult`, etc.), mirroring the existing `adminFetch`/
`AuthError`/`ForbiddenError` machinery byte-for-byte. `App.tsx` gains a
"Users" tab.

**The firm-ID field is a required text input, always shown -- there is no
firm-picker dropdown.** Two independent reasons converge on the same
answer: (1) no `GET /admin/firms` list route exists yet (Epic 2 Track C's
firms page, C2, has not shipped), so there is nothing to populate a
dropdown from; (2) the console's sign-in gate calls only `GET
/admin/whoami`, which gates on the STRICT `require_app_admin` -- never the
composite `require_app_admin_or_owning_manager` the user routes themselves
accept -- so every account that can sign into this console today is
necessarily an app admin, and `admin_auth.resolve_target_firm` refuses
(422) an app admin who omits a firm. A firm-manager sign-in mode, where the
firm comes from the token and the selector must be HIDDEN (a manager who
names one at all is refused 403), is a later bead's concern once the
console itself supports signing in as one; `UsersPage` does not attempt to
guess which actor kind is signed in, because there is currently only one
possible answer.

**Where the bead's contract diverged from the existing console's own
layout convention, the bead won.** Every prior console page
(`WhoAmIPage`, `AuditLogPage`, `ConfigEditorPage`) lives under
`admin-console/src/components/`; the bead's `## Surfaces` list named
`admin-console/src/pages/UsersPage.tsx` explicitly. Followed literally --
this is the FIRST page under `pages/` rather than `components/` -- and
`docs/components/admin-service.md` calls out the split explicitly so the
next reader is not left wondering whether it was an accident. Reversible
and low-consequence either way; noted here rather than escalated.

Test suite (`UsersPage.test.tsx`, 12 tests) pins the exit criterion
verbatim: create shows the reset link exactly once and never a password
(asserted two ways -- no `Password` label ever renders, AND the `createUser`
wire call the component actually made carries no `password` key, so a
future accidental field on that request fails the test even if nothing in
the DOM changed); disable and role-change each call their route EXACTLY
ONCE with the resolved firm and then re-read the list; the firm-ID input is
`required`; selecting the role a user already holds is a no-op (no call at
all); a 401/403 mid-session routes to `onAuthExpired` instead of the page's
own generic banner, matching every other page's convention.

Mutation-verified per CLAUDE.md scar #9: reverted each pinned behavior in
turn (duplicated the reset-link render, dropped `required` off the firm-ID
input, dropped the post-disable re-read, dropped the role-unchanged
no-op guard) and confirmed the corresponding test failed each time, then
restored and re-ran green.

## Lessons

Writing the "never a password" assertion as a literal `/password/i` text
ban was wrong on the first pass -- the page's own legitimate copy says
"password-reset link", so the naive assertion failed against CORRECT
output. The fix generalizes: a "never renders X" guard needs to target the
specific shape of X (a labeled input, a rendered VALUE, a wire-request key)
rather than banning the word that also appears in adjacent, intended
copy. Banning a word is one synonym (or, here, one adjacent correct usage)
from a false failure in the other direction from CLAUDE.md's usual
"blacklist is one synonym from a false pass" warning -- worth naming
because the failure mode here was the opposite: a too-broad guard that
would have forced weakening or deleting a real security-relevant assertion
to make a legitimate render pass.

## Doc freshness

`docs/components/admin-service.md`: extended the console's "Pages"
list and its API-client function list for the four new user routes; added
a "Users page" subsection documenting the always-required firm selector and
why, the reset-link-once/never-a-password behavior, and the mutate-then-
re-read pattern; noted `pages/` as the first departure from the
`components/`-only layout; bumped the test-glob note to cover
`pages/*.test.tsx`. *Last updated* bumped to 2026-09-09.

`docs/components/auth.md` and `docs/components/config-deployment.md` both
track `admin-console/` and flagged STALE by `closeout_prep.py`'s doc-
freshness check, but their triggering files (`backend/services/auth.py`,
`admin_backend/services/admin_auth.py`, `admin_backend/routes/
user_routes.py`, `admin_backend/services/user_admin.py`,
`backend/routes/form_kit_routes.py`, `admin_backend/main.py`) all last
changed in bd `polyglot-pdf-dmjl5` (commit `1b3c98dd`, already merged to
`dev` before this branch forked) or earlier -- nothing in THIS diff touches
any of them, and neither doc's prose makes a claim this bead's change
falsifies (no new gate, no new deploy step, no new env var or config key).
Reviewed and left as-is; not this bead's staleness to fix.

Every other STALE doc the check listed (`context-compression.md`,
`jit-schema.md`, `pdf-filling.md`, `tool-call-flow.md`, `voice-ai.md`,
`websocket-routing.md`, and the `docs/standards/*.md` set) tracks backend
voice/AI/PDF-filling surfaces this bead never touches -- pre-existing
staleness in the checked-out worktree, unrelated to this change, left for
whichever bead owns those surfaces next.

## Files touched

- `admin-console/src/pages/UsersPage.tsx` (new)
- `admin-console/src/pages/UsersPage.test.tsx` (new, 12 tests)
- `admin-console/src/utils/adminApi.ts` (`listUsers`, `createUser`,
  `setUserDisabled`, `setUserRole`, `FIRM_ROLES`, and their wire types)
- `admin-console/src/App.tsx` (new "Users" tab)
- `docs/components/admin-service.md`

Review outcomes recorded in the closeout ping.
