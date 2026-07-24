# Transcription language_codes -- endpoint verification (bd polyglot-pdf-y25o)

**Date:** 2026-07-16. **SDK:** google-genai 2.8.0. **Backend:** Vertex
(ADC, project polyglot-demo-aa709, us-central1).
**Script:** `scripts/spikes/probe_transcription_lang_codes.py`.

## Question

`AudioTranscriptionConfig.language_codes` (BCP-47 ASR bias) is SDK-2.8-present
but was marked NOT endpoint-verified on our native-audio models
(`docs/genai_docs/live-api-best-practices.md`). Does the production Live model
accept it at connect, or does it 1007/1008-reject the config?

## Method (deploy-fidelity)

The probe builds the adapter's REAL connect config (`_build_live_config`:
production 7-tool declarations, VAD, compression, SI) -- per the
deploy-fidelity rule in docs/standards/testing.md -- with ONE delta:
`language_codes=["es-US"]` on BOTH `input_audio_transcription` and
`output_audio_transcription`. Success = connect + text turn + audio reply, no
1007/1011. A hint-off control arm runs only if the hint arm fails. Cost: 2
connects x 1 short text turn (< $0.05 total; Gate-2 trivial-pilot).

## Results

| Arm | Model | Backend | Result |
|-----|-------|---------|--------|
| hint-on `["es-US"]` | `gemini-live-2.5-flash-native-audio` (production default tier) | Vertex | **OK** -- connected, audio reply (11,114 bytes), no error close |
| hint-on `["es-US"]` | `gemini-3.1-flash-live-preview` (premium tier) | Vertex | 1008 -- model NOT AVAILABLE on Vertex at all |
| hint-off control | `gemini-3.1-flash-live-preview` | Vertex | 1008 identically -- proves the 3.1 failure is model availability, NOT the hint |

## Verdict

- **ACCEPTED on the production default tier** (Vertex 2.5 native audio):
  `language_codes` on both transcription configs connects and streams cleanly.
  `TRANSCRIPTION_LANGUAGE_HINT_ENABLED` ships **default true**.
- **Premium tier (3.1) remains unverified for this field** -- it does not exist
  on Vertex (expected: config.py notes the premium tier runs on AI Studio with
  VERTEXAI=false), and AI Studio probing is barred by the Vertex-only billing
  directive. If a deploy flips `USE_PREMIUM_MODEL=true` (AI Studio 3.1), either
  verify there first or set `TRANSCRIPTION_LANGUAGE_HINT_ENABLED=false` for
  that deploy -- the kill-switch exists for exactly this.
- What this probe does NOT measure: whether the bias actually improves
  session-language transcription accuracy (the "distrito quintal" class). That
  is a behavioral question for the voice-harness / live testers, not a config
  acceptance question.

## Addendum -- speech_config.language_code (bd polyglot-pdf-m1lg, 2026-07-22)

**Question:** Google's Live docs recommend the API-level
`speech_config.language_code` match the user's language (framed for the
cascaded model). The adapter never set it. Does the production NATIVE-AUDIO
tier accept it, and does it reduce output-language slips?

**Acceptance (same deploy-fidelity probe, `--arm speech-lang`):** ACCEPTED --
`speech_config={'language_code':'es-US'}` on the full deploy config connected
and streamed audio cleanly on Vertex `gemini-live-2.5-flash-native-audio`
(one connect, <$0.05).

**Behavioral A/B (ru 14q DTI slices, n=3 per arm, ~$3.3; runs
20260722T230852Z/231100Z/231312Z off vs 231520Z/231732Z/231941Z on):**

| arm | fills | Latin-word intrusions in model speech (per run) |
|---|---|---|
| flag OFF | 38/42 | 0 / 1 ("legally") / 5 ("Form, In Care Of Name") |
| flag ON | 38/42 | 1 ("legally") / 4 ("In Care Of Name") / 0 |

No reliability regression; no measurable slip reduction at n=3. The dominant
"intrusion" class is the ENGLISH FIELD NAME read aloud -- the untranslated
spoken-name problem (epic polyglot-pdf-tupu), which no speech-level setting
can fix; the residual single-word slip ("legally") appears once per arm.

**Verdict: SHIPPED default ON** (`SPEECH_LANGUAGE_CODE_ENABLED`, kill-switch
mirroring the transcription-hint flag): it is Google's documented
recommendation, endpoint-accepted, free, and regression-clean. Claimed on the
honest basis of "recommended + harmless", NOT on a measured slip win.
