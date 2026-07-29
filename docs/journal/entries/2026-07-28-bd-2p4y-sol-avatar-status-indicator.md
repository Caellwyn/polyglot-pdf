---
title: "Sol: one wordless avatar replaces the status icon, the FAB pulse ring, and the status dot"
date: 2026-07-28
bead: polyglot-pdf-2p4y
tags: [frontend, overlay, ux, accessibility, i18n, voice]
---

# polyglot-pdf-2p4y -- Sol, the avatar status indicator

## Why

The overlays reported session state with three separate widgets, and each of
them reported a fact about our infrastructure rather than an answer to the
user's question:

- **desktop**: an emoji traffic light (`green circle` / `stopwatch` / `white
  circle`) plus the raw `status` string -- i.e. our socket's state, rendered as
  English.
- **mobile**: a ring pulsing on a fixed 2s loop around a mic-emoji puck, both
  tinted by a `statusColor` legend (green connected / amber paused / blue ready
  / grey otherwise). The pulse ran at the same rate whatever the session was
  doing, so it only ever communicated "this widget is alive"; the colour was a
  legend the user had to learn, and on the one surface where the panel is
  collapsed by default it was the *only* status available.

The user's actual question is narrower than any of that: **is it my turn?**

The maintainer had prototyped a replacement -- Sol, a sun/moon avatar, in
`pitch/ignored_pitch/sol-avatar.html` (gitignored) -- to serve as mascot and
status indicator at once, and asked for it on both overlays.

The i18n constraint is what makes the wordless approach necessary rather than
decorative: the app ships in 17+ spoken languages, and a status indicator built
from words or from a colour legend fails a user who reads neither.

## What shipped

Six states, none of which contain a letter:

| state | reads as | cue |
|---|---|---|
| idle | ready, nothing pending | rays turn very slowly |
| listening | your turn | rays **stop dead** and breathe in length with mic energy |
| thinking | working on it | rays turn (16s/rev) + sparkles |
| speaking | its turn | halo rings swell out of the disc and fade |
| paused | you chose this; all is well | crescent moon + drifting stars |
| offline | something is wrong | Sol leaves; a crossed-out cloud remains |

Two grammar choices carried over from the prototype are worth recording because
they are counter-intuitive:

- **Stillness is what attention looks like.** Listening *stops* the rotation. A
  thing that keeps moving while you talk reads as busy with something else.
- **The rays listen; the body speaks.** Two different organs for the two turns,
  so a user never has to work out which is happening.

And one that is a safety property rather than an aesthetic:

- **Speaking moves the halo, not the orb.** Disc scale and brightness stay
  capped (~6% / ~7%) and, unlike the rays and rings, deliberately do **not**
  take the small-size motion boost -- a bright orb throbbing 13% on a phone is
  a different kind of object than one throbbing 6%. The rings carry the
  amplitude instead; they cost no luminance. Amplitude is also smoothed on two
  clocks (~120ms drives geometry, ~230ms drives brightness only), because the
  eye integrates light over time and a luminance swing tracking every syllable
  reads as flicker even at small amplitude.

## Structure -- why three files, not a paste

`VoiceOverlay.tsx` and `VoiceOverlayMobile.tsx` are hand-duplicated of each
other (both carry the "if you change logic here, change it in the other" header
comment). Pasting ~200 lines of SVG + CSS into both would have guaranteed drift,
so:

- **`frontend/src/shared/Sol.tsx`** -- the single source of the SVG and the CSS
  (exported as a string, since both overlays style themselves via inline
  `<style>{...}</style>` blocks and neither imports a `.css` file). Per-instance
  gradient/mask ids, because the mobile overlay renders **two** Sols (the FAB
  and the panel row) and a shared `url(#id)` breaks when either unmounts.
- **`frontend/src/shared/solState.ts`** -- the pure `status -> SolState`
  mapping, so the precedence rule lives in one testable place instead of being
  re-derived in each overlay.
- **`frontend/src/shared/useGeminiSpeaking.ts`** -- the missing speaking signal
  (below).

## The precedence rule

`paused > offline > speaking > thinking > listening > idle`, with the three
activity states additionally gated on a **live session** (`connected` /
`connected <suffix>` only).

Each ordering earns its place:

- **paused outranks everything** -- claiming to listen or think while the user
  has paused is a lie about whether we are consuming their mic.
- **offline outranks everything** -- never dress a broken session as activity.
- **speaking beats thinking** -- the backend can leave `agent_processing` armed
  into the first audio frames; audible output is the ground truth.
- **the live-session gate** -- a stale `speaking`/`thinking` flag left over from
  a dropped socket must not animate an avatar whose session is gone.
- **listening requires `micSending`, not mere connectedness** -- this preserves
  the bd `polyglot-pdf-1dvp` correction, where the old indicator lit precisely
  when it was *not* listening.

## The speaking signal did not exist

Nothing in the UI knew whether the assistant was talking. `audioManager` tracks
`geminiIsSpeaking` internally and exposes `isSpeaking()`, but that is a plain
getter with no subscription, used only for barge-in logic.

What *did* exist: `window.vffOnAudioPlaybackStart` / `...End`, fired by
`audioManager` and -- verified by grep across `frontend/src` -- **declared in two
files and subscribed by none.** They were left for an activity watchdog that
never attached.

`useGeminiSpeaking` claims them, but:

- **chains** any pre-existing handler rather than overwriting it, and **restores
  it on unmount** -- the overlay remounts on a desktop<->mobile breakpoint
  cross, and a future watchdog must be able to attach without silently losing
  one of the two events;
