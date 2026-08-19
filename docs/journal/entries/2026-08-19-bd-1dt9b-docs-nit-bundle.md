---
date: 2026-08-19
bead: polyglot-pdf-1dt9b
title: "docs: fix 3 stale claims -- intro player, validated-draft wording, unpublished status"
tags: [review]
---

## Trigger

Continuing the standing low-complication-bead sweep: three unrelated,
single-file docs-nit beads found in the backlog, each a factual claim that
went stale after a feature shipped and the doc describing it wasn't updated.

## What shipped

- **bd 1dt9b**: `docs/standards/confirmation-and-audit.md` claimed the
  Undertaken legal register (the "you agree to review..." intro-script
  wording) was unreachable because "the intro clip has no frontend player."
  The player shipped in bd s1iex.5 (closed) --
  `frontend/src/shared/introPlayer.ts` POSTs to `/api/tts/intro` and
  `DisclaimerModal`'s `introParagraphs` prop renders the intro script when
  the frontend flag is on. Corrected to the real, narrower gate: both
  `INTRO_TTS_ENABLED` (backend) and `VITE_INTRO_CLIP_ENABLED` (frontend)
  default off, so the register is unreachable on the DEFAULT deployment,
  not unreachable outright.
- **bd m2dxw**: `schema-editor/README.md` and `EDITOR_GUIDE.md` both
  described the local `/api/extract` output as "a validated draft." Under
  the current contract (`extract_form.py`'s `EXIT_ISSUES` path ->
  `storedWithIssues: true`), a draft is stored even when it does not fully
  validate, mirroring the hosted route's behavior. Corrected both files.
- **bd 4dtny**: `schema-editor/EDITOR_GUIDE.md` was stale on the
  `unpublished` kit status (added by bd 6dz0): the status-badge line still
  enumerated two values, and the Unpublish / Publish-again buttons were
  undocumented. Verified both buttons are real
  (`schema-editor/src/components/RemoteCatalogue.tsx`) and documented their
  actual gating (Unpublish is author-only; Publish-again reruns the full
  publish gate). Of the bead's three cited defects, only these two still
  reproduced -- the third ("Always available" claim about Revert to draft)
  no longer existed in the file, fixed by an earlier untracked pass.

## Lessons

The `4dtny` bead's third cited defect had already been silently fixed
before this pass claimed it -- the same "bead premise no longer matches
current dev" shape as `gz7dv` and `z7joa` from earlier batches this
session. Verifying each of a bead's individual claims against the live
file (not just trusting the bead description wholesale) before writing a
fix continues to pay off: two of three claims in `4dtny` were live, one
wasn't, and fixing only the live two kept the change scoped to what the
exit criterion actually required.

## Doc freshness

- `docs/standards/confirmation-and-audit.md` -- stamp bumped; live checker
  reports OK.
- `schema-editor/README.md`, `schema-editor/EDITOR_GUIDE.md` -- no
  freshness stamp (confirmed outside the tracked tier-2 set, per bd
  m2dxw's own description); no stamp change applicable.

## Files touched

- `docs/standards/confirmation-and-audit.md` -- corrected Undertaken-register
  reachability claim + stamp bump (bd 1dt9b)
- `schema-editor/README.md` -- corrected "validated draft" wording (bd m2dxw)
- `schema-editor/EDITOR_GUIDE.md` -- corrected "validated draft" wording (bd
  m2dxw) + documented the unpublished status and its two buttons (bd 4dtny)
