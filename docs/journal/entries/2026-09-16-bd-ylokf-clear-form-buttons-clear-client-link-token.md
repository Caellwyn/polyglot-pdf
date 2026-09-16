---
date: 2026-09-16
bead: polyglot-pdf-ylokf
title: "bug hunt batch 3: config-editor silent Save, worklet URL, vacuous guard test, KNOWN_CHANNELS drift, alert-cap comment, Clear-form token leak"
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
- **Three manual Clear-form/Start-Fresh buttons leaking the client-link
  token** (bd polyglot-pdf-ylokf): `SchemaFormDemo.tsx`, `VoiceOverlay.tsx`,
  and `VoiceOverlayMobile.tsx` each called `SchemaFormStateManager.clear()`
  (or a raw `sessionStorage.removeItem`) plus `clearOnboardingState()`
  directly instead of the composed `clearAllClientState()` the four
  AUTOMATIC wipe triggers (completion, idle timeout, "Done -- clear now",
  staff logout) already use -- so an explicit "clear my data" click left
  `vff_client_link_token` behind. All three now call
  `clearAllClientState()`. In `VoiceOverlay.tsx` the call had to move to
  just before the reload (after the DOM-clearing loop) so
  `wipeSitesReload.test.ts`'s nearby-reload source-scan guard could
  actually see it within its 4-code-line lookahead budget; that guard's
  self-test count moved from 4 to 7 sites and was mutation-verified by
  restoring the far-apart placement.

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
- **A source-level "nearby reload" scan has a real lookahead budget, and
  code has to be written to fit it, not just to work.** `wipeSitesReload
  .test.ts`'s guard only looks 4 CODE lines ahead of a
  `clearAllClientState()` call for a `window.location.reload()`; placing
  the wipe call before an unrelated 30-line DOM-clearing loop (functionally
  harmless -- the reload replaces all of it regardless) still fails the
  guard. When adding a call the guard scans for, place it directly
  adjacent to the reload it must be near, not wherever is logically
  convenient.
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
Fresh buttons previously said they call `clear()`/`removeItem()` +
`clearOnboardingState()` directly and never clear `vff_client_link_token` --
now corrected to describe the fixed behavior (all three call
`clearAllClientState()` too). The `*Last updated:*` stamp itself was missed
in the first commit and bumped in a follow-up commit, caught by
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
- `frontend/src/demo/VoiceOverlay.tsx` -- Clear Form button now calls `clearAllClientState()`, moved adjacent to the reload
- `frontend/src/demo/VoiceOverlayMobile.tsx` -- Clear Form button now calls `clearAllClientState()`
- `frontend/src/demo/clearFormButtonsClearClientLinkToken.test.tsx` -- new: behavioral pin for both overlay Clear Form buttons
- `frontend/src/schema-forms/SchemaFormDemo.tsx` -- Start Fresh button now calls `clearAllClientState()`
- `frontend/src/shared/audioManager.ts` -- worklet URL resolves to an absolute path on every route
- `frontend/src/shared/audioManager.workletUrl.test.ts` -- new: pins the URL across 4 routes under localhost and a stubbed deployed hostname
- `frontend/src/shared/wipeSitesReload.test.ts` -- self-test count updated 4 -> 7 wipe sites
- `tests/test_purge_test_artifacts_cli.py` -- `KNOWN_CHANNELS` drift test now discovers the route file set by globbing
