---
date: 2026-09-09
bead: polyglot-pdf-e4dt8
title: "feat(telemetry): E3.8 Error Reporting shape (type + frames, never the message), WS close-code events, monitoring script"
sprint: 22
tags: [security, testing, conventions]
---

## Trigger

Epic 3 bead 8 of the admin-console program (plan:
`docs/sprint_22_admin-console_plan.md`, "Errors"). The console needs an errors
view and the operator needs alerts, and neither could be built on what the app
was emitting.

Two things were in the way, and they turned out to be the same shape of
problem.

**The exception message was a P0 PII leak with a local fix.** structlog's stock
`format_exc_info` processor renders the exception MESSAGE into the JSON output.
In a form-filling app that message routinely embeds a field value -- a parse
error over an A-number, a validation error naming a date of birth -- and it
goes to stdout, Cloud Run, Cloud Logging. bd `polyglot-pdf-p84m` found this and
fixed it at two call sites in `live_ai_gemini.py`: they were rewritten to log
`error_type=type(e).__name__` and their `self._log.exception(...)` was gated
behind `DEV_LOGGING_ENABLED`. Every OTHER `.exception(...)` / `exc_info=True`
site under `backend/` kept rendering the message straight through. That is
CLAUDE.md scar #8 exactly: one instance of a set fixed, the set never
enumerated.

**Closes had no countable shape.** The `/fill` route closed eight different
ways. Some lines carried the close code, some carried only a prose reason, and
the schema and source rejections carried neither. Cloud Monitoring's log-based
metrics count log ENTRIES matching a filter, so no single filter could count
"the 1013s" and no alert policy could fire on a rate.

## What shipped

### The processor swap

