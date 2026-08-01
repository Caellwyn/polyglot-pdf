---
date: 2026-07-31
bead: polyglot-pdf-u4r0
title: "Re-derive positions after family completion so appended options are placed"
tags: [extractor, testing]
---

## Trigger

The maintainer asked the sharpest possible triage question after the bd icyi
closeout filed six follow-ups: **"If I extract new forms with the current
pipeline, will each one have to be fixed, or are these retroactive fixes for
forms created prior to the current pipeline? If every new form has to be fixed,
then we are not done with the pipeline."**

That question splits the backlog cleanly, so it got measured rather than
guessed:

- **bd ks1y (i-90 choice-field rects) is RETROACTIVE.** Measured on the fresh
  w7_v3 extraction built by the current pipeline: all 6 consolidated-choice
  fields have a field rect matching their `options[0]` widget EXACTLY -- 0
  mismatches. A new extraction is self-consistent by construction, so
  re-extracting i-90 as a parallel v2 resolves that bead's substance outright
  rather than needing a separate patch.
- **bd u4r0 (this one) is a LIVE PIPELINE DEFECT.** Every future extraction
  whose 3c2 step completes a widget family is affected; re-extracting does NOT
  escape it. So the pipeline was one bug short of "extract a form, it is
  correct" -- which is what this entry closes.

## What shipped

`_backfill_positions` (step 3, line ~1344) runs BEFORE
`_complete_grouped_families` (3c2, ~1365). Completion appends missing
widget-family members as options carrying only
`{value, label, pdf_field_name}` -- no rect -- and nothing downstream fills
them. Confirmed by reading every step between 3c2 and the end of `extract()`:
none touches option positions.

**Why it is a bug, not cosmetic:** `valuePainting.selectedOptionRects` iterates
the SELECTED values and returns `[]` mid-loop the moment one lacks a rect, so
selecting a completed option loses the per-option marks for every other
selection on that field too -- it falls back to a label at the field rect. (An
earlier draft of this entry, the code comment and the test message all said
"ONE positionless option disables painting for the WHOLE field", full stop.
That overstates it: the painter loops `selectedValues`, not `field.options`, so
an UNSELECTED positionless option is harmless. Corrected in all three places --
fresh-eyes caught the same wrong severity model propagated to three readers.)
It also violated the invariant bd polyglot-pdf-icyi had just established:
*where a widget resolves, the deterministic dump rect OWNS pdf_position*.

**The fix is a late re-derive (3d2) after 3c2/3d, not a reordering.** Moving
step 3 down was the other candidate and was rejected on evidence:

- RECT DERIVATION is IDEMPOTENT -- verified byte-identical on a second run over
  the real i-90 kit (132 fields / 75 options, same counts, same bytes);
- since icyi it derives UNCONDITIONALLY, so there is no trusted model rect left
  for a second pass to clobber -- the property that makes a re-run safe now and
  would NOT have been true before that bead;
- of the steps in between, 3a (`/TU`) and 3c2 write no positions at all, and 3d
  DOES write one per minted field -- but a deterministic already-converted rect
  from the same dump with the same `+1`, so re-deriving reproduces it exactly.
  Measured: the late pass changes ZERO pre-existing position values on w7 or
  f1040, and that is now pinned by
  `test_the_late_pass_reproduces_3d_minted_positions_exactly` rather than only
  asserted in prose. (An earlier draft of this bullet -- and the matching code
  comment -- claimed the intervening steps touch "never positions", which is
  simply false for 3d and self-contradicted two lines later. Fresh-eyes round 2
  caught it in both places; the load-bearing part of the safety argument had a
  false premise a reader would hit on the first step they checked.)

**But "the pass is idempotent" was too broad, and the review caught it.** Rect
derivation is; the PAGE-BASE SHIFT inside the same function is not. It one-shot
corrects the MODEL's ordinal base, so a second run moves positions the first run
already shifted -- model pages `[-1, 0]` become `[0, 1]` and then `[1, 2]`, and
that `2` is off a one-page document. That is precisely the off-the-document
failure the deterministic-exempt set was built to prevent, reintroduced from the
other direction by my own fix. The late pass now takes `normalize_pages=False`,
pinned by a regression test. Worth stating plainly: I justified the whole design
with an idempotence claim that was true of the part I was thinking about and
false of the part I was not.

Also corrected the 3c2 comment, which claimed it *"Runs BEFORE the backfill"* --
that reads as step 3, which actually runs ABOVE it. The ordering that matters is
3c2 before 3d (so a completed member is not also minted as a loose duplicate
field), and the comment now says so.

