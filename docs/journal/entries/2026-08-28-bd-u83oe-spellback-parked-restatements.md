---
date: 2026-08-28
bead: polyglot-pdf-u83oe
title: "docs(spellback): fix two more live 'model is parked' restatements"
tags: [voice, spellback, doc-freshness]
---

## Trigger

bd `polyglot-pdf-kvrfq` wire-verified that the name_spellback tool's
"model is parked" design assumption is false. `kvrfq` and a follow-up
(`98dsq`) corrected four locations; this bead's own two named targets
turned out to be the start of a longer chain.

## What shipped

Fixed the two named locations, then found and fixed two MORE live
restatements via a broader grep sweep during review. Both of the new
fixes were in `frontend/src/webFormConnection.ts`, and inserting lines
there shifted six unrelated line-number citations in
`docs/technical_guide.md`, caught across four separate review rounds.

## Lessons

**A one-line docstring edit to a heavily-cited file can break more
citations than the edit itself touches, and a mechanical checker can miss
every one of them.** `scripts/check_doc_freshness.py`'s citation checker
(built earlier this session) only catches a citation running past a
file's EOF or landing on a blank line -- it cannot catch a citation that
still lands on real, non-blank code that just isn't the RIGHT code
anymore. Six citations drifted this way from two small insertions, and
the mechanical check reported "clean" the entire time. Four review rounds
were needed because each round's grep for "the specific pattern last
found" missed a sibling a few lines away in the same file -- only an
exhaustive, repeated sweep (not a single pass) actually closed it out.

**When a bead's own scope keeps growing mid-review, the right response is
usually to finish the current ripple, not to stop and re-scope.** This
bead named two files; by the end it touched four, because the SAME edit
kept causing the SAME class of side effect. Splitting each newly-found
citation into its own bead would have meant four more review cycles for
fixes that were already made in the course of finishing this one. The
line was drawn at: fix everything THIS diff's own edits broke (in-scope,
however far that chain runs); file separately anything that was ALREADY
broken before this diff touched it (out of scope, however similar it
looks).

## Files touched

- `frontend/src/shared/audioSpellbackHold.test.ts` -- docstring corrected
- `backend/services/callback_handler.py` -- docstring corrected
- `frontend/src/webFormConnection.ts` -- two docstrings corrected
- `docs/technical_guide.md` -- six citations re-anchored to symbol names
