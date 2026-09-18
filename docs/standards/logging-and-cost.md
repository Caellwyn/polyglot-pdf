# Logging & cost tracking

**Tracks:** backend/utils/token_file_logger.py backend/config.py backend/adapters/live_ai_gemini.py backend/adapters/text_ai_gemini.py backend/services/spellback_tts.py backend/services/notice_tts.py backend/services/intro_tts.py backend/utils/log_schemas.py backend/utils/structured_logger.py scripts/setup-telemetry.sh sql/telemetry_views.sql backend/services/credit_ledger.py backend/utils/logging.py scripts/setup-monitoring.sh scripts/telemetry_bq_setup.py

*Last updated: 2026-09-18 (bd polyglot-pdf-65jeu: module-level `structlog.get_logger().bind(...)` froze `ConsoleRenderer` onto 49 loggers, so `ledger_export`, `form_session_ended`, `usage_rollup_written` and `sweep_expired_links_complete` reached Cloud Logging as textPayload and never matched the sink's `jsonPayload.event_type` filter -- the income view had no source rows. All 49 sites are now bind-free `structlog.get_logger(module=...)`, and the processor chain is applied at import of `backend/utils/logging.py`, which both `main.py` files now import first. NOTE for the post-deploy check: the stdout/stderr split described below was measured when these lines were console-rendered; which stream the now-JSON rows land on must be re-confirmed against the live table names before the `${TELEMETRY_TABLE_STDERR}` assumption in `sql/telemetry_views.sql` is trusted.)*

*Last updated: 2026-09-18 (bd polyglot-pdf-vm2fu: `scripts/setup-telemetry.sh`'s sink-table detection now goes through a new `scripts/telemetry_bq_setup.py list-tables` subcommand instead of `bq ls --project_id=... --format=csv "$DATASET" 2>/dev/null | tail -n +2` -- that pipeline swallowed stderr and treated an EMPTY listing as "no tables yet", indistinguishable from a `bq` CLI that failed to list at all (observed live: a broken `bq` shim on one machine returned nothing while the sink's stdout table was confirmed present via the same google-cloud-bigquery client this script already depends on for LOCATION derivation and the dataset-scoped IAM grants). `list-tables` exits non-zero with a message on any real API error, which the script now aborts on rather than silently reporting every gated cost view PENDING.)*

*Last updated: 2026-09-17 (bd polyglot-pdf-k5w16: the sink-writer dataEditor grant call was doubling the `serviceAccount:` prefix on a re-run -- `gcloud logging sinks describe --format=value(writerIdentity)` already returns it prefixed, but the grant call always assumed a bare email -- aborting the script under `set -e` before any view was applied. `scripts/setup-telemetry.sh` now normalises WRITER_IDENTITY to a bare email once, right after both the create and update branches assign it. `telemetry_bq_setup.py grant-dataset-role` is also now idempotent-tolerant on the write path: an `update_dataset` failure whose message says the access entry already exists is logged and treated as success rather than aborting, on top of the pre-existing snapshot-based `already_granted` check. Separately, `sql/telemetry_views.sql`'s header wrongly claimed `CREATE VIEW` tolerates a not-yet-existent source table ("BigQuery views are late-bound") -- live-confirmed false: creating `income_month` before the sink's stderr-stream table existed failed with a 404 at CREATE time, not a successfully-created zero-row view. `setup-telemetry.sh` now applies each of the five views independently, gated on whether ITS OWN source table already exists, reporting the rest as pending and exiting 0 -- see the "Views" and "IAM" paragraphs below.)*

*Last updated: 2026-09-17 (bd polyglot-pdf-vzvio: scripts/setup-telemetry.sh derives the telemetry dataset LOCATION from the Cloud Billing export dataset via new scripts/telemetry_bq_setup.py, instead of a hard-coded us-central1, and the sink-writer dataEditor + admin-backend-sa dataViewer grants move to that script's grant-dataset-role subcommand -- the BigQuery API's Dataset.access_entries -- instead of `bq add-iam-policy-binding`, which was exiting non-zero on at least one maintainer machine.)*

