---
date: 2026-09-14
bead: polyglot-pdf-xtj97
title: "fix(forms): whitespace deadlocks the voice path -- pin the exit invariant, not the instance"
tags: [testing, review, conventions]
---

## Trigger

bd polyglot-pdf-xtj97, filed as a P1 regression: bd 5ovod tightened
`confirm_field` to reject whitespace-only values, and `skip_field`'s
`alreadyFilled` guard was untrimmed, so for a REQUIRED field holding `"   "` all
three voice-path exits could refuse at once.

The severity came from what sits downstream. The backend marks BOTH the confirm
(`no_value`) and skip (`already_filled`) refusals NON-RETRYABLE
(`callback_handler.py:969-985`, `:1203-1214`), so the model is told to stop
trying -- while the field keeps coming back.

## What shipped

**Criteria 1 and 2 were already satisfied on `dev`.** The guard reads
`!isBlankFieldValue(existing)` (`webFormConnection.ts:2337`) and
`skipfield.test.ts:258` already drives a real `skip_field` message with
`"   "`. Both landed inside bd 5ovod's OWN PR (commit `8da0142f3`), so the bead
was filed against an intermediate state of that branch rather than against
`dev`. Checked rather than assumed -- the fix being present is the kind of thing
worth verifying before writing code for it.

**Criterion 3 was the real work, and it is the half that stops this recurring.**
Nothing asserted the general invariant; the existing coverage pinned the
whitespace INSTANCE. So this adds
`frontend/src/webFormConnection.exitmatrix.test.ts`: 11 stored value shapes
(null, undefined, `''`, whitespace, tab/newline, a real answer, `'0'`, `[]`,
`['White']`, `false`, `0`) x required/optional, swept against all three exits,
asserting the refusals are never unanimous.

**It drives the REAL handlers.** Confirm and skip fire actual
`confirm_field` / `skip_field` messages at a real `WebFormConnection` and read
the acks; clear calls the real `validateField`. The obvious version -- re-typing
the three predicates as local helpers -- passes forever while production drifts.

No production change. Reviews: fresh-eyes NO-GAPS (1 round), Opus cross-surface
NO-GAPS (1 round), each finding one prose defect I then fixed.

## Lessons

**The bug was in the INTERSECTION, so the test had to be a matrix.** Each of the
three guards was individually correct and defensible:

- confirm refuses whitespace (whitespace is not an answer)
- skip refuses a filled field (do not discard a real answer)
- clear refuses `''` on required (required fields need a value)

Nothing was wrong with any one of them. The deadlock existed only where all
three fired on the same value shape, and no single-guard test could see it. A
whitespace-specific test would not have caught it either, because whitespace
only became lethal once a DIFFERENT predicate moved. **When a bug lives in the
intersection of correct rules, pin the intersection.**

**A test one layer below the guard is blind to it -- and this bead is the proof
twice over.** bd 5ovod's own escapability test called `markFieldSkipped`
DIRECTLY, one layer beneath `handleSkipFieldRequest`'s guard, so it could not
see the guard at all and passed while the real path deadlocked. That is why this
test fires real socket messages rather than calling predicates.

**Mutation testing is what told me the invariant was aimed correctly, including
when it stayed GREEN.** Four mutations:

- restore the untrimmed guard (the real regression) -> 3 red, including
  `tab/newline`, a shape nobody had enumerated
- tighten confirm to reject `''` everywhere -> GREEN, *correctly*: clear still
  carries an optional `''` field
- tighten confirm AND clear -> GREEN, *correctly*: skip still carries it
- close all three -> 12 DEADLOCK failures

The two green results mattered as much as the red ones. A guard that fires
whenever anything moves is noise; this one fires exactly when a deadlock is
real. **Diagnose why a mutation survived before reacting to it** -- twice the
answer was "the system is genuinely still safe", not "the test is weak".

**Both reviewers found the same defect class in my work: prose that overstated
the code.** Fresh-eyes flagged that treating "no ack" as a refusal might mask a
crashing handler (I tested it: a throwing handler reddens loudly, so the
convention is right, and the comment now carries that evidence). The Opus pass
caught that "the voice session cannot move past it" was simply false --
`switch_to_field` pins another field and `resolveLivePin` returns that pin ahead
of both priority loops, so the model CAN work around it. What is actually true
is worse: the form can never be COMPLETED, because `isSectionValid` fails
forever and Priority 2 hands the field back. Stranded-forever, not
stuck-on-this-turn -- and it surfaces at the END of a long session.

An overstated comment is not a style nit. It teaches the next reader a mechanism
that does not exist, and here the accurate version was the more alarming one.

## Doc freshness

Not re-run for this branch: the diff is one new test file, and no tier-1/2 doc
carries a `**Tracks:**` glob covering `frontend/src/*.test.ts`. The Opus
reviewer independently confirmed no doc states the exit set or the guard
semantics this test encodes.

## Files touched

- `frontend/src/webFormConnection.exitmatrix.test.ts` (new) -- the exit-matrix
  invariant, driving the real handlers. No production file changed.

Filed in passing:
- `polyglot-pdf-ykfx0` -- Preview view mode renders no skip control, so a
  voice-only user there has no UI exit (`PreviewPane` never receives
  `onFieldSkip`). Out of scope: this bead's criteria are about the voice-path
  TOOL exits, and threading a new callback through `PreviewPane` is a
  user-facing change.
- `polyglot-pdf-km40m` -- the comment-accuracy nit above; fixed and closed in
  this same PR since it was about this very file.
- `polyglot-pdf-qpz11` -- not new: the reviewer added `capturePreFilledValues`
  (`connection.ts:321`, still writing whitespace as `confirmed: true`) as a
  sixth member of that bead's untrimmed-predicate set, and corrected its
  `surfaces` metadata.
