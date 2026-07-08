---
date: 2026-07-07
bead: polyglot-pdf-f58l
title: "P1.4: E2E voice-harness verification + pdf-view component doc"
sprint: 8
tags: [testing, conventions]
---

## Trigger

Closing bead of the preview-mode epic (`polyglot-pdf-js7q`, sprint 8): the
end-to-end voice-harness verification of the live Preview surface (epic rubric
#3 + #4), the flag-off deployed-parity check (#6), and the tier-2 component
doc. Everything the epic built (P0.1-P1.3) already shipped; this bead proves it
works together against real Gemini and documents the module.

## What shipped

- **`docs/components/pdf-view.md`** (+ INDEX row): current-state tier-2 doc for
  the whole `frontend/src/pdf-view/` module -- the flag/cutover gate, dual view
  modes, the live surface (overlays + value painting + fill-state colors), the
  snap-to camera, the true-preview modal, and the accepted fidelity caveats
  (client-paint vs PyMuPDF, group labels at field rect, signature/textarea
  edges).
- **E2E voice-harness verification (PASS)** -- scripted audio through real
  Gemini, with `?previewUi=1` and Preview mode active the whole run:
  - Gemini transcribed the digits fixture and called `update_form_fields`;
    the field filled `1234567` and, after the "yes" fixture, confirmed.
  - **The value painted onto the actual PDF overlay**: overlay went
    `current` (empty) -> `current` ("1234567") on fill -> `confirmed`
    ("1234567", green) after confirm -- the fill -> confirm -> paint chain on
    the rendered I-90, digit-aligned in the A-Number comb boxes (screenshot in
    the PR).
  - Snap-to camera: proven at 0px-off centering in the P1.3 (35t0)
    verification; on this run the camera cleared the orange marker on confirm
    (the intended 35t0 behavior) and Gemini advanced to the next field.
- **Flag-off parity check (PASS)**: at `?previewUi=0` the app renders no
  toggle, no preview button, no preview pane, and fetches ZERO pdfjs / lazy
  preview chunks (`actualPdfjsLoaded: []`, `lazyPreviewChunksLoaded: []`) --
  behaviorally the pre-epic UI.

## Lessons

- **The AI Studio key is credit-depleted (1011); Vertex is the working local
  Gemini path.** `VERTEXAI=true GOOGLE_CLOUD_PROJECT=polyglot-demo-aa709` with
  the existing user ADC (`google.auth.default` refreshes clean) connects and
  transcribes + tool-calls fine (model `gemini-live-2.5-flash-native-audio`).
  Updates the voice-harness setup note: try Vertex first when 1011 hits.
- **Two harness gotchas compounded, both environment-not-product:**
  1. A backgrounded (hidden) automation tab clamps `setTimeout` to ~1 Hz, so
     the harness's real-time-paced audio injection crawled (~1 chunk/sec) and
     the session idle-timed-out before a full utterance landed. Fix: stream the
     PCM with microtask yields (no wall-clock `sleep`) so pacing is
     throttle-immune; drive the whole cycle from a fire-and-forget `window.__vff`
     and poll it across short calls (a single blocking call exceeds the 45s CDP
     limit).
  2. In NATIVE VAD the blasted audio fragmented -- Gemini heard 6-13 char
     scraps and never tool-called. Running the backend with
     `DISABLE_GEMINI_VAD=true` (MANUAL VAD) so the harness brackets each
     utterance with explicit `activity_start`/`activity_end` gave Gemini a
     clean turn boundary -> reliable transcribe + `update_form_fields`. Manual
     VAD is the robust harness mode for scripted injection.

## Doc freshness

New `docs/components/pdf-view.md` created; INDEX row added. `schema-forms.md`
already carries the flag/toggle/pane paragraph (bumped in the vxwj/ogrt
closeouts) and needs no change. The recurring pre-existing STALE set (backend
worktree mtimes) left as-is.

## Files touched

- `docs/components/pdf-view.md` (new), `docs/INDEX.md` (component row)
- this journal entry
- (ride-along) `docs/journal/telemetry/2026-07-07T00-45-33Z-*.json` from PR #342
