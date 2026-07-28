---
date: 2026-07-27
bead: polyglot-pdf-l1a9
title: "Sprint-17 C1+C2: extraction-time field<->widget ledger, extraction_info stamping, publish-gate lint backstop"
tags: [extraction, pipeline, editor]
---

> This PR bundles C1 (bd polyglot-pdf-l1a9) and C2 (bd polyglot-pdf-xazf) --
> the plan explicitly left the bundling call to the executor; both are small,
> share the exemption constant, and together arm the maintainer's W-7
> re-extraction checkpoint (pipeline fails loudly at birth; the publish gate
> catches hand-edits later).

## Trigger

Epic polyglot-pdf-did2 (sprint 17, plan: docs/sprint_17_acroform-integrity_plan.md).
The maintainer's W-7 "phantom signature fields" turned out to be LLM labeling
errors bound to REAL widgets, and the actual publish blocker was a missing
extraction_info stanza -- with NO modern writer for that stanza anywhere (only
the retired prior_extractor stamped placeholders). Maintainer's must-fix: every
field shown in the editor is linked to an actual widget; fix the pipeline first,
then they re-extract W-7 and verify.

## What shipped

- `backend/services/schema_repair.py`: `FIELD_LEVEL_NAME_EXEMPT_TYPES`
  (select/radio/checkbox_group/table/address_group -- identity lives per-option/
  column/slot; table+address_group are enumerated-but-unverified, zero real
  instances) + `_check_no_name_non_choice`: a source=pdf field outside that set
  with NO pdf_field_name raises RepairError (same fail-loud contract as the
  hallucinated-widget check). Runs AFTER checkbox-shape normalization so the
  lone-option-checkbox name lift is not a false positive. type=signature is
  deliberately NOT exempt (the deterministic dump maps real signature widgets
  to `text`; a signature-typed field is always an LLM inference).
- `scripts/authoring/extract_form.py`:
  - `_stamp_extraction_info` (+`EXTRACTOR_VERSION = "extract_form-v1"`): every
    extraction now stamps extracted_at (UTC ISO), extraction_confidence 0.0
    (documented "not a measured quantity" convention -- the model has no unknown
    sentinel and changing it is out of scope), extractor_version, and
    manual_review_required=True. Stamped before validate so the validated
    artifact is the stored artifact. This closes the publish gate's 422 for
    every future extraction.
  - `_check_dump_coverage`: post-backfill, every fillable dump widget (lint's
    is_fillable_widget semantics) must be claimed by some field/option (lint's
    exact-or-dot-suffix _match_dump_names -- one convention, no drift). Anything
    unclaimed after `_backfill_unclaimed_widgets` means the pipeline itself
    failed: COVERAGE-FAILED on stderr + an authoring.coverage provenance record.
  - `_classify_exit`: a repair-FAILED draft or a coverage gap now classifies
    EXIT_ISSUES. Pre-existing gap closed in passing: a RepairError-degraded
    draft (hallucinated widgets) with passing Pydantic and 0 lint ERRORs
    previously exited 0 VALID -- invisible to the tri-state.
- Verified (no change needed): the editor extract route persists acroform.json
  (v96b) and consumes exit 3 as storedWithIssues -- so a phantom-carrying draft
  now surfaces as stored-with-issues in the catalogue instead of clean.

## Tests

- `tests/test_schema_repair.py`: +4 (no-name text+signature raise; exempt types
  pass; non-pdf skipped; lone-option lift not a false positive). Ten existing
  fixtures used name-less `dep` text scaffolding -- now themselves the defect
  the new check catches; named them (`dep[0]`) rather than weakening the check.
- `tests/test_extract_form_ledger.py` (new): coverage (unclaimed reported;
  option + dot-suffix claims resolve; buttons/barcodes excluded; no dump = no
  signal), stamping (model_validate accepts the stanza), exit classification
  (repair-failed -> ISSUES; coverage gap -> ISSUES; clean -> VALID; empty ->
  HARD_FAIL).
- Full pytest (-m "not external") green.

## C2 (bundled): publish-gate lint backstop

- `backend/services/schema_lint.py`: `_check_field_backing` at the
  _check_dump_claims call site. `field-unbacked` (ERROR, schema-only, fires
  dump-less): a source=pdf field outside the shared exemption set naming no
  widget at all. `field-claim-unresolvable` (ERROR, dump-gated): a field/option
  claim resolving to zero dump widgets -- the case register() silently drops,
  which is exactly how the original phantom confusion stayed invisible. The
  /lint route's dump-lessness stays the accepted dump-* asymmetry (documented
  in the rule docstring); mark-complete (which loads the kit dump) enforces.
  Imports FIELD_LEVEL_NAME_EXEMPT_TYPES from schema_repair (cycle-safe;
  single source, no drift).
- Tests: `backend/tests/test_schema_lint.py` +6 (unbacked fires dump-less /
  exempt types / non-pdf skip; unresolvable fires with dump + genuinely silent
  without + option-level path). Fixture updates: name-less `dep` text
  scaffolding in tests/test_extract_form_lint.py named (same rationale as the
  repair-test fixtures -- the scaffolding itself became the defect).

## Closeout notes

- Doc-freshness: every STALE doc flagged by prep is a backend/frontend doc
  stale vs OTHER recent dev commits (config.py, live_ai_gemini.py et al.) --
  none cites this branch's touched files (docs/components/pdf-filling.md, the
  nearest surface doc, reads OK). No doc update owed by these beads.
- Beads audit: one stale in_progress bead, polyglot-pdf-btbi (W-7 require_if
  residuals) -- the MAINTAINER's own claim, possibly superseded by their
  decision to re-extract W-7 through the fixed pipeline; flagged for their
  call in the merge ping, not transitioned unilaterally.
- Review tiers: Opus subagent spawns 400 in this session (model-config:
  effort/thinking mismatch on the session's Fable setting) -- the strong-model
  clearing passes ran on the available decision-gate tier instead, disclosed
  in the PR.

## Deferred / relies on siblings

- The maintainer's W-7 re-extraction is the epic's criterion-1 acceptance gate.
- C3/C4 (editor truth + Ignored escape hatch) follow as separate PRs.
- polyglot-pdf-hj6w (fresh-eyes filed): table/address_group sub-claims never
  register in the dump walks -- will matter the first time either type
  appears with real widgets.
