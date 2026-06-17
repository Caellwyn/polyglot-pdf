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

**Part 2 -- confirm/harden the deploy gate across all paths.** `deploy-demo.sh`
and `deploy-production.sh` do NOT upload form-kits themselves -- each sets the
bucket/env then invokes `./deploy-all.sh`, whose `kit_is_complete` loop gates the
upload. BUT fresh-eyes caught a FOURTH path I'd missed: `scripts/deploy-form-kit.sh`
is an independent form-kit deploy script (`--all` loops every kit) that uploaded
AND manifested kits with NO status gate -- a real draft-leak that falsified
criterion 2's "no path uploads a draft." Fixed: added a `kit_is_complete` gate
(matching deploy-all.sh's exact grep) to both its `upload_kit` and its manifest
loop. Then extended the deploy-gate harness (`tests/test_deploy_all_kit_gates.sh`,
bd 45x5) with two assertion kinds: `no-bypass` (delegating wrappers have no own
form-kit cp/rsync) for demo/prod, and `gate-present` (the actual `if !
kit_is_complete` GUARD CALL, not just the function name) for the two direct-upload
paths deploy-all.sh + deploy-form-kit.sh. Also broadened the no-bypass regex to
catch rsync, and verified the gate-present check is non-vacuous (removing the guard
makes it FAIL). (Note: there is no ACTIVE prod -- CLAUDE.md -- but
`deploy-production.sh` exists and delegates correctly, so it's verified regardless.)

**Fresh-eyes assess (Sonnet, arm B picker, 2 rounds to NO-GAPS):** round 1 scored
criterion 1 PASS, criterion 2 FAIL -- the missed `scripts/deploy-form-kit.sh` path
(high-confidence, in-scope) plus two test-robustness gaps (vacuous gate-present
grep; rsync blind spot). All three adopted and fixed; round 2 returned NO-GAPS.

**Outer review went via the Opus-4.8 FALLBACK, not Codex:** Codex's usage limit
was exhausted (watch returned ERROR), so per the closeout skill (Step 7.5) the
reviewer-of-last-resort -- the fresh-eyes agent at `model: opus` -- did the outer
review. It returned NO-GAPS (both criteria PASS; it ran the bash gate harness
14/14 with mutation checks proving non-vacuity, and the vitest suites), which
carries the same authority as a clean Codex review. The bead was closed by hand
(the watcher's Codex-only `--close-on-clean` did not fire).

**Telemetry gap:** the harness_ledger row for this PR (arm BC) incremented the
experiment counter but its JSON file did not persist to disk (cause unclear; the
file the script reported writing was absent on a follow-up `git add`). Not
regenerated, to avoid double-counting the arm in the cache. Warn-only; does not
block the merge.

**Exit-criteria scorecard** (both PASS):

1. Editor view + set status:draft|complete, persisted to metadata.json. PASS --
   `setKitStatus` (read-merge-write) + the FormCatalogue toggle; 4 unit tests
   (`formKitDirectory.status.test.ts`) + 2 component tests assert the write and
   the badge/label flip.
2. Deploy filter holds across deploy-demo.sh, deploy-production.sh, AND a direct
   deploy-all.sh --form-kits -- no path uploads a draft. PASS -- demo/prod
   delegate to deploy-all.sh's gate (no independent upload); deploy-all.sh and the
   independent scripts/deploy-form-kit.sh both guard uploads with kit_is_complete;
   the no-bypass + gate-present regression checks lock all four paths (14/14
   assertions pass).

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
- `scripts/deploy-form-kit.sh` -- NEW `kit_is_complete` gate on both `upload_kit`
  and the manifest loop (was an ungated 4th deploy path; fresh-eyes finding).
- `tests/test_deploy_all_kit_gates.sh` -- `no-bypass` (demo/prod, cp+rsync) +
  `gate-present` (the actual `if ! kit_is_complete` guard call) for deploy-all.sh
  and scripts/deploy-form-kit.sh.
- `docs/journal/entries/2026-06-17-bd-nr8u-editor-status-deploy-gate.md` -- THIS entry.
