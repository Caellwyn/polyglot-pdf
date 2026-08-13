---
date: 2026-08-13
bead: polyglot-pdf-fqexm
title: "The static bundle bypassed the whole kit lifecycle"
sprint: 19
tags: [testing, conventions, review]
---

## Trigger

Filed 2026-08-07 during the kit-lifecycle epic, picked up immediately after bd
polyglot-pdf-hqztg merged (PR #582). hqztg had just spent ten review rounds
making sure an editor cannot put a form in front of clients on their own -- and
this bead is the hole that made all of that bypassable.

## What was wrong

`frontend/scripts/generate-form-manifest.ts` runs on `prebuild`, `predev`,
`pretest`, `postinstall` and `prepreview` -- so on every Firebase Hosting build.
It indexed every kit that had a schema and a PDF, and copied the WHOLE
`form-kits/` tree into `frontend/public/`. No status gate anywhere: the
`KitMetadata` interface did not even declare `status`.

The backend honours the lifecycle (`_require_published`, plus the list filter)
and both deploy scripts skip anything that is not `complete`. The frontend build
did not, and it is the one that decides what Firebase Hosting serves.

Against the real tree that meant `f1040` (draft) and `w9-heldout` (no metadata
at all) were published -- schema, PDF, and an index entry. And because
`SchemaFormDemo` falls back to the bundled manifest whenever the backend call
fails, a RETIRED form stayed reachable there, which is precisely what
`unpublished` exists to prevent.

## What shipped

One predicate (`kitPublishFilter.ts`, beside `kitCopyFilter.ts` and for the same
stated reason), consulted by BOTH the index path and the copy path -- the copy
consults the set the index already decided, so the two cannot disagree. Fail
closed: unreadable metadata, absent `metadata.json`, a missing `status`, or an
unrecognised status all withhold.

## Four rounds, five findings -- and all five were about TESTS, not the gate

The gate itself was right in the first commit. Every round found a way the
tests, or my changes to them, failed to hold it:

1. **A branch became wrong without being edited.** The `fs.rm` that clears the
   previous build lives inside `copyKitsToPublic()`, and a pre-existing
   `if (!forms.length) return` skipped that call. Harmless while the only way to
   get an empty result was "no kits exist" -- but the gate gave `forms` a SECOND
   way to come back empty: every kit withheld. So retiring your LAST published
   form skipped the wipe, leaving its files and a stale index still served. The
   sharpest case of the feature, failing.

2. **An unrequested behaviour change.** The filter also stopped copying
   root-level files, so `form-kits/README.md` no longer publishes. Correct --
   authoring notes are not client assets -- but it fell out of the kit-id lookup
   rather than being asked for. Now explicit and pinned; an unpinned side effect
   is one refactor from silently reverting.

3. **I broke an existing test's coverage without touching that test.** At base
   the call site was `filter: shouldCopyKitPath` -- a direct reference, so
   `formKitBundle.archive.test.ts` genuinely covered the shipped behaviour.
   Wrapping it in a composed lambda meant that test proved the predicate CORRECT
   but no longer proved the script CALLS it. Deleting the underscore guard left
   all 17 tests green while republishing every superseded schema to Hosting.
   This is the sharpest lesson of the bead: **composing a function under test
   moves the seam, and the old test may no longer reach it.**

4. **A test that could not fail.** "Withholds every unpublished kit's FILES, not
   just its index entry" asserted a strict subset of the parametrized cases
   above it. Its name promised index/copy separation; it re-checked the copy
   half. No mutation could kill it while sparing the others.

5. **An optimisation that deleted the only test that could fail.** My test file
   spawns real subprocesses, so I merged two scenarios into one shared fixture
   to halve them. All 12 tests stayed green -- and so did the mutation restoring
   finding 1's bug, because the shared fixture always has one publishable kit,
   so `forms.length` is never zero. Caught only by re-running the mutation
   rather than trusting the green suite. **Cheaper tests that cannot fail are
   not cheaper.**

## Two things I was confidently wrong about

Worth recording, because the corrections came from re-running experiments rather
than from better reasoning:

- A test failed and looked like my regression. I chased two plausible causes --
  a stale generated bundle, then a blocking subprocess -- and was wrong both
  times. **Stashing the diff and re-running the baseline** showed the failure
  without my changes at all (filed as bd polyglot-pdf-cfl28).
- I then reported that my subprocesses had turned that flake from intermittent
  into reliable. Round 3 removed my test file entirely and still saw it fail 1
  of 4 runs, versus 2 of 4 with the file present. Same rate. **I had inferred
  causation from two consecutive samples.**

Round 4 modelled the discipline I had been missing: it found a mutation that
survived, then instrumented `fs.cp` to check whether the branch was reachable at
all. It was not (a rejected directory prunes its subtree, so the children are
never visited), so it declined to demand a test for unreachable code -- which
would have been the same anti-pattern the earlier rounds were fixing.

## Cross-surface result

The outer review traced every changed contract into untouched consumers. The
backend and root tests that reference `f1040`/`w9-heldout` all read the SOURCE
`form-kits/` tree, never the bundle, so they are unaffected; the voice harness
drives `i-90` (complete); nothing fetched the README; no CI or deploy
environment sets the new `FORM_KITS_PUBLIC_DIR`; and the `"complete"` literal
agrees with `deploy-all.sh` and `form_kit_routes.py`.

It found one real interaction, filed as bd polyglot-pdf-pk2ns: **local dev now
lists a draft it cannot load.** `LocalFormKitStore` is deliberately permissive
(`enforce_complete_on_public_reads = False`) so a maintainer can test-drive
drafts -- but its manifest hardcodes the STATIC path, which is exactly what this
gate stops producing. Deployed surfaces are unaffected. The fix belongs in the
local store, which can already serve the schema through its own API (the client
comment at `SchemaFormDemo.tsx:165` anticipates precisely that), so local mode
keeps serving drafts end to end while the bundle keeps its gate. Left to pk2ns
rather than widening this bead into the backend; the interaction is recorded in
`kitPublishFilter.ts` where the next reader will meet it.

## Follow-ups

- bd polyglot-pdf-pk2ns -- local dev lists drafts the bundle no longer ships.
- bd polyglot-pdf-983wp -- a published kit still ships its internal working
  files (`schema_archived.json`, `*_schema_backup.json`, `migration_report.json`,
  an annotated PDF). Pre-existing, same class as the `_archive` leak bd
  polyglot-pdf-w3zw fixed, but these carry ordinary names so the underscore rule
  misses them. This bead gates WHICH KITS ship, not which files within one.
- bd polyglot-pdf-cfl28 -- the pre-existing `SchemaForm.previewEdit` flake.