## Lessons

**A test that performs the fix itself proves nothing about the pipeline.** The
first draft called `_backfill_positions` and `_complete_grouped_families`
directly, in order, and asserted the appended options ended up positioned. It
passed. Then the mutation check -- disabling the REAL 3d2 step in `extract()` --
left it **green**, because the test was doing the late re-derive with its own
hands rather than checking that the pipeline does it. The bead's exit criterion
had actually asked for "a test that drives a partially-grouped family through
the pipeline stage order", and the direct-call version quietly did not.

Replaced with a test that drives the real `extract()`, stubbing only
`arm_llm_native.run` and generating a 1-page PDF carrying a minable checkbox
family. Mutation-verified: disabling 3d2 now fails it with the right diagnosis
(*"option p2_checkbox3_1 shipped with NO pdf_position"*).

This is the THIRD time in two beads that a guard of mine passed while verifying
nothing (icyi: a coupling test satisfied by a substring inside a comment; a
real-kit guard comparing 0 of i-90's 132 fields; now this). The pattern is
consistent enough to name: **when the thing under test is a pipeline's
ORCHESTRATION -- the order in which it calls things -- a test that calls those
things itself has replaced the subject with a re-implementation.** Drive the
real entry point, and mutate the production step to confirm the test can fail.

**A commit message is not a change. I made this exact mistake twice in one
bead.** Both times I described a journal correction in a commit message and did
not write it into the entry -- first the i-90 select-option measurement, then
the "never positions" claim above. Both were caught only because I re-read the
file afterward to check. The commit message is the most convincing possible
place to record a fix that does not exist, because it reads like evidence. When
a message says "also corrected X in the journal", grep for X before committing.

**An idempotence claim needs to name WHICH part is idempotent.** The whole
design rested on "the pass is idempotent, so re-running it is safe". That was
true of rect derivation and false of the page-base shift living in the same
function -- and re-running it double-shifted model pages off the document. A
function is not idempotent; its individual effects are. Enumerate them.

**Fixture vacuity needs its own assertion.** Two earlier fixture attempts
returned `{fields_completed: 0, options_added: 0}` -- family mining requires
BUTTON widgets (`logical_type` checkbox/radio) sharing a leaf base on one page
with distinct `[n]` indexes, which a bare rect dump does not satisfy. Both would
have "passed" while exercising nothing. The shipped test asserts
`len(opts) == 3` with an explicit *"this test would be vacuous"* message before
it asserts anything about positions.

## Real-kit safety, stated precisely

`w7`, `i-90` and `f1040` all return `{fields_completed: 0, options_added: 0}`
from 3c2, so the late pass is a strict no-op on every committed kit today --
consistent with this defect only biting a FRESH extraction whose 3c2 step
actually completes a family.

One correction to how I first phrased that safety check. I wrote "0 positionless
options"; the review measured **219 of i-90's 294 options carry no
`pdf_position`** -- and re-measuring confirms it exactly: all 219 belong to
`type: select` fields (the state / height dropdowns).
`_backfill_positions` skips those deliberately and correctly, because a
combobox's choice-values have no printed box to place. Zero checkbox/radio
family options are positionless. So the safety conclusion holds, but the
sentence I used to support it was false, and repeating it would have taught the
next reader that any positionless option is a defect.

## Doc freshness

No tier-1/tier-2 doc tracks `extract_form.py`'s stage order (the freshness
checker flags only voice/runtime surfaces, all stale before this branch and
untouched by it). `docs/schema_format.md` already documents pdf_position
ownership from bd icyi and needs no change: this bead closes a gap in WHEN the
documented rule is applied, not what the rule is.

## Files touched

- `scripts/authoring/extract_form.py` -- the 3d2 late re-derive with the
  rejected-alternative rationale; corrected the stale 3c2 ordering comment.
- `tests/test_extract_form_backfill.py` -- the `_family_pdf` fixture, the
  pipeline-level `test_extract_gives_family_completed_options_a_position` with
  an anti-vacuity assertion, and
  `test_the_late_pass_does_NOT_re_shift_model_pages`. (A `_family_dump` helper
  also shipped in the first draft and was never called by anything -- dead
  scaffolding carrying an authoritative-sounding docstring, duplicating the
  live `_write_family_dump` in `tests/test_extract_form_group_completion.py`.
  Removed.)
