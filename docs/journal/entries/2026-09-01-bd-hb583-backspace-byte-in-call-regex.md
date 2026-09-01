---
date: 2026-09-01
bead: polyglot-pdf-hb583
title: "test(voice): a literal 0x08 byte in the CALL regex defeated the bare-call shape"
tags: [frontend, testing]
---

## Trigger

`frontend/src/shared/speakingSignalCallSites.test.ts`'s `CALL` regex was
meant to have three alternatives (member call, computed member, bare
destructured call) via `(?:\.\s*|\[\s*['"\`]|\b)`. The third alternative
-- what an editor renders as `\b` (word boundary) -- was actually a
literal 0x08 BACKSPACE control byte on disk, not the two characters
backslash+b. Verified: `grep -rlP '\x08' frontend/src` matched only this
file, and reading the raw bytes at that position confirmed code 8.

Consequence: the alternation's third branch matched only a literal
backspace byte, which never occurs in source. `CALL` therefore matched
ONLY member calls (`.isSpeaking()`) and computed-member calls
(`['isSpeaking']()`) -- the bare destructured-call shape the comment
above the regex explicitly documents (`isSpeaking()` from `const {
isSpeaking } = am`) was invisible to both `discoverConsumers()` (which
decides which files are even scanned) and the per-line classification
walk. The test stayed green only because every call site that exists
today happens to be a member call.

## Fix

- Replaced the literal 0x08 byte with a real two-character `\b` escape
  (done via a small Node script operating on the raw bytes, since a
  string-based editor match can't reliably target a literal control byte).
- Hardened `discoverConsumers()` to test comment-STRIPPED text
  (`splitCodeLines`, the same stripper the per-line walk already used)
  rather than the raw file. This was previously accidental: the same
  0x08 bug that broke the bare-call shape also happened to make `CALL`
  never match prose/comment mentions, so a JSDoc reference to an
  accessor name was (by luck, not by construction) never mistaken for a
  decision site. Now it holds by construction.
- Extracted `discoverConsumers()`'s filter predicate into a named
  `isConsumerContent()` function, so a test can call the REAL production
  logic directly instead of hand-recomposing `CALL` + `splitCodeLines`
  inline -- the Opus cross-surface review caught that my first version of
  the comment-only test did exactly that hand-recomposition, and stayed
  green even when `discoverConsumers()`'s own comment-stripping was
  reverted (CLAUDE.md scar #8: pinning nothing real). Rewritten to call
  `isConsumerContent()` directly; mutation-verified it now reddens under
  that same revert.
- Added two tests: one pins that `CALL` matches a bare destructured call
  (and that the other two shapes keep matching -- this bead must not
  narrow them); one pins, via `isConsumerContent()` directly, that a
  comment-only mention is NOT a consumer while a real call still IS.

## Correction: isAnyAudioPlaying is NOT gated on the unmerged a08po branch

An earlier draft of this entry wrongly claimed `isAnyAudioPlaying` "does
not currently exist on `dev`" and traced it to bd `polyglot-pdf-a08po`
(PR #698, still open/unmerged). That grep was scoped to only
`webFormConnection.ts` and mistakenly generalized to the whole tree.
`isAnyAudioPlaying` is in fact defined in `audioManager.ts` and already
called (a real member-call, `audioManager.isAnyAudioPlaying()`) in
`useGeminiSpeaking.ts` -- shipped well before this bead, via bd
`polyglot-pdf-s1iex.4` (PR #592), and `useGeminiSpeaking.ts` is already
one of the four files in this test's own `SCANNED` list. `a08po`/#698 is
unrelated to that accessor's existence -- and the bead itself is
`CLOSED` (shipped 2026-08-31); only its PR (#698) remains open, for its
own, separate reasons.

The bead's underlying cross-surface concern (a comment-only mention of
an accessor name falsely marking a file as a "consumer") is not
currently reproducible against any EXISTING production file this test
discovers -- no file in the repo today mentions either accessor in a
comment only, verified by shape-enumerating every real mention in the
tree during the Opus cross-surface review. The fix still stands on its
own merits and is pinned directly against `isConsumerContent()` itself
(see Testing below), independent of whether any real file happens to
exercise it today.

## Review

Two rounds: an inner fresh-eyes pass (`NO-GAPS`) and an Opus cross-surface
pass. The cross-surface round found the isAnyAudioPlaying/a08po
misattribution above, plus that the comment-only test as first written
didn't actually call `discoverConsumers()`'s real logic (see Fix above) --
both fixed in this same diff before shipping. It also filed two
non-blocking follow-ups: `polyglot-pdf-yutz2` (the now-real `\b` also
matches function/type DECLARATIONS, not just calls -- currently latent
because the only declarations live in the basename-excluded
`audioManager.ts`) and `polyglot-pdf-fw4uu` (this entry's a08po-status
wording, also fixed inline).

## Testing

Mutation-verified all fixes independently:
- Reverting the `\b` fix to the original 0x08 byte reddens the new
  bare-call test and the new comment-only-mention test (both).
- Reverting `isConsumerContent()`'s comment-stripping (keeping the regex
  fix) now correctly reddens the comment-only-mention test, since it
  calls that real function directly rather than a hand-recomposed
  expression.

Full frontend suite: 123 files / 1791 tests, all green.
