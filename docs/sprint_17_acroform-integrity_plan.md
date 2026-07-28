# Sprint 17 -- AcroForm integrity: field<->widget invariant, truthful editor, ignore escape hatch

*Plan of record for epic `polyglot-pdf-did2`. Maintainer-approved 2026-07-27.
Sprint plans are a chronological record, exempt from current-state-only.*

## Why

The maintainer's W-7 verification was blocked by apparent "phantom signature
fields". Forensics reversed the premise: the fields are LLM LABELING errors
bound to REAL widgets (`applicant_signature` actually claims the applicant
phone widget `f1_40[0]`; `agent_signature` the agent printed-name widget
`f1_44[0]`; the W-7's true signature lines carry no AcroForm widgets -- they
are pen-ink lines). The only publish blocker on the kit was missing
`extraction_info` (its 2026-07-02 CLI extraction predates provenance stamping
-- and the modern pipeline stamps none either, so every future extraction has
the same mark-complete failure). The editor compounded the confusion by
rendering un-reviewed auto-complete fields green and giving unlocatable claims
a false error message.

**Maintainer priority hierarchy (their framing):**

- **MUST-FIX: every field shown in the editor is linked to an actual widget.**
  A widget-less field is not human-fixable at all.
- **Inevitable + human-fixable: LLM labeling errors** (a nearby real widget
  tagged with the wrong apparent label). Improving label-to-widget linking is
  nice-to-have, OUT of this sprint.
- **Escape hatch, not primary tool: the Ignored status** (leaves cruft; the
  invariant should make it rare).

Direction: fix the pipeline FIRST; the maintainer re-extracts W-7 through the
corrected pipeline and verifies it (accepting the loss of current hand-edits).
Also directed: un-reviewed renders AMBER even when automatically complete --
green is reserved for human sign-off.

## Exit rubric

| # | Criterion | Verify |
|---|-----------|--------|
| 1 | Pipeline deterministically correct for AcroForm: source=pdf extraction hard-fails (RepairError, never silent-drop) on an unresolvable claim, an unbacked non-exempt-type field, or a post-backfill unclaimed fillable widget; every extraction stamps honest `extraction_info` and persists its dump. No type==widget-kind equality; no naive count checks. | Unit tests per defect class; fixture extraction carries extraction_info + acroform.json; i-90 lints 0-ERROR; **the maintainer re-extracts W-7 and accepts.** |
| 2 | A hand-edited draft cannot sneak an unbacked field past publish: lint ERRORs `field-unbacked` (schema-only) + `field-claim-unresolvable` (dump-gated; the /lint route's dump-lessness stays the accepted asymmetry). | Lint unit tests both branches; publish-gate 409 test; i-90 stays 0-ERROR. |
| 3 | Editor truth: un-reviewed renders AMBER everywhere (list icon, PDF overlay, counts) even when auto-complete -- green only on human sign-off; unlocatable claims name the widget plainly (never the false "Missing PDF field name"); page-out-of-range gets its own distinct reason. | Vitest pins across all three surfaces + both message texts; live eyeball. |
| 4 | Ignored (grey) escape hatch: confirmation-gated; refused while required or referenced (7 reference surfaces); grey group; stops counting everywhere; survives save->reload; un-ignore restores exactly (orphan fallback). | Vitest suite (gates, round-trip, restore-exactness, undo) + hand-drive. |

## Bead tree (each child = one bead = one PR; MECE surfaces)

| Bead | Child | Inherits | Surfaces |
|------|-------|----------|----------|
| `polyglot-pdf-l1a9` | C1 pipeline ledger + extraction_info stamping (P1, FIRST) | 1 | backend/services/schema_repair.py, scripts/authoring/extract_form.py, backend/tests/ |
| `polyglot-pdf-xazf` | C2 publish-gate lint rules (P1; may bundle into C1's PR) | 2 | backend/services/schema_lint.py, backend/tests/ |
| `polyglot-pdf-g63j` | C3 truthful display: amber-until-reviewed + accurate messages (P1) | 3 | schema-editor/src/utils/{reviewStatus,validation,pdfCoordinates}.ts, components/{FieldOverlay,PDFViewer}.tsx |
| `polyglot-pdf-mzkw` | C4 Ignored quarantine escape hatch (P2, LAST; blocked by C3) | 4 | schema-editor/src/utils/ignoreField.ts (new), components/{FieldEditor,FieldList}.tsx, types/schema.ts, App.tsx |

Execution order: C1 (+C2) -> **maintainer W-7 re-extraction checkpoint** -> C3
-> C4. C1/C2 (backend) are parallelizable with nothing; C3/C4 are editor-only
and sequenced (C4 blocked by C3 -- both touch status rendering).

Superseded beads: `polyglot-pdf-emap` closed into C1+C2;
`polyglot-pdf-nkqm` closed into C3+C4 (its uncommitted validation.ts draft in
worktree `nkqm-phantom-ignore` folds into C3).

## Out of scope

- Improving LLM label-to-widget linking quality (tooltip-vs-semantics
  heuristics, prompt grounding) -- maintainer-classified nice-to-have.
- ExtractionInfo model changes (unknown-confidence sentinel) -- documented
  0.0 convention instead.
- Fixing the /lint route's structural dump-lessness (accepted asymmetry).
- Delete-field capability (barred). OCR / non-AcroForm extraction modes.
- bd z3rs's translation-coverage-quality work (separate, in flight).
