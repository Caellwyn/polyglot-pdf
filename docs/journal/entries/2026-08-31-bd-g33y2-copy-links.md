---
date: 2026-08-31
bead: polyglot-pdf-g33y2
title: "feat(schema-editor): author auto-populate links from either end -- and a guard whose own hardcoded type list disagreed with the runtime"
tags: [schema-editor, testing, review]
---

## Trigger

The I-90 has four fields that fill themselves in from an earlier answer
(`a_number` -> `p8_a_number`, plus the three name fields). The mechanism,
`copy_to`, already worked end to end -- the voice runtime fans a value out and
the PDF prints it, measured -- but the editor could not author, show, or repair
a single link. The maintainer asked for it while completing the i-90 v2 kit.

## What shipped

The relationship is stored ONCE, as `copy_to` on the SOURCE, and shown from BOTH
ends: standing on A "copies to B", standing on B "copied from A". The
target-side view is DERIVED by scanning `fields[]`, so the two directions cannot
disagree and no migration was needed. Editing from either side writes the same
array with inverted arguments.

Adding a link sets `read_only` on the target in the same commit (maintainer
requirement: a field populated from another AND freely editable invites an
author to type a value the next source edit overwrites). The preview now fans
values out too, matching the voice app.

Deliberately NOT `copy_from`, which matches the requested UI direction
literally: no model declares it, no lint checks it, and the runtime IGNORES it,
so authoring one produces a link that populates nothing (bd
polyglot-pdf-nkhca).

## Lessons

**The requirement I asked about was narrower than the one I got.** I offered
three storage options; the maintainer answered with a behaviour instead: "I want
to see both... and I want to be able to change that relationship from either
place. How you implement that is up to you." The question I should have asked
was about the UI, not the schema. Storage then followed from the runtime: only
`copy_to` is read, so only `copy_to` is stored.

**I nearly shipped an unmet exit criterion by reasoning around it.** I argued
criterion 2 (the preview shows a target filling in) was superseded by the
maintainer's later decision. Fresh-eyes' answer was the bead's own TITLE --
"author auto-populate links AND SHOW THEM IN THE PREVIEW" -- and that the
decision was about the authoring UI's direction, not the preview. The argument
was plausible and wrong, and I was the one motivated to believe it.

**A guard with its own hardcoded type list disagreed with the runtime's
predicate, and my mutation testing could not see it.** `CHOICE_TYPES =
{select, radio, checkbox_group}` looked complete. The runtime's
`isStringEnumField` also counts a `type: "checkbox"` CARRYING options[] -- 27
such fields in the adult-intake demo, 59 in the i-589 draft. So the guard
UNDER-refused the exact defect it existed to stop (text -> options-bearing
checkbox: value enum-rejected, prints blank) and OVER-refused that same field as
a source.

My tests covered `select` and `radio` targets but never a `checkbox` target, so
deleting the whole guard reddened 3 and I read that as coverage. **A mutation
only proves the cases you wrote.** The sharpest detail: my own checkbox fan-out
test, added one commit earlier, builds both fields as `type: 'checkbox'` with
options -- the missing shape was already sitting in my diff, untested by the
guard beside it.

The fix was not to widen the list. It was to stop keeping a second definition:
`isOptionBacked` reads the DATA (does it carry options?), so a new field type is
correct for free. Replaced the spot-checks with a table-driven matrix over the
whole `FieldType` union x with/without options -- 576 cells. Reverting to the
hardcoded list reddens 23; the reviewer then ran two OVER-firing mutants I had
not thought to try (49 and 23 red), proving the matrix is a two-sided guard
rather than a restatement of the implementation.

**A near-duplicate that must NOT be collapsed needs the reason in the code.**
`rawOptionCount` looks like a fourth copy of `safeOptions`, which the same file
tree already has. Reusing it would be wrong: `safeOptions` DROPS unreadable
entries while the runtime counts them raw, so for an options array of nulls the
two disagree -- reintroducing precisely the divergence this work closed. Without
that sentence in the code, the next reader's tidy-up silently reopens the bug.

**I lost work to an over-broad restore.** While proving an unrelated
`App.grouping` failure was a pre-existing parallel-run flake (it was -- those
tests pass in isolation with and without this diff), I ran
`git checkout HEAD -- schema-editor/src`, which discarded uncommitted edits
along with the temporary ones. Commit before investigating, or scope the restore
to the files actually touched.

## Follow-ups filed

- `polyglot-pdf-gpaed` (opus): the VOICE path never fans out `copy_to` -- the
  fan-out lives only in the manual-edit handler. Compound with the read-only
  coupling: `read_only` makes a field permanently AI-unwritable while
  `isSectionValid` does NOT exclude read_only, so a REQUIRED copy target would
  dead-end a session. The four gold i-90 targets are non-required with no
  `show_if`, which is why this has never bitten.
- `polyglot-pdf-vvgyr`: there is NO `copy_to` lint rule anywhere -- a dangling,
  self-referential or cyclic link arriving by hand-edit or older extraction
  passes every gate. Also owns the type-change-after-linking bypass and the
  non-severity-gated un-review.
- `polyglot-pdf-nkhca`: settle `copy_from` -- a key nothing declares, lints, or
  honours.
- `polyglot-pdf-mjzrh`, `polyglot-pdf-87jlr`, `polyglot-pdf-3u3g3`,
  `polyglot-pdf-xpukz`, `polyglot-pdf-b9ggp`: smaller items.

## Files touched

- `schema-editor/src/utils/copyLinks.ts` (new) -- storage, derivation, refusals
- `schema-editor/src/components/FieldEditor.tsx` -- both-ends UI, memoized pickers
- `schema-editor/src/components/PreviewPane.tsx` -- fan-out on both value handlers
- three test files: the utility, the UI wiring, and the preview
