---
date: 2026-07-25
bead: polyglot-pdf-kcia
title: "Deferred-nit cleanup bundle: kcia (harness/probe) + rcbw (fixture accent) + 6hhc (editor UX)"
tags: [conventions, testing, schema-editor]
---

## Trigger

Three accumulated deferred-nit beads (arm-C deferrals from earlier closeouts),
bundled into one PR per the doctrine's "several tiny nit beads bundled into one
closeout." All were reviewer-classified low-confidence/cosmetic at the time.

## What shipped

**kcia (4 notes from the probes-PR review):**
1. The "Google recommends it" comments on `speech_config.language_code`
   (live_ai_gemini.py + config.py) now carry the vendored doc's tier scoping:
   the recommendation is for the CASCADED gemini-live-2.5-flash tier
   (live-api-best-practices.md:56); on this repo's native-audio tier the field
   is endpoint-VERIFIED accepted, not doc-recommended.
2. WAIVED with rationale (recorded here): "optionally add 1 en smoke run next
   sweep" asks for future LIVE test coverage, not a code change -- out of scope
   for a nit cleanup PR (no live spend), and the kill-switch already de-risks
   the en-US path. Left for the next language sweep.
3. The cost harness (measure_form_session_costs.py) now captures
   `SPEECH_LANGUAGE_CODE_ENABLED` + `TRANSCRIPTION_LANGUAGE_HINT_ENABLED` in
   its run meta, so an m1lg A/B run's arm is machine-readable from the meta,
   not distinguishable only by findings prose.
4. The probe's `--arm` parsing (probe_transcription_lang_codes.py) was a
   substring check that silently ran the DEFAULT arm for the equals form
   (`--arm=speech-lang`). Replaced with a real `_arm_from_argv` that accepts
   both forms and hard-errors on an unknown arm (self-checked).

**rcbw:** `scripts/spikes/fixtures/multilang_phrases.json` es.confirm_yes
"Si, es correcto." -> "Sí, es correcto." (unaccented "Si" means "if"; the
JSON is UTF-8 data, accents allowed).

**6hhc (2 schema-editor UX nits):**
1. The FieldEditor "Why this field is flagged" banner was always red; now it
   is severity-aware -- ERROR-class findings (and local completeness errors,
   which ARE errors) render red to match FieldList.getFieldStatus's red row,
   WARNING-class render amber. A WARNING-only field no longer shows a green row
   with a red banner. Pinned by a new FieldEditor.severity.test.tsx (4 cases).
2. Undo-after-rename no longer drops the selection: selection is deliberately
   not part of undo history, so undoing a field-id rename left selectedFieldId
   holding the vanished NEW id (editor fell back to the metadata panel). Added
   a position-preserving re-point -- when the selected id vanishes, re-select
   the field now at its last-known index (a rename keeps the field's slot).
   Guarded so it never fires on load/clear or a delete (delete resets selection
   to null first). Pinned in App.rename.test.tsx (the existing undo test now
   also asserts selection recovery).

- Tests: FieldEditor.severity (4 new) + the rename-undo-selection assertion;
  full schema-editor suite 763 green + tsc clean; full backend + scripts
  suites green.
- Fresh-eyes triage: (filled at closeout -- see PR.)

## Lessons

- A substring `--arm` check (`"--arm" in argv and "speech-lang" in argv`) is a
  silent-wrong-arm trap: it passes for the space form and the equals form
  fails OPEN to the default. Parse the value, don't membership-test the tokens.
- Selection-not-in-history is a fine design choice, but it needs a
  vanish-recovery: any operation that both moves selection AND is undoable
  (rename) orphans the selection on undo. Re-pointing by position is the
  minimal robust fix without threading selection through the history stack.

## Doc freshness

- No tier-1/tier-2 doc tracks the touched files; comments carry the scoping.
  Reviewed, left.

## Files touched

- `backend/adapters/live_ai_gemini.py`, `backend/config.py` -- cascade-tier scoping comment (kcia 1)
- `scripts/spikes/measure_form_session_costs.py` -- language-flag capture in run meta (kcia 3)
- `scripts/spikes/probe_transcription_lang_codes.py` -- robust --arm parsing (kcia 4)
- `scripts/spikes/fixtures/multilang_phrases.json` -- es accent (rcbw)
- `schema-editor/src/components/FieldEditor.tsx` -- severity-aware banner (6hhc 1)
- `schema-editor/src/App.tsx` -- undo selection re-point (6hhc 2)
- `schema-editor/src/components/FieldEditor.severity.test.tsx` -- new (6hhc 1)
- `schema-editor/src/App.rename.test.tsx` -- selection-recovery assertion (6hhc 2)
