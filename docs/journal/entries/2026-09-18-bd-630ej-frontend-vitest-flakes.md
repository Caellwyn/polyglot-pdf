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

**A bug in the "fix" itself, caught by the outer cross-surface review:**
the first version of `setupTests.ts` imported `configure` from
`@testing-library/dom` directly. This repo has TWO copies of that package
installed -- a hoisted 10.4.1 (a peer dep of `@testing-library/user-event`)
and a nested 9.3.4 under `@testing-library/react`'s own `node_modules`
(RTL 14's `^9.0.0` range) -- and `configure()`'s state is module-level, so
the two copies are configured independently. `screen` (what every test
actually calls `findBy*`/`waitFor` on) resolves through RTL's re-export,
which uses the NESTED copy. Importing `configure` from `@testing-library/dom`
therefore configured the WRONG copy -- a silent no-op, verified by
comparing `getConfig().asyncUtilTimeout` on both copies before and after
calling `configure()`. Fixed by importing `configure` from
`@testing-library/react` instead (it re-exports the same nested binding
`screen` uses); verified with the same before/after `getConfig()` check,
this time showing the nested copy's value actually change. Filed
`polyglot-pdf-civyl` for the deeper fix (de-duplicating the dependency so
this footgun can't recur) since that's a separate, larger change than this
PR's scope.

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

**Deferred, filed as follow-up beads (not blocking):**
- `polyglot-pdf-niwtm` -- 11 files in `frontend/src/demo/*.test.tsx` each
  hand-roll a near-identical connectionManager mock cast `as any`. The cast
  is why the `isPaused` gap went unnoticed by TypeScript. (Initially
  spawned as a `spawn_task` chip rather than a bead; the inner fresh-eyes
  reviewer correctly flagged that beads, not chips, are this repo's system
  of record, and filed the durable bead itself. The chip was dismissed as
  superseded.)
- `polyglot-pdf-4y11h` -- `maxForks: 8` is a fixed number above CI's actual
  core count (`ubuntu-latest` = 4 cores, 2 on free public repos), so the
  fork-concurrency cap never binds on CI -- only on this dev machine's 22
  cores. Filed by the outer cross-surface reviewer; non-blocking because
  the bead set this PR closes was reported and reproduced against local
  worktree runs, not a CI failure.
- `polyglot-pdf-civyl` -- the `@testing-library/dom` dependency
  duplication described above (the actual root cause of the
  wrong-import bug this PR's outer review caught and this PR fixed
  inline). Filed for the deeper de-duplication fix.

**Verification:** ran the full suite repeatedly rather than trusting a
single green pass, since the bug WAS intermittent. Across two rounds
(before and after fixing the wrong-import bug above), 13 of 14 full-suite
`npx vitest run` invocations in this worktree came back fully green
(170/170 files, 2395/2395 tests). The one exception had **zero test
failures** -- only a benign internal `[vitest-worker]: Timeout calling
"onTaskUpdate"` IPC log (vitest's own main-process/worker RPC channel,
unrelated to any test, not exposed as a public config option). Confirmed
the `isPaused` TypeError string does not appear in any of the later full
runs (`grep -c` = 0), where it was present before the fix. After the
wrong-import fix specifically, also directly ran the three files the
outer reviewer flagged as combining fake timers with the now-actually-live
10x async timeout (`VoiceOverlayListeningIndicator.test.tsx`,
`SchemaForm.completionClear.test.tsx`,
`webFormConnection.switchdurability.test.ts`) -- 48/48 tests, 5.18s total,
no stalling.

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

A mock cannot tell you the real config is inert, either (a sibling of
CLAUDE.md scar #7's "a mock cannot tell you the real dependency is
forbidden"). `configure({ asyncUtilTimeout: 10000 })` from the WRONG
`@testing-library/dom` copy still returns normally, sets SOME module's
state, and every prior full-suite run still came back green -- because
`maxForks: 8` and the two per-file fixes were doing the real work, and
the global config was silently along for the ride. Green test runs proved
the SYMPTOM was gone; they did not prove the STATED mechanism was the one
that fixed it. The outer cross-surface review caught this by executing a
direct `getConfig()` comparison across both installed copies rather than
trusting the diff's own comment -- the same "prove it, don't infer it"
standard CLAUDE.md's testing scar tissue asks of new tests applies to a
new *config* too.

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
  `@testing-library`'s `asyncUtilTimeout` to 10000ms; imports `configure`
  from `@testing-library/react` (not `@testing-library/dom` directly) so
  it resolves the same nested package copy `screen` actually uses.
- `frontend/src/schema-forms/components/SchemaForm.previewEdit.test.tsx`
  -- `mountInPreview()`'s `findByTestId` now gets an explicit timeout; all
  four tests in the first describe block now carry the
  `LAZY_MOUNT_TIMEOUT_MS` test-level timeout that was already defined but
  only wired into a later describe block.
- `frontend/src/demo/VoiceOverlay.continuousheader.test.tsx` -- added the
  missing `isPaused` mock method.
