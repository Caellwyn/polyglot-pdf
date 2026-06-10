---
date: 2026-06-10
bead: polyglot-pdf-bxw
title: "WS-E1: keyed RequestCoordinator slots (request_id -> future)"
tags: [refactor, testing]
---

## Trigger

WS-E part 1 of the voice round-trip hardening epic (`polyglot-pdf-wpw`).
`RequestCoordinator` tracked each pending frontend round-trip in ONE slot PER
request TYPE (`_pending_next_field_request`, `_pending_field_value_request`,
etc.). Two overlapping requests of the same type clobbered: the second
overwrote the slot, the first's future was orphaned (its caller hung to
timeout), and the first response to arrive resolved whichever future currently
held the slot -- a cross-resolve. WS-E1 makes same-type concurrency safe; it is
also the prerequisite for relaxing `0c1`'s switch lock (plan hazard 4) and for
WS-E2's synchronous confirm_field.

## What shipped

`backend/services/request_coordinator.py`: replaced the four single-slot fields
with one `self._pending: Dict[str, Dict]` keyed by `request_id`. Each request
registers its own future; each handler (or a timeout) pops by id. Three private
helpers centralize the bookkeeping: `_register` (new id + future), `_discard`
(drop on send-failure/timeout/error), and `_resolve` (resolve by id, only if the
entry is of the EXPECTED type -- a response whose id maps to a different type is
never cross-resolved).

**Behavior preserved** so consumers (`callback_handler`,
`form_filling_service`) need no changes: every public method signature; the
per-request timeouts (5s form_state/section_info, 2s next_field/field_value);
the `HINT_REQUEST_TIMEOUT` sentinel; the `strip_field_id_from_hint` applied in
the next-field handler.

Tests (red-first, in `backend/tests/test_request_coordinator.py`): two concurrent
same-type requests resolve to their OWN callers (`len(_pending) == 2` is
impossible under the old single slot, so it is a genuine red gate); a wrong-type
response does not cross-resolve; a mismatched id leaves the genuine future
intact. The existing handler-internals tests were updated from poking the
removed `_pending_*` fields to seeding the keyed map. 239 backend tests pass.

Fresh-eyes triage: recorded in the merge ping (this entry predates the review).

## Lessons

- **A single slot per "kind" is a latent clobber the moment two of that kind
  overlap.** The fix is to key by the correlation id the protocol already
  carries (`request_id`) rather than by a coarser bucket. Keying also lets the
  resolve path reject a wrong-type response instead of silently honoring it.
- **A refactor that keeps the public surface identical is the cheapest to land**
  -- the consumers were untouched, so the blast radius is the one file + its
  tests.

## Doc freshness

`tool-call-flow.md` was the only doc flagged (it `Tracks:`
`request_coordinator.py`). It references the coordinator only via the
`HINT_REQUEST_TIMEOUT` sentinel behavior -- which this refactor preserves
unchanged -- and does not describe the internal slot mechanism, so its
current-state prose is still accurate. Reviewed and left as-is. (Note: this
branch is off `dev` and predates the `0c1` PR's `tool-call-flow.md` update, which
is unrelated to the coordinator section.)

## Files touched

- `backend/services/request_coordinator.py` -- keyed `_pending` map +
  register/discard/resolve helpers.
- `backend/tests/test_request_coordinator.py` -- clobber + cross-resolve +
  mismatch tests; existing tests adapted to the keyed map.
