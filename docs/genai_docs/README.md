# `genai_docs/` — authoritative `google-genai` SDK reference

**Read these before writing or changing any code that touches the Gemini SDK**
(`from google import genai`) — especially the Live API adapter
[`backend/adapters/live_ai_gemini.py`](../../backend/adapters/live_ai_gemini.py).

## Why this folder exists

Google ships the `google-genai` SDK fast and its public docs are inconsistent
and sometimes self-contradictory (model names, modalities, method signatures all
drift across pages). Web search and Context7 are **unreliable** for this SDK —
the Context7 entry for `google.genai` (Python) is broken. These files are
locally-curated ground truth, kept in-repo so agents trust them over training
data or live web docs.

> If a file here conflicts with your training data or a web doc, **this folder
> wins.** If two files here conflict, prefer the one whose example you can
> verify against the live endpoint, and note the conflict.

## Contents

| File | What it covers | Reach for it when |
|------|----------------|-------------------|
| [`codegen_instructions.md`](codegen_instructions.md) | Official Gemini API Python coding guidelines: correct SDK surface (`genai.Client()`, `client.models.*`, `client.aio.live.*`), explicit anti-patterns (legacy `google-generativeai`, `genai.configure`, `GenerativeModel`, `types.ResponseModality.TEXT`), thinking/streaming/structured-output/function-calling/media examples. | Any `google-genai` call — pick the right method, avoid deprecated patterns. |
| [`genai.live-docs.md`](genai.live-docs.md) | `genai.live` module reference (`AsyncLive` / `AsyncSession`): `connect(model=, config=)`, `send_client_content`, `send_realtime_input`, `send_tool_response`, `receive()`, deprecated `send`/`start_stream`. | Working on the Live WebSocket session lifecycle / message-sending surface. |
| [`gemini_live_api_examples.md`](gemini_live_api_examples.md) | End-to-end Live example (Python + JS): connect, send audio/text/video blobs, receive **audio + transcriptions** (`input_transcription`/`output_transcription`), handle tool calls. Canonical example model: `gemini-3.1-flash-live-preview` + `response_modalities:["AUDIO"]`. | Implementing audio in/out, transcription, or tool-call round-trips. |
| [`live-api-best-practices.md`](live-api-best-practices.md) | System-instruction design, precise tool defs, streaming (20–40 ms chunks, interruption → discard client buffer), **context-window compression** (`ContextWindowCompressionConfig`; 15-min audio cap without it), **session resumption** tokens (valid 2 h) + **GoAway**/`generationComplete` handling, the **compounding per-turn billing** model, proactive-audio caveats. | Cost/latency tuning, long-session reliability, SI/tool prompt design. |

## Hard-won facts (verified against the live endpoint, 2026-05-30)

- **Native-audio models emit AUDIO only.** Requesting `response_modalities:["TEXT"]`
  against a native-audio model fails with **1007** ("response modalities (TEXT)
  not supported"). Text from native models arrives as
  `input_transcription`/`output_transcription` on `server_content`, not a TEXT modality.
- **Model naming is inconsistent.** The 2.5 native model appears as both
  `gemini-2.5-flash-native-audio-preview-12-2025` and `gemini-live-2.5-flash-preview`;
  a genuinely *cascaded* `gemini-live-2.5-flash` also exists (best-practices line 54).
  Do **not** infer "native vs cascade" from a name alone — verify against the endpoint.
- **Compounding cost is the dominant lever.** Every turn re-bills the entire
  accumulated context window; native audio accrues ~25 tokens/sec. Context-window
  compression / size limits are the first-class fix (see epic `polyglot-pdf-l3a`).

## Related project context

- Active model selection + the two A/B tiers: [`../technical_guide.md`](../technical_guide.md)
  (`USE_PREMIUM_MODEL`), and [`../../backend/config.py`](../../backend/config.py).
- Voice adapter surface doc (planned): `components/voice-ai.md` (bead `polyglot-pdf-rvz`).
- AI-models standard (planned): `standards/ai-models.md` (bead `polyglot-pdf-5df`).
- Context-compression / cost epic: `polyglot-pdf-l3a`.
