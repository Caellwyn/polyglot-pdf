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

**Finding (5/5 runs total, 2.5 native-audio, AI Studio):** H1 (model skips the
tool call) is REJECTED. `confirm_field` fires RELIABLY (5/5). The twist is in the
TIMING, and it VARIES run to run: sometimes EARLY, on the verify-question turn --
right after Gemini speaks "Is <value> correct?", BEFORE the "yes" is injected
(2.5 confirming proactively/optimistically) -- and other runs on the post-"yes"
turn (the textbook flow). Either way it fires. So the live g8w FLAKY is a HARNESS
observation/timing issue: the harness only watches `ssConfirmed` AFTER injecting
"yes", so on an early-confirm run it can miss (or race) the confirm that already
landed during the verify question. The fix belongs in the harness, not the
prompt/model. Filed follow-up **polyglot-pdf-tfz** (watch `ssConfirmed` from the
verify turn onward). Recorded in bd memory
`gemini-2p5-confirms-field-proactively-on-verify-turn` -- contrast
`gemini-3p1-skips-update-form-fields` (3.1 genuinely skips a call; this is the
opposite -- 2.5 fires it, just sometimes early).

The probe detects `confirm_field` on BOTH turns and records WHEN (early vs
post-yes); an earlier post-yes-only tally would undercount the early-confirm runs
(Codex PR #126). It REDACTS tool-call args (the field `value` is PII) and output
transcripts (they echo the value) in its logs, and its deadline-bounded `_drain`
now CLOSES its per-turn iterator (a leaked receive iterator can eat the next
turn's messages -- fresh-eyes/Codex PR #126).

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
RUNBOOK noted. Added `webFormConnection.reloadstate.test.ts` (3 cases) covering
the reload contract (Codex + fresh-eyes both asked for coverage of the new path).

## Review triage (fresh-eyes + Codex round 1)

Both reviewers converged on real bugs in the probe's detection logic -- a strong
signal, not nits. Adopted ALL of them inline (no deferrals):

- **Probe confirm tally counted only the post-"yes" turn** (Codex P1) -- but 2.5
  often confirms on the verify turn, so the tally could report 0 and contradict
  the finding. Fixed: detect `confirm_field` on BOTH turns, label early vs
  post-yes, respond to whichever fired.
- **Probe logged raw tool-call args + output transcripts** (Codex P1 x2) -- both
  carry the user's field value (PII). Redacted to field_id + value length and a
  transcript char-count; the in-process tally still keeps args.
- **Leaked async iterator in `_drain`** (fresh-eyes blocker) -- on the
  every-turn timeout path the abandoned `session.receive()` iterator was never
  closed and could buffer/eat the next turn's messages. Added
  `finally: await it.aclose()`.
- **`resetFieldState` skipped the save+dispatch when the field key was already
  absent** (fresh-eyes + Codex) -- so React/DOM didn't resync on a second
  same-page clear. Fixed: always re-save + dispatch when storage exists.
- **No verdict when `update_form_fields` never fires** (fresh-eyes) -- the
  summary was silent, which could read as "model clean". Added an explicit
  NO VERDICT branch distinguishing a setup failure from an H1 signal.
- **No test for the new reset/reload path** (Codex) -- added
  `webFormConnection.reloadstate.test.ts`.

Re-ran the probe live after the fixes (5/5 confirm across all runs) and the
backend + new FE tests green.

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
