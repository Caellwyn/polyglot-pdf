---
date: 2026-09-18
bead: polyglot-pdf-630ej
title: "test(frontend): SchemaForm.previewEdit + VoiceOverlay.voicemode flake in the FULL vitest suite but pass in isolation"
tags: [testing, harness]
---

## Trigger

The user asked to fix "the frontend vitest failures," noting there were
roughly 10 open beads about it. `bd list --all | grep -i vitest` turned up
nine open beads describing the same underlying symptom from different
angles and dates (2026-08-13 through 2026-09-15): a full `npx vitest run`
from `frontend/` intermittently failed a rotating set of files -- always
overlay/preview-heavy suites, always passing cleanly in isolation, always a
*different* failing file each run. That instability makes "is the frontend
suite green?" unanswerable as a pre-PR gate, which is exactly the failure
mode CLAUDE.md warns against (a flaky suite trains everyone to re-run
instead of read).

The nine beads: polyglot-pdf-630ej, sdds1, 8urce, qta6l, sw5vl, ab4us,
cfl28, 73o17, 6wmq.

## What shipped

**Root cause 1 -- unbounded fork concurrency.** `frontend/vite.config.ts`
had no `poolOptions.forks.maxForks`, so vitest defaulted to spawning one
fork per CPU core (22 on this machine), each booting a full jsdom
environment. That oversubscribes the box: `findBy*`/`waitFor` calls and
hook/test timeouts intermittently starved under the contention. Capped
`maxForks` at 8 and raised `testTimeout` to 10000ms.

**Root cause 2 -- the real gap: testing-library's OWN timeout is separate
from vitest's.** `@testing-library/dom`'s `findBy*`/`waitFor` retry
timeout (`asyncUtilTimeout`, default 1000ms) is a *different* config knob
from vitest's `testTimeout` -- raising the latter does nothing for the
former. This is why `SchemaForm.previewEdit.test.tsx` already had a
`LAZY_MOUNT_TIMEOUT_MS = 20000` constant with a comment explaining exactly
this failure mode, passed as the **test-level** timeout to some `it()`
calls (`bd polyglot-pdf-ykfx0`'s block did this correctly) -- but the
`findByTestId` call inside `mountInPreview()` never received it, and the
*first* describe block's four tests (`bd polyglot-pdf-7esr`) never passed
the constant as their own test-level timeout either. Added a new
`frontend/src/setupTests.ts` that calls `configure({ asyncUtilTimeout:
10000 })` globally, wired in via `vite.config.ts`'s `setupFiles`, so every
`findBy*`/`waitFor` call across the suite gets the same headroom without
touching each of the ~16+ files that use them without an explicit
per-call override. Also fixed `mountInPreview()`'s call directly and added
the missing `LAZY_MOUNT_TIMEOUT_MS` to the first describe block's four
tests, since that file's own comment already documented the intended fix
-- it just wasn't fully wired.

**A third, distinct (non-timing) bug found along the way:**
`VoiceOverlay.continuousheader.test.tsx`'s local `makeManager()` mock
(cast `as any`) was missing `isPaused`, causing an intermittent
`TypeError: connectionManager.isPaused is not a function` whenever
`VoiceOverlay.tsx`'s connection-error path called it (bd 6wmq's own
diagnosis, confirmed present in this session's logs before the fix and
absent after). Added the missing mock method.

**Not fixed here, correctly out of scope:** bd 73o17 also named
`App.grouping.test.tsx`'s `summarizeCatalogue is not a function` as a
related flake to check. That file no longer exists in the tree (`find`
returned nothing) -- stale reference from an earlier state of the repo,
nothing to action.

**Deferred, filed as a follow-up bead (not blocking):** 11 files in
`frontend/src/demo/*.test.tsx` each hand-roll a near-identical
connectionManager mock cast `as any`. The cast is why the `isPaused` gap
went unnoticed by TypeScript. Spawned via `spawn_task` (chip
`task_b76ee8ba`) rather than filed as a bead directly, per the
scope-creep rule -- it's a real structural improvement but not itself
blocking this closeout, and the user can start it in a fresh worktree.

**Verification:** ran the full suite repeatedly rather than trusting a
single green pass, since the bug WAS intermittent. 10 of 11 full-suite
`npx vitest run` invocations in this worktree came back fully green
(170/170 files, 2395/2395 tests). The one exception had **zero test
failures** -- only a benign internal `[vitest-worker]: Timeout calling
"onTaskUpdate"` IPC log (vitest's own main-process/worker RPC channel,
unrelated to any test, not exposed as a public config option). Confirmed
the `isPaused` TypeError string does not appear in any of the later full
runs (`grep -c` = 0), where it was present before the fix.

`sw5vl` (sessionCredential.test.ts's synchronous FS-walk test timing out
at the 5000ms default under load) is covered by the same `testTimeout:
10000` bump -- the walk itself does legitimate, correct work and doesn't
need to get faster, just more headroom under contention.

## Lessons

vitest's `testTimeout` and `@testing-library`'s `asyncUtilTimeout` are
two *separate* timeout knobs that look like they'd cover each other and
don't. A test-level timeout bump (`it(..., 20000)`) does not extend an
internal `findBy*` call's own retry budget -- that needs either an
explicit `{ timeout }` third argument per call, or a global `configure()`
in a setup file. `SchemaForm.previewEdit.test.tsx` had already correctly
diagnosed this in a comment and even named the right constant
(`LAZY_MOUNT_TIMEOUT_MS`) -- it just wasn't fully wired into every call
site that needed it, which is exactly the "the first fix was correct, it
just wasn't the whole set" shape CLAUDE.md's scar tissue #8 describes.

## Doc freshness

Ran `check_doc_freshness.py` (via `closeout_prep.py`). It flagged 16
stale docs, but every one tracks files this branch never touched
(`backend/config.py`, `backend/routes/websocket_routes.py`,
`frontend/src/schema-forms/state/schemaFormState.ts`, etc. -- all edited
by other recent commits, none touched here). Per the skill's own
guidance ("if a stale doc tracks files your branch did NOT touch, leave
it -- it was already stale before you"), left all of them as-is. No
`docs/components/` or `docs/standards/` doc tracks
`frontend/vite.config.ts` or vitest/testing-library setup specifically,
so none needed a bump for this change.

## Files touched

- `frontend/vite.config.ts` -- capped fork concurrency (`maxForks: 8`),
  raised `testTimeout` to 10000ms, wired in the new setup file.
- `frontend/src/setupTests.ts` (new) -- globally raises
  `@testing-library/dom`'s `asyncUtilTimeout` to 10000ms.
- `frontend/src/schema-forms/components/SchemaForm.previewEdit.test.tsx`
  -- `mountInPreview()`'s `findByTestId` now gets an explicit timeout; all
  four tests in the first describe block now carry the
  `LAZY_MOUNT_TIMEOUT_MS` test-level timeout that was already defined but
  only wired into a later describe block.
- `frontend/src/demo/VoiceOverlay.continuousheader.test.tsx` -- added the
  missing `isPaused` mock method.
