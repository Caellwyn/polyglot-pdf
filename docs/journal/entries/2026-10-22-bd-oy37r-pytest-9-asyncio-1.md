---
date: 2026-10-22
bead: polyglot-pdf-oy37r
title: "chore(deps): upgrade pytest 9 / pytest-asyncio 1.x / pytest-cov 7 test tooling"
tags: [testing]
---

## Trigger

Pinned back by bd niwcu: pytest-asyncio 1.x no longer leaves an event loop installed, so six SYNC tests in backend/tests/test_request_coordinator.py::TestResponseHandlers failed ('There is no current event loop') building asyncio.Future()s.

## What shipped

pytest 9.1, pytest-asyncio 1.4, pytest-cov 7.1 in requirements-dev.txt (never in the image). TestResponseHandlers installs an explicit per-test event loop (autouse fixture) and tears it down; no assertion changed. Full suite under the new tooling: 6763 passed, the same collected count as the old tooling (no silently dropped tests). Two earlier full runs died at the same 57% point with exit 127; a verbose rerun completed cleanly, and the deaths coincided with another branch's run dying at the same moment -- an external interruption, not a test. Hold released.

## Lessons

Pytest-plugin majors change implicit fixtures; tests that relied on a side effect (an installed loop) fail far from the plugin. Compare COLLECTED counts, not only pass/fail.

## Doc freshness

docs/standards/testing.md: its "Dep pins" line updated to pytest 9.1.1 / pytest-asyncio 1.4.0.

## Files touched

- backend/requirements-dev.txt, backend/tests/test_request_coordinator.py
- .github/dependabot.yml, tests/test_dependabot_config.py (hold released)
