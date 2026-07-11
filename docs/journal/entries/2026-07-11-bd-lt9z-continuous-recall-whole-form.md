---
date: 2026-07-11
bead: polyglot-pdf-lt9z
title: "Continuous-mode get_field_value recall widened to the whole form (was scoped to the pinned first section)"
tags: [hotfix, testing]
---

## Trigger

Found during the G3 fill-correctness gate (bd polyglot-pdf-jnjj.7). In
continuous-session mode (the demo's production default),
`SchemaFormStateManager.getFieldBySpokenName` searched only
`{currentSectionId} + completedSections`. Continuous mode pins `currentSectionId`
to the FIRST section (bd polyglot-pdf-944q) and never calls
`switchToSection` / `markSectionComplete`, so `completedSections` stays empty --
a `get_field_value` lookup for any filled field OUTSIDE section 1 returned
`found=false` even when the field was filled. A silent wrong-answer path.

## Fix (option (a) from the G3 findings)

`getFieldBySpokenName` now branches on `state.continuousSessionEnabled`: in
continuous mode it searches the WHOLE schema (`state.schema.fields`), mirroring
`buildContinuousManifest`, which already presents the whole form as one section.
Section mode is unchanged (current + completed sections). The spoken-name /
alias matching logic is factored into a shared `matchesField` closure so both
paths use identical matching. ~20 lines, frontend-only.

## Why the SI needs no change (exit criterion 2 -- recorded decision)

The bead scoped three options: (a) widen the lookup, (b) steer the SI to
`ask_secretary` and treat `get_field_value` as legacy, (c) both. **Chose (a),
and (a) alone is complete** -- no SI steering needed:

- `get_field_value` stays a first-class recall tool (not deprecated).
- The model already learns every field's spoken name in continuous mode from
  `buildContinuousManifest`, which packs ALL fields (`field_id|spoken_name`) into
  the single synthetic "current section" the handshake sends. So the empty
  `getPreviousSpokenNames` (completed-sections-only) is NOT a functional gap in
  continuous mode -- the names reach the model via the manifest, not via
  `previous_spoken_names`. The only real defect was the LOOKUP rejecting a valid
  name, which (a) fixes.
- `ask_secretary` (whole-form, bd jnjj.45) remains the primary recall path;
  this just stops `get_field_value` from silently failing when the model uses it.

## Verification

- New `getFieldBySpokenName()` describe block in `schemaFormState.test.ts` pins:
  section mode finds a current-section field and rejects a not-yet-visited one;
  continuous mode finds fields OUTSIDE section 1 (field-4 in section-2a, field-6
  in section-3a) plus aliases; unknown names return null in both modes.
- Full frontend suite green (56 files / 906 tests, default forks pool); `tsc`
  clean.
