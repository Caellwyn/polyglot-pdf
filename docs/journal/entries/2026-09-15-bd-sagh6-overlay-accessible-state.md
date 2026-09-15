---
date: 2026-09-15
bead: polyglot-pdf-sagh6
title: "fix(pdf-view): the overlay's fill state and value now reach assistive tech"
tags: [testing, review, conventions]
---

## Trigger

Filed by the Opus reviewer during bd polyglot-pdf-c9dfo's closeout. The PDF
overlay conveyed a field's fill state ONLY through an inline border/background
colour and a `data-fill-state` attribute -- neither of which any screen reader
reads.

I measured the before state rather than assuming it, and it was worse than the
bead described:

    editable overlay:  role=button, aria-label "Edit USCIS Number"  (no state)
    read-only overlay: role=null,   aria-label=null                (INVISIBLE)

The second case was not merely missing its state. The box was absent from the
accessibility tree entirely.

It matters most for `skipped`, which means a required question was deliberately
left unanswered and a human must follow up. The form view says so in words (a
badge plus a `role=status` note); the PDF view said it in purple. And since bd
polyglot-pdf-ykfx0 gave Preview its own skip button, a screen-reader user can
now both CREATE and fail to perceive that state without ever leaving the PDF
surface -- the popover note that confirms it vanishes when the popover closes.

## What shipped

The accessible name carries the field, its VALUE and its STATE, in both modes:
`"USCIS Number: A123456789 (confirmed)"`, `"USCIS Number (set aside to answer
later)"`, and plain `"USCIS Number"` when untouched.

- A non-clickable overlay takes `role="img"`. An aria-label on a roleless div is
  not reliably announced, and "img" is honest: a graphic whose colour stands for
  a state.
- `STATE_PHRASES` is a `Record<FillState, string>`, like the palette maps, so a
  sixth state cannot ship without deciding what it announces. `empty` is
  deliberately silent -- an unfilled field has nothing to report, and a phrase on
  every blank box would bury the states that do.
- The wording is "set aside to answer later", matching the Preview legend and
  deliberately NOT the form view's "needs follow-up" -- that phrase is how tests
  and screen readers locate the form-view note, and repeating it broke a passing
  test during c9dfo.
- Option marks stay presentational: they are extra hit targets for the SAME
  field editor and the box carries the role, so announcing each would be
  duplicate noise. (Folded in bd polyglot-pdf-jlwr6, which the reviewer filed for
  the bare contextless "X" they announced.)

Three existing tests asserted `role === null` as shorthand for "not clickable";
retargeted to `not.toBe('button')`, which is what their names and neighbouring
assertions actually claim. Naming a previously-unnamed element is an improvement,
not a regression.

Reviews: fresh-eyes to NO-GAPS over three rounds, Opus cross-surface over three.
Every round found something real, and every finding was in my own new work.

## Lessons

**Each fix to the accessibility tree created the next problem in it.** That is
the shape of this whole bead, and it is worth stating plainly:

1. Colour alone reached nothing -> put the state in the accessible name.
2. `role="img"` is an ARIA LEAF: its name REPLACES its subtree. So the moment the
   read-only overlay became nameable, the painted VALUE inside it became
   unreachable. Measured: `textContent "A123456789"` while announcing only
   `"USCIS Number: confirmed"`. I had traded one gap for a worse one --
   announcing a field's STATUS while hiding the user's ANSWER.
3. Fixed by putting the value in the name. But `role="button"` is NOT a leaf, so
   the child text stayed exposed and the value could now be announced TWICE.
4. Fixed with `aria-hidden` on a wrapper -- which broke the CSS. Then the select
   case (below).

The transferable bit: an accessibility fix changes what the *tree* contains, and
the tree has rules (leaf roles, name computation, pruning) that the DOM does not.
Each step I reasoned about the attribute I was adding and not about the tree it
landed in.

**The wrapper broke layout in a file I never opened.** `.pdf-field-overlay` is
`display:flex` with no `justify-content`, and `.pdf-field-overlay__check`'s
`margin: 0 auto` is what centres the X. My `<span aria-hidden>` became the flex
item, leaving the auto margin no free space -- the X would have parked at the LEFT
edge of every single-box checkbox. Invisible to a green suite, because nothing
asserts glyph position.

The fix was to add NO node: `aria-hidden` on the EXISTING painted spans, which
are already the flex items. I considered `display: contents` on the wrapper and
rejected it -- it relies on a coincidence between that property's layout
behaviour and its a11y-tree behaviour, which is the unverified-rationale trap I
had already hit twice in this same bead.

**A pixel constraint is not a speech constraint.** `paintedValueFor` paints a
select's `pdf_on_value` -- the PDF export code -- because a speakable label
("Armed Forces Americas (AA)") clips in a 36px i-90 state box. Its own comment
says labels "became speakable names for the voice model". I reused that text as
SPEECH text, so a screen reader announced `"Current State: AA (confirmed)"`.

Radio and checkbox_group already speak labels, so select was the single type
where paint-text and speech-text must differ -- and the one place reusing the
painter silently degraded the result. Found by review, not by construction, which
is why the reviewer then enumerated all 22 paint/speech branch combinations
mechanically rather than trusting that select was the only one. It was.

**The reviewer talked me out of a refactor, correctly.** I offered to move the
select dispatch into a `spokenValueFor` helper beside `paintedValueFor`. It
pointed out that co-location does not prevent drift -- it only makes drift
visible -- whereas the test asserting BOTH sides in one place makes drift *fail*.
And the helper would have had to re-call `selectedOptionRects` or take it as a
parameter, so the coupling would be identical, just further away.

## Doc freshness

`docs/components/pdf-view.md` tracks FieldOverlay.tsx and my change made two of
its claims incomplete -- not wrong, which is why the reviewer filed rather than
blocked, but incomplete *because of this diff*:

- the accessibility sentence described only `role=button` keyboard activation,
  with no accessible-name contract -- so a next session could have reintroduced
  either defect this bead fixed;
- the select paragraph says selects paint the export code "never their label",
  still true of PAINTING, while the name now deliberately uses the label. Left
  as-is that reads as an inconsistency someone would "fix" and re-break speech.

Both updated here, and `polyglot-pdf-12nco` closed as done rather than left
open against a file I was already editing.

## Files touched

- `frontend/src/pdf-view/FieldOverlay.tsx` -- `STATE_PHRASES`,
  `accessibleNameFor`, the spoken-value computation (including the select
  label split), `role="img"` on the non-clickable branch, and `aria-hidden` on
  the painted spans and option marks.
- `frontend/src/pdf-view/valuePainting.ts` -- `optionLabel` exported rather than
  re-typed.
- `frontend/src/pdf-view/FieldOverlay.a11y.test.tsx` (new).
- `frontend/src/pdf-view/PDFViewer.dimming.test.tsx`,
  `frontend/src/pdf-view/PreviewPane.popover.test.tsx` -- the two retargeted
  role assertions.
- `docs/components/pdf-view.md` -- the two claims above.

Filed and closed in passing: `polyglot-pdf-jlwr6` (option marks, folded in),
`polyglot-pdf-12nco` (the doc, fixed here).
