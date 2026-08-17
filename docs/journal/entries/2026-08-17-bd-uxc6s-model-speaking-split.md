---
tags: [voice, barge-in, audio, scar-tissue, testing, enumerate-the-set]
beads: [polyglot-pdf-uxc6s]
surfaces: [frontend/src/shared, frontend/src/demo]
---

# A predicate that answered two different questions, and got one of them wrong

`isSpeaking()` on the audio manager means "is Gemini talking?" -- except that
turned out to be two questions with different right answers, and one caller
group had been silently getting the wrong one.

## The conflation

bd `s1iex.4` changed `isSpeaking()` to `geminiIsSpeaking && activeClipCount
=== 0`. That was correct and deliberate: a synthesized clip now lives INSIDE
the playback context, and `onVADSpeechStart` suspends that context while
`onVADSpeechEnd` only resumes it when the model is quiet. If a clip counted as
speaking, it would suspend mid-word and never resume. Subtracting clips
prevents a real deadlock.

But the same predicate is read by the barge-in sites, which ask a *different*
question: "would flushing the queue cut the model off mid-utterance?" For those,
a clip is irrelevant -- and during a model-PCM + clip **overlap** the predicate
answers false while the model is genuinely talking, so every barge-in skipped
its flush and the model kept talking over the user.

The overlap is reachable, and the s1iex.4 diff documents why itself:
spellbackPlayer's pre-clip drain-wait is bounded and "plays anyway on timeout."

## The root cause was one level below the bead's description

The bead framed this as "subtracting clips makes it model-only, which is wrong
during an overlap." Measuring it showed something sharper: **`geminiIsSpeaking`
is set true by BOTH producers** -- the PCM scheduler and `attachClipElement`.

```
overlap (model + clip) -> (geminiIsSpeaking=true, activeClipCount=1)
clip alone             -> (geminiIsSpeaking=true, activeClipCount=1)
```

They are *the same state*. No arithmetic on those two variables can separate
them, because the model-PCM fact was already destroyed when both producers
wrote the same flag. That is why the fix has to read `activeAudioSources`
directly -- the model-PCM source list -- rather than trying to correct
`isSpeaking()` in place. Worth knowing before reaching for a subtraction: check
whether the quantity you are subtracting from still contains the information.

## The bead named five sites; there were eight, and the omissions were the
## dangerous ones

Enumerating before touching anything (scar #7) found three call sites the bead
did not list -- and all three were in the group where a change would be
actively harmful:

- `VoiceOverlay.tsx:503` and `VoiceOverlayMobile.tsx:433` -- the SUSPEND half.
- `connection.ts`'s `onVADSpeechEnd` -- the **RESUME** half.

Had I worked from the bead's list and then "tidied up the remaining
`isSpeaking()` calls for consistency," I would have re-introduced the exact
deadlock s1iex.4 exists to prevent. The bead's list was safe only by omission:
it never told me those three must NOT move, so nothing in it would have stopped
me. All three now carry comments saying the choice is deliberate.

## Testing the guard found a hole in the guard

The set-pinning test classifies every call site by the accessor it must use.
First cut looked fine and passed. Then I mutated in a *new* unclassified
consumer written the way a real caller would write it:

```ts
connectionManager?.getAudioManager()?.isSpeaking()
```

It sailed straight through -- my regex anchored on a receiver literally named
`audioManager`. The guard would have caught a regression of an existing site
while missing the case it primarily exists for: a NEW site choosing wrong.

Same shape as bd `8bjdx` two rounds ago (a `field.options` scan evaded by a
consumer that named the object `trigger`). The recurring lesson: **a
source-scanning guard must be mutation-tested with the shape a future author
would actually write, not just by regressing a line already in the table.**
Regressing an existing line only proves the table is wired up; it says nothing
about the net's holes.

A second, subtler version of the same problem: the first cut keyed entries on
fragments that *included the method name*, so regressing a site made its entry
go STALE rather than tripping the accessor assertion -- a real failure, but with
an unhelpful message pointing at the table instead of at the offending line.
Fragments are now accessor-independent, so a regression matches its entry and
fails with "X uses isSpeaking() where the classification says isModelSpeaking()"
plus the reason. Two `connection.ts` sites share a line shape and are
disambiguated by the nearest preceding token rather than a line number, which
would rot on the first edit above them.

## The outer review found the doc I had falsified

I enumerated the CODE consumers carefully -- eight sites, three categories,
a test pinning the set. I never asked which DOC asserted the contract I was
changing.

`docs/components/voice-ai.md` said: "TWO predicates, deliberately distinct:
`isSpeaking()` is MODEL-ONLY (every caller is turn-taking / barge-in logic)."
Both halves were true on `origin/dev`; both were false the moment my diff
landed. There are three predicates now, and NO barge-in caller reads
`isSpeaking()` any more.

That is the tier-2 doc an agent reads before touching the audio pipeline, so
it was steering the next author toward the exact accessor my new guard exists
to reject -- a guard and a doc pointing opposite directions, with the doc
loaded first.

Same lesson as bd `77j0d` the round before, arriving from a different angle:
**"where does this claim live?" is a bigger question than "which code calls
this function?"** There, the answer included bd memories. Here it included a
surface doc. In both cases my enumeration was rigorous within the category I
had chosen and blind to the category I had not.

## Three more holes, all in things I had just built

The same review filed three non-blocking findings, and the pattern in them is
uncomfortable: each is a place where I fixed one instance of a class and left
a sibling.

- **The anchor collapse.** My set-pin guard resolved a site by
  `lines.indexOf(text)` -- first match wins. Regressing the RESUME half to
  match the flush half makes both `connection.ts` sites byte-identical, so
  both bind to the first site's anchor and the PRIMARY assertion passes on a
  genuine deadlock regression. The staleness test caught it, but its message
  says "update or remove the entry" -- the wrong remedy, pointed at the table
  instead of the bug. Now resolved by line index.
- **`cleanup()` left `activeAudioSources` populated.** It resets
  `activeClipCount` and `geminiIsSpeaking`; my accessor reads a THIRD piece of
  state I never added there. The sources are stopped with their context
  closed, so `onended` never fires to drain them -- a stranded entry reports
  the model as talking for the manager's whole life.
- **A comment of mine claimed an overlap that cannot occur at that site.**
  Mobile's PTT press releases the clip synchronously before the check, so
  `isSpeaking()` would have read the same there. The accessor choice is still
  right for a reason that survives (`s1iex.5` adds a second clip producer),
  but I had written down a justification that was false.

## Process notes

- The overlap test drives REAL scheduled PCM alongside an attached clip. The
  existing clip tests (`clipAnimatesSol.test.ts`) only ever drive clips, which
  is exactly why they could not see this: the bug needs both producers active
  at once, and no test had ever put them there.
- Mutation-verified in both directions, deliberately: narrowing
  `isModelSpeaking` back to the conflated predicate reddens 3 tests, widening it
  to a union reddens 2 different ones. A signal that must sit strictly between
  two others needs both bounds pinned, or the next "simplification" collapses it
  into whichever neighbour is closer.
- A `SchemaForm.previewEdit` failure appeared mid-run. Rather than reasoning
  that my diff was unrelated, I stashed and re-ran: it passes on clean `dev` and
  is flaky under full-suite load -- already tracked as bd `cfl28`. ~60 seconds
  and dispositive.
