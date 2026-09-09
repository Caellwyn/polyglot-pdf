# Logging & cost tracking

**Tracks:** backend/utils/token_file_logger.py backend/config.py backend/adapters/live_ai_gemini.py backend/utils/log_schemas.py backend/utils/structured_logger.py

*Last updated: 2026-09-09 (bd polyglot-pdf-wio6m: usage event v2 -- one emitter
shape for every paid call, the `usage_kind` closed set, and the text +
TTS pricing tables. bd polyglot-pdf-cjifh: the live-voice path now threads
firm/employee/link/kit/channel/model into every per-turn usage event.)*

How this project tracks Gemini token usage + cost, where the per-token rates live,
and the phased roadmap from "JSONL file for local analysis" to a real
observability pipeline.

For **what may and may not be logged** (the PII/PHI rules every logger obeys), see
[hipaa-pii-policy.md](hipaa-pii-policy.md). For the **confirmation audit trail**,
see [confirmation-and-audit.md](confirmation-and-audit.md). For the model-family
selection that drives which rate row is used, see [ai-models.md](ai-models.md).

## Token + cost tracking (live today)

Cost is computed in the Gemini Live adapter and written to a JSONL file for
offline analysis. Counts and costs only — no field values, no transcript text.

### Where the pieces live

- **Rates** — `backend/config.py` holds `GEMINI_PRICING_BY_FAMILY`, a dict of
  per-token rates keyed by model family (`"2.5"`, `"3.1"`). Rates are written as
  per-1M list prices divided by `_PER_1M`. Verified against Google pricing
  2026-05-30:

  | Family | text-in | audio-in | text-out | audio-out |
  |--------|--------:|---------:|---------:|----------:|
  | `2.5` (native-audio) | 0.50 | 3.00 | 2.00 | 12.00 |
  | `3.1` (live preview) | 0.75 | 3.00 | 4.50 | 12.00 |

  `model_family(model_name)` maps a concrete model id to a family key with a
  version-bounded regex (so `gemini-3.1-flash` → `"3.1"` but `gemini-3.10-flash`
  does not). `get_pricing_for_model(model_name)` returns the rate row, falling
  back to `DEFAULT_PRICING_FAMILY` (`"2.5"`) for unknown names. A legacy flat
  `GEMINI_PRICING` alias still resolves to the default family's rates for older
  importers.

  Two **further** tables live beside it, because they bill as different products
  and the Live rates do **not** transfer to them:

  `TEXT_GENERATION_PRICING` prices the plain `generate_content` endpoint (the
  secretary / validator / translation paths), per 1M tokens, verified against
  ai.google.dev/gemini-api/docs/pricing on 2026-09-09:

  | Model | text-in | cached-in | out |
  |-------|--------:|----------:|----:|
  | `gemini-2.5-flash` | 0.30 | 0.03 | 2.50 |
  | `gemini-2.5-flash-lite` | 0.10 | 0.01 | 0.40 |

  `get_text_generation_pricing(model_name)` matches on the id with any
  date/preview suffix stripped, **longest key first** so a `-lite` id is not
  billed at flash rates. Unlike the Live lookup it returns `None` for an unknown
  model rather than a fallback row: for a cost dashboard an explicit gap beats a
  confident wrong number, and callers emit `cost_estimate_usd: None`.

  `TTS_PRICING_USD_PER_CHAR` prices Cloud Text-to-Speech per **character**, keyed
  by voice tier (`tts_voice_tier(voice_name)` resolves
  `{locale}-Chirp3-HD-{persona}` → `Chirp3-HD`). The Chirp3-HD rate is currently
  **`None` — unverified**: cloud.google.com/text-to-speech/pricing could not be
  fetched on 2026-09-09. Per the standing rule, an unfetchable page leaves an
  explicit `None` rather than a number written from memory, and
  `backend/tests/unit/test_pricing_tables.py::test_tts_pricing_is_filled_in` is
  `xfail(strict=True)` on it — so filling the rate in turns that test red and
  forces the marker off. Do not fill it from memory.