*Last updated: 2026-09-16 (bd polyglot-pdf-2kbo0, sprint 23 B1b: the `/health` payload is status + the two probes and nothing else.)*

*Last updated: 2026-09-16 (bd polyglot-pdf-wfgjz, sprint 23 B1a: the token file is local-dev only on two guards -- a K_SERVICE no-op in the writer and the .env.DEV gate at the call site -- and the per-turn print() banner is now the structured `token_usage` event. On a deployed instance `configure_logging` never runs below INFO.)*

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
  | `gemini-2.5-pro` | 1.25 | 0.125 | 10.00 |

  The `gemini-2.5-pro` row is the `<=200k`-token-prompt tier (this app's
  validator/translation prompts never approach 200k); the page's `>200k` tier
  is not carried here. It bills `VALIDATOR_PRO_MODEL`'s default-on whole-form
  pass and `OPTION_TRANSLATION_MODEL`'s authoring-time bake -- both
  `gemini-2.5-pro` by default (`backend/config.py`) -- so a missing row here
  would leave the product's single most expensive text call reporting a null
  cost.

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
  flushes. A single global instance is reached via `get_token_logger()`. This
  file is for local development / the visualization dashboard, **not**
  production, on two independent guards (bd `polyglot-pdf-wfgjz`):
  `log_token_event` returns without writing when `K_SERVICE` is set, and the
  adapter's call site runs only under the `backend/.env.DEV` marker
  (`DEV_LOGGING_ENABLED`), which the image never carries. BigQuery is the
  production path (Phase 5 below).

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
Cloud Logging — queryable/exportable off a deployed run. The per-turn console
banner that used to `print()` the same counts is gone: it is one structured
`token_usage` event (counts + cost, no text), so the per-turn token counts no
longer reach stdout outside structlog's processors (bd `polyglot-pdf-wfgjz`). The remaining event types (session
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
site). All three are `emit_wired: True` now — bd `polyglot-pdf-cjifh` (live)
and bd `polyglot-pdf-t86oz` (text + TTS) both landed, so none of the
allowlist's `test_paid_site_emits_a_usage_event` cases is xfail any more. The
Live adapter's own proof was never xfail (it already called
`log_gemini_api_response` before this): bd `polyglot-pdf-cjifh` widened that
existing call with the firm/employee/link/kit/channel/model context ids
(`_handle_fill_session` -> `FormFillingService.start_session` ->
`LiveAIGemini.set_session_context`, threaded from the WS route's decoded
token claims and `link_tokens.link_channel()`), so a live-voice usage event now
actually carries them instead of six nulls. bd `polyglot-pdf-t86oz` did the
same for the other two: `TextAIGemini._generate` takes an optional
`usage_kind` + `session_ctx` (the singleton adapter cannot hold session ids
on `self`, so callers thread them through the call — `ValidatorService` and
`FormFillingService._text_ai_session_ctx()`), emitting `log_text_ai_usage`
with a cost from `TEXT_GENERATION_PRICING`; and each of `synthesize_spellback`
/ `synthesize_notice` / `synthesize_intro` calls a shared
`_log_tts_usage_event` helper (`spellback_tts.py`) after an ACTUAL synthesis
(never on a cache hit), emitting `log_tts_usage` with a character count and a
cost from `TTS_PRICING_USD_PER_CHAR` — `None` today since that table's
Chirp3-HD rate is still the unverified `None` above.

(Routine application logging today goes through `structlog` — `structlog.get_logger()`
bound per module — not through `StructuredLogger`.)

## BigQuery telemetry sink + cost/income views (bd polyglot-pdf-rd3s8, E3.6)

