---
date: 2026-07-02
bead: polyglot-pdf-gihj
title: "fix: 8-bead small-bug bundle -- falsy tool-state values, nested validation constraints, overlay gates, visibility semantics, save-path error handling"
tags: [hotfix, testing]
---

## Trigger

A maintainer-initiated "grab a bunch of open beads and resolve them" sweep. The
ready queue held a crop of small, self-contained P2/P3 bug beads that were each
too small to warrant a full PR cycle alone, so eight were claimed and bundled
into one PR per the bead/PR contract (one PR may close several whole beads):
polyglot-pdf-gihj, -0mv2, -gtbw, -8v53, -bxng, -rigd, -5k52, -k2ww.

## What shipped

**Backend (2 beads).**
- **gihj** -- `_handle_get_form_status_tool` skipped any falsy value
  (`if not value`), so a checkbox stored as `False`, a numeric `0`, or an
  explicit empty string vanished from the model's compact form-state view.
  Only `None`/missing now counts as unanswered (legacy non-dict branch too).
- **0mv2** -- `_validate_text`/`_validate_date`/`_validate_number` read
  pattern/length/min/max/digits_only/date_constraint from the flattened
  top-level keys only, silently skipping the canonical nested
  `validation.<snake_case>` location of raw schema dicts. New
  `_resolve_constraint` helper (mirrors cn0e's `_resolve_format_preset`:
  nested-first, top-level fallback, dict or Pydantic model) wired into all
  three validators. Tests exercise the REAL i-90 nested fields plus the
  pre-flattened validation_handler shape (no regression).

**Frontend (4 beads).**
- **8v53** -- the mobile FAB speech-dot badge kept the dead
  `vad.userSpeaking && !nativeVad` gate 1dvp removed from the panel row
  (permanently dark under the deployed native-VAD default); now
  `isListening && micSending`.
- **bxng** (re-scoped; see the bead comment) -- the bead pre-dated PR #278,
  which deliberately made the listening-indicator + meter gates
  connected-only in BOTH overlays; those were NOT widened. The one real
  remaining divergence was mobile `isConnected` itself, which excluded
  `switching_section`/`reconnecting` -- status dot flashed grey and the
  thinking indicator vanished mid-switch. Widened to match desktop.
- **rigd** -- `shouldShowField`'s `is_empty`/`is_not_empty` compared only
  null/undefined/"", so a checkbox-group's empty `[]` counted as NOT empty
  (inverted gate; latent -- no schema uses these operators yet). Array
  branches added, mirroring `is_checked`; the schema-editor preview port
  (`conditionalVisibility.ts`) updated to match with its parity test.
- **5k52** -- `updateField`'s steered-marker carry-forward read the prior
  FieldValue by exact key while `markFieldsSteered` writes through the
  `[]`-bracket alias, so a value migrating between id variants dropped the
  marker (one extra re-steer). Carry-forward now uses the same alias fallback.
- **k2ww** -- test-parity gap: added the FE mirror of the backend
  uscis_account normalization/validation suite.

