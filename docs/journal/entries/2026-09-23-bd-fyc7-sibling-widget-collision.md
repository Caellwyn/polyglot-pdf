---
date: 2026-09-23
bead: polyglot-pdf-fyc7
title: "Two always-on editor checks, and the carve-out that is the actual work"
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

**On a detector, the carve-out IS the work -- the detection is the easy half.**
Both fixes took more thought in deciding what NOT to flag than in flagging.

- A shared `pdf_field_name` is not automatically wrong: a genuine AcroForm radio
  group is exactly one widget name whose options differ by export code
  (`pdf_on_value`), which is the `/AS` appearance-state write the backend's
  radio arm performs. So the check flags a shared widget only where the
  claimants fail to disambiguate.
- A field-level `pdf_field_name` is not automatically wrong either: it is the
  legitimate shared-name shape for radio, and invalid only on `checkbox_group`.

Get either boundary wrong and the rule reddens every real radio group in every
shipped kit. A detector whose false positives outnumber its catches is worse
than no detector, because authors learn to ignore the colour -- which is the
very signal the fix exists to restore. This is the "position-based rules must
be SCOPED, not global" trap wearing different clothes.

**So the mutation that proves a detector is the one that removes its
CARVE-OUT, not the one that removes its detection.** Disabling a check and
watching the positive tests redden only proves the code runs. The load-bearing
question is whether the false-positive guard is real, and the only way to know
is to delete it and watch an ACCEPTANCE test fail. Both carve-outs here were
verified that way, and both were genuinely load-bearing. A detector shipped
with only positive tests is one refactor away from flagging everything, with a
green suite the whole time.

**Read the backend before writing a client-side mirror.** Both rules encode
invariants that live in `backend/models/form_models.py` and the fill routes.
Guessing at "a shared name is probably wrong" would have produced a rule that
contradicts how radios are actually filled. The v2 rule
("a checkbox_group's boxes are independent widgets, so each option MUST carry
its own pdf_field_name") is stated outright in the backend, with a comment
explaining why the shared-name path is radio-only -- five minutes of reading
that replaced an assumption with a fact.

## Doc freshness

No tracked docs affected: this diff touches only `schema-editor/src/utils/`,
and no `docs/` file documents `checkFieldComplete`'s rule set. The
schema-editor's own guide was updated in the previous PR of this session (bd
`kk74`) and describes the colour SEMANTICS, which are unchanged here -- these
checks add new reasons a field is red, not a new meaning for red.

No CLAUDE.md changes.

## Files touched

- `schema-editor/src/utils/validation.ts` -- sibling-widget-collision check
  (with the `pdf_on_value` carve-out); checkbox_group ungating of the
  unmapped-option check; stray field-level name as its own error.
- `schema-editor/src/utils/validation.test.ts` -- 9 tests: 4 driving the
  defects, 3 as false-positive guards (a real radio group must stay clean), 1
  for distinct widgets, 1 feeding a malformed options array (this function is
  on the per-field RENDER path, where a throw is a blank screen -- bd `8bjdx`).
