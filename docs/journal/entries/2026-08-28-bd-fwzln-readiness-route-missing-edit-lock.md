---
date: 2026-08-28
bead: polyglot-pdf-fwzln
title: "fix(editor): readiness route writes without checking the edit lock"
tags: [backend, editor-kit-routes]
---

## Trigger

`POST /api/editor/kits/{kit_id}/readiness` (`backend/routes/editor_readiness_routes.py`)
persists a readiness stamp via `_stamp_readiness` -> `store.put_metadata`, but
never called `_require_edit_lock` -- every sibling schema/metadata write path
in `editor_kit_routes.py` does. So editor A could overwrite the readiness
stamp of a kit editor B holds the lock on.

`_require_edit_lock`'s own docstring already names this exact enumeration
failure mode: "every route containing `put_schema` must call this" -- this
route slipped the enumeration because it reaches `put_metadata` through the
`_stamp_readiness` helper rather than calling it directly, and the route was
filed in a SEPARATE module (`editor_readiness_routes.py`) specifically so it
would not conflict with concurrent kit-lifecycle work on
`editor_kit_routes.py` (bd `polyglot-pdf-na1zy`'s own docstring) -- which also
meant it wasn't sitting next to its siblings where the pattern is visible.

## What shipped

Added the `_require_edit_lock(meta, role)` call, in the same position
(after the write-lock check, before the actual write) every sibling route
uses.

Three new tests:
1. A kit held by another editor (sam) refuses a restamp attempt by a
   different editor (maria) with 409, naming the holder -- the metadata file
   is verified byte-identical before/after (never-destroy contract, same as
   the existing write-locked and unparseable-metadata tests in this file).
2. Control: the lock holder may restamp their OWN kit (the guard gates on
   identity, not mere lock presence).
3. Control: an author may restamp a kit an editor holds (the existing
   author-outranks-editor preemption rule, bd `polyglot-pdf-5tuas`, applies
   here too -- not a stricter rule invented for this route).

Mutation-verified: removing the new `_require_edit_lock` call reddened
exactly the first new test (9/10 passed) -- the two control tests correctly
stayed green since neither depends on the guard actually firing.

## The Opus cross-surface review found the fix wasn't pinned by the set

The repo already has a property test guarding exactly this invariant,
`test_EVERY_schema_write_is_DOMINATED_by_the_editing_lock` in
`test_kit_lifecycle_statuses.py`. It statically scans `editor_kit_routes.py`
for `await store.put_schema(` calls and asserts each is preceded by a
`_require_edit_lock(` call in the same function -- but it scanned only ONE
module and ONE write shape. The readiness route lives in a SEPARATE module
(`editor_readiness_routes.py`, deliberately split out per bd `na1zy` to
avoid conflicting with concurrent kit-lifecycle work) and writes via
`put_metadata`, not `put_schema` -- invisible on both axes. So this bug had
been shippable under a green test suite the whole time; the property test's
own scope was the gap, not just this one route.

Widened the test to scan both route modules and both write shapes. That
surfaced a THIRD issue: the property test is a static text-scan and cannot
see through a helper call -- `_stamp_readiness` (the shared helper both the
hosted save path and this route call) has its own unguarded `put_metadata`
write, by design (its callers guard before invoking it). A naive widening
either flags `_stamp_readiness` itself as an offender (wrong -- it has no
lock context of its own) or, if `_stamp_readiness` is blanket-allowlisted,
goes blind to a caller that stops guarding before calling it (verified: this
is exactly what happened on a second mutation-test pass -- allowlisting the
helper by name made the test pass even with my own new guard call removed).
Fixed by treating a CALL to `_stamp_readiness` as a write-site marker in the
calling function, so the guard requirement moves to where it actually
belongs -- confirmed correct only after a third mutation-verify pass
(remove the guard -> the widened test now reddens on exactly
`editor_readiness_routes.stamp_kit_readiness`).

Also corrected two tier-2 docs that had drifted with the property test's own
scope: `docs/technical_guide.md`'s readiness-route row and
`docs/components/pdf-filling.md`'s lock-guard summary both claimed the
lock-domination guarantee more broadly than the (pre-widening) test actually
enforced.

Filed `polyglot-pdf-c63tu` for a genuinely separate, pre-existing sibling gap
found during this same trace (`POST /kits/{kit_id}/label` has the identical
missing-guard bug) -- correctly allowlisted-with-a-reason in the widened
property test rather than silently fixed here or silently ignored.

## Files touched

- `backend/routes/editor_readiness_routes.py` -- added the missing
  `_require_edit_lock` call.
- `backend/tests/unit/test_editor_readiness_routes.py` -- 3 new tests.
- `backend/tests/unit/test_kit_lifecycle_statuses.py` -- widened the
  lock-domination property test to both route modules, both write shapes,
  and helper-call-site tracking for `_stamp_readiness`.
- `docs/technical_guide.md`, `docs/components/pdf-filling.md` -- corrected
  the lock-guard coverage claims.

## Follow-up

`polyglot-pdf-c63tu` filed for `set_editor_kit_label`'s identical
missing-guard bug (pre-existing, out of this bead's scope).
