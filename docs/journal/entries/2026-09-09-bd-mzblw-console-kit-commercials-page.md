---
date: 2026-09-09
bead: polyglot-pdf-mzblw
title: "feat(console): C1 kit commercials page"
sprint: 22
tags: [testing, conventions]
---

## Trigger

Epic 2 Track C bead C1 of the admin-console program (plan:
`docs/sprint_22_admin-console_plan.md`, "Frontend" -- "kit commercials
page first (smallest), then firms list/detail with ledger + links, then
users"). Bead `polyglot-pdf-f0kuu` had already shipped the admin service's
three kit-commercial routes (`GET /admin/kits`, `GET`/`PUT
/admin/kits/{kit_id}/commercial`), but nothing in the console could call
any of them -- an operator would have needed curl and a bearer token to
change what a form costs. This bead builds the console page.

## What shipped

`admin-console/src/pages/KitCommercialsPage.tsx`: lists every kit (`GET
/admin/kits`) with its `credit_cost`, `cap_usd` (the route's own field
name -- see below) and `source` ("kit" when a commercial doc exists,
"default" when the kit rides the global fallback). Clicking "Edit" on a
row does a FRESH `GET /admin/kits/{kit_id}/commercial` read -- never the
list row's already-rendered values, which can be stale if another operator
just saved the same kit (pinned by its own test with a deliberately
different fresh-read value). One Save PUTs the WHOLE commercial body
(`credit_cost`, `burn_cap_usd`, `display`), matching the route's own "a PUT
replaces the whole doc" contract -- never a partial patch. A successful
save re-reads the kit (GET) and reloads the list, mirroring
`ConfigEditorPage`/`UsersPage`'s established round-trip pattern.

`adminApi.ts` gains `listKits`, `getKitCommercial`, `setKitCommercial` plus
their wire types (`KitCommercial`, `KitsPage`, `SetKitCommercialRequest`,
`SetKitCommercialResult`), mirroring the existing `adminFetch`/`AuthError`/
`ForbiddenError` machinery byte-for-byte. `App.tsx` gains a "Kit
commercials" tab.

**Field-level 422 surfacing via an allowlist.** Client-side validation
mirrors `kit_routes.py`'s own rules (`credit_cost` a positive int,
`burn_cap_usd` a positive finite number) ahead of the network call, so an
obviously bad value never round-trips to the server. But the server's own
422 is still what this page trusts for anything its own check does not
catch: `fieldFromDetail` classifies a 422 onto the `credit_cost` /
`burn_cap_usd` field it names, by an ALLOWLIST prefix match against
`kit_routes.py`'s own detail strings ("credit_cost must be..." /
"burn_cap_usd must be...") -- never a blacklist, so a future unrelated
failure message can never be misrouted onto a field by accident. This
mirrors CLAUDE.md's "pin message text with an allowlist" rule at the UI
layer rather than only in a test.

