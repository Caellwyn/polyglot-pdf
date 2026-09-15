---
date: 2026-09-14
bead: polyglot-pdf-ykfx0
title: "fix(forms): give Preview mode the skip control it never had"
tags: [testing, review, conventions]
---

## Trigger

Filed during bd polyglot-pdf-xtj97's closeout, from a gap noticed in passing:
the voice path's three tool exits are now provably never all-closed, but that
invariant is about what the MODEL can do. It says nothing about the USER.

In Preview (the PDF surface) the answer was "nothing". `SchemaForm` rendered
`PreviewPane` with `onFieldChange` / `onFieldBlur` / `onFieldFocus` and no
`onFieldSkip`, and `PreviewPane` had no such prop to receive. So a user working
on the PDF whose only other exit was voice had no interface escape from a
required field they could not answer.

That contradicts the stated product rule, which this repo's own tier-2 doc
spells out: leaving a required field blank on a legal intake draft "has to be
explicit -- said aloud, or via the skip control"
(`docs/components/schema-forms.md`). In Preview the control did not exist. The
only escape was to discover that switching views offers one.

## What shipped

**The prop, threaded through the whole chain** -- `SchemaForm` -> `PreviewPane`
-> `PDFViewer` -> `FieldEditPopover` -- ending in the same "Skip for now"
button, resolved by the same `handleFieldSkip` -> `markFieldSkipped` path the
form view uses. The popover closes after skipping, so a resolved field is not
left under an editor whose button has just vanished.

**The gate mirrors the form view's**, using the SAME shared predicates rather
than re-typed copies: a handler exists, the field is required, still empty, not
already skipped. Two surfaces disagreeing about when skipping is offered would
be its own bug. `empty` goes through `isBlankFieldValue`, so a space-filled
required field stays skippable -- the shape bd polyglot-pdf-xtj97 pinned on the
voice side.

**17 tests across two files, and they had to be two.** `PreviewPane.skip.test.tsx`
pins the popover's gating by rendering `PreviewPane` directly;
`SchemaForm.previewEdit.test.tsx` drives the REAL chain and asserts the skip
lands in `SchemaFormState`. The second exists because the first is structurally
blind to `SchemaForm` dropping the prop -- which is exactly where the bug lived.

Mutation matrix, nine mutations, each restored: dropping the prop at any of the
four links reddens (2, 7, 7, 7 tests); dropping any of the three gate conditions
reddens (2, 1, 3); replacing `isBlankFieldValue` with an untrimmed `=== ''`
reddens 7.

Reviews: fresh-eyes NO-GAPS, Opus cross-surface NO-GAPS over two rounds. Four
findings filed, two fixed here (both in code this PR added).

## Lessons

**A mutation that SURVIVES is a finding about your understanding, not a gap to
patch.** M8 -- passing `[field]` instead of the whole field list -- did not
redden anything. I had written a comment explaining that the whole list was
needed to resolve a `require_if` referencing another field, and a test I
believed pinned it.

Reading the evaluator instead of patching the test showed the comment was
simply false: `evaluateAtomicCondition` accepts a `fields` parameter and never
reads it -- the trigger value is looked up in `fieldValues` -- and nothing in
`validation.ts` indexes `fields` at all. The argument is inert today.

I kept passing it (it mirrors `SectionRenderer`'s call, and hard-coding
`[field]` would bake in an evaluator internal that is not part of its contract)
but the docstring now says plainly that it is inert, records how that was
verified, and warns against adding a test for it -- such a test could only pass
by coincidence. The two conditional tests were retargeted to pin what they CAN
see: that the gate evaluates `require_if` at all, which is real and
mutation-verified.

**The same false-rationale class bit twice more in this one PR.** The Opus pass
caught that my skipped-note used an invented CSS class with no rule anywhere and
dropped the `role="status"` its form-view twin carries -- so the note rendered
unstyled and announced nothing, in the one place where pressing the button makes
it vanish on the same render. Round 2 then caught my comment claiming
`schema-form.css` is "imported globally" when it has exactly one import site.
Both conclusions were defensible; both stated reasons were wrong.

