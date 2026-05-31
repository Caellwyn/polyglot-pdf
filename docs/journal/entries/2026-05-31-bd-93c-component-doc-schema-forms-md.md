---
date: 2026-05-31
bead: polyglot-pdf-93c
title: "Schema-forms + PDF-filling component docs (93c + 2yu)"
tags: [conventions]
---

# polyglot-pdf-93c (+2yu): schema-forms + pdf-filling component docs

A two-doc batch for the docs-reorg epic (`polyglot-pdf-gfb`), covering the
form-state + PDF-export surfaces. Paired because they share the form-kit /
field-type material and the FieldValue-unwrap seam between them.

## Trigger

Next gfb batch after the voice/WS/AI spine (#32). Both surfaces were `_(planned)_`
in INDEX. Read every source file fully before drafting (the deliberate response to
the voice batch, where I shipped fabrications that two fresh-eyes passes had to
catch).

## What shipped

Two new tier-2 component docs, verified line-by-line against dev code, + the two
`docs/INDEX.md` rows flipped from `_(planned)_` to live links:

- **components/schema-forms.md** (93c) — `SchemaFormStateManager` over the single
  `schema_form_state` sessionStorage key; the `FieldValue` wrapper and the
  unwrap-before-PDF rule; the `schemaFormStateChange` event vs the silent `clear()`;
  section-based nav + the parts→sections load-time migrations; `FieldRenderer`'s 6
  implemented field types (+ number) vs the 3 stubs (signature/address_group/table);
  conditional `show_if` + `flip_readonly_bit` unlock; `copy_to`; manual-edit
  auto-confirm. Flags the **`ai_voice`/`manual_edit` (frontend) vs `verbal`/`manual`
  (backend)** confirmation-method vocabulary split.
- **components/pdf-filling.md** (2yu) — the stateless `/api/fill-pdf` flow; PyMuPDF
  fill by type; the scar tissue: **must pass the page that contains the widget**
  (weak-ref → re-fetch fresh widget), XFA exact-then-`endswith` path matching, XFA
  checkboxes set `field_value`+`/AS` without `update()`, `need_appearances`
  intentionally off, and `apply_field_flag_changes` unlocking read-only widgets
  (the PDF-side `flip_readonly_bit`). Form-kit store local-vs-GCS via
  `FORM_KITS_MODE`. Absorbs `DEBUG_PDF_FILLING.md` as the debug runbook.

Fresh-eyes triage: _(filled at closeout)_.

## Lessons

- **Read the whole surface first.** Reading `schemaFormState.ts`, `types/schema.ts`,
  `FieldRenderer`, the fill route, and `form_kits.py` in full *before* writing meant
  the concrete claims (field-type stub list, the XFA "set-don't-update" checkbox
  path, the two confirmation vocabularies) came straight from code, not memory.
- **Cross-surface vocabulary drift is worth calling out explicitly.** The
  `ai_voice`/`manual_edit` vs `verbal`/`manual` split is exactly the kind of thing
  a reader would get wrong; the doc names both sides.

## Doc freshness

Both new docs: freshness OK; `tests/test_doc_freshness.py` 38 passed; conventions
clean. `technical_guide.md` STALE is pre-existing (owned by `polyglot-pdf-gfb.2`),
not touched here.

## Files touched

- `docs/components/schema-forms.md` — new (93c)
- `docs/components/pdf-filling.md` — new (2yu)
- `docs/INDEX.md` — two component rows → live links
- `docs/journal/entries/2026-05-31-bd-93c-...md` — this entry
