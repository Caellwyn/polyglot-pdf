---
date: 2026-06-09
bead: polyglot-pdf-6fj
title: "Reconcile 10 stale tier-1/tier-2 docs flagged by check_doc_freshness"
tags: [conventions]
---

## Trigger

The maintainer kept hitting `check_doc_freshness.py` "STALE" warnings on the
harness -- 10 docs had a `*Last updated:*` stamp older than the last commit of
the code they `**Tracks:**`. The warning is exit-0 (warn-only) but fires on every
commit, so it had become persistent noise. No bead existed; filed
`polyglot-pdf-6fj`.

## What "stale" actually means here

`check_doc_freshness.py` compares each doc's parsed `*Last updated:* YYYY-MM-DD`
stamp (end-of-day UTC) to the git commit time of every file its `**Tracks:**`
glob covers. Newer code than the stamp -> STALE. A stamp bump is the documented
fix -- but only *after* confirming the prose still matches the code. So this was
not a mechanical date-bump job: each doc had to be re-read against its tracked
code first.

## Method

Fanned out 10 read-only audits (one per stale doc), each comparing the doc's
factual claims against the current tracked code and reporting only genuine drift.
Verified every reported drift by hand against the code before editing. Result:
4 docs had real drift, 6 were accurate (stamp-only).

## Real drift found + fixed

- **schema-forms.md** -- claimed a `flip_readonly_bit` field "becomes editable
  when its `show_if` condition is met." `FieldRenderer.tsx` actually keys
  `isDisabled` off `shouldUnlock` (the `unlock_method` flag) *alone*; `show_if`
  is only logged for debugging. Visibility and unlock are independent decisions.
- **risk-rating.md** -- the high-risk `backend/models/` row listed
  `tool_models.py` and `websocket_models.py` as shared wire contracts. Both are
  dead: `websocket_models.py` is empty (0 bytes), `tool_models.py` has no
  importers, and tool declarations now live in `config.py#TOOL_DECLARATIONS`.
  Narrowed the row to `form_models.py` (the only live one) and noted the two
  dead siblings stay `low` until wired up.
- **voice-and-vad.md** -- claimed `send_activity_end()` always sends
  `ActivityEnd()`. Per bd `polyglot-pdf-6vo`, in **native** mode (the default) it
  sends `audio_stream_end=True` -- the realtime signal compatible with automatic
  VAD; a raw `ActivityEnd()` there conflicts with Gemini's VAD and can leave the
  turn open. Only **manual** mode sends `activity_end`. Documented the
  mode-conditional behavior.
- **technical_guide.md** -- listed `VERTEXAI` and `DISABLE_GEMINI_VAD` as code
  constants "**not** `getenv`." Both are `os.getenv`-overridable, and
  `DISABLE_GEMINI_VAD` defaults to `false` (native), not `true`. Moved both into
  the env-var table with correct defaults and reworded the "Manual VAD" gotcha,
  which had implied VAD was off by default.

## Stamp-only (verified no drift)

pdf-filling, ai-models, confirmation-and-audit, logging-and-cost, terminology,
hipaa-pii-policy. Several of these flagged only because `live_ai_gemini.py` was
committed late on 2026-06-08 (the bd-akn/6vo VAD fix) -- a turn-taking change,
not a change to the PII / pricing / confirmation surfaces those docs describe.

## Outcome

`check_doc_freshness.py` is clean (freshness + sprint-archive + doc-conventions);
`tests/test_doc_freshness.py` 39 passed. Closeout prep: 225 passed, docs fresh.

## Side note (collision guard)

`bd_safe.py claim` aborted because the in-flight `polyglot-pdf-akn` (a backend
`.py` fix) had no declared write-surface, so the guard could not prove
non-overlap. Surfaces were provably disjoint (docs `.md` vs backend `.py`), so I
claimed with `--no-surface-check`. Also reset the staleness flag on the
long-running `polyglot-pdf-hrn` epic (active, not abandoned) so closeout prep read
READY.
