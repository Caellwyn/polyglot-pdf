---
date: 2026-07-10
bead: polyglot-pdf-6cfu.2
title: "Integrate deterministic section derivation into extraction (extract_form.py + schema_contract)"
sprint: 10
tags: [extractor, testing]
---

## Trigger

Bead 2 of the deterministic form divisions epic (`polyglot-pdf-6cfu`, plan
`docs/sprint_10_deterministic-divisions_plan.md`). The 6cfu.1 prototype
(`derive_sections.py`) passed its go/no-go checkpoint (PR #392); this bead
wires it into the extraction pipeline so the LLM never decides section
boundaries again, and folds in the maintainer's checkpoint feedback
(2026-07-10): 'To review' gathering for unclear fields, balanced cap-splits,
and the amended cap policy (display-sanity ~40, not a validator constraint).

## What shipped

- **Pipeline step 3e** (`extract_form.py`): after positions are backfilled,
  families completed, and unclaimed widgets recovered,
  `derive_sections.derive_and_apply()` derives parts/sections from the PDF
  and OVERWRITES any LLM-emitted boundaries, re-filing every field's
  `section_id`. The division record (strategy, cap, to-review ids, notes)
  rides in `_bakeoff.authoring.division`. New `--division-cap` CLI flag.
- **Contract stops asking** (`schema_contract.py`): parts/sections/section_id
  removed from the TOP-LEVEL and FIELD shapes with an explicit do-not-emit
  rule; `render_example()` strips divisions from the prompt rendering while
  `CANONICAL_EXAMPLE` keeps them (FormSchema requires them to validate -- the
  sync test's guarantee). The few-shot exemplar (`arm_llm_native.build_fewshot`)
  no longer showcases section conventions either. Belt and braces: even a
  model that emits sections anyway is overwritten by step 3e.
- **'To review' sections** (`derive_sections.py`): name-pattern strays gather
  into per-page review sections and positionless fields into a pageless
  'To review (unplaced)' bucket, all under the well-known `sec_to_review` id
  prefix + a 'To review' part; ids recorded in the output's `to_review` block
  for the editor's review gate (bead 6cfu.3).
- **Balanced cap-splits**: `_balanced_chunks` targets ceil(total/cap) chunks
  of near-equal size at family-run boundaries (22 at cap 20 -> 11+11; f1040
  'Dependents' 42 at cap 40 -> 21+21), replacing greedy fill-to-cap (20+2).
  `DEFAULT_CAP` is now 40 per the amended cap policy.
- **6cfu.1 outer-review hardening**: `run()`/`derive_for_pdf()` close the
  fitz doc in a `finally` and raise a friendly `ValueError` on 0-page/corrupt
  PDFs; PDF-only field loading skips widget-less dump fields.
- **`_backfill_unclaimed_widgets` simplified**: no section filing (the
  `recovered_fields` bucket and `_section_for_page` are gone) -- recovered
  fields carry `section_id: ""` and step 3e re-files them.
- **Deferred decision noted**: parts group strictly by widget-name part
  number, so i-90's page-7 `P1_`-named re-entry fields make derived Part 1
  span pages non-contiguously -- mirrors the form's own naming; the related
  sub-heading-bleed limiter is bead `polyglot-pdf-h1eo` (already filed).
- Fresh-eyes assess loop + Opus outer review results are recorded in the PR
  and merge ping (this entry is written pre-review; gaps found there ship in
  the same PR).

## Lessons

- fitz cannot SAVE a zero-page PDF, so a 0-page guard has to be tested
  against an in-memory `fitz.open()` doc, not a file fixture.
- When a prompt contract and its validated canonical example must diverge
  (the example needs keys the model must not emit), render a stripped COPY
  for the prompt and pin both shapes in the sync test -- never weaken the
  validated object.

## Doc freshness

No tier-2 doc tracks `scripts/authoring/` / `scripts/bakeoff/` surfaces (the
only mention, `docs/components/config-deployment.md`'s subprocess note, is
still accurate). The stale docs `closeout_prep` flagged (voice/VAD, WS
protocol, terminology, etc.) all track backend/frontend files this branch did
not touch -- pre-existing staleness, left as-is. The sprint plan
(`docs/sprint_10_deterministic-divisions_plan.md`) already describes this
bead's design; no update needed.

## Files touched

- `scripts/authoring/derive_sections.py` -- cap 40 + balanced splits +
  To-review sections + schema-facing API (`fields_from_schema`,
  `derive_for_pdf`, `apply_to_schema`, `derive_and_apply`) + doc-handle/
  0-page/empty-widget hardening
- `scripts/authoring/extract_form.py` -- step 3e wiring, division metadata,
  `--division-cap`, simplified `_backfill_unclaimed_widgets`
- `scripts/bakeoff/schema_contract.py` -- do-not-emit divisions rule,
  stripped prompt example
- `scripts/bakeoff/arm_llm_native.py` -- few-shot exemplar drops divisions
- `tests/test_derive_sections.py` -- NEW: balanced splits, To-review,
  apply_to_schema, hardening guards
- `tests/test_extract_form_sections.py` -- NEW: real-kit integration (w7 +
  i-90), section stability, 1-based pages, FormSchema validity
- `tests/test_extract_form_backfill.py` -- section-filing pins updated to
  the derived world
- `tests/test_schema_contract_sync.py` -- stripped-example pins
