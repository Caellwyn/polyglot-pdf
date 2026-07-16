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