Declarative, operator-run infrastructure -- `scripts/setup-telemetry.sh` creates
the `polyglot_telemetry` dataset, a Cloud Logging sink over
THREE Cloud Run services -- the public backend, its staging twin, AND the admin
service (`polyglot-admin`; `ledger_export` is emitted only by
`admin_backend/routes/credit_routes.py` and `sweep_routes.py`, never by the
public backend, so leaving the admin service out of the sink filter makes
`income_month` return zero rows forever) -- the IAM grants the sink and
`admin-backend-sa` need, and applies `sql/telemetry_views.sql`'s view
definitions via `bq query`. Nothing here runs from a deploy script; an operator
runs it by hand, same as `setup-gcp-project.sh` and `setup-admin-service.sh`.

**The sink filter is three shapes ORed together, not one.** The plan's prose
("filtered to `jsonPayload.event_type` in the usage / session / ledger_export /
error set") reads as if every emitter carries `event_type` at the same JSON
depth. It does not -- verified against real emitted JSON, not reconstructed from
memory:

| Event kind | Emitter | Actual JSON shape |
|---|---|---|
| Usage (`gemini_api_response`, `text_ai_usage`, `tts_usage`) | `StructuredLogger._emit` | **nested**: `jsonPayload.message.event_type`, and every context/cost/count field one level deeper still, under `jsonPayload.message.metadata.*` |
| `ledger_export` | `credit_ledger.py`'s plain `structlog` call, with an explicit `event_type=` kwarg | **flat**: `jsonPayload.event_type` |
| `form_session_started` / `form_session_ended` | `confirmation_logger.py`'s plain `structlog` calls, with **no** `event_type` kwarg | **flat, different key**: `jsonPayload.event` (structlog's positional event name, since no `event_type` was bound) |

