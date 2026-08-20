---
date: 2026-08-19
bead: polyglot-pdf-xg0pm
title: "docs(technical_guide): fix stale editor_kit_routes.py citations + kit-status enumeration"
tags: [review]
---

## Trigger

Continuing the low-complication-bead sweep: two related beads in the same
file. `xg0pm` found that four `backend/routes/editor_kit_routes.py` line
citations in `docs/technical_guide.md`'s Surface contracts section 1 --
explicitly the blast-radius reference CLAUDE.md points reviewers at -- had
drifted from the code they describe, sending a reviewer to the wrong
function. `vf48u` found that the same file's translate-options route row,
plus `docs/components/config-deployment.md`'s deploy-gate sentence, still
enumerated the kit lifecycle as two-valued after bd 6dz0 added a third
status (`unpublished`).

## What shipped

For `xg0pm`: re-derived and mechanically verified all four cited line
ranges against the current file (`save_editor_kit_schema` at 1617-1700, not
602-646; `FormSchema.model_validate` at 2809, not 1530; the lint gate at
2841-2852, not 1571-1600; `get_editor_kit_schema` at 1567-1568, not 553).
While re-verifying the same paragraph -- not in the bead's original
enumeration -- found the adjacent `form_kits.py` `put_schema` citations had
also drifted across the abstract base / Local / GCS store classes, and
fixed those too. Verified every citation with a small script asserting the
cited line range's text actually contains the function/gate name claimed.

For `vf48u`: widened both stale two-valued enumerations to match the
`/status` row's already-correct "write-locked (complete OR unpublished)"
framing. Neither fix touches behavior -- both underlying gates
(`_is_write_locked`, `kit_is_complete`) were already correct; this was pure
doc drift.

Also pruned both files' `*Last updated:*` stamps. `technical_guide.md`'s had
grown into a long stacked chain of prior beads' fix locations (the banned
history-chain shape, though pre-existing and outside these two beads'
scope to fully re-architect); replaced with a clean current-state sentence,
preserving the two genuinely current-state facts mixed into that same
paragraph (the Surface-contracts-map's stated purpose, and the
continuous-DTI-is-default note).

## Lessons

Re-verifying an entire cited paragraph rather than only the bead's named
citations caught three more drifted citations in the same sentence
(`form_kits.py`'s `put_schema` across all three store implementations) that
weren't part of the original bug report. This is the same "enumerate the
set, not the instance" discipline CLAUDE.md scar tissue #7 already names --
applied here at sentence-scope rather than repo-scope: when a fix touches
one claim in a dense multi-citation sentence, checking every OTHER claim in
that same sentence is cheap and catches siblings before a future review
round has to find them one at a time.

## Doc freshness

- `docs/technical_guide.md` -- stamp rewritten (pruned the stacked-history
  chain to a current-state sentence); live checker reports OK.
- `docs/components/config-deployment.md` -- stamp bumped in its existing
  journal-pointer style; live checker reports OK.

## Files touched

- `docs/technical_guide.md` -- fixed 9 line citations in Surface contracts
  section 1 (bd xg0pm) + widened the translate-options row's status
  enumeration (bd vf48u) + stamp rewrite
- `docs/components/config-deployment.md` -- widened the deploy-gate
  sentence's status enumeration (bd vf48u) + stamp bump
