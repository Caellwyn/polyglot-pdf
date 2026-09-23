---
date: 2026-09-23
bead: polyglot-pdf-fyc7
title: "Two always-on editor checks, and a carve-out I got backwards"
tags: [schema-editor, testing, conventions]
---

## Trigger

Bug-hunt continuation. Both beads sit in one function --
`schema-editor/src/utils/validation.ts` `checkFieldComplete` -- and both are
the same shape of gap: a defect the BACKEND lint catches, that the client
misses, so the field renders green in the editor while being unfillable or
wrong-filling at publish time.

That asymmetry is the reason these matter more than their size suggests. The
field list's at-a-glance status is `checkFieldComplete` alone, with no backend
round-trip, so "green" offline is the only signal an author has while working.

## What shipped

**bd `polyglot-pdf-fyc7` -- two sibling options claiming one PDF widget.**
Nothing flagged it. At fill time, on a `checkbox_group`, ticking option A also
ticks B's box; on a `select`/`radio` the last-processed claimant wins and
overwrites the other's value. bd `p2bd` had shipped only its first criterion --
the dropdown that CREATES mappings refuses to offer a sibling-claimed widget --
which stops NEW duplicates through that one UI path and does nothing for a
schema that arrives with one already baked in (hand-edited JSON, a legacy
free-text-era export, an import from another tool, or anything authored before
that fix).

**bd `polyglot-pdf-ufj7` -- a stray field-level name hiding an unmapped group.**
The unmapped-option check was gated behind `!field.pdf_field_name` for every
choice type. Correct for select/radio; wrong for `checkbox_group`, where v2
forbids a field-level name outright -- so a stray one short-circuited the whole
branch and a group with EVERY option unmapped reported zero errors. Also now
flags the stray name as its own error: reporting only the unmapped options
would have the author fix symptoms while the shape the backend rejects stayed.

## Lessons

**A MUTATION PROVES A GUARD HAS AN EFFECT, NOT THAT THE EFFECT IS WANTED --
and I learned this the expensive way in this very PR.**

I shipped two carve-outs on the collision check, and reasoned carefully about
both. One exempted claimants carrying distinct `pdf_on_value` export codes, on
the grounds that this is how a genuine AcroForm radio group is authored. I
mutation-verified it (removing it reddens an acceptance test, so it is
load-bearing). The inner reviewer then reproduced that same mutation
independently, in an out-of-repo scratch copy, and agreed.

**All of that verification was rigorous, and all of it was checking the wrong
property.** The Opus cross-surface pass read the filler instead, and the
carve-out is simply false: the `/AS` write that consumes `pdf_on_value` runs
ONLY on the branch where an option has NO `pdf_field_name` of its own and
inherits the field-level one -- a shape that never enters this check at all,
because only option-level names are bucketed. Once options carry their own
names the filler resolves BY NAME and ignores `pdf_on_value` entirely, so both
claimants write to one widget and the last wins. My carve-out exempted
precisely the defect the check exists to catch. The backend had said so all
along: `dump-widget-multiclaim` is an ERROR for 2+ option-level claimants, with
no export-code exemption and no type filter.

The second carve-out (excluding `select` on fill-mechanics grounds) was wrong
in a different way -- correct about the fill, but it left the editor GREEN on a
shape the publish gate hard-REFUSES. Green here, refused there, is worse than a
flag that is strictly-true-but-moot.

So the lesson is narrower and sharper than "the carve-out is the work":

- A mutation answers *does this line change behaviour?* It cannot answer *is
  this the behaviour we want?* Only the consumer can answer that.
- A confidently-wrong guard WITH a passing test pinned to it is harder to
  dislodge than no guard, because every subsequent reviewer sees a test
  asserting the intended behaviour and moves on. Two reviewers did exactly
  that here.
- When writing a client-side mirror of a backend rule, the question is not
  "what is true about the mechanism?" but **"what does the authoritative side
  actually do?"** I reasoned from the fill mechanics and got a defensible
  story; the backend's lint rule was three lines long and said the opposite.
  Read the rule, do not re-derive it.

**THE SET HAD FOUR MEMBERS, AND I FOUND THEM ONE ROUND AT A TIME.** This is
the part worth carrying forward. The bead named one predicate. Three
successive outer-review rounds each found the next member of the same set:

