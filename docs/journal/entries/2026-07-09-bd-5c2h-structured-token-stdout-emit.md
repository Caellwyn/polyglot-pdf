---
date: 2026-07-09
bead: polyglot-pdf-5c2h
title: "Emit per-turn token usage as structured stdout JSON (Cloud Logging jsonPayload)"
tags: [performance, testing]
---

## Trigger

The maintainer asked whether per-turn token usage is stored in a structured,
machine-extractable form -- specifically, whether a form run on the deployed
backend could later be pulled and graphed (total token burn per turn on a line
graph), or whether only the human-readable text printout exists.

Investigation found the gap: per-turn token/cost data was written to
`backend/logs/token_usage.jsonl` (a local-dev-only file, explicitly documented as
non-production) plus a `print()` pretty-block to stdout. On Cloud Run the JSONL
lives on the container's ephemeral filesystem and is lost when the instance
recycles, and only the `print()` block and the session-end `session_cost_summary`
structlog event reach Cloud Logging. So per-turn granularity from a deployed run
could not be extracted algorithmically without scraping the text block. This is
the minimal slice of the logging roadmap's Phase 5 (`polyglot-pdf-0bs`, the full
BigQuery pipeline) that unblocks per-turn analysis without any new infrastructure.

## What shipped

Alongside the existing file write in the token-tracking block of
`backend/adapters/live_ai_gemini.py`, the same per-turn event is now emitted as one
structured JSON line to stdout via the already-scaffolded
`StructuredLogger.log_gemini_api_response(...)` (event_type `gemini_api_response`).
The emit is gated by the same `if self._form_session_id and self._form_id:` guard
as the file write and wrapped in its own try/except so a logging failure can never
break the live session. It carries per-modality token counts, per-modality + total
`cost_estimate_usd`, and session cumulative totals, keyed by
`form_id`/`form_session_id`/`gemini_session_id` (as `ws_session_id`)/`section_id`.
It lands as `jsonPayload` in Cloud Logging -- queryable with
`gcloud logging read 'jsonPayload.message.event_type="gemini_api_response"'` and
exportable for the per-turn line graph. The `get_structured_logger` import already
existed in the adapter (it was a dead import); this makes it a live call.

No BigQuery sink was added -- that remains the separate Phase 5 bead
`polyglot-pdf-0bs`, which was wired to depend on this bead (`bd dep add
polyglot-pdf-0bs polyglot-pdf-5c2h`) so the roadmap ordering stays correct.
HIPAA-safe by construction: the `StructuredLogger` envelope has no field-value slot,
so only counts + costs can ride along.

Added `backend/tests/unit/test_structured_logger.py` -- the FIRST test coverage of
`StructuredLogger` (previously zero): three tests asserting the single Cloud-Logging
line + envelope shape, that counts/costs survive to the payload, and the no-field-value
HIPAA guard. The file write and `print()` block are unchanged (the emit is purely
additive).

Fresh-eyes (Step 5.5): <FILL: round count + adopt/reject/defer>. Opus outer review
(Step 5.6): <FILL: round count, two independent NO-GAPS>.

## Lessons

The structured-logging scaffolding (`StructuredLogger` + `log_schemas.py`
`TokenUsageMetadata`) was fully built but had exactly one unwired consumer -- the
token emit. Wiring one call site turned "defined contract, emits nothing" into a
live queryable stream with no new infra. When a doc says a subsystem is scaffolding
"not yet emitting," check whether the missing piece is just a call site before
scoping a larger build.

## Doc freshness

Bumped `docs/standards/logging-and-cost.md` (`Tracks:` covers
`structured_logger.py` and `live_ai_gemini.py`, both changed): corrected the stale
"emits nothing yet / single dead import never called" claim to document the now-live
per-turn token emitter, and re-stamped `Last updated` to 2026-07-09 pointing at this
entry. No other tracked doc covers the changed files.

## Files touched

- `backend/adapters/live_ai_gemini.py` -- additive structured stdout emit next to the existing token file write.
- `backend/tests/unit/test_structured_logger.py` -- new; first StructuredLogger coverage (3 tests).
- `docs/standards/logging-and-cost.md` -- corrected stale scaffolding claim; re-stamped.
