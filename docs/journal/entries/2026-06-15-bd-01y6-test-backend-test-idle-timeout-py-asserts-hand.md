---
date: 2026-06-15
bead: polyglot-pdf-01y6
title: "test(backend): test_idle_timeout.py asserts hand-rolled mocks, not the real watchdog (uov.9 finding)"
tags: [testing, conventions]
---

## Trigger

Bead polyglot-pdf-01y6, a finding filed during the T2.2 WS-lifecycle audit (bd
polyglot-pdf-uov.9). `backend/tests/unit/test_idle_timeout.py` held four tests
that read as idle-watchdog coverage but were self-fulfilling mocks -- the exact
fake-coverage pattern the spec-driven-test epic exists to catch.

## What shipped

Deleted the four fake tests, keeping the one real one:

- **Removed** `test_idle_timeout_message_sent` (built the idle_timeout payload and
  called `mock_ws.send_json`/`close` itself, then asserted the mock recorded its
  own call), `test_gemini_session_cleanup_on_idle` (called
  `mock_service.end_session()` itself then asserted it ran),
  `test_activity_resets_idle_timer` (asserted `sleep(0.1) < 60` -- tautological,
  no production code), and `test_watchdog_task_cancellation` (defined a LOCAL
  `watchdog_task` and tested asyncio, not the route's). All four stayed green
  independent of the production watchdog.
- **Kept** `test_idle_timeout_configuration` -- the one non-self-fulfilling test
  (the `WS_IDLE_TIMEOUT_SEC == 120` default the watchdog actually reads).
- Added a file header documenting the removal and pointing to the real coverage.

**Delete, not rewrite -- the judgment call.** The watchdog's
send-idle_timeout-then-close-1000 behavior and its session cleanup are now
genuinely covered by
`test_websocket_auth_lifecycle.py::test_idle_watchdog_sends_message_then_closes_1000`
(shipped in uov.9), which drives the REAL `_handle_fill_session` watchdog with a
controllable clock and is mutation-verified. Rewriting the deleted tests would
only duplicate that. The two behaviors the fakes gestured at but did not cover --
activity-resets-the-idle-timer and watchdog-cancellation-on-disconnect -- are not
worth a contrived clock-driven test here; if either warrants a real spec, that is
T3.5 (uov.16)'s call, and this bead blocks uov.16 so the judgment carries forward.

349 backend tests pass (down from 353: the four fakes removed; the real coverage
was already counted). Test-only, no product code changed.

## Lessons

The cheapest honest resolution of fake coverage is often DELETE, not rewrite --
specifically when the behavior is already covered for real elsewhere. Rewriting
every fake test into a real one is a reflex worth resisting: a real test that
duplicates existing coverage adds maintenance cost without adding a guard. The
test to write (or keep) is the one that fails when a DISTINCT piece of production
behavior breaks; if no such gap exists, deletion is the correct, smaller change.
This complements the self-fulfilling-mock entry added to docs/standards/testing.md
in uov.9: that entry says how to SPOT the anti-pattern; this one says the fix is
not always "rewrite it."

## Doc freshness

`docs/standards/testing.md` already carries the self-fulfilling-mock anti-pattern
note (added in uov.9, citing the auth-lifecycle entry); no new doc rule is needed
here -- this bead is the cleanup that note anticipated. The STALE docs closeout
flags track files this branch did NOT touch -- pre-existing drift, not owed here.

## Files touched

- `backend/tests/unit/test_idle_timeout.py` -- removed the four self-fulfilling
  tests; kept `test_idle_timeout_configuration`; added a header documenting the
  removal and the real coverage that supersedes it.
- `docs/journal/entries/2026-06-15-bd-01y6-test-backend-test-idle-timeout-py-asserts-hand.md`
  -- this entry.