**A real bug found by writing the test, not by inspection: native HTML5
number-input `min`/`required` constraints silently block form submission.**
The inputs originally carried `min="1"` / `min="0"` and `required` -- normal
instincts for a number field. The client-side-validation tests (submit a
negative value, expect the page's own error message) failed with the error
banner simply never appearing. Root cause: jsdom (like a real browser)
refuses to fire a form's `submit` event at all when a native HTML5
constraint is violated, so `handleSave`'s own validation code never ran --
the page silently did nothing instead of either saving or explaining why
not. Removed `min`/`required` from both inputs: this page's OWN validation
(`validateCreditCost`/`validateBurnCapUsd`, run inside `handleSave`) is the
actual source of truth here (it must mirror the route's rule exactly, not
merely a browser's separate and looser one), so the native constraint was
redundant at best and a silent-failure trap at worst.

**Discrepancy from the bead's own prose, decided and noted rather than
silently worked around:** the bead text says the list should show
`credit_cost, burn_cap_usd, source ... and updated_by`. The ACTUAL routes
(`kit_routes.py`'s `list_kits` / `get_kit_commercial`) spread
`kit_commercials.resolve_commercial`'s return value, which is
`{credit_cost, cap_usd, source}` -- no `updated_by` (only the raw Firestore
doc carries that field, and neither GET route echoes it), and the field is
`cap_usd`, not `burn_cap_usd` (that spelling is the PUT request body's own
key, matching the stored doc). Built the page against the route's actual,
tested contract (verified via `admin_backend/tests/unit/test_kit_routes.py`
directly, not just the docstring) rather than the bead's prose, since the
Surfaces list for this bead does not include `kit_routes.py` -- adding
`updated_by` to the response would be a backend wire change outside this
bead's scope. Decided rather than escalated: low-consequence, reversible
(a future bead can add the field), and the bead's Surfaces list itself
settles which side gets to change.

**A real data-loss gap found while building the page, filed rather than
silently worked around: `display` cannot survive an edit through this
console.** `kit_commercials.resolve_commercial` deliberately never returns
a kit's `display` value (its own docstring: "not read here" -- it only
resolves what the mint path needs), and both GET routes this page calls
spread that same dict, so neither ever surfaces `display` either. Since
PUT replaces the whole commercial doc by design, and this page has nothing
to read the current `display` from, every save through this page sends
`display: {}` -- silently erasing any label a kit was seeded with (`scripts/
seed_kit_commercials.py` sets `display.label` on every kit it touches). This
is a pre-existing gap in bead A3/B3's read side, not something this bead's
own Surfaces (`adminApi.ts` + the page + the tab, not `kit_routes.py`) can
fix directly -- filed as bd `polyglot-pdf-zcbm1` (add `display` to
`resolve_commercial`'s return value) rather than silently shipping the data
loss or expanding this bead's scope into a route it was not asked to touch.

Test suite (`KitCommercialsPage.test.tsx`, 12 tests) pins the exit
criterion verbatim: list shows credit cost/cap/source; Edit loads a fresh
read, not the list row's stale values; the edit-save-reread round trip
fires EXACTLY ONE PUT and the editor reflects the RE-READ value (not merely
the PUT response's own echo -- the test deliberately makes the re-read
return a THIRD, different number so the assertion cannot pass by accident);
a 422 naming `credit_cost` or `burn_cap_usd` surfaces next to that specific
field, not as a generic banner; an unrelated failure (no field named) shows
the generic banner instead; client-side validation refuses a non-positive
value before any network call; Cancel saves nothing; a 401/403 on load or
save routes to `onAuthExpired` instead of the page's own error handling.

Mutation-verified per CLAUDE.md scar #9: reverted the exactly-one-PUT
guard (fired the PUT twice), the field classifier (made it always return
null), and the fresh-read-on-edit behavior (read the stale list row
instead) in turn, confirmed the corresponding test failed each time, then
restored and re-ran green (12/12).

**Merge note:** this worktree branched before bd `polyglot-pdf-r8z9g`
(the Firms tab) landed on `dev`. Merged `origin/dev` in before closeout to
resolve the resulting `App.tsx`/`adminApi.ts` conflicts up front (both
pages' tabs and API functions coexist) rather than leaving it for the
finisher's rebase.

## Lessons

A `type="number"` input's `min`/`max`/`required` attributes are not free
extra validation layered on top of a component's own logic -- they can
silently PREVENT that logic from ever running, because the browser (and
jsdom, faithfully) blocks the `submit` event entirely on a constraint
violation, with no error surfaced to the app at all. Any page whose OWN
`onSubmit` handler is the actual source of truth for a validation rule
should not also declare a native HTML constraint expressing a similar-but-
not-guaranteed-identical rule, or a value the native check rejects never
reaches the code meant to explain why. Caught here only because the test
asserted the page's OWN error text appeared, not merely "the value did not
save" (which would have passed vacuously either way).

## Doc freshness

`docs/components/admin-service.md`: new dated entry for the kit-
commercials console page, alongside (not replacing) the existing B3 and
r8z9g entries.

`docs/technical_guide.md`: surface contract 24 (kit commercial routes)
gains a "Console consumer" paragraph pointing at `KitCommercialsPage.tsx`
and summarizing the field-level-422 and fresh-read-before-edit behavior, so
a future backend change to these routes' response shape has an explicit
pointer to the one frontend caller that would need updating.

## Files touched

- `admin-console/src/pages/KitCommercialsPage.tsx` (new)
- `admin-console/src/pages/KitCommercialsPage.test.tsx` (new, 12 tests)
- `admin-console/src/utils/adminApi.ts` (`listKits`, `getKitCommercial`,
  `setKitCommercial`, and their wire types)
- `admin-console/src/App.tsx` (new "Kit commercials" tab; merged against
  `origin/dev`'s Firms tab)
- `docs/components/admin-service.md`
- `docs/technical_guide.md`

Review outcomes recorded in the closeout ping.

## Cross-surface review fix round

The Opus outer cross-surface review traced every producer/consumer contract
this bead touches (`listKits`/`getKitCommercial`/`setKitCommercial` against
`kit_routes.py`, the `cap_usd`/`burn_cap_usd` two-spelling contract into
`kit_commercials.py` and `link_budget.py`, the `display: {}` wipe, the
`fieldFromDetail` prefix coupling, the `App.tsx` tab union, the audit
action, and the `kits/` collection's channel-scoping) and returned
`GAPS-FOUND (1)`. Breakdown:

- **Adopted (1):** `docs/components/admin-service.md`'s "Pages:"
  enumeration under "The console" section named five pages and omitted
  `KitCommercialsPage.tsx` -- a tier-2 current-state doc under-describing
  the shipped console (the page was documented only in the file's dated
  changelog stamp, not the current-state section). Added Kit commercials
  to the "Pages:" list and gave it its own detail bullet matching the
  Users-page/Firms-pages shape. While in the same section, also enumerated
  `listKits`/`getKitCommercial`/`setKitCommercial` into the "API client:"
  bullet's function list -- the identical staleness class the reviewer
  flagged, on the same bullet's sibling. Filed by the reviewer as bd
  `polyglot-pdf-a0xr0`; closed by this fix round.
- **Rejected/refuted (0):** none -- every other traced contract came back
  OK (see the reviewer's contract-trace list in the PR).
- **Deferred, pre-existing, not this bead's to fix (2, both already
  filed):** the `kits/` collection's lack of channel-suffixing means the
  admin-console candidate (staging) build writes the DEMO's real kit
  pricing -- filed as bd `polyglot-pdf-vdc3w`; it is a property of the
  whole console programme (the merged Firms page's credit grants have the
  same exposure and are strictly more consequential) rather than of this
  bead specifically, and the reviewer flagged it explicitly for the
  maintainer rather than treating it as blocking. The `display: {}` wipe
  on save was independently reconfirmed pre-existing and currently
  cosmetic (no reader of `display.label` anywhere in the repo) -- already
  filed as bd `polyglot-pdf-zcbm1`, unchanged by this round.
