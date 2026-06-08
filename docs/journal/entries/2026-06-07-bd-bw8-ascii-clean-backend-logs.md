---
date: 2026-06-07
bead: polyglot-pdf-bw8
title: "ASCII-clean backend log strings + comments (pass 1: uncontended source files)"
tags: [conventions]
---

## Trigger

`polyglot-pdf-bw8` -- follow-up to `polyglot-pdf-sun` (which ASCII-cleaned the
Gemini PROMPT strings in `config.py`). A full backend sweep, prompted by the
maintainer's "keep cleaning up non-ASCII," found remaining scar-#6 violations that
are NOT prompt content but still risk a cp1252 `UnicodeDecodeError`/`Encode` on
`print()`/stdout: emoji in log strings and em-dashes/arrows in comments.

The maintainer also flagged that **parallel sessions are touching the same
surfaces and causing conflicts**. That shaped the scope of this pass (see below).

## What shipped

ASCII-cleaned **9 uncontended backend source files** (0 non-ASCII bytes each):

- `backend/adapters/live_ai_gemini.py` (~60, the big one) -- the per-message emoji
  prefixes in `_log.*` / `print()` calls were replaced with short bracketed ASCII
  tags carrying the same meaning (the file's own "LOGGING ... GUIDE" legend
  documented each glyph; the legend was rewritten glyph->tag accordingly):
  `[send] [ok] [activity] [text] [audio-start] [transcript] [interrupt] [mic]
  [mic-off] [warn] [error] [config] [tools] [stop] [audio] [model-turn] [tokens]
  [session] [closed] [retry] [fatal] [wait]`. Em-dash -> `--`, `~` for the `~`
  approx sign.
- `websocket_routes.py`, `audio_handler.py`, `callback_handler.py`,
  `ai_context.py`, `dev_file_logger.py`, `structured_logger.py`, `vad_metrics.py`
  -- same emoji->tag map + `--`/`->` for em-dash/arrow.
- `models/form_models.py` -- a `label_translations` field-description example
  contained a literal CJK word; replaced the two CJK chars with `\uXXXX` escapes
  so the source is ASCII while the runtime string is byte-identical (verified the
  escape decodes to the same value).

The `callback_handler.py` change includes one Gemini-FACING string (the
"sent too many fields" tool-response the model reads): `[warn] IMPORTANT: ...`
-- still meaningful, now ASCII.

## Why this was a SCOPED pass (collision avoidance)

The maintainer's conflict warning is real: a survey of in-flight work found
**PR #113 was a parallel session's fix for the SAME bead (`0y7`) I had just merged
as #111** -- it was reworked into a superset and merged into `dev`. To avoid
re-creating that pattern, I checked the open PRs' file lists and the active bead
claims, then deferred every file another session is touching:

- **Deferred `backend/config.py` + `backend/services/form_filling_service.py`** --
  both in **open PR #112** (`bd dx7`, "stop speaking field_id").
- **Deferred `backend/routes/pdf_fill_routes.py`** -- named in the **active
  `7a9.14`** claim's preserve-list (its PR #114 touched only `scripts/bakeoff` +
  docs, but the bead explicitly works on that file's choice-field round-trip).
- **Deferred `backend/tests/*`** -- em-dashes/glyphs in test docstrings/comments
  (incl. a BOM in `test_live_ai_gemini.py:1`); lowest cp1252 risk (tests rarely
  `print()` to a prod console), lower value, and test files churn.

The change-surface guard (`bd_safe.py claim`) ABORTED the first claim on overlap
with `7a9.14` (which declares no formal surfaces -> "UNKNOWN"); I verified the real
overlap is absent (PR #114 = bakeoff+docs only) and that I exclude `pdf_fill_routes.py`,
then re-claimed with `--no-surface-check`. The guard did its job -- I respected its
signal by narrowing scope rather than overriding blindly.

## Lessons

Before a broad mechanical sweep across many files, cross-check open PRs' file lists
+ active bead claims and scope OUT every contended surface -- the cheap conflict to
avoid is the one you can see coming. The change-surface guard's "UNKNOWN surfaces"
abort is a prompt to go verify the real overlap, not a wall to `--no-surface-check`
past reflexively.

## Doc freshness

- **Reviewed and left** the docs the freshness checker flagged: they're stale on
  pre-existing mtimes / files this pass touched only for log-string cosmetics. The
  emoji legend lives in `live_ai_gemini.py` itself (rewritten in-place); no
  component/standards doc documents the log glyphs, so none needed a prose edit.

## Beads housekeeping

`bw8` is a **multi-pass** cleanup; this is pass 1. The bead is updated (not closed)
with the deferred residual: `config.py` + `form_filling_service.py` (after PR #112
merges), `pdf_fill_routes.py` (after `7a9.14`), and the `backend/tests/*`
em-dashes/BOM. `polyglot-pdf-hrn` (P1 harness epic) again flagged stale in_progress
-- another track's epic, left as-is.

## Files touched

- `backend/adapters/live_ai_gemini.py` -- emoji log prefixes -> ASCII tags + legend rewrite.
- `backend/routes/websocket_routes.py`, `backend/services/audio_handler.py`, `backend/services/callback_handler.py`, `backend/services/ai_context.py`, `backend/utils/dev_file_logger.py`, `backend/utils/structured_logger.py`, `backend/utils/vad_metrics.py` -- emoji/arrow/em-dash -> ASCII.
- `backend/models/form_models.py` -- CJK example -> `\uXXXX` escapes (runtime value unchanged).
