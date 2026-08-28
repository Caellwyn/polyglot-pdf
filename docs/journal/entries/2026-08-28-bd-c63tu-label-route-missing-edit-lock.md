---
date: 2026-08-28
bead: polyglot-pdf-c63tu
title: "fix(editor): POST /kits/{kit_id}/label writes metadata without checking the edit lock"
tags: [backend, editor-kit-routes]
---

## Trigger

Found during the Opus cross-surface review of `bd polyglot-pdf-fwzln` (the
readiness route's identical missing-guard bug): `POST
/api/editor/kits/{kit_id}/label` (`set_editor_kit_label`) requires only
`require_editor_role`, reads meta via `_load_meta_or_404`, and writes a
merged metadata dict via `store.put_metadata` -- but never called
`_require_edit_lock`, unlike every sibling schema/metadata write route in
the same file. An editor holding no lock on a kit could rename its display
label while a different editor holds the edit lock on it.

`bd fwzln`'s own widened set-pinning property test
(`test_EVERY_schema_write_is_DOMINATED_by_the_editing_lock` in
`test_kit_lifecycle_statuses.py`) already had this exact function
allowlisted WITH a reason recording the deferral, rather than either
silently ignoring or silently fixing it -- so closing this bead means
removing that allowlist entry and letting the property test do its job.

## What shipped

Added the `_require_edit_lock(meta, role)` call, same position every
sibling route uses (after loading metadata, before merging/writing it).

Removed `set_editor_kit_label`'s allowlist entry from the property test --
it is no longer exempt.

Three new tests in `test_editor_kit_routes.py`, mirroring
`test_editor_readiness_routes.py`'s pattern from `bd fwzln`:
1. A kit held by another editor (sam) refuses a rename by a different
   editor (maria) with 409, naming the holder; metadata verified
   byte-identical before/after.
2. Control: the lock holder may rename their own kit.
3. Control: an author preempts an editor's lock (bd `polyglot-pdf-5tuas`).

Corrected `docs/technical_guide.md`'s `/label` route row to mention the new
409 condition, matching the readiness route's row.

Mutation-verified TWICE: removing the new guard call reddened exactly the
first new test in `test_editor_kit_routes.py` (9/10 passed), AND also
reddened `bd fwzln`'s widened property test in
`test_kit_lifecycle_statuses.py` -- confirming that test's whole point
(catching a future omission of this exact shape) actually works now that
this specific allowlist exemption is removed.

## Files touched

- `backend/routes/editor_kit_routes.py` -- added the missing
  `_require_edit_lock` call to `set_editor_kit_label`.
- `backend/tests/unit/test_editor_kit_routes.py` -- 3 new tests.
- `backend/tests/unit/test_kit_lifecycle_statuses.py` -- removed
  `set_editor_kit_label`'s now-obsolete allowlist entry.
- `docs/technical_guide.md` -- corrected the `/label` route row.
