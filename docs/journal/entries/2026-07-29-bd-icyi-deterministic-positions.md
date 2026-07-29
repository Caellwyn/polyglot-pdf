---
date: 2026-07-29
bead: polyglot-pdf-icyi
title: "Deterministic widget rects must OWN pdf_position; LLM coords are the no-rect fallback"
tags: [extractor, postmortem, testing]
---

## Trigger

The maintainer extracted a fresh W-7 kit and reported that NO bounding boxes
drew on the schema editor's PDF preview -- except for checkboxes. The previous
two extractions of the same form had drawn them correctly.

Measured immediately: 48 of the 54 fields carried `pdf_position.page = 0`
instead of the required 1-based page. The editor's PDF viewer matches pages
`1..numPages` by exact equality, so page 0 matches no rendered page and the
overlay silently paints nowhere. The 6 fields that DID draw were exactly the
choice fields (5 radio + 1 checkbox_group) -- the ones whose rects come from
the deterministic dump path, which correctly applies `+1`.

First question answered before touching anything: **was this the guidance
staleness gate that had just merged (PR #508)?** No. That PR's only change to
`extract_form.py` was reporting a count of discarded model proposals; it
touched no positioning, page, or overlay code. Confirmed by reading the diff
hunks directly, not the commit subject.

## What shipped

**Root cause was a priority inversion, not a missing guard.** The extraction
contract (`scripts/bakeoff/schema_contract.py` FIELD SHAPE) *asked* the model
for `pdf_position`, and `_has_usable_position` accepted whatever came back as
long as width and height were positive -- it never validated `page`. So the
deterministic dump-rect back-fill only ran as a REPAIR for missing/zero-size
rects and never overwrote a plausible-but-wrong model rect. The same run also
rounded every coordinate (469.2 -> 469).

Evidence that made the diagnosis airtight rather than plausible:

- All 48 broken fields HAD a matching widget with a real rect available -- the
  data was never missing, it was ignored.
- v2 (the previous day, same prompt) carried the SAME 48 model-authored
  integer-rounded rects; it just happened to emit `page: 1`. Pure model
  non-determinism against an unguarded field, not a code regression.
- 486 widgets across all four real kits (w7 69, i-90 195, f1040 199,
  w9-heldout 23) carry non-degenerate rects: 0 degenerate. The deterministic
  path is reliable on AcroForms.

**Maintainer decision (2026-07-29): flip the priority.** Where a widget
resolves, the dump rect wins UNCONDITIONALLY at both field and option level,
and the contract now tells the model NOT to emit `pdf_position` at all --
exactly the treatment `parts`/`sections`/`section_id` already get. Model
coordinates survive ONLY where no widget resolves (the route a future
non-AcroForm/scanned PDF needs, deliberately kept rather than deleted). On
that fallback path a 0-based page is an ordinal counting-scheme difference,
not corrupt data, so `_normalize_model_page_base` shifts every model page up
by one when any is 0. A field with neither a resolvable widget nor a usable
model rect now carries NO `pdf_position` key, instead of a zero-size
placeholder that reads as a real position downstream.

**An unexpected second symptom fixed itself.** Section derivation reads field
positions, so page 0 had been poisoning it too: v3 dumped 48 fields into one
meaningless "Page 0 (top)" bucket that had to be cap-split in half. The fresh
extraction derived the form's actual printed structure -- Name, Applicant's
Mailing Address, Foreign (non-U.S.) Address, Birth Information, Acceptance
Agent's Use ONLY, 8 sections in 1 part. One bug, two visible symptoms.

**Fresh re-extraction (the maintainer chose re-extract over in-place repair,
to see a fresh run in totality):** 54/54 fields on page 1, 0 missing, and
every rect an exact match to the PDF's widget geometry; 21/21 option positions
correct; integer-rounded rects 48 -> 5 (those 5 are integral in the PDF
itself). Guidance coverage improved incidentally (52 vs 51 instructions, 50 vs
43 details), lint warnings 6 -> 5, cost $2.13 vs $2.05.

### Fresh-eyes triage

Two gaps found, **both adopted** (neither deferred):

1. **The contract change would have silently zeroed a bake-off metric.** Raw
   bake-off arms render the same `SCHEMA_CONTRACT` and are scored on their
   DRAFT output, which never goes through the back-fill -- so once the contract
   stopped asking for `pdf_position`, `schema_score._pos_match` would score
   every future arm's absent position as a MISS, pegging the attribute at 0%
   forever and breaking comparability with every historical number. The
   reviewer filed it out-of-scope (bd polyglot-pdf-89ge); I **closed that bead
   and fixed it here instead** -- my diff causes it, so shipping it broken was
   not an option. Absent draft position is now not-applicable (`None`), exactly
   as an absent GOLD position already was. A present-but-wrong position is
   still a miss, so the metric keeps its teeth. This is the same
   scorer-artifact class `test_schema_score_derivation.py` already existed to
   fix for sections (bd mhyt) -- worth knowing that "the contract stopped
   asking for X" always has a scorer half.
2. **An unpinned behavior change at the option level.** Removing the early
   `continue` means an option with a bogus `pdf_field_name` but a plausible
   model rect is now *reported* in `unmatched` where it used to be skipped
   silently. That is the better behavior (a bogus widget name is what the
   unmatched list exists to surface), but it was a real delta with no test --
   now pinned.

Also noted and NOT flagged as blocking: `_complete_grouped_families` appends
options with no `pdf_position` at all (pre-existing, untouched by this diff);
and the fallback's "any page==0 -> shift all" rule is form-wide and blunt, but
unreachable on AcroForms and documented as an accepted tradeoff.

## Lessons

**"Ask the model for a value the computer can compute exactly" is a latent
bug, not a shortcut.** Five numbers per field were being generated instead of
read, and the failure was invisible for two extractions because the model
guessed the right page base by luck. The generalizable rule: if a value is
mechanically derivable from the source artifact, derive it and tell the model
not to emit it. `parts`/`sections` already worked this way in this very
contract -- `pdf_position` was the straggler.

**A test that is internally consistent can still miss a whole class of bug.**
The broken schema was well-formed: valid page key, valid numbers, positive
sizes. Nothing in 2257 tests noticed, because nothing compared the schema
against the PDF it describes. The new real-kit guard does exactly that, with a
0.06pt tolerance (the dump serializes rects to one decimal, so a deterministic
value legitimately differs from PyMuPDF's raw float by up to 0.05pt -- exact
equality false-fires while a model rect, rounded to whole points, is caught
easily).

**Mutation-check a regression guard before trusting it.** The first
mutation run passed, which looked like the new guard was useless -- but the
real cause was that the kit which shipped the bug is untracked scratch and does
not exist inside the worktree, so the guard never saw it. Added a second pin
that drives the exact production shape through `_backfill_positions` directly;
reverting the trust inversion now fails 2 tests. A guard whose teeth you have
not verified is decoration.

**A marker key stamped onto data leaks.** The first draft tagged deterministic
rects with a `_deterministic_rect` key so the normalization pass could tell
them apart -- and it leaked into every kit and every dict-equality assertion in
the test file. Replaced with an identity set (`id()` of the position dicts),
which writes nothing into the data. Pinned by a test asserting a written
position carries exactly the five real keys.

## Doc freshness

`docs/schema_format.md` updated: `pdf_position` now documents the 1-based page
convention (and that page 0 silently draws nothing), who OWNS the value
(deterministic widget geometry overwrites model output), the no-widget
fallback, and that a field with no derivable position carries no key at all.
Dropped the stale "(for non-fillable PDFs)" qualifier, which described the
fallback as if it were the main case.

The doc-freshness checker also flagged ~20 tier-2 docs as STALE, all
voice/runtime/backend surfaces (auth, context-compression, voice-ai,
terminology, ...). **None track the extraction/authoring files this branch
touched** and all were stale before it; left alone deliberately.

Beads housekeeping: no orphans. Two stale in-progress beads (ah76, btbi) belong
to other sessions' work, not this branch -- not transitioned.

## Files touched

- `scripts/authoring/extract_form.py` -- the inversion: dump rect wins
  unconditionally at field + option level; `_normalize_model_page_base` for the
  no-widget fallback's page base; degenerate placeholders dropped;
  `_has_usable_position` docstring rescoped to "is a MODEL rect worth keeping".
- `scripts/bakeoff/schema_contract.py` -- FIELD SHAPE no longer asks for
  `pdf_position`; says why, and points at `pdf_field_name` as the key that
  matters instead.
- `scripts/schema_score.py` -- absent draft position is not-applicable, not a
  miss (the bake-off half of the contract change).
- `tests/test_extract_form_backfill.py` -- rewrote the two tests that encoded
  the OLD priority; added the dump-wins pins (field + option), the
  fallback-survival + page-shift pins, the real-kit page/geometry guard, the
  mutation pin, the five-keys pin, and the option unmatched-reporting delta.
- `tests/test_schema_score_derivation.py` -- not-asked-is-not-applicable pins.
- `docs/schema_format.md` -- position ownership + page-base documentation.
