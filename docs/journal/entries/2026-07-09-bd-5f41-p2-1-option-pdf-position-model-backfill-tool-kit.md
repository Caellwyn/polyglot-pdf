---
date: 2026-07-09
bead: polyglot-pdf-5f41
title: "P2.1: option pdf_position -- model + backfill tool + kit schemas + JIT option sanitizer"
sprint: 9
tags: [conventions, testing]
---

## Trigger

First bead of the sprint-9 editable-Preview epic (`polyglot-pdf-oaiz`, plan
`docs/sprint_9_editable-preview_plan.md`). Preview mode paints radio /
checkbox_group selections as labels at the FIELD-level rect because
`FieldOption` carried no rect of its own; painting a mark at each selected
option's printed box (epic rubric R1, executed by P2.2) needs per-option
`pdf_position` in the kit schemas first. The AcroForm dump already records
every widget's rect and on_value, so the backfill is purely mechanical.

Session note: the original builder subagent died mid-bead on an API auth
error (401) after landing the model field, the extract_form.py extension, and
most tests; the orchestrator picked the work up from the tree, verified it,
fixed three wrong test expectations, and finished the remaining surfaces.

## What shipped

- `FieldOption.pdf_position: Optional[PDFPosition]`
  (`backend/models/form_models.py`) -- same shape as `FormField.pdf_position`.
- `extract_form._backfill_positions` extended to options[] (one shared
  implementation, per the plan): suffix-aware name lookup (reuses
  `schema_lint._match_dump_names` -- i-90 alone has 32 option names that only
  resolve as leaf suffixes), `pdf_on_value` disambiguation for multi-widget
  groups, the documented shared-field-name radio shape, and an
  unmatched-report instead of guessing. Returns
  `{fields_filled, options_filled, unmatched}`; the `_bakeoff.authoring`
  provenance keeps `positions_filled` as the historical int and adds
  `option_positions_filled` / `option_positions_unmatched`.
- **Dropdown rule** (found by running against real kits): a shared-name group
  whose widgets carry NO on_value is a combobox/listbox (i-90's height
  selects), where options are choice values of one widget, not printed boxes
  -- silently skipped, not unmatched. Without this the i-90 check reported 19
  false unmatched.
- Field-level lookup became suffix-aware as a side effect (strict superset of
  the old exact-name match): i-90 gained its 4 previously-unpositioned
  radio-group fields (ethnicity/race/eye/hair), and w7-2 gained all 61 field
  rects -- its committed schema had ALL-degenerate (0,0,0,0) positions because
  its leaf-name claims never matched the old exact lookup. w7-2 Preview
  overlays render for the first time.
- New `scripts/authoring/backfill_option_positions.py`: standalone CLI over
  the same implementation (`--kit` / `--schema`+`--pdf`, `--check`,
  idempotent, in-memory `acroform_dump.dump_pdf`, ASCII-safe writes). Exit
  codes: 0 clean / 1 check-found-patchable / 2 unmatched.
- Kits patched: i-90 (70 options + 4 fields), f1040 (24), w7 (13), w7-2
  (13 + 61 fields). `--check` exits 0 on all four after patching (R2
  evidence); all four still validate under `FormSchema.model_validate`.
- JIT option sanitizer: `manifest_service.get_next_field_schema` now strips
  option dicts to `value`/`label`/`spoken_label` -- `pdf_field_name`,
  `pdf_on_value`, `pdf_position`, `label_translations` never reach the
  (default-off) JIT `confirm_field` tool response (epic rubric R5 half).
- Tests: 34 in `tests/test_extract_form_backfill.py` (option join, on_value
  disambiguation, shared-name shape, dropdown skip, idempotence, unmatched
  reporting) + the sanitizer test in
  `backend/tests/unit/test_manifest_service.py`. Full backend suite green
  (1729 passed).

Review record: fresh-eyes round 1 (Sonnet) found the branch was based one
commit behind origin/dev, silently reverting PR #355's i-90 p2_checkbox3
fix -- fixed by rebasing and re-running the backfill (the restored 5 options
got their own rects); round 2 (Opus) NO-GAPS. Opus outer review: round 1's
second confirming pass caught the sanitizer crashing on bare-string options
(AttributeError; the pre-sanitizer pass-through tolerated them) -- fixed with
an isinstance guard + test; round 2, both independent Opus passes NO-GAPS on
the final diff. Adopted 2 findings inline, deferred 1 as bead
polyglot-pdf-lj5v (get_field_guidance option-sanitizer parity), FE type sync
already owned by P2.2 polyglot-pdf-lp5v.

## Lessons

- **Run new mapping code against the real kits before trusting the design.**
  The dropdown rule was invisible in the plan and the synthetic tests; the
  first real `--check` run on i-90 surfaced 19 false unmatched. Synthetic
  fixtures pin behavior; real data finds the missing rule.
- **A "0 backfilled" provenance count is a symptom worth chasing.** w7-2
  shipped with `positions_filled: 0` and 61 degenerate rects -- nobody chased
  it because the kit "worked" (list view does not need rects). The suffix-
  aware unification fixed it for free.
- **Inherited-work verification pays.** The dead subagent's tests encoded
  three wrong expectations (asserting the field-level pass would NOT fill from
  option widgets -- contradicting the documented pre-existing convention);
  verifying implementation-vs-test against the documented behavior caught
  them.

## Doc freshness

- `docs/components/jit-schema.md` -- added the option-sanitizer note to the
  per-confirm tool-response section; bumped.
- `docs/standards/terminology.md` -- checkbox_group / radio rows now mention
  per-option `pdf_position`; bumped.
- Reviewed and left: `docs/standards/risk-rating.md` (additive presentation
  field, no risk-tier impact), `docs/standards/si-reduction.md` (the
  sanitizer trims a default-off tool-response path, not the SI),
  `docs/components/pdf-view.md` (painting behavior unchanged until P2.2).
  All other docs flagged by the freshness gate track files this branch did
  not touch (stale before this branch).

## Files touched

- backend/models/form_models.py -- FieldOption.pdf_position
- backend/services/manifest_service.py -- JIT option sanitizer
- backend/tests/unit/test_manifest_service.py -- sanitizer test
- scripts/authoring/extract_form.py -- option-level backfill join
- scripts/authoring/backfill_option_positions.py -- new standalone CLI
- tests/test_extract_form_backfill.py -- option backfill tests (+3 fixed)
- form-kits/{i-90,f1040,w7,w7-2}/schema.json -- backfilled positions
- docs/sprint_9_editable-preview_plan.md, docs/INDEX.md -- sprint-9 plan filing
- docs/components/jit-schema.md, docs/standards/terminology.md -- doc bumps
