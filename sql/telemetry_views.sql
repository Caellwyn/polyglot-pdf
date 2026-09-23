-- sql/telemetry_views.sql -- Epic 3 bead 6 (E3.6), plan:
-- docs/sprint_22_admin-console_plan.md "BigQuery".
--
-- Applied by scripts/setup-telemetry.sh via `bq query`, NOT run by any
-- deploy script. An operator runs the setup script by hand, under their own
-- gcloud credentials, after the Cloud Logging sink (also declared by that
-- script) has had time to land at least one row of each event kind.
--
-- CREATING A VIEW DOES require its referenced table(s) to already exist
-- (bd polyglot-pdf-k5w16, corrected 2026-09-17: an earlier version of this
-- comment claimed the opposite). "BigQuery views are late-bound" is true
-- only for a table a view's DEFINING QUERY references by name where that
-- table does not exist YET at query-time re-resolution -- it does NOT mean
-- `CREATE VIEW` itself tolerates a nonexistent table at creation time. Live
-- confirmation, same date: applying this file's income_month view before the
-- sink had written a stderr-stream row failed with "404 Not found: Table
-- ...run_googleapis_com_stderr" -- a hard CREATE-time error, not a
-- successfully created view that merely returned zero rows. This is exactly
-- why scripts/setup-telemetry.sh discovers BOTH sink destination tables with
-- `bq ls` before applying any view, and now applies each view whose source
-- table already exists while reporting the rest as pending (rather than
-- letting `set -e` abort the whole apply step on the first missing table).
--
-- WHERE THE COLUMNS COME FROM. Two different log shapes feed this dataset,
-- and every view below is written against the shape its source event
-- ACTUALLY has (verified against the real emitted JSON, not the plan prose):
--
--   1. Usage events (gemini_api_response, text_ai_usage, tts_usage), emitted
--      by backend/utils/structured_logger.py's StructuredLogger._emit(...).
--      These land as a NESTED jsonPayload: the envelope is one level down,
--      under `message`, and every context/cost/count field (firm_id,
--      employee_id, kit_id, channel, model, usage_kind, cost_estimate_usd,
--      ...) is nested ANOTHER level down inside `message.metadata`. So a
--      usage row's cost is at JSON path `$.message.metadata.cost_estimate_usd`,
--      not `$.cost_estimate_usd`.
--   2. ledger_export, emitted by backend/services/credit_ledger.py through
--      plain structlog (`_log.info(LEDGER_EXPORT_EVENT, event_type=...,
--      ...)`). structlog's JSONRenderer (backend/utils/logging.py) puts
--      every bound key at the TOP LEVEL of the JSON line, so a ledger row's
--      firm is at JSON path `$.firm_id`, not nested under any `message` or
--      `metadata` object. This is a genuinely different shape from (1), not
--      a typo -- backend/tests/unit/test_telemetry_views.py pins both shapes
--      by deriving the expected column set from log_schemas.USAGE_CONTEXT_KEYS
--      (nested form) and credit_ledger.LEDGER_EXPORT_FIELDS (flat form)
--      rather than hand-listing them here, so this file and those constants
--      cannot silently drift apart.
--
-- ACCESSOR SHAPE: JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.path'), NOT
-- STRUCT DOT-ACCESS (bd polyglot-pdf-0fus0, supersedes bd polyglot-pdf-vqgkj's
-- direct-field-access fix). A Cloud Logging -> BigQuery sink materializes
-- `jsonPayload` as a RECORD (STRUCT) column, but it INFERS that STRUCT's
-- sub-fields from the rows it has actually received, and SKIPS any field
-- whose value was null in every row seen so far -- this is documented sink
-- schema-auto-detection behavior, and vqgkj's own dot-access fix (2026-09-09)
-- was written and merged before either sink table existed anywhere to check
-- it against. LIVE 2026-09-23, with both sink tables finally populated:
-- creating income_month failed with "400 Field name channel does not exist
-- in STRUCT<firm_id STRING, timestamp STRING, level STRING, ...> at
-- [13:15]" -- the stderr table's very first row (a subscription_grant
-- top-up written by the admin service, which serves both channels and so
-- writes channel=None/null by design) never gave the sink a non-null
-- `channel` value to infer a column from, so `jsonPayload.channel` does not
-- exist as a struct field AT ALL and any view referencing it directly
-- cannot be CREATEd -- a hard schema error, not the silently-empty-column
-- failure mode vqgkj's comment (correctly) warned JSON_VALUE-on-a-STRING
-- would cause. Every nullable field has this same trap waiting (usd_amount
-- is null on debits/refunds/promo; link_jti null on grants; kit_id null on
-- TTS usage; employee_id null on staff sessions) -- whichever field happens
-- to be null across every row landed so far blocks the view, and the
-- failure is ORDER-DEPENDENT: a later row can add the column silently, so
-- this recurs on any fresh dataset without warning.
--
-- The fix: `TO_JSON_STRING(jsonPayload)` first serializes the CURRENT
-- STRUCT (whatever sub-fields it happens to have inferred so far) back to a
-- JSON string -- this always succeeds regardless of which fields exist,
-- because it walks the struct's actual schema rather than assuming one.
-- `JSON_VALUE(that_string, '$.path')` then extracts the path if present and
-- returns NULL (not an error) if it is absent, which is exactly the
-- resilience this bead needs: a view that references a field skipped by
-- inference now returns NULL for it instead of failing to CREATE at all.
-- This is a different call shape from what vqgkj's comment warned against:
-- that comment considered JSON_VALUE applied DIRECTLY to the STRUCT column
-- (a type error) or to an already-extracted STRING sub-field (re-parses the
-- string's contents as JSON, wrongly) -- neither is what happens here.
-- `TO_JSON_STRING(jsonPayload)` re-serializes the whole top-level STRUCT
-- into ONE valid JSON document every time (struct-to-JSON conversion, not a
-- parse of a value that might not itself be JSON), and `JSON_VALUE` then
-- parses that guaranteed-valid document, not a bare scalar like the string
-- `live`. This is the same accessor shape the ad-hoc verification queries
-- written during this epic already use successfully against both live
-- tables. Numeric sub-fields (`cost_estimate_usd`, `usd_amount`, `amount`)
-- come back out of JSON_VALUE as STRING regardless of the sink's original
-- inferred type, so those are read with SAFE_CAST to FLOAT64 (not just to
-- normalize an INT64 source, as under dot-access, but because JSON_VALUE
-- itself never returns a typed number). String sub-fields (firm_id,
-- channel, usage_kind, ...) are used as JSON_VALUE returns them, no cast
-- needed. hosting_cost_by_service_month is UNCHANGED by this bead -- it
-- reads the Cloud Billing export table, a normal (non-sink-inferred) BigQuery
-- table with a fixed schema Google publishes, so `service.description` /
-- `resource.name` direct field access there was never the bug this bead
-- fixes and stays exactly as it was.
--
-- THE SINK LANDS ROWS IN TWO TABLES, NOT ONE (bd polyglot-pdf-ih428). A
-- Cloud Logging -> BigQuery sink names its destination table per LOG ID
-- (with --use-partitioned-tables, one partitioned table per log ID) -- NOT
-- per resource type or event_type -- and this dataset's sink filter matches
-- TWO different Cloud Run log streams:
--
--   - Usage events (gemini_api_response / text_ai_usage / tts_usage) are
--     printed directly to STDOUT by
--     backend/utils/structured_logger.py:118
--     (`print(json.dumps(log_entry), file=sys.stdout, flush=True)`),
--     landing under Cloud Run's `run.googleapis.com/stdout` log and
--     therefore the sink's run_googleapis_com_stdout table.
--   - ledger_export (backend/services/credit_ledger.py) and the two
--     session events form_session_started / form_session_ended
--     (backend/utils/confirmation_logger.py) go through plain structlog
--     calls, which reach stdlib logging's root StreamHandler --
--     backend/utils/logging.py's configure_logging() calls
--     `logging.basicConfig(level=..., format="%(message)s")` with NO
--     `stream=` argument, so that handler defaults to Python's stdlib
--     default of STDERR. These land under `run.googleapis.com/stderr` and
--     therefore the sink's run_googleapis_com_stderr table.
--
-- So the three cost views below (which filter on the NESTED
-- $.message.event_type JSON path, i.e. usage events) read
-- `${TELEMETRY_TABLE_STDOUT}`, and income_month (which filters on the flat
-- $.event_type = 'ledger_export' shape) reads
-- `${TELEMETRY_TABLE_STDERR}` -- substituting the same single table into
-- both would leave one set of views permanently and silently empty (no
-- BigQuery error; the JSON path simply never matches). setup-telemetry.sh
-- discovers both table names with `bq ls` on the dataset (there is no
-- `gcloud logging sinks describe` call involved -- that command reports the
-- sink's config, not its destination tables) and substitutes each
-- placeholder independently. See that script for the substitution
-- mechanics.
--
-- `${BILLING_EXPORT_TABLE}` is substituted with the detailed Cloud Billing
-- export table (`` `BILLING_PROJECT.BILLING_DATASET.gcp_billing_export_resource_v1_XXXXXX` ``).
-- That export is a MAINTAINER console step (plan: Epic 3 bead 7, NOT this
-- bead) and is not retroactive, so hosting_cost_by_service_month returns no
-- rows until it is enabled -- the view definition itself does not depend on
-- that having happened yet.

-- ---------------------------------------------------------------------------
-- cost_by_firm_month -- every paid call's cost, grouped by paying firm.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW `${DATASET}.cost_by_firm_month` AS
SELECT
  FORMAT_TIMESTAMP('%Y-%m', timestamp) AS month,
  JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.metadata.firm_id') AS firm_id,
  JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.metadata.channel') AS channel,
  JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.metadata.usage_kind') AS usage_kind,
  COUNT(*) AS call_count,
  SUM(SAFE_CAST(JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.metadata.cost_estimate_usd') AS FLOAT64)) AS cost_usd
FROM `${TELEMETRY_TABLE_STDOUT}`
WHERE JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.event_type') IN (
  'gemini_api_response', 'text_ai_usage', 'tts_usage'
)
GROUP BY month, firm_id, channel, usage_kind;

-- ---------------------------------------------------------------------------
-- cost_by_kit_month -- every paid call's cost, grouped by form kit.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW `${DATASET}.cost_by_kit_month` AS
SELECT
  FORMAT_TIMESTAMP('%Y-%m', timestamp) AS month,
  JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.metadata.kit_id') AS kit_id,
  JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.metadata.channel') AS channel,
  JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.metadata.usage_kind') AS usage_kind,
  COUNT(*) AS call_count,
  SUM(SAFE_CAST(JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.metadata.cost_estimate_usd') AS FLOAT64)) AS cost_usd
FROM `${TELEMETRY_TABLE_STDOUT}`
WHERE JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.event_type') IN (
  'gemini_api_response', 'text_ai_usage', 'tts_usage'
)
GROUP BY month, kit_id, channel, usage_kind;

-- ---------------------------------------------------------------------------
-- cost_by_employee_month -- every paid call's cost, grouped by the firm
-- employee whose link the call ran under (null for staff / no-link calls).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW `${DATASET}.cost_by_employee_month` AS
SELECT
  FORMAT_TIMESTAMP('%Y-%m', timestamp) AS month,
  JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.metadata.employee_id') AS employee_id,
  JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.metadata.firm_id') AS firm_id,
  JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.metadata.channel') AS channel,
  JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.metadata.usage_kind') AS usage_kind,
  COUNT(*) AS call_count,
  SUM(SAFE_CAST(JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.metadata.cost_estimate_usd') AS FLOAT64)) AS cost_usd
FROM `${TELEMETRY_TABLE_STDOUT}`
WHERE JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.event_type') IN (
  'gemini_api_response', 'text_ai_usage', 'tts_usage'
)
GROUP BY month, employee_id, firm_id, channel, usage_kind;

-- ---------------------------------------------------------------------------
-- hosting_cost_by_service_month -- Cloud Run + Firebase Hosting spend, split
-- by service name so staging hosting cost never mixes with demo. Reads the
-- Cloud Billing detailed export table (Epic 3 bead 7, maintainer console
-- step, NOT this bead), filtered to the two SKU families this app actually
-- pays for. Returns zero rows until that export is enabled -- it is not
-- retroactive. UNCHANGED by bd polyglot-pdf-0fus0: this is a normal,
-- Google-published, fixed-schema BigQuery table, not a sink-inferred one,
-- so the schema-independence problem this bead fixes does not apply here --
-- direct struct field access is correct and stays as-is.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW `${DATASET}.hosting_cost_by_service_month` AS
SELECT
  FORMAT_TIMESTAMP('%Y-%m', usage_start_time) AS month,
  service.description AS gcp_service,
  -- resource.name carries the Cloud Run SERVICE NAME (polyglot-backend vs
  -- polyglot-backend-staging) for Cloud Run line items; Firebase Hosting
  -- line items have no per-site resource name in the export, so those rows
  -- group under NULL rather than being misattributed to one channel -- see
  -- the plan's "staging hosting never mixes with demo" requirement, which
  -- this column split is what actually enforces for Cloud Run (Hosting cost
  -- is comparatively small and shared across channels by construction: one
  -- Firebase Hosting site per Firebase project, not per channel).
  resource.name AS resource_name,
  SUM(cost) AS cost_usd
FROM `${BILLING_EXPORT_TABLE}`
WHERE service.description IN ('Cloud Run', 'Firebase Hosting')
GROUP BY month, gcp_service, resource_name;

-- ---------------------------------------------------------------------------
-- income_month -- REAL income only. firm_kind = 'live' is HARD-CODED here,
-- not left to callers: income cannot filter on channel (the admin service
-- that writes purchase/subscription_grant entries has none), and the
-- snapshotted firm_kind on each ledger_export line is the ONLY test-vs-real
-- line available. A caller who forgets a WHERE clause on this view still
-- gets real-money-only numbers.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW `${DATASET}.income_month` AS
SELECT
  FORMAT_TIMESTAMP('%Y-%m', timestamp) AS month,
  JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.type') AS entry_type,
  JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.channel') AS channel,
  COUNT(*) AS entry_count,
  SUM(SAFE_CAST(JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.usd_amount') AS FLOAT64)) AS usd_amount
FROM `${TELEMETRY_TABLE_STDERR}`
WHERE JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.event_type') = 'ledger_export'
  AND JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.type') IN ('purchase', 'subscription_grant')
  AND JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.firm_kind') = 'live'
GROUP BY month, entry_type, channel;
