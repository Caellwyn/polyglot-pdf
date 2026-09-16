---
date: 2026-09-16
bead: polyglot-pdf-wfgjz
title: "fix(logging): B1a -- the 422 that never echoes, the token file that never ships, and the knobs a deploy cannot turn"
tags: [security-audit, logging, pii, testing]
---

## Trigger

Sprint 23 (the security + data-leak audit, epic `polyglot-pdf-uijam`, plan
`docs/sprint_23_security-audit_plan.md`), workstream B1a, threat actor T3:
PF-3 (a 422 echoes the request body), PF-11 (the token dashboard file is
written on the production container), and the close-reason and verbosity
pins. Independent of B1b, which owns the `error=` kwarg class on top of
e4dt8's exception processor. Built in-session (no builder subagent, every
command through a hidden single process) because the maintainer was at
the machine.

## What shipped

- **A value-free 422 on both apps.** `backend/utils/validation_errors.py`
  returns each pydantic error's `loc`, `type` and `msg` only; FastAPI's
  default also returned `input` (the client's value) and `ctx` (which can
  quote it). Installed at import in `backend/main.py` and
  `admin_backend/main.py`. For a custom validator's `value_error` /
  `assertion_error` -- whose text pydantic renders verbatim, and which route
  validators interpolate the submitted value into (the disclaimer timestamp
  bound does exactly that) -- `msg` is replaced by the generic phrase, so the
  choke point closes every such site at once. A sentinel posted where an int
  is expected (`/api/disclaimer-acceptance`; the admin credit-adjust body) and
  an in-type, out-of-range sentinel are both asserted absent from the 422
  text, and `app.debug` is pinned False on both apps.
- **The token dashboard file is local-dev only, on two layers.**
  `TokenFileLogger.log_token_event` returns without writing when
  `K_SERVICE` is set (the container's disk is not a log store), and the one
  call site in `live_ai_gemini.py` is gated on the `backend/.env.DEV`
  marker (`DEV_LOGGING_ENABLED`), which the image never carries. The
  per-turn usage banner -- nine `print()` lines that reached Cloud Logging
  as bare stdout text -- is one structured `token_usage` event carrying
  counts and cost only.
- **Deployed floors on the verbosity knobs.** `configure_logging` never
  runs below INFO with `K_SERVICE` set, whatever `LOG_LEVEL` says (the
  noisy-library WARNING cap already stood); `Settings` forces
  `LIVE_DEV_TRANSCRIPTS` and `LIVE_DEV_AUDIO_DUMP` off with `K_SERVICE`
  set; the `SEND_TRANSCRIPT` harness knob in `websocket_routes.py` -- the
  one library/debug env name the backend actually read -- is honoured only
  without `K_SERVICE`. A source scan requires any read of a verbosity or
  debug env name to sit inside a `K_SERVICE`-gated statement.
- **The wire close reason is a static literal.** Every close site on
  `/ws/fill` (the `_close_ws` wrapper's callers and the raw idle-timeout
  close) sends a literal from an independently stated set of six wire
  reasons; the AST pin resolves a `reason` variable to its literal
  assignment and refuses anything else. A runtime test proves `_close_ws`
  puts exactly the stated literal on the wire and nothing from its
  telemetry metadata.
- **The text-model adapter is a guarded file.** `text_ai_gemini.py` joined
  `test_no_pii_logging.py`'s GUARDED_FILES; its existing log calls carry ids
  and counts only, and the guard now fails a future `prompt=` / `text=` /
  `message=` kwarg there. `secretary_context.py` builds the prompt and has no
  log call at all, so it stays under the deny-by-default backend sweep rather
  than a vacuous per-file entry.

## Verification

- Targeted (hidden single process): `test_no_pii_logging.py`,
  `test_token_usage_local_only.py`, `test_deployed_verbosity_floor.py`,
  `admin_backend/.../test_validation_error_shape.py`, `test_ws_close_events.py`,
  `test_websocket_protocol.py`, `test_usage_event_live_plumbing.py` -- green.
- Full backend suite: the first run failed two `test_usage_event_live_plumbing`
  cases -- the dev-marker gate had been placed around the whole session-context
  block, which also holds the structured per-turn Cloud Logging emit, so a
  deployed run would have lost its per-turn token events. The gate now wraps
  the file write alone; the plumbing tests pass again. Rerun after the fix:
  5939 passed / 282 skipped, no failures. The twelve process-spawning test files, run separately
  with every child windowless: 524 passed / 5 skipped.
- Scar #9: twelve one-line mutations, each in its own interpreter (the app
  modules import once per process) and each RED with exit code 1: the handler
  install removed from either app; `input` added back to the safe keys; the
  custom-validator `msg` replacement removed (the submitted timestamp came
  straight back in `msg`, exactly as the outer reviewer predicted); the
  K_SERVICE INFO clamp removed; the dump-knob block removed; the SEND_TRANSCRIPT
  guard removed; the token writer's K_SERVICE return removed; the dev-marker
  gate replaced by `if True`; a `print()` of the counts restored; one close
  site's literal turned into an f-string; `_close_ws` made to append its
  metadata to the wire reason.

## Review record

REVIEW_RECORD

## Lessons

- **A framework default is a sink, and it has more than one field.**
  FastAPI's 422 quoted the client's value in `input`; dropping that was the
  obvious fix, and the outer review found the second channel -- pydantic
  renders a custom validator's `ValueError` text into `msg`, and the
  disclaimer route interpolates the value into that text. The choke point
  now blanks `msg` for those error types instead of trusting every
  validator site.
- **A deploy floor beats a documentation promise.** "Prod never sets
  LOG_LEVEL=DEBUG" is an intention; `K_SERVICE` is a fact the code can
  read. Every knob that could raise log volume or forward transcripts now
  checks the fact.
- **Pin the wire, not just the log.** e4dt8 counted close CODES for the
  monitors; the TEXT on the wire is a separate channel with its own set.

## Doc freshness

Bumped: `docs/standards/hipaa-pii-policy.md` (three new per-surface rows, the
token/cost row, the guarded-files enumeration), `docs/standards/logging-and-cost.md`
(the writer's two guards, the banner), `docs/components/config-deployment.md`
(the "Deployed verbosity floors" bullet), `docs/components/voice-ai.md` (the
token-file sentence). Acked (`docs/freshness/*.ack`, each with the exact list of
what B1a changed): admin-service, context-compression, jit-schema,
tool-call-flow, websocket-routing, ai-models, risk-rating, schema-key-visibility,
section-reset-deprecation, si-reduction, stateless-architecture,
validation-delegation, voice-and-vad, ws-protocol, technical_guide -- none
makes a claim about the changed lines.

## Files touched

- backend/utils/validation_errors.py -- new
- backend/main.py, admin_backend/main.py -- install the handler
- backend/utils/token_file_logger.py -- deployed no-op
- backend/adapters/live_ai_gemini.py -- structured usage line; dev-marker gate on the file logger (only those lines)
- backend/utils/logging.py -- deployed INFO floor
- backend/config.py -- deployed dump-knob floor
- backend/routes/websocket_routes.py -- SEND_TRANSCRIPT honoured locally only
- backend/tests/test_no_pii_logging.py -- 422 sentinel, close-reason set pin, wrapper passthrough; text-model adapters guarded
- backend/tests/unit/test_token_usage_local_only.py -- new
- backend/tests/unit/test_deployed_verbosity_floor.py -- new
- admin_backend/tests/unit/test_validation_error_shape.py -- new
- docs/journal/entries/2026-09-16-bd-wfgjz-log-sink-b1a.md -- this entry
