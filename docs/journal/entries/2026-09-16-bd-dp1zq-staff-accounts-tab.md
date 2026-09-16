---
date: 2026-09-16
bead: polyglot-pdf-dp1zq
title: "feat(admin-console): Users tab becomes Staff accounts with a purpose intro, firm select, and a one-line purpose header on every page"
sprint: 22
tags: [conventions, testing]
---

## Trigger

Maintainer feedback 2026-09-15 after the first console sign-in: "not sure
what the 'users' tab does." The Users tab (bead C3,
`admin-console/src/pages/UsersPage.tsx`) manages a firm's staff accounts --
create by email/firm/role (returning a one-time password-reset link, no
email sent), disable/re-enable, change role, list staff -- but nothing on
the page said so, and the firm field was a free-text id left over from
before `GET /admin/firms` (bead B1) existed. This bead traces to the
admin-console program plan (`docs/sprint_22_admin-console_plan.md`), which
lists the tab rename and firm select as follow-ups once B1 landed.

## What shipped

1. Renamed the tab and page heading from "Users" to "Staff accounts"
   (`App.tsx`'s tab list, `UsersPage.tsx`'s `<h2>`).
2. Added a two-sentence intro to `UsersPage.tsx` naming the concrete
   actions (create/disable/re-enable/role-change/list) and the
   manager-vs-employee permission split (manager: mint links, see the
   firm's links, manage staff from the firm console; employee: mint links,
   see only their own links) -- the bead's own verbatim requirement.
3. Turned the firm field from free text into a `<select>` fed by
   `listFirms()` (`GET /admin/firms`), showing `name (firm_id) [kind]`,
   loaded once on mount. A `listFirms()` failure falls back to the
   ORIGINAL free-text field plus its Load button -- the select and the
   text fallback are never shown together. An `AuthError`/`ForbiddenError`
   from `listFirms()` still routes through `onAuthExpired` (the console's
   single mid-session-eviction path) rather than silently degrading to the
   text fallback.
4. Added a new shared `admin-console/src/components/PageIntro.tsx`
   (`data-testid="page-intro"`) and gave every page under
   `admin-console/src/pages/` (Alerts, Cost & income, Errors, FirmDetail,
   Firms, Kit commercials, Monitoring, Usage, Users) plus the two shell
   components `AuditLogPage.tsx` and `ConfigEditorPage.tsx` a one-sentence
   purpose header through it, per the bead's "apply the same pattern to
   every tab" instruction. FirmDetailPage (a drill-down sub-view of the
   Firms tab, not a standalone tab) got one too -- deciding "every page
   under src/pages" literally, which keeps the enumeration test in point 5
   below simple (no exclusion list to maintain) and is harmless.
