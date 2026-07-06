---
date: 2026-07-05
bead: polyglot-pdf-vtdx
title: "Ten-bead small-fix batch (vtdx, kfm1, 4b30, krcd, zi2s, n1uw, 0yjb, m0mm, 4y4e, tmby)"
tags: [hotfix, refactor]
---

## Trigger

Maintainer directive (2026-07-05): "continue to knock out low risk beads
independently, feel free to parallelize what can be done in tandem." Ten small
open beads were claimed and bundled into ONE PR per the bead/PR contract
(several whole beads, individually too small for a full PR cycle each). Three
parallel Sonnet subagents implemented the non-overlapping surfaces (backend
Python / schema-editor TS / authoring scripts); the orchestrator did the docs,
deploy-script, and schema-JSON beads and reviewed+committed everything
centrally.

## What shipped (per bead)

- **vtdx** (backend/services/audio_handler.py): `send_manual_field_update` no
  longer drops falsy manual edits -- the skip predicate is now
  `value is None or whitespace-only string`, so checkbox-False and 0 notify
  Gemini (mirrors the bd gihj fix in callback_handler). Two new unit tests
  (False and 0 both call `send_text_message`); the None/whitespace skip cases
  were already covered.
- **kfm1** (docs/doctrine/branch-protection-setup.md): the procedural
  review-gate description now states the auto-merge-vs-ping split (bd 16pj)
  instead of the stale unconditional maintainer-merge wording.
- **4b30** (deploy-production.sh): `BACKEND_EXTRA_ENV="VERTEXAI=true"` is now
  set explicitly on the deploy-all.sh call (matching deploy-demo.sh) so the
  production channel's auth mode no longer rides config.py's implicit default.
- **krcd** (schema-editor/public/schemas/i-90/i-90_schema.json): removed the
  dead `p7_checkbox7extend[1]` reference from all three places (section field
  list, controls_fields[0].unlocks, conditional_fields). Note: the canonical
  form-kits copy (post h76m.5) still carries one occurrence in its DEPRECATED
  `conditional_fields` array -- the lint rule does not audit that array; the
  demo copy is now strictly cleaner than required.
- **zi2s** (form-kits/i-90/schema.json): `p2_checkbox2[5].show_if` widened
  from `equals P2_checkbox1[1]` (commuter only) to
  `in [P2_checkbox1[0], P2_checkbox1[1]]`, matching `p2_checkbox1.
  controls_fields` which unlocks the reason field for BOTH plain-LPR and
  commuter -- every applicant must be able to give a reason. Retrospective
  rubric (legacy bead, no criteria at creation): (1) show_if gates on the same
  option set as controls_fields; (2) the edited schema passes FormSchema
  validation + schema_lint (verified: 0 findings); (3) suites pass.
- **n1uw** (schema-editor/src/utils/fieldGrouping.ts): `had_require_if` typed
  `boolean` (was `boolean | undefined`) and its restore check now uses the same
  falsy style as `had_show_if` -- closes the latent stale-require_if clobber
  path (the bd 319g class).
- **0yjb** (schema-editor/src/App.tsx): local `handleOpenKit` now fetches the
  new kit's PDF BEFORE revoking the prior kit's blob URL (mirrors the bd
  92qe.2 fix in `handleOpenRemoteKit`), so a failed fetch no longer leaves the
  displayed kit with a dead PDF. New regression test
  `App.local-kit.test.tsx` proves the prior URL survives a failed open (and
  was verified to FAIL against the pre-fix ordering). Criterion-2 deviation,
  noted honestly: the bead asked the test to prove "the prior kit still
  renders", but in local mode ANY open error routes to the full-screen error
  view (unlike remote's AuthError carve-out), so "still renders" is
  structurally unassertable; the test pins the substantive guarantee (URL
  never revoked -> reopening kit A still shows a live PDF). Changing the
  error-view architecture is out of scope.
- **m0mm** (nits, PR #306): eval_extraction render_table form column widened
  12->16 (fits `w9-heldout* [gc]`); group_candidates Family A same-index drop
  pinned by a synthetic-dump test (`test_group_candidates.py`) -- test chosen
  over a runtime warning as the least-invasive signal.
- **4y4e** (nits, PR #304): eval_extraction gains a scripts/authoring sys.path
  insert (in-process import of extract_form now resolves); f1_cell double
  formatting collapsed to a single spec (the visible number is unchanged; a
  redundant trailing space is dropped, harmless -- render_table output is only
  print()ed, never parsed).
- **tmby** (nits, PR #302): editor_kit_routes lint-detail segments capped at
  200 chars each (one huge option value can no longer eat the whole [:1400]
  budget); schema_lint `_check_cycles` now DFS's edges collected during the
  main walk instead of re-walking every show_if (identical findings; suite
  unchanged).

## Verification

Combined suites after ALL changes: backend+harness 1569 passed / 3 skipped,
frontend 739 passed, schema-editor 627 passed across 35 files (default vitest
pool -- file count checked per the threads-pool scar). The edited i-90 schema
passes FormSchema validation and lint_schema with 0 findings.

## Doc freshness

- **Bumped:** docs/doctrine/branch-protection-setup.md (the kfm1 fix IS the
  freshness fix; Last updated -> 2026-07-05).
- No other tier-1/2 doc tracks the touched files in a way this batch alters.

## Skipped from the candidate list (and why)

- **31u1** (ProtectedRoute spinner): the bead itself flags option-1-vs-option-2
  as a product/UX call for the maintainer, and a prior session already released
  it from a bundle for exactly that reason. Left open, unclaimed.
- **s8gp / 5jvn** (validation-model fixes): real but meatier; deferred to a
  possible second batch rather than bloating this one.
