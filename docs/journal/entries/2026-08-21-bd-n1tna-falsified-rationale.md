---
date: 2026-08-21
bead: polyglot-pdf-n1tna
title: "docs(disclaimer): correct the falsified no-deterministic-text rationale"
tags: [review, conventions]
---

## Trigger

bd polyglot-pdf-nsb4y made the legacy model-read path serve deterministic
scripted text. That falsified a "no deterministic text to name" rationale
restated at five code sites the nsb4y diff never touched -- diff-induced
drift, not pre-existing rot.

The subtlety that makes this worth recording: **the FACT at every site was
still true, only the REASON was wrong.** `script_version` really is `None`
on that path. So nothing failed, no test went red, and no reader would
notice -- the comments simply taught the wrong causal model.

## What shipped

Six sites corrected to state the real mechanism: the client sources the
value from `introPlayerRef.current?.scriptVersion()`
(`VoiceOverlay.tsx:1315`), and `introPlayerRef` is populated only when
`introEnabled` (`:126`). It is `None` because the intro player was never
constructed -- not because there is nothing deterministic to name. Since
both intro flags default OFF, the DEFAULT deployment is the affected one:
the user reads deterministic scripted text and the audit record names
nothing. That is a real evidence gap, now labelled as such and pointed at
bd polyglot-pdf-pyebx.

Sites: `disclaimer_routes.py` (field comment + docstring), both overlays,
the test docstring (assertion untouched), and the `technical_guide.md`
routes row.

## Lessons

**A stale RATIONALE is invisible to every gate we have.** A stale fact
eventually breaks a test or contradicts an observable value; a stale reason
attached to a true fact breaks nothing. Tests pass, types check, greps for
the fact come back correct. The only detector is a human reading the
sentence and knowing the code. That makes rationale prose a surface worth
sweeping deliberately after any change that alters *why* something behaves
as it does -- not just *what* it does.

**Enumerate independently, then subtract.** I re-derived the set by grep
rather than trusting the bead's list. That confirmed its five, and also
separated out three near-misses that matched the phrasing but not the
claim: `extract_form.py:491` (widget option sets, unrelated) and
`VoiceOverlay.tsx:744` / `VoiceOverlayMobile.tsx:652` (about double-firing).
Scar #7 is usually framed as "don't fix one of N" -- the mirror risk is
fixing something that only *looks* like a member.

**Splitting a set along an ownership boundary is not an incomplete
enumeration.** `confirmation-and-audit.md:364` carries the same stale
clause and was deliberately left alone: it is bd pyebx's sole exit
criterion, and pyebx is tier:opus / cross-surface with an undecided
maintainer call attached (should the legacy path record a version at all?).
Fixing it here would have stripped an open bead of its purpose and forced a
product decision into a comment sweep. The outer review independently
agreed this split was correct rather than a gap.

## Doc freshness

- `docs/technical_guide.md` -- routes row updated; no stamp bump needed
  (bd abn4o / PR #622 removed the hand-bumped stamp from this file).
  Checker reports OK; the routes-table pinning test passes.
- `docs/standards/confirmation-and-audit.md` -- deliberately untouched, see
  above.
- The outer review filed `polyglot-pdf-33bsd`: bd pyebx cites this stale
  sentence at lines 335-336, but it actually sits at 364, which would send
  whoever picks it up to unrelated correct prose.

## Files touched

- `backend/routes/disclaimer_routes.py` -- field comment + handler docstring
- `backend/tests/unit/test_disclaimer_acceptance_route.py` -- docstring only
- `frontend/src/demo/VoiceOverlay.tsx` -- script_version comment
- `frontend/src/demo/VoiceOverlayMobile.tsx` -- same, byte-identical site
- `docs/technical_guide.md` -- disclaimer-acceptance routes row
