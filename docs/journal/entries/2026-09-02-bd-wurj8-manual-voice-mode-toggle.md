---
date: 2026-09-02
bead: polyglot-pdf-wurj8
title: "feat(voice-ux): manual/voice mode toggle replaces Pause -- suppress elicitation at the adapter, not the speaker"
tags: [refactor, testing]
---

## Trigger

The Pause button did not do what its name promised, and the gap was not cosmetic.

Traced (`connection.ts`, `pause()`): it stopped the mic outright, so the user went
MUTE, not merely deaf. It called `flushAudioQueue()`, which discards Gemini's
in-flight audio CLIENT-side only -- the model had already finished asking its
question into a buffer nobody heard, and then sat waiting for an answer. Coming
back therefore could not just resume: `resume()` had to re-arm the mic AND fire a
debounced 1.5s `recovery_prompt` (bd `polyglot-pdf-yo5t`) to make Gemini re-ask
the question the pause had destroyed. A paid turn, to undo a button press.

So "pause" was deaf AND mute AND costly -- close to the opposite of what the
maintainer wanted it for, which was: let a user walk away, or let the
"mostly manual" profile work in silence with the assistant still present and
correctly oriented, ready the instant they want it.

## The decision

Replace it with a sticky **manual/voice mode toggle**. The voice UI is now
exactly two controls -- push-to-talk (non-sticky) and this one -- and that limit
is a design constraint, not an aesthetic: many users touch this app once, so
anything needing explanation must fit in about a sentence of the spoken intro,
and the third sentence is where people stop listening.

## What made this non-obvious: WHERE to put the gate

The tempting implementation is a client-side speaker mute. It is wrong, and it is
wrong in exactly the way the old `pause()` was wrong.

Every text turn this app sends to Gemini carries `turn_complete=True` -- it does
not merely inform the model, it ASKS it to respond. `send_text_message` (queued
hints: next-field guidance, manual-edit notices) and `send_client_content` (the
direct "speak now": disclaimer, initiating message, secretary answers, validator
steers) both land at `_send_text_turn`. So muting the speaker leaves the model
talking into a discarded buffer: billed, unheard, and then waiting on an answer
to a question the user never received.

The gate therefore lives at the adapter (`LiveAIGemini.set_voice_muted`), before
the turn reaches Gemini. That is what makes manual mode genuinely silent AND
free, instead of silent-looking and still billed.

**Context is held, not dropped.** Manual mode's promise is that the assistant is
oriented the moment it is wanted, so the newest suppressed turn is kept and
replayed onto the ordinary text queue on unmute. Only the newest: these messages
restate whole current state ("the next unfilled field is X"), so an older one is
not additional information, it is a stale contradiction -- and replaying a
backlog would bill for every one of them.

**A held `send_client_content` returns False.** Callers already treat False as
"this was never voiced" (a queued or failed send returns False too). This matters
most for the validator steer, which HOLDS a section on a delivered steer: a held
turn reporting success would strand the user waiting on speech that never came.

## Two-sided invariants

Both of these are correct in isolation on either side and broken if only one side
ships, which is why they are written down here as well as in the code:

1. **A PTT press leaves manual mode at BOTH ends** -- the client flips its own
   toggle in `sendActivityStart`, and the backend unmutes on `vad_activity_start`
   before forwarding it. Pressing to talk is an unambiguous request for the
   assistant; it must not require finding the toggle first.
2. **The mode is client-owned and re-asserted on every (re)connect.** The backend
   is stateless and each new Gemini session defaults to speaking, so
   `onSessionReady` / `onSessionRestarted` re-send it. Without that, a GoAway or
   auto-drop silently starts the assistant talking again with no user action --
   precisely the surprise the mode exists to prevent.

Deliberately NOT folded into `rehydrateAudio` (the shared reconnect routine):
that early-returns under the test harness and while paused, and the mode is a
protocol fact, not an audio-device fact.

## Scope held

The toggle removed the only UI caller of `pause()`, so nothing now sets status
`'paused'` and a whole branch is unreachable -- `pause`/`resume`/`isPaused`, the
post-resume re-prompt machinery, both overlays' Resume arms, and the `'paused'`
arm of Sol's state map. Enumerated and filed as bd `polyglot-pdf-oaidu` rather
than folded in: it crosses Sol's state machine and ~30 `connection.test.ts` cases
that drive `pause()`/`resume()` directly, and this bead's exit criteria do not ask
for it. A dead-but-inert branch is not a user-facing defect; a rushed removal
across those surfaces would be.

