---
date: 2026-09-08
bead: polyglot-pdf-q63ye
title: "chore(select): retire the three select carve-outs -- every choice type carries identity the same way"
tags: [schema, lint, repair, form-kits, testing]
---

## Trigger

PR 3b, the last of the g2fpr epic (`polyglot-pdf-ps4hf`). PR 1 taught the
filler to write a dropdown's `pdf_on_value`; PR 2 taught the writers to
produce it; PR 3c protected sessions; PR 3a migrated the maintainer's kit
(267 options, run by the maintainer on 2026-09-08). With no kit left in the
old shape, the three places that restated "a dropdown's value IS the PDF
export code" could go: `schema_lint._check_options` (the 4we6j `/Opt`
exemption in the slug rule), `schema_repair._mint_slugs` (the "preserve a
sanctioned code" branch) and `form_models._collect_v2_problems` (the model
gate's select exemption).

## What shipped

- Lint: the slug rule applies to every choice type with no dropdown
  exemption; the two channel rules collapse to one statement -- every dropdown
  choice carries a `pdf_on_value` the PDF declares -- so a choice lacking one
  is an ERROR with a dump present whatever its value looks like (exit
  criterion 2). The former `select-value-not-slug` rule was the slug rule
  restated for the code-in-both shape; retired with the carve-out. Every
  remedy that meets the pre-migration shape names the migration tool.
- Repair: a sanctioned code in a dropdown's value is CONVERTED (code into
  `pdf_on_value`, value minted with the shared select minter), the per-field
  version of the migration; the empty-value hold-aside (ot284) stays.
- Model gate: selects follow the slug rule; the 422 names the migration.
- The kit-driven render guard (`test_pdf_fill_dropdown_export_codes.py`)
  named a `schema_edited.json` the kit never had and had skipped for months
  (bd eeyqg); it now reads `schema.json`, asserts the CODE prints, and runs
  the whole publish gate in route order on the migrated kit -- exit
  criterion 1, measured on the real thing.
- The G1b answer key resolves a state through `pdf_on_value` (bd bxjck).

## Lessons

**The exit criterion was measurable on the real kit, so measure it there.**
The kit ships an acroform dump; `lint_schema(migrated, dump)` gave zero
ERRORs and `model_validate` passed before the change (the migration's doing)
and after (the retirement's). A synthetic fixture would have proven the rule;
the real kit proves the kit.

**A skipped guard reads as green.** Six tests had skipped on every machine
since the kit was renamed; fixing the filename turned them into six real
runs, one of which caught a quarantine artefact (a `show_if` naming another
quarantined field) that had nothing to do with dropdowns -- the assertion is
now scoped to the option rules it was written to guard.

**Retiring a carve-out means retiring the rule that restated it.** The
code-in-both rule existed only because the slug rule had an exemption to
work around; once the exemption went, keeping the rule would have doubled
every finding. The registries (backend header, editor labels and remedies)
and the parity test moved together.

**Two findings with one fix is fine; two findings with opposite fixes is
not.** A pre-migration option now gets both a slug-rule finding and a
channel finding; both name the migration. The old shape had one finding
saying "do NOT regenerate" beside another saying "regenerate" -- that is the
contradiction, not the count.

## Files touched

- `backend/services/schema_lint.py`, `backend/services/schema_repair.py`,
  `backend/models/form_models.py` -- the three retirements
- `schema-editor/src/utils/lintFindings.ts` -- retired rule label/remedy
- `backend/scripts/g1b_answer_key.py` -- state resolves through `pdf_on_value`
- `backend/tests/test_schema_lint.py`, `backend/tests/test_form_models_v2.py`,
  `tests/test_schema_repair.py` -- pins flipped to the new contract
- `backend/tests/test_pdf_fill_dropdown_export_codes.py` -- the guard runs
- `backend/tests/unit/test_g1b_state_resolution.py` (new)
- `backend/tests/unit/test_select_on_value_consumers.py` -- verdicts
- `docs/components/pdf-filling.md`
