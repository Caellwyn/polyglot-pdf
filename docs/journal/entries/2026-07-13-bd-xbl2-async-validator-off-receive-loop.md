---
date: 2026-07-13
bead: polyglot-pdf-xbl2
title: "W1: async backend -- validation off the receive loop + per-window fail-open + batch dedupe"
sprint: 12
tags: [performance, refactor, testing]
---

## Trigger

Sprint-12 epic polyglot-pdf-09da (decoupled async validator; maintainer-approved
plan `docs/sprint_12_async-validator_plan.md`), first child W1. Today the
cross-field contradiction validator runs ONCE, synchronously, inline in the WS
receive loop: the `section_complete` / `form_complete` arms
(`websocket_routes.py`) `await service.handle_validation_boundary(...)` BEFORE the
ack. That blocks the receive loop for the duration of the flash-lite call (bounded
only by `VALIDATOR_TIMEOUT_SEC`), and -- because the per-section trigger is dead in
continuous mode -- a contradiction on page 1 of a 7-page form is not caught until
the whole form is confirmed. W1's job is the BACKEND half of the fix: get
validation off the receive loop and add the machinery the later children (W2
page-end windows, W3 queue/drain) plug into.

## What shipped

The validator now runs OFF the WS receive loop. Every validation trigger acks the
client IMMEDIATELY and spins the flash-lite pass into a tracked `asyncio`
background task; nothing in the voice/tool path awaits it, so a slow or hung
validator adds zero voice-turn latency.

- **`websocket_routes.py`** -- the `section_complete` / `form_complete` arms no
  longer `await` the validator; they call a new `_spawn_validation(...)`
  (fire-and-forget, tracked) then send the ack. `_run_validation_and_push` is the
  background runner: it calls the service, pushes the `validation_result` envelope,
  and is CRASH-SAFE (every exception -- including the validator's own -- is caught
  and logged there, so a background-task failure can never propagate into the
  receive loop). A new `validate_windows` arm is the async page-end trigger W2 will
  emit to: it carries a list of overlapping windows and acks `validate_windows_ack`.
  In-flight validation tasks are tracked in a set and CANCELLED in the teardown
  `finally` (guarded by `locals().get(...)` in case an early error preceded their
  setup) so a lingering task cannot push to a closed socket.
- **`form_filling_service.py`** -- new `handle_validation_windows(windows)`: runs
  one flash-lite call PER WINDOW concurrently (bounded by a semaphore), each with
  its own fail-open + `VALIDATOR_TIMEOUT_SEC`, then DEDUPES conflicts across the
  whole batch by their field-id SET (overlapping windows -- size ~20, stride ~10 --
  make one real conflict surface once per spanning window; the duplication is
  structural). Helpers: `_validate_one_window` (the shared single-window fail-open
  primitive, now reused by the legacy `handle_validation_boundary` too),
  `_dedupe_conflicts_by_field_set` (frozenset key -> order-insensitive),
  `_union_window_fields` (dedupe the windows' fields by id, OR-ing the `steered`
  flag). The existing `_suppress_already_steered` + `_inject_validator_steer` run
  over the window union, so the steer/suppression semantics match the single-window
  path.
- **`config.py`** -- `VALIDATOR_MAX_CONCURRENT_WINDOWS` (default 8) caps the
  concurrent flash-lite fan-out; windows past the cap queue.
- **Wire contract UNCHANGED.** The `validation_result` envelope is still
  `{type, conflicts}` -- W1 changed WHEN it is pushed (async, after the `*_ack`),
  not its shape. An early draft added a `trigger` field to the envelope; I dropped
  it to keep `validation-delegation.md` contract 1 untouched (the field was only a
  test/debug convenience, and widening a governed envelope contract without need is
  churn W3 would have to reckon with).

**Decisions (autonomous, defended):**
- *Convert the existing `section_complete`/`form_complete` arms to async* rather
  than only adding the new `validate_windows` path. The bead explicitly cites
  websocket_routes.py:692/:713 as the inline awaits to remove; the frontend's
  section-switch gate already fails open on its 6s timer and its
  `handleValidationResult` is time-independent, so an async result arriving after
  the ack is safe (verified by reading `webFormConnection.ts`).
