---
date: 2026-06-08
bead: polyglot-pdf-2m9
title: "Dev logging overhaul + logs.py explorer (the debugging instrument that found the mic bug)"
tags: [conventions, testing]
---

## Trigger

While debugging "Gemini does not respond" locally (bd polyglot-pdf-6vo), the dev
Gemini logger had blind spots exactly where the answer was: it logged
`send/text_turn`, `tool_call`, `interrupted`, and errors -- but NOT whether user
mic audio reached Gemini, whether Gemini responded with audio, turn boundaries, or
session open/close. So "did audio flow / did Gemini respond / where did it break"
was invisible, and exploration meant eyeballing raw JSONL or grepping. The
maintainer asked for a first-class debugging tool: better-organized logs + an
explorer (SQL/pandas-like, not grep), with frontend console capture so logs stop
being copy/pasted.

## What shipped

**Logging coverage (`backend/utils/dev_file_logger.py` + `live_ai_gemini.py`).** New
lifecycle helpers on the existing JSONL schema (timestamp/direction/message_type/
session_id/ws_session_id/content), so the explorer + any analytics consumer keep
working:
- **Audio rollups, both directions** -- `audio_summary` (first frame + every 100),
  emitted on enqueue (`stream_audio`) AND a separate `gemini_send` at the ACTUAL
  `send_realtime_input` boundary. This distinction matters: it once stopped a wrong
  diagnosis -- "reached the queue" is not "reached Gemini".
- **Session lifecycle** -- `session_open`/`session_close` (close carries audio-in/out
  frame totals), making session churn explicit.
- **`event_shape` probe** -- for every received event, a PHI-safe shape (booleans +
  transcription **lengths**, never text): has_audio, has_server_content, interrupted,
  turn_complete, generation_complete, input/output_transcription_len,
  model_turn_parts, tool_call. This is what finally localized the live bug.
- **`SEND_TRANSCRIPT` env flag** (route reads it; launcher defaults it true locally)
  to enable input/output audio transcription. Safe for native-audio: it adds only
  `*_audio_transcription` config, never `response_modalities=TEXT` (which 1007s the
  native-audio model).

**Frontend console mirror (`devConsoleCapture.ts` + `POST /dev/console-log`).** The
browser console is mirrored into the SAME backend log, so `logs.py` shows one
correlated timeline (a `[PTT] press` line next to the audio frames it produced).
Hard-gated: the route 404s unless `.env.DEV`, and the client only POSTs to a
localhost backend -- never cloud.

**Explorer (`scripts/logs.py`).** Pure-stdlib CLI (zero deps): `sessions` (top-level
index with a "NO mic audio / NO response / queued-but-not-sent" health read),
`session <id>` (Gemini + frontend-console timeline interleaved by ws_session_id),
`console`, `errors`, `tail`, `types`, and a DuckDB `sql` escape hatch (graceful
fallback if duckdb absent). `--json` for machine parsing. Forces UTF-8 stdout so the
emoji-laden captured console lines never crash the explorer on Windows cp1252.

## How it earned its keep

The instrument worked: `event_shape` showed `input_transcription_len` stayed **0**
across the user's entire 700-frame utterance while `gemini_send` confirmed every
frame crossed into Gemini -- i.e. Gemini received the audio but extracted no speech.
That pointed at the audio CONTENT, and the maintainer found the cause on their end:
the browser was using the closed-laptop mic (silence). Switching mics, Gemini
responded. So the logger converted an opaque "she doesn't respond" into a precise,
correct diagnosis.

## Doc freshness

- **Bumped** `docs/standards/hipaa-pii-policy.md`: it already documented the
  `.env.DEV`-gated dev file logger; updated that row for the new sinks (audio
  rollups, `event_shape`, transcription text under `SEND_TRANSCRIPT`) and added a row
  for the new `/dev/console-log` ingest -- both PHI-relevant, both `.env.DEV`/
  localhost-gated. This is the one doc whose documented policy my change actually
  touches.
- **Reviewed and left** the rest of the freshness-flagged docs (voice-ai,
  context-compression, tool-call-flow, ai-models, risk-rating, stateless-architecture,
  etc.). They are flagged only because their tracked files (`live_ai_gemini.py`,
  `websocket_routes.py`, `main.py`) got an mtime bump from ADDING dev-only logging;
  none of their documented runtime behavior changed. The new dev tooling has no
  tier-2 doc of its own yet -- a follow-up doc bead can formalize one if wanted;
  `scripts/logs.py --help` is self-documenting in the meantime.

## Verification

- Backend imports clean with the new route (`backend.main`); `py_compile` clean on
  all touched modules.
- `logs.py` exercised on real captured sessions (sessions/session/console/errors/
  tail/types) -- the health read and interleaved timeline both work.
- Full frontend suite: 125 pass + the 3 pre-existing DisclaimerModal failures
  (Chinese-text getByText, bd polyglot-pdf-pwt). Typecheck unchanged at the 24-error
  pre-existing baseline.
- ASCII-clean: zero non-ASCII in all touched backend `.py` and `scripts/logs.py`
  (the branch was rebased onto the dev emoji-cleanup; my added code was already ASCII).
- Bundled with bd polyglot-pdf-6vo in one PR (the voice fixes + the instrument that
  debugged them). The "stops responding after the first field" bug reproduced
  locally this session is a SEPARATE issue (0y7-family), left for a fresh session --
  now debuggable with this logger.

## Files touched

- `backend/utils/dev_file_logger.py` -- lifecycle/audio/event helpers.
- `backend/adapters/live_ai_gemini.py` -- audio rollups, gemini_send boundary, session markers, event_shape probe.
- `backend/routes/dev_console_routes.py` (new) + `backend/main.py` -- console ingest route.
- `backend/routes/websocket_routes.py` -- SEND_TRANSCRIPT env passthrough.
- `frontend/src/shared/devConsoleCapture.ts` (new) + `frontend/src/schema-forms/main.tsx` -- console mirror.
- `scripts/logs.py` (new) -- the explorer.
- `scripts/dev-local.sh` -- local stack launcher (Firebase/auth/WS/VAD/transcript env + node_modules junction).
- `docs/standards/hipaa-pii-policy.md` -- new dev sinks documented.
