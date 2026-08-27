---
date: 2026-08-22
bead: polyglot-pdf-xddtl
title: "fix(form_kits): draft-snapshot store methods join snapshot_id into a path without sanitising it"
tags: [security, testing]
---

## Trigger

`LocalFormKitStore.load_draft_snapshot` joined `snapshot_id` straight into
`self._drafts_dir(kit_id) / snapshot_id / "schema.json"`, and
`GCSFormKitStore.load_draft_snapshot` joined it into `_build_blob_path(...)`,
neither with any sanitisation. `snapshot_id` is always the store's own
monotonic counter at write time, so both were unreachable through the only
existing caller -- `restore_kit_draft_snapshot` in
`backend/routes/editor_kit_routes.py` already guards `isascii()+isdigit()`
before the store is touched. Not a live vulnerability, but a real gap: the
archive's sibling reader (`load_archived_revision`) runs its untrusted
segment through `encode_marker()` and never trusts its caller this way --
the draft-snapshot pair were the only path-joining readers in the file left
on the opposite posture, and any second caller added later (a cleanup job,
an admin route) would have inherited the traversal silently.

Verified live before the fix, on both stores:
- Local: `load_draft_snapshot('w7', '../../../outside_secret')` read a
  planted `schema.json` three directory levels above the kit root
  (`_drafts` -> `w7` -> the store root -- three hops to escape it).
- GCS: blob names have no path-resolution semantics, so a `..`-bearing
  `snapshot_id` doesn't climb anywhere -- it becomes a literal substring of
  the constructed blob path. Planting a fake blob at the exact literal
  string `_build_blob_path` would construct (`form-kits/w7/_drafts/../other-
  firms-kit/schema.json`) and requesting `snapshot_id='../other-firms-kit'`
  read it back. This is blob-path *injection*, not filesystem traversal --
  a distinct mechanism with the same outcome.

## What shipped

Both methods now refuse a `snapshot_id` that is not
`isinstance(str) and isascii() and isdigit()`, raising `FormKitNotFound`
before any path or blob-path is built -- matching the archive reader's
posture. One test per store in `backend/tests/unit/test_kit_draft_snapshots.py`.

## Lessons

**Mutation-verifying a traversal test needs the traversal to actually
resolve where the test thinks it does -- get the `..` depth or the exact
literal string wrong and the test passes for free, proving nothing.** Two
distinct instances of the same trap this bead, one per store:

- *Local*: the store root **is** `tmp_path` (`LocalFormKitStore(tmp_path)`
  in the fixture), and the escaped path is
  `<root>/w7/_drafts/<snapshot_id>/schema.json`. Climbing from `_drafts`
  to a sibling of `<root>` itself is three hops (`_drafts -> w7 -> root ->
  sibling`), not two. A test written with `../../outside_secret` (two
  levels) under-shoots by one, lands harmlessly inside the store root, and
  passes identically whether the guard is present or absent -- caught only
  by mutation-testing it (remove the guard, rerun, watch it still pass),
  never by reading the assertion.
- *GCS*: blob names are flat strings with no resolution semantics, so the
  "escape" is injection into a literal path, not a climb. A registry key
  written as the *resolved* target (`form-kits/other-firms-kit/schema.json`)
  never matches what `_build_blob_path` actually constructs
  (`form-kits/w7/_drafts/../other-firms-kit/schema.json`, `..` and all, as
  literal characters) -- the test's decoy blob was simply never at the
  path the code would look up, so it "passed" without exercising anything.
  The fake registry's entry shape mattered too: `_FakeBlob.download_as_bytes`
  reads `registry[name]["data"]`, so a bare string value (rather than a
  `{"data": ...}` dict) crashes with a `TypeError` upstream of the
  assertion -- a different way to fail to prove what the test claims.

Both were caught the only reliable way: remove the guard, rerun, confirm
the test *actually* reddens (and reddens with the *expected* failure mode --
"DID NOT RAISE", not a `TypeError` from an unrelated fixture bug), restore,
confirm green again. Reading the assertion, or trusting a first "3 passed"
result, would have shipped two vacuous tests pinning nothing.

**A store method's guard duplicating its own caller's guard is
intentional, not dead code.** The route's `isascii()+isdigit()` check stays;
this fix's store-level guard is a second, independent layer defending
against any caller the route doesn't gate (`redundant-guards-need-per-
layer-tests` applies here too -- each layer keeps its own test).

## Scoping note

The outer cross-surface review traced the fix's own stated posture ("don't
rely on the one call site staying the only one") outward and found a
genuinely separate, pre-existing gap: `/fill-pdf` in
`backend/routes/pdf_fill_routes.py` passes body-supplied `kit_id` and
`pdf_filename` to `store.load_pdf_bytes` without either of the sanitisers
every other caller in the file uses. Confirmed pre-existing (identical on
`origin/dev`) and out of this bead's scope -- filed as
`polyglot-pdf-7hicd` rather than folded in here.

## Doc freshness

`closeout_prep.py` flagged `docs/components/pdf-filling.md` and
`docs/technical_guide.md` as STALE relative to this commit's
`form_kits.py` mtime. Checked both against the diff: neither doc's
draft-snapshot description changes -- the route-level guard, the ring
eviction, the namespace separation from the archive, and "non-numeric
snapshot ids 400 before reaching the store" are all still accurate exactly
as written. This is a mtime-only false positive, not a content gap; no doc
edit made.

## Files touched

- `backend/services/form_kits.py` -- guard added to both
  `LocalFormKitStore.load_draft_snapshot` and
  `GCSFormKitStore.load_draft_snapshot`
- `backend/tests/unit/test_kit_draft_snapshots.py` -- one mutation-verified
  test per store
