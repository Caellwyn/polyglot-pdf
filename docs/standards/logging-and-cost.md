# Logging & cost tracking

**Tracks:** backend/utils/token_file_logger.py backend/config.py backend/adapters/live_ai_gemini.py backend/utils/log_schemas.py

*Last updated: 2026-05-30*

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
  `get_pricing_for_model(self._model)`, multiplies tokens × rate per modality, and
  accumulates `self._session_total_cost` / `self._session_total_tokens` (+ the
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
> context* on every turn, and native audio accrues ~25 tokens/sec. Long sessions
> get expensive fast — the motivation for the context-compression epic
> (`polyglot-pdf-l3a`). The cumulative cost in `token_usage.jsonl` is the baseline
> that work measures against.

## Structured event schemas (defined, not yet emitting)

`backend/utils/log_schemas.py` defines `TypedDict` shapes for a structured event
stream (`BaseLogEvent`, `TokenUsageMetadata`, `SessionEventMetadata`,
`FieldEventMetadata`, `ErrorEventMetadata`, `WebSocketEventMetadata`) plus an
`EventType` literal. The shapes are HIPAA-shaped by construction — `BaseLogEvent`
carries `field_id` with the comment `# NEVER include field values!` and has no
value field.

`backend/utils/structured_logger.py` (`StructuredLogger` / `get_logger()`) imports
these schemas and exposes a typed, stdout-JSON emit API for the Cloud Run → BigQuery
pipeline ("LOGGING_OVERHAUL_PLAN Phase 1"). But **it emits nothing yet**: the only
non-test reference is a single dead import in `live_ai_gemini.py`
(`get_logger as get_structured_logger`) that is never called. So the typed event
stream is scaffolding — the contract is defined, the wiring lands in Phases 2–4 below.

(Routine application logging today goes through `structlog` — `structlog.get_logger()`
bound per module — not through `StructuredLogger`.)

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

*Last updated: 2026-05-30*