1. `checkFieldComplete` -- the row status (the bead's target).
2. `hasUncoveredStructuralError` -- the COUNT mirror, in the same file family.
   Teaching only the row means rows paint red while the strip reports the form
   fully reviewed and "Next to review" skips them.
3. The same mirror's ORDERING. I fixed member 2 and wrote tests, but my
   collision case used a checkbox_group with no field-level name and my
   field-level-name case used a CLEAN radio. The COMBINATION was untested and
   all 117 editor tests passed with the bug present.
4. `publish_readiness.has_uncovered_structural_error` -- a THIRD mirror, in
   Python, one surface further out. Its docstring opens "The exact mirror of
   reviewStatus.ts ... and it MUST [match], or a field counts reviewed in the
   STAMP while the open editor renders it red." It fed the readiness block in
   `metadata.json`, which the kit CATALOGUE renders -- so one saved kit would
   show two different completion percentages.

Each time I believed I had fixed "the" predicate. The tell I kept missing is
in the code itself: every one of these files says in its own docstring that it
mirrors another. **A file that declares itself a mirror is a set member by
construction** -- grep for the claim, not for the symbol.

**AND THE NET THAT SHOULD HAVE CAUGHT IT WAS BLIND BY CONSTRUCTION.** There is
a shared parity fixture consumed by both the TS and Python halves, created
because "prose could not hold the mirror together... only a shared expectation
catches that class of drift." It passed green through three rounds of me
changing one side. Its non-triviality guard checks case COUNT and that both
outcomes appear -- neither can detect a missing DIMENSION. So a fixture whose
entire purpose was catching this drift had no case for any of the new classes.

The generalizable form: **a set-pinning test pins the members you thought of.**
Adding an error class to a mirrored predicate means adding a fixture case, and
no count-based non-triviality guard will remind you. Verified by mutating the
NET rather than the code -- reverting the Python reddens four of the six new
cases, each named.

**The related trap, still true: an error class added to one predicate and not
its mirror splits an invariant.** `checkFieldComplete` (row status) and
`hasUncoveredStructuralError` (the count) re-implement the same question
separately. Teaching only one about a new error class means rows paint red
while the strip reports the form fully reviewed and "Next to review" refuses
to stop on them -- the exact thing `ValidationPanel`'s comment promised could
never happen. That comment is now written as an invariant to MAINTAIN rather
than a property that holds by itself.

**Where reading the backend DID work.** The `ufj7` half went the other way and
is the control case: the v2 rule ("a checkbox_group's boxes are independent
widgets, so each option MUST carry its own pdf_field_name") is stated outright
in `form_models.py`, I read it rather than inferring it, and that half needed no
correction. The difference between the two halves was not care -- it was whether
I took the rule from the authoritative side or reconstructed it from mechanism.

## Doc freshness

No tracked docs affected: this diff touches only `schema-editor/src/utils/`,
and no `docs/` file documents `checkFieldComplete`'s rule set. The
schema-editor's own guide was updated in the previous PR of this session (bd
`kk74`) and describes the colour SEMANTICS, which are unchanged here -- these
checks add new reasons a field is red, not a new meaning for red.

No CLAUDE.md changes.

## Files touched

- `schema-editor/src/utils/validation.ts` -- sibling-widget-collision check
  mirroring the backend's `dump-widget-multiclaim` exactly (no export-code
  exemption, no type filter); checkbox_group ungating of the unmapped-option
  check; stray field-level name as its own error.
- `schema-editor/src/utils/validation.test.ts` -- 10 tests, including the ONE
  genuine false-positive guard (a field-level shared name with per-option
  export codes -- the real AcroForm radio shape -- must stay clean) and a
  malformed-options case, since this function is on the per-field RENDER path
  where a throw is a blank screen (bd `8bjdx`).
- `schema-editor/src/utils/reviewStatus.ts` -- the COUNT mirror: same ungating,
  plus both new error classes, reading through one normalized name list so a
  malformed kit degrades instead of blanking the strip. Docstring now
  enumerates the classes and says to keep them in step.
- `schema-editor/src/utils/reviewStatus.test.ts` -- 4 tests pinning
  strip/row agreement via `reviewCounts`, plus the no-throw case.
- `schema-editor/src/utils/optionsConsumerSet.test.ts` -- exemption re-pointed
  at the single guarded read.
- `schema-editor/src/components/ValidationPanel.tsx`,
  `schema-editor/src/components/FieldEditor.tsx` -- comments that asserted
  invariants now say what maintains them.
