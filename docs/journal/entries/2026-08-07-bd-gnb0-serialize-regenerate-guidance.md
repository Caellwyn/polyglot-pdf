---
date: 2026-08-07
bead: polyglot-pdf-gnb0
title: "regenerate-guidance serializes like extract (shared scratch file + lost update)"
sprint: 18
tags: [schema-editor, testing]
---

## Trigger

A wired prerequisite of sprint-18 C3 (bd 05k9, drift resolution -- its batch
rewrite rides this route), and the reason C3 could not start. The
regenerate-guidance route ran `enrich_schema` in a worker thread with NO
concurrency guard, unlike the extract route beside it which holds
`_extract_semaphore`. Two races, both SILENT (a wrong or empty rewrite, never
an error).

## What shipped

**1. The shared CLI scratch file.** `scripts/bakeoff/llm_providers.py` keyed
its CLI-transport scratch path on `os.getpid()` -- correct for the one-shot
CLI scripts the module was written for, wrong once the backend (ONE
long-lived process) started calling it. Two concurrent calls named the same
path: A's `finally` deleted the file B was about to read, or B's CLI
overwrote A's JSON. Now a single `_cli_scratch_path()` helper mints a uuid4
path per CALL, used by both CLI transports in the module.

ENUMERATED THE SET before fixing (scar tissue #7): four pid-keyed scratch
paths exist under `scripts/`. Two are in this module and reachable from the
long-lived backend -- both fixed. The other two
(`arm_llm_native_chunked.py`, `order_probe.py`) are imported by no backend
module (verified by grep) and run as one-shot CLI processes, where pid-keying
is correct; the reasoning is recorded in the helper's docstring so the next
reader does not have to re-derive it, and the test pins the uniqueness
PROPERTY rather than the naming shape.

**2. The lost update.** The route did `load_schema` -> mutate across a
minutes-long model call -> `put_schema` with no version check, so two
overlapping regenerates silently discarded one side's write. SCOPE, stated
because the bead's own text implied more: this closes regenerate-vs-regenerate
only. `put_schema` still has no version check, so a regenerate racing a
`PUT /schema` remains open -- filed by the outer review as bd
polyglot-pdf-gpghk, and the lock's comment says so rather than letting the
next reader assume the write path is safe. Now the whole read/enrich/apply/write window runs
under a per-instance lock, the same guard and the same rationale as the
extract semaphore. The lock is taken BEFORE the load -- taken any later, a
queued request would still mutate its pre-lock snapshot and lose a write. The
body moved into `_regenerate_guidance_locked` purely so the lock wraps one
call instead of re-indenting ~150 lines; no behavior inside changed.

The lock is PER EVENT LOOP, reusing the pattern (and the reason) the onboard
lock next to it already documents.

**Tests** (`backend/tests/unit/test_guidance_regen_serialization.py`), both
mutation-verified: restoring the pid-keyed path reddens the scratch tests;
removing the lock reddens the race test (3/3 runs, after the sleep-free
sync described in Lessons).

## Lessons

- **A harness can make a concurrency test vacuous.** The first version of the
  race test used the suite's shared `TestClient` and passed WITH THE LOCK
  REMOVED. Measured why: TestClient runs each request on its own fresh event
  loop, so the per-loop lock map handed the two requests different locks and
  they could never contend. That is a harness artifact, not the deployed
  shape (uvicorn serves one process on ONE loop). The test now drives both
  requests as concurrent tasks on a single loop via
  `httpx.ASGITransport`. Generalizes: when a test for a race passes, check it
  can fail before believing it -- and check that the concurrency it sets up is
  the concurrency production has.
- A latch keyed on arrival order ("first caller waits") is itself racy and
  made the test nondeterministic; keying the hold on the request's own data
  (which field it rewrites) made it deterministic.
- **Synchronize a race test on an OBSERVED state, never a wall-clock sleep.**
  The first working version used `await asyncio.sleep(0.2)` to let the second
  request reach the route -- a guess that goes false on a loaded runner
  (fresh-eyes flagged it). It now polls until the second request is
  demonstrably in flight: parked on the lock (fixed) or arrived at the model
  call (unfixed). Both worlds reach the same observed state, which is what
  keeps the lock-removal mutation reddening it -- re-verified 3/3 after the
  change, with 3/3 clean runs restored.

Opus cross-surface round 1: GAPS-FOUND (2), both adopted. (1) The new test
assigned `subprocess.run` directly rather than through `monkeypatch` --
`importlib`-loading llm_providers by path gives a fresh PROVIDER module but
the SAME stdlib subprocess, so the fake leaked process-wide and reddened 5
tests in two untouched files under the root `tests/` suite. Invisible to my
own pre-PR run, which scoped to `backend/tests`. Fixed via monkeypatch and
mutation-verified (restoring the bare assignment reproduces exactly those 5
failures); the trap is now recorded in docs/standards/testing.md, together
with the run-BOTH-roots rule that would have caught it. (2) The lock's
comment credited it with closing a regenerate-vs-`PUT /schema` race it does
not close -- scoped to the truth, pointing at the reviewer's bead
polyglot-pdf-gpghk for the broader unguarded write path. The reviewer also
filed polyglot-pdf-xlvba (uuid4 scratch orphans are never reclaimed on a hard
kill, since the per-call path removed the old pre-existence sweep).

## Doc freshness

No tier-1/2 doc describes the regenerate route's concurrency; the rationale
lives beside the lock and in the scratch-path helper's docstring. The
technical_guide route table's entry for this route is unchanged (its
behavior, auth, and status codes are all the same).

## Files touched

- scripts/bakeoff/llm_providers.py -- `_cli_scratch_path` helper; both CLI
  transports use it
- backend/routes/editor_kit_routes.py -- `_get_guidance_lock` + the route
  split into `_regenerate_guidance_locked`
- backend/tests/unit/test_guidance_regen_serialization.py (new)
- docs/journal/entries/2026-08-07-bd-gnb0-serialize-regenerate-guidance.md