`backend/utils/logging.py` now runs `pii_safe_exception_processor` in place of
`format_exc_info`. It emits `error_type` (the class name, queryable on its
own), `stack_trace` (frames as file/line/function plus each chained
exception's TYPE), and `severity` (the level, uppercased). No message, no
locals, no source text. The `__cause__` / `__context__` chain is walked, capped
at 5 links and 30 frames each.

Fixing it at the PROCESSOR rather than at the call sites is the whole point:
structlog has one global chain, so the guarantee holds for every site by
construction rather than by each author remembering. `EXCEPTION_LOGGING_SITES`
registers the files that log exceptions, and the test re-derives that set from
the AST so an addition is visible at review.

That shape is also what Cloud Error Reporting GROUPS on. The previous
`error_type`-only line was PII-safe but ungroupable -- Error Reporting showed
nothing and an operator was back to grepping. A file path, a line number and a
function name are repository facts, not user data.

The message is DROPPED, not scrubbed. The value arrives as arbitrary user
speech, so no pattern covers it; only a wholesale drop cannot be defeated by an
input. Developers who need it have the `.env.DEV`-gated file log.

Because `.exception(...)` is now safe everywhere, the two `DEV_LOGGING_ENABLED`
branches in `live_ai_gemini.py` collapsed. The stderr `traceback.print_exc()`
block STAYS dev-gated -- it bypasses structlog entirely, so the processor
cannot protect it. That distinction is the interesting half of the change.

### Counted close events

`StructuredLogger.log_ws_close` (the wiring the previously-unwired `log_error`
was waiting for) emits every close as a `ws_error` event carrying
`metadata.close_code` and a fixed `metadata.reason_token`, at a severity
DERIVED from the code via a module-level table -- so two call sites cannot
disagree about how bad a 1013 is.

Non-exception on purpose: a close is a control-plane outcome with no traceback,
and routing thousands of frame-less entries into Error Reporting would drown
the real crashes.

`websocket_routes._close_ws` wraps every close on `/fill` and never raises -- a
telemetry failure on a teardown path must not turn a clean refusal into a 500.
The per-site structlog lines stay alongside; they carry context
(`not_enrolled`, the mismatched kit ids, the `jti`) a generic close event has
no field for.

The 1011/1006 family is emitted from `live_ai_gemini.py` instead, because it is
a GEMINI-side close the route only ever learns about second hand, and the
adapter's except block is the one place the code is read off the wire. Only the
spontaneous-drop codes are counted: a normal end and a GoAway expiry arrive
through that same block, and counting them would make the metric fire on every
healthy session.

### Fresh-eyes round: the wire reason the wrapper quietly changed

Adopted (1 blocker). `_close_ws`'s `reason` kwarg defaulted to `reason_token`,
so the five sites that previously called `websocket.close(code=X)` with NO
reason kwarg -- 1003 `handshake_not_text`, 1007 `handshake_json_decode`,
1007 `handshake_not_object`, 1007 `schema_missing`, 1008
`invalid_schema_source` -- silently began putting a string on the wire that
the peer had never received. The builder's own changed-contracts claim said
every close reason was byte-identical; it was not.

The trap is that the wrapper takes two same-looking strings: `reason_token` is
telemetry-only, `reason` is the bytes the client sees. Defaulting one to the
other collapsed the distinction the docstring was drawing. The default is now
`""` -- exactly what a bare `websocket.close(code=X)` sends -- and the two
sites that DID rely on the old default for their wire string (1013
`budget_exhausted` / `budget_unavailable`) now state it explicitly. Every wire
reason is once again byte-identical to `origin/dev`.

Nothing caught this, which is the real finding: every existing close assertion
checks `code` and none checks `reason`. Three tests now pin it
(`test_ws_close_events.py`) -- the empty default as a mechanism, and the
per-site wire reason in BOTH directions, since `webFormConnection.handleClose`
does a strict `event?.reason === "budget_exhausted"` compare whose sibling
`budget_unavailable` must NOT match it. Mutation-verified against four
mutations, including restoring the exact original bug.

Adopted (1 nit): a spurious `# noqa: E501` on a short signature in
`tests/test_setup_telemetry_script.py`, introduced by this diff.

Deferred (2, both pre-existing and filed): `polyglot-pdf-5di76` (the ~100-site
`error=str(e)` kwarg leak, the same shape this bead fixed for `.exception()`
but reached by a different code path) and `polyglot-pdf-7lmdr`
(`firms_store_status`'s probe can wedge permanently if a non-`Exception`
escapes before `in_flight.set()`).

### scripts/setup-monitoring.sh

Operator-run and declarative, sibling of `setup-telemetry.sh`. Three log-based
metrics, two alert policies (5xx rate, 1011 rate, both `ALIGN_RATE`), and one
uptime check per CHANNEL on `/health` -- demo, staging and admin each get their
own, because staging and demo run different code on the same project and a
shared check would either miss a broken demo or page on a staging channel that
is expected to be broken.

`roles/errorreporting.viewer` and `roles/monitoring.viewer` move out of the IAM
envelope test's `DEFERRED_ROLES` in the same commit, with a test that the
script actually GRANTS them. `polyglot-backend-sa` gains neither, pinned
negatively.

`setup-telemetry.sh`'s sink filter gained `ws_error` in its nested clause --
which that script's own header had predicted this bead would need to do, and
the prediction held exactly.

### /health

`firms_store_status()` is wired in, closing bd `polyglot-pdf-vq5wd`. Its own
docstring had named the precondition: `/health` is unauthenticated, so the
wiring bead must add the cache, the in-flight coalescing and the `wait_for`
bound first. All three landed. The two probes get separate budgets, so a
stalled firms store cannot eat the sink probe's answer.

## Lessons

**A source-level guard is structurally blind to a render-time leak.**
`test_no_pii_logging.py` is a good grep guard and it could never have caught
this: the leaking call is `self._log.exception("tool_callback_error",
tool=tool_name)`, which has no sensitive kwarg to grep for. The PII arrives
from the processor chain, after the source is out of the picture. The doc's own
"remaining blind spot is the sink/shape" paragraph described this exact case;
it took a bead to notice that the paragraph was a bug report.

**A test that derives its expectation from the thing under test asserts
nothing.** The first version of the close-severity test parametrized over
`WS_CLOSE_SEVERITY` itself. Flipping 1011 to WARNING flipped the expectation
with it and all 12 tests still passed. The expected family is now written out
independently in the test file, and the mutation reddens.

**Two mutations survived and both taught something.** Rendering the frame's
SOURCE LINE did not redden the "no locals" test -- in that test the value lives
only in a local and the source text is clean, so a separate test with the
sentinel as a literal on the raising line was needed. And the coalescing test
passed with the coalescing removed, because the fake probe was instant and the
four threads never actually overlapped; it needed a deliberately slow probe to
measure coalescing rather than scheduling luck. Both are the same lesson: a
mutation that does not redden is information about the TEST, not permission to
move on.

**A filter at the wrong depth is worse than a missing one.** This repo emits
through two renderers -- `StructuredLogger` nests under a `message` key, a
plain structlog call renders flat under `event`. A monitoring filter written at
the wrong depth matches nothing while the script exits 0, the metric exists and
the policy shows green. The outage it was built for goes unreported and nothing
anywhere errors. The tests assert the DEPTH of each path, not the presence of
the field names, because only the depth distinguishes the working filter from
the silent one.

## Doc freshness

- `docs/standards/logging-and-cost.md` -- new "Errors, close events, and
  monitoring" section; **Tracks:** gained `backend/utils/logging.py` and
  `scripts/setup-monitoring.sh` (neither was tracked by any doc before);
  stamp bumped. Acked (`docs/freshness/`) for the same-day mtime ordering.
- `docs/standards/hipaa-pii-policy.md` -- two new per-surface rows (exception
  rendering, WS close events); corrected the "remaining blind spot" paragraph;
  **Tracks:** gained `backend/utils/logging.py`; stamp bumped. Acked for the
  same reason.
- `docs/components/websocket-routing.md` -- the `_close_ws` contract and why
  1011/1006 is counted in the adapter; stamp bumped.
- `docs/components/voice-ai.md` -- two scar-tissue bullets; stamp bumped.
- `docs/technical_guide.md` -- Surface contract 27, covering both halves.
- Reviewed and left as-is: `ws-protocol.md` (describes wire MESSAGES; this bead
  adds none), `risk-rating.md`, `stateless-architecture.md`,
  `voice-and-vad.md` -- each flagged stale by other beads' changes to files
  they also track, none affected by this one.
- No CLAUDE.md change.

## Files touched

- `backend/utils/logging.py` -- `pii_safe_exception_processor`,
  `pii_safe_exception_info`, `EXCEPTION_LOGGING_SITES`; processor swapped in
  the chain.
- `backend/utils/structured_logger.py` -- `log_ws_close`, `WS_CLOSE_SEVERITY`.
- `backend/routes/websocket_routes.py` -- `_close_ws`; all ten `/fill` closes
  routed through it.
- `backend/adapters/live_ai_gemini.py` -- the two DEV-gated exception branches
  collapsed; the 1011/1006 counted event.
- `backend/main.py` -- `firms_store` on `/health`; `HEALTH_PROBE_TIMEOUT_S`.
- `backend/services/firms.py` -- cache + in-flight coalescing on
  `firms_store_status`.
- `scripts/setup-monitoring.sh` -- new.
- `scripts/setup-telemetry.sh` -- sink filter widened with `ws_error`.
- `backend/tests/unit/test_error_shape.py` -- new (10 tests).
- `backend/tests/unit/test_ws_close_events.py` -- new (16 tests: the shape,
  the close SET, and the on-the-wire reason per site).
- `backend/tests/unit/test_health.py` -- four probe tests + a cache-reset
  fixture.
- `backend/tests/unit/test_firms_service.py` -- four cache/coalescing tests +
  an autouse cache reset (without which the pre-existing error test passed on
  a stale `"ok"`).
- `backend/tests/test_no_pii_logging.py` -- the sentinel case.
- `tests/test_setup_monitoring_script.py` -- new (32 tests).
- `tests/test_setup_telemetry_script.py` -- the `ws_error` sink clause.
- `admin_backend/tests/unit/test_admin_sa_iam_envelope.py` -- the two roles
  moved out of `DEFERRED_ROLES`; two grant tests.
- Docs as listed above.

Review outcomes recorded in the closeout ping.
