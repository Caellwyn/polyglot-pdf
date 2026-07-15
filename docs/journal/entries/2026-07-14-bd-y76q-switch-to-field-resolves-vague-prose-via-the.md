---
date: 2026-07-14
bead: polyglot-pdf-y76q
title: "switch_to_field resolves VAGUE prose via the secretary internally (one voice turn, not three)"
tags: [review, testing, refactor]
---

## Trigger

From a maintainer + orchestrator design discussion while closing PR #439. The
#439 fix let the model ask_secretary "which field is X?", read the field_id out of
the response, then call switch_to_field(id) -- THREE voice turns for one
navigation. Voice turns are the expensive, latency-heavy, error-prone unit, and
the model copying a field_id between two tool responses is the id-hallucination
failure class (bd polyglot-pdf-3vby). The voice model genuinely does not know what
other fields exist (tight compression window), so making it orchestrate the lookup
is a shot in the dark. The maintainer's insight: fold the prose->field resolution
INSIDE switch_to_field, with the secretary as the smart fuzzy matcher.

## What shipped

switch_to_field now takes the user's own words -- an exact id, a spoken name, or a
vague description ("that government id thing with 12 digits", "the box where they
sign") -- and resolves it internally. One voice turn.

Resolution ladder (backend/services/callback_handler.py `_handle_switch_to_field_tool`):
1. **Exact match first** -- the frontend's existing `resolveFieldForNavigation`
   (id/spoken_name/name/alias). The common "go back to my mailing city" path, zero
   secretary calls.
2. **Secretary fuzzy match** on an exact miss -- the handler calls the injected
   ask_secretary handler to identify the field, then re-attempts the switch with
   the exact id it returns. Fuzzy matching lives in the secretary (a model
   reasoning over the whole catalog), NEVER in the exact frontend resolver, so no
   silent mis-fill (the lt9z trap stays avoided). Bounded: at most one secretary
   call + one re-attempt per tool call.

Graceful degrade (`_switch_degrade_response`, never hangs, never a guessed field):
- (a) **secretary semantic pushback** -- SECRETARY_SI can now set `resolved:false`
  and say what it could not find ("I could not find a 12-digit government ID
  field"); the handler voices that clarify prose;
- (b) **secretary candidates** that do not land / are ambiguous -> "Did you mean
  X or Y?";
- (c) **secretary pending (deadline blown) / failed** -> fall back to the
  frontend's algorithmic word-overlap candidate matcher -> "Did you mean ...?";
- (d) nothing to suggest -> a bare clarify ask.

Contract changes:
- **SECRETARY_SI** (backend/adapters/text_ai_gemini.py): two question kinds (value
  recall / field identification) + a structured `resolved:false` pushback signal.
- **`TextAIGemini.ask()`** now returns `(answer, sources, resolved)` (was
  `(answer, sources)` from #439). `handle_ask_secretary` carries `resolved` on the
  ok status dict; the port contract updated.
- **`handle_ask_secretary` gains `deliver_late`** (default True). The internal
  switch-resolution query passes `deliver_late=False`: a deadline-blown INTERNAL
  lookup is DRAINED (new `_drain_secretary_lookup`), never voiced as a spurious
  "answer to your earlier question" follow-up turn (there is no user question
  waiting). Tracked as a `(drain, lookup)` pair so teardown cancels it like a
  deliver pair. (This was the one bug the Opus outer review caught -- the switch
  degraded in-turn correctly, but the async late-deliver still fired.)
- **switch_to_field tool description**: pass the user's own words / a description;
  the tool resolves it. The DTI SI no longer nudges the model to pre-resolve via
  ask_secretary -- it just calls switch_to_field.

## Lessons

- **The safe place for fuzzy field-matching is the secretary (a model over the
  full catalog), never the frontend resolver.** The banned trap (lt9z) is fuzzy
  RESOLUTION in the deterministic resolver that auto-fills the wrong field. A model
  identifying a field from a vague description, whose result is then re-resolved
  EXACTLY and confirmed via the normal switch->re-prompt, carries no silent-mis-fill
  risk -- it is a suggestion the exact resolver validates.
- **An internal tool that reuses a user-facing async helper must opt out of the
  user-facing side effects.** `handle_ask_secretary`'s deadline-blown path
  DELIVERS a late answer -- correct for a user question, wrong for an internal
  navigation lookup where no question is pending. A `deliver_late=False` mode
  (drain, do not voice) is the clean separation.

## Doc freshness

The doc-freshness checker flags docs STALE from prior-session commits; none
document the specific switch/secretary flow changed here (voice-ai.md,
tool-call-flow.md do not spell out the switch_to_field resolution ladder). No
current-state doc needed a content update; left as-is per the doc-maintenance rule
for docs tracking otherwise-unchanged behavior.

## Files touched

- `backend/adapters/text_ai_gemini.py` -- SECRETARY_SI field-identification mode + resolved pushback; ask() -> (answer, sources, resolved).
- `backend/ports/text_ai_port.py` -- ask() 3-tuple contract.
- `backend/services/form_filling_service.py` -- handle_ask_secretary carries resolved + deliver_late param; _drain_secretary_lookup; async-deliver unpacks 3-tuple.
- `backend/services/callback_handler.py` -- switch handler refactored into _request_switch_ack / _switch_success_response / _resolve_field_via_secretary (deliver_late=False) / _switch_degrade_response (4-tier ladder).
- `backend/config.py` -- switch_to_field tool description (accepts a description); DTI SI steers nav straight to switch_to_field.
- `backend/tests/unit/test_switch_to_field_tool.py` -- 5 new secretary-resolution + degrade-tier tests.
- `backend/tests/unit/test_ask_secretary_handler.py` -- 3-tuple stubs; deliver_late=False drain test.
- `backend/tests/unit/test_text_ai_gemini.py` -- 3-tuple + resolved-pushback tests.
- `backend/tests/unit/test_tool_contract_static.py` -- SI + tool-desc pins for the new flow.
