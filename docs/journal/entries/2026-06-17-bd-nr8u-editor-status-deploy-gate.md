---
date: 2026-06-17
bead: polyglot-pdf-nr8u
title: "D2: editor status toggle + confirm deploy gate across all paths"
sprint: 5
tags: [testing, conventions]
---

## Trigger

`bd polyglot-pdf-nr8u`, Track D (D2) of sprint 5 / epic 7a9
(`docs/sprint_5_i90-authoring-loop_plan.md`). Re-scoped per the 2026-06-14 Codex
plan review: the MINIMAL draft-leak deploy gate moved INTO D1 (b0pe), so D2 is no
longer the thing standing between drafts and production. What remained: (1) let a
human view + set a form's `status` (draft|complete) from the editor -- D1 writes
`status:draft` on onboard, D2 adds the promote-to-complete control; and (2)
confirm/harden that the deploy filter (`status != complete -> skipped`) holds
across every deploy path, so no path can leak a draft.

## What shipped

**Part 1 -- editor status UI.** `setKitStatus(entry, status)` in
`formKitDirectory.ts` read-merge-writes a kit's `metadata.json` `status`,
preserving label/schema/pdf and any unknown keys (never a blind overwrite), and
returns the refreshed `CatalogueEntry`. `FormCatalogue` grows a per-card status
toggle: a draft (or unknown-status) kit shows "Mark complete"; a complete kit
shows "Revert to draft". The toggle is shown only for kits that HAVE a schema --
a PDF-only kit can't meaningfully be complete (the deploy gate skips schema-less
kits regardless). The toggle sits outside the card's open-button (valid HTML; the
open-button opens the kit, the toggle publishes/unpublishes it).

**Part 2 -- confirm/harden the deploy gate across all paths.** Investigation
showed `deploy-demo.sh` and `deploy-production.sh` do NOT upload form-kits
themselves -- each sets the bucket/env then invokes `./deploy-all.sh`, whose
`kit_is_complete` loop is the single gate. So criterion 2 was structurally already
true; the work was to CONFIRM it and lock it against regression. Extended the
existing deploy-gate harness (`tests/test_deploy_all_kit_gates.sh`, bd 45x5) with
a no-bypass check: assert neither wrapper has its own `gcloud/gsutil` form-kit
copy, and that `deploy-all.sh` still references `kit_is_complete`. (Note: there is
no ACTIVE prod for this project -- CLAUDE.md / the architecture decision -- but
`deploy-production.sh` exists and delegates correctly, so the gate is verified on
it as a script regardless.)

**Exit-criteria scorecard** (both PASS):

1. Editor view + set status:draft|complete, persisted to metadata.json. PASS --
   `setKitStatus` (read-merge-write) + the FormCatalogue toggle; 4 unit tests
   (`formKitDirectory.status.test.ts`) + 2 component tests assert the write and
   the badge/label flip.
2. Deploy filter holds across deploy-demo.sh, deploy-production.sh, AND a direct
   deploy-all.sh --form-kits -- no path uploads a draft. PASS -- demo/prod both
   delegate to deploy-all.sh's gate (no independent upload); the no-bypass
   regression check in the gate harness locks it (13/13 assertions pass).

**Verification:** 6 new FE tests (4 setKitStatus units + 2 catalogue toggle
component) + 3 new deploy-gate assertions; FE suite green (the forks-runner pool
threw transient "Timeout starting forks runner" errors on this Windows box --
confirmed environmental: 188 tests pass and a `--pool=threads` run of the changed
files is clean); `tsc --noEmit` clean. Backend suite green from prep.

**Fresh-eyes assess (recorded at closeout -- see merge ping for round count).**

## Lessons

- **"Harden across all paths" can be a confirm-and-lock job, not a re-implement
  job.** The instinct on "make the gate hold everywhere" is to add gating to each
  deploy script. But demo/prod already routed through the one gated script, so the
  correct, minimal work was to verify that single chokepoint and add a regression
  test that fails if a future edit introduces a bypassing upload -- not to
  duplicate the gate. Trace the actual call graph before adding belt-and-suspenders.

## Doc freshness

- FE + a test harness; the schema editor has no tier-2 component doc, and the
  deploy/form-kit-status behavior is covered by the deploy doctrine + the gate's
  own test. Any docs `check_doc_freshness.py` flags that track files this branch
  did NOT touch were stale before this branch and are left as-is (recorded here).

## Files touched

- `schema-editor/src/utils/formKitDirectory.ts` -- NEW `setKitStatus(entry,
  status)` (read-merge-write of metadata.json status, preserves other fields).
- `schema-editor/src/components/FormCatalogue.tsx` -- per-card status toggle
  (Mark complete / Revert to draft) + `handleSetStatus` (writes + re-scans);
  schema-bearing kits only.
- `schema-editor/src/utils/formKitDirectory.status.test.ts` -- NEW. 4 unit tests
  (promote, revert, preserve-unknown-keys, write-when-no-metadata).
- `schema-editor/src/components/FormCatalogue.test.tsx` -- 2 new tests (promote a
  draft via the toggle + persisted to disk; no toggle for a schema-less kit).
- `tests/test_deploy_all_kit_gates.sh` -- no-bypass assertions (demo/prod route
  through deploy-all.sh; deploy-all.sh still calls kit_is_complete).
- `docs/journal/entries/2026-06-17-bd-nr8u-editor-status-deploy-gate.md` -- THIS entry.
