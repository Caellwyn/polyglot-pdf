---
date: 2026-09-09
bead: polyglot-pdf-r8z9g
title: "feat(console): C2 firms list/detail with ledger, grants, links and revoke"
sprint: 22
tags: [testing, conventions]
---

## Trigger

Epic 2 Track C bead C2 of the admin-console program (plan:
`docs/sprint_22_admin-console_plan.md`, "Frontend" -- "kit commercials page
first (smallest), then firms list/detail with ledger + links, then users").
Beads `polyglot-pdf-zopqq` (firm CRUD + credit grant/adjust) and
`polyglot-pdf-jmiys` (link listing + revoke) had already shipped every route
this bead's UI drives, but nothing in the console could call any of them --
an operator managing a firm's kind, balance, or minted links would have
needed curl and a bearer token. This bead builds the console pages.

## What shipped

`admin-console/src/pages/FirmsPage.tsx`: loads `GET /admin/firms` on mount
(deliberately unfiltered, matching the route's own contract) and lists every
firm's kind badge, balance, and status. The create form's `kind` <select>
has NO default -- an explicit "Choose kind..." placeholder that is never a
valid `FirmKind`, so the Create button stays disabled until an operator
actively picks mock or live. This is the exit criterion's first half
("create refuses without kind") enforced client-side ahead of the route's
own 422, and deliberately in the safer direction: a mis-defaulted LIVE firm
can mint for real money (plan: "a mis-defaulted mock firm merely blocks
staging while a mis-defaulted live firm mints for free"), so defaulting the
select to either option would have been the wrong call to make silently.

`admin-console/src/pages/FirmDetailPage.tsx`: profile, an `allowed_kits`
editor (a comma-separated textarea, committed as a full replace matching the
route's own contract), a kind-change control, balance, a paginated ledger
table, grant/adjust forms, and bead B4's link listing with a channel
selector and revoke.

**Kind change is confirm-twice in the CONSOLE, not the route** --
`firm_routes.py`'s own docstring says so explicitly ("a route cannot see how
many times a human clicked"). Opening the change-kind form is confirmation
#1; typing a reason and submitting shows a second, explicit confirm dialog
("Confirm: change firm-a from live to mock? This affects real billing
behavior.") whose own Submit is confirmation #2 -- `setFirmKind` is called
from nowhere else. `reason` is required client-side ahead of both steps,
mirroring the route's own required-reason 422.

**Grant shows `usd_amount` only for the two income types.** `credit_routes.py`
requires `usd_amount` for `subscription_grant`/`purchase` and refuses it on
`promo_grant`; the console mirrors both halves -- the field only renders for
the first two, and switching the type <select> to `promo_grant` actively
CLEARS any typed `usd_amount` so a value typed before the switch can never
ride along on a request the route would 422 on.

**Adjust requires a reason, enforced by two independent layers.** The input
carries a native `required` attribute (catches an empty value before the
form's own submit handler even runs) and the handler itself does a
`.trim()` check (catches a whitespace-only value the native check lets
through). Writing the mutation-verify test for this exposed the two-layer
shape directly: reverting only the `.trim()` check left the "blank reason"
test green (native validation still caught it) while failing the
"whitespace-only" test -- so both tests together, not either alone, pin the
full property. See Lessons below.

**Revoke calls the route once and re-reads**, same MUTATE-THEN-RE-READ
round trip every other write on this page (and `ConfigEditorPage`/
`UsersPage` before it) already uses. The Revoke button is disabled for any
link whose status is not `minted`, matching `link_routes.py`'s own
409-on-non-minted refusal -- the disabled state is a UI courtesy, not the
actual enforcement, which still lives server-side.

`admin-console/src/App.tsx` gains a fifth tab, Firms, whose detail view is a
SUB-STATE of that tab (`openFirmId`) rather than a sixth tab: clicking a
firm name opens the detail page in place, and switching tabs away and back
to Firms always returns to the list (a tab click clears `openFirmId`).

`adminApi.ts` gains `listFirms`, `createFirm`, `getFirm`, `setFirmStatus`,
`setFirmAllowedKits`, `setFirmKind`, `grantCredits`, `adjustCredits`,
`listFirmLinks`, `revokeLink`, plus their wire types, mirroring the existing
`adminFetch`/`AuthError`/`ForbiddenError` machinery byte-for-byte (`setFirmStatus`
is included for completeness against the route table even though this
bead's UI does not surface an active/suspended toggle -- the plan's page
description names status as a LIST column, not a detail-page control, and no
exit criterion calls for one; a future bead can wire it against the same
client function without touching `adminApi.ts` again).

**Cross-surface review round (fix pass).** The Opus outer review traced
every producer/consumer contract this bead's diff touches and returned
`GAPS-FOUND (1)`. Breakdown:

- **Adopted (blocker, fixed inline).** `adminApi.ts`'s `LedgerEntry`
  interface declared `doc_id: string` (non-optional) and
  `FirmDetailPage.tsx`'s ledger table keyed its rows on it, but
  `GET /admin/firms/{firm_id}` never sends `doc_id` -- `credit_ledger.py`'s
  `read_entries()` returns the persisted document verbatim, and `doc_id` is
  attached only to `append_entry`'s/`refund_expired_link`'s *return* values
  (which is why the grant/adjust routes' result types correctly include it).
  Every ledger row was rendering with `key={undefined}`, so a new grant or
  adjust re-read would re-key every row by array position instead of
  identity. Fixed in-diff rather than by touching the backend: `doc_id` is
  now `doc_id?: string` with a comment explaining the omission, the table
  keys on `` `${entry.ts}-${index}` `` (fields the route actually sends)
  instead, and `FirmDetailPage.test.tsx`'s ledger fixture dropped the
  fabricated `doc_id: 'l1'` it had been mocking (it was masking exactly this
  gap) to match what the route really returns. A new test asserts no React
  "unique key" console warning renders; mutation-verified by reverting the
  key expression back to `entry.doc_id` and confirming the test catches it.
  The cheaper long-term fix -- having the backend attach `doc_id` like the
  sibling `audit_routes.py` list route already does -- is filed separately
  (`polyglot-pdf-migp9`) rather than done here, since it touches a backend
  surface (`credit_ledger.py`) this bead's diff does not otherwise reach.
- **Deferred (nit, filed as a bead, not fixed in this pass).** The doc-stamp
  edit to `docs/components/admin-service.md` appended a second
  *Last updated:* stamp instead of replacing the existing one (violates
  `docs/doc-architecture.md`'s prune-on-bump rule; `check_doc_freshness.py`
  does not catch this exact shape). Filed as `polyglot-pdf-fcxek`.
- **Confirmed OK, no action.** Every other producer/consumer pair the
  reviewer traced -- `listFirms`/`createFirm`/`setFirmStatus`/
  `setFirmAllowedKits`/`setFirmKind`/`grantCredits`/`adjustCredits`/
  `listFirmLinks`/`revokeLink` against their routes, the `FIRM_KINDS`/
  `FIRM_STATUSES`/`GRANT_TYPES`/`LINK_CHANNELS` constant mirrors, and the
  `Tab`/`openFirmId`/`FirmsPageProps`/`FirmDetailPageProps` additions --
  matched their producers exactly and needed no change.

## Lessons

**A React effect split across two hooks on overlapping dependencies can
double-fire on mount.** The first draft had one `useEffect([firmId])` that
called both `loadFirm()` and `loadLinks(channel)`, plus a second
`useEffect([channel])` that also called `loadLinks(channel)` -- reasoning
that "firm changes reload everything, channel changes reload only links."
On mount, BOTH effects run together (mount is a change in every dependency
at once), so `listFirmLinks` fired twice for the same render. The fix is
one effect keyed on both dependencies (`useEffect(..., [firmId, channel])`)
so a firm switch and a channel switch each reach the same single call site.
This generalizes: a value read by two different effects for two different
reasons still needs ONE effect if any single mount/change can trigger both
reasons at once -- the "sounds like two reasons" instinct does not imply
"two effects" when the reasons can co-occur.

**A `required` HTML attribute and a JS `.trim()` guard are not redundant --
they catch different inputs, and pinning "reason required" needs a test
per input class.** An empty string is caught by native browser (and
jsdom) form-validation before `onSubmit` ever fires; a whitespace-only
string passes native validation (it is non-empty) and is caught only by
the handler's own `.trim()` check. The first mutation-verify attempt on
the adjust-credits form asserted the component's OWN error message text
("A reason is required.") for a blank-reason test, which failed --
correctly-flagging in a useless direction, since native validation had
already blocked the submit before the handler (and its error-setting code)
ever ran. Fixed by asserting only the property BOTH layers guarantee
together (the route is never called) for the blank case, and keeping the
message-text assertion for the whitespace-only case, which is genuinely
handler-only. Mirrors `docs/standards/testing.md`'s "mutation-verify per
parametrization" rule one level down: a single required-ness property can
be split across two enforcement layers, and a test suite claiming to pin
"required" needs to exercise the layer boundary (blank vs. whitespace-only),
not just one representative input.

## Doc freshness

`docs/components/admin-service.md` (Tracks admin-console/): bumped
*Last updated:*, added a dated changelog entry, and updated the "Pages" /
"API client" prose to describe `FirmsPage.tsx` + `FirmDetailPage.tsx` and
the ten new `adminApi.ts` exports. The pre-existing "no `GET /admin/firms`
list route exists yet" sentence in the Users-page prose was corrected to
current state (that route has existed since bead `zopqq`; this bead is what
finally gives it a caller). The Testing section's existing
`admin-console/src/pages/*.test.tsx` line already covers the two new test
files with no wording change needed.

`docs/sprint_22_admin-console_plan.md` was reviewed, not edited: this
bead's scope (C2) matches the plan's Track C description verbatim, and the
plan's own doc-freshness discipline (frozen scope docs) does not call for a
per-bead edit.

## Files touched

- `admin-console/src/pages/FirmsPage.tsx` (new)
- `admin-console/src/pages/FirmDetailPage.tsx` (new)
- `admin-console/src/pages/FirmsPage.test.tsx` (new)
- `admin-console/src/pages/FirmDetailPage.test.tsx` (new)
- `admin-console/src/utils/adminApi.ts` (extended: firm/credit/link calls
  and types)
- `admin-console/src/App.tsx` (Firms tab + `openFirmId` sub-state)
- `docs/components/admin-service.md` (current-state prose + changelog entry)
