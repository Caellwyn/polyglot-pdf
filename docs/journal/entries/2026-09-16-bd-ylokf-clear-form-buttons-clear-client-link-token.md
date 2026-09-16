---
date: 2026-09-16
bead: polyglot-pdf-ylokf
title: "bug hunt batch 3: config-editor silent Save, worklet URL, vacuous guard test, KNOWN_CHANNELS drift, alert-cap comment, Clear-form token handling"
tags: [testing, review, security]
---

## Trigger

Third batch of the self-directed sonnet/haiku bug-hunt sweep, continuing on
from batches 1 (PR #800) and 2 (PR #809). The maintainer's instruction:
self-select simple beads tagged `tier: sonnet` / `tier: haiku`, fix and
close as many as possible, re-tier to `opus` and release any that prove more
complex on investigation.

## What shipped

Six independently-scoped fixes, each with its own mutation-verified pinning
test:

- **admin-console Save-on-unset silent no-op** (bd polyglot-pdf-mmn1n,
  duplicate bd polyglot-pdf-mcark closed as the same bug): clicking Save on
  a config row whose draft was UNSET did nothing visible -- no PUT, no
  message, and a stale "Saved &lt;other key&gt;." banner from a previous
  row's save stayed on screen, reading as confirmation of a click that did
  nothing. `handleSave` now shows a message naming the key and explaining
  the fallback, and clears any stale banner first.
- **audioManager.ts's AudioWorklet URL resolution** (bd polyglot-pdf-43dxt):
  the worklet URL resolved path-relative to the current route in
  production (`new URL('../shared/...', window.location.href)`), a
  leftover from an old GCS `demo/`-subdirectory layout. It happened to
  resolve correctly on every route in production today purely by
  arithmetic coincidence (a single `../` cancelling a single path
  segment) -- the same class of bug bd polyglot-pdf-3bsyv fixed for
  index.html assets, one route depth away from breaking. Now resolves to
  the absolute `/shared/audio-processor.worklet.js` on every route,
  independent of path depth. Enumerated other path-relative runtime asset
  resolutions per CLAUDE.md scar #8 (grepped for `new URL(...,
  window.location.href)` across `frontend/src`) -- this was the only
  instance; everything else matching `../shared/` is a static import
  statement resolved by the bundler, not a runtime browser resolution.
- **A vacuous guard test** (bd polyglot-pdf-uyoi4):
  `test_get_db_never_returns_a_working_client_with_no_app_pre_existing`'s
  assertion (`assert db is None`) sat INSIDE a `pytest.raises(Exception)`
  block. An `AssertionError` is itself an `Exception`, so the test passed
  even when the no-real-Firestore guard was fully defeated and `get_db()`
  returned a real, working client. Moved the assertion outside the
  `raises` block. The mutation test that proves this (removing all three
  guard patches) reproduced the exact 2026-09-15 incident condition ON
  THIS MACHINE: with the guard fully removed, `get_db()` succeeded and
  returned a REAL, live Firestore client via this developer's own working
  ADC -- the precise failure mode the guard exists to prevent. Also
  widened the module docstring, which still named only two of the three
  patch targets after the guard's round-2 warm-cache fix.
- **A hand-listed drift test** (bd polyglot-pdf-ddavu):
  `test_known_channels_matches_every_admin_route_copy` hand-listed 3 of
  the 7 `admin_backend/routes/*.py` modules carrying their own literal
  `KNOWN_CHANNELS` tuple, silently missing `ops_routes.py`,
  `report_routes.py`, `sweep_routes.py`, and `usage_routes.py` -- the
  first two of whose own comments already said "matching every other
  admin route module's own copy." Now derives the file set by globbing
  for the literal, with a `>=5` floor as a broken-glob tripwire (5, not 7,
  since the floor is a gross-undercount tripwire rather than a tight
  bound -- see the test's own docstring). Mutation-verified against
  exactly the shape the old test could not catch: changing
  `ops_routes.py`'s tuple alone (leaving the three originally hand-listed
  files and `purge.py` untouched) now reddens the test.
- **A code comment describing the wrong evaluation order**
  (bd polyglot-pdf-lnvjg): the `_PAGE_LIMIT` comment in
  `admin_backend/routes/alert_routes.py` claimed the firm-scoped route's
  filter runs AFTER the page cap is applied to the full stream (a
  cross-firm truncation hazard). Both list helpers actually filter FIRST,
  then sort, then cap the already-filtered result -- the cap is per-firm,
  not global. Comment-only fix, no behavior change.
- **Three manual Clear-form/Start-Fresh buttons and the client-link token**
  (bd polyglot-pdf-ylokf): the bead's premise was that `SchemaFormDemo.tsx`,
  `VoiceOverlay.tsx`, and `VoiceOverlayMobile.tsx` each called
  `SchemaFormStateManager.clear()` (or a raw `sessionStorage.removeItem`)
  plus `clearOnboardingState()` directly instead of the composed
  `clearAllClientState()` the four AUTOMATIC end-of-session wipe triggers
  (completion, idle timeout, "Done -- clear now", staff logout) already
  use -- and that this was a bug, since it left `vff_client_link_token`
  behind after an explicit "clear my data" click. The first pass of the
  fix routed all three handlers through `clearAllClientState()` to close
  that "leak". **The premise was wrong, and the Opus outer cross-surface
  review caught it before merge**: `ClientLinkEntry.tsx`'s reload-recovery
  branch depends entirely on `hasClientLinkToken()` to reach the "ready"
  phase once the URL's redemption fragment is stripped (which it always is,
  post-redemption) -- clear the token and the reload every one of these
  handlers triggers lands on "This link is not valid" instead of the
  client's own form. `onboardingStorage.ts`'s `clearOnboardingState()`
  already documents the matching half of this invariant (bd
  polyglot-pdf-ugm6: "A CLIENT-LINK SESSION KEEPS ITS FORM"); the token
  needs the identical protection. The corrected fix reverts all three
  handlers to `SchemaFormStateManager.clear()` + `clearOnboardingState()`
  -- the ORIGINAL pre-bug-hunt shape -- and never touches the token there.
  A staff session never has the token set in the first place, so this costs
  staff nothing; a client-link session keeps its ability to resume.
  `wipeSitesReload.test.ts`'s self-test count went 4 -> 7 -> back to 4 as
  the fix was tried and then corrected -- the three manual buttons are
  correctly NOT on the `clearAllClientState()` scan path. Three behavioral
  tests (one per handler) now pin the CORRECTED direction: the token
  survives a click while form state is cleared.

## Lessons

- **A type-check catches what a test-runner mock cannot.** The
  `clearFormButtonsClearClientLinkToken.test.tsx` addition initially
  compiled a `setChannelConfigKey` mock returning `undefined` where the
  function's real return type is `ConfigSetResult` -- `vitest run` alone
  never caught this (it does not run `tsc`), but `npm run build:hosted`
  (which admin-console's own bundle-content test invokes) did, and the
  suite would have shipped a type error that only a production build
  surfaces. Running the actual build, not just the test runner, before
  closing a frontend bead is worth the extra step when the change touches
  a typed mock.
- **A bead's own premise can be wrong, and "the exit criteria pass" is not
  proof it wasn't.** bd ylokf described the token surviving a manual
  Clear-form click as a leak to close. It is not -- it is the SAME
  mid-session-preservation invariant `clearOnboardingState()`'s own comment
  already documents for the form pin (bd polyglot-pdf-ugm6), just applied
  to the credential instead of the form id. Both the inner fresh-eyes round
  and the first outer-review pass on the FIRST fix attempt scored the
  bead's stated exit criteria as met and moved on; it took the SECOND
  outer-review pass -- specifically tracing the consumer
  (`ClientLinkEntry.tsx`'s reload-recovery branch) that the bead's own
  description never mentioned -- to find that meeting the letter of the
  bead shipped a client-facing lockout. A bead whose fix touches a shared
  wipe path used by both staff and client-link sessions needs its
  consumers traced, not just its own exit criteria checked.
- **A source-level "nearby reload" scan has a real lookahead budget, and
  code has to be written to fit it, not just to work** -- moot for this
  bead's final shape (the three manual buttons no longer call
  `clearAllClientState()` at all), but worth keeping for the next site that
  does: `wipeSitesReload.test.ts`'s guard only looks 4 CODE lines ahead of
  a `clearAllClientState()` call for a `window.location.reload()`. When
  adding a call the guard scans for, place it directly adjacent to the
  reload it must be near.
- **Re-verify a git branch's diff against `origin/dev` before trusting it,
  especially mid-session after another PR from the same lineage merged.**
  This batch's branch was initially created on top of batch 2's now-merged
  commits; `git diff origin/dev...HEAD --stat` still showed the ENTIRE
  batch-2 diff as "new" because the squash-merge produced different SHAs
  than the original unsquashed commits. `git rebase origin/dev` hit real
  conflicts trying to replay the old commits against files `origin/dev`
  had since moved forward on. Recovered by diffing against the exact
  parent commit the branch was built on (`git diff <old-parent>...HEAD`,
  which isolates only the genuinely new work), filtering out the two
  doc/journal hunks already merged upstream, and applying that as a patch
  onto a fresh branch cut from current `origin/dev`.

## Doc freshness

`docs/components/schema-forms.md` was flagged STALE against this branch's
changes to `frontend/src/demo/VoiceOverlay.tsx`,
`VoiceOverlayMobile.tsx`, and `frontend/src/schema-forms/SchemaFormDemo.tsx`.
The "two-step path" paragraph describing the three manual Clear-form/Start
Fresh buttons went through two revisions matching the two fix attempts:
first corrected to (wrongly) say all three now call `clearAllClientState()`
too, then corrected again once the outer review caught the client-link
lockout to state the final, shipped behavior -- the three manual buttons
are deliberately NOT on the `clearAllClientState()` path and never clear
`vff_client_link_token`. The `*Last updated:*` stamp itself was missed in
the first commit and bumped in a follow-up commit, caught by
`check_doc_freshness.py`.

All other STALE docs the checker flagged (tool-call-flow.md,
websocket-routing.md, si-reduction.md, stateless-architecture.md,
ws-protocol.md, technical_guide.md, and others) track files this branch did
not touch -- pre-existing staleness from other concurrent work on `dev`,
left as-is per the closeout rule.

## Files touched

- `admin-console/src/components/ConfigEditorPage.tsx` -- visible message + stale-banner clear on Save-while-unset
- `admin-console/src/components/ConfigEditorPage.test.tsx` -- two new pinning tests, corrected mock return type
- `admin_backend/routes/alert_routes.py` -- `_PAGE_LIMIT` comment corrected (filter-then-cap, not cap-then-filter)
- `backend/tests/unit/test_no_real_firestore_guard.py` -- assertion moved outside `pytest.raises`, docstring widened to three patch targets
- `docs/components/schema-forms.md` -- corrected "two-step path" paragraph, stamp bumped
- `frontend/src/demo/VoiceOverlay.tsx` -- Clear Form button clears form state + onboarding selection, deliberately preserves the client-link token
- `frontend/src/demo/VoiceOverlayMobile.tsx` -- Clear Form button clears form state + onboarding selection, deliberately preserves the client-link token
- `frontend/src/demo/clearFormButtonsClearClientLinkToken.test.tsx` -- behavioral pin: both overlay Clear Form buttons clear form state but PRESERVE the client-link token
- `frontend/src/schema-forms/SchemaFormDemo.tsx` -- Start Fresh button clears form state + onboarding selection, deliberately preserves the client-link token
- `frontend/src/schema-forms/SchemaFormDemo.startFreshPreservesClientLinkToken.test.tsx` -- behavioral pin: Start Fresh clears form state but PRESERVES the client-link token
- `frontend/src/shared/audioManager.ts` -- worklet URL resolves to an absolute path on every route
- `frontend/src/shared/audioManager.workletUrl.test.ts` -- new: pins the URL across 4 routes under localhost and a stubbed deployed hostname
- `frontend/src/shared/wipeSitesReload.test.ts` -- self-test count confirms exactly 4 wipe sites (the three manual buttons are correctly excluded)
- `tests/test_purge_test_artifacts_cli.py` -- `KNOWN_CHANNELS` drift test now discovers the route file set by globbing