5. New `admin-console/src/pages/pageIntroCoverage.test.tsx` enumerates
   `src/pages/*.tsx` with `fs.readdirSync` (not a hand-typed list --
   CLAUDE.md scar #8) and asserts each page renders exactly one
   `page-intro` node. Mutation-verified: adding a new page file without a
   matching case fails the file-list assertion; removing a `<PageIntro>`
   render (or its import) from any page fails that page's own assertion --
   caught for real during development when five pages' `<PageIntro>` JSX
   was added without the matching import, which this test's first run
   flagged immediately.
6. `UsersPage.test.tsx` rewritten: the `loadFirm()` helper now drives the
   `<select>` (the default path once `listFirms()` succeeds), a new
   describe block covers the text-fallback path (required input, loading
   through it, and the auth-failure-does-not-fall-back case), plus new
   tests for the rename and the intro's required phrases. Mutation-verified
   by reverting the heading rename (rename test fails), forcing the select
   branch to render unconditionally (all three fallback tests fail), and
   removing a `<PageIntro>` from `FirmsPage.tsx` (its coverage test fails)
   -- each mutation was applied, watched red, then reverted before the
   final commit.

No backend change: this bead is entirely `admin-console/` presentation and
consumes the existing `GET /admin/firms` response shape (`FirmRow`)
unchanged. No new route, env var, or wire shape.

### Fresh-eyes round 1 (adopt/reject/defer)

The reviewer scored exit criterion 2 ("every console page has a purpose
header") a partial FAIL: the literal test (enumerate `src/pages`, assert
each renders one) passed, but `admin-console/src/components/WhoAmIPage.tsx`
-- a real, listed tab (`App.tsx`'s nav, first item) -- had no `PageIntro`
while its two sibling `src/components/` shell pages (`AuditLogPage.tsx`,
`ConfigEditorPage.tsx`) got one in this same diff. The bead's own
description item 3 says "the same intro pattern is applied to every tab,"
so this was a real gap, not a nit.

- **Adopted:** added `PageIntro` to `WhoAmIPage.tsx` (same markup/placement
  pattern as `AuditLogPage.tsx`/`ConfigEditorPage.tsx` -- `<h2>` then
  `<PageIntro>` immediately after), and wrote
  `admin-console/src/components/WhoAmIPage.test.tsx` (the page previously
  had no test file at all), pinning the identity rendering, the null-email
  fallback, and the new purpose header. Mutation-verified by reverting the
  `PageIntro` render and watching the new header test go red, then
  restoring it.
- **Rejected (refuted, no code change):** the "fallback form renders for
  one tick before `listFirms()` resolves" observation in `UsersPage.tsx` --
  the reviewer confirmed this is a harmless loading flash already covered
  by the existing `findBy*` async queries, not a rubric gap; no fix needed.
- **Deferred (pre-existing, out of scope, already filed):** the dated
  "Last updated" chronological-entry chain in
  `docs/components/admin-service.md` reproduces unchanged on `origin/dev`
  and is a pre-existing tier-2 doc convention issue, not something this
  bead introduced. The reviewer filed `polyglot-pdf-gpu4v` for it; no
  further bead needed here.

### Fresh-eyes round 2 (adopt/reject/defer)

The reviewer scored exit criterion 2 a FAIL again, same gap class as round
1 but on the two siblings round 1's fix did not reach: round 1 added
`PageIntro` to `WhoAmIPage.tsx` and gave it a brand-new test file pinning
the header, but `AuditLogPage.tsx` and `ConfigEditorPage.tsx` -- the other
two `src/components/` shell pages that got a `PageIntro` in the ORIGINAL
diff, sitting in the identical blast radius -- kept their existing test
files unchanged. Both pages' `<PageIntro>` block could be deleted and the
full suite stayed green; per CLAUDE.md scar #8 (enumerate the set before
fixing any of it), the set was "all three `src/components/` shell pages
that gained a PageIntro in this bead," and only one of three got the
matching pin.

- **Adopted:** added one `it()` to each of `AuditLogPage.test.tsx` and
  `ConfigEditorPage.test.tsx` (mirroring the `WhoAmIPage.test.tsx` pattern
  from round 1) asserting `findAllByTestId('page-intro')` has length 1 and
  the intro's text matches the page's own verbatim copy. Mutation-verified:
  deleted the `<PageIntro>` block from each production file, re-ran both
  test files, and confirmed exactly the two new assertions went red (21 of
  23 tests in the two files stayed green, isolating the new tests as the
  ones actually covering this), then restored both files unchanged (no
  diff against the pre-mutation copy) before committing.
- **Rejected (refuted, no code change):** the `<select>` blank placeholder
  option (`value=""`) in `UsersPage.tsx` -- the reviewer confirmed
  `loadUsers`'s `if (!targetFirmId) return;` guard already makes selecting
  it a no-op, and `UsersPage.test.tsx` already covers a real selection
  working; not a bug.
- **Deferred (pre-existing, already filed):** the
  `docs/components/admin-service.md` dated-entry chronological pattern --
  matches the file's own pre-existing convention, already filed as
  `polyglot-pdf-gpu4v` in round 1, not worsened by this diff. No new bead
  needed.

Full backend suite and root-level tests re-run clean after this round's
fix (no backend or root-test files touched by either round).

## Lessons

The coverage-test approach (enumerate a directory from disk, assert a
structural property of every file in it) earned its keep twice in one
session: once catching five missing imports during development, and once
confirmed by deliberately adding a scratch file to prove the enumeration
itself is live rather than a frozen snapshot. Worth reaching for whenever a
bead's exit criterion is phrased as "every X has property Y" -- CLAUDE.md
scar #8 (enumerate the set, don't hand-list it) applies as much to a
frontend page inventory as to a backend call-site audit.

## Doc freshness

`docs/components/admin-service.md` (Tracks line already covers
`admin-console/`) bumped with a dated current-state entry describing the
rename, the shared PageIntro pattern, and the firm-select/fallback
behavior. No other tier-2 doc tracks these files. `docs/technical_guide.md`
gets no new Surface contract entry -- this bead adds no route, wire shape,
or cross-surface contract; it only consumes the existing documented
`GET /admin/firms` contract from the client side.

## Files touched

- `admin-console/src/components/PageIntro.tsx` -- new shared one-sentence
  purpose-header component.
- `admin-console/src/App.tsx` -- tab label "Users" -> "Staff accounts".
- `admin-console/src/pages/UsersPage.tsx` -- rename, intro, firm select
  with text fallback.
- `admin-console/src/pages/UsersPage.test.tsx` -- rewritten for the select
  path, new fallback describe block, rename/intro tests.
- `admin-console/src/pages/pageIntroCoverage.test.tsx` -- new: enumerates
  `src/pages/*.tsx` and asserts each renders one purpose header.
- `admin-console/src/pages/{AlertsPage,CostReportsPage,ErrorsPage,
  FirmDetailPage,FirmsPage,KitCommercialsPage,MonitoringPage,
  UsagePage}.tsx` -- added a `PageIntro` import + one-sentence header each.
- `admin-console/src/components/{AuditLogPage,ConfigEditorPage,WhoAmIPage}.tsx`
  -- same, for the three shell tabs (`WhoAmIPage.tsx` added in fresh-eyes
  round 1 after review found it missing).
- `admin-console/src/components/WhoAmIPage.test.tsx` -- new (fresh-eyes
  round 1): the page had no test file before this fix.
- `admin-console/src/components/AuditLogPage.test.tsx`,
  `admin-console/src/components/ConfigEditorPage.test.tsx` -- (fresh-eyes
  round 2) added the purpose-header assertion these two files were missing;
  no production code changed.
- `docs/components/admin-service.md` -- dated current-state entry for this
  bead.