The pattern across all three: I wrote an explanation that sounded right and did
not check it. The cheap discriminator is the one this repo already records --
after writing "X because Y", ask whether Y has been verified, and if Y is a
claim about code that exists, go grep for it.

**A test whose assertion cannot see the property it names will ship the bug.**
`getByText(/needs follow-up/i)` matched regardless of role or class, which is
precisely why the unstyled, silent note passed review-by-test. The fix was to
assert the ROLE and the shared classes; mutation-verified by restoring the
invented markup, which reddens that test alone.

**`git checkout <file>` discards uncommitted work, and I relearned it three
times in one session.** Mid-mutation-run it reverted the prop wiring in two of
four files; the surviving two made the chain look half-built and sent me
debugging a "missing button" that was really a lost edit. Commit before
mutating. The tell is a test failing for a reason that contradicts something you
just verified.

**A red suite is not evidence until you have the baseline.** The full suite
failed 4, then 5, then 7 tests across three runs of IDENTICAL code, and two of
those failures were in my own file -- which is exactly the shape that makes you
start rewriting good tests. The failures turned out to be TIMEOUTS, never
assertions.

The measurement that settled it: a pristine `origin/dev` worktree, with none of
my changes, fails the SAME tests under full-suite load (4 failed | 2254 passed),
while those same files pass 18/18 there in isolation. So every failure on my
branch is pre-existing, filed as `polyglot-pdf-acn4d` with that baseline
recorded. My three new tests did inherit the slowness -- they mount the real
lazy-loaded chain -- so they got explicit headroom; the pre-existing `7esr`
tests in the same file were left alone as out of scope.

Cost: this was chased twice in one session. The cheap discriminator is the one
the repo already records -- run the failing file ALONE, and if it passes, get a
baseline on a clean checkout of the base branch before touching anything.

## Doc freshness

Not re-run for this branch. The Opus reviewer traced the two tier-2 docs that
`Tracks:` these files and found two genuine issues, both PRE-EXISTING on
`origin/dev` and both filed rather than fixed here: `pdf-view.md` twice calls a
fixed bug an open gap (`polyglot-pdf-9utmk`), and `schema-forms.md`'s
`isBlankFieldValue` consumer list has not been told about this diff's new member
(`polyglot-pdf-txyq4`).

## Files touched

- `frontend/src/pdf-view/FieldEditPopover.tsx` -- the `onFieldSkip` +
  `allFields` props, the `canSkip` gate, the button, and the skipped note
  reusing `SectionRenderer`'s styled markup.
- `frontend/src/pdf-view/PDFViewer.tsx`, `frontend/src/pdf-view/PreviewPane.tsx`
  -- prop forwarding.
- `frontend/src/schema-forms/components/SchemaForm.tsx` -- passes
  `handleFieldSkip` to `PreviewPane` (the missing line).
- `frontend/src/pdf-view/PreviewPane.skip.test.tsx` (new),
  `frontend/src/schema-forms/components/SchemaForm.previewEdit.test.tsx`.

Filed in passing:
- `polyglot-pdf-c9dfo` -- pre-existing: a skipped field paints as `'empty'` on
  the PDF overlay, visually identical to one never touched, which contradicts
  the "renders visibly distinct, NOT a silent blank" contract. This PR makes
  Preview the surface where users will now CREATE that state.
- `polyglot-pdf-6w75j` -- pre-existing: `applyResume.test.ts` reads the
  untracked W-7 kit at module scope, so its 13 tests throw at collection in any
  fresh worktree and in CI. The suite reports a green-looking pass count
  alongside a file-level FAIL.
- `polyglot-pdf-9utmk`, `polyglot-pdf-txyq4` -- the two doc items above.
- `polyglot-pdf-0y9qb` -- the unstyled/silent note; fixed and closed in this PR.
