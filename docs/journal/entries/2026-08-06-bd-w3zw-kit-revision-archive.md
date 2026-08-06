---
date: 2026-08-06
bead: polyglot-pdf-w3zw
title: "Kit revision archive on republish + audit-schema retrieval"
sprint: 19
tags: [testing, conventions]
---

## Trigger

Sprint 19 (docs/sprint_19_firm-tier-kit-lifecycle_plan.md), epic
polyglot-pdf-7jmy child 1 of 4 -- the first implementation bead of the kit
lifecycle epic, and the one the rest of the chain is blocked behind.

Kit storage is ONE slot per kit_id with overwrite-in-place, while the
confirmation audit trail (bd 47r3) records kit_id + a revision marker. A marker
is not a storage address, so republishing a kit destroyed the schema its
earlier confirmation records were confirmed against: the trail could name a
revision the store could no longer produce, and "what did field p1_line3a ask?"
became unanswerable. Epic rubric #2 is exactly that retrieval.

## What shipped

- **Store primitives** (`backend/services/form_kits.py`): `put_archived_revision`,
  `load_archived_revision`, `list_archived_markers` on `FormKitStore` with local
  and GCS implementations, reusing the existing atomic temp+replace write and
  the FormKitNotFound-vs-FormKitStoreError wrapping discipline. Archives live at
  `<kit_id>/_archive/<marker>/`.
- **`encode_marker`**: a kit-controlled marker becomes a path segment, so it is
  untrusted like a filename -- but it cannot go through `safe_filename`, because
  real markers contain characters that guard rejects (the "/" in a "12/2024"
  edition date, the ":" in a `sha256:` fingerprint). It ENCODES rather than
  rejects so every marker round-trips, and collapses dot runs so no literal ".."
  survives in a stored name.
- **The archive hook** (`backend/routes/editor_kit_routes.py`) on the
  revert-to-draft transition, resolving the marker from the superseded
  revision's own schema via the existing `resolve_edition_marker`. Best-effort:
  a failure logs loudly and never blocks the revert.
- **`scripts/read_kit_revision.py`**: operator retrieval by kit_id + marker,
  returning the current schema when the marker still matches it, else the
  archived copy. Keeps "absent" (exit 1) distinct from "store unreadable"
  (exit 2), the read_confirmations.py lesson from bd z2is.
- 19 tests, mutation-verified; full backend suite 1621 passed.

**Hook placement deviates from the plan, deliberately.** The plan said to
archive "on promotion to complete". That is too late: a published kit's schema
cannot be written at all (five write-path gates refuse while status is
complete), so the only route to a new revision is
complete -> draft -> save -> complete, and by promotion time the superseded
bytes are already overwritten. The archive fires on the revert instead -- the
last moment the published revision exists. The plan's INTENT (superseded
revisions stay retrievable) is unchanged; only the location moved.

## Lessons

1. **A helper-level test suite can be fully green with the feature unwired.**
   Four mutations were run. Three were caught. The fourth -- deleting the
   archive call from the status route entirely -- left ALL 17 tests passing,
   because every test called `_archive_published_revision` directly and none
   drove the route. Two tests over the real HTTP endpoint fixed it. This is the
   existing "verify the mutation that MATTERS, and drive the real entry point"
   scar tissue, hit again in a new shape: the tempting mutation (break the
   logic) was caught, while the likely regression (drop the call) was not.
   Generalizable rule already in docs/standards/testing.md's mutation guidance;
   this entry is the second instance.
2. **Check the neighbouring test file's helpers before copying one from
   elsewhere.** The new file's `_run` used `asyncio.get_event_loop()`, which
   passes in isolation and fails once another file closes the loop -- 19
   failures in the full suite after a clean isolated run. `test_editor_kit_routes.py`
   sits beside it and already documents the fix (bd polyglot-pdf-r8gq) in a
   comment on its own `_run`. The DeprecationWarning was visible in the very
   first green run and I did not act on it.
3. **A coarse `surfaces` declaration blocks unrelated work.** The bead declared
   `scripts/` (the retrieval script's name was unknown at planning time), which
   collided with an active P0 voice-bug claim writing spike scripts under the
   same directory. The guard refused the claim, correctly. The fix was to narrow
   the declaration to the exact files -- not to override. Worth preferring
   specific paths at creation time when the file is predictable, and updating
   the declaration as soon as it is known.

## Doc freshness

- `docs/components/pdf-filling.md` BUMPED. It tracks `form_kits.py` and
  enumerates the store's editor write/list surface exhaustively, so three new
  archive methods made that list incomplete -- an additive change still
  falsifies an exhaustive list. Added a Revision archive paragraph (the
  primitives, the marker encoding, why the hook is on revert-to-draft, why
  archives are invisible to both catalogues) and re-stamped the date. My first
  pass through this entry claimed the doc stayed accurate; the freshness gate
  correctly disagreed.
- `docs/standards/confirmation-and-audit.md` describes the marker precedence
  this bead consumes but does not change it (author_version is bead xzw5).

## Beads housekeeping

No orphans. Four stale in_progress beads (52qm.1 grouped-control voice fill;
dft1 client-side resume; ggla DRAFT_ filename; oagt Parts 6/7 invariant) all
belong to OTHER work streams -- the deployment track and the voice epic -- and
were left untouched: transitioning another session's claimed bead from here is
the collision the change-surface guard exists to prevent. This bead's own
surfaces were narrowed at claim time (see Lessons 3).

## Files touched

- `backend/services/form_kits.py` (archive primitives, `encode_marker`)
- `backend/routes/editor_kit_routes.py` (`_archive_published_revision` + the
  revert-to-draft hook)
- `scripts/read_kit_revision.py` (new, operator retrieval)
- `backend/tests/unit/test_kit_revision_archive.py` (new, 19 tests)
- `docs/journal/entries/2026-08-06-bd-w3zw-kit-revision-archive.md` (this entry)
