---
date: 2026-08-07
bead: polyglot-pdf-na1zy
title: "s18 C4b: local-folder readiness stamping (the local half of C4)"
sprint: 18
tags: [schema-editor, testing]
---

## Trigger

Sprint-18 C4 (bd g687) shipped one definition of review progress
(publish_readiness) with stamps written on the HOSTED save/publish routes --
but a LOCAL-folder save (App.handleSave -> writeSchemaToHandle) is a pure
File System Access write with no backend round trip, so no local save ever
refreshed a stamp. Consequences already filed: a catalogue Refresh moved a
kit's percentage BACKWARD (bd bqgr), the "absent" hint told local users to
do something the local save could not deliver (bd oqoh), and a locally-saved
kit rendered a STALE confident percentage (bd j8sr, second half). C4b was
split out at C4's closeout to settle the design question: who may write a
stamp when the save never touches the backend?

## What shipped

Option (b) from the bead -- ONE writer preserved -- plus an honest fallback:

- **New backend route POST /api/editor/kits/{kit_id}/readiness**
  (backend/routes/editor_readiness_routes.py, registered in main.py): takes
  the just-saved schema and recomputes + persists the stamp through the SAME
  `_stamp_readiness` the hosted save uses (identical lint inputs, identical
  best-effort and never-destroy-metadata semantics). It lives in its own
  small module rather than editor_kit_routes.py because that file is
  concurrently claimed by the sprint-19 kit-lifecycle work (bd 6dz0); this
  module only imports its helpers, so the two changes cannot conflict.
- **Client wiring (App.handleSave)**: after a successful IN-PLACE kit save,
  when a backend is reachable AND the same-folder handshake (bd s2bf) proved
  it serves the picked folder, the editor calls the route -- the backend
  writes metadata.json in the shared folder and the catalogue's next read
  shows the fresh number. When no backend is reachable (or the call fails),
  the client only INVALIDATES the old stamp (`readiness.verified = false`,
  schema-editor/src/utils/localStamp.ts) so the card degrades to the verify
  hint instead of a stale confident percentage. Invalidation retracts a
  claim; it computes nothing, so it is not a second stamp producer. Stamping
  is best-effort either way: the completed save never fails or blocks on it.
- **Save-As guard hardened**: the stamp block gates on a local `pickedNow`
  flag computed BEFORE the async `setSavingToKit(false)` state flip -- the
  state read alone would have stamped kit A's metadata after a Save-As to an
  arbitrary file, C4's criterion-3 hazard.
- **Tests** (all mutation-verified):
  backend/tests/unit/test_editor_readiness_routes.py (token gate, 404/422,
  stamp persists measuring the POSTED schema with other metadata keys
  preserved, stale stamp replaced, unparseable metadata left byte-identical);
  schema-editor localStamp.test.ts (invalidate preserves every other key,
  no-ops with nothing to retract, never destroys an unparseable file; the
  POST carries the editor token and AuthErrors on 401); and
  App.local-stamp.test.tsx pinning the three exit criteria at the wiring
  level (no-backend save invalidates; backend+handshake save restamps; a
  failed restamp falls back to invalidation without failing the save;
  Save-As touches nothing; reload-from-file/discard touches nothing).
  Mutations: disabling the stamp block reddens 4 tests; dropping the
  pickedNow guard reddens exactly the Save-As pin.

Full suites green: backend pytest and the schema-editor vitest run
(323 files / 1225 tests), plus tsc.

Fresh-eyes (sonnet): NO-GAPS round 1, all three criteria PASS. Opus
cross-surface round 1: GAPS-FOUND (2), both adopted -- (1) the route was
registered on the hosted app with no status check, so an editor token could
overwrite a PUBLISHED kit's stamp with counts for a body never saved; fixed
with a 409 on complete kits (mutation-verified test) and a marked write-lock
site for the sprint-19 lifecycle work (bd 6dz0) to fold into its
is-write-locked predicate. (2) docs/technical_guide.md's route table was
missing the new route; row added and the stamp bumped. The reviewer also
filed bd g8ftl (narrow invalidate-after-successful-restamp race; degraded
outcome is the honest hint, non-blocking). Opus rounds 2-3: PR #562 (bd
6dz0 kit-lifecycle statuses) merged into dev mid-closeout; after the merge
the reviewer found two interaction gaps, both adopted -- the 409 guard
widened to 6dz0's _is_write_locked predicate with _lock_reason's
state-naming detail (an unpublished kit must refuse too, with the right
message), and the client post-save block now SKIPS write-locked kits
entirely (complete or unpublished): their metadata.json is protected bytes,
not even a stamp retraction may touch it. Both parametrized over the full
write-locked set and mutation-verified per parametrization.

## Lessons

- A React state setter inside the same closure is a trap for guards: the
  flag you just "set" still reads its old value for the rest of the
  callback. Compute the guard from local facts (`pickedNow`), not from state
  you are mid-flipping.
- "One writer" survives a mode split if the offline arm is restricted to
  RETRACTING claims rather than making them -- invalidation needs no
  computation, so it cannot drift from the definition.

## Doc freshness

No tier-1/2 doc tracks the local save path in prose; the C4 stamp contract
docs live in code docstrings (readinessStamp.ts, publish_readiness.py),
updated in place. Freshness-checker STALE flags at closeout all track files
this branch did not touch (pre-existing; left for their owning changes).

## Files touched

- backend/routes/editor_readiness_routes.py (new) + backend/main.py
- backend/tests/unit/test_editor_readiness_routes.py (new)
- schema-editor/src/utils/localStamp.ts (new) + localStamp.test.ts (new)
- schema-editor/src/App.tsx (handleSave wiring + import)
- schema-editor/src/App.local-stamp.test.tsx (new)
- docs/journal/entries/2026-08-07-bd-na1zy-local-folder-readiness-stamping.md