- **Cost calc + accumulation** — `backend/adapters/live_ai_gemini.py` reads
  `usage_metadata` off each Gemini response, splits tokens by modality, calls
  `get_pricing_for_model(self._model_name)`, multiplies tokens × rate per modality, and
  accumulates `self._session_total_cost` / `self._session_total_tokens` -- and
`self._connection_total_cost`, which MUST stay in lockstep with them (bd
polyglot-pdf-ik7e). The per-session counters are zeroed on every Gemini
session start, and a SECTION SWITCH restarts that session on the same
adapter -- so they hold one section, which is right for the cost LOG and
fatal for the client-link spend CEILING. The ceiling reads the never-reset
`_connection_total_cost` via `session_cost_usd()`. (+ the
  per-modality running totals) across the Gemini session.

- **The writer** — `backend/utils/token_file_logger.py`. `TokenFileLogger`
  appends one event per turn to `backend/logs/token_usage.jsonl` via
  `log_token_event(...)`. The **caller passes already-computed costs and
  cumulative totals** — the logger does no pricing itself; it just serializes the
  event (per-event `event`/`cost` blocks + a `session_cumulative` block) and
  flushes. A single global instance is reached via `get_token_logger()`. The
  module docstring is explicit: this file is for local development / the
  visualization dashboard, **not** production (BigQuery is the eventual prod
  path — see roadmap Phase 5).

> **Why cost matters here.** The Gemini Live API re-bills the *entire accumulated
> context* on every turn, and native audio accrues ~25 tokens/sec (see
> `docs/genai_docs/` live-api-best-practices). Long sessions get expensive fast —
> the motivation for the sliding-window compression that ships by default today
> (see [../components/context-compression.md](../components/context-compression.md),
> bd `polyglot-pdf-x8rt` / `polyglot-pdf-7872`). The cumulative cost in
> `token_usage.jsonl` is the baseline that work measures against.

> **MEASURED COST INVARIANT -- AUDIO-IN NOW LEADS (do not re-derive from the rate
> table).** On the **2.5** native-audio model with the production configuration
> (continuous DTI + DERIVED context compression), **audio-input is the largest
> single cost line**, with text-input close behind on the happy path:
>
> | | audio-in | text-in | other |
> |---|---|---|---|
> | happy path | ~49% | ~47% | ~4% |
> | unhappy path (corrections) | ~60% | ~36% | ~5% |
>
> **This is an EVOLUTION and a WIN, not a contradiction of the older number.**
> Text-in genuinely *was* 95-98% of session cost when it was measured (bd
> `polyglot-pdf-wyhh` / `jnjj.6`): the SI was ~4.4k tokens re-sent every turn on
> top of a context that accumulated without bound, so text volume swamped
> everything. Two pieces of work removed that -- **context-window compression**
> (bd `polyglot-pdf-x8rt` / `polyglot-pdf-7872`) bounds the re-sent context to the
> derived sliding window, and the **SI diet** (epic `polyglot-pdf-jnjj`, shipped in
> bd `polyglot-pdf-6a79`) cut the static backbone. With text-in capped, the ~6x
> per-token price gap on audio finally shows through. The text side has been
> optimized to where it is no longer the dominant problem; what remains is largely
> the irreducible cost of a voice product.
>
> **Implication -- the cost levers have MOVED:**
> 1. **Audio-in** (how much the user speaks, and how many turns they take) is now
>    the biggest line. A correction costs disproportionately because it adds
>    expensive audio, not cheap text -- measured: the unhappy path's audio-in is
>    2.52x the happy path's while its text-in is only 1.54x.
> 2. **Billed events per turn.** A turn averages ~2.1 billed events because a tool
>    call re-sends the whole context, so per-turn text-in runs ~1.7x the context
>    size. Cutting one tool round-trip per field saves a whole context re-send.
> 3. **SI size** still matters (it sets the compression floor, and a bigger SI
>    derives a bigger window -> fewer evictions) but it is no longer the single
>    dominant line it was.
>
> **PROVENANCE, and what would invalidate this.** The underlying run is bd
> `polyglot-pdf-89mt` (full 22-field W-7, both paths, deploy-fidelity config;
> $0.59 happy / $1.25 unhappy all-in, ~$0.05/field flat across the form). Its
> raw artifacts were deliberately NOT shipped -- the numbers live in that bead's
> close reason, which is the citable record. **Its raw split (56% / 66% audio-in)
> was measured on a ~2,485-token SI; the SHIPPED `DTI_SYSTEM_INSTRUCTION` is
> ~3,363 tokens today** (measure it: `len(Settings().DTI_SYSTEM_INSTRUCTION)/4`),
> so the table above re-weights that extra text at ~2.1 events/turn. **The
> ORDERING is the durable finding; treat the percentages as approximate.**
> Re-measure if the SI changes materially, and note the split depends on
> compression being ON and DERIVED -- on a loose 12000/9000 window text-in
> re-inflates and the old "SI is everything" shape returns (cost/field rose 2.10x
> across a form vs 1.15x with the derived window).
>
> (On **3.1** the split shifts again -- reasoning/thinking bills as *output*; but
> 2.5 is the production tier.) Older source tables, superseded but retained for
> the pre-compression baseline: `scripts/spikes/form_session_costs_findings.md`
> and `scripts/spikes/jnjj_g2_jit_cost_findings.md`.