**Schema-editor (1 bead + rigd's port).**
- **gtbw** -- the plain-download save path (non-File-System-Access browsers)
  was the only save path of four without a try/catch; a `saveSchema` throw
  escaped unhandled with no user-visible signal. Now routed through the
  `setSaveError` banner like the other three, with a regression test.

**Pre-PR assess (Step 5.5).** Rubric: all 11 exit criteria across the 8 beads
scored PASS. Fresh-eyes (Sonnet, picker arm ran, 1 round): **NO-GAPS**. It
verified the bxng re-scope is faithful desktop parity (the shared
`isConnected` also gates the PTT bar / pause button on desktop identically --
pre-existing coupling, not new scope) and filed one out-of-scope bead:
**polyglot-pdf-vtdx** -- `send_manual_field_update` (audio_handler.py) has the
same falsy-skip bug class gihj fixed, in a sibling path this bundle did not
touch. Its low-confidence note about stale `[]`-alias duplicate entries in
`fieldValues` is the family already tracked by polyglot-pdf-abuk.

## Verification

- Backend: `pytest -m "not external"` -- 1237 passed, 3 skipped (prep re-run
  on `backend/tests/`: 674 passed). Includes the new falsy-answers test, the
  nested-constraint suite, and the updated compact-format tests (the `""`
  semantics change updated two existing assertions -- see Lessons).
- Frontend: vitest -- 493 passed / 31 files, including 8 new overlay-gate
  tests (rAF-driven `micSending`, native-VAD mock), the is_empty array tests,
  the steered-alias migration tests (both directions), and the uscis_account
  mirror.
- Schema-editor: vitest -- 382 passed / 31 files (3 pre-existing fork-pool
  startup-timeout warnings from the worktree junction setup; not test
  failures), including the download-fallback banner regression test and the
  updated is_empty parity test.

## Lessons

- **An exit criterion can quietly widen a wire-visible format.** gihj's
  "only null/missing is empty" phrasing also changes what an explicit `""`
  means in the compact state string (`field::status` now appears). Two
  existing tests asserted the old omission; both were updated deliberately
  rather than worked around -- the bead's description named the empty-string
  case explicitly, so the criterion governed.
- **A re-scope note on a bead is load-bearing.** bxng's exit criterion as
  written (widen the listening indicator) would have REVERTED PR #278's
  deliberate design; the bead's reconcile note redirected to the real residual
  divergence. Reading the note before implementing avoided shipping a
  regression dressed as a fix.
- **Bug classes recur in sibling paths.** The falsy-skip pattern fixed in
  gihj existed verbatim in `send_manual_field_update` (now polyglot-pdf-vtdx,
  filed by fresh-eyes). When fixing a value-truthiness bug, grep for the
  pattern family before closing the book.

## Doc freshness

- Bumped: `docs/components/schema-forms.md` (both stamps) -- points here for
  the rigd `shouldShowField` array fix + 5k52 steered-alias carry-forward.
- Reviewed and left: the other STALE flags from `check_doc_freshness.py`
  (tool-call-flow.md, voice-ai.md, confirmation-and-audit.md,
  hipaa-pii-policy.md, validation-delegation.md, stateless-architecture.md,
  terminology.md, ws-protocol.md, and the rest) -- grep-verified none assert
  the specific behaviors this branch changed; their staleness stems from
  OTHER branches' files (config.py, live_ai_gemini.py, deploy scripts) and
  pre-dates this PR.
- Beads housekeeping: no orphans; the three stale in_progress items (hrn,
  jf6w, ue5s) are genuinely active epics/tasks, left as-is.

## Files touched

- `backend/services/callback_handler.py` -- gihj falsy-skip fix
- `backend/tests/unit/test_get_form_status_compact.py` -- falsy-answers test + updated "" semantics
- `backend/utils/field_validator.py` -- `_resolve_constraint` + wiring
- `backend/tests/unit/test_field_validation_responses.py` -- nested-constraint suite
- `frontend/src/demo/VoiceOverlayMobile.tsx` -- FAB badge gate + widened isConnected
- `frontend/src/demo/VoiceOverlayListeningIndicator.test.tsx` -- 8 new gate tests
- `frontend/src/schema-forms/utils/validation.ts` -- is_empty/is_not_empty array branches
- `frontend/src/schema-forms/utils/validation.test.ts` -- rigd + k2ww tests
- `frontend/src/schema-forms/state/schemaFormState.ts` -- steered []-alias carry-forward
- `frontend/src/schema-forms/state/schemaFormState.test.ts` -- alias-migration tests
- `schema-editor/src/App.tsx` -- download-fallback try/catch
- `schema-editor/src/App.save.test.tsx` -- banner regression test
- `schema-editor/src/utils/conditionalVisibility.ts` -- is_empty parity port
- `schema-editor/src/utils/conditionalVisibility.test.ts` -- updated parity test
- `docs/components/schema-forms.md` -- stamp bump
