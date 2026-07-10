---
date: 2026-07-09
bead: polyglot-pdf-d9lz
title: "Reconcile the bake-off scorer (schema_score.py) to the v2 schema dialect"
tags: [schema-v2, bakeoff, tooling]
---

## Trigger

Surfaced by Codex review of PR #316 and confirmed in the 2026-07-09 bead audit.
After bd polyglot-pdf-h76m.4 rendered the extractor contract from the v2 registry
and bd polyglot-pdf-h76m.15 migrated the i-90 gold to v2 (`schema_version: 2`),
the bake-off scorer `scripts/schema_score.py` still graded in the v1 dialect --
so any arm run against the v2 contract got corrupted, pessimistic scores. The
maintainer (2026-07-06) gated the scorer reconciliation on h76m.15 landing rather
than shipping an interim dual-dialect scorer; h76m.15 has since closed, so this
is that reconciliation.

## The two v1-isms (verified against the migrated v2 gold)

1. **Option matching keyed on value first.** `_opts_match` built its comparison
   set as `value or label`. In v2 the option `value` is a semantic slug the
   extractor derives from the label (the i-90 gold now carries e.g.
   `yes_proceed_to_item_numbers_5_a_5_c`), so two correct extractions -- or the
   independently-slugged gold vs. an arm -- can hold DIFFERENT slugs for the same
   option and score as an option mismatch even when labels + pdf_field_names are
   identical.

2. **Two dead v1-legacy trigger-side keys in `rel_keys`.** The relationship-recall
   loop counted `conditional_fields` AND `controls_fields`. Both were deleted from
   the v2 FormField model at the P6.2 flip (form_models.py `_enforce_v2_rules`:
   "the trigger-side controls_fields / group_kind / conditional_fields fields have
   been deleted from the model"), both are lint-ERRORed as
   `legacy-trigger-side-logic` (schema_lint.py), and both are 0/0 across every v2
   gold kit (i-90, w7, w7-2, f1040) -- so a v2 arm can never emit them and they
   only diluted the conditionals table with dead buckets. The scorer also MISSED
   `require_if`, a live v2 target-side relationship key
   (populated 9/14/6 in w7/w7-2/f1040; 0 in i-90, which simply has no require_if
   relationships).

## What shipped

- `_opts_match`: key options on `label` first, `value` as fallback (bare-value
  options still match). Dialect-stable, since the label is the text both gold and
  every extraction derive verbatim from the PDF.
- `rel_keys`: dropped BOTH v1-legacy trigger-side keys `conditional_fields` and
  `controls_fields` (deleted from the v2 model, lint-ERRORed, 0/0 in every v2
  gold); added `require_if` (live v2 key). The remaining keys (`show_if`,
  `require_if`, `conditional_logic`, `conditional_behavior`, `copy_to`,
  `overflow_to_supplement`) are all live v2 model fields / tolerated aliases.
- Reconciled the coupling test `tests/test_schema_contract_sync.py`
  (`test_contract_advertises_every_scorer_graded_key`): removed `controls_fields`
  from its scorer-graded-key list to match the reconciled `rel_keys`.
- Module docstring updated to the v2 key list.
- New `tests/test_schema_score_v2_dialect.py`: label-first match incl. the
  divergent-slug recovery case, a wrong-label penalty (Jaccard bar still bites),
  the value fallback, and the v2 `rel_keys` vocabulary via a scored run.

## Scope / risk

NO CI, gate, runtime, or user exposure. `schema_score.py` is a manual bake-off /
authoring research harness (invoked by manual runs +
`test_schema_score_section_grouping.py` with its own fixtures). This only changes
what those manual experiment scores report. Full schema/score/contract/bakeoff
suite green (86 passed); the existing grouping tests are unchanged.

## Scar tissue

A scoring/eval harness silently inherits the OLD data dialect after a schema
migration: the gold and the contract moved to v2, but the scorer kept grading v1
option-values and a dead v1 relationship key, so it quietly mis-scored every v2
arm with no failing test to flag it. When migrating a schema dialect, audit the
EVAL harness (scorer, gold, fixtures) as an explicit migration step -- it has no
runtime signal to catch the drift. Cross-ref bd polyglot-pdf-h76m.15 (gold
migration), the v2 relationship vocabulary in `backend/models/form_models.py`.
