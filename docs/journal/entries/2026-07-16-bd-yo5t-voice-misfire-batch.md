---
date: 2026-07-16
bead: polyglot-pdf-yo5t
title: "fix(voice): tester-misfire batch -- unpause re-prompt, stored-value echo, SI dates/options/UNMISTAKABLY, ASR language bias"
tags: [hotfix, testing]
---

## Trigger

The maintainer's 2026-07-16 Spanish tester session surfaced a batch of voice
misfires: pause/unpause left the AI silent, then it filled an A-number field
with "12345678" the user never said and confirmed a DIFFERENT number than the
field held; the AI slipped into Portuguese-ish words ("distrito quintal") and
English option labels mid-Spanish-session; it wrote "Johanson" but read back
"Johnson" (and JOA/JOE, Fatima/Fatim); and it asked the user to restate dates
as "year, month, day" instead of converting them itself. The maintainer set
the pause design (debounced re-prompt, 1-2s, flutter-safe), supplied Google's
ASR-bias guidance (`input_audio_transcription.language_codes`) and the
"RESPOND UNMISTAKABLY IN <language>" power phrasing, and approved a four-bead
plan. This PR closes polyglot-pdf-yo5t, -h7wx, -oqkj, and -y25o.

## What shipped

- **yo5t (unpause re-prompt).** Diagnosis: `pause()` discards Gemini's
  in-flight question client-side only -- Gemini finishes into a flushed buffer
  and waits for an answer the user never heard; `resume()` re-armed the mic but
  sent nothing. The `recovery_prompt` channel (backend `send_recovery_prompt` +
  `RECOVERY_PROMPT_LEVEL_1..3`, unit-tested) existed with ZERO production
  callers (the jf6w epic replaced the verbal watchdog with a modal and left the
  channel idle). Fix: `resume()`'s warm path arms a 1.5s debounced timer that
  sends level 1; canceled by re-pause / disconnect / the reconnect route (which
  already re-prompts via `RESUME_INITIATING_MESSAGE`) / PTT press / VAD speech
  start, and suppressed at fire time if AI audio is playing. Level-1 wording
  gained "Do not fill or change any field until the user answers" (the phantom
  "12345678" was the model acting with no real user turn after resume).
- **h7wx (stored-value echo).** Diagnosis: `update_form_fields` success
  responses said only "Fields updated successfully" -- no value echo -- while
  the SI tells the model it cannot see form state and the production sliding
  window evicts old turns, so confirmation read-backs came from (possibly
  evicted) model memory and diverged from the stored value. Fix: the success
  response now carries `stored_values` (the post-validator CANONICAL value,
  e.g. "A-12345678" -> "12345678") and repeats it in the message; the DTI SI
  workflow step 3 now reads back FROM the tool response, character by character
  for names/numbers, and a CONSTRAINTS line forbids filling values the user
  never gave. PII: the echo is model-facing only; production structlog calls
  still log counts (pinned by a capture-log test).
