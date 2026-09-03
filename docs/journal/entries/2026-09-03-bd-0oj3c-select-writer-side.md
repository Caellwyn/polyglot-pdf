---
date: 2026-09-03
bead: polyglot-pdf-0oj3c
title: "feat(authoring+editor): selects are written in the v2 shape -- slug value, export code in pdf_on_value"
tags: [authoring, schema-editor, prompt, testing]
---

## Trigger

PR 2 of five under epic `polyglot-pdf-ps4hf`. PR 1 taught the filler and the
preview to READ a select's `pdf_on_value`; nothing yet WROTE it. The extractor
still emitted `{value: code, label}`, the editor still authored the export code
into `option.value`, and the extraction prompt still told the model a select
condition names the code. This makes the three writers agree with the reader.

## What shipped

- `conditional_vocabulary.mint_select_slugs` / `strip_trailing_code` (Python)
  and `fieldGrouping.mintSelectSlugs` / `stripTrailingCode` (TypeScript): ONE
  definition each side of the two select-only minting rules -- a label's
  trailing `(CODE)` is stripped (`'Alabama (AL)'` -> `alabama`, not
  `alabama_al`), and a code that is already a valid slug (`'5'`) IS the value.
  Kept codes are reserved before minting so a sibling cannot collide.
- `extract_form._backfill_dropdown_options` writes
  `{value: slug, label, pdf_on_value: code}`, minted over the whole option set;
  `prior_labels` is keyed on the CODE so a kit already in the v2 shape keeps
  its labels on re-run.
- `schema_contract.py`: the skeleton, the CHOICE-FIELD rule and the
  condition-reference rule say slug-in-value, code-in-`pdf_on_value`.
- `FieldEditor.tsx`: the select mint skip is retired (its comment named this
  bead); the "PDF export code" input is bound to `pdf_on_value`; both "+ Add
  Option" sites mint a slug. Editing the code no longer retargets dependents --
  the slug they reference is unchanged -- so `codeBeforeEditRef` and its
  focus/first-keystroke dance are gone.

## Lessons

**The (CODE) strip is a rule, not a nicety, and it has to live in one place
per language.** `mint_option_slug('Alabama (AL)')` is `alabama_al`. Three
writers (extractor, editor, the coming migration) would each have restated the
strip; the Python helper and the TypeScript helper share fixtures so they
cannot drift apart unnoticed.

**A numeric code is already a slug, and the extractor test cannot prove it.**
`mint_select_slugs(['5'], ['5'])` yields `'5'` whether the code is KEPT or
MINTED from the label `'5'` -- the two paths agree by coincidence. Only the
unit test with a reworded label (`'five feet'` with code `'5'` -> `'5'`)
carries the property. A mutation that reddens one test and not the other is
telling you which test holds the invariant.

**When a contract inverts, its pin inverts with it.** The prompt test pinned a
three-place CARVE-OUT ("for a select this rule does NOT apply"). The new
invariant is the opposite: any passage naming a select's export code must say
it lives in `pdf_on_value`. Rewritten as a scan with three needles, and
mutated three ways -- including one that left `pdf_on_value` in the same
sentence chunk and so proved only the needle, not the scan; a second mutant
that removed it from the chunk was needed to prove the scan bites.

**Ten extractor tests and ten editor tests pinned the old shape, correctly.**
They were not wrong when written; they were the contract. Flipping them was
mostly `o["value"]` -> `o["pdf_on_value"]` where the property was "which PDF
codes were written", plus new-shape assertions for the slug side.

**A non-parsing mutant proves nothing -- again.** MUT C's first anchor matched
twice, the fallback mangled the file, and vitest reported "1 failed, 15
passed" -- the FILE failed to compile and the number looked like a result.
Redone with a valid expression and `tsc` on the mutant before trusting it.

## Files touched

- `backend/models/conditional_vocabulary.py`, `schema-editor/src/utils/fieldGrouping.ts`
- `scripts/authoring/extract_form.py`, `scripts/bakeoff/schema_contract.py`
- `schema-editor/src/components/FieldEditor.tsx`
- tests: extractor, prompt, editor (rewritten), two minter unit files, consumer pin
