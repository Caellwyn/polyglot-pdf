---
date: 2026-07-17
bead: polyglot-pdf-d25e
title: "fix(i18n): three 2h9j follow-ups -- editor rename staleness (d25e), first-session language seeding (p8sq), test isolation (r8gq)"
tags: [schema-editor, testing, conventions]
---

## Trigger

Three small bug beads bundled into one PR (the bead/PR contract allows whole-bead
bundling; each was too small for its own review cycle). All three fell out of bd
polyglot-pdf-2h9j (extraction-time option translations, PR #459): d25e and p8sq
were filed during its planning/live-verification; r8gq was filed by its outer
review (a latent test-ordering bug the new CLI test file introduced). Maintainer
delegated the follow-ups in-chat (2026-07-17, "follow up on those next beads
while I'm away").

## What shipped

- **d25e** -- `FieldEditor.tsx`: an option-label edit now DROPS that option's
  `label_translations` (they translate the OLD text and are keyed by language on
  the option, so a renamed option showed/spoke wrong-language labels via the
  runtime kit-precedence path). The drop rides the label `onChange` (React fires
  it only on a real text change); blur-without-change touches nothing; sibling
  options keep theirs. Re-bake on demand via the editor's Translate-options
  action or `translate_option_labels.py`. NEW
  `FieldEditor.translations.test.tsx` (2 tests).
- **p8sq** -- `SchemaFormStateManager.init` now seeds `selectedLanguage` from
  the app-start onboarding choice (`onboardingStorage.loadOnboardingState`),
  plus a backfill for pre-fix persisted states missing it. Previously the
  handshake-visible state got the language only at DISCLAIMER-AGREE, so a fresh
  session's FIRST connect carried `spoken_language: null` -- wrong en-US ASR
  bias for the disclaimer phase (bd y25o intent defeated) and the bd-ow1e
  option-translation warm-up guard-skipped until the post-agree reconnect.
  Live-verified (dev-local, fresh Spanish session on W-7): the FIRST connect
  now applies es-US bias and `option_translation_ready`/`applied` fire at
  session start (13/13 labels from the kit, zero secretary calls). The
  disclaimer-agree write is untouched. +4 state tests (seed, no-onboarding,
  pre-fix backfill, no-overwrite-on-resume).
- **r8gq** -- the translate-CLI test suite's `asyncio.run` closes the legacy
  implicit main-thread loop; 40 tests in `test_editor_kit_routes.py` /
  `test_form_kit_routes.py` / `test_dti.py` then failed when the CLI file was
  ordered FIRST (green today only by pytest's deterministic collection order).
  Every sync-test `asyncio.get_event_loop().run_until_complete` is now
  `asyncio.run`, and `test_coordinator_stash_and_consume` (which drives
  production `_register` -> `asyncio.Future()`) runs inside `asyncio.run`.
  Verified: the full backend suite passes with the CLI file forced first AND
  in natural order.

## Lessons

- `asyncio.get_event_loop().run_until_complete` in sync tests is a landmine
  with a delay fuse: it works until ANY earlier-ordered test calls
  `asyncio.run` (which closes the implicit loop), then dozens of unrelated
  tests fail. Use `asyncio.run` in sync test helpers; code that constructs
  futures (`asyncio.Future()`) must run inside a running loop.
- The schema-editor vitest suite wedges (zero output, indefinitely) when
  launched as a BACKGROUNDED Bash task on this machine, while the identical
  foreground run finishes in ~13s -- twice now. Run it foreground with a
  timeout (local memory: schema-editor-vitest-hangs-in-background).

## Doc freshness

- No tier-1/tier-2 doc tracks these behaviors at the level that changed (the
  d25e drop is an editor internal; the p8sq seed restores the ALREADY-documented
  y25o handshake contract; r8gq is test-internal). Flagged-stale docs from the
  freshness checker all track files this branch did not change -- reviewed and
  left, staleness predates this branch.

## Files touched

- `schema-editor/src/components/FieldEditor.tsx` -- label-edit translation drop.
- `schema-editor/src/components/FieldEditor.translations.test.tsx` -- NEW.
- `frontend/src/schema-forms/state/schemaFormState.ts` -- onboarding-language
  seed + backfill (import of onboardingStorage).
- `frontend/src/schema-forms/state/schemaFormState.test.ts` -- +4 tests.
- `backend/tests/unit/test_editor_kit_routes.py`, `test_form_kit_routes.py`,
  `test_dti.py` -- asyncio.run migration (r8gq).
- Suites: backend green with CLI-first ordering; frontend 1029; schema-editor
  755.
