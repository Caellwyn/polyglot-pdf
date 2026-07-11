---
date: 2026-07-11
bead: polyglot-pdf-6cfu.3
title: "Schema editor section management: add/rename/merge/remove, regenerate divisions, and the To-review publish gate"
tags: [schema-editor, extractor]
---

## Trigger

Sprint 10 (epic `polyglot-pdf-6cfu`): with divisions now derived
deterministically at extraction (6cfu.2), the editor needed (a) manual
section management for the cases derivation gets wrong -- maintainer-directed
add/remove/merge/rename on top of the existing reassign-field dropdown; (b) a
"Regenerate divisions" action re-running the derivation on the stored kit;
and (c) the maintainer's checkpoint requirement: fields in `sec_to_review*`
sections must be HIGHLIGHTED and re-filing them must be REQUIRED before a
form can be marked complete -- a hard gate, not a suggestion.

## What shipped

- `schema-editor/src/utils/sectionOps.ts` -- pure section ops returning one
  atomic `{fields, sections, parts}` patch per operation (one undo step).
  Invariants: `section.fields[]` <-> `field.section_id` bidirectional
  consistency; `parts[].section_ids` pruned on removal (emptied parts
  dropped); `order` renumbered to match array order; minted ids never squat
  the `sec_to_review` review-gate prefix.
- `schema-editor/src/components/SectionManager.tsx` -- modal (Fields-pane
  "Sections" button): inline rename, per-row "Merge into..." select, Remove
  (fields become Uncategorized; merge is the re-file path), Add section, and
  hosted-author "Regenerate divisions". Destructive ops behind
  `window.confirm` (existing convention). To-review rows carry an amber
  "re-file required" badge.
- `FieldList` highlights a To-review section amber with the same badge while
  it still holds fields; `validation.ts` mirrors the gate client-side so the
  panel explains the block before the author hits publish.
- Backend `schema_lint.py`: `TO_REVIEW_PREFIX` + `to-review-pending` ERROR
  rule (one finding per un-reviewed field, keyed on the field's own
  section_id so dangling pointers are caught; plus one per one-sidedly stale
  to-review section list). The publish gate (status -> complete) already
  blocks on lint ERRORs, so the hard gate needed NO new gate code -- pinned
  by a route test (409 with the to-review finding named; re-filing unblocks).
- Backend `POST /api/editor/kits/{id}/derive-divisions` (author tier):
  re-runs `derive_sections.derive_and_apply` on the stored draft + its PDF
  (in-process; PyMuPDF is already a backend dep), stores the result, updates
  `_bakeoff.authoring.division`, returns strategy/counts/to-review ids +
  post-derivation lint counts. 409 published kit / missing PDF, 422
  unreadable PDF (schema untouched), equality with a direct
  `derive_and_apply` call pinned by test.

Exit criteria: (1) PASS -- ops function on a loaded kit (live-verified, see
below) with consistency invariants unit-tested; save/reload round-trip pinned
at the API level (the publish-gate test PUTs a re-filed schema and re-reads
it). (2) PASS -- the route's stored output equals direct derivation (pinned);
the action sits behind confirm dialogs (live-verified: the flow only proceeds
once confirm passes). Note: the criterion's "bead-1 prototype output" predates
the maintainer's cap amendment (20 -> 40, 2026-07-10); the route runs the SAME
derivation module extraction runs, at the amended default. (3) PASS --
schema-editor suite 693 passed including 31 new tests; backend suite 994
passed including 12 new.

## Live verification (hosted editor + local backend, scratch kit copies)

Ran the hosted editor against a local backend on scratch copies of w7 +
f1040: author access-code gate; w7 regenerate -> 8 derived sections matching
the printed headings with "Other Information" WHOLE at 22 fields (cap 40 --
no more 20+2 split); f1040 regenerate -> 14 sections (Dependents 21+21
balanced, Income whole at 30) with "To review (unplaced)" carrying the amber
badge in both the manager and the field list; merging it into Income re-filed
the 4 positionless fields and cleared the badge; one Undo restored the whole
merge atomically. Zero console errors.

## Lessons

- Making the review gate a LINT RULE bought three surfaces for one
  implementation: the publish gate blocks automatically (it already rejects
  lint ERRORs), the editor's validation panel explains it, and extraction's
  tri-state exit correctly reports a fresh draft with to-review fields as
  stored-with-issues.
- The sandboxed browser preview CAN drive the hosted editor (its storage
  fallback tolerates the opaque origin) -- but React inputs need
  native-setter + dispatched events; `preview_fill`/`preview_click` alone
  don't reach React state. Screenshots time out on the PDF canvas; DOM
  queries via `preview_eval` are the reliable assertions.

## Doc freshness

- No tier-1/2 doc tracks the schema-editor surface (no
  `docs/components/schema-editor.md` exists); the freshness checker's STALE
  flags all track files this branch did not touch -- reviewed and left.

## Files touched

- `schema-editor/src/utils/sectionOps.ts` (new), `components/SectionManager.tsx`
  (new), `App.tsx`, `components/FieldList.tsx`, `utils/validation.ts`,
  `utils/remoteKitStore.ts` + 5 test files (4 new)
- `backend/services/schema_lint.py`, `backend/routes/editor_kit_routes.py`
- `backend/tests/test_schema_lint.py`, `backend/tests/unit/test_editor_kit_routes.py`
