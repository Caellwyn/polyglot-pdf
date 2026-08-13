---
date: 2026-08-12
bead: polyglot-pdf-oqqxj
title: "Bug-hunt bundle: text-client cache lock, K_SERVICE test isolation, ackSha1 parity fixture"
sprint: null
tags: [testing, concurrency, conventions]
---

## Trigger

Maintainer-requested bug-hunt roundup: find easy, single-surface beads and
close a few. Bundled three unrelated small bugs into one PR since none
individually warranted a full review cycle -- explicitly a low-lying-fruit
sweep, not epic work.

Also found (and left alone): the five certification-denylist beads (6u6h,
4qu2, dhds, px13, 4mqw) are correctly self-documented as blocked -- their
target file doesn't exist on `dev` yet, only on an unmerged branch. Skipped
per the bead's own note rather than re-verifying from scratch.

## What shipped

1. **bd polyglot-pdf-oqqxj / bd polyglot-pdf-ioe8d** (duplicate beads, same
   root cause): `backend/dependencies.py`'s `_cache_get_or_build` mutated
   `_TEXT_AI_CACHE` from worker threads with no lock -- duplicate ~3s builds
   on a cold cache, or a `KeyError` on a hit-path read racing a concurrent
   eviction.
2. **bd polyglot-pdf-5xhbb**: `backend/tests/conftest.py` had no fixture
   isolating `K_SERVICE`, so a bare `Settings()` in a test inherited the
   ambient shell's value, silently flipping two fail-closed guards
   (VERTEXAI, VFF_DISABLE_AUTH) under a Cloud-Run-like environment.
3. **bd polyglot-pdf-eh2i**: `test_publish_readiness.py`'s parity harness
   had fixture-coverage gap -- the double-pop bug the bead described was
   already fixed in the same commit that introduced the file, but no
   fixture case exercised a LITERAL (non-`@identity`) `ackSha1`, so nothing
   pinned the fix.

## Scar tissue

**1. A "fix" that closes one race can open a narrower one in the same
function.** The cache lock went through three internal shapes before
landing, each caught by the next review round:

- v1: one continuous critical section around check+build+return. Correct
  for the KeyError race, but holds the lock across the ~3s `build()` call
  itself -- which SERIALIZES two keys (`text_ai`, `text_ai_pro`) that
  production builds concurrently via `asyncio.gather`. The outer
  cross-surface review measured this: ~0.85s vs ~0.49s with 0.3s fake
  builders. A "correct" fix regressed the exact latency win (bd 4hnyq,
  9.4s->3.2s) the caching existed to protect -- and the test suite didn't
  catch it, because no test measured concurrent-DIFFERENT-key timing
  (only same-key duplicate-build counting and a same-key hit-path race).
- v2: per-key IN-PROGRESS PLACEHOLDER (a `_BuildInProgress` object holding
  a `threading.Event`), lock held only for dict bookkeeping, released
  during the actual build. Closed the serialization regression. But a
  SUBSEQUENT fresh-eyes round found: cross-key eviction on overflow wiped
  an unrelated key's IN-PROGRESS placeholder, so a later caller for that
  (still-building) key saw the cache empty and started a duplicate build
  -- the ORIGINAL bug, reopened through eviction instead of no-lock.
- v3: evict only FINISHED entries, never in-flight placeholders. This
  makes the size bound soft during a concurrency burst (self-heals on the
  next miss) -- verified acceptable because production's real key space is
  ~2 entries (`get_settings()` is `@lru_cache(maxsize=1)`, so eviction
  never fires at all in a deployed instance); the overshoot is only
  reachable by a test harness building many distinct configs concurrently.

Three review rounds on ONE function, each one closing the true race while
introducing (or exposing) the next-narrower one. The fix that "obviously
works" the first time you hold a lock is rarely the one that survives
someone measuring the thing the lock was never supposed to touch.

**2. Timing-based concurrency tests can go green for the wrong reason.**
The first version of the round-2 gap's regression test used many concurrent
threads and hoped the scheduler would interleave badly enough to expose the
race. It didn't reliably -- 5/5 clean runs even against the flawed code. The
round-3 test instead used `threading.Event`s to force the EXACT interleaving
deterministically (block a builder mid-build, trigger an eviction from a
different key, then start a second caller for the blocked key). Only the
deterministic version caught the bug reliably; only the deterministic
version is trustworthy as a regression pin. A concurrency test that merely
"usually" reproduces a race is not proof the fix works -- the same
mutation-verify discipline this repo already applies to ordinary logic
(revert the fix, watch the test go red) applies doubly to timing-dependent
tests: if a race test can pass on the KNOWN-BROKEN code even once, force
the interleaving explicitly instead of hoping the scheduler cooperates.

**3. Collection-time exposure is a different attack surface than test-time.**
The first K_SERVICE fix (a per-test autouse fixture) is invisible to pytest
COLLECTION -- several test files import `backend.main` at module scope,
which resolves `Settings()` while pytest is still discovering test files,
before any fixture has ever run. An autouse fixture cannot protect against
a failure that happens before fixtures exist. The real fix needed a
module-level statement in `conftest.py` (runs at import, ahead of
collection) -- and pytest.ini's SECOND testpath (`tests/`, the
harness-tooling suite) doesn't share `backend/tests/conftest.py` at all, so
it needed its own copy of the same guard. Two testpaths in one `pytest.ini`
is two exposure surfaces, not one.

## Review record

Four inner fresh-eyes rounds (1 gap, then NO-GAPS, then 1 more gap from the
same function, then NO-GAPS) and two outer Opus cross-surface rounds (3
gaps: the serialization regression, the collection-time exposure, one docs
staleness; then NO-GAPS). Every finding across both layers was a genuine,
reproduced behavior gap -- none were false positives, and none required
escalation. All fixes were mechanical once located: the hard part in every
round was the review agent actually MEASURING the regression (wall-clock
timing, a forced thread interleaving, a live collection-abort repro) rather
than reasoning about it from the diff.
