---
date: 2026-09-17
bead: polyglot-pdf-b554d
title: "fix(links): _mirror_budget_exhausted stomps a revoked status, re-opening a revoked link once A3's gate lands"
sprint: 22
tags: [security, testing, hotfix]
---

## Trigger

Bead polyglot-pdf-b554d, filed against the admin-console program (plan:
docs/sprint_22_admin-console_plan.md). websocket_routes.py's
`_mirror_budget_exhausted` -- the socket teardown's best-effort telemetry
write on `links[_<channel>]/{jti}.status` when a client's socket trips its
spend ceiling -- wrote `status=budget_exhausted` unconditionally once its
read confirmed the doc existed, with no check on the status it was
overwriting. That was harmless while `links_store.record_mint()` was the
only writer of the field (the mirror could only ever overwrite `minted`),
but bead A3 (`polyglot-pdf-jecrl`, already landed) added the admin revoke
route (`POST /admin/links/{jti}/revoke`, bd `polyglot-pdf-jmiys`) as the
first non-mint writer, which flips `minted -> revoked`. That makes the
stomp reachable: a client's live socket that later trips
`LinkBudgetExhausted` after staff revoked their link would silently
overwrite `revoked` with `budget_exhausted` -- a status the A3 open gate
(`links_store.OPEN_BLOCKING_STATUSES`) does not refuse an open on, so the
revoked link opens again. The whole point of the revoke route is defeated
by a race the revoking operator cannot see or prevent.

## What shipped

`_mirror_budget_exhausted` now reads the current `status` (it already read
the doc to avoid creating an orphan) and skips the write -- exactly like
the missing-doc case it already had -- whenever that status is already in
`links_store.OPEN_BLOCKING_STATUSES` (`revoked` or `refunded`). This
mirrors `links_store.mark_opened()`'s own terminal-state rule ("a record
already... revoked or refunded is left alone").

Per CLAUDE.md scar #8 (enumerate the set before fixing the instance), also
added a set-derived test
(`test_the_complete_set_of_links_status_writers_all_guard_terminal_states`
in `backend/tests/unit/test_credit_refunds.py`) that AST-scans every
`.py` file under `backend/` and `admin_backend/` (excluding tests) that
references `links_store`, finds every dict literal carrying a `"status"`
key, and asserts the resulting set matches exactly:

- the 5 sanctioned writers, each already internally guarded against a
  terminal current status (`links_store.build_mint_record` -- fresh doc
  only, nothing to stomp; `links_store.mark_opened`; `credit_ledger`'s
  refund status-flip; the admin revoke transaction; and this bead's fixed
  mirror), and
- 3 allowlisted non-writers (an HTTP response body and an audit-log
  payload that happen to construct a dict with a `"status"` key but never
  touch the links doc), each with its own documented reason.

A new, unguarded writer -- including the plan's still-unbuilt
`opened`/`completed` mirrors -- will fail this test by name (file +
function) instead of a review round finding it one increment at a time,
which is the exact failure shape CLAUDE.md's scar #8 names as the largest
source of review rounds in this repo.

## Lessons

A best-effort mirror that reads-before-write to avoid one hazard (creating
an orphan doc, in this case) is a natural place to also close a second,
unrelated hazard (overwriting a terminal state) for free -- the read
already happened; only the branch on its result was missing. When a
finding names sibling writers explicitly (as this bead's description did),
enumerate them mechanically (AST/grep) rather than trusting the hand-list,
even when the hand-list turns out correct: the AST scan here surfaced 3
additional dict literals with a "status" key that were NOT status writers
at all (an HTTP response body, an audit-log payload) -- false positives
that needed their own documented reasoning to allowlist, which is exactly
the kind of adversarial check a set-derived test earns for free on its
next run.

## Doc freshness

- `docs/components/auth.md` (Tracks: ... backend/services/links_store.py
  backend/routes/websocket_routes.py ...): prose update to the
  `_mirror_budget_exhausted` paragraph describing the terminal-state skip,
  plus a new paragraph naming the complete pinned writer set. New
  `*Last updated: 2026-09-17*` line added at the top of the stack.
- `docs/components/websocket-routing.md` (Tracks: ...
  backend/routes/websocket_routes.py ...): one-line stamp bump noting the
  internal helper fix is not a WS protocol change, pointing to auth.md for
  the full contract.
- Both confirmed OK by `scripts/check_doc_freshness.py` after the edit.
- Reviewed (not bumped) six more docs whose Tracks: line covers
  backend/routes/websocket_routes.py and that closeout_prep also flagged
  STALE purely because editing that file bumped its mtime:
  hipaa-pii-policy.md, risk-rating.md, security-posture.md,
  stateless-architecture.md, voice-and-vad.md, ws-protocol.md. None
  document anything this change touches (the fix is internal to
  `_mirror_budget_exhausted`'s Firestore write, not PII logging, risk
  rating, the WS wire protocol, VAD/turn-taking, or the stateless-backend
  invariant) and none needed a prose change -- left as-is per closeout
  triage ("stale docs you did not touch -> leave and note"; these were
  reviewed, just not substantively touched).
- Other STALE docs the checker reported that track files this bead did
  not touch at all (admin-service.md, config-deployment.md, voice-ai.md,
  ai-models.md, bead-tiers.md, logging-and-cost.md, terminology.md,
  testing.md, technical_guide.md -- the last exempt from a stamp by
  design) were left as-is, unrelated to this bead's diff.

## Files touched

- `backend/routes/websocket_routes.py` -- the terminal-state guard in
  `_mirror_budget_exhausted`.
- `backend/tests/unit/test_credit_refunds.py` -- updated the existing
  mirror tests' fake snapshot to supply `to_dict()`; added the
  parametrized terminal-status guard test; added the set-derived writer
  enumeration test.
- `docs/components/auth.md`, `docs/components/websocket-routing.md` --
  current-state prose + stamp updates.
