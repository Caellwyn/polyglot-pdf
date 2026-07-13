---
date: 2026-07-13
bead: polyglot-pdf-pr3i
title: "W3: validatorFindingsQueue + finding-driven drain -> oiok steer composer"
sprint: 12
tags: [refactor, testing]
---

## Trigger

Sprint-12 epic 09da (decoupled async validator), child W3 -- the payoff task that
ties W1 (async backend) + W2 (stride windows) into the finding-driven correction
loop. The report-cadence revision (bd c3uo) set the shape: report a contradiction
to the voice model ONLY when one exists (a voice turn is expensive), for all forms,
not at a page/section/form boundary.

## What shipped

The validator is now finding-driven end to end: a contradiction is voiced the
moment its window verdict lands, and a clean check spends zero voice turns.

**The core architectural change -- who injects the steer.** W1's
`handle_validation_windows` used to compose + inject the steer itself and return
the delivered conflicts. W3 splits that: the windows path is now REPORT-ONLY (it
returns the surviving conflicts, each with a `field_names` id->name rider, and
injects nothing), and steer injection moves to a new client-driven
`drain_findings` round-trip. This is deliberate and matches the plan: the CLIENT
owns the finding queue (the stateless-backend invariant + it owns the
`steered`-marker + W4's re-arm lifecycle), so the client must own WHEN to report.

Flow:
- Backend `validation_result` (report-only) carries the surviving conflicts.
- FE `handleValidationResult` ENQUEUES them into a new persisted
  `validatorFindingsQueue` (dedupe by field-id set; a clean result enqueues
  nothing) and, if the queue grew, sends `drain_findings` immediately.
- Backend `drain_findings` arm -> `handle_drain_findings` composes ONE steer via
  the shipped oiok composer (`_compose_validator_steer`) + injects it off the
  receive loop, replies `drain_findings_result` with the DELIVERED conflicts.
- FE marks those fields `steered` and CONSUMES them from the queue only on the
  drain result -- so an un-delivered steer (dead session) keeps the finding queued
  to retry, and a field is never marked steered for a steer the model never heard.
- The queue is client-owned + persisted, so it survives a reconnect;
  `handleSessionReady` re-drains a surviving queue.

**Surfaces.** backend/services/form_filling_service.py (report-only windows +
`handle_drain_findings`); backend/routes/websocket_routes.py (`drain_findings`
arm + background runner, reusing the validation task set for disconnect cleanup);
frontend/src/schema-forms/types/schema.ts (`ValidatorFinding` type);
frontend/src/schema-forms/state/schemaFormState.ts (`validatorFindingsQueue` +
`enqueueValidatorFindings`/`consumeValidatorFindings`, mirroring the W2
persistence pattern); frontend/src/webFormConnection.ts (enqueue + `drainFindings`
+ `handleDrainFindingsResult`, wired on the result + reconnect seams).

**Decisions (autonomous, defended):**
- *validation_result becomes REPORT-ONLY.* This changes a contract W1 just shipped,
  but it is exactly what the approved report-cadence-revision plan directs (the
  client-queue -> drain_findings -> backend-composer flow is spelled out there), so
  it is derivable from the plan, not a new direction -- mine to implement.
- *Steer marked/consumed on the drain RESULT, not on the drain send.* An
  un-delivered steer must not mark a field steered (it would suppress a real
  re-steer forever) -- delivery confirmation gates both the marker and the consume.
- *field_names rides each conflict* (from the report-only windows path) so the
  client's drain payload carries the names the composer needs without re-deriving
  them from schema.
- *The probe (probe_validator_rail.py) is documented, not re-run.* It drives the
  same `_compose_validator_steer` + inject the drain path runs, so its live rail
  assertion still proves the drain path's behavior; the report-only enqueue/drain
  round-trip is covered deterministically by the FE + drain service tests. No live
  spend incurred (dry-run wiring verified).

## Lessons

When a client-owned queue drives a backend side effect, gate the queue-consume +
any client-side "done" marker on the backend's DELIVERY confirmation, not on the
send. Consuming optimistically (on send) loses the finding if the side effect
silently fails; marking optimistically (steered-on-send) permanently suppresses a
legitimate retry. The round-trip's result message is the only safe consume/mark
trigger.

## Doc freshness

- **Bumped** docs/standards/ws-protocol.md (new `drain_findings` /
  `drain_findings_ack` / `drain_findings_result` types; `validation_result` now
  report-only + gains a `field_names` rider), docs/components/websocket-routing.md
  (control-message table + validator-results note), and
  docs/standards/validation-delegation.md (contract 1: the async path's steer now
  routes through the drain, not the result).
- **Reviewed and left** the other transitively-flagged stale docs (config,
  context-compression, jit-schema, si-reduction, etc.): flagged only by
  config.py/form_filling_service.py mtimes, prose not invalidated by W3.

## Files touched

- backend/services/form_filling_service.py -- handle_validation_windows report-only
  (+ field_names rider) + new handle_drain_findings.
- backend/routes/websocket_routes.py -- drain_findings arm + _run_drain_and_push /
  _spawn_drain background runner.
- backend/scripts/probe_validator_rail.py -- W3 drain-path note (rail unchanged).
- backend/tests/unit/test_validator_windows.py -- windows path now report-only
  (no inject) assertions.
- backend/tests/unit/test_drain_findings.py (new) -- drain-path compose/inject,
  batching, fail-open (undelivered/dead-session/raise).
- backend/tests/integration/test_proactive_complete_events.py -- drain_findings arm
  ack + result-push tests.
- frontend/src/schema-forms/types/schema.ts -- ValidatorFinding type.
- frontend/src/schema-forms/state/schemaFormState.ts -- validatorFindingsQueue
  (interface/init/save/load) + enqueue/consume ops.
- frontend/src/webFormConnection.ts -- enqueue-on-result + immediate drain +
  drain-result mark/consume + reconnect re-drain.
- frontend/src/webFormConnection.validatorsteer.test.ts -- updated for the W3 flow
  (steer marks on the drain result).
- frontend/src/webFormConnection.drainfindings.test.ts (new) -- enqueue/drain/consume
  /clean-no-drain/dedupe/reconnect E2E.
- frontend/src/schema-forms/state/schemaFormState.findingsqueue.test.ts (new) --
  pure queue-op unit tests.
- docs/standards/ws-protocol.md, docs/components/websocket-routing.md,
  docs/standards/validation-delegation.md -- bumped.
