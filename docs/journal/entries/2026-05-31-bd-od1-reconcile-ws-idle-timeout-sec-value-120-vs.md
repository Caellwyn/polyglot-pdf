---
date: 2026-05-31
bead: polyglot-pdf-od1
title: "Reconcile WS_IDLE_TIMEOUT_SEC to 60 (value/comment/tests now agree)"
tags: [testing, conventions]
---

## Trigger

`polyglot-pdf-od1` (surfaced by Copilot on PR #16): `backend/config.py` set
`WS_IDLE_TIMEOUT_SEC = 120`, but its inline comment said "60s" and three test
assertions expect `== 60` (`test_idle_timeout.py:111`,
`test_idle_timeout_flow.py:49,81`). These three failures were the persistent red
in every test run across this session's earlier closeouts (4cm), so settling the
intended value also cleans the suite.

## What shipped

**Determined the intended value is 60, not 120.** `git blame -L` on the line shows
it was originally `60` (matching comment + tests) and a single commit (`b9eac1e`)
bumped it to `120` without touching the comment or the tests — the signature of a
drift, not a deliberate config change. Every *other* source agrees on 60:
`docs/releases/heartbeat_keepalive.md`, `planning_documents/TECHNICAL_GUIDE.md`,
and the archived guide. Restored `WS_IDLE_TIMEOUT_SEC = 60` as the single source
of truth; value, comment, and all three tests now agree.

**Confirmed the CI gap behind the drift.** The bead asked whether `backend/tests/`
runs in CI. Answer: **no CI runs the suite at all** — there is no
`.github/workflows/` (only `.github/*-instructions.md`), and `gh run list` shows
only Copilot review runs, never a pytest job. So the 155+ tests run only locally,
on demand, which is exactly why the 60/120 drift went unnoticed. Filed
**bd polyglot-pdf-r19** to wire pytest into CI as a required status check (its own
work, overlaps the deploy-gate bead `4r1`).

**Tests:** full non-external suite now **158 passed, 0 failed** (was 3 failing).
The earlier "import error at collection" the bead noted did not reproduce — the
idle-timeout suite collects and passes 9/9 when run with `PYTHONPATH=<repo-root>`
(the bare `pytest tests/` from `backend/` mis-collects; see closeout notes).

**Review (fresh-eyes):** _(filled at Step 8 after triage)_

## Lessons

- A constant whose **inline comment and tests both disagree with its value** is
  almost always a drift introduced by an edit that moved the value alone — `git
  blame -L <line>,<line>:<file>` settles intent fast. Trust the convergent sources
  (comment + tests + docs), not the lone outlier.
- **Tests that aren't in CI are tests that silently rot.** This drift survived
  because nothing ran the suite on a gate. Tracked the fix in `polyglot-pdf-r19`.

## Doc freshness

- `docs/technical_guide.md`: the env-var prose previously cited
  `WS_IDLE_TIMEOUT_SEC` *without a number* (deliberately, pending this bead) and
  described the 120/60/tests disagreement as open. Updated to state the resolved
  value (`60`) and drop the now-stale "tracked in od1" note. (No `**Tracks:**`
  line, so the freshness checker skips it; bumped by hand.)
- `check_doc_freshness.py`: clean for all tracked tier-1/tier-2 docs.

## Files touched

- `backend/config.py` — `WS_IDLE_TIMEOUT_SEC` default 120 -> 60
- `docs/technical_guide.md` — env-var prose: state the resolved value, drop the open-issue note
