---
date: 2026-09-01
bead: polyglot-pdf-yofv4
title: "test(kits): derive the write-lock-gated route set instead of hand-listing it"
tags: [backend, testing]
---

## Trigger

`test_kit_revision_archive.py::test_every_schema_writing_editor_route_refuses_a_published_kit`'s
docstring claimed "A new SHAPE-writing route added later must gate or
fail this test" -- but the test body was a hand-typed list of six client
calls. A seventh schema-writing route added without a write-lock gate
would simply not be exercised, and the test would stay green. Matches
CLAUDE.md scar #7 (enumerate the block, don't hand-list it).

## What deriving the set actually found

Enumerating `ekr.router.routes` and checking which handler (or a helper
it calls) invokes `_is_write_locked` surfaced a REAL gap, not a
hypothetical one: `restore_kit_draft_snapshot`
(`POST /kits/{kit_id}/draft-snapshots/{snapshot_id}/restore`) calls
`store.put_schema` directly and IS gated by `_is_write_locked` in the
route itself -- but was never exercised by the old hand-typed list. It
had been gated correctly all along; the test just never proved it.

Also noted: `regenerate_editor_kit_guidance`'s gate lives in a helper it
calls (`_regenerate_guidance_locked`), not the route handler directly --
a purely source-inspection-based derivation (walking only the route's own
function body) would miss it. Chose NOT to build an automated
source-walker for this reason: reflection over an arbitrarily deep call
graph is its own maintenance burden, and the router's registered handler
set is small and stable enough that a maintained ALLOWLIST partition
(gated vs. exempt-with-a-reason) is the more legible and equally rigorous
choice, provided the partition itself is asserted complete against the
live router on every test run.

## Fix

- Added `_WRITE_LOCK_GATED_ROUTES` (7 entries, driven to 409 in the
  behavioral test) and `_WRITE_LOCK_EXEMPT_ROUTES` (every other route on
  `ekr.router`, each with an inline reason).
- Added `test_every_ekr_route_is_accounted_for_by_the_write_lock_partition`:
  enumerates `ekr.router.routes` at test time and asserts the live set
  equals exactly the union of the two maintained sets above -- both
  directions (a new unaccounted route, and a stale listed route no longer
  on the router).
- Extended the behavioral test to drive the newly-discovered `restore`
  route to a 409, tracked via a `driven` set built by a new `_assert_gated`
  helper, and asserted `driven == _WRITE_LOCK_GATED_ROUTES` (see the
  Review section below for why this replaced an earlier, weaker
  `len(...) == 7` check).
- Rewrote the docstring to describe what actually backs the "a new route
  must gate or fail this test" claim now: the enumeration test, not
  discipline.

## Review

Two rounds, both `NO-GAPS`. The Opus cross-surface round re-derived the
entire 25-route partition independently (not trusting the inner
reviewer's count) and filed two non-blocking follow-ups:

- `polyglot-pdf-941b4` (left open): the partition covers only
  `ekr.router`; a sibling router (`editor_readiness_routes.py`, same
  `/api/editor` prefix) has its own `_is_write_locked`-gated route
  (`stamp_kit_readiness`) that this partition's "complete" framing could
  wrongly be read as also covering. Not a live gap -- that route already
  has its own dedicated test -- but a real scope boundary worth a reader
  knowing about. Left as its own bead rather than folded in here: it is a
  materially different property test (a second router, a different
  fixture) and bundling it would have re-widened this bead's scope past
  what it was filed to fix.
- `polyglot-pdf-fe5og` (fixed inline, this same diff): the original
  `assert len(_WRITE_LOCK_GATED_ROUTES) == 7` guard didn't actually catch
  what its own comment claimed -- deleting one of the driven `client.post`
  calls left the length at 7 and the test green. Replaced with a `driven`
  set literally built from every `_assert_gated` call, compared for
  EQUALITY (not just count) against `_WRITE_LOCK_GATED_ROUTES`.

## Testing

Mutation-verified all three fix components:
1. Added a stub route (`POST /kits/{kit_id}/mutation-test-stub`) that
   calls `store.put_schema` with NO `_is_write_locked` gate. The
   enumeration test failed immediately with a clear message naming the
   unaccounted route and the decision required. Removed the stub.
2. Removed `restore_kit_draft_snapshot`'s own `_is_write_locked` check.
   The behavioral test's new `restore` assertion failed (404 instead of
   409, since without the gate the snapshot-id lookup runs first).
   Restored.
3. Deleted the `restore` `_assert_gated` call (keeping `_WRITE_LOCK_GATED_
   ROUTES` unchanged). The `driven == _WRITE_LOCK_GATED_ROUTES` assertion
   failed with a clear diff naming the missing route -- the exact
   regression the earlier `len(...) == 7` version did NOT catch. Restored.

Full `test_kit_revision_archive.py` + `test_editor_kit_routes.py`: 242
tests, green.
