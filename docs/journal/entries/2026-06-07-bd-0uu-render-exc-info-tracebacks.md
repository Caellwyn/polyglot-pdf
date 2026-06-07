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

## Review round (fresh-eyes)

Fresh-eyes flagged a high-confidence blocker: the `_BinarySuppressFilter`
suppresses any record whose message exceeds 2000 chars, and a rendered
traceback (now in the JSON line) would routinely cross that -- silently dropping
the very error logs this fix exists to surface.

Investigating it produced a sharper finding: `_BinarySuppressFilter` is attached
to the **loggers** (root + named noisy ones), never to the **StreamHandler**.
structlog logs through its own loggers via `LoggerFactory()`; those records reach
root by **handler propagation**, which does NOT run the originating logger's
filters. Proven empirically: a 2595-char structlog INFO line passes through
unfiltered and the filter's `.filter()` is never invoked for structlog records.
So the 2000-char guard never actually sees a traceback -- the blocker as
described does not fire in this configuration, and the `format_exc_info` fix
alone is sufficient (verified: a 2091-char traceback renders into `exception`
and reaches output).

Resolution:
- Kept a small **defense-in-depth** edit: exempt ERROR-and-above from the
  2000-char guard (`record.levelno < logging.ERROR`), so the filter is correct
  *if* it is ever moved onto the handler. Comment states plainly that the filter
  is currently inert for structlog records.
- Filed `polyglot-pdf-h79` (P3) for the real latent issue: the binary-suppress
  filter does not run on structlog (JSON) output at all. Out of scope for this
  one-line logging fix.

## Lessons (review round)

Running backend tests from the **main-repo cwd** silently imports main's
unedited copy of `backend/utils/*`, not the worktree edit (the venv lives in
main, which tempts `cd`-ing there). The fix "looked broken" until `m.__file__`
revealed the wrong import path. Captured to local memory
(`run-backend-tests-from-worktree-not-main`); sibling of the
closeout-scripts-audit-main trap. Also: `closeout_prep.py` runs only
`backend/tests/`, so the pre-existing `manifest_wrapper`-fixture collection
errors in top-level `backend/test_jit_system_e2e.py` are outside its scope (and
unrelated to this change).

## Files touched

- `backend/utils/logging.py` -- added `structlog.processors.format_exc_info`
  before `JSONRenderer`; exempted ERROR-and-above from the `_BinarySuppressFilter`
  2000-char guard (defense-in-depth) with an explanatory comment.
