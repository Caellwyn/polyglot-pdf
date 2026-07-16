---
date: 2026-07-16
bead: polyglot-pdf-rvac
title: "fix(voice-ux): tester-session UX fixes -- slower pace, char-by-char read-back, spelling-first names, clear-form resets to language choice, no section rubber-band, hide Submit"
tags: [hotfix, conventions, testing]
---

## Trigger

A live tester session surfaced five UX rough edges (maintainer report,
2026-07-16). None were tracked; they were batched into one bead
(polyglot-pdf-rvac) because each is a small, independent fix and a full PR cycle
per fix would waste review resources:

1. The AI talks too fast -- needs to be slower in general, and MUCH slower when
   reading back numbers or spelled-out names (character by character).
2. The "Clear form" button clears fields but does NOT return to the app-start
   language-choice screen, so a tester cannot cleanly reset between clients.
3. In the simplified view, the shown section pops back to section 1 after every
   confirmation (it moves to the right section when the next question starts,
   then rubber-bands back once the value is confirmed).
4. The "Submit Form" button does nothing (there is no submission target yet) and
   only confuses testers.
5. In 1 of 4 tests the AI asked for the name first and THEN asked how to spell it
   -- an extra, unnecessary voice turn.

## What shipped

**Backend (system-instruction wording, `backend/config.py`).**

- *Pace + character-by-character read-back (issue 1).* The DTI SI SPEECH STYLE
  block now instructs the model to speak noticeably slower than a natural
  conversational pace, and -- for numbers (dates, phones, ZIPs, id numbers) and
  spelled-out names -- to pronounce each digit/letter INDIVIDUALLY with a distinct
  pause between characters (e.g. `N ... G ... U ... Y ... E ... N`) rather than
  running them together, so the user can verify one character at a time.
- *Spelling-first names (issue 5).* The NAMES block (both the live DTI SI and the
  legacy harness-baseline SI, kept in sync) now states that asking for the
  spelling must be the VERY FIRST question for a name field, and explicitly
  forbids asking the name first and then re-asking for the spelling. The
  static-contract substrings (`"how do you spell"`, `"spelling back"`) are
  preserved, so `test_tool_contract_static.py` stays green (28/28).

**Frontend UX.**

- *Clear-form returns to language choice (issue 2).* Extracted the onboarding
  sessionStorage helpers (the app-start form + language keys, and
  `clearOnboardingState`) out of `SchemaFormDemo.tsx` into a shared
  `schema-forms/onboardingStorage.ts`, so the overlays can force the same full
  reset without re-declaring the key strings. `VoiceOverlay.handleClearForm` and
  `VoiceOverlayMobile.handleClearForm` now call `clearOnboardingState()` before
  the reload; with both onboarding keys absent, `SchemaFormDemo`'s mount effect
  re-shows the language-choice modal.
- *No section rubber-band (issue 3).* In continuous mode the visible section is
  UI-only: the voice session fills across the whole form and the connection's
  persisted state keeps `currentSectionId` pinned at the first section. A
  confirmation's field-value save (`webFormConnection.updateField` ->
  `SchemaFormStateManager.save`) dispatches `schemaFormStateChange` carrying that
  pinned section, and `SchemaForm`'s listener was blindly adopting it -- popping
  the paged view back to section 1. Both listeners (the `schemaFormStateChange`
  storage listener AND the `vffOnSectionChanged` handler) now preserve the current
  React `currentSectionId` in continuous mode via a functional `setState` updater,
  taking only the fresh field values. The non-continuous path still adopts
  `newState.currentSectionId` unchanged (the deprecated section-reset flow owns
  nav there). A regression test was added to the existing continuous-mode
  section-paging describe block.
- *Hide Submit (issue 4).* The whole navigation block (manual prev/next AND the
  "Submit Form" button) is now gated to non-continuous mode, so nothing renders
  in the production continuous path. The Submit button was removed outright rather
  than hidden with CSS; a code comment points at re-adding it when a real
  submission target exists.

**Assess (SPEAR pre-PR).** Exit-criteria rubric scored 4/4 PASS (both criteria,
both halves). Recursive adversarial fresh-eyes: 1 Sonnet round -> NO-GAPS, then
the guaranteed Opus final clearing round -> NO-GAPS. Fresh-eyes surfaced two
low-confidence nits, both PRE-EXISTING and out of scope for this bead, neither a
gap against the rubric: (a) the non-continuous storage-listener fallback has no
direct regression test (an existing test gap this diff didn't need to close);
(b) `SchemaFormDemo.handleClearSession` hardcodes the `"schema_form_state"` key
literal instead of calling `SchemaFormStateManager.clear()` like the two overlay
handlers do (functionally correct today; a latent rename landmine). Both deferred,
not fixed inline (unchanged pre-existing code); noted here rather than filed as
beads given their triviality.

## Lessons

In continuous mode, `currentSectionId` is a UI-only paging cursor -- the backend
and the connection's persisted state deliberately keep it pinned at the first
section (the backend is stateless; the client owns section state, and continuous
mode has no section-COMPLETE transitions). Any `setState(load())` that adopts the
persisted `currentSectionId` wholesale will therefore fight the UI's paging. The
fix pattern is a functional updater that keeps `prevState.currentSectionId` in
continuous mode and merges only the fresh field values. This is already captured
in `docs/components/schema-forms.md`; not general enough for a `standards/` line.

## Doc freshness

- **Bumped** `docs/components/schema-forms.md` (it tracks `SchemaForm.tsx`): the
  Rendering prose said the form has "a final Submit" and "continuous sessions show
  only Submit" -- now WRONG, since the nav block (incl. Submit) is hidden in
  continuous mode; and the `currentSectionId`-FOLLOWS state prose now records the
  rubber-band-guard in the listeners. Stamp advanced to 2026-07-16 with a pointer
  to this entry.
- **Reviewed and left** `docs/components/voice-ai.md`: it documents the Gemini
  adapter / session / tool-calling mechanics, NOT the SI prose content (the SI
  text lives in `config.py`; the doc points to it), so the pace/spelling wording
  changes do not affect its current-state prose.
- **Left as pre-existing stale** the many `standards/` + `technical_guide.md` docs
  the freshness checker flags because they track the large `backend/config.py`
  file: they describe models / cost / VAD / token-reduction / risk, none of which
  my SI-wording edits touch. They were already stale (dated 2026-07-05..07-15)
  before this branch; not this branch's to fix.

## Files touched

- `backend/config.py` -- DTI SI SPEECH STYLE (pace + per-char read-back); DTI +
  legacy SI NAMES block (spelling-first).
- `frontend/src/schema-forms/onboardingStorage.ts` -- NEW; shared onboarding
  sessionStorage keys + load/save/clear helpers.
- `frontend/src/schema-forms/SchemaFormDemo.tsx` -- import onboarding helpers from
  the shared module (removed the local copies).
- `frontend/src/demo/VoiceOverlay.tsx` -- `handleClearForm` clears onboarding
  state before reload.
- `frontend/src/demo/VoiceOverlayMobile.tsx` -- same clear-form change.
- `frontend/src/schema-forms/components/SchemaForm.tsx` -- continuous-mode
  section-preservation in both state listeners; nav block (incl. Submit) gated to
  non-continuous mode.
- `frontend/src/schema-forms/components/SchemaForm.test.tsx` -- regression test:
  the paged section survives a confirmation-time field-value save.
- `docs/components/schema-forms.md` -- freshness bump (Submit hidden; rubber-band
  guard).
