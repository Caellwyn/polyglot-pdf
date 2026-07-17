---
date: 2026-07-16
bead: polyglot-pdf-0x10
title: "Epic: schema-editor UX polish (rename, instructions, overlay, required, option badge, error hints)"
tags: [schema-editor, testing]
---

## Trigger

Maintainer session 2026-07-16: six UX pain points from hands-on W-7 touch-up
work in the hosted schema editor, approved as one epic (polyglot-pdf-0x10)
with per-issue child beads .1-.6. The maintainer's assistants were confused
by mutating internal slugs, mute red error icons, misaligned PDF overlays,
and instructions text flooding the simplified view.

## What shipped

One PR closing all six children (each individually small; one review cycle
beats three for a single coherent epic):

- **.1 field-id rename** (`fieldRename.ts`, `FieldIdHeader` in
  `FieldEditor.tsx`, `handleRenameField` in `App.tsx`): pencil-edit of the
  internal id with snake_case/duplicate/empty guards; one undoable commit
  retargets other fields' show_if/require_if (legacy + composite), section
  show_if, section fields[], copy_to, and the untyped supplements[].fields
  pass-through; selection follows; a merge stash mentioning the old id is
  dropped (ungroup falls back to reconstruction). pdf_field_name never moves.
- **.2 instructions are AI-guidance only**: the visible `help.instructions`
  render was removed from the editor PreviewPane AND the live app's six
  schema-forms field components (+ the orphaned CSS rule). The voice
  SI/guidance consumers (manifest_service, ai_context, secretary_context,
  navigation hint) are untouched; format_hint remains the on-screen hint.
- **.3 overlay anchoring**: overlays were positioned from the full-width page
  wrapper while the canvas centered itself inside it -- misaligned at every
  zoom below fit-width (the reported "only 150% works" was fit-width on the
  reporter's pane). The wrapper is now w-fit + mx-auto; the canvas no longer
  self-centers.
- **.4 top-level required debris**: schema_repair gained
  `migrate-top-level-required` (truthy -> validation.required, never
  clobbering the canonical key; legacy key always dropped) so Repair-all can
  clear the lint ERROR; all three editor schema load paths self-heal the same
  shape via `migrateLegacyRequired`. Root cause fixed earlier by bd 8n2s; this
  cleans the data the old editor left behind.
- **.5 option slug settles on blur**: the per-keystroke re-mint (which turned
  `c` into a sentence-long slug mid-typing, chip mutating under the cursor)
  now mints once when the label edit settles, with the bd-432u dependent
  retarget at the same settle point; the value chip moved out of the default
  option row into the author-tier Advanced disclosure.
- **.6 per-field error explanations**: checkFieldComplete no longer
  false-positives consolidated groups (per-option pdf_field_name counts as
  mapped; partial mapping names the unmapped options) and returns named
  review reasons; the field-list icon tooltips every reason; backend lint
  findings are lifted from the ValidationPanel (new `onReport` prop) through
  App into the list AND a "Why this field is flagged" banner in FieldEditor.

Assess/review outcome: fresh-eyes ran 3 rounds (Sonnet clear -> Opus found
the address_fields rename dangle, fixed inline + closed reviewer-filed bd
polyglot-pdf-8k7v -> Opus round 2 found the symmetric copy_from dangle,
fixed inline -> Opus round 3 NO-GAPS with an exhaustive kit-JSON
field-id-key enumeration). Outer review: two independent Opus passes both
NO-GAPS on the final diff. Adopt/reject/defer: 2 adopted (address_fields,
copy_from), 1 refuted (empty-string field_id can never reach the wire --
schema_lint.field_id_of returns None for falsy ids), 2 deferred as true
nits to bd polyglot-pdf-6hhc (WARNING-severity banner styling; selection
drop on undo-after-rename, a pre-existing pattern).

## Lessons

- A layout bug can masquerade as a scale-math bug: the overlay coordinate
  math was correct at every zoom; only the positioning CONTEXT diverged
  (centered canvas vs. wrapper-anchored overlay layer). No test asserted the
  two boxes coincide -- the new PDFViewer.overlayanchor test pins that
  contract directly.
- Type-level removal of a legacy key (8n2s) does not remove it from DATA:
  raw `response.json()` loads keep unknown keys and JSON.stringify re-saves
  them forever. A lint rule flagging a legacy shape needs a matching repair
  action AND a load-time migration, or old artifacts are permanently red
  with no UI recourse.
- Derived-on-every-keystroke join keys are hostile UX and churn references;
  mint identifiers when an edit SETTLES (blur/commit), not per change event.

## Doc freshness

`docs/components/schema-forms.md` reviewed: it documents runtime schema
consumption, not the editor UI or per-field help rendering -- left as-is.
No tier-1/tier-2 doc documents the removed instructions render or the
editor's status icons, so nothing to bump. CLAUDE.md untouched.

## Files touched

- schema-editor/src/utils/fieldRename.ts (+test) -- new: rename + retarget
- schema-editor/src/utils/schemaMigrate.ts (+test) -- new: load-time required migration
- schema-editor/src/utils/validation.ts (+test) -- consolidated-group mapping, reviewReasons
- schema-editor/src/utils/schemaLoader.ts / formKitDirectory.ts / remoteKitStore.ts -- migrate on load
- schema-editor/src/components/FieldEditor.tsx -- id header, problems banner, blur-mint, chip move (+metadata/optionslug/problems/rename tests)
- schema-editor/src/components/FieldList.tsx (+errorhints test) -- status tooltips, lint map
- schema-editor/src/components/ValidationPanel.tsx (+test) -- onReport mirror
- schema-editor/src/components/PDFViewer.tsx / PDFPage.tsx (+overlayanchor test) -- overlay anchoring
- schema-editor/src/components/PreviewPane.tsx -- no instructions render
- schema-editor/src/App.tsx (+App.rename.test) -- rename handler, lint lift
- schema-editor/src/types/schema.ts -- FieldStatus.reviewReasons
- frontend/src/schema-forms/components/fields/*.tsx (+instructions-not-rendered test) -- no instructions render
- frontend/src/schema-forms/styles/schema-form.css -- rule removed
- backend/services/schema_repair.py -- migrate-top-level-required action
- tests/test_schema_repair.py -- 5 new tests