- *Kept `handle_validation_boundary` intact* (now a single-window helper, dead in
  the production dispatch path but still test-covered and reusable). Removing it is
  the legacy-path deletion the plan sequences to C7 (bd polyglot-pdf-55jg), not W1;
  keeping the tested single-window primitive is the reversible default.
- *Envelope shape frozen* (dropped the `trigger` field) -- see above.
- *Config knob name/default* (`VALIDATOR_MAX_CONCURRENT_WINDOWS`, 8) -- the bead is
  silent on the format; a reversible config default is mine to pick.

**Assess (Step 5.5).** Exit-criteria rubric scored 3/3 PASS (evidence in the PR
body). Fresh-eyes ran on Sonnet (diff > 80 lines), then Opus for the terminal
clearing round. Sonnet returned `GAPS-FOUND (2)`: (1) the disconnect-cancellation
cleanup had no test, (2) the `VALIDATOR_TIMEOUT_SEC` comment in `config.py` was
stale ("runs INLINE in the WS receive loop"). Both adopted and fixed: added
`test_inflight_validation_is_cancelled_on_disconnect` (proves a blocked task is
cancelled on disconnect and never pushes) and rewrote the comment to the async
reality. A low-confidence third observation -- the contract-test file's local
`_mock_service` still stubbed only `handle_validation_boundary` -- was folded in
too (stub both, preventing a latent trap for a future test). No out-of-scope beads
filed. Adopt 3 / reject 0 / defer 0.

## Lessons

Cancelling an `asyncio` task that has not yet STARTED running does not execute its
body or `except`/`finally` -- so a test that spawns a background task and
immediately disconnects proves nothing about cancellation. The task must be given
a tick to reach its blocking `await` first (a small `hold_open` in the mock WS's
receive loop), then the teardown cancel actually interrupts a running task. This is
general to any "cancelled-on-teardown" test.

## Doc freshness

- **Bumped** `docs/standards/ws-protocol.md` (new `validate_windows` /
  `validate_windows_ack` types; `validation_result` now pushed async after the
  `*_ack`, envelope shape unchanged) and `docs/components/websocket-routing.md`
  (control-message table + validator-results note updated to the async W1 flow).
  Both showed `OK` in the closeout prep after the bump.
- **Reviewed and left** the transitively-flagged stale docs (`si-reduction.md`,
  `stateless-architecture.md`, `terminology.md`, `validation-delegation.md`,
  `voice-and-vad.md`, `technical_guide.md`): they are flagged only because
  `config.py` / `websocket_routes.py` / `form_filling_service.py` fall in their
  `Tracks:` globs, but W1 does not invalidate any of their current-state prose.
  `validation-delegation.md`'s contract-4 section-switch-gate description remains
  accurate -- the deprecated gate still fails open on the async result.

## Files touched

- `backend/routes/websocket_routes.py` -- ack-first + `_spawn_validation`
  background runner (crash-safe); `validate_windows` arm; task tracking + cancel on
  disconnect.
- `backend/services/form_filling_service.py` -- `handle_validation_windows`
  orchestration + `_validate_one_window` / `_dedupe_conflicts_by_field_set` /
  `_union_window_fields` helpers.
- `backend/config.py` -- `VALIDATOR_MAX_CONCURRENT_WINDOWS`; refreshed the stale
  `VALIDATOR_TIMEOUT_SEC` comment.
- `backend/tests/unit/test_validator_windows.py` (new) -- dedupe (order-insensitive),
  per-window fail-open/timeout, concurrency cap, union OR-steered, pure helpers.
- `backend/tests/integration/test_proactive_complete_events.py` -- rewritten for the
  async flow (ack-immediately, slow-validator does not delay the ack/ping,
  background exception never crashes the loop, disconnect cancels an in-flight task).
- `backend/tests/contract/test_websocket_protocol.py` -- `validate_windows` /
  `validate_windows_ack` documented; `validate_windows` added to the
  known-no-FE-sender set; local `_mock_service` stubs the async windows path too.
- `docs/standards/ws-protocol.md`, `docs/components/websocket-routing.md` -- bumped.
