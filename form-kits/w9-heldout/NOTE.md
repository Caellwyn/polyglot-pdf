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
(`all_of/any_of/none_of` over atomic conditions -- no nesting). Verdict:
**fits, with ONE documented exception** (line 3b below) whose flat
approximation is fail-open and which cannot make the epic gate unmeetable --
the gate scores lint cleanliness and fill success, and `show_if` is optional
metadata, so no extraction is forced into invalid output by this form.

Widget-to-label mapping (verified against the PDF's widget rects + page
text, fresh-eyes round 1 -- an earlier draft of this note had LLC wrong):

| widget    | label                        |
|-----------|------------------------------|
| c1_1[0]   | Individual/sole proprietor   |
| c1_1[1]   | C corporation                |
| c1_1[2]   | S corporation                |
| c1_1[3]   | Partnership                  |
| c1_1[4]   | Trust/estate                 |
| c1_1[5]   | LLC (enter classification)   |
| c1_1[6]   | Other (see instructions)     |
| c1_2[0]   | Line 3b foreign-partners box |

1. **Line 3a federal tax classification** -- seven checkboxes `c1_1[0]..c1_1[6]`
   (check exactly one). They share the base name `c1_1` with DISTINCT
   on-values 1-7: the true-AcroForm radio-kid pattern (v2
   `FieldOption.pdf_on_value`), complementing W-7's opposite pattern (distinct
   names, all on-value "1"). Single-select semantics; no nesting.
2. **LLC classification code** (`f1_03[0]`) -- fill C/S/P only when the LLC box
   (`c1_1[5]`) is checked: one membership condition. Flat.
3. **Line 3b** (`c1_2[0]`) -- THE ONE EXCEPTION. The form's own instruction
   text gates it on: checked "Partnership", OR checked "Trust/estate", OR
   (checked "LLC" AND entered "P" as its classification). That last disjunct
   is a conjunction inside a disjunction --
   `any_of(partnership, trust_estate, all_of(llc, code=P))` -- one level
   DEEPER than the flat model can express. Recorded here as evidence for a
   future nesting extension (the epic exit gate's carve-out anticipates
   exactly this file). The acceptable flat approximation is
   `any_of(partnership, trust_estate, llc)`: it over-SHOWS the 3b box for
   C/S-classified LLCs (fail-open -- the printed instructions tell those
   filers it does not apply), never hides it from someone who needs it.
4. Everything else (name, TIN, address, exempt codes) is unconditional text.

No "(A OR B) AND (C OR D)" cross-product nesting exists on the form; the 3b
case above is the only structure beyond one level.

## Files

- `form.pdf` -- the blank form, byte-for-byte as downloaded.
- Deliberately NO `schema.json` (the manifest never serves this kit; a schema
  here would mean somebody tuned against the held-out form -- see above).
