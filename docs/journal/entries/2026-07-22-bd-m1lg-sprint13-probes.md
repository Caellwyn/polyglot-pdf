---
date: 2026-07-22
bead: polyglot-pdf-m1lg
title: "feat(voice+si): sprint-13 probes -- speech_config.language_code shipped, register rule shipped (m1lg + zmlo, closes h1me)"
tags: [harness, conventions, testing]
---

## Trigger

Sprint 13 D-probes (docs/sprint_13_multilingual-ux_plan.md), run under the
experimentation gates after Bundle C merged (PR #463). Maintainer authorized
the autonomous run-through (2026-07-22 in-chat, "keep knocking out what you
can"); spend stayed within the plan's ~$25-30 envelope (~$7.30 this PR:
$0.05 acceptance probe + 6 ru m1lg A/B runs + 3 ru + 3 es zmlo runs).

## What shipped

- **m1lg -- `speech_config.language_code` (SHIPPED default ON).** Google's
  Live docs recommend the API-level language code match the user's language;
  the adapter never set it. Probe (`probe_transcription_lang_codes.py
  --arm speech-lang`, deploy-shaped config): ACCEPTED on Vertex
  `gemini-live-2.5-flash-native-audio`. Behavioral ru A/B (n=3/arm): fills
  identical 38/42 vs 38/42; Latin-word intrusions statistically flat (6 vs 5,
  dominated by the untranslated English FIELD NAME class -- epic tupu's
  domain). Shipped from the adapter's existing per-session bias codes behind
  `SPEECH_LANGUAGE_CODE_ENABLED` (kill-switch mirroring y25o), claimed
  honestly as "recommended + harmless", not as a measured slip win. Findings:
  `transcription_lang_codes_findings.md` addendum.
- **zmlo -- language-agnostic REGISTER rule (SHIPPED; closes h1me).** Both
  SIs: warm/conversational/plain-vocabulary register pinned in EVERY session
  language, full-sentence asks, never bare two-word demands, translate
  form/section titles. ru A/B vs the m1lg on-arm (only the rule differs):
  mean words/turn 7.7 -> 8.5 with courteous phrasings ("Ne mogli by vy...")
  and the remaining short sentences being confirm tags; no fill regression
  (37/42 vs 38/42). es check n=3: 40/42, register stays warm. Residual: 1/6
  runs still read a section title in English -- structural fix (translated
  section labels) noted on bd tupu.2. Per the maintainer's direction the
  GENERAL rule suffices; no per-language register controls. Findings:
  `multilingual_ux_findings.md` register-A/B section.
- 9 + 6 run data sets committed; SI pin test
  `test_dti_and_legacy_si_carry_register_and_title_translation_guidance` and
  speech-config unit pins added.

## Lessons

- The dominant "language slip" in ru sessions is not a model drift at all --
  it is the ENGLISH FIELD NAME the system itself injects. Speech-level
  settings cannot fix a content-level leak; epic tupu is the real fix.
- A/B arms can be chained frugally: the m1lg on-arm doubled as the zmlo
  baseline (identical config except the register rule), saving 3 runs.

## Doc freshness

voice-ai.md bumped (speech_config + register rule are voice-AI behavior).
ai-models.md / config-deployment.md reviewed-and-left (config.py mtime only;
their content -- model tiers, deployment -- is untouched by an SI-text/flag
addition). Pre-existing stale set unchanged (recorded in the two prior
2026-07-22 entries).

## Files touched

- backend/adapters/live_ai_gemini.py (speech_config block)
- backend/config.py (SPEECH_LANGUAGE_CODE_ENABLED + REGISTER blocks x2)
- backend/tests/unit/{test_transcription_language_bias.py,
  test_tool_contract_static.py}
- scripts/spikes/{probe_transcription_lang_codes.py (--arm speech-lang),
  transcription_lang_codes_findings.md, multilingual_ux_findings.md}
- scripts/spikes/data/* (15 run sets), fixtures/audio_cache (es confirm pcm)
- docs/components/voice-ai.md + this entry
