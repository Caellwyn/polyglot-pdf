---
date: 2026-07-30
bead: polyglot-pdf-w70y
title: "Field-ID overlay: the reviewer-facing half of field<->widget assignment"
tags: [schema-editor, frontend, form-kits, review-tooling]
---

## Trigger

Bd `polyglot-pdf-a1xt` shipped two CLI tools for the off-by-N field<->widget
assignment class -- a field claiming a widget that is real and claimed exactly
once, but belonging to a different printed row than the field means. One of them,
`overlay_field_guesses.py`, proved the idea works by finding a previously unknown
shift in W-7's signature block.

But it is a batch tool: run it, get a PDF, open the PDF. The maintainer's read was
that the *editor* is where reviewers already work, and the editor already draws a
coloured box over every widget. So the useful move is not a new tool but a toggle
on the existing overlay layer -- swap the boxes for the field IDs.

Explicitly NOT a gate. The maintainer's constraint: flagging some fields implies
the unflagged ones are correct, and reviewers are the last line of defence against
exactly the errors an automated check cannot see. This shows every field equally
and leaves the judgement to the person.

## What shipped

A "Show field IDs" checkbox left of the zoom controls. Off: today's coloured
status boxes. On: each field's own ID drawn over the widget it claims.

- **Session-only state** (`useState` beside `scale`). A transient inspection mode,
  not a preference, so a reload returning to boxes is intended.
- **Field IDs, not spoken names.** IDs are short, stable, and are what the field
  list and properties panel show; spoken names are voice-facing prose.
- **Hover, click and the selection glow are unchanged.** The `spoken_name` tooltip
  is still the full-name recovery path.

## One colour source (the load-bearing structural change)

Status colour (green reviewed / amber needs-review / red error) is now computed
once into `STATUS_COLORS` and read by BOTH modes -- the box border in box mode,
the label text in ID mode. Previously it was an `if/else if/else` assigning
`borderColor` directly.

This matters because a second colour table is how the two modes drift into
disagreeing, and a reviewer who sees a green box labelled in amber stops trusting
either signal. The anti-drift case is a test: render the same field in both modes
and assert both land in the same band.

The existing box-mode RGB values are byte-identical, so all 21 pre-existing
`FieldOverlay` tests pass untouched -- which is the evidence the restructure was
behaviour-preserving.

## Two overflow rules that behave differently

Sizing follows the widget: `font = screenPos.height * 0.72`. `screenPos` is
already multiplied by `scale`, so the label tracks zoom with no scale term --
pinned by a test, because reintroducing one is the obvious way to break it.

**Vertical (too small to read) -> suppress the label, keep the FULL box.** Keyed
on SIZE, not field type. A 36pt `select` on i-90 is exactly as unreadable as a
checkbox, and a type-based rule (the maintainer's first instinct) was measured to
miss 29 of 49 illegible fields there while the size rule catches all of them.
A suppressed field keeps its full-width box rather than the 1px hairline a
labelled field gets -- that box is then the only thing marking it.

**Horizontal (too long) -> truncate with an ellipsis.** Never spill into a
neighbour.

**Zoom recovers the first and NOT the second.** This is the correction worth
recording. Suppressed labels genuinely reappear on zoom -- verified live, i-90's
8pt checkboxes go from no label at 100% to legible at 200%. But truncation is
zoom-INVARIANT: box width and font size both scale linearly, so the overflow
ratio is constant and a label cut at 100% is cut identically at 300%.

| form | labelled | truncated | worst observed |
|---|---|---|---|
| f1040 | 114 | 18 (16%) | `fld_spouse_deceased_date`, ~3 of 24 chars |
| i-90 | 132 | 85 (64%) | `p1_checkbox4`, ~2 of 12 chars |
| w7 | 46 | 5 (11%) | `itin_part2`, ~5 of 10 chars |

I had told the maintainer zoom was the escape hatch for BOTH before measuring
it -- the same "asserted a property nobody executed" failure the `a1xt` review
rounds kept finding. Measured in a browser, corrected, and pinned by a test that
asserts the ratio is scale-independent. The maintainer accepted the tradeoff
(hover recovers the full name); the toggle's tooltip now says so plainly.

## Verified in a browser, not only in jsdom

jsdom has no layout engine, so it cannot observe clipping -- the unit tests can
only pin the CSS contract. The editor loads kits through a native folder picker
that automation cannot drive, so the check ran against a temporary harness
mounting `FieldOverlay` over widget geometry lifted from i-90 and f1040 (wide
text boxes, a narrow one, 8-10pt checkboxes), then deleted.

What that caught which jsdom could not: real truncation (`scrollWidth >
clientWidth`), real suppression, the white text halo, the hairline-vs-full border
distinction, and the zoom-invariance above.

## Decisions (defended)

- **Size threshold rather than a checkbox-type exclusion.** The maintainer
  proposed excluding checkboxes; measured, that misses 29 of 49 illegible fields
  on i-90 (they are small `select`/`text`, not checkboxes) and would keep them
  unlabelled even zoomed in where they would fit. The size rule catches all 128
  illegible fields across the three kits and is zoom-aware.
- **Reversed the earlier "never drop a label" decision.** That decision produced
  4px labels; suppression replaced it once the numbers were on the table.
- **Kept a 1px hairline in ID mode instead of removing the border.** It preserves
  the widget's extent, which is what tells a reviewer whether a truncated label
  belongs to the narrow box or the wide one beside it.
- **Did not thread `lintFindingsByField` into the viewer.** A pre-existing gap (a
  lint-ERROR field reds in the list but not on the PDF) and a separate concern.

## Verification

- 22 new tests (15 overlay, 7 viewer integration).
- Full schema-editor suite: 963 passed across 68 files.
- `tsc --noEmit` clean -- `paintOrder` and `WebkitTextStrokeWidth` are typed in
  the installed `csstype`, so no cast is needed.
- Live browser check against real widget geometry (above).
- The non-ASCII glyphs the scar-#6 check flags in these two files
  (checkmarks, arrows) are pre-existing on `dev` and on no line this change adds.
