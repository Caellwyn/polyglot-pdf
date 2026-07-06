---
date: 2026-07-06
bead: polyglot-pdf-zgln
also_closes: polyglot-pdf-r5vp
title: "P5.3b one-click Repair-all endpoint + editor button"
tags: [schema-editor, extractor, conventions]
---

## Trigger

Lane-2 bead of the schema-v2 epic `polyglot-pdf-h76m` (plan P5.3), the second of
the three sub-beads P5.3 was split into (after P5.3a `v96b` store-with-issues,
before P5.3c `nivy` widget picker). It depends on P5.3a for the persisted
AcroForm dump artifact -- the repair pass's widget-existence check needs it.

Repair logic already existed as `backend.services.schema_repair.repair()` (P5.2,
`h76m.13`), wired into the CLI extraction pass (`extract_form._repair_schema`).
This bead surfaces it as a one-click editor action, over the SAME function, so a
contractor repairs a stored-with-issues draft in place -- and the editor's output
equals CLI repair on the same input by construction.

## What shipped

- `POST /api/editor/kits/{kit_id}/repair` (author tier -- repair MUTATES the
  stored schema, like extraction): loads the kit's schema + its persisted
  `acroform.json` dump (via `_load_kit_dump`, bd v96b), runs
  `schema_repair.repair(schema, dump)`, stores the repaired schema, and returns
  the repairs report (`applied` / `dropped` / `aliasHits` / `repairs[]` --
  mirroring the CLI's `_bakeoff.authoring.repair` block) plus the POST-repair
  lint counts the editor re-renders.
  - A `RepairError` (the draft references PDF widgets the form does not have --
    repair must NOT invent mappings) is a **422 CLIENT error** naming the
    widgets, never a 500: it is a fixable data defect a human must resolve.
  - A complete (published) kit is refused (409 -- revert to draft first, same as
    save); a schemaless kit is 404.
- `remoteKitStore.repairKit(kitId)`.
- `ValidationPanel`: a "Repair all (N)" button (N = error count) shown author-tier
  on a stored kit only when ERROR-class defects exist. It runs the repair, then
  the host (`App.handleRepairAll`) reloads the repaired schema, which re-runs the
  lint effect. Unsaved edits are guarded: repair operates on the STORED draft, so
  the handler prompts to save/discard first (a silent reload would clobber them).

## == CLI output, by construction

The route calls the exact `schema_repair.repair()` the CLI runs, so equivalence
is structural, not a re-implementation. The test pins it anyway:
`test_repair_all_stores_and_reports_and_equals_cli` asserts the STORED repaired
schema equals `schema_repair.repair(draft, None)` called directly -- the "== CLI
repair on the same input" exit criterion.

## Verification

Exit criteria: (1) a stored imperfect draft repairs with a working Repair-all
whose result == direct `repair()` output (== CLI) --
`test_repair_all_stores_and_reports_and_equals_cli` + the ValidationPanel
button tests; (2) a draft with hallucinated widgets returns a clear client error,
not a 500 -- `test_repair_hallucinated_widget_is_422_not_500`. Backend: 88
editor+exit tests pass (incl. author-gate 403, published-kit 409, schemaless 404,
dump-aware repair). FE: ValidationPanel 10 tests (3 new Repair-all); touched
App/save suites green; typecheck clean. Full FE suite relied on CI's Linux runner
(the local vitest fork-pool hangs -- see the v96b entry).

## bd r5vp: stale-open guard (folded in)

The Opus fallback review filed r5vp: `handleRepairAll` awaited repair + reload
without the `openSeqRef` monotonic-token guard `handleOpenRemoteKit` uses (Codex
PR #280). Repairing kit A (a multi-second round trip) while opening kit B
mid-flight would let A's reload clobber B's displayed schema. Folded the fix into
this PR (small, same file, self-inflicted this bead): `handleRepairAll` captures
`openSeqRef` at entry and abandons after each await if a newer open/repair
superseded it. A test opens A, repairs A (hung), opens B, then releases the
repair and asserts A's reload never runs.

## Unblocks

P5.3c (`nivy`, the widget picker) is the last of the P5.3 trio; then P6.1
depends on all three.

## Doc-freshness note

closeout_prep flagged the usual tier-2 docs as STALE. Reviewed: none of their
`Tracks:` lines name a file this diff touched (`editor_kit_routes.py`,
`schema-editor/**`) -- pre-existing drift from other work's mtimes, left as-is.
