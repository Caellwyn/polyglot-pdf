---
date: 2026-08-31
bead: polyglot-pdf-cke6v
title: "client links: a spent link ends voice honestly -- and four rounds where each fix created the next bug"
tags: [client-links, voice-ux, frontend, i18n, review-rounds, regression-chain]
---

## Trigger

A client whose magic link hit its SPEND CEILING was closed 1013 with reason
`budget_exhausted`. `handleClose` branched on no code at all, so it burned
every backoff retry against a socket guaranteed to refuse, then settled on
`reconnect_failed` -- the status that drives a modal offering a Reconnect
button that cannot work. A client reads that as the app being broken, which is
exactly what the backend's 1013-not-1008 choice was made to avoid.

## What shipped

A terminal `budget_exhausted` status, checked before every retry branch. A
third variant on the existing modal: no recovery action, but dismissible. The
copy says what still works -- typing, download, print -- and every word of it
is true, because retrieval never redeems a link.

**The load-bearing distinction: 1013 carries TWO reasons with opposite
handling.** `budget_exhausted` is permanent. `budget_unavailable` means OUR
spend store was briefly unreachable, which is transient and must keep
retrying. Branching on the CODE -- the obvious fix -- would strand a client
over our own outage. A test reddens on exactly that mistake.

## Four rounds, four regressions, each created by the previous fix

This is the part worth keeping. Every one was mine, every one was found by the
adversarial review, and none was visible from the diff I was looking at.

| Round | What I broke | How |
|---|---|---|
| 1 | (the original bug) | retries + dead Reconnect |
| 2 | the save prompt | new status left the `voiceEnding` gate that previously covered it |
| 2 | a section switch mid-close | early return skipped the teardown; watchdog overwrote the terminal status 15s later and the dead button came BACK |
| 3 | the Save button | my modal covered the nudge holding it -- and, after I aligned the copy, said the identical words |
| 4 | the whole page | suppressing the modal while the nudge is up meant pressing SAVE (which silences the nudge) summoned an unclosable full-viewport scrim |

The through-line: **I kept reasoning about the component I was editing rather
than the screen a client ends up looking at.** Each fix was locally correct.
The reviewer caught every one by asking what a real person sees and can do
next -- which is a different question from "is this code right".

Round 4's is the sharpest. The modal's own copy promises the client can still
type, download and print, while `position: fixed; inset: 0; z-index: 10000`
prevented all three. A terminal message that blocks the page contradicts
itself, and no unit test asks whether the page is usable.

## A test that pinned the bug as the spec

I wrote `it('offers NO buttons at all')` and mutation-verified it. It passed,
it was not vacuous, and it was **wrong** -- it asserted the exact property that
trapped the client, so any future fix would have had to delete a passing test
to proceed.

Mutation verification proves a test CAN fail. It does not prove the behavior it
pins is the behavior you want. Those are different questions and I had been
treating the first as sufficient.

## Translations: sourced, never invented

The message needs to exist in every supported language and I cannot write 17
translations. `resumeStrings.ts` already carried this message -- and later the
dismiss label -- professionally translated in exactly the same languages, from
the kit translation pipeline. Both were lifted rather than machine-translated.

That created its own bug, which round 1 caught: I authored the English row and
lifted the other 17, and they said opposite things -- EN "your answers are
safe" vs ES "save now so you do not lose your answers", with only English
naming the cause and the remedy. **English moved DOWN to match**, because the
alternative was machine-translating an immigration-intake message.

That is a real loss, deliberately taken: no client is now told the spend
ceiling is the cause, or that the firm can issue a new link. bd
`polyglot-pdf-7cy2f` carries the copy+translation pass.

## Enumeration, three times

Adding a status is never one edit. Each round found another set I had fixed
only one member of:
- terminal-status lists (`solState.isOffline`, the drop-marker clear)
- the `voiceEnding` gate
- five "no buttons" comments, two of which told a future maintainer that
  adding a button would be wrong -- written by this branch, falsified by this
  branch

The last one I found by grepping the CLAIM ("no buttons / button-less / not
dismissible") rather than the bead id -- the memory key
`enumerate-by-claim-not-by-identifier`, earned two beads ago and applied
without prompting here. 14 hits, 5 live false assertions; the `reconnecting`
variant's own no-buttons lines are still true and were left alone.

## Deliberately not fixed

- **Mobile has no save nudge at all**, so a mobile client is told to save with
  no Save control. Pre-existing, but this bead's copy makes it worse by
  instructing the save. Filed.
- **`onCancel` is optional at the type level**; a discriminated union would
  turn a forgetful caller into CI-red instead of a silently missing button.
  Stronger, but a refactor of a shared component beyond this bead --
  bd `polyglot-pdf-leakz`. Current form fails safe.
- **Raw status tokens** (`budget_exhausted`) render untranslated in a status
  line; **SaveNudge has no stylesheet at all**. Both pre-existing, both filed.

## One environment note

This session's bash PATH broke midway -- Windows-style and semicolon
separated, so `head`, `git`, `node`, `python` and `bd` all vanished. Three
backend tests then failed because the deploy script they exercise found no
interpreter. I nearly filed that as pre-existing breakage on dev: it
reproduced identically on a clean checkout, which is normally dispositive. It
was not, because the environment fault applies equally to both branches.
Reading the error text ("No python interpreter found") settled it where the
comparison could not.
