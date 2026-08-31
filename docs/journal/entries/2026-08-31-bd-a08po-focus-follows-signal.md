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

## Why a click is ignored while the model is speaking

The first proposal was to let the in-flight question keep its own referent while
a click moved focus elsewhere. The maintainer rejected it: under DTI the model
holds ONE field's schema at a time and the backend coercion pointer
(`_current_field_id`) is singular, so a second referent has no representation --
ambiguous focus is a mis-fill, not a UX wrinkle.

Their replacement rule is what shipped, and it is better because it keys on a
signal that is genuinely unambiguous: **typing is intent, clicking is not.**
Nobody types into a field by accident, but fidget-clicking during playback is
common. So typing moves the origin unconditionally; a click waits until the model
is silent. The fidget case resolves to nothing happening, which is correct for
noise.

`isModelSpeaking()` is the predicate, not `isSpeaking()` -- per bd
polyglot-pdf-uxc6s the latter reads false during a model+clip overlap, which
would let exactly the mis-fill through. The new call site is registered in
`speakingSignalCallSites.test.ts`, the enumeration that forces every author to
declare which of the three speaking questions their site asks.

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

The origin field is visited LAST: the user just acted on it, so the next thing to
offer is what follows it, and it is only returned if nothing else qualifies.

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

## A real defect the tests found

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

## Deferred, deliberately

Typing does NOT interrupt the model's audio (bd polyglot-pdf-6fau6, P3). Under
this design the typed value already lands correctly and, under PTT, nothing typed
can be captured as a spoken answer -- so the interrupt buys only "a voice does
not talk over me," an annoyance fix, not a correctness one. The energy-based
barge-in path is where the implementation risk in this area concentrates, and it
is being retired anyway (bd polyglot-pdf-v1m8g). Ship the focus work; revisit
with evidence.

## Verification

Full frontend suite green: 1789 passed / 0 failed across 410 suites (backend:
3124 passed). 14 new tests, all mutation-verified -- reverting the rotation
reddens 4, removing the speaking-suppression reddens 2.
