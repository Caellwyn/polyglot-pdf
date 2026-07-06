---
date: 2026-07-05
bead: polyglot-pdf-v96b
title: "P5.3a tri-state exit + store-with-issues + persist AcroForm dump"
tags: [schema-editor, extractor, conventions]
---

## Trigger

Lane-2 bead of the schema-v2 epic `polyglot-pdf-h76m` (plan:
`~/.claude/plans/rustling-discovering-hearth.md`, P5.3), split from the original
P5.3 (h76m.14) into three reviewable sub-beads: **P5.3a** (this bead -- the
backend store-with-issues core), P5.3b (`zgln`, repair-all), P5.3c (`nivy`, the
widget picker). The split was mine (process/PR-shaping): P5.3 spanned the
extractor script, two backend routes, two frontend components, and a new UI --
too large for one reviewable PR, and the widget picker is an independent feature.

Before this, the hosted extract route was all-or-nothing: a draft that failed
validation OR was lint-dirty 502'd, discarding minutes of paid extraction. The
plan's store-with-issues design keeps an imperfect-but-usable draft so the author
repairs it in the editor, while the promotion gate still blocks publishing it
(the two-gate seam).

## What shipped

- **Tri-state exit** (`extract_form.py`): `main()` now returns 0 (valid +
  lint-clean), 3 (stored-with-issues: parseable, >= 1 field, but invalid and/or
  lint-dirty), or 1 (no usable draft: 0 fields). It already always-wrote the
  draft + recorded the `_bakeoff.authoring.lint` block (h76m.5); `_classify_exit`
  maps `(schema_valid, lint errors, field count)` to the code. Named `EXIT_*`
  constants are the contract the route reads.
- **Kit JSON artifacts** (`form_kits.py`): `put_json_artifact` /
  `load_json_artifact` on both stores (Local + GCS), thin wrappers over the
  existing atomic-write / no-cache-upload machinery. Used to persist the AcroForm
  dump as the kit's `acroform.json`. A missing artifact is `FormKitNotFound`
  (callers degrade to the dump-less path); an unreadable one is
  `FormKitStoreError`.
- **Store-with-issues extract route** (`editor_kit_routes.py`): passes
  `--keep-dump` so the dump lands next to the draft; on a parseable draft with
  >= 1 field it STORES the draft + the `acroform.json` artifact and returns 200
  carrying `errorCount` / `warningCount` / `storedWithIssues`. 502 ONLY on
  crash / timeout / no-JSON / no-usable-draft. The store floor requires >= 1
  FIELD-SHAPED (dict) member in `fields`, re-derived from the WRITTEN draft, not
  the exit code alone -- checking merely "non-empty list" was NOT enough
  (fresh-eyes): a crash mid-write can leave a non-empty list of NON-DICT junk
  that `lint_schema` silently filters out (0 findings), which would otherwise
  store as a false "clean success" with a junk field count. `fieldCount` counts
  real (dict) fields too. Lint runs after store (dump-aware) using the SAME
  `schema_lint` the promotion gate uses, so store and promote agree. The
  extractor's `_classify_exit` applies the same dict-member floor, so its exit
  code and the route's floor agree.
- **Promotion gate closes the widget-claim hole**: `set_editor_kit_status` now
  loads the persisted dump (`_load_kit_dump`, best-effort) and passes it to
  `lint_schema`, so the dump-only `dump-widget-multiclaim` rule runs at the
  mark-complete gate too (previously extraction-time only).
- **Editor surfaces it**: `RemoteCatalogue` shows the store-with-issues lint
  counts in the extraction notice ("Extracted ... with issues (3 errors, 1
  warning). Open it to review and repair ...").

## The two-gate seam, pinned

store-with-issues (this bead) and promote-requires-zero-lint-ERRORs (P2.1) are
DISTINCT gates. A test stores a Pydantic-VALID but lint-ERROR draft (duplicate
option values -- v1 tolerance parses it, lint rejects it) via the route, then
asserts mark-complete 409s on the LINT gate specifically (a Pydantic-invalid
draft would 422 at the earlier gate, so the fixture is chosen to reach the lint
layer). A stored-with-issues draft is un-promotable until repaired.

## Route <-> extractor constant sync

The route runs `extract_form.py` as a subprocess and cannot import its
`EXIT_ISSUES` constant, so it mirrors the literal `3` as `_EXTRACT_EXIT_ISSUES`.
`test_extract_form_exit.test_route_exit_constant_matches_extract_form` pins the
two equal so a change to the extractor's exit code cannot silently desync the
route's store-with-issues branch.

## Verification

Exit criteria (this bead): (1) a forced-imperfect extraction stores draft +
report, returns 200 with counts -- `test_extract_stores_lint_dirty_draft_with_
issues_200`; (2) unparseable / zero-field output still 502s --
`test_extract_zero_field_draft_is_no_usable_draft_502`,
`test_extract_missing_output_failure_detail_scrubs_temp_path`; (3) two-gate seam
-- `test_stored_with_issues_draft_is_unpromotable_two_gate_seam`. Backend suite
green (570+ passed, 2 skipped). Frontend: the touched files
(RemoteCatalogue/ValidationPanel/App.hosted) pass 47/47 and typecheck is clean;
the full FE suite hangs on this machine's vitest fork-pool startup (a known local
flake -- CI's Linux runner runs it green, as on PRs #313/#316).

## Unblocks

P5.3b (`zgln`, repair-all -- needs this bead's persisted dump for the repair
widget-existence check) and P5.3c (`nivy`, widget picker -- needs the dump
artifact). Both feed P6.1.

## Doc-freshness note

`docs/components/pdf-filling.md` tracks `form_kits.py` (which this bead changed),
so it was updated to document the new `put_json_artifact` / `load_json_artifact`
store surface. The other STALE-flagged tier-2 docs (auth, context-compression,
several standards) do NOT track any file this diff touched -- pre-existing drift
from other work's file mtimes, left as-is.
