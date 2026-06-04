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
- **Model naming is inconsistent — verify against the endpoint, don't trust a name.**
  The 2.5 native model is documented under multiple strings, but they are **not
  interchangeable in practice**: `gemini-2.5-flash-native-audio-preview-12-2025`
  is verified to connect and return audio (2026-05-30), whereas the older
  `gemini-live-2.5-flash-preview` (our retired `MODEL_LIVE` default) **1008'd**
  ("not found for bidiGenerateContent"). A genuinely *cascaded* `gemini-live-2.5-flash`
  also exists (best-practices line 54). Pin the explicit `-preview-12-2025` string;
  do **not** infer "native vs cascade" or "this alias works" from a name alone.
- **Compounding cost is the dominant lever.** Every turn re-bills the entire
  accumulated context window; native audio accrues ~25 tokens/sec. Context-window
  compression / size limits are the first-class fix (see epic `polyglot-pdf-l3a`).
- **DEAD END: `contextWindowCompression` is an unreleased/unsupported STUB on
  native-audio Live models -- do not pursue it.** (Verified 2026-06-04, bd
  `polyglot-pdf-l3a.1`.) The SDK type exists ahead of the server implementation: the
  config serializes, the server ACCEPTS it (no rejection, triggers 200-4096), but it
  NEVER evicts -- prompt tokens compound past the trigger exactly as with compression
  off, on both `gemini-3.1-flash-live-preview` and
  `gemini-2.5-flash-native-audio-preview-12-2025`, identically under `v1alpha`/`v1beta`.
  No cascade Live model is reachable on our key (all `1008`); the docs' compression
  example uses a cascade model. The cost lever the `l3a` epic was premised on is **not
  available** for our model family. Keep `CONTEXT_COMPRESSION_ENABLED=False`; do not
  re-investigate unless Google announces native-audio support. Diagnostics under epic
  `polyglot-pdf-l3a`.
- **An SDK type's EXISTENCE is not evidence the feature is IMPLEMENTED.** This is the
  real lesson from the compression dead end above -- *not* "docs lie." Honest trace: the
  vendored docs here were CORRECT (they named compression as the long-session cost lever,
  true at the API-surface level, and never claimed native-audio support -- they did not
  mislead us). The false confidence came from **SDK introspection**: `nv0` opened
  `google.genai.types`, saw `ContextWindowCompressionConfig` with real fields, and wrote
  "verified SDK syntax / canonical" -- over-reading *the type exists* as *the feature
  works on our model*. For preview/Live features the SDK ships **ahead of the server**,
  so a type can exist for something unimplemented; introspection gives you a config's
  SHAPE, never its AVAILABILITY. Rule: do **not** promote "the SDK has a type for X" to
  "X works" in a design doc. When a feature is **load-bearing** for a plan, confirm
  availability with **one cheap connect-and-watch-one-turn probe BEFORE building** -- not
  a full sweep after. (Probing is for load-bearing availability assumptions, not every
  SDK question -- probes cost real tokens. Here the expensive mistake was building the
  feature + a 4-session sweep on an unverified premise; a single connect probe would have
  caught it first.) (bd memory `gemini-capability-questions-need-endpoint-probe`.)

## Related project context

- Active model selection + the two A/B tiers: [`../technical_guide.md`](../technical_guide.md)
  (`USE_PREMIUM_MODEL`), and [`../../backend/config.py`](../../backend/config.py).
- Voice adapter surface doc (planned): `components/voice-ai.md` (bead `polyglot-pdf-rvz`).
- AI-models standard (planned): `standards/ai-models.md` (bead `polyglot-pdf-5df`).
- Context-compression / cost epic: `polyglot-pdf-l3a`.
