---
date: 2026-06-07
bead: polyglot-pdf-kbf
title: "Full Gemini I/O dev logging + model A/B toggle + local dev runner"
tags: [observability, debugging, voice-ai, dev-tooling]
---

## Trigger

`bd polyglot-pdf-kbf`. Debugging why `gemini-3.1-flash-live-preview`
unreliably emits the `update_form_fields` tool call. Live Cloud Run logs showed
the model get interrupted (user speaks a value) and then SAY "I'm having trouble
saving the value" with NO `update_form_fields` call, no error, and no exception
reaching the backend. The precursor PR #100 (`format_exc_info`) confirmed there
was no swallowed traceback -- the call simply never arrives.

The maintainer wants the FULL message exchange to/from Gemini captured before
concluding the model regressed, plus a way to A/B 3.1 vs 2.5, and -- since
constant redeploys are a poor debug loop -- a local runner for the whole stack.
Four hypotheses to discriminate: (1) validation block in the tool RESPONSE,
(2) tool-definition/system-instruction mismatch, (3) front/back-end or websocket
tooling, (4) the model just not following the tool-definition examples.

## What shipped

**1. Full Gemini I/O dev capture (`backend/adapters/live_ai_gemini.py`).**
A new `_dev_log_io(direction, message_type, content)` helper routes through the
EXISTING `get_dev_logger()` -- which is a no-op unless `backend/.env.DEV` exists,
so it writes ONLY to local `backend/logs/gemini_<date>.jsonl` and NEVER to
Cloud Run (production logs stay PII-free; bd polyglot-pdf-oeq). Each entry is
stamped with a monotonic `seq` and the active `model` so a session is fully
re-orderable and A/B-attributable. Capture points (full bodies, both tool-call
paths):
- `tool_call` -- the raw + parsed args Gemini emitted (tests hyp. 2/4).
- `tool_callback_result` -- the body the callback produced (tests hyp. 1).
- `tool_response` -- the body actually sent on the wire back to Gemini.
- `text_turn` -- the hint/prompt text sent to Gemini (+ which send method).
- `interrupted` -- now also captures `canceled_tool_names`, so a barge-in that
  kills an in-flight `update_form_fields` is visible (tests hyp. 3/4).

The production structlog path is unchanged (still logs only names/keys/sizes);
the `GEMINI_INTERRUPTED` structlog line gains a safe `canceled_tool_names` field.

**2. Model A/B toggle (dev feature).** The mechanism already existed
(`USE_PREMIUM_MODEL` / `MODEL_NATIVE`, family-aware pricing). Added a labeled
DEV-FEATURE comment block in `config.py` documenting the 3.1<->2.5 A/B workflow
and pointing at the local runner. The active model is now on every dev-log entry,
so each captured session is unambiguously one model. No new runtime code path --
restart-to-switch (one clean sample per run), per the maintainer's call.

**3. Local dev runner + skill.** `scripts/dev-local.ps1` (PowerShell, per the
maintainer's platform) starts the backend (`uvicorn ... :8000` -- the port the
frontend's dev WS URL defaults to) with `VERTEXAI=false` (AI Studio has 3.1) and
the frontend vite server (`:5173`), creates `backend/.env.DEV` to turn on
full-body logging, and tears both down on Ctrl-C. `-Model standard` runs 2.5;
`-BackendOnly` / `-NoDevLog` flags included. A `run-local` skill
(`.claude/skills/run-local/`) wraps it for "spin up the local stack" requests and
later rapid frontend iteration. Avoids `Start-Process -Environment` (PS 7.4+
only) for Windows PowerShell 5.1 compatibility.

**4. Tool-call flow map (`docs/components/tool-call-flow.md`).** Code expectation
vs. wire reality for `update_form_fields` and `confirm_field`, keyed to the
dev-log `message_type`s -- the lens for reading a captured session against the
four hypotheses. Linked from `docs/INDEX.md`.

## Tests

`backend/tests/test_dev_io_logging.py` (3 tests): full bodies captured when dev
mode is ON (with seq + model + session-correlation fields); NOTHING written when
OFF (the prod-safety contract); and the helper never raises even if the logger
blows up (debug logging must not break a live session). The existing PII-logging
guard (`test_no_pii_logging.py`) still passes -- the new capture routes through
the dev logger, not `_log.*`/`print`, so it does not trip the prod-leak scanner.
Full backend/tests suite: 204 passed, 2 skipped.

## Decisions (defended)

- **Capture via the existing `.env.DEV` dev logger, run LOCALLY** (maintainer's
  explicit choice) rather than a temporary prod body-logging flag -- full
  fidelity, zero cloud PII risk, no redeploy.
- **Reused the existing model toggle** instead of building a runtime/per-connection
  switch -- restart-to-switch is enough for clean A/B samples and adds no new code
  path through session setup (maintainer agreed).
- **PowerShell runner** (maintainer's platform call) with PS 5.1 compatibility.
- **Did NOT fix the pre-existing non-ASCII** emoji log prefixes / the `~=` char in
  `live_ai_gemini.py`; they predate this bead and changing them is out of scope
  (I did drop a trailing space on the line I edited). Flagged, not fixed.

## Doc freshness

New `docs/components/tool-call-flow.md` (dated today) + INDEX entry. Updated
`voice-ai.md` -- the one doc whose CURRENT-STATE prose this change actually
touches: its barge-in section said `GEMINI_INTERRUPTED` logs "canceled tool-call
ids" (now ids AND names), and its Tool-calling section now points at the flow map
+ the `_dev_log_io` capture. Bumped its date stamp.

The other ~14 docs the freshness checker flags are pre-existing drift from
2026-06-03..06-06 work by OTHER PRs (the config.py / live_ai_gemini.py timestamps
are an earlier PR today, plus 06-05 frontend work). This change is purely additive
dev tooling and does not contradict their current-state prose -- e.g. the config
edit is a comment-only DEV-FEATURE block, and `ai-models.md` already documents the
A/B toggle correctly. Re-dating 14 docs whose described behavior is unchanged would
balloon a debug PR; left as-is, owned by the PRs that actually made them stale.

## Files touched

- `backend/adapters/live_ai_gemini.py` -- `_dev_log_io` helper + 6 capture points;
  `canceled_tool_names` on the interrupt path.
- `backend/config.py` -- DEV-FEATURE A/B toggle comment block.
- `backend/tests/test_dev_io_logging.py` -- new (3 tests).
- `scripts/dev-local.ps1` -- new local dev runner.
- `.claude/skills/run-local/SKILL.md` -- new skill.
- `docs/components/tool-call-flow.md` + `docs/INDEX.md` -- new flow map + link.