A filter checking only `jsonPayload.event_type IN (...)` would silently drop
every session row (wrong key) and every usage row (wrong nesting depth) while
matching only `ledger_export` -- BigQuery would return zero session/usage rows
with no error anywhere. `scripts/setup-telemetry.sh`'s `SINK_FILTER` is an OR
across all three shapes instead. Error events (the plan's fourth member) are
deliberately not yet in the filter: Epic 3 bead 8 (`setup-monitoring.sh`, not
this bead) is what first wires `StructuredLogger.log_error` to a real call
site, and it will land under the same nested `message.event_type` shape as
usage events when it does.

**A logger bound at IMPORT time never reaches the sink at all** (bd
polyglot-pdf-65jeu). `structlog.get_logger().bind(module=...)` at module level
instantiates the bound logger against the configuration current AT THAT MOMENT.
Both apps import their route and service modules BEFORE calling
`configure_logging()`, so all 49 such loggers kept structlog's DEFAULT
processors -- `ConsoleRenderer` -- for the life of the process, and their lines
reached Cloud Logging as **textPayload** (`2026-09-15 21:38:03 [info     ]
ledger_export  amount=-1 ...`), not the `jsonPayload` the sink filter matches.
Observed live on staging 2026-09-18: `ledger_export`, `form_session_ended`,
`usage_rollup_written` and `sweep_expired_links_complete` were all invisible to
BigQuery, so `income_month` (source: `ledger_export`) could not be built. Only
`StructuredLogger._emit`'s usage events were unaffected, because that emitter
prints its own `json.dumps` rather than going through the processor chain.
The fix has two independent halves: every module-level logger is now created
bind-free as `structlog.get_logger(module=...)` (a lazy proxy that resolves
configuration on the first LOG call), and `backend/utils/logging.py` applies
the chain at ITS OWN import, with both `main.py` files importing it FIRST --
which also covers a module that logs during its own body, as
`backend/services/auth.py` does with `firebase_admin_initialized`. Pinned by
`tests/test_structlog_json_output.py` (a fresh subprocess import of each real
app) and by the empty-set assertion in `backend/tests/unit/test_error_shape.py`.

**The sink lands rows in TWO destination tables, not one** (bd
polyglot-pdf-ih428): a Cloud Logging -> BigQuery sink names its destination
table per LOG ID, and this sink's filter matches both the
`run.googleapis.com/stdout` stream (usage events -- `StructuredLogger._emit`
prints them directly to stdout) and the `run.googleapis.com/stderr` stream
(`ledger_export` and the session events -- plain `structlog` calls that reach
stdlib logging's root handler, which `backend/utils/logging.py`'s
`configure_logging()` leaves at Python's default stream, stderr, having never
passed `stream=`). `scripts/setup-telemetry.sh` discovers both table names via
`scripts/telemetry_bq_setup.py list-tables` (bd polyglot-pdf-vm2fu), NOT `bq
ls` -- the old `bq ls ... 2>/dev/null | tail -n +2` pipeline swallowed stderr
and treated an EMPTY listing as "no tables yet", indistinguishable from a
`bq` CLI that failed to list at all (a broken shim, a DNS blip); a
list-tables API error now aborts the script instead of silently reporting
every gated view PENDING -- and substitutes the discovered names into two
separate SQL placeholders, `${TELEMETRY_TABLE_STDOUT}` and
`${TELEMETRY_TABLE_STDERR}`.

**Views** (`sql/telemetry_views.sql`): `cost_by_firm_month`, `cost_by_kit_month`,
`cost_by_employee_month` (all three read the nested usage-event shape from
`${TELEMETRY_TABLE_STDOUT}`, grouped by month + the relevant id +
`usage_kind`, so different paid paths never sum into one opaque total),
`hosting_cost_by_service_month` (reads the Cloud Billing detailed export
table -- a separate maintainer console step, Epic 3 bead 7, not retroactive --
filtered to Cloud Run + Firebase Hosting SKUs), and `income_month` (reads
`ledger_export` rows from `${TELEMETRY_TABLE_STDERR}`, `type IN ('purchase',
'subscription_grant')`, with `firm_kind = 'live'` **hard-coded in the view**
so a caller cannot forget the mock-firm filter -- this bead inherits Epic 3's
overall exit criterion 5, the income-filter half). Every view's referenced
columns are pinned by `backend/tests/unit/test_telemetry_views.py` as a
**derived** set (from `log_schemas.USAGE_CONTEXT_KEYS` and
`credit_ledger.LEDGER_EXPORT_FIELDS`), not hand-listed, so a view that drifts
onto a column its source event does not emit fails there instead of shipping
a silently-null dashboard column.

**Each view is applied independently, gated on its OWN source table existing** (bd polyglot-pdf-k5w16). `CREATE VIEW` requires its referenced table to already exist -- "BigQuery views are late-bound" is true only for re-resolving a table reference at QUERY time, not at CREATE time, and an earlier version of this file and `sql/telemetry_views.sql` both got that backwards (live-confirmed: applying `income_month` before the sink's stderr-stream table existed failed with a 404, not a quietly-empty view). `scripts/setup-telemetry.sh` therefore extracts and applies each view's `CREATE OR REPLACE VIEW` statement on its own `bq query` call -- `cost_by_firm_month`/`cost_by_kit_month`/`cost_by_employee_month` gated on `TELEMETRY_TABLE_STDOUT`, `income_month` gated on `TELEMETRY_TABLE_STDERR`, and `hosting_cost_by_service_month` applied whenever `BILLING_EXPORT_TABLE` was given at all -- reporting any view whose table is not there yet as PENDING and still exiting 0, instead of the previous all-or-nothing gate that skipped every view until BOTH sink tables existed.

**The dataset location is DERIVED from the Cloud Billing export dataset, not
hard-coded** (bd polyglot-pdf-vzvio). BigQuery refuses to create a view that
reads a table in a different location than its own dataset --
`hosting_cost_by_service_month` does exactly that, reading the maintainer's
billing export table -- so a fixed `us-central1` silently breaks that view
the moment the billing export happens to live elsewhere (observed 2026-09-15:
the maintainer's export is in the US multi-region). When
`BILLING_EXPORT_TABLE` is given, `scripts/setup-telemetry.sh` calls
`scripts/telemetry_bq_setup.py resolve-location` (the `google-cloud-bigquery`
API, already a backend dependency) to read that table's own dataset location
and uses it for the telemetry dataset; that helper refuses (aborting the
script) if the telemetry dataset already exists, already holds tables, and
its location differs from the billing dataset's -- a populated dataset cannot
be moved between locations, so the script must not paper over the conflict
with a location it cannot actually apply. Only the no-`BILLING_EXPORT_TABLE`
path still defaults to `us-central1`, since there is nothing to derive a
location from yet.

**The sink step is create-or-update, not create-only** (bd polyglot-pdf-f7f0h):
`scripts/setup-telemetry.sh` runs `gcloud logging sinks describe` first to
decide between `sinks create` (first run) and `sinks update` (the sink
already exists), so a re-run after `SINK_FILTER` changes -- e.g. a future
bead adding the error-event clause -- actually applies the new filter to the
live sink. A bare `sinks create` fails on an existing sink and cannot do
this, which is why the script never relies on create alone.

**IAM:** the sink's own writer identity (printed by `gcloud logging sinks
create`'s output on first creation, or read back via `gcloud logging sinks
describe --format=value(writerIdentity)` on a re-run, parsed at runtime
either way) gets `roles/bigquery.dataEditor` on the dataset;
`admin-backend-sa` gets `roles/bigquery.jobUser` (project-level, to run
queries) and dataset-scoped `roles/bigquery.dataViewer` -- both moved out of
`admin_backend/tests/unit/test_admin_sa_iam_envelope.py`'s `DEFERRED_ROLES`
set into `EXPECTED_ADMIN_SA_ROLES`, granted by `scripts/setup-telemetry.sh`
rather than `scripts/setup-admin-service.sh`'s `PROJECT_ROLES` array (that
script grants the admin service's non-BigQuery roles; this dataset-adjacent
pair travels with the script that creates the dataset). **The two
dataset-scoped grants (the sink writer's `dataEditor` and
`admin-backend-sa`'s `dataViewer`) go through `scripts/telemetry_bq_setup.py
grant-dataset-role`, not `bq add-iam-policy-binding`** (bd
polyglot-pdf-vzvio): on at least one maintainer machine `bq` itself exits
non-zero on this call because its shim needs `CLOUDSDK_PYTHON` pointed at an
installed Python, which aborted the whole script (via `set -e`) before the
views were ever applied. The helper grants the role through
`google-cloud-bigquery`'s `Dataset.access_entries` + `Client.update_dataset`
-- the same mechanism `bq add-iam-policy-binding` itself uses on a dataset
target -- and is idempotent two ways (bd polyglot-pdf-k5w16 added the
second): a SNAPSHOT check before writing (an access entry already granting
the exact role/member pair, in either its IAM-style or BigQuery's own
normalized legacy READER/WRITER/OWNER form, is left alone -- no write
attempted), and an update_dataset failure whose message says the entry
already exists is treated as success rather than an abort (covers a
concurrent grant racing this one, or a live entry shaped in a way the
snapshot check does not recognize). `admin-backend-sa`'s project-level
`roles/bigquery.jobUser` is unaffected: it was always granted via `gcloud
projects add-iam-policy-binding`, which never used `bq`.

**WRITER_IDENTITY is normalised to a bare email before that grant call**
(bd polyglot-pdf-k5w16). The two branches above hand back DIFFERENT
shapes for the same value: `gcloud logging sinks describe
--format=value(writerIdentity)` (the re-run/update branch) already
returns the `serviceAccount:service-...` PREFIXED form, while the
create-branch grep pulls a bare email straight out of `sinks create`'s
own output. The grant call always assumed the bare shape
(`--member "serviceAccount:$WRITER_IDENTITY"`), which doubled the prefix
on the update branch -- observed live 2026-09-17: the first re-run after
PR #850 landed aborted with `could not grant roles/bigquery.dataEditor ...
to serviceAccount:serviceAccount:service-...`, and `set -e` meant the
view-creation step never ran even though the underlying grant was fine.
`setup-telemetry.sh` now strips a leading `serviceAccount:` from
WRITER_IDENTITY once, right after both branches assign it and before the
grant call reads it.

## Errors, close events, and monitoring (bd polyglot-pdf-e4dt8, E3.8)

### The exception shape

`backend/utils/logging.py` runs `pii_safe_exception_processor` in the
structlog chain, NOT `structlog.processors.format_exc_info`. The stock
processor renders the exception MESSAGE, and in a form-filling app that
message can embed a field value (a parse error over an A-number, a validation
error naming a date of birth) -- a P0 (bd `polyglot-pdf-p84m`).

Every `.exception(...)` / `exc_info=True` site under `backend/` or `admin_backend/` renders
through this one processor, which emits:

| Field | Content |
|-------|---------|
| `error_type` | The exception class NAME, so a log filter can count by type without parsing a trace. |
| `stack_trace` | Frames as `file`, `line`, `function` only -- plus each exception's TYPE. Never the message, never locals, never source text. The `__cause__` / `__context__` chain is walked (capped at 5 links, 30 frames each). |
| `severity` | The level, UPPERCASED. Cloud Logging reads `severity`, not structlog's lowercase `level`; `level` stays in place for existing queries. |

That is the shape Cloud Error Reporting ingests and GROUPS on. The earlier
local fix -- a bare `error_type=type(e).__name__` line at two call sites in
`live_ai_gemini.py` -- was PII-safe but ungroupable, so Error Reporting showed
nothing. A file path, a line number and a function name are repository facts,
not user data, so frames buy grouping at no privacy cost.

The message is DROPPED, not scrubbed: the value arrives as arbitrary user
speech, so no pattern covers it and only a wholesale drop cannot be defeated
by an input. Developers who need the message have the `DEV_LOGGING_ENABLED`
file log (`backend/utils/dev_file_logger.py`), which never leaves the machine.

`EXCEPTION_LOGGING_SITES` in that module registers every file in either
service that logs an exception; `backend/tests/unit/test_error_shape.py` re-derives the set from
the AST and fails on an addition or a removal, so a new site is visible at
review rather than after it has shipped. `backend/tests/test_no_pii_logging.py`
carries the sentinel case: an exception whose message contains a sentinel must
render frames and type with the sentinel nowhere in the output.

### WebSocket close events

`StructuredLogger.log_ws_close` emits every close as a structured,
NON-exception `ws_error` event carrying `metadata.close_code` and
`metadata.reason_token`, at a severity derived from the code
(`WS_CLOSE_SEVERITY`): 1011/1006 ERROR, 1007/1008/1013 WARNING, anything
unclassified ERROR so it is loud rather than silent.

Non-exception on purpose -- a close is a control-plane outcome with no
traceback, and routing thousands of frame-less entries into Error Reporting
would drown the real crashes.

`websocket_routes._close_ws` wraps every close on `/fill` (it never raises: a
telemetry failure on a teardown path must not turn a clean refusal into a
500). The 1011/1006 family is emitted from `live_ai_gemini.py` instead,
because that is a GEMINI-side close the route only learns about second hand,
and only for the spontaneous-drop codes -- a normal end and a GoAway expiry
come through the same block. `reason_token` is a FIXED identifier, never
user-derived text.

`backend/tests/unit/test_ws_close_events.py` pins both the shape and the SET:
an AST walk finds every `close()` on the route, and a bare one outside the
allowlist fails.

### scripts/setup-monitoring.sh (operator-run)

Sibling of `setup-telemetry.sh`. Declarative and idempotent
(describe-then-create-or-update at every step -- policies and uptime checks
have no operator-chosen id, so a create-only script would duplicate them on
every re-run). Pinned by `tests/test_setup_monitoring_script.py`.

| Resource | Detail |
|----------|--------|
| `ws_close_1011_count` | Gemini-side drops. 1006 is deliberately excluded -- it also fires on ordinary network churn, which would raise the metric's floor above the alert threshold. |
| `ws_close_1013_count` | Budget refusals. A business signal, not an error: a rising rate means link ceilings are too low for real usage. |
| `mint_refused_count` | Refused mint requests. |
| Policy `polyglot 5xx rate` | Cloud Run's own `request_count` by response class, `ALIGN_RATE` over 5m. |
| Policy `polyglot ws 1011 rate` | Reads the log-based metric above, `ALIGN_RATE`, 15m duration -- an occasional 1011 is a tolerated fact of the native-audio models. |
| Uptime checks | ONE PER CHANNEL on `/health`: demo, staging, admin. Staging and demo run different code on the same project, so a shared check would either miss a broken demo or page on a staging channel that is expected to be broken. |
| IAM | `roles/errorreporting.viewer` + `roles/monitoring.viewer` on `admin-backend-sa`, moved out of the IAM envelope test's `DEFERRED_ROLES`. `polyglot-backend-sa` gains neither (scar #7), pinned negatively. |

**Filter shapes matter more than the field names.** This repo emits through
two renderers: `StructuredLogger._emit` nests its envelope under a `message`
key (so `ws_error` reads at `jsonPayload.message.event_type`, with the code at
`jsonPayload.message.metadata.close_code`), while a plain structlog call
renders flat at `jsonPayload.event` (where `link_mint_refused` lives). A
filter written at the wrong depth matches NOTHING while the script still exits
0 -- an alert that never fires, which nothing else would notice. The tests
assert the depth of each path, and `setup-telemetry.sh`'s sink filter gained
`ws_error` in its nested clause so these rows reach BigQuery too.

### /health probes

`/health` reports two Firestore probes: `confirmation_sink` (a WRITE probe --
that writer fails OPEN) and `firms_store` (a READ probe -- that reader fails
CLOSED, so IAM drift silently hides every firm's private kits). Both are
cached 5 minutes, coalesce concurrent callers onto one round trip, and are
bounded by a separate `HEALTH_PROBE_TIMEOUT_S` `wait_for` each -- `/health` is
unauthenticated, so any caller can drive them at their own rate, and a stalled
store must not eat the other probe's answer. A degraded probe still returns
200: the ALERT pages, not a flapping uptime check. Those two probes and
`status` are the WHOLE payload: no model id, audio rate, upload limit,
provider flag or key-presence bit (sprint 23 B1b), because the route is
unauthenticated and anything more is a free fingerprint of the deployment.


### The uvicorn access log is OFF (bd polyglot-pdf-6rj0j, sprint 23 B0)

uvicorn's per-request access line -- the full request target at INFO -- is
not emitted anywhere this app runs: the deployed image's CMD passes
`--no-access-log`, and `configure_logging()` lists `uvicorn.access` among
the WARNING-capped library loggers for a uvicorn started without the flag
(the local launchers). The reason was `/ws/fill`'s `?token=` credential (it rides the first
frame since sprint 23 C2; `?token=` is honoured one more deploy)
(see [hipaa-pii-policy.md](hipaa-pii-policy.md)); the cost is that the app
stream carries no per-connection line, so per-request status and latency
come from Cloud Run's `run.googleapis.com/requests` log instead. The two
guards are pinned separately by `tests/test_dockerfile_app_module.py` and
`tests/test_logging_access_log.py`.

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
| 5 — BigQuery integration | Cloud Logging → BQ sink + cost/income views | **done** (bd `polyglot-pdf-rd3s8`; older placeholder bd `polyglot-pdf-0bs` describes a superseded design and should be closed as duplicate) |
| 6 — Compliance + audit | separate dataset, IP hashing, zero-PII validation | `polyglot-pdf-yqg` |