## Structured event schemas

`backend/utils/log_schemas.py` defines `TypedDict` shapes for a structured event
stream (`BaseLogEvent`, `TokenUsageMetadata`, `SessionEventMetadata`,
`FieldEventMetadata`, `ErrorEventMetadata`, `WebSocketEventMetadata`) plus an
`EventType` literal. The shapes are HIPAA-shaped by construction — `BaseLogEvent`
carries `field_id` with the comment `# NEVER include field values!` and has no
value field.

`backend/utils/structured_logger.py` (`StructuredLogger` / `get_logger()`) imports
these schemas and exposes a typed, stdout-JSON emit API for the Cloud Run → BigQuery
pipeline ("LOGGING_OVERHAUL_PLAN Phase 1"). The **one** wired emitter today is the
per-turn token event: `live_ai_gemini.py` calls
`get_structured_logger().log_gemini_api_response(...)` alongside the file write, so
every turn's counts + costs land as a `gemini_api_response` `jsonPayload` line in
Cloud Logging — queryable/exportable off a deployed run without scraping the
`print()` block (bd `polyglot-pdf-5c2h`). The remaining event types (session
lifecycle, field, error) are still scaffolding — the contract is defined, the wiring
lands in Phases 2–4 below.

### Usage event v2 — one shape for every paid call

Every paid model or TTS call emits the **same** event shape, so the Cloud Logging
→ BigQuery sink sees one column shape instead of one per call path. The private
`StructuredLogger._emit_usage(...)` is the single emitter; three thin wrappers sit
on top of it:

| Wrapper | `event_type` | Covers |
|---------|--------------|--------|
| `log_gemini_api_response` | `gemini_api_response` | the Gemini Live voice session |
| `log_text_ai_usage` | `text_ai_usage` | secretary / validator / translation `generate_content` |
| `log_tts_usage` | `tts_usage` | spell-back / notice / intro `synthesize_speech` |

`log_gemini_api_response` keeps its v1 name and positional signature, so the live
adapter's existing call site is untouched; the new ids arrive as optional keywords.

The kind of paid call is carried in a **`usage_kind`** field, not in the key set.
`backend/utils/log_schemas.py` defines it as a closed `Literal`: `live_voice`,
`text_secretary`, `text_validator`, `text_translation`, `tts_spellback`,
`tts_notice`, `tts_intro`. The envelope's optional context keys are listed once in
`USAGE_CONTEXT_KEYS` (`firm_id`, `employee_id`, `link_jti`, `kit_id`, `channel`,
`model`), and `_emit_usage` writes **all** of them on **every** call, `None`
included.

