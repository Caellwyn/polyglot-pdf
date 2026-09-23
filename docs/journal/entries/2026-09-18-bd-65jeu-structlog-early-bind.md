---
date: 2026-09-18
bead: polyglot-pdf-65jeu
title: "fix(logging): loggers bound at import keep structlog's console renderer"
sprint: 22
tags: [hotfix, postmortem, security]
---

## Trigger

A full W-7 session was run on staging (build 3c4990170) and the telemetry work
from Epic 3 was checked against it. None of the plain structlog events --
ledger_export, form_session_ended, usage_rollup_written,
sweep_expired_links_complete -- had reached the BigQuery dataset. They were in
Cloud Logging, but as textPayload, in structlog's ConsoleRenderer format:

    2026-09-15 21:38:03 [info     ] ledger_export  amount=-1 channel=staging event_type=ledger_export ...

The sink filter matches jsonPayload.event_type, so it never saw them. The
stderr sink table never appeared, income_month (source: ledger_export) could
not be created, and Epic 3's exit criterion 5 was dead on live. Only the usage
events were JSON, because StructuredLogger._emit prints its own json.dumps
rather than rendering through the processor chain -- which is exactly what
disguised the problem as a sink-configuration bug rather than a logging one.

## What shipped

The root cause is import ORDER, not configuration.
structlog.get_logger().bind(module=...) at module level instantiates the bound
logger against the configuration current AT THAT MOMENT -- .bind() on
structlog's lazy proxy is what forces that resolution. Both apps call
configure_logging() AFTER importing their route and service modules
(backend/main.py, admin_backend/main.py), so every one of those loggers froze
structlog's DEFAULT processors -- ConsoleRenderer plus the stock exception
renderer -- for the life of the process.

Reproduced locally before changing anything: bind one logger before
configure_logging() and one after, then log the same event on both. The early
one prints console text; the late one prints JSON.

The second consequence was the serious one. The default pipeline renders
exceptions through ConsoleRenderer, message and traceback included. So
pii_safe_exception_processor -- the E3.8 guard, and PR #831's 193-site sweep --
was bypassed for every early-bound logger, and
docs/standards/hipaa-pii-policy.md's "exception messages never reach the logs"
did not hold for them. In this app an exception message can embed a field
value. The mutation run made it vivid: with the fix reverted, the driver
printed ValueError: ZZQQ_FIELD_VALUE_SENTINEL_65JEU straight to stderr.

Both existing guards were structurally blind to it.
backend/tests/test_no_pii_logging.py greps source, and the call sites are clean
(self._log.exception("tool_callback_error", tool=tool_name) has no sensitive
kwarg to find). backend/tests/unit/test_error_shape.py exercised the CONFIGURED
chain, not the frozen one. Neither could see a leak that happens at render time
on a logger that never adopted the chain.

Two independent halves, both kept:

1. All 49 module-level sites become structlog.get_logger(module=...). The
   bind-free form returns a lazy proxy whose initial values are applied on the
   first LOG call, so it picks up whatever configuration exists then. .bind()
   still chains normally for per-request context.
2. backend/utils/logging.py applies the chain at ITS OWN import, and both
   main.py files now import it FIRST.

Half 2 is not redundant. Half 1 alone left firebase_admin_initialized still
rendering as console text, because backend/services/auth.py logs DURING ITS OWN
MODULE BODY -- it never binds early, it simply emits before anything is
configured. Half 1 cannot reach that; only configuring earlier can. Conversely
half 1 removes the import-ordering dependency that half 2 introduces. Each
alone closes the hole for a different set, so both stay.

The set was enumerated from the AST, not from grep or recall (scar #8). The
three runtime binds (self._log = ... inside __init__, in live_ai_gemini.py,
text_ai_gemini.py, validator_service.py) run long after configuration and were
deliberately left alone.

## Lessons

A global that is configured at startup is only configured for code that reads
it after startup. The bug needs no mistake at any call site: all 49 lines were
idiomatic, and the configuration itself was correct. What was wrong was the
ORDER, which no individual file shows. When a framework has one global
configuration point, the question worth asking is not "is it configured
correctly?" but "what ran before it?".

Two guards on one invariant can both be blind in the same direction. The
source-level grep and the shape test looked like defence in depth for the
exception-message rule. Both assumed the configured chain was the chain in use.
A guard that verifies a MECHANISM cannot detect that the mechanism was never
attached -- that takes an end-to-end check on the real entry point, which is
why the new test imports each app in a fresh subprocess.

A mutation test must fail for the stated reason. With the fix reverted the
unconfigured .exception() re-raises, the interpreter prints the traceback on its
way out, and the process exits non-zero. The first version of the test asserted
the exit code first, so it reported "driver crashed" and buried the PII leak it
was written to catch. The sentinel assertion now runs BEFORE the exit-code gate.
Related: text=True decoded the child through the parent's cp1252 locale, and the
broken-config output carries ANSI bytes -- the decode threw inside subprocess's
reader thread, both streams came back empty, and the test reported "the app
emitted nothing at all". That is a pass-shaped failure message for a real leak.
The test now captures bytes and decodes UTF-8 with errors="replace", precisely
because the output is least well-behaved exactly when the test matters most.

## Doc freshness

- docs/standards/logging-and-cost.md -- new paragraph on why an early-bound
  logger never reaches the sink; stamp bumped. The stamp also FLAGS FOR THE
  POST-DEPLOY CHECK that the stdout/stderr split documented there was measured
  while these lines were console-rendered, so which stream the now-JSON rows
  land on must be re-confirmed against the live table names before
  sql/telemetry_views.sql's TELEMETRY_TABLE_STDERR assumption is trusted.
- docs/standards/hipaa-pii-policy.md -- records that the processor only guards a
  logger that uses it, and why both existing guards missed it; stamp bumped.
- docs/technical_guide.md -- Surface contract 18's flat claim that JSONRenderer
  puts bound keys at the top level now carries its precondition.
- Reviewed and left as-is: the other docs the freshness script flagged
  (admin-service.md, auth.md, config-deployment.md, and the rest) track files
  whose mtimes moved only because of the one-line logger change; nothing those
  docs describe -- routes, auth rules, the WS handshake, ledger semantics -- was
  touched.

## Files touched

- backend/utils/logging.py -- processor chain extracted to
  _configure_structlog(), called at import; configure_logging() delegates.
- backend/main.py, admin_backend/main.py -- backend.utils.logging imported
  first, with the reason recorded.
- 47 further modules under backend/ and admin_backend/ -- one line each,
  .bind(k=v) to get_logger(k=v).
- tests/test_structlog_json_output.py -- NEW: fresh-subprocess import of each
  real app, asserting every line parses as JSON, that the sink's event_type key
  is present, and that a sentinel exception message never appears.
- backend/tests/unit/test_error_shape.py -- static set test asserting the
  module-level bind set is EMPTY, plus a guard-the-guard test proving the AST
  walk flags a module-level bind and ignores a runtime one.

Review outcomes recorded in the closeout ping.
