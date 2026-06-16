# AI models & pricing (swappable, A/B-able)

**Tracks:** backend/config.py backend/dependencies.py backend/adapters/live_ai_gemini.py

*Last updated: 2026-06-16. The demo runs on Vertex AI (`VERTEXAI=true`,`USE_PREMIUM_MODEL=false`); `_resolve_model` is backend-aware, so the standard tier picks the Vertex native-audio id (`gemini-live-2.5-flash-native-audio`) with no `MODEL_NATIVE` pin -- the AI Studio id 1008s on Vertex (bd polyglot-pdf-a079); see [journal/entries/2026-06-15-bd-a079-demo-vertex-ai-switch.md](../journal/entries/2026-06-15-bd-a079-demo-vertex-ai-switch.md). The `MODEL_LABELING` knob documents its reuse as the SI-reduction epic's cheap-model validator id (bd polyglot-pdf-jnjj, pillar B); rationale owned by [validation-delegation.md](validation-delegation.md).*

How the Gemini model is selected, how to A/B two tiers in live testing, and how
that selection drives cost. The cost mechanics themselves live in
[logging-and-cost.md](logging-and-cost.md); this doc owns the **selection** rule.

## We run native audio-to-audio Live models only

No cascade / half-cascade. `backend/config.py` defines two tiers (module-level
constants):

| Tier | Model id | Family |
|------|----------|--------|
| **standard** (default), AI Studio | `gemini-2.5-flash-native-audio-preview-12-2025` | `2.5` |
| **standard** (default), Vertex | `gemini-live-2.5-flash-native-audio` | `2.5` |
| **premium** (opt-in), AI Studio only | `gemini-3.1-flash-live-preview` | `3.1` |

The standard tier's id is **backend-aware** (`_resolve_model` picks by `VERTEXAI`)
because the native-audio Live model is published under a different id on each
backend and each `1008`s on the other. The premium (3.1) tier has no Vertex id as
of 2026-06.

