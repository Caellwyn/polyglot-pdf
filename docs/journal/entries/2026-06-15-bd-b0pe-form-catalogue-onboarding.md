---
date: 2026-06-15
bead: polyglot-pdf-b0pe
title: "D1: form catalogue + drag-drop onboarding (the editor's front door)"
tags: [schema-editor, feature]
---

## Trigger

`bd polyglot-pdf-b0pe`, the MVP of Track D (sprint 5, epic 7a9). The maintainer
surfaced the editor's missing FRONT DOOR: no way to onboard a new form. The editor
read a hardcoded `AVAILABLE_FORMS` list from its own `public/schemas/` static
copy, disconnected from `form-kits/`. The need: drag-drop an AcroForm PDF to add it
to a catalogue, see all forms at a glance, with completed forms gated from the
voice app.

## What shipped

Three layers, all on the local-files + git model the maintainer chose (no backend
API / browser-GCS auth):

1. **Deploy complete-gate** (`deploy-all.sh`). A `kit_is_complete` helper gates
   BOTH the upload and manifest loops (~lines 192-237): a kit reaches GCS / the
   voice-app manifest only if its `metadata.json` has `status:complete`. Draft or
   unmarked kits stay local + git-backed but never deploy. This closes the
   draft-leak window the Codex plan review flagged -- folded INTO D1 (not deferred
   to D2) because the moment D1 can write drafts into `form-kits/`, an unfiltered
   deploy would leak them. Added `form-kits/i-90/metadata.json status:complete` so
   the existing deployed form still ships (no regression).
2. **Catalogue logic** (`fileSystemAccess.ts` directory API + `formKitDirectory.ts`):
   `pickDirectory` (showDirectoryPicker, readwrite), `listKits` (read every
   `form-kits/<id>/` from a chosen dir), `readKitEntry` (label/status/has-schema),
   `loadKitSchema`, `onboardPdf` (drop a PDF -> new `form-kits/<id>/` with form.pdf
   + metadata.json status:draft, id-collision suffixing), `deriveFormId`.
3. **Catalogue UI** (`FormCatalogue.tsx` + `App.tsx`): "Open form-kits folder" ->
   list kits with status badges + drag-drop a PDF to onboard. Opening a kit reads
   its schema from the directory handle and builds a blob URL for its PDF to drive
   the existing schema + PDFViewer flow; the kit's own schema.json handle is the
   in-place save target (Cmd+S writes back, no picker). The old FormSelector now
   only renders when the directory API is absent (fallback).

The voice app's load path is untouched -- it still reads the GCS manifest, which
the gate now keeps draft-free.

## Lessons

- **Review a PLAN, not just code -- it's where the cheap fixes live.** Codex
  reviewing PR #199 (the plan) caught the draft-leak window, the wrong deploy
  surface, and the directory-API gap BEFORE any code was written. The draft-leak
  one was the keeper: deferring the gate to D2 would have shipped drafts to
  production via any deploy between D1 and D2. Fixed as one sentence in a plan
  instead of a production incident.
- **A "success" callback on an incomplete object is a bug.** Fresh-eyes round 1:
  the drop handler auto-opened the freshly-onboarded kit, but a just-dropped PDF
  has no schema yet, so the open errored on every SUCCESSFUL drop. The fix (surface
  a notice, don't auto-open) then spawned a notice-lifecycle gap (round 2: stale
  notice on folder-change). Two rounds of follow-on from one UX decision.
- **The grep-based bash gate is robust when anchored on the quoted key.**
  `"status"[[:space:]]*:[[:space:]]*"complete"` is case-sensitive and immune to
  the word "complete" appearing in other fields -- verified against 10+ adversarial
  inputs in review. No jq dependency needed.

## Doc freshness

- Frontend + a deploy script; the schema-editor has no tier-2 component doc, and
  `docs/components/config-deployment.md` describes form-kit storage modes but not
  the per-kit status gate -- a candidate doc update, but the gate is new behavior
  this bead introduces, noted here rather than retro-fitting a doc mid-feature.

## Follow-ups filed (fresh-eyes, out of scope for D1)

- `polyglot-pdf-45x5` -- no functional (behavioral) test for the bash
  `kit_is_complete` gate; the repo has no shell-test harness to slot into.
- `polyglot-pdf-snpi` -- `deploy-all.sh` hardcodes `schema.json` and ignores the
  `metadata.json` custom `schema` filename field.

## Files touched

- `deploy-all.sh` -- NEW `kit_is_complete` helper gating both form-kit loops.
- `form-kits/i-90/metadata.json` -- NEW (status:complete, preserves the deploy).
- `schema-editor/src/utils/fileSystemAccess.ts` -- directory-handle types +
  `isDirectoryAccessSupported` + `pickDirectory`; `FsFileHandle` gains `kind`.
- `schema-editor/src/utils/formKitDirectory.ts` -- NEW. Catalogue + onboarding logic.
- `schema-editor/src/components/FormCatalogue.tsx` -- NEW. The catalogue UI.
- `schema-editor/src/App.tsx` -- `handleOpenKit` + blob-URL PDF + integration;
  catalogue is the front door, FormSelector a fallback; welcome/guide copy updated.
- 3 new test files (formKitDirectory 11, FormCatalogue 6, plus A1 mock updates);
  160 editor tests pass.
- `docs/journal/entries/2026-06-15-bd-b0pe-form-catalogue-onboarding.md` -- THIS entry.
