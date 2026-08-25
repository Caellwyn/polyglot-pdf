---
date: 2026-08-24
bead: polyglot-pdf-suwud
title: "docs(audit): risk-rating.md rates disclaimer_routes.py as medium, understating the durable evidence write"
tags: [doctrine]
---

## Trigger

`docs/standards/risk-rating.md` grouped `disclaimer_routes.py` with
`form_kit_routes.py` under one row ("narrower blast radius than the
WS/PDF routes"). That was accurate when the route was log-only; since bd
`polyglot-pdf-0dsv4` it writes durably to the `confirmation_events`
Firestore collection -- the same legal-evidence trail the
irreversible-kit-deletion guard reads -- from an unauthenticated
endpoint, with a client-supplied `form_session_id` reaching the
filesystem as a filename. Filed by the `0dsv4` cross-surface review as a
judgment call about the risk table's own thresholds, not a factual error.

## What shipped

Split `disclaimer_routes.py` into its own row, explaining the med-vs-high
call explicitly rather than asserting it: unauthenticated by deliberate
design, every field bounded at the Pydantic model (bd `polyglot-pdf-g3kui`),
the session-id-as-filename surface guarded again at the sink
(`confirmation_logger._is_safe_session_id`), and the write is fail-open.
Concluded: stays med -- the remaining risk is unbounded write volume (no
auth gate, no rate limit), not a data-shape or path-traversal bug, since
both of those are already closed off. Added the file to the doc's own
`**Tracks:**` line, which had never named it.

## Lessons

**A doc can go unmonitored simply by never being told to watch a file.**
`risk-rating.md`'s freshness check never had a chance to flag this row as
stale -- `disclaimer_routes.py` wasn't in the doc's `**Tracks:**` line at
all, so every commit that changed the route's actual risk profile
(`0dsv4`'s durable write, `g3kui`'s field bounds) was invisible to the
mechanical staleness check. The doc was correct by luck (someone happened
to file a bead about it) rather than by the system that exists to catch
exactly this.

## Doc freshness

`docs/technical_guide.md` is flagged stale for `disclaimer_routes.py`
(from bd `g3kui`'s unrelated merge, not this diff) but its existing
`/api/disclaimer-acceptance` route-table entry is already fully accurate
(unauthenticated by design, durable write, fail-open, session-id
validated as a safe path segment) -- confirmed, no edit needed here.

## Files touched

- `docs/standards/risk-rating.md` -- new row for `disclaimer_routes.py`,
  file added to Tracks line, stamp bumped
