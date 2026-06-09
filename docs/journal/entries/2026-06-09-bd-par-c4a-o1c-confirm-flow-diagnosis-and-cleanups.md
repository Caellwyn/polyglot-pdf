---
date: 2026-06-09
bead: polyglot-pdf-par
title: "Confirm-flow diagnosis (2.5 confirms proactively) + tool-response and same-page-retry cleanups (par, c4a, o1c)"
tags: [voice, diagnosis, testing, cleanup]
---

## Trigger

Three small voice-flow beads from the 0ux/g8w line, bundled into one PR:

- **par (P2, bug/diagnosis):** the g8w voice harness, run against a 0ux-FIXED
  backend, saw the fill path work (`update_form_fields` fired, field filled
  `1234567`) but the confirmation never landed: after "yes that is correct" was
  injected, `ssConfirmed` stayed false and the harness reported FLAKY "field
  never confirmed". The question: does 2.5 native-audio call `confirm_field` at
  all, or does the harness "yes" injection mis-time Gemini's verify question?
- **c4a (P3, chore):** `LiveAIGeminiSession.send_tool_response` (the port
  wrapper) built `types.FunctionResponse(id=r["id"], ...)` -- a direct `r["id"]`
  that `KeyError`s on a missing id, and which did NOT route through the new
  `_build_function_response` helper. Dead on the hot path (the receive loop sends
  directly), but the port contract implies a future caller could re-introduce the
  0ux id gap.
- **o1c (P3, chore):** for SAME-PAGE harness retries, clearing only
  `sessionStorage` does not go through `SchemaFormStateManager.save()` /
  `schemaFormStateChange`, so SchemaForm's React state and the live
  `WebFormConnection.state` still held the prior filled/confirmed value.

## What shipped

### par -- diagnosis (no behavior change)

Added `backend/scripts/probe_confirm_field.py`, extending `probe_tool_call_id.py`
to the confirm turn. It drives the flow deterministically from the backend side
(greeting -> answer -> `update_form_fields` -> tool_response -> verify question ->
"yes" -> observe `confirm_field`), which removes the live-harness timing variable.

**Finding (3/3 runs, 2.5 native-audio, AI Studio):** H1 (model skips the tool
call) is REJECTED. `confirm_field` fires RELIABLY (3/3). The twist: it fires on
the VERIFY-QUESTION turn -- immediately after Gemini speaks "Is A123456789
correct?", BEFORE the "yes" is injected. 2.5 confirms the value
PROACTIVELY/optimistically rather than strictly waiting for user assent. So the
live g8w FLAKY is a HARNESS observation/timing issue: the harness only watches
`ssConfirmed` AFTER injecting "yes" and can miss (or race) the confirm that
already landed during the verify question. The fix belongs in the harness, not
the prompt/model. Filed follow-up **polyglot-pdf-tfz** (watch `ssConfirmed`
across the verify turn). Recorded in bd memory
`gemini-2p5-confirms-field-proactively-on-verify-turn` -- contrast
`gemini-3p1-skips-update-form-fields` (3.1 genuinely skips a call; this is the
opposite -- 2.5 fires it, just early).

Secondary finding: native-audio turns after a tool response do NOT deliver a
clean `turn_complete` here -- every drained turn hits the wall-clock timeout.
That is why `_drain` is deadline-bounded (an unbounded `session.receive()` hangs
the probe); the first probe run hung exactly there before the timeout was added.

### c4a -- route the wrapper through the helper

`send_tool_response` now builds responses via
`_build_function_response(r["name"], r["response"], r.get("id"))` -- shares the
hot path's omit-if-absent 0ux id-handling and tolerates a missing id instead of
`KeyError`ing. Kept the method (the port still declares it) rather than deleting
it. Added a missing-id unit test.

### o1c -- same-page-rerun-safe field clear

Added `WebFormConnection.reloadState()` (re-`load()`s its in-memory state from
sessionStorage) and a `resetFieldState(fieldId)` member on the
`__VFF_TEST_INJECT` hook that clears a field through
`SchemaFormStateManager.save` (fires `schemaFormStateChange` so SchemaForm's
React state reloads) and refreshes both the connection-manager closure's `state`
and the live `WebFormConnection.state`. The harness `clearFieldState` prefers the
hook, falling back to the direct DOM + storage clear (still correct for the
documented reload-between-attempts path and for an app build predating the hook).
RUNBOOK noted.

## Doc-freshness review (timestamp-stale, content-current)

`closeout_prep` flagged several tier-2 docs STALE because my edits touched files
they cite (`live_ai_gemini.py`, `connection.ts`, `webFormConnection.ts`). I
reviewed each and confirmed NONE needs a content change for this PR -- my edits
are behavior-preserving for what those docs describe:

- `ai-models.md`, `voice-and-vad.md`, `hipaa-pii-policy.md`, `logging-and-cost.md`,
  `risk-rating.md`: c4a is an internal wrapper reroute (no model selection, VAD,
  PII/logging, or risk surface change); o1c adds a test-only inject hook + a
  reload method (no voice-protocol change). The remaining staleness on these docs
  comes from OTHER branches' edits to the same files (callback_handler.py,
  config.py, etc.), out of scope here.
- `pdf-filling.md`, `schema-forms.md`, `terminology.md`, `technical_guide.md`:
  triggered entirely by files I did not touch (pdfFiller.ts, validation.ts,
  main.py, websocket_routes.py, ...). Not this PR's concern.

The doc-freshness check is timestamp-based and warn-only (exit 0); this note is
the journal record the rule asks for in lieu of a content bump.
