# Logging & cost tracking

**Tracks:** backend/utils/token_file_logger.py backend/config.py backend/adapters/live_ai_gemini.py backend/utils/log_schemas.py backend/utils/structured_logger.py

*Last updated: 2026-08-14 (bd polyglot-pdf-77j0d: the MEASURED COST INVARIANT is
rewritten -- AUDIO-IN now leads where text-in was said to be 95-98%, recovered
from the unshipped bd polyglot-pdf-89mt measurement and re-weighted for today's
shipped SI).*

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

## Structured event schemas (defined, not yet emitting)

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
