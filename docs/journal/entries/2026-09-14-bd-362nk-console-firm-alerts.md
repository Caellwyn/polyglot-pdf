---
date: 2026-09-14
bead: polyglot-pdf-362nk
title: "feat(admin-console): alerts section on FirmDetailPage with a shared AlertRow component"
sprint: 22
tags: [refactor, testing]
---

## Trigger

Epic 3 follow-up from the maintainer's 2026-09-14 alerts decision, part
(b): alerts should appear (a) in the firm's own console where staff
generate links (bd polyglot-pdf-62o4d, shipped separately) and (b) in
the admin console's firm detail. Part (a) shipped first; this bead is
part (b) -- the admin console's `FirmDetailPage.tsx` (bd
polyglot-pdf-r8z9g, Epic 2 Track C bead C2) gains an Alerts section
listing the firm's alerts from the SAME operator-wide `GET
/admin/alerts?firm_id=<id>` route `AlertsPage.tsx` (bd
polyglot-pdf-i6dlb, E3.11b) already calls, with the same
kind/level/plain-text rendering that page uses.

## What shipped

Two changes, landed as separate commits so the extraction and the new
feature can be reviewed independently:

1. **A new shared component, `admin-console/src/components/AlertRow.tsx`**,
   extracted byte-for-byte out of `AlertsPage.tsx`'s own inline `<tr>`
   markup (kind, a level badge, formatted timestamp, acknowledged
   status, and the Acknowledge button with its busy/disabled logic).
   AlertsPage.tsx now imports and renders through this component instead
   of a second copy of the same markup; its own `formatTs` helper moved
   into the new file. A `showFirm` prop (default off) toggles the Firm
   column AlertsPage's cross-firm view needs -- FirmDetailPage's section
   is already scoped to one firm and omits it.

2. **FirmDetailPage.tsx's new Alerts section**, over the exact same
   `GET /admin/alerts?firm_id=<id>` / `PATCH /admin/alerts/{id}/acknowledge`
   calls `AlertsPage.tsx` already uses via `adminApi.ts`'s existing
   `listAlerts`/`acknowledgeAlert` -- no new backend route, IAM grant, or
   API client function was needed. The section lists unacknowledged
   alerts FIRST (a stable client-side sort on `Boolean(acknowledged_by)`,
   since `alert_routes.py`'s own ordering is newest-timestamp-first with
   no acknowledged-aware ordering of its own -- this is a genuine sort
   requirement, not a filter: the section shows every alert for the
   firm, unlike AlertsPage's own unacknowledged-ONLY default). Acknowledge
   calls the PATCH exactly once per click (the shared component's own
   busy-while-in-flight gate) and re-reads the alerts list on success
   only, mirroring every other mutation on this page's established
   mutate-then-re-read round trip. A failed alerts fetch sets its OWN
   isolated `alertsError` state and never touches the page's shared
   `error`/`firm` state -- the bead's own requirement that a fetch error
   here "never blanks the rest of the detail page" -- and an empty list
   renders an explicit "No alerts for this firm." message rather than a
   blank table.

`admin-console/src/pages/FirmDetailPage.test.tsx` gained a new "alerts"
describe block (fetch-on-mount with the firm_id filter, unacknowledged-
first ordering against a deliberately ACK-then-UNACK fixture order, the
empty state, fetch-error isolation asserted against the profile/balance/
ledger still rendering, acknowledge-once-then-reread, no-reread-on-
failure, and the disabled button on an already-acknowledged row); a new
`AlertRow.test.tsx` pins the component's own render/interaction behavior
plus a SOURCE-LEVEL check (reading both page files' text and asserting
each imports `'../components/AlertRow'`) for exit criterion 2's own
wording: "a test asserts both import it".

Every new assertion was mutation-verified per CLAUDE.md scar #9: the
unacknowledged-first sort was bypassed (test failed), the empty-state
condition was disabled (test failed), the alerts-fetch error handler was
mutated to also null out `firm` (the isolation test failed via its own
`renderLoaded` helper timing out), the post-acknowledge re-read call was
removed (test failed), the busy-disable guard on the shared button was
dropped (the component test failed), and the `AlertRow` import was
removed from `AlertsPage.tsx` (the source-level shared-import test
failed) -- each mutation reverted afterward and the suite re-confirmed
green.

## Lessons

Extracting a shared row component ahead of a second consumer, rather
than after, kept the new page's section a thin wrapper (state + one
sort + one handler) instead of a second hand-written copy of the same
markup -- the bead's own framing ("extract that row renderer into a
shared component rather than copying it") made this the natural order
rather than something worth debating.

"Unacknowledged first" reads, on a quick pass, like it could be the
same requirement as AlertsPage's own "unacknowledged-only default" --
it is not. AlertsPage filters the query itself (`acknowledged=false`);
this section fetches every alert for the firm and only reorders the
render. Conflating the two would have silently hidden a firm's already-
acknowledged alert history from its own detail page, which nothing in
the bead asked for. The ACK-then-UNACK fixture ordering in the new test
(rather than an already-sorted fixture) is what actually exercises the
reordering rather than merely preserving incoming order.

## Doc freshness

`docs/components/admin-service.md`: new dated stamp paragraph at the
top (the one `check_doc_freshness.py` reads); the "Firms pages" bullet
gains a paragraph on the new alerts section; the "Monitoring pages"
bullet's `AlertsPage.tsx` prose now notes the `AlertRow` extraction and
its `showFirm` prop.

`docs/technical_guide.md` (no stamp, by design): Surface contract 29's
own paragraph gains a sentence naming FirmDetailPage as a new consumer
of the same routes (not a new route); Surface contract 32's intro
corrected a stale claim -- it described the admin console's firm-detail
alerts view as "already shipped, unaffected" by bd polyglot-pdf-62o4d's
own work, which became false the moment this bead shipped the same
view's new section.

`docs/components/config-deployment.md` and `docs/standards/testing.md`
were reviewed via `scripts/check_doc_freshness.py`'s stale-doc report:
both track `admin-console/` broadly (deploy mechanics and CI wiring
respectively), neither makes any claim this bead's page-content change
touches, and both were already stale against unrelated files (deploy
scripts, `pytest.ini`, `conftest.py`) before this bead started -- left
as-is. Two pre-existing stale in-progress beads (`polyglot-pdf-0dsv4`,
`polyglot-pdf-ih428`) surfaced by `closeout_prep.py` are unrelated to
this work and left for the orchestrator.

Review outcomes recorded in the closeout ping.

## Files touched

- `admin-console/src/components/AlertRow.tsx` (new) -- the shared alert
  row renderer.
- `admin-console/src/components/AlertRow.test.tsx` (new) -- component
  tests plus the shared-import source check.
- `admin-console/src/pages/AlertsPage.tsx` -- now renders through
  `AlertRow`; its inline row markup and `formatTs` helper removed.
- `admin-console/src/pages/FirmDetailPage.tsx` -- new Alerts section,
  state, load/acknowledge handlers, unacknowledged-first sort.
- `admin-console/src/pages/FirmDetailPage.test.tsx` -- new "alerts"
  describe block (7 tests).
- `docs/components/admin-service.md`, `docs/technical_guide.md` -- see
  Doc freshness above.