## Testing note

Eleven mutations, and one of them is the lesson worth keeping.

Verifying "manual mode must not gate the user's own turn signals", I mutated the
guard in `send_activity_start` with a `.replace(..., 1)` -- which hit the FIRST
matching `if self._current_session is None:` in the file, inside
`send_client_content`, not the one I meant. The suite went green, and green there
meant nothing: the mutation had landed somewhere harmless. Re-targeted by the
unique neighbouring log line, it reddened exactly the right test.

A mutation that applies is not automatically a mutation that applies WHERE YOU
MEANT (see bd memory `mutation-can-apply-and-still-be-inert`). Assert the mutated
text is where you intended, not merely that the file changed.

The overlay tests are parametrized over desktop and mobile and were mutation-
verified per parametrization: breaking the desktop toggle left the mobile cases
green and vice versa, which is what proves the two near-duplicate overlays are
each genuinely pinned.

One other trap: the "does not tear down the mic" assertion had to be a DELTA, not
an absolute. PTT holds the mic at a resting mute between presses, so `muteInput`
is already called once at mount; an absolute assertion there would have been
measuring PTT rather than this control.

## The same defect three times, and what finally ended it

Review found the held-context mechanism broken in three rounds. Each fix was
locally correct; each left one more ordering open. Worth recording because the
progression is the lesson, not any individual bug.

- **R1.** `set_voice_muted(False)` cleared the held turn unconditionally, so an
  unmute during the teardown window put it on an orphaned queue -- silently, since
  `put_nowait` raises nothing and nobody drains it. Fixed: clear only after a
  successful put.
- **R2.** `send_text_message` checked `_text_queue is None` BEFORE `_voice_muted`,
  so a NEWER hint arriving in that window was never recorded, and the replay then
  voiced the OLDER one as current. Worse than R1: the model names the wrong field
  confidently instead of staying silent. Fixed: mute check first, mirroring
  `send_client_content`.
- **R3.** If the UNMUTE ITSELF raced the teardown, the turn stayed held forever --
  the only flush site was the unmute branch, gated on `was_muted`, and a user who
  has already unmuted never touches the toggle again.

Every fix was "handle one more ordering", and every finding differed from the last
only in WHICH order two events arrived. That is the tell from scar #8: stop
patching instances, change the mechanism.

The mechanism fix is one `_flush_muted_context()` that asks whether both
preconditions hold RIGHT NOW -- not muted, and a live queue -- called from every
site where either can become true (the unmute path and queue creation). Whichever
arrives second delivers. A new ordering cannot open a fourth variant, because no
single site owns the decision any more.

**Pinning a test that mirrors production.** Driving the real queue-creation path
spawns the live session loop, so the tests use a small helper mirroring its two
relevant lines. A mirror can drift, and then every teardown test stays green while
the bug is back -- so an ast guard asserts the real `set_callbacks` calls the flush
INSIDE the branch that creates the queue, not merely somewhere in the function.
Mutation-verified: deleting the production call reddens that guard while all 16
behavioural tests stay green, which is precisely the blind spot it exists for.

A reviewer also caught one of my tests setting `_text_queue = None` to "simulate
teardown" against `send_client_content` -- which never reads `_text_queue`, so the
line asserted nothing. When simulating a state, check that the code under test
actually reads the thing you are setting.

## Verification

- Backend: 4418 passed, 0 failed on the full CI scope (`backend/tests tests`).
- Frontend: 1892 passed; the single failure is `SchemaForm.previewEdit`, the
  known pre-existing flake proven on `origin/dev` and tracked as bd
  `polyglot-pdf-7y2yk` (passes in isolation).
- Control copy translated across all 18 shipped languages. The existing
  derived-from-`SPOKEN_LANGUAGES` completeness test covers the new keys, and was
  itself mutation-verified: removing one language's string fails CI rather than
  silently falling back to English. Per the module header the non-English strings
  remain a machine-generated first draft pending native-speaker review.

Exit criterion 1 ("verified locally, not just in unit tests") needs the local
voice stack against a live Gemini session -- the toggle renders only while
connected, so it is a behavioural check, not a render check.
