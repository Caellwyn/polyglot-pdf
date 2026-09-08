---
date: 2026-09-03
bead: polyglot-pdf-5ovod
title: "fix(forms): whitespace is not an answer -- one two-line fix, and the set it belonged to"
tags: [refactor, testing, review]
---

## Trigger

Leaving a field blank on a legal intake draft is a real decision. It has to be an
explicit act -- said aloud, or via the skip control -- not a side effect of typing
spaces.

It wasn't. A field containing only spaces satisfied the completion gate, passed
the required check, hid its own skip button, and could be confirmed -- while
printing blank on the PDF and never reaching the backend at all.

## What the fix actually was

Two lines of real logic: whitespace counts as absent. Everything else -- thirty
commits, five fresh-eyes rounds, four cross-surface rounds -- was about the SET
that logic belonged to.

The bead named two divergent sites. There were **seven**, and the backend was
correct at every one of its own. The divergence was entirely client-side, where
six predicates had each hand-written "is this field answered?" and every copy
tested `=== ''` without trimming.

## The pattern, which is the real content of this entry

**Every single review finding was a sibling the previous fix left behind.** Not
one was in the original change.

| Round | The sibling |
|---|---|
| 1 | `computeNextField` has TWO value predicates; fixing one left whitespace invisible to navigation entirely |
| 2 | `SchemaForm.tsx` auto-confirmed every keystroke -- the primary UI manufacturing the bad state |
| 3 | `isFormComplete` didn't get the recovery arm, so it CONTRADICTED `computeNextField` (and fires the paid validator) |
| 4 | `getProgressCounts` read 100% on an unfinished form; `computeReadyWindows` retired a blank field from validation PERMANENTLY |
| outer 1 | `skip_field`'s guard was the last voice EXIT -- closing the others created a deadlock |
| outer 2 | `switch_field`'s ack told the model to "read back" a blank |
| outer 3 | `already_confirmed` is checked BEFORE `has_value`; I fixed the branch below the one that fires first |

Each fix was locally correct and locally complete. The failure was never the
logic; it was believing a predicate had one home.

**What finally ended it** was not another patch but three structural moves:
one `isBlankFieldValue` for "is it answered", one `isConfirmedButBlank` for the
narrower "is it settled", and an invariant test asserting every consumer gives
the SAME answer -- so a future consumer fails CI instead of drifting quietly.

## The distinction that is easy to get wrong

The two helpers differ on exactly one input: a bare `''`.

- "Is it **answered**?" -- `''` is not an answer.
- "Is it **settled**?" -- a confirmed `''` on an OPTIONAL field IS the deliberate
  "the user said this does not apply" answer (bd `polyglot-pdf-6oe6`).

Reaching for the broad helper at a settle-site breaks that path. Not
hypothetical: I did it on the first attempt at the validator-window fix, and it
stopped a legitimately-confirmed optional field from ever settling. My own probe
caught it before review did.

The cross-surface pass then found the choice was **correct but unpinned** at the
fourth site -- swapping the helpers left all 1950 tests green. Now pinned; the
substitution reddens.

## The deadlock, and why in-diff review could never find it

Tightening the confirm gate was right. But `skip_field` had its own untrimmed
guard, so once the other exits closed, a required whitespace field had **no voice
exit at all**: cannot confirm, cannot skip, cannot clear. The backend marks the
skip refusal NON-RETRYABLE and its message suggests the very remedy the required
check had just closed, while `computeNextField` keeps re-offering the field.

Five fresh-eyes rounds cleared this because **the broken guard is in an untouched
file** -- nothing in the diff points at it. Only following the changed CONTRACT
outward reaches it. This is the clearest argument in the repo for why the outer
pass is a different job, not a second opinion.

**Generalised:** when you make a predicate STRICTER, enumerate every EXIT from the
state it now rejects, not just every site sharing the predicate. Recorded as bd
memory `tightening-a-gate-can-remove-the-last-exit`.

## Where my own verification was weaker than I claimed

Worth recording plainly, because it recurred:

1. **A one-field fixture cannot distinguish two code paths** that both return
   that field. My commit claimed "reverting the navigation predicate reddens
   exactly its own test"; reverting Priority 1 alone left all nine green.
2. **A test one layer below a guard is blind to the guard.** My escapability test
   called `markFieldSkipped` directly instead of driving `skip_field`, so it
   proved escapability beneath the blockage and passed while the real path
   deadlocked.
3. **Two false completeness claims in prose** -- "every predicate routes through
   it" (four did not) and "the backend's predicates all `.strip()`" (one does
   not). Both were assertions I made without enumerating.

The through-line: **prose and fixtures have no test to fail.** I am measurably
more likely to overstate in a comment or a docstring than in code, which is why
every behavioural change here now re-reads its own surrounding claims.

A count in prose rots the same way: "those six sites" went stale twice while I
edited the same paragraph. It is now written without a numeral.

## Verification

- Backend: full CI scope, 0 failed (no backend change was needed -- it was
  already correct).
- Frontend: 1952/1952 on a clean run. The suite is load-unstable on this machine
  independent of the diff -- three consecutive runs of the SAME tree gave 3
  failed, 4 failed, then 0, in files not in the diff, each passing in isolation
  (bd `polyglot-pdf-7y2yk`).
- Every fix mutation-verified, several against the exact defect a reviewer had
  just demonstrated.

## Deliberately left open

`applyResume`, the preview painter, and the DOM pre-fill capture still test
untrimmed. None gates completion, confirmation, progress or a voice exit, so they
are out of this bead's scope -- named honestly in the doc rather than implied
covered, and tracked as bd `polyglot-pdf-qpz11`, `polyglot-pdf-dctry`,
`polyglot-pdf-rm9x8`.