> **Why 2.5 is the default.** **Both models now emit `update_form_fields`
> reliably.** The historic "3.1 only calls the tool ~50% of the time and
> confabulates an 'I'm having trouble saving' message" defect (`bd
> polyglot-pdf-5oq`, 2026-06-07) was **not** a model regression — it was the
> `update_form_fields` `value` parameter declared with **no type**. Under
> `google-genai` 2.8.0, 3.1 rejects an untyped required param (2.5 tolerated it),
> so the call failed server-side. Typing `value` as `"string"` fixed 3.1 — 4/4
> with the full production system instruction (`bd polyglot-pdf-wpw.4`,
> 2026-06-11, via
> [`backend/scripts/probe_si_bisect_i9q8.py`](../../backend/scripts/probe_si_bisect_i9q8.py)).
> 2.5 stays the default for its **audio-path** behavior, not tool-calling: its
> known tradeoff is intermittent AUDIO silence (no-audio turns / `1011`), which
> did **not** reproduce in recent usage (`bd polyglot-pdf-daa`: 30/30 audio turns
> clean). Set `USE_PREMIUM_MODEL=true` to run 3.1. (3.1 is modestly pricier on
> text-out, 4.50 vs 2.00 /1M — audio in/out identical.)

> **Model names are not reliable signals.** Google's naming is inconsistent — the
> 2.5 native model has *also* appeared as `gemini-live-2.5-flash-preview`, and that
> exact string returned `1008 not found for bidiGenerateContent` in the contract
> test. The constants above are the strings **verified to connect and return
> audio**. Don't infer native-vs-cascade from a name; verify against the live
> endpoint. (See [`genai_docs/`](../genai_docs/README.md).)

## Selection is env-swappable (no redeploy)

`Settings` (config.py) resolves the active model in a `model_validator`:

- `USE_PREMIUM_MODEL` (env, **default `false`** → 2.5) flips between the two tiers;
  set it `true` to run the 3.1 premium tier (now tool-call-reliable; see above).
- `MODEL_NATIVE` is the **resolved** active model and the single source of truth.
  Setting `MODEL_NATIVE` directly via env pins an exact string and **overrides**
  the flag (`_resolve_model` only fills it in when empty).
- **Backend-aware standard tier.** When `MODEL_NATIVE` is unset and the standard
  tier is active (`USE_PREMIUM_MODEL=false`), `_resolve_model` picks the id by
  backend: `VERTEXAI=true` -> `gemini-live-2.5-flash-native-audio` (Vertex),
  `VERTEXAI=false` -> `gemini-2.5-flash-native-audio-preview-12-2025` (AI Studio).
  The native-audio Live model is published under different ids on each backend and
  each `1008`s on the other, so this lets a Vertex deploy work with **no pin**.
  Both are 2.5-family, so `model_family()` bills them identically. The premium
  (3.1) tier has no Vertex id (AI-Studio-only as of 2026-06), so it is unaffected.
- `MODEL_LABELING` (default `gemini-2.5-flash`) is a separate knob for the cheap,
  non-Live TEXT model. The original field-labeling/normalizer path it was named for
  is deprecated; today the knob is read only by `/health` (orphaned). The
  SI-reduction epic's **cheap-model validator** (`bd polyglot-pdf-jnjj`, pillar B)
  REUSES this knob for the validator model rather than adding a new one -- so when B
  lands, set `MODEL_LABELING=gemini-2.5-flash-lite` to run the validator on the lite
  tier (the default stays `gemini-2.5-flash`). The reuse decision + the "why
  flash-lite" rationale are owned by
  [validation-delegation.md](validation-delegation.md) (F3); this doc just records
  that the validator's model id rides on `MODEL_LABELING`, not a new env var.
- `VERTEXAI` (env, **default `true`**) picks the **service/auth mode**, not the
  model. `true` -> Vertex AI ("AI Agent Platform") via service-account ADC +
  `GOOGLE_CLOUD_PROJECT` (compliance-friendly; keeps request data private). `false`
  -> Gemini Developer API (**AI Studio**) via `GEMINI_API_KEY` -- the *only*
  credential AI Studio accepts (no ADC/SA path). This matters because **model
  availability AND the model id differ by service**: the native-audio Live models
  are published under DIFFERENT ids on each backend, and a Live
  (`bidiGenerateContent`) connect with the wrong-backend id `1008`s. As of 2026-06:
  - **AI Studio:** native-audio is `gemini-2.5-flash-native-audio-preview-12-2025`
    (the `config.py` default selected by `USE_PREMIUM_MODEL=false`), and
    `gemini-3.1-flash-live-preview` is available (the only backend with 3.1).
  - **Vertex:** the AI Studio native-audio id above is NOT published in any region
    (Live connect `1008`s); the Vertex native-audio Live model is
    `gemini-live-2.5-flash-native-audio` (verified on `us-central1`, the adapter's
    default location). 3.1 is NOT on Vertex (it `1008`s -- "policy violation").

  The **demo** runs `VERTEXAI=true` (Vertex, SA ADC) with `USE_PREMIUM_MODEL=false`
  -- the privacy-preserving path, on a 2.5-family native-audio model
  (`bd polyglot-pdf-a079`). It does **not** pin `MODEL_NATIVE`: `_resolve_model` is
  backend-aware, so the standard tier on Vertex resolves to
  `gemini-live-2.5-flash-native-audio` on its own (see "Backend-aware standard tier"
  below). To A/B 3.1 you flip back to the AI-Studio path (`VERTEXAI=false`,
  `USE_PREMIUM_MODEL=true`) -- a Vertex round-trip can't reach 3.1, and with no pin
  to clear the flip is clean. Surfaced on `/health` as `vertexai`.

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

*Last updated: 2026-06-16. The demo runs on Vertex AI (`VERTEXAI=true`,`USE_PREMIUM_MODEL=false`); `_resolve_model` is backend-aware, so the standard tier picks the Vertex native-audio id (`gemini-live-2.5-flash-native-audio`) with no `MODEL_NATIVE` pin -- the AI Studio id 1008s on Vertex (bd polyglot-pdf-a079); see [journal/entries/2026-06-15-bd-a079-demo-vertex-ai-switch.md](../journal/entries/2026-06-15-bd-a079-demo-vertex-ai-switch.md). The `MODEL_LABELING` knob documents its reuse as the SI-reduction epic's cheap-model validator id (bd polyglot-pdf-jnjj, pillar B); rationale owned by [validation-delegation.md](validation-delegation.md).*
