# AI models & pricing (swappable, A/B-able)

**Tracks:** backend/config.py backend/dependencies.py backend/adapters/live_ai_gemini.py

*Last updated: 2026-05-31*

How the Gemini model is selected, how to A/B two tiers in live testing, and how
that selection drives cost. The cost mechanics themselves live in
[logging-and-cost.md](logging-and-cost.md); this doc owns the **selection** rule.

## We run native audio-to-audio Live models only

No cascade / half-cascade. `backend/config.py` defines two tiers (module-level
constants):

| Tier | Model id | Family |
|------|----------|--------|
| **standard** (default) | `gemini-2.5-flash-native-audio-preview-12-2025` | `2.5` |
| **premium** | `gemini-3.1-flash-live-preview` | `3.1` |

> **Model names are not reliable signals.** Google's naming is inconsistent — the
> 2.5 native model has *also* appeared as `gemini-live-2.5-flash-preview`, and that
> exact string returned `1008 not found for bidiGenerateContent` in the contract
> test. The constants above are the strings **verified to connect and return
> audio**. Don't infer native-vs-cascade from a name; verify against the live
> endpoint. (See [`genai_docs/`](../genai_docs/README.md).)

## Selection is env-swappable (no redeploy)

`Settings` (config.py) resolves the active model in a `model_validator`:

- `USE_PREMIUM_MODEL` (env, default `false`) flips between the two tiers.
- `MODEL_NATIVE` is the **resolved** active model and the single source of truth.
  Setting `MODEL_NATIVE` directly via env pins an exact string and **overrides**
  the flag (`_resolve_model` only fills it in when empty).
- `MODEL_LABELING` (default `gemini-2.5-flash`) is a separate knob for the
  field-labeling/normalizer path (normalizer currently deprecated; kept as an
  env knob and surfaced on `/health`).

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

*Last updated: 2026-05-31*
