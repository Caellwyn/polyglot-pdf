# AI models & pricing (swappable, A/B-able)

**Tracks:** backend/config.py backend/dependencies.py backend/adapters/live_ai_gemini.py backend/adapters/text_ai_gemini.py

*Last updated: 2026-10-21 (bd polyglot-pdf-bd1zs: standard voice tier -> `gemini-3.8-live`; lite text tier -> `gemini-3.1-flash-lite` on the Vertex `global` location.)*

How the Gemini models are selected, how to A/B two voice tiers in live testing,
and how that selection drives cost. The cost mechanics themselves live in
[logging-and-cost.md](logging-and-cost.md); this doc owns the **selection** rule.

## We run native audio-to-audio Live models only

No cascade / half-cascade. `backend/config.py` defines two tiers (module-level
constants):

| Tier | Model id | Family | Where it is served |
|------|----------|--------|--------------------|
| **standard** (default) | `gemini-3.8-live` | `3.8` | Vertex `us-central1` **and** AI Studio (same id) |
| **premium** (opt-in) | `gemini-3.1-flash-live-preview` | `3.1` | AI Studio only |

The standard tier still resolves **backend-aware** (`_resolve_model` picks
`MODEL_NATIVE_STANDARD_VERTEX` when `VERTEXAI=true`, `MODEL_NATIVE_STANDARD`
otherwise) because Live ids have historically differed per service. For 3.8 the
two constants hold the same id. `gemini-3.8-live` is **regional**: it connects on
Vertex `us-central1` (the Live adapter's location) and `1008`s at the `global`
location (endpoint-verified 2026-10-21).

> **Why 3.8 is the default, and how it differs.** `gemini-3.8-live` is Google's
> stable "default option for most low-latency voice agent experiences", priced
> identically to 3.1 on the Live endpoint. Three behavioral differences from the
> older families are handled in the adapter
> ([migration notes](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-live#migrating);
> each endpoint-verified on Vertex):
> - **No thinking config.** Any `thinking_config` makes the connect `1007`
>   ("not allowlisted to customize the thinking level"). The adapter sends the
>   2.5-only `thinking_budget=0` solely to the 2.5 family, so 3.8 gets none.
> - **Function calls default to `NON_BLOCKING`.** Unmarked, 3.8 called
>   `update_form_fields` and then ended its turn silently after the tool result.
>   The adapter marks every declaration `behavior: BLOCKING` for the 3.8 family,
>   restoring the wait-for-result-then-speak contract every tool here is written
>   for.
> - **`send_client_content` works for the whole session**, and on 3.8
>   `turn_complete=True` **interrupts** any generation in progress. The adapter's
>   text turns use it unchanged.
>
> Proactive audio is permanently on (setting it `false` errors) and affective
> dialog was removed; the adapter sets neither.

> **Model names are not reliable signals.** Google's naming is inconsistent, and a
> plausible id can `1008` on one service while working on the other. The constants
> above are the strings **verified to connect and return audio**. Don't infer
> availability or native-vs-cascade from a name; verify against the live endpoint.
> (See [`genai_docs/`](../genai_docs/README.md).)

## Selection is env-swappable (no redeploy)

`Settings` (config.py) resolves the active model in a `model_validator`:

- `USE_PREMIUM_MODEL` (env, **default `false`** → 3.8) flips between the two tiers;
  set it `true` to run the 3.1 premium tier.
  **LOCAL ONLY.** 3.1 exists only on AI Studio, so `USE_PREMIUM_MODEL=true` *is*
  the AI-Studio flip under another name — and it is the variant the Vertex-only
  startup guard CANNOT catch: `_resolve_model` sets the premium id before the
  `VERTEXAI` branch, so a deployed service starts fine and then `1008`s at
  connect time.
- `MODEL_NATIVE` is the **resolved** active model and the single source of truth.
  Setting `MODEL_NATIVE` directly via env pins an exact string and **overrides**
  the flag (`_resolve_model` only fills it in when empty).
- `MODEL_LABELING` (default **`gemini-3.1-flash-lite`**) is the knob for the cheap,
  non-Live TEXT model behind `get_text_ai()` in `backend/dependencies.py`: the
  SI-reduction epic's **per-section validator and secretary** (`bd
  polyglot-pdf-jnjj`, pillar B). The reuse decision + the "why flash-lite"
  rationale are owned by [validation-delegation.md](validation-delegation.md)
  (F3); this doc just records that the validator's model id rides on
  `MODEL_LABELING`, not a new env var. No deploy channel pins it, so the code
  default is what runs.
- `TRANSLATION_VERIFY_BT_MODEL` (default `gemini-3.1-flash-lite`) is the lite
  back-translation leg of the authoring-time translation gate.
- `OPTION_TRANSLATION_MODEL` (default `gemini-2.5-pro`) is the AUTHORING-time
  knob for baking option `label_translations` into kit JSON (bd polyglot-pdf-2h9j:
  the extraction post-pass, the editor translate-options route, and
  `scripts/authoring/translate_option_labels.py` all read it). Pro over lite on
  the same one-off-per-form rationale as `EXTRACTOR_MODEL`; consumers construct
  `TextAIGemini` with an EMPTY fallback chain (a deliberately chosen tier fails
  loud rather than silently degrading to lite) and a bounded thinking budget
  (2.5-pro cannot disable thinking). The RUNTIME option-translation path (bd
  ow1e) still rides the lite chain -- it is only the fallback for labels a kit
  does not carry.
- `VERTEXAI` (env, **default `true`**) picks the **service/auth mode**, not the
  model. `true` -> Vertex AI ("AI Agent Platform") via service-account ADC +
  `GOOGLE_CLOUD_PROJECT` (compliance-friendly; keeps request data private). `false`
  -> Gemini Developer API (**AI Studio**) via `GEMINI_API_KEY` -- the *only*
  credential AI Studio accepts (no ADC/SA path).

  > **VERTEX IS THE ONLY PRODUCTION PATH** (maintainer directive 2026-08-04, bd
  > `polyglot-pdf-5e6a`). Vertex's privacy agreement is what prevents Google from
  > using client data for model training; AI Studio's consumer terms do not offer
  > that, so no deployed use of it is acceptable. When `K_SERVICE` is set (Cloud
  > Run), `VERTEXAI=false` **fails startup outright** -- there is deliberately
  > **no override flag**. AI Studio is permitted **for local development only** (no
  > `K_SERVICE`), e.g. testing a model that is not yet on Vertex. A model ships
  > only once it is **GA for Vertex customers**.

  The **demo** runs `VERTEXAI=true` (Vertex, SA ADC) with `USE_PREMIUM_MODEL=false`
  and does **not** pin `MODEL_NATIVE`, so the standard tier resolves to
  `gemini-3.8-live` on its own. A/B-ing 3.1 requires the AI-Studio path
  (`VERTEXAI=false`, `USE_PREMIUM_MODEL=true`), so it is a **LOCAL-ONLY** exercise.
  Not surfaced on `/health` (which reports no configuration at all since
  sprint 23 B1b); the startup refusal IS the enforcement.

## Vertex location: Live is regional, text is `global`

The two adapters build their Vertex clients at **different locations**, because
the models they serve are published in different places (all endpoint-verified
on project `polyglot-demo-aa709`, 2026-10-21):

| Model | `us-central1` | `global` | Used by |
|-------|---------------|----------|---------|
| `gemini-3.8-live` | ✅ | ❌ `1008` | `LiveAIGemini` (location `us-central1`) |
| `gemini-3.1-flash-lite` | ❌ `404` | ✅ | `TextAIGemini` default model |
| `gemini-3.5-flash-lite` | ❌ `404` | ✅ | `TextAIGemini` outage fallback |
| `gemini-2.5-pro` | ✅ | ✅ | whole-form validator, authoring |

`TextAIGemini.DEFAULT_VERTEX_LOCATION` is therefore `"global"`. That is still
Vertex -- the same project, service account and no-training data terms -- but the
`global` endpoint carries **no regional data-residency commitment**: Google may
serve the request (field values included) from any region. Whether that is
acceptable for this product's data is tracked in bd `polyglot-pdf-bsq6y`.

Every RUNTIME construction (`backend/dependencies.py`,
`backend/services/editor_text_ai.py`, `backend/services/option_translation.py`)
takes the default. Two AUTHORING scripts pass a location explicitly and stay on
`us-central1` by default: `scripts/authoring/extract_form.py`
(`GOOGLE_CLOUD_LOCATION`) and `scripts/authoring/translate_option_labels.py`
(`--location`). Both default to `gemini-2.5-pro`, which serves at either
location; pointing either at a 3.x lite model also needs `global`.

The text adapter's outage fallback chain (`DEFAULT_FALLBACK_MODELS`) is
`gemini-3.5-flash-lite` -- it stays within the lite tier on purpose (cost
discipline; see [validation-delegation.md](validation-delegation.md)).

`backend/dependencies.py` is the **one** place runtime models reach adapters:
`get_live_ai()` constructs `LiveAIGemini(api_key=settings.GEMINI_API_KEY,
model=settings.MODEL_NATIVE, vertexai=settings.VERTEXAI)` (a fresh instance per
connection -- a CRITICAL bug-fix comment there). `get_text_ai()` constructs
`TextAIGemini(api_key=settings.GEMINI_API_KEY, model=settings.MODEL_LABELING,
vertexai=settings.VERTEXAI)` for the cheap text-gen validator/secretary path.
Routes depend on the service factory, so nothing else picks a runtime model.

## A/B-ing 3.8 vs 3.1

**Locally only.** 3.1 is AI-Studio-only, and a deployed service cannot run the
AI Studio path at all (Vertex-only rule above).

1. Set `USE_PREMIUM_MODEL=true` (or pin `MODEL_NATIVE=<id>`) and restart — no code
   change, no redeploy of a new image.
2. The adapter reports the active model on every token-usage print and binds it to
   its structured logger (`model=self._model_name`).
3. Cost follows automatically: the cost calc keys off the active model's **family**
   via `get_pricing_for_model(self._model_name)` (see
   [logging-and-cost.md](logging-and-cost.md) for the rate table). So a 3.8 vs 3.1
   run is directly cost-comparable from `token_usage.jsonl`.

## Rules

- **Change the model via env, never by editing the adapter.** The constructor's
  `model=` default is a fallback only; prod always passes `settings.MODEL_NATIVE`.
- **When adding a new Live tier/family,** add the model constant here *and* a
  pricing row in `GEMINI_PRICING_BY_FAMILY` (config.py) -- `model_family()` matches
  the rows' keys, so an unlisted family bills at `DEFAULT_PRICING_FAMILY` (`3.8`).
  Also check the family-gated branches in `live_ai_gemini.py` (`thinking_config`,
  tool `behavior`, the text-turn send method) against the new model's migration
  notes. See [logging-and-cost.md](logging-and-cost.md).
- **When adding a text model,** add a `TEXT_GENERATION_PRICING` row (an unpriced
  model logs `cost_estimate_usd=None`) and confirm it answers at
  `TextAIGemini.DEFAULT_VERTEX_LOCATION`.
- **Verify any new model string against the live endpoint** -- on Vertex, at the
  location the adapter actually uses -- before shipping it as a default. A
  plausible-looking name can `1008`/`404`.
