# AI models & pricing (swappable, A/B-able)

**Tracks:** backend/config.py backend/dependencies.py backend/adapters/live_ai_gemini.py

*Last updated: 2026-06-09. See [journal/entries/2026-06-07-bd-5oq-default-to-2p5-tool-call-reliability.md](../journal/entries/2026-06-07-bd-5oq-default-to-2p5-tool-call-reliability.md) for the 2.5-default switch (3.1 tool-call unreliability), and [journal/entries/2026-06-04-bd-jrl-demo-ai-studio-3.1.md](../journal/entries/2026-06-04-bd-jrl-demo-ai-studio-3.1.md) for the prior AI-Studio/3.1 setup.*

How the Gemini model is selected, how to A/B two tiers in live testing, and how
that selection drives cost. The cost mechanics themselves live in
[logging-and-cost.md](logging-and-cost.md); this doc owns the **selection** rule.

## We run native audio-to-audio Live models only

No cascade / half-cascade. `backend/config.py` defines two tiers (module-level
constants):

| Tier | Model id | Family |
|------|----------|--------|
| **standard** (default) | `gemini-2.5-flash-native-audio-preview-12-2025` | `2.5` |
| **premium** (opt-in) | `gemini-3.1-flash-live-preview` | `3.1` |

> **Why 2.5 is the default.** 2.5 **reliably emits the `update_form_fields` tool
> call**; 3.1 does **not** — in audio mode it calls the tool only ~50% of the time
> and often confabulates an "I'm having trouble saving" message without calling it
> at all, so fields silently fail to save (`bd polyglot-pdf-5oq`, reproduced via
> [`backend/scripts/probe_tool_call.py`](../../backend/scripts/probe_tool_call.py),
> 2026-06-07; TEXT modality can't rescue it — native-audio 3.1 `1007`s on TEXT).
> The old "2.5 is intermittently silent" worry did **not** reproduce in our usage
> (`bd polyglot-pdf-daa`: 30/30 audio turns clean, zero `1011`). So 2.5 is the
> working default; set `USE_PREMIUM_MODEL=true` to opt back into 3.1 once a
> revision fixes audio-mode tool-calling. (3.1 is modestly pricier on text-out,
> 4.50 vs 2.00 /1M — audio in/out identical.)

> **Model names are not reliable signals.** Google's naming is inconsistent — the
> 2.5 native model has *also* appeared as `gemini-live-2.5-flash-preview`, and that
> exact string returned `1008 not found for bidiGenerateContent` in the contract
> test. The constants above are the strings **verified to connect and return
> audio**. Don't infer native-vs-cascade from a name; verify against the live
> endpoint. (See [`genai_docs/`](../genai_docs/README.md).)

## Selection is env-swappable (no redeploy)

`Settings` (config.py) resolves the active model in a `model_validator`:

- `USE_PREMIUM_MODEL` (env, **default `false`** → 2.5) flips between the two tiers;
  set it `true` to run the 3.1 premium tier (note its tool-call unreliability above).
- `MODEL_NATIVE` is the **resolved** active model and the single source of truth.
  Setting `MODEL_NATIVE` directly via env pins an exact string and **overrides**
  the flag (`_resolve_model` only fills it in when empty).
- `MODEL_LABELING` (default `gemini-2.5-flash`) is a separate knob for the
  field-labeling/normalizer path (normalizer currently deprecated; kept as an
  env knob and surfaced on `/health`).
- `VERTEXAI` (env, **default `true`**) picks the **service/auth mode**, not the
  model. `true` -> Vertex AI ("AI Agent Platform") via service-account ADC +
  `GOOGLE_CLOUD_PROJECT` (compliance-friendly; prod default). `false` -> Gemini
  Developer API (**AI Studio**) via `GEMINI_API_KEY` -- the *only* credential AI
  Studio accepts (no ADC/SA path). This matters because **model availability
  differs by service**: as of 2026-06 `gemini-3.1-flash-live-preview` is NOT on
  Vertex (it `1008`s -- "policy violation"), but IS on AI Studio. The **demo**
  runs `VERTEXAI=false` (AI Studio, key injected via Secret Manager) with
  `USE_PREMIUM_MODEL=false` -- i.e. the 2.5 default (`bd polyglot-pdf-5oq`); the
  AI-Studio path is kept so 3.1 stays reachable for A/B (`USE_PREMIUM_MODEL=true`)
  without a Vertex round-trip. Surfaced on `/health` as `vertexai`.

`backend/dependencies.py` is the **one** place the model reaches the adapter:
`get_live_ai()` constructs `LiveAIGemini(api_key=settings.GEMINI_API_KEY,
model=settings.MODEL_NATIVE, vertexai=settings.VERTEXAI)` (a fresh instance per
connection — a CRITICAL bug-fix comment there), and `get_form_filling_service()`
depends on that provider. Routes depend on the service factory, so nothing else
picks a model.

## A/B-ing 2.5 vs 3.1

1. Set `USE_PREMIUM_MODEL=true` (or pin `MODEL_NATIVE=<id>`) and restart — no code
   change, no redeploy of a new image.
2. The adapter reports the active model on every token-usage print and binds it to
   its structured logger (`model=self._model_name`).
3. Cost follows automatically: the cost calc keys off the active model's **family**
   via `get_pricing_for_model(self._model_name)` (see
   [logging-and-cost.md](logging-and-cost.md) for the rate table). So a 2.5 vs 3.1
   run is directly cost-comparable from `token_usage.jsonl`.

## Rules

- **Change the model via env, never by editing the adapter.** The constructor's
  `model=` default is a fallback only; prod always passes `settings.MODEL_NATIVE`.
- **When adding a new tier/family,** add the model constant here *and* a pricing
  row in `GEMINI_PRICING_BY_FAMILY` + a `model_family()` branch (config.py), or it
  bills at the default `2.5` rate. See [logging-and-cost.md](logging-and-cost.md).
- **Verify any new model string against the live endpoint** before shipping it as a
  default — a plausible-looking name can 1008.

*Last updated: 2026-06-09. See [journal/entries/2026-06-07-bd-5oq-default-to-2p5-tool-call-reliability.md](../journal/entries/2026-06-07-bd-5oq-default-to-2p5-tool-call-reliability.md) for the 2.5-default switch (3.1 tool-call unreliability), and [journal/entries/2026-06-04-bd-jrl-demo-ai-studio-3.1.md](../journal/entries/2026-06-04-bd-jrl-demo-ai-studio-3.1.md) for the prior AI-Studio/3.1 setup.*