- **polls `isSpeaking()` at 200ms while speaking** to cover the hole the events
  cannot: `flushAudioQueue()` on a barge-in stops playback *without* firing the
  end event (deliberately -- firing it there would spam the watchdog), so a
  purely event-driven flag would stick "speaking" on forever after every
  interruption. The poll is armed only while speaking, so idle costs nothing.

## Reduced motion needed real work, not just `animation: none`

The naive `prefers-reduced-motion` block collapsed **listening and thinking into
the same picture** -- both are "a sun with full-opacity rays", differing only by
rotation and twinkles, which is exactly what the media query kills. Verified in
a browser: identical computed style on every distinguishing property.

Each motion-dependent state therefore gets a static substitute: listening pins
the rays **fully extended** (visibly longer than idle's rest length), thinking
pins the **sparkles visible** (the state's own motif), speaking pins a **steady
halo ring**. All six now read apart with the clock stopped.

## What was deliberately KEPT

The ear + mic-energy chip stays, despite the prototype's "one object replaced
three" thesis. It reports the **mic send gate** specifically -- distinguishing
*mic alive but gated* from *audio reaching the backend* (bd
`polyglot-pdf-s3zv`), and showing a crossed-out ear during the
not-listening-yet transients (bd `polyglot-pdf-3to5`). Sol's listening state
fires only in the "reaching the backend" case, so folding the chip in would have
silently deleted a diagnostic that exists because silent mic loss made a live
demo hang invisibly on 2026-06-10. The mobile FAB's green mic-activity badge (bd
`polyglot-pdf-8v53`) stays on top of Sol for the same reason.

## Verification

Frontend **1099 passing** (up 18, all new), backend **1323 passed / 1 skipped**,
`tsc --noEmit` clean.

Beyond the suite, the real component was driven in a browser via a dev-only
harness (`frontend/sol-preview.html` + `src/dev/solPreview.tsx`; the deployed
`vite.config.schema.ts` declares a single explicit `input`, so it cannot ship):
all 24 instances rendered, 72 gradient ids unique with zero cross-instance
`url(#...)` references, and the amplitude response was swept at
`--e`/`--eb` = 0 / 0.5 / 1 to confirm the geometry moves and the brightness cap
holds.

Two bugs were found and fixed *by* that browser pass, neither of which any unit
test would have caught: the disc over-scaling (13% -> 5.5%) and the
reduced-motion state collapse.

A caveat worth stating plainly: the Browser pane would not composite frames in
this session, so **no human has visually eyeballed Sol yet** -- every claim above
is a computed-style or DOM assertion. Animation timelines were frozen at
`currentTime: 0`, which initially read as "the stars never appear"; driving each
animation's clock by hand confirmed the keyframes are correct (stars reach 0.90
opacity, twinkles 0.95). The preview page is the fastest way for a human to
confirm the look.

## Doc-freshness triage

`closeout_prep` flagged `docs/standards/voice-and-vad.md` and
`docs/standards/section-reset-deprecation.md` as stale because both list
`frontend/src/demo/VoiceOverlay.tsx` in a broad `Tracks:` line. **Reviewed
against this branch: both remain accurate and were not bumped.** voice-and-vad's
only relevant claim is that the mic-energy meter merely *reads* the send gate
without altering it -- still true, and true of Sol as well; section-reset's
reference is to the manual section-jump dropdown, untouched here. The remaining
STALE entries are pre-existing and belong to unrelated backend work.

## The speaking halo needed a second amplitude source

Writing this entry surfaced a defect the whole test suite had missed, because it
is a *semantic* error rather than a broken assertion: the speaking halo was
being fed `micEnergy`.

The mic is near-silent precisely when the assistant is talking. Every unit test
passed, the CSS moved correctly under a synthetic amplitude, and the state
machine was right -- but in production the most distinctive of Sol's six states
would have sat visually dead, which is exactly the failure mode the FAB's old
fixed-rate pulse was being replaced *for*.

The mic path gets its RMS free from the capture worklet; the playback path had
no equivalent, because chunks are scheduled straight onto `BufferSource`s. So
`audioManager` now splices an `AnalyserNode` between those sources and
`ctx.destination` (`source.connect(getOutputAnalyser(ctx))`, with the analyser
itself connected onward -- it is a pass-through, not a sink) and exposes
`getOutputEnergy(): number` on the same 0-100 scale as the mic energy.

Sol takes it as a **getter**, not a value: the level changes every frame, and
threading it through React state would re-render the whole SVG ~50x/sec. The
component picks its source by state -- output while speaking, mic while
listening -- so the two turns visualise two different voices.

Measured in a browser against the real `createAudioManager`, playing a
0.5s 440Hz PCM16 frame at amplitude 20000: **0 before playback, ~43.8 sustained
during, 0 again after the clip ends.** The analyser is lazily built per playback
context and dropped in `cleanup()`, since the context is closed and recreated
across reconnects.

## Follow-ups not taken

- `isWarming` / `isReady` are now dead in `VoiceOverlay.tsx` -- but they were
  already dead at `HEAD` before this change (verified via `git show`), so they
  were left alone rather than folded into an unrelated diff. Mobile's copies
  *were* removed, because Sol removed their last consumer (`statusColor`).
- The output analyser is a **pull** API rather than a subscription, because its
  only consumer is an avatar that already runs a per-frame loop. If a second
  consumer appears (a waveform, a captions timing cue), a callback registration
  matching `setEnergyCallback` would be the natural shape.
