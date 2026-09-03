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

## The same defect five times, and what finally ended it

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

- **R4.** The mechanism fix was right and its PRECONDITION was wrong. `finalize()`
  cancels the text sender and only nulls the queue several awaits later, so there
  is a window where the queue still exists and a put succeeds onto a pipe whose
  reader is already dead. The turn was logged as sent, cleared, and then died with
  the queue.

Every fix was "handle one more ordering", and every finding differed from the last
only in WHICH order two events arrived. That is the tell from scar #8: stop
patching instances, change the mechanism.

The mechanism fix is one `_flush_muted_context()` that asks whether both
preconditions hold RIGHT NOW, called from every site where either can become
true. Whichever arrives second delivers, so no single site owns the decision.

- **R5.** The precondition was still a proxy. Teardown queues a `None` sentinel
  BEFORE cancelling the sender, and the loop exits on it -- so a turn queued
  behind the sentinel is unreadable while the task is not yet `done()`. Checking
  the consumer was better than checking the queue, and still not the fact itself.
  Fixed with an explicit `_text_pipeline_closing` flag set at the top of the
  drain, before any await and before the sentinel.

**R4 and R5 are the more interesting failures, because the mechanism was already
right.**
I had written into that function's docstring that "a new ordering cannot open a
fourth variant" -- and a fourth ordering promptly appeared, because the mechanism
was asking the wrong QUESTION. It tested for a queue object; what it needed was a
live consumer. Every test, every doc sentence and my own reasoning had modelled
teardown as one instant (`Queue` -> `None`), when it is a multi-await process with
an observable middle state where the queue lies about being usable.

Two lessons worth separating. Changing from event-keyed to condition-keyed was
genuinely the right move and it did close R1-R3. But a condition is only as good
as the thing it measures, and I reached for a proxy twice running: "there is a
queue" stood in for "something will read this" (R4), and then "the reader task is
alive" stood in for the same thing (R5). Both are true during teardown while the
fact they represent is false, because teardown is STAGED -- sentinel, then cancel,
then null -- and each stage falsifies a different proxy.

**When a fix's correctness rests on a precondition, ask whether that precondition
can be true while the thing it stands for is false.** If the answer is yes,
recording the fact directly (a flag set by the code that knows) beats inferring it
from a nearby observable, however natural the inference looks. And a confident
no-more-bugs claim in a comment is a smell: I wrote one, and the next review round
disproved it.

A useful detail from R5: the sentinel-state test failed on FIRST run, for a
second reason -- the test mirror had not been taught to clear the new flag, so
the flush it modelled was a no-op. That is the mirror-drift the ast guard exists
to prevent, catching itself in the act. The guard now pins both halves of the
restart (flush AND clear), so a future mirror cannot silently diverge on either.

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

## A state that changes without a click has to be published

The PTT auto-unmute is a deliberate feature: pressing to talk leaves manual mode
so the user need not hunt for the toggle. It also means the mode changes with no
click, and the overlay read it exactly once, at mount. So after a PTT press the
session went live while the button went on saying "Quiet Mode" -- telling the
user the opposite of the truth, which is worse than having no indicator, because
the control exists precisely to answer "will this thing speak?".

Fixed with `onVoiceModeChange` on the manager; both overlays subscribe and
re-read on mount. A constructor callback would not have worked: the manager is
built in `SchemaForm` and reaches the overlays as a prop.

**The mock was doing the production code's job.** My first version looked
verified -- removing the subscription from the overlays reddened the tests. But
removing the MANAGER's notification left them green, because the mock notified
its own listeners rather than routing through real code. A mock that reimplements
the behaviour under test converts a broken mechanism into a passing suite. The
fix was tests that drive the REAL manager (`connection.test.ts`), where both
halves redden independently.

**And writing those tests found a bug six review rounds had not.** The toggle
called `audioManager?.resetPlaybackClock()`. `?.` guards a missing MANAGER, not a
manager missing that METHOD -- against a partial audio manager it throws straight
out of a click handler and blanks the overlay. This is the same slip I had
already made and fixed earlier in this bead (`getAudioManager`), reintroduced a
few hundred lines away. Fixing an instance does not inoculate the next site;
feature-detect every hop into an optional collaborator, especially off an event
handler.

