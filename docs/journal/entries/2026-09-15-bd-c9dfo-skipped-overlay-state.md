---
date: 2026-09-15
bead: polyglot-pdf-c9dfo
title: "fix(pdf-view): a skipped field no longer paints as an untouched blank"
tags: [testing, review, conventions]
---

## Trigger

`fillStateFor` had four fill states and no `skipped`. `markFieldSkipped` stores
`{value: null, skipped: true, confirmed: true}`, and the `isEmpty` check fired
on that null *before* anything read the flag -- so on the PDF surface a
deliberately-skipped required field was pixel-identical to one the user never
touched.

That contradicted the contract `schemaFormState.ts` states for
`markFieldSkipped`: a skipped field "renders visibly distinct as skipped --
needs follow-up ... NOT a silent blank". True in the form view, which paints a
Skipped badge. False on the overlay.

Filed by the Opus reviewer during bd polyglot-pdf-ykfx0's closeout, which is
also what raised its reachability: giving Preview its own skip control means a
user can now CREATE this state without leaving the PDF surface, and the popover
note that confirms it vanishes when the popover closes. The overlay is the only
lasting evidence.

## What shipped

**One branch and its ordering.** `skipped` is checked before the empty
short-circuit and below `current` -- the field the assistant is asking about now
outranks the fact it was skipped earlier, and `switch_to_field` can re-pin a
skipped field.

**Purple, 2px dotted, with a tint.** Deliberately NOT the form view's amber
badge colour: amber is already `current` on this surface, and a skipped field
must not read as the one being asked about. Dashed was taken too (a dimmed
`show_if`-hidden field), so skipped carries both an unused hue and an unused
stroke. The legend banner names it, or the colour is unexplained.

**No CSS rule**, contrary to the bead's fix sketch. `pdf-view.css` documents
that fill-state border/background ride INLINE because inline beats a class
rule, so a `.pdf-field-overlay--skipped` rule would be dead code.
`Record<FillState, string>` on both palette maps meant tsc forced both to gain
the key.

**A dimmed skipped field keeps its colour** (fresh-eyes round 1). Dimming
otherwise replaces border AND background wholesale, so a `show_if`-hidden
skipped field painted grey-dashed + transparent -- the defect again, one
condition deeper. Reachable because `dimmed` tracks `show_if` alone: skip a
field and a later answer hides it, or hide it and then skip it.

Reviews: fresh-eyes GAPS-FOUND(2) then GAPS-FOUND(1) then clear; Opus
cross-surface GAPS-FOUND(1). Every finding was real, and every one was in this
PR's own work.

## Lessons

**My first fix for the dimmed case was too broad, and writing the test is what
caught it.** Adding `skipped` to the `isDimmed` exemption also made the field
CLICKABLE and dropped its 0.35 opacity -- breaking bd polyglot-pdf-lp5v's rule
that a `show_if`-hidden field is "dimmed, never removed, and never clickable".
`isDimmed` gates five things; only the paint needed changing. The narrow version
(`keepsColourWhileDimmed`) is pinned from both sides, so neither removing it nor
widening it back survives.

The transferable bit: when a fix reaches for an existing exemption, check
everything that exemption gates. I assumed it governed paint because paint was
what I was looking at.

**Two of five styling mutations SURVIVED my first test pass, for the same
reason.** I asserted `not.toEqual` on the whole `{border, background}` object,
so styling skipped with `empty`'s exact border still passed (the background
differed), and styling it exactly like `current` passed too. A viewer reads ONE
cue at a glance, so each cue has to carry the distinction alone. Fixed by
asserting per-cue.

**A non-vacuity floor that cannot fail is not a floor.** My legend guard sliced
between two literals and asserted `length > 40`. `slice(start, -1)` does NOT
yield an empty string -- it widens to (end of file - 1). So if only the END
anchor drifted, the "banner" became nearly the whole file and the floor passed;
the phrase check then held only because that phrase happens not to recur later.
Fresh-eyes mutation-verified exactly that. Now asserts the anchors were found
and bounds the region on both sides.

**A test whose name contradicts its assertion is worse than no test.** One of
mine was called "still paints a skipped field that HOLDS a value by its value"
and its comment argued the value should win -- while asserting the flag wins. A
reader would have trusted the prose and "fixed" the code to a rule it never
implemented. I verified the reachability claim by PROBE rather than repeating
the reviewer's: `markFieldSkipped` then `updateField` yields
`{value: "Maria", confirmed: false}` -- the flag IS dropped, so the combination
cannot arise in the app.

**`git checkout <file>` ate unstaged work four times in this one bead.** Twice
it silently reverted a production fix I had just written, leaving tests that
were correctly failing while I looked for a logic error. Committing before each
mutation run helps; restoring from a copy OUTSIDE the repo is what actually
fixed it, and is what I used for the last mutation.

## Doc freshness

`docs/components/pdf-view.md` tracked all three changed files and carried a
CLOSED four-item list of overlay colours -- byte-identical on `origin/dev`,
where it was correct. **My diff falsified it**, which by the repo's rule makes
it a blocker rather than a bead, so it is fixed here: the colour list gains the
fifth state, and the `fillStateFor` precedence line now describes the ordering
and the dimming exemption. Stamp bumped.

Not fixed here, already open and untouched by this diff: bd
polyglot-pdf-9utmk (the same file's stale `1utg` known-gap paragraph).

## Files touched

- `frontend/src/pdf-view/PDFViewer.tsx` -- the `skipped` branch in
  `fillStateFor`, before the empty test and below `current`.
- `frontend/src/pdf-view/FieldOverlay.tsx` -- the `FillState` member, both
  palette entries, and `keepsColourWhileDimmed`.
- `frontend/src/pdf-view/PreviewPane.tsx` -- the legend names the colour.
- `frontend/src/pdf-view/fillState.test.ts`,
  `frontend/src/pdf-view/PDFViewer.skippedOverlay.test.tsx` (new).
- `docs/components/pdf-view.md` -- the falsified claims above.

Filed in passing:
- `polyglot-pdf-sagh6` -- pre-existing: the overlay conveys fill state by
  colour alone, with no accessible text. Not this diff's regression, but this
  diff extends colour-only conveyance to a state the form surface *does* give
  real text (a badge plus a `role=status` note), and a screen-reader user can
  now create it without leaving the PDF view.

One thing deliberately left alone: the legend banner is hard-coded English,
like every other chrome string in this repo. There is no i18n layer for UI
strings, so translating this one would be inventing a contract.
