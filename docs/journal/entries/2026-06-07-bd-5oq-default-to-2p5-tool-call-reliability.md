---
date: 2026-06-07
bead: polyglot-pdf-5oq
title: "Default to 2.5 native-audio model -- 3.1 unreliably emits update_form_fields"
tags: [bugfix, voice-ai, model-selection]
---

## Trigger

`bd polyglot-pdf-5oq`. The voice form-filler's headline bug: the AI says "I'm
having trouble saving the value" and the field never fills. Diagnosed in the
bd polyglot-pdf-kbf session: live logs showed the model getting the answer, then
speaking "trouble saving" with NO update_form_fields tool call, no error, and no
exception reaching the backend.

## How it was reproduced (no mic needed)

`backend/scripts/probe_tool_call.py` (new) drives Gemini Live directly via the
SDK with the REAL Settings.SYSTEM_INSTRUCTION + TOOL_DECLARATIONS: it sends the
greeting, then a text turn standing in for the user's transcribed answer ("My
A-Number is A123456789"), and reports exactly what the model emits. Text is a
faithful stand-in -- the tool-call decision is made on the transcript, not the
audio.

## What the probe found (~40 runs, A/B)

- **3.1 (gemini-3.1-flash-live-preview), AUDIO modality:** emits
  update_form_fields only ~50% of the time and HIGH-variance across sessions
  (4/5, 3/5, 3/6, 2/6, 1/6). It frequently CONFABULATES the failure -- says "I'm
  having trouble saving" / "there was an error processing that" (the exact live
  phrase) WITHOUT ever emitting the call. Prompt-hardening did not fix it: any
  confirm/acknowledge/next-field speech instruction drops the rate toward 0; a
  pure fill-only prompt still won't stabilize it; a two-turn split (tool-call
  turn, confirm via tool response) works for the confirmation half but does not
  raise the underlying ~50% call rate. TEXT modality can't help -- native-audio
  3.1 1007s on TEXT (known: native emits AUDIO only).
- **2.5 (gemini-2.5-flash-native-audio-preview-12-2025):** emits the correct
  call (field_id + value) reliably WITH the unmodified production confirm
  workflow.

So this is a 3.1 audio-mode tool-calling regression that no prompt/architecture
change on our side fixes. Hypotheses ruled out by the probe: validation block
(no call to validate), tool-def parse mismatch (2.5 parses the same defs fine),
front/back-end or websocket (the probe bypasses both).

## The fix

Switch the default native-audio model to 2.5:
- `backend/config.py`: `USE_PREMIUM_MODEL` field default flipped `true -> false`
  (2.5), with the reasoning documented inline.
- `deploy-demo.sh`: the demo now deploys `USE_PREMIUM_MODEL=false`. This is the
  OPERATIVE switch -- the deploy script was hardcoding `USE_PREMIUM_MODEL=true`,
  so flipping only the config default would NOT have changed the live demo.
- `backend/tests/unit/test_model_selection.py`: inverted the
  polyglot-pdf-4p0 regression guard (which pinned 3.1) to pin 2.5 as the new
  no-arg default, so a future accidental flip back to 3.1 is caught.

Models stay env-swappable: set `USE_PREMIUM_MODEL=true` to opt back into 3.1
once a revision fixes audio-mode tool-calling.

## Why no silent-audio mitigation (the deferred half)

The maintainer initially paired the switch with "mitigate 2.5's intermittent
silence." On scoping it, bd polyglot-pdf-daa was already CLOSED "NOT AFFECTED --
measured clean": 30/30 sustained audio turns on 2.5, zero code=1011. The
~80%-failure forum report does not reproduce in our usage, and the existing
activity-watchdog / recovery-prompt path already covers stalls. So building new
mitigation would solve a problem we don't have. Maintainer agreed: ship the
switch as-is; reopen with the daa 1011-probe if silence ever appears live.

## Decisions (defended)

- **Switched the model rather than keep iterating 3.1 prompts** -- the probe
  showed a hard ~50% ceiling that prompt/restructure can't clear; 2.5 just works.
  (Maintainer chose the direction after the data.)
- **Edited the DEPLOY SCRIPT, not just the config default** -- without it the
  live demo would have stayed on 3.1. Deploy-config change, enacting the
  maintainer's model decision.
- **Flipped the config field default too** (not only the deploy override) so 2.5
  is the honest default everywhere (local dev, prod-on-Vertex) unless overridden.
- **Filed, did not bundle:** ASCII cleanup of the SYSTEM_INSTRUCTION strings
  (scar #6 -- arrows/bullets/em-dashes) -> bd polyglot-pdf-sun, kept OUT of this
  PR because those strings are sent to Gemini and normalizing them needs its own
  probe-verified behavior check.
- **No speculative mitigation** for 2.5 silence (see above).

## Doc freshness

`docs/standards/ai-models.md` documents the model tiers + which is default; its
"3.1 is the reliable default" framing is now stale. Updated its default + the
"why" to 2.5/this bead and bumped the date. Other freshness-flagged docs are
pre-existing drift from other PRs and untouched by this change.

## Files touched

- `backend/config.py` -- USE_PREMIUM_MODEL default true->false (+ reasoning).
- `deploy-demo.sh` -- demo deploys USE_PREMIUM_MODEL=false.
- `backend/tests/unit/test_model_selection.py` -- pin 2.5 as no-arg default.
- `backend/scripts/probe_tool_call.py` -- new reusable tool-call A/B probe.
