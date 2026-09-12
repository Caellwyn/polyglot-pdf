---
date: 2026-09-12
bead: polyglot-pdf-i6dlb
title: "feat(admin-console): E3.11b monitoring pages -- health, usage, cost/income reports (delayed label), alerts acknowledge, errors"
sprint: 22
tags: [testing, conventions]
---

## Trigger

Epic 3 bead 11b of the admin-console program (plan:
`docs/sprint_22_admin-console_plan.md`, Epic 3 "Console views"). Bead
`polyglot-pdf-mpebj` (E3.11a) had already shipped the five backend read
routes -- `GET /admin/health`, `GET /admin/errors`,
`GET /admin/firms/{firm_id}/usage`, `GET /admin/reports/cost` +
`GET /admin/reports/income`, and `GET`/`PATCH /admin/alerts` -- but the
console had no pages calling any of them; an operator would have needed
curl and a bearer token to check whether staging was up, see a firm's
month, pull a cost report, or acknowledge an alert. This bead builds the
five console pages.

## What shipped

Five new `admin-console/src/pages/*.tsx` pages, each with a Vitest file
mocking `adminApi.ts` and mutation-verified per assertion.

**MonitoringPage.tsx** fetches `GET /admin/health` for BOTH channels
independently on mount into two side-by-side cards -- a slow or failing
channel never blocks or blanks the other's card (each card owns its own
`{loading, error, health}` state, not one shared pair). Three backend
states render distinctly: `configured: false` ("Not configured"),
`configured: true, reachable: false` ("Unreachable"), and `reachable:
true` (the backend's version SHA) -- plus a fourth, the console's OWN
`/admin/health` call itself throwing, shown as that card's own error
text. Never a blank card in any of the four states.

**UsagePage.tsx** loads the firm list (`GET /admin/firms`) into a picker
(unlike `UsersPage.tsx`'s free-text firm-id field -- usage reporting has
no manager-vs-admin split narrow enough to justify skipping the full
list), then reads `GET /admin/firms/{firm_id}/usage` for the chosen
firm/month/channel. `usage_routes.py`'s own contract is "a missing rollup
doc is an empty reading, not a 404" -- every field comes back `null` --
so this page treats `sessions_completed === null` as the "no data this
month" signal and renders an explicit message rather than a table of
zeros. `by_kit`/`by_employee`/`by_language` each render as their own
table, sorted by key (the map keys carry no inherent order) for a stable
render across reloads.

**CostReportsPage.tsx** has a Cost tab (`GET /admin/reports/cost`,
group-by firm/kit/employee, optional channel) and an Income tab (`GET
/admin/reports/income`, no channel control at all -- mirroring that
route's own 422-on-any-channel-value refusal, since income rows carry no
channel). Both tabs replicate `report_routes.py`'s `_validated_range`
client-side, BEFORE any network call: the same 12-month inclusive
ceiling, the same `to`-before-`from` check, and the identical message
text (verified character-for-character against the route). This is a UX
backstop, not a trust boundary -- the server's own 422 still governs
anything the client check misses, and `MAX_REPORT_RANGE_MONTHS` is
exported from `adminApi.ts` as the one shared constant rather than a
second hardcoded `12`. The `delayed`/`note` label renders only when the
response's own `delayed` flag is true, never assumed.

**AlertsPage.tsx** defaults to `acknowledged=false` (bead requirement:
unacknowledged-only default); kind/firm/status filters apply on submit
only via a `Filter` button, not live-as-you-type -- the mount effect is
DELIBERATELY empty-deps (a real bug caught while writing the tests: with
`loadAlerts` in the effect's dependency array, changing any filter
select auto-fires a request, so by the time a test clicked the explicit
Filter button the button itself read "Loading..." and the click missed
it entirely). Acknowledge calls `PATCH .../acknowledge` exactly once per
click (a per-row `busyId` disables the button while in flight) and
re-reads the list ONLY on success -- mirrors `UsersPage.tsx`'s
established "a failed mutation must not trigger the success re-read"
rule. A 409 (already acknowledged by someone else) shows the route's own
message next to that row without an extra re-read.

**ErrorsPage.tsx** has channel tabs over `GET /admin/errors`, one fetch
per tab switch. Renders ONLY the five `ErrorGroup` fields `adminApi.ts`
types (count, first/last seen, error_type, top_frame) BY NAME -- no
object spread, no key iteration anywhere in the render path -- so a
payload carrying an extra key (a stray `message`, say) has no code path
that could ever put it in the DOM. Pinned by a test that feeds exactly
that shape (an `ErrorGroup` cast carrying a sentinel `message` value) and
asserts the sentinel is absent from `document.body.textContent`, not
merely from a typed field -- the stronger assertion, since a typed-field
check alone would not catch a leak through an untyped `(group as
any).message` read.

`adminApi.ts` gains `getChannelHealth`, `getChannelErrors`,
`getFirmUsage`, `getCostReport`, `getIncomeReport`, `listAlerts`,
`acknowledgeAlert`, and the wire-contract exports `MONITORING_CHANNELS`,
`COST_GROUP_BY`, `MAX_REPORT_RANGE_MONTHS`, `ALERT_KINDS`,
`ALERT_LEVELS`, mirroring the existing `adminFetch`/`AuthError`/
`ForbiddenError` machinery byte-for-byte. `App.tsx` gains five plain tabs
(Monitoring, Usage, Cost & income, Alerts, Errors) alongside the existing
six -- none needs Firms/FirmDetail's sub-state pattern.

Test suite: `MonitoringPage.test.tsx` (7), `UsagePage.test.tsx` (6),
`CostReportsPage.test.tsx` (11, covering both tabs), `AlertsPage.test.tsx`
(6), `ErrorsPage.test.tsx` (7) -- 37 new tests. Mutation-verified per
CLAUDE.md scar #9: for each page, the production branch its key assertion
pins was reverted (the unconfigured/unreachable distinction, the
all-null-usage empty state, the 12-month range ceiling, the
already-acknowledged disabled-button check, the not-re-read-on-failure
call count, and the allowlist render path), the corresponding test
observed failing, then restored and re-verified green.

All 122 admin-console tests (28 pre-existing components + 26 pre-existing
Users/KitCommercials + 31 pre-existing Firms/FirmDetail + 37 new) pass,
confirmed in per-file/per-group runs -- a single full-suite parallel
invocation on this shared machine intermittently hits vitest 4's
hardcoded 5-second fork-boot timeout under load (unrelated to this
bead's code; reproduces identically on the unmodified pre-existing
`FirmsPage.test.tsx` alone), so verification ran in smaller batches
instead of one all-files pass.

## Lessons

A `useEffect` that fires a data load and lists that load's own
`useCallback` in its dependency array will re-fire on EVERY change to
anything that callback closes over -- including form/filter state meant
to be applied only on an explicit submit. If a page has both a
"live-reactive" mount effect and an explicit Filter/Apply button, the two
are contradictory: the effect makes the button redundant (every filter
change already re-queried) while also racing it (a select's onChange and
the button's onClick can both be in flight, and the button's own
disabled-while-loading state can swallow a click that lands mid-request).
The fix is an intentionally empty dependency array for a mount-only
effect, with a comment naming the alternative that was rejected and why.
Caught here only because a test clicked the explicit button and asserted
the SPECIFIC filter values reached the mock -- a looser assertion (any
call happened) would have passed vacuously on the auto-fired request
instead.

`vitest run --no-watch` (rather than plain `vitest run`, which still
initializes the dev-server's file watcher during collection) is
materially faster to boot in a git-worktree checkout: this repo's
`.claude/worktrees/` holds ~170 sibling checkouts, and `vite.config.ts`'s
chokidar `ignored: ['**/.claude/worktrees/**']` glob still costs an
initial directory walk before the ignore takes effect. Without
`--no-watch`, that walk alone can exceed vitest 4's hardcoded 5-second
worker-boot timeout, producing a `[vitest-pool]: Timeout starting forks
runner` error with "no tests" rather than an actual test failure --
easily misread as a real regression. `--no-watch` skips the watcher setup
entirely.

## Doc freshness

`docs/components/admin-service.md`: new dated entry at the top (the one
`check_doc_freshness.py` reads) alongside the existing entries; extended
the "Pages:"/"API client:" bullets and added a new "Monitoring pages"
bullet describing each of the five pages, matching the
Users-page/Firms-pages/Kit-commercials-page detail-bullet shape.

`docs/technical_guide.md`: Surface contract 29 (Epic 3 bead E3.11a, the
backend routes this bead's pages consume) gains a "Console consumer"
paragraph naming all five pages, mirroring contract 24's existing
`KitCommercialsPage.tsx` consumer paragraph.

## Files touched

- `admin-console/src/pages/MonitoringPage.tsx` (new)
- `admin-console/src/pages/MonitoringPage.test.tsx` (new, 7 tests)
- `admin-console/src/pages/UsagePage.tsx` (new)
- `admin-console/src/pages/UsagePage.test.tsx` (new, 6 tests)
- `admin-console/src/pages/CostReportsPage.tsx` (new)
- `admin-console/src/pages/CostReportsPage.test.tsx` (new, 11 tests)
- `admin-console/src/pages/AlertsPage.tsx` (new)
- `admin-console/src/pages/AlertsPage.test.tsx` (new, 6 tests)
- `admin-console/src/pages/ErrorsPage.tsx` (new)
- `admin-console/src/pages/ErrorsPage.test.tsx` (new, 7 tests)
- `admin-console/src/utils/adminApi.ts` (seven new calls + wire types)
- `admin-console/src/App.tsx` (five new tabs)
- `docs/components/admin-service.md`
- `docs/technical_guide.md`

Review outcomes recorded in the closeout ping.
