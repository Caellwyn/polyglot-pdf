---
date: 2026-06-15
beads: [polyglot-pdf-y61i, polyglot-pdf-45x5]
pr: TBD
tags: [testing, refactor]
---

# y61i + 45x5: forward-ref schema validation + deploy-gate functional tests

Two non-reserved bugfixes bundled (a schema-editor correctness bug + the deploy
gate's missing test coverage). Sequenced after the snpi/979r PR (#213) merged, so
the deploy-gate harness here also covers the `kit_schema_file` helper that PR
introduced.

## y61i -- validateSchema falsely flagged forward references

`schema-editor/src/utils/validation.ts` built its known-field-id `Set`
INCREMENTALLY inside the same loop that ran the reference checks. So a field whose
`show_if.field` or `controls_fields.{shows,unlocks,makes_required}` targeted a
field appearing LATER in `schema.fields` was falsely flagged "references
non-existent field" -- the target had not been added to the set yet. Real I-90 data
happens to list controlled fields before their trigger, which masked the bug.

Fix: build the COMPLETE field-id set in a first pass, then run the reference checks
against it (forward refs now resolve). Duplicate-ID detection genuinely needs an
incremental "seen so far" set -- a duplicate is an id seen EARLIER in the list --
so it keeps its own `seenIds` set in the loop; only the reference checks moved to
the full set. (Note: this is the EDITOR's validation module,
`schema-editor/src/utils/validation.ts`, NOT the runtime voice-app's
`frontend/src/schema-forms/utils/validation.ts` -- a separate file with its own
logic; only the editor copy had this bug.)

5 regression tests (`validation.test.ts`): a forward `show_if` ref and forward
`controls_fields` refs are no longer flagged; a genuinely-missing `show_if` /
`controls_fields` target is STILL flagged (with the right id + `warning` type); a
genuine duplicate ID is still caught.

## 45x5 -- functional tests for the deploy safety-gate

`kit_is_complete` in `deploy-all.sh` is the safety-critical gate that keeps DRAFT
form-kits out of production GCS. It had ONLY `bash -n` (a syntax check) guarding it
-- a regressed grep pattern could silently leak a draft to production with no CI
catch.

The script was not sourceable: it ran arg-parsing + deploy flow at top level, so a
test couldn't load just its functions. Added a **sourcing guard** (`return 0` when
`BASH_SOURCE[0] != $0`) right after the helper definitions -- sourcing now exposes
only the functions; direct execution (`./deploy-all.sh ...`) still runs the full
flow (verified both: the test sources cleanly, and a direct `--frontend` run still
prints the header + deployment plan).

`tests/test_deploy_all_kit_gates.sh` is a plain-bash harness with a tiny
assert/counter (bats is NOT installed in this repo/CI and the bead allows "bats or
equivalent"). It sources `deploy-all.sh`, disables the inherited `set -e` (an
expected "skip" makes `kit_is_complete` return non-zero, which would otherwise
abort the harness), and covers:
- `kit_is_complete`: the 4 REQUIRED cases -- status:complete (pass), status:draft
  (skip), missing status field (skip), missing metadata.json (skip) -- plus a
  whitespace-padded complete.
- `kit_schema_file` (bd snpi): custom filename, no-schema-field default,
  no-metadata default, multiline key/value, whitespace-padded value -- this RETIRES
  the hand-verification snpi shipped with.

10/10 cases pass, exit 0.

## Pre-PR fresh-eyes

Sonnet, 1 round -> NO-GAPS: both criteria PASS with file:line evidence; confirmed
the two forward-ref tests would FAIL against the old incremental-set code (not
vacuous), that dup detection uses the incremental `seenIds` (not the full set), and
that the sourcing guard + `set -e`/`set +e` ordering is correct. Two findings, both
fixed: (1) test 4 (controls_fields missing-ref) now asserts `type === 'warning'`
symmetric with test 3, so a severity regression to 'error' can't slip through; (2)
the harness's `set +e`-after-source ordering is load-bearing (the sourced `set -e`
leaks errexit) -- strengthened the comment + an inline marker so a future edit can't
insert a statement under the leaked errexit.

## Pre-PR assess + closeout notes

- **Tests:** schema-editor 173 pass (incl. the 5 new validation tests); the
  deploy-gate harness 10/10; backend 360 pass (unaffected); tsc clean; `bash -n
  deploy-all.sh` parses.
- **Doc-freshness:** 8 docs flagged STALE, ALL tracking backend/frontend voice-path
  files this branch did not touch (carried in from other merged work). Notably
  `schema-forms.md` tracks `frontend/src/schema-forms/utils/validation.ts` -- a
  DIFFERENT file from the editor's `schema-editor/src/utils/validation.ts` I
  changed. No doc tracks `validation.ts` (editor) or `deploy-all.sh`, so nothing is
  this PR's to bump.
- **Beads slip:** the recurring 2 stale IN_PROGRESS beads (`hrn`, `jf6w`) belong to
  other active sessions; left untouched.
