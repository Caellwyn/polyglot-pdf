---
date: 2026-08-31
bead: polyglot-pdf-a08po
title: "feat(voice-ux): focus follows the user's most recent explicit signal"
tags: [voice-ux, schema-forms, navigation, dti, client-state]
---

## Trigger

The maintainer described errors when "jumping around and filling fields manually
and expecting the voice agent to keep up," and asked for a hierarchy: a verbal
request switches focus; clicking a field switches focus; otherwise the next
unverified field.

The trace found levels 1 and 3 already working and **level 2 entirely absent** --
there was no `onFocus` handler anywhere in the frontend. Every field component
had `onBlur`; none had `onFocus`. Clicking into a field was invisible to the
system.

## What was actually broken

Two failures, both hitting the user who types rather than speaks:

1. **Questions answered about the wrong field.** With no focus signal, asking
   "what does this mean?" with the cursor in field 12 got an answer about
   whatever the fill order left current.

2. **Focus snapped back to the top.** `computeNextField` always scanned from
   index 0, so after every manual edit the model re-targeted the FIRST
   unconfirmed field while the user worked far below it. For a mostly-manual
   session the model's sense of "where we are" was wrong throughout.

## The design decision that shaped everything

The maintainer's hierarchy was written as a static ranking, but levels 1 and 2
are both explicit user acts -- so a click after a voice jump could never win.
They confirmed the intent was **most-recent-explicit-signal wins**, which is what
shipped: all signals write the same state and the last one takes effect.

The larger move was **decoupling focus from elicitation**. Setting focus (which
field is the referent) and making the model SPEAK are separate concerns. Once
separated, a click can move focus silently, and the timers and typing-interrupt
rules we had been considering became unnecessary -- there is nothing to
interrupt. Silence is recoverable ("what goes here?" is one utterance); unwanted
speech is not.

## Why a click is ignored while audio is playing

The first proposal was to let the in-flight question keep its own referent while
a click moved focus elsewhere. The maintainer rejected it: under DTI the model
holds ONE field's schema at a time and the backend coercion pointer
(`_current_field_id`) is singular, so a second referent has no representation --
ambiguous focus is a mis-fill, not a UX wrinkle.

Their replacement rule is what shipped, and it is better because it keys on a
signal that is genuinely unambiguous: **typing is intent, clicking is not.**
Nobody types into a field by accident, but fidget-clicking during playback is
common. So typing moves the origin unconditionally; a click waits until playback
is over. The fidget case resolves to nothing happening, which is correct for
noise.

The predicate ended up being `isAnyAudioPlaying()` -- the clip-inclusive union.
It started as `isModelSpeaking()`, which the outer review showed was wrong; that
story is below. The call site is registered in `speakingSignalCallSites.test.ts`,
the enumeration that forces every author to declare which of the three speaking
questions their site asks.

## Rotation, not a second pin

`searchOriginFieldId` is a search ORIGIN. It moves where the scan starts; it
never forces a field to be next, and a live `switch_to_field` pin still outranks
it. The scan rotates -- runs to the end, then wraps -- rather than scanning
forward and stopping.

Rotating is what makes the wrap a complete sweep. Fields a user filled out of
order and skipped past are visited after the tail, so they are still reached.
That has a design consequence worth recording: **there is no separate end-of-form
"go back for missed fields" phase to build**, and completion is unchanged -- an
empty search still means every shown field is confirmed, exactly `isFormComplete`'s
existing condition. The maintainer had mixed feelings about redirecting users
backward mid-run; the rotation resolves it by making the sweep part of the normal
search order instead of a phase.

Where the origin sits in the rotation depends on the GESTURE that set it, which
the first cut got wrong and the review caught: a manual EDIT answers the field,
so the scan resumes AFTER it; a CLICK points AT it, so it is offered next.
Treating both as "resume after" sent the model to the clicked field's neighbour.

## Two tests that passed for the wrong reason

Mutation-verifying the rotation (revert it, watch the tests redden) caught a real
gap in my own tests. The first wrap test put the origin at the LAST field, with
earlier fields open. Under a rotation-removed mutant that arrangement **still
returns the same field** -- rotation and raw schema order agree there, so the
test proved nothing about wrapping and stayed green on the mutant.

I first "fixed" it by moving the origin mid-form, and it STILL survived: with
everything after the origin confirmed, both orders again reach the earliest open
field. The wrap is only observable when an open field sits on **each side** of
the origin -- rotation serves the later one first, raw order the earlier one.
Rebuilt that way, the mutation went from reddening 2 tests to reddening 4.

The lesson is the one this repo keeps paying for: a mutation only proves
something if the assertion's arrangement can actually distinguish the two
behaviors. "It went red somewhere" is not the bar.

## Two real defects the review found

### Gaps the inner reviewer caught

