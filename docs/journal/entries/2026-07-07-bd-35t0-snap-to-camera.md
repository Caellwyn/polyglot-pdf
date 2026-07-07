---
date: 2026-07-07
bead: polyglot-pdf-35t0
title: "P1.3: snap-to camera + snap-back button"
sprint: 8
tags: [conventions]
---

## Trigger

Fourth bead of the preview-mode epic (`polyglot-pdf-js7q`, sprint 8), on top
of the P1.2 live surface (PR #341). Maintainer-specified camera model from the
epic planning session: when the voice model starts a new field the camera
SNAPS to it (no animated motion -- avoids motion discomfort); users wander
freely; a button snaps back.

## What shipped

- **`useSnapToField`** (`frontend/src/pdf-view/useSnapToField.ts`): snaps on
  every current-field CHANGE (keyed on the `currentFieldId` SchemaForm tracks
  from `next_field_hint`) via `scrollIntoView(block:'center',
  behavior:'auto')` -- instant, centered in whichever ancestor actually
  scrolls. Brief retry loop while pages lay out; `CSS.escape` for bracketed
  mirror ids.
- **Free-wander rule (decided)**: user scrolling is never fought -- snaps fire
  only on a field change or the button press. No scroll-suppression state; the
  bead left the exact rule open and this is the simplest predictable one,
  matching the maintainer's original description verbatim.
- **Snap-back button** on the Preview toolbar (disabled until a session hint
  names a current field), with the pane now height-constrained
  (`max-height`) so the toolbar stays visible while scrolling and the pane is
  the snapping viewport.

## Lessons

- **Verify the actual scroller, not the intended one.** The first cut did
  manual `scrollTop` math on the pane div -- which had `overflow:auto` but no
  height constraint, so the WINDOW was the real scroller and every snap
  silently no-oped (`scrollTop` read back 0). Caught only because the live
  check asserted post-snap positions instead of trusting the code path ran.
  `scrollIntoView` is scroller-agnostic and strictly less code.
- A live session's opening `next_field_hint` fires the current-field path
  without any voice interaction -- handy for verifying hint-keyed UI on the
  local stack.

## Doc freshness

No tier-1/2 doc tracks `frontend/src/pdf-view/` yet -- the epic's P1.4 bead
(`polyglot-pdf-f58l`) creates `docs/components/pdf-view.md` covering the whole
module including this hook. The recurring pre-existing STALE set left as-is.

## Files touched

- `frontend/src/pdf-view/useSnapToField.ts` (new),
  `frontend/src/pdf-view/PreviewPane.tsx` (toolbar + hook wiring),
  `frontend/src/pdf-view/pdf-view.css` (toolbar, snap button, pane viewport)
- this journal entry