That unconditional write is the point of v2. At the BigQuery sink a *missing* key
and a *null* are different things: a row that simply omits `firm_id` drops out of a
`GROUP BY firm_id` silently, so a per-firm cost total under-reports with no error
anywhere. A null is queryable. `backend/tests/test_usage_event_schema.py` pins this
per `usage_kind`, deriving the key list from `USAGE_CONTEXT_KEYS` rather than
repeating it.

**PII:** ids, counts, costs and model names only. The envelope has no slot for a
field value or transcript, so the shape is HIPAA-safe by construction — see
[hipaa-pii-policy.md](hipaa-pii-policy.md) and
`backend/tests/test_no_pii_logging.py`.

**Call-site coverage.** `backend/tests/test_usage_event_coverage.py` AST-walks
everything under `backend/` that Cloud Run executes (exclusion-derived, like
`backend/tests/unit/test_deployed_iam_envelope.py`) and enumerates every
`generate_content`, `aio.live.connect` and `synthesize_speech` call. The set must
equal a pinned allowlist, so a new paid call anywhere fails the test the day it is
added rather than billing silently. `backend/scripts/` is deliberately out of
scope: those probes run on an operator's own budget. Today the allowlist holds
three sites — the Live adapter, the text adapter, and `spellback_tts._synthesize_sync`
(which `intro_tts` and `notice_tts` both call, so the three TTS paths share one
site). The text and TTS emit proofs are `xfail(strict=True)` until bead
`polyglot-pdf-t86oz` plumbs the ids through; strict, so wiring one turns the test
red and forces the marker off. The Live adapter's own proof is NOT xfail (it
already called `log_gemini_api_response` before this): bd `polyglot-pdf-cjifh`
widened that existing call with the firm/employee/link/kit/channel/model
context ids (`_handle_fill_session` -> `FormFillingService.start_session` ->
`LiveAIGemini.set_session_context`, threaded from the WS route's decoded
token claims and `link_tokens.link_channel()`), so a live-voice usage event now
actually carries them instead of six nulls.

(Routine application logging today goes through `structlog` — `structlog.get_logger()`
bound per module — not through `StructuredLogger`.)

## Voice round-trip timing checkpoints (bd polyglot-pdf-cwsy)

The backend logs `structlog` INFO events at every stage of the voice round trip
so tool-call latency can be attributed (no field values are ever logged):
`timing_session_connect_ready`, `timing_sysinstruction_build` (+`size_bytes`),
`timing_activity_start`/`timing_activity_end`, `timing_tool_call_received`
(`tool`, `since_activity_end_ms` -- the headline user-to-tool-call number),
`timing_tool_callback_ms`, `timing_tool_response_sent`,
`timing_coordinator_roundtrip` (`request_type`, `roundtrip_ms`),
`timing_section_switch_total`, and `timing_audio_drops_session` (emitted only
when nonzero; `audio_frames_dropped` also rides in the session-end
`session_cost_summary`). The adapter also logs `gemini_go_away_received`
(`time_left`) when the Live server sends a GoAway message before terminating
the connection -- no PII, just the duration string.

## Roadmap (phased)

Phase 1 (token/cost file logging) is done. The remaining phases are tracked as
beads; this doc is their canonical home (migrated out of
`planning_documents/TODO.md`).

| Phase | Scope | Bead |
|-------|-------|------|
| 1 — Token/cost logging | per-event + per-session token + cost to JSONL | **done** |
| 2 — Session lifecycle | `session_start`/`session_end` + WS connect/disconnect, keyed by `form_session_id` | `polyglot-pdf-g0e` |
| 3 — Frontend `logger.ts` | batched client event emitter; keeps PHI local | `polyglot-pdf-3ae` |
| 4 — Field + error tracking | voice attempts, manual edits, section nav, error categorization | `polyglot-pdf-ytf` |
| 5 — BigQuery integration | Cloud Logging → BQ sink + log receiver | `polyglot-pdf-0bs` |
| 6 — Compliance + audit | separate dataset, IP hashing, zero-PII validation | `polyglot-pdf-yqg` |
