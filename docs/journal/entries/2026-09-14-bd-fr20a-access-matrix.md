---
date: 2026-09-14
bead: polyglot-pdf-fr20a
title: "test(auth): C1 route/gate matrix + cross-tenant access tests, HTTP and WS (sprint 23)"
tags: [security-audit, testing, auth]
---

## Trigger

Sprint 23 (the security + data-leak audit, epic `polyglot-pdf-uijam`, plan
`docs/sprint_23_security-audit_plan.md`), workstream C1, threat actors T1
(anonymous caller) and T2 (authenticated wrong-tier user). The existing
route pins (`test_http_route_auth.py`, `test_admin_route_auth.py`) proved
every route CARRIES a gate; nothing proved what each gate ANSWERS to each
kind of caller, and nothing exercised the WebSocket at all. Built by a
Sonnet builder in an isolated worktree; the orchestrator ran the review
loops and closeout.

## What shipped

Two new test files, no production code:

- `backend/tests/integration/test_access_matrix.py` (29 tests). Derives the
  HTTP route set from the live `app.routes` graph (importing the existing
  pins' helpers, not copying them) and asserts the expected status for
  nine actors -- anonymous, firm-A employee, firm-A manager, firm-B
  manager, client link for firm A, client link for firm B, editor,
  claimless Firebase token, app admin -- across every route. Every
  registered route must be gated by a recognised dependency, listed in
  `_DELIBERATELY_UNGATED_HTTP_ROUTES`, or belong to the editor surface, or
  the suite fails. Three WebSocket cases over `websocket_connect` with
  patched verifiers: anonymous is refused BEFORE accept; a firm-B link
  naming a firm-A kit closes 1008 `link_kit_mismatch`; and a tripwire
  pinning a REAL GAP (below).
- `admin_backend/tests/unit/test_access_matrix.py` (15 tests). Same shape
  over the admin service's five gates; proves a manager cannot read
  another firm's links, users or usage, an employee cannot revoke, and an
  editor-role token cannot reach admin.

Mutations (builder, re-run by fresh-eyes): five gate removals/swaps and two
WS-branch disables each turned exactly the right tests red; a
self-test registers a throwaway ungated route and proves the
classification check catches it.

## The gap the matrix found

A STAFF Firebase token's handshake `kit_id` is never scoped to the
caller's firm on `/ws/fill`: `kit_gates.require_visible` /
`firm_allowed_kits` are never called in `websocket_routes.py`, and the
only kit check (`link_kit_mismatch`) runs inside the client-link branch.
A firm-A manager naming a firm-B private kit reaches `session_ready`. The
socket serves no kit bytes (the schema rides the client's own handshake
and the HTTP schema/pdf reads ARE gated), so this is record and telemetry
integrity plus defence in depth rather than store access -- but it is
exactly the refusal the plan's criterion 3 required. Pinned as CURRENT
behaviour by `test_ws_a_STAFF_token_naming_a_kit_outside_its_firm_is_NOT_refused`
(its docstring says to invert it when the gap closes); the fix is folded
into bead C2 (`polyglot-pdf-bwevj`), which owns `websocket_routes.py`.

## Link-token and redemption review (the bead's second deliverable)

- `iat` unchecked: non-issue -- nothing downstream reads it and the whole
  payload is HMAC-signed; `exp` is the only time check.
- `jti` entropy: non-issue -- 128-bit CSPRNG, pinned by `test_link_tokens.py`.
- Secret-rotation runbook: real gap -- the doc states only the consequence
  and there is no key-version claim, so rotation is an all-at-once
  cutover. Filed `polyglot-pdf-jx5u9`.
- `open_link()` reopen check is a non-transactional get-then-set that can
  race `complete_link()` and admit one extra paid session at the boundary.
  Filed `polyglot-pdf-mzhrp` (P3).

The full route/gate table for both services is on the bead's notes, for
workstream G's posture doc.

## Review record

**Fresh-eyes (sonnet): one round, GAPS-FOUND (0)** with one comment fix
adopted: the ungated allowlist carried a dead un-prefixed
`/disclaimer-acceptance` entry and a comment claiming a double mount that
does not exist (the router carries `prefix="/api"` itself). Two non-bugs
recorded there so nobody rediscovers them: the admin file samples four of
five gate names because no admin route carries `require_firm_manager`;
and no separate `author` actor exists because the voice-app gates never
read the editor-role claim, so author and editor are indistinguishable
there.

**Opus cross-surface review:** one round, NO-GAPS. Three findings, all filed rather than blocking: the CI failsafe classifies the 27 `/api/editor/*` routes by module name, so an ungated editor route would ship green (`polyglot-pdf-18rpl`, editor-surface work outside this bead); the client-link cross-kit row 404'd on a kit the fixture never defined, so it never reached the visibility gate it claimed to pin (`polyglot-pdf-uosul` -- fixed in this PR instead: the second kit is now a real private firm-A kit and the row goes red when `firm_allowed_kits`' client-link narrowing is removed); and one admin unit test spends ~4 s in credential discovery because it deliberately runs the real verifier (`polyglot-pdf-fpyfx`, pre-existing). The reviewer's own gate-removal mutation ran a real admin route body against the project and created a stray Firebase user; reported to the maintainer for deletion and recorded on `fpyfx`, since a unit test that can reach the real project when a gate is removed is the underlying hazard.

**Housekeeping reviewed and left:** other sessions' in-progress beads; the
stale-doc flags are all for files this branch did not touch. The prep
script's suite gate timed out under machine load (four parallel runs);
the suite was re-run directly: 6096 passed.

## Lessons

- **A matrix over the LIVE route table finds what a hand-listed one
  cannot.** The staff-kit gap was invisible to every existing pin because
  those asserted "a gate is attached", not "the gate refuses this caller".
- **Pin a discovered gap as a tripwire, not as a skip.** A `pytest.skip`
  would have hidden it; a test that asserts the current wrong behaviour
  and says so in its docstring fails the moment someone fixes it, so the
  fix and the pin travel together.
- **When the bead says "record verdicts", write the non-issues down too.**
  Two of the four review items were non-issues; recording why saves the
  next auditor the same trace.

## Doc freshness

Bumped: none needed -- `docs/standards/testing.md` and
`hipaa-pii-policy.md` track test globs but their claims are unchanged by
two new test files; the route/gate table lands in workstream G's
`security-posture.md`, which owns that surface.

## Files touched

- backend/tests/integration/test_access_matrix.py -- HTTP + WS matrix (new)
- admin_backend/tests/unit/test_access_matrix.py -- admin matrix (new)
- docs/journal/entries/2026-09-14-bd-fr20a-access-matrix.md -- this entry