- **oqkj (SI gaps).** DATES rule (convert naturally spoken dates yourself;
  NEVER ask the user to restate in a format); option labels spoken TRANSLATED
  into the session language, never verbatim English (labels reach the model
  English-only); "YOU MUST RESPOND UNMISTAKABLY IN <language>" in the SI
  LANGUAGE block, both initiating templates, and the per-injection
  spoken-language anchor (ghv4's "Speak <lang> aloud").
- **y25o (ASR language bias).** SI steers only the LLM output; the ASR
  transcribing a mumbled Spanish word as Portuguese drags auto-detect with it.
  The handshake now carries the app-start `spoken_language`
  (change_spoken_language arrives after connect -- too late for per-connect
  config); `backend/utils/language_codes.py` maps the 18 spoken languages to
  BCP-47 (Quechua deliberately unmapped); `_build_live_config` sets
  `language_codes` on the requested transcription blocks behind
  `TRANSCRIPTION_LANGUAGE_HINT_ENABLED` (default true). Endpoint probe
  (deploy-real config): ACCEPTED on the Vertex 2.5 native-audio default tier;
  the 3.1 premium tier does not exist on Vertex (1008 on the control arm too),
  so it stays unverified behind the kill-switch --
  `scripts/spikes/transcription_lang_codes_findings.md`.
- **Deferred:** translated option labels in kits (polyglot-pdf-ow1e, a
  product/cost epic candidate tied to the 90-language expansion + ryu6).
- **Verification:** full backend suite (1993 passed; the ws-protocol
  key-coverage contract test caught the undocumented `spoken_language`
  handshake key -- doc updated), full frontend suite (1016 passed), live voice
  harness PASS (fill -> confirm-after-yes -> advance) with the stored-value
  echo observed in the real tool response, a live pause/resume drive showing
  the level-1 re-prompt reaching Gemini as a text turn (and run 1 showing the
  AI-speaking guard correctly suppressing a double-prompt on a short pause),
  and the en-US bias applied on a real handshake-driven connect.
- Fresh-eyes triage breakdown: (filled at closeout -- see PR.)

## Lessons

- **Wired-but-callerless machinery is worth grepping for before building.**
  The entire backend half of the unpause fix (route, service method, prompt
  constants, tests) already existed from the retired activity-watchdog design;
  the fix was one debounced caller. A stale frontend comment even claimed the
  channel was "broken backend-side" -- it wasn't (zy3 landed); comment fixed.
- **A tool response is the model's only trustworthy memory under compression.**
  Anything the model must later SAY (a value to confirm) has to ride a tool
  response or injection -- its conversational memory is evictable, and it
  confabulates rather than saying "I don't know". Same principle as the DTI
  guidance blocks; now applied to confirmation read-backs.
- **Config-level language control and prompt-level language control are
  different ends of the pipeline** -- the ASR hint (`language_codes`) governs
  what the model HEARS, the SI governs what it SAYS; a language slip can enter
  at either end. Both are now locked.
- The dev-file logger writes unit-test tool traffic into the same
  `gemini_<date>.jsonl` as live sessions when `.env.DEV` exists -- filter by
  timestamp/session before reading a "live" trace out of it.

## Doc freshness

Bumped (content + stamp):
- `docs/genai_docs/live-api-best-practices.md` -- language_codes section
  updated from "NOT yet endpoint-verified" to verified-on-default-tier, with
  the probe pointer and the premium-tier caveat.
- `docs/standards/ws-protocol.md` -- new `spoken_language` handshake key row
  (enforced by the key-coverage contract test).
- `docs/components/voice-ai.md` -- ASR language bias + stored-value echo in the
  Response config section.
- `docs/components/websocket-routing.md` -- handshake spoken_language ->
  pre-connect service seeding.
- `docs/components/tool-call-flow.md` -- update round-trip now describes the
  stored-value echo + read-back-from-response.
- `docs/standards/voice-and-vad.md` -- new "Pause / unpause" section (the
  re-prompt debounce + guards).
- New findings doc: `scripts/spikes/transcription_lang_codes_findings.md`.

Reviewed and left as-is (flagged stale by the checker because they track
`backend/config.py` / other files this branch touched, but their prose is not
invalidated by this diff -- most were already stale from other branches'
churn): components/auth.md, config-deployment.md, context-compression.md,
jit-schema.md; standards/ai-models.md, confirmation-and-audit.md,
hipaa-pii-policy.md, logging-and-cost.md, risk-rating.md,
section-reset-deprecation.md, si-reduction.md, stateless-architecture.md,
terminology.md, validation-delegation.md; technical_guide.md.

## Files touched

- frontend/src/shared/connection.ts -- debounced post-unpause re-prompt (arm/cancel/fire guards)
- frontend/src/shared/connection.test.ts -- 8 re-prompt tests; fieldManager/audioManager mock destroy()
- frontend/src/webFormConnection.ts -- stale "recovery_prompt broken" comment fixed
- frontend/src/schema-forms/state/schemaFormState.ts -- spoken_language on both handshake shapes
- frontend/src/schema-forms/state/schemaFormState.test.ts -- handshake spoken_language tests
- backend/config.py -- RECOVERY_PROMPT_LEVEL_1 wording; DTI SI step-3 read-back-from-echo + never-fill-unspoken + DATES + option-language + UNMISTAKABLY; INITIATING/RESUME templates; TRANSCRIPTION_LANGUAGE_HINT_ENABLED
- backend/services/ai_context.py -- per-injection anchor carries UNMISTAKABLY
- backend/services/callback_handler.py -- stored_values echo (canonical values) on update success
- backend/services/form_filling_service.py -- derive + hand transcription language codes to the adapter
- backend/adapters/live_ai_gemini.py -- set_transcription_language_codes + config application
- backend/routes/websocket_routes.py -- parse handshake spoken_language, seed service pre-connect
- backend/utils/language_codes.py -- NEW: spoken-language-name -> BCP-47 map
- backend/tests/unit/test_stored_value_echo.py -- NEW
- backend/tests/unit/test_dti_si_voice_rules.py -- NEW
- backend/tests/unit/test_transcription_language_bias.py -- NEW
- scripts/spikes/probe_transcription_lang_codes.py -- NEW: endpoint probe
- scripts/spikes/transcription_lang_codes_findings.md -- NEW: probe findings
- docs/standards/ws-protocol.md, docs/genai_docs/live-api-best-practices.md -- see Doc freshness
