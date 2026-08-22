---
date: 2026-08-19
bead: polyglot-pdf-1bsuq
title: "docs(technical_guide): document 3 uncatalogued cross-surface contracts"
tags: [review]
---

## Trigger

Continuing the low-complication-bead sweep: three unrelated beads all
targeting `docs/technical_guide.md`'s "Surface contracts" section --
CLAUDE.md's stated blast-radius reference for cross-surface reviews. Each
found a real contract that exists in code (and, in two of three cases, is
already test-pinned) but was never catalogued in the map a reviewer is told
to consult.

## What shipped

- **bd 1bsuq**: the `/api/editor/kits/{kit_id}/extract` route row didn't
  mention its write-locked-kit 409 gate (bd w3zw), even though the
  adjacent translate-options row documents the identical property for its
  own route. Verified the gate directly (`_is_write_locked(meta)` in
  `extract_editor_kit`) and matched the sibling row's phrasing.
- **bd 5guak**: added Surface contracts entry 8 for the intro agree-label
  mirror (`backend/services/intro_agree_labels.json` <->
  `DisclaimerModal.tsx`'s `BUTTON_TRANSLATIONS`). The label is
  interpolated into SPOKEN AUDIO via `intro_tts.build_intro_text`'s
  `[AGREE LABEL]` placeholder, so a drift means Sol says a button name
  that isn't on screen. The pair is already test-pinned; only the map
  entry was missing.
- **bd qfak0**: added entry 9 for `LIVE_VOICE_NAME`'s two independent
  consumers -- the Gemini Live session voice (an unaccepted name hard-1007s
  every session) and the spell-back TTS persona, which in turn selects the
  clip's measured loudness gain. `docs/components/voice-ai.md` already
  documents this well; the cross-surface map did not.

Every citation in both new entries and the corrected row was mechanically
verified (grep + line-content checks against the real files).

## Lessons

The outer Haiku docs-review caught a real markdown syntax error in my own
stamp rewrite -- a double-closing-paren (`).).`) left over from combining
this fix's credit with a pre-existing journal-entry link inline. Worth
naming as its own small trap: when a stamp's closing punctuation has to
thread through both a markdown link's own `)` and the outer parenthetical's
`)`, it's easy to leave one extra character behind. Fixed and re-verified
by having the reviewer trace the full paren-nesting tree, not just eyeball
it.

## Doc freshness

- `docs/technical_guide.md` -- stamp rewritten again (had regrown a
  stacked-history chain since this worktree branched before an earlier
  PR's stamp-prune landed on `dev`); replaced with a clean current-state
  sentence crediting all three beads plus the pre-existing `kkos` entry.
  Live checker reports OK, doc conventions clean.

## Files touched

- `docs/technical_guide.md` -- fixed the extract route row (bd 1bsuq) +
  added Surface contracts entries 8 (bd 5guak) and 9 (bd qfak0) + stamp
  rewrite