## "Provably safe" is not "covered"

Round 7 pointed at two `connection?.setVoiceMode(mode)` calls -- optional chaining
guarding the object but not the method, the shape of the bug found one round
earlier. I had ALREADY audited those two sites myself and cleared them, correctly:
`connection` is a concretely-typed `WebFormConnection` the manager constructs, so
a missing method is not reachable and `?.` is right there.

The reviewer agreed with that reasoning and then found what it had let me skip
past: those lines had NO TEST COVERAGE. Every test reaching them did so with
`connection === null`, so the optional chain short-circuited and the send was
never exercised. Nor was `WebFormConnection.setVoiceMode` itself -- a grep for
`voice_mode` across the whole frontend test suite returned nothing. The entire
client -> backend path for this feature was unverified.

That matters because manual mode is enforced at the BACKEND. A mode that never
reaches the socket is not manual mode: the UI reads "quiet" while the assistant
keeps talking and keeps billing, which is indistinguishable to the user from the
feature not existing.

**The mistake was answering a different question than the one that mattered.** I
asked "can this break in production?" and stopped at a sound "no". The question
that needed asking was "if someone breaks this later, does anything fail?" A type
that makes a bug unreachable today is not a regression test; it is an argument,
and arguments do not run in CI.

Closed with the mock carrying the method the real class has, four tests driving
the send path through the manager (including the reconnect re-assertion criterion
1 depends on for a user whose session drops mid-form), and a new file pinning the
wire frame itself. Four mutations, all caught -- including deleting the method
body and renaming the mode value, which the backend rejects rather than coerces.

## Presence is not translation

Separately from the replay saga, review caught one Tagalog label shipped as bare
English while the label on the line ABOVE it was translated -- my own
inconsistency, and a straight failure of "translated in every shipped language".

The interesting part is why the completeness test missed it. That test asserts
every language HAS every key with a non-empty value; a value left as English
satisfies it perfectly. Presence is not translation, and the two look identical to
a truthiness check.

The new guard flags any value byte-identical to the English one, written as an
ALLOWLIST rather than a blanket rule -- two entries legitimately match ("Pause" is
the ordinary French and German word), and a rule forbidding that would be wrong
for real loanwords. The allowlist entry is where you record WHY a match is
deliberate. It is mutation-verified in both directions: it names the exact
offender when a translation is missed, and it fails when an allowlist entry goes
stale because someone later translates that word -- a guard that can rot silently
buys little.

One process note worth keeping: the new test PASSED while `tsc` failed on it. Had
I stopped at green tests, that would have been a CI break shipped by a change
whose whole purpose was catching an omission.

## Verification

- Backend: 4430 passed, 0 failed on the full CI scope (`backend/tests tests`).

  A caveat worth recording, because it cost a re-run: an EARLIER full run of this
  same tree reported 2 failures, both in guards that read
  `backend/adapters/live_ai_gemini.py` FROM DISK to assert structural properties.
  They were reading a file my mutation probes had temporarily modified -- the
  suite and the probes were running concurrently. Both pass in isolation on the
  clean tree. A source-reading guard cannot run while anything edits the files it
  inspects, so mutation probes and a full suite must not overlap.
- Frontend: 1911 passed, all 134 files. (`SchemaForm.previewEdit` failed on an
  earlier run and passed on this one -- the known pre-existing flake proven on
  `origin/dev`, tracked as bd `polyglot-pdf-7y2yk`.)
- Control copy translated across all 18 shipped languages. The existing
  derived-from-`SPOKEN_LANGUAGES` completeness test covers the new keys, and was
  itself mutation-verified: removing one language's string fails CI rather than
  silently falling back to English. Per the module header the non-English strings
  remain a machine-generated first draft pending native-speaker review.

Exit criterion 1 ("verified locally, not just in unit tests") needs the local
voice stack against a live Gemini session -- the toggle renders only while
connected, so it is a behavioural check, not a render check.
