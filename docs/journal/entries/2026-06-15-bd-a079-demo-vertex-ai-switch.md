---
date: 2026-06-15
beads: [polyglot-pdf-a079]
pr: TBD
tags: [deployment, voice-ai, ai-models]
---

# a079: switch the demo Gemini backend from AI Studio to Vertex AI

## Why

The demo ran on AI Studio (the Gemini Developer API, API-key auth) for one
reason: Gemini 3.1 preview access. We are not using 3.1. Staying on AI Studio
bought nothing and cost data privacy -- AI Studio request data is not covered by
the Vertex AI data governance we want. Moving to Vertex keeps request data
private.

## What changed -- and the wrinkle that grew the scope

The bead was scoped as a one-line env flip (`VERTEXAI=false` -> `true`). That
turned out to be insufficient, for a reason worth recording: **the native-audio
Live model is published under DIFFERENT ids on AI Studio vs Vertex, and a Live
(`bidiGenerateContent`) connect with the wrong-backend id `1008`s.**

- AI Studio native-audio (the `config.py` default selected by
  `USE_PREMIUM_MODEL=false`): `gemini-2.5-flash-native-audio-preview-12-2025`.
- That id is **NOT published on Vertex in any region** -- I probed
  `us-central1`, `us-east5`, and `global`; every Live connect `1008`d.
- The Vertex native-audio Live model is **`gemini-live-2.5-flash-native-audio`**,
  which connects and returns audio on `us-central1` (the adapter's default
  location). Still a 2.5-family native-audio model.

So the change is `VERTEXAI=true` PLUS `MODEL_NATIVE=gemini-live-2.5-flash-native-audio`
pinned in `deploy-demo.sh`'s `BACKEND_EXTRA_ENV`. The pin wins over
`USE_PREMIUM_MODEL` in `config.py` `_resolve_model` (a non-empty `MODEL_NATIVE`
short-circuits the flag). `model_family()` still classifies it as `2.5`, so
pricing bills at the 2.5 rate -- no cost-tracking drift.

First deploy used `VERTEXAI=true` with the OLD (AI Studio) model and broke the
demo voice path -- the model 1008'd on the Live connect. Caught by the fresh-eyes
reviewer, who flagged that the local "auth works" proof used `generate_content`
(text REST), not `bidiGenerateContent` (the Live WebSocket the app actually
uses). Re-probing the Live path surfaced the id difference; the model pin is the
fix.

No code or IAM change was needed beyond the env. The Vertex path is the code
default and fully implemented (`live_ai_gemini.py`
`genai.Client(vertexai=True, project=..., location=...)`). Preconditions already
satisfied: `GOOGLE_CLOUD_PROJECT` set in the backend env; `aiplatform.googleapis.com`
enabled by the deploy; the demo Cloud Run SA (`polyglot-backend-sa`) already
holds `roles/aiplatform.user`. `GEMINI_API_KEY` is still injected via Secret
Manager but unused on this path (kept for a future AI-Studio 3.1 A/B).

## Verification

1. Standalone Vertex Live connect (the adapter's exact client construction,
   ADC-only): `gemini-live-2.5-flash-native-audio` on `us-central1` connected and
   returned audio 3/3 runs.
2. Deployed: `./deploy-demo.sh` ran clean (Cloud Build SUCCESS; Cloud Run
   revision `polyglot-backend-00063-2w4` serving 100% as `polyglot-backend-sa`).
   Live `/health` reports `"vertexai":true` and
   `"native":"gemini-live-2.5-flash-native-audio"`.
3. **End-to-end voice (exit criterion 2): maintainer live test-drive on the
   deployed demo.** Full cycle works -- disclaimer, ask for A-number, fill,
   verify, confirm, advance. An apparent "silence after the first fill" during
   testing was traced to **push-to-talk timing**, not the model: the Cloud Run
   logs show the first `update_form_fields` round-trip completing cleanly
   (`tool_call_received` -> `field_update_success` -> `tool_response_sent`, no
   crash), with the conversation continuing once PTT was used correctly.

## 3.1 note

3.1 is not on Vertex as of 2026-06 (it `1008`s -- "policy violation"). Running it
still requires the AI-Studio path (`VERTEXAI=false`, `USE_PREMIUM_MODEL=true`).

## Out of scope

- The obsolete production channel (`polyglot-forms-919f2`, `deploy-production.sh`)
  is being abandoned (no live customers, pre-MVP). The earlier prod-deploy-account
  fix (bd `polyglot-pdf-dwvb`) was reverted and closed as moot in the same session.
- `deploy-all.sh` has a stale `BACKEND_EXTRA_ENV` example comment (still says the
  demo runs AI Studio); filed as bd `polyglot-pdf-5rpo`.
