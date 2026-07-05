# W-9 -- the held-out evaluation form (bd polyglot-pdf-h76m.6, P2.2)

**This form is HELD OUT. Do not tune prompts, contracts, or repair rules
against it.** It exists so `scripts/authoring/eval_extraction.py` can measure
extraction quality on a form nobody optimized for. Committing a schema for it,
adding it to few-shot exemplars, or special-casing its widget names in any
pipeline code defeats its purpose (the epic exit gate runs on it precisely
because it is untouched).

- Source: IRS Form W-9 (Rev. March 2024), downloaded 2026-07-05 from
  https://www.irs.gov/pub/irs-pdf/fw9.pdf (public domain, fillable AcroForm).
- Shape: 6 pages, 23 widgets -- 15 text, 8 checkboxes.

## Flat-model fit check (done at SELECTION time, per the plan)

The epic's conditional model is ONE level of boolean structure
(`all_of/any_of/none_of` over atomic conditions -- no nesting). The W-9's
real-world logic all fits:

1. **Line 3a federal tax classification** -- seven checkboxes `c1_1[0]..c1_1[6]`
   (check exactly one). Notably they share the base name `c1_1` with DISTINCT
   on-values 1-7: the true-AcroForm radio-kid pattern (v2
   `FieldOption.pdf_on_value`), complementing W-7's opposite pattern (distinct
   names, all on-value "1"). Single-select semantics; no nesting.
2. **LLC classification code** (`f1_03[0]`) -- fill C/S/P only when the LLC box
   (`c1_1[3]`) is checked: one `includes`/membership condition. Flat.
3. **Line 3b foreign-partners checkbox** (`c1_2[0]`) -- applies only when 3a is
   partnership or trust/estate: `any_of` two membership conditions. Flat (one
   level, no cross-product).
4. Everything else (name, TIN, address, exempt codes) is unconditional text.

No "(A OR B) AND (C OR D)" cross-nesting exists anywhere on the form, so a
failure against the one-level ceiling cannot be blamed on the form -- the
epic-gate carve-out should stay empty here.

## Files

- `form.pdf` -- the blank form, byte-for-byte as downloaded.
- Deliberately NO `schema.json` (the manifest never serves this kit; a schema
  here would mean somebody tuned against the held-out form -- see above).
