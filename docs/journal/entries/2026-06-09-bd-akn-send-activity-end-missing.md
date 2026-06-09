---
date: 2026-06-09
bead: polyglot-pdf-akn
title: "fix(voice): FormFillingService missing send_activity_end -- crashed WS on every PTT turn"
tags: [hotfix, testing]
---

## Trigger

The maintainer deployed the latest `dev` build and found the voice connection
"resets each time I try to talk to Gemini." The console logs showed the
WebSocket closing immediately after the disclaimer-accept and after every
push-to-talk release, followed by an auto-reconnect -- a reset-on-every-turn
loop that made the gemini -> user -> tool-response -> gemini round-trip
unusable.

## What shipped

A one-method backend fix. The `/ws/fill` handler
(`backend/routes/websocket_routes.py`, the `vad_activity_end` branch) calls
`service.send_activity_end()` on every `activity_end` message -- which the
frontend sends after the disclaimer accept AND after every push-to-talk
release. `FormFillingService` had `send_activity_start` (delegating to
`AudioHandler`) but **no `send_activity_end`**, so the call raised
`AttributeError`, propagated out of the receive loop, crashed the ASGI handler,
and closed the socket. The frontend auto-reconnected; the next PTT release
crashed it again. `AudioHandler.send_activity_end` and `LiveAI.send_activity_end`
already existed -- only the service-level passthrough was missing (a regression
from the native-VAD/PTT confirm-flow work around PR #126).

The fix adds the 4-line delegation mirroring `send_activity_start`. I
cross-checked every `service.*` method the route calls against the service's
definitions: `send_activity_end` was the only gap.

**Diagnosis was from the production backend logs** (the Cloud Run traceback
named the exact line + missing attribute), then **verified end-to-end on the
local stack + real Gemini via the voice-harness**: multiple `vad_activity_end`
round-trips now flow cleanly (zero `AttributeError` / `Exception in ASGI`), the
Gemini session stays alive across turns, and the full `update_form_fields`
round-trip completes (field `p1_line1_aliennumber` filled `1234567`,
`tool_response success=true`).

Deferred / out of scope: the confirm step (`confirm_field` / `ssConfirmed`)
not landing in the harness run is the SEPARATE model-skips-the-tool-call issue
(bd `gemini-3p1-skips-update-form-fields` / `polyglot-pdf-0ux`), not this
connection bug -- left untouched.

## Lessons

When a route handler delegates to a service, a missing passthrough fails
loudly but at the WORST layer: the `AttributeError` doesn't surface as a tidy
4xx, it tears down the WebSocket receive loop and reads (client-side) as a
mysterious connection reset. The fast path to the cause was the **backend
logs**, not the frontend console -- the ASGI traceback named the line and the
missing attribute outright. (Reinforces the existing scar that backend tool/
error detail lives in Cloud Run `jsonPayload`, and that this stateless backend
surfaces server errors only as socket closes to the client.)

Harness lesson (recorded to `bd remember
voice-harness-native-vad-needs-activity-brackets`): the voice-harness's
native-VAD path streams continuous audio + trailing silence and relies on
Gemini's own VAD to close the turn, which often does NOT segment the injected
fixture (`input_transcription_len: 0`, no tool call, field never fills =>
FLAKY). Injecting with explicit `sendActivityStart()` / `sendActivityEnd()`
brackets forces the turn and the fill lands reliably. Also: never run two
injectors concurrently.

## Doc freshness

`closeout_prep.py` flagged several stale docs
(`docs/components/pdf-filling.md`, `schema-forms.md`,
`docs/standards/{ai-models,confirmation-and-audit,hipaa-pii-policy,
logging-and-cost,risk-rating,terminology,voice-and-vad}.md`,
`docs/technical_guide.md`). **None track `backend/services/form_filling_service.py`
(this branch's only changed file)** -- every flag is from PRIOR commits already
on this branch (06-07/06-08), so per the doc-freshness rule they were stale
before this work and are left as-is, not bumped by this focused fix. No
CLAUDE.md changes.

## Files touched

- `backend/services/form_filling_service.py` -- added `send_activity_end`
  (4-line delegation to `AudioHandler`, mirroring `send_activity_start`).
