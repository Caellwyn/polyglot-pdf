---
date: 2026-06-07
bead: polyglot-pdf-0uu
title: "Render exc_info tracebacks in structlog JSON output"
tags: [bugfix, logging, observability]
---

## Trigger

`bd polyglot-pdf-0uu`. While investigating why the voice form-filler does not
advance to the next field after the user verbally confirms, the live Cloud Run
logs showed an `event_handling_error` firing in `live_ai_gemini.py` immediately
after a `confirm_field` tool response was sent -- but with **`"exc_info": true`
and NO traceback**. The caught exception (the prime suspect for the "doesn't
advance" bug) was undebuggable from the logs.

Root cause: `backend/utils/logging.py` configured structlog with `JSONRenderer`
but no `format_exc_info` processor in the chain. structlog records the
`exc_info=True` flag (set by `.exception()`), but without a renderer processor
`JSONRenderer` serializes only the boolean and drops the actual traceback.

The maintainer authorized this logging-visibility fix as its own separate PR --
a precursor to the form-fill investigation -- so the swallowed traceback becomes
visible before we diagnose the real `confirm_field` error.

## What shipped

Inserted `structlog.processors.format_exc_info` immediately before
`JSONRenderer` in the processor chain. That processor converts the `exc_info`
into a rendered traceback string under an `"exception"` key, which
`JSONRenderer` then serializes into the JSON log line (and thus into Cloud Run
`jsonPayload`).

Verified locally:
- A raised-and-`.exception()`-logged error now emits a full `"exception"` field
  containing `Traceback ... ValueError: ...` (118+ chars), where previously it
  emitted only `"exc_info": true`.
- A normal (non-exception) `.info()` log is **unaffected** -- no spurious
  `"exception"` key, all bound fields intact. `format_exc_info` is a no-op when
  there is no `exc_info` on the event.
- The 10 existing logging/logger tests pass; full backend suite: 201 passed.

## Lessons

Two log-reading gotchas, captured to local memory
(`backend-logs-are-jsonpayload-not-textpayload`):
1. This backend's structlog lands in Cloud Logging as **`jsonPayload`**, not
   `textPayload`. A `gcloud logging read ... textPayload:"confirm_field"` filter
   returns nothing even when tool calls are firing -- pull `--format=json` and
   inspect `jsonPayload.event`. (I initially mis-concluded "no tool calls in
   48h" from a textPayload grep.)
2. `.exception()` without a traceback processor silently drops the stack -- the
   gap this bead fixes.

## Doc freshness

No tier-1/tier-2 doc tracks `backend/utils/logging.py` (confirmed via grep for
`utils/logging` / `configure_logging` across `docs/` -- zero hits), so there is
nothing to bump for this change. The doc-freshness checker flagged ~17 stale
docs, but all are **pre-existing drift from 2026-06-03..06-05 backend/frontend
work by other PRs** (websocket_routes, config, live_ai_gemini, schema-forms,
etc.) -- none track the file this PR touched, and none were made stale by this
change. Triaging that backlog is out of scope for a one-line logging fix.

Also left untouched: the stale in_progress bead `polyglot-pdf-hrn` (Harness
tuning / bounded autonomy, P1) flagged by closeout -- a separate long-running
epic, unrelated to this PR.

## Files touched

- `backend/utils/logging.py` -- added `structlog.processors.format_exc_info`
  before `JSONRenderer` (+6 incl. comment).
