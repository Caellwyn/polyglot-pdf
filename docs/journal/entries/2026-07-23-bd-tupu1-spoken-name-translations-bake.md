---
date: 2026-07-23
bead: polyglot-pdf-tupu.1
title: "feat(i18n): field spoken_name_translations -- schema field, bake extension, full 4-kit backfill (epic tupu step 1)"
tags: [extractor, conventions, testing]
---

## Trigger

Epic polyglot-pdf-tupu (sprint 13, maintainer-approved 2026-07-22): non-English
sessions hear ENGLISH field names ("uscis online account number" read aloud in
the es assessment run) because the model's per-field guidance carries English-
only spoken names. Step 1 creates the data: per-field translations in the kit
schemas, mirroring the proven option label_translations pipeline (ow1e/2h9j).

## What shipped

- `spoken_name_translations: Record<lang-name, string>` on the FIELD dict --
  canonical lowercase language-name keys, identical convention to option
  label_translations. Added to the FormField Pydantic model and both TS type
  files (frontend + schema-editor; editor tsc green).
- The shared bake (`option_translation.py::bake_label_translations`) now also
  collects field spoken names (falling back to `name`, the same fallback
  `get_field_guidance` renders) and translates the UNION of missing labels +
  names in ONE batched call per language -- the one-call-per-language pin the
  bake tests enforce survives. Fan-out writes canonical keys with the same
  only_missing/idempotency/failure-skip semantics; report gains additive keys
  (spoken_names / names_missing / names_translated / fields_updated). All
  three call sites (CLI, extraction step 3f, editor route) inherit the
  extension unchanged; the CLI --check now counts name gaps.
- Backfill: all 4 kits x all code-backed languages -- f1040 176 names, i-90
  132, w7 59, w7-2 59, each x17 languages. Verify pass: "fully covered" on
  all four; a second run makes zero model calls (idempotency proven live).
- Tests: 3 new bake pins (union single call + fan-out incl. name-fallback
  fields; idempotency + alternate-key coverage; failure-skip + gap re-fill).
  Full backend suite 1175 passed; frontend 1032; editor tsc clean.

## Lessons

- The one-batched-call union pattern let spoken names ride the existing
  per-language call at zero marginal call count -- the whole 4-kit x 17-lang
  backfill was one CLI run per kit.

## Doc freshness

docs/schema_format.md section 11 updated: spoken_name_translations documented
with example, supported-language count corrected to 18. Component docs
unaffected (runtime delivery is tupu.2's surface).

## Files touched

- backend/services/option_translation.py (collect/iter helpers + _bake_one
  union + field fan-out)
- backend/models/form_models.py (FormField.spoken_name_translations)
- scripts/authoring/translate_option_labels.py (check counts + print columns)
- schema-editor/src/types/schema.ts, frontend/src/schema-forms/types/schema.ts
- form-kits/{f1040,i-90,w7,w7-2}/schema.json (backfill)
- backend/tests/unit/test_option_translation_bake.py (+3 pins, report-shape
  update)
- docs/schema_format.md + this entry