Round 1 found the click/edit conflation above (a rubric fail on criterion 1), and
a second one: `switch_to_field` pins a field, but confirming it released the pin
onto whatever the origin pointed at BEFORE the jump -- the same "focus snaps
backward" failure arriving via the verbal path. `confirmField` and
`markFieldSkipped` now advance the origin to the field just handled, as a pair:
they are the two pin-releasing paths, and an origin left stale by only one would
strand the scan exactly where the other fixed it.

### A defect the tests found

The first cut of the suppression guard read
`connectionManagerRef.current?.getAudioManager()?.isModelSpeaking()`. Optional
chaining guards a null receiver, not a MISSING METHOD -- and this runs on a raw
DOM focus event, which can fire before the manager is built, after teardown, or
against a partial manager. It threw a `TypeError` straight into the field's event
handler. Every hop is now feature-detected; absent audio means nothing is
speaking, so the origin moves.

## Enumeration

`onFocus` was plumbed through every field component as a SET (all six types, both
checkbox renderings, both select inputs), not the ones that happened to come up.
One `replace_all` silently matched only one of SelectField's two sites because
their indentation differed -- caught by grepping the count afterward, which is
the check that makes the enumeration real rather than intended.

## The outer review earned its keep: a bug in a file the diff never touched

The inner reviewer cleared the diff twice. The outer cross-surface pass then
found the real one, and it was invisible from inside the diff.

The click suppression originally gated on `isModelSpeaking()`. That reads
`activeAudioSources.length > 0` -- model PCM ONLY -- and audioManager's own
docstring calls it "structurally incapable of counting a clip." The
deterministic spell-back player (bd 22h1f) deliberately WAITS for that count to
reach zero before playing its clip. So for the entire spell-back window the
guard read "nothing is speaking" while the user was hearing
"K-O-W-A-L-C-Z-Y-K, is that correct?" -- with the form fully clickable, because
only the mic is held.

That window is the one that must not be open. `name_spellback` carries NO
field_id on the wire (config.py: the client resolves the current field itself,
so the spelled value can only ever be a STORED value, never the model's memory
-- bd h7wx, jnjj.46). It resolves via `computeNextField` -- the very function
this bead made steerable by a click. A click during the clip would have made the
client spell a DIFFERENT field's value back, and the user, hearing a plausible
read-back, would confirm it.

Fixed by gating on `isAnyAudioPlaying()`, the clip-inclusive union. A clip is
playback; the bead's own rule is that clicks during playback do nothing.

Two things this cost beyond the one-line fix:

- **The enumeration did not cover the third signal.** `speakingSignalCallSites`
  exists precisely to stop a caller asking the wrong "is Gemini talking?"
  question, but its `CALL` regex matched only `isSpeaking|isModelSpeaking` --
  so moving to `isAnyAudioPlaying` would have moved my site OUT of the guard
  entirely. Widening it immediately surfaced an unclassified site that had been
  invisible all along: the avatar's PREFERRED path in useGeminiSpeaking.ts (only
  its legacy fallback was classified). `siteKey` now normalizes the union to its
  own token rather than collapsing all three, so swapping between the union and
  a turn-taking accessor cannot keep matching the same entry.

- **A comment that had become false.** webFormConnection's spellback docstring
  said the field is resolved by "the same pin-aware computation" -- true when
  the only mover was the pin, and now wrong: a USER gesture moves it too, a
  channel neither cited bead anticipated. Someone reading that comment would
  believe the resolution was safe by construction.

The lesson is the one the review layer is built for: the diff was clean in
isolation, and the defect lived in the gap between a new caller's ASSUMPTION
about `isModelSpeaking()` and that function's actual semantics, in a file the
diff never opened.

## Deferred, deliberately

Typing does NOT interrupt the model's audio (bd polyglot-pdf-6fau6, P3). Under
this design the typed value already lands correctly and, under PTT, nothing typed
can be captured as a spoken answer -- so the interrupt buys only "a voice does
not talk over me," an annoyance fix, not a correctness one. The energy-based
barge-in path is where the implementation risk in this area concentrates, and it
is being retired anyway (bd polyglot-pdf-v1m8g). Ship the focus work; revisit
with evidence.

## Verification

Full frontend suite green: 1799 passed / 0 failed (backend: 3124 passed, not
touched by this change). 23 new tests, all mutation-verified:
  - reverting the rotation reddens 4;
  - ignoring `searchOriginIncludesSelf` reddens 2;
  - removing the playback suppression reddens 2;
  - reverting the guard to `isModelSpeaking()` -- the outer-review bug -- reddens
    3 (the spell-back case plus both halves of the enumeration).

One flake surfaced along the way and was proved PRE-EXISTING before being set
aside: `SchemaForm.previewEdit.test.tsx` fails intermittently under full-suite
load. Verified by stashing this branch's whole source diff, checking out
origin/dev's frontend/src, and reproducing it there with none of this code
present. Filed as bd polyglot-pdf-7y2yk rather than worked around here.
