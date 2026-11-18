# Deployed telemetry: gemini-3.8-live vs gemini-live-2.5-flash-native-audio

bd `polyglot-pdf-o40eo` · pulled 2026-11-17 · READ-ONLY, zero model spend.
Script: [`3p8_deployed_telemetry.py`](3p8_deployed_telemetry.py) · raw aggregates
(no PII): [`data/3p8_deployed_telemetry_aggregates.json`](data/3p8_deployed_telemetry_aggregates.json).

## Bottom line (read this first)

**3.8 has barely run deployed. n = ONE form session, on staging, never on demo.**
There is not enough deployed data to quote 3.8 cost or latency as a product
figure. What the logs do show is below. Treat it as one test drive, not a
sample.

- **Demo has never served 3.8.** `polyglot-backend` (demo) was last deployed
  **2026-09-23** (revision `polyglot-backend-00099-kn5`). Its only session in
  the log window (2026-11-04) logged `model=gemini-live-2.5-flash-native-audio`.
  The investor-facing demo is still on 2.5.
- **Staging ran 3.8 exactly once**, on 2026-10-22 at 04:46Z. That was
  8 minutes after the staging deploy (`polyglot-backend-staging-00015-dw9`,
  updated 04:38Z), so it was the post-deploy test drive. It was 1 form session
  with 7 model turns and 3 tool calls, and the main WebSocket lasted 61 s.
- **No deployed 2.5 latency baseline survives.** Cloud Logging keeps 30 days
  (`_Default` bucket, `retentionDays: 30`), so every `timing_*` line before
  2026-10-18 is gone. The BigQuery sink keeps usage and `ws_error` rows only,
  not `timing_*`. In the window, the only 2.5 session (demo, 2026-11-04) had
  no tool calls, so it gives no tool latency either.
- **None of the forum failure modes is visible, but n is too small to rule
  anything out:**
  - 0 turns with a transcript but no audio;
  - 0 drops with codes 1011 or 1006 (deployed logs, plus the
    `ws_close_1011_count` metric over 120 days);
  - 0 GoAway messages;
  - nothing close to 15 minutes (longest 3.8 WebSocket: 61 s).
- **One lead to follow up:** the 3.8 session's first (intro) adapter instance
  ended with an unintentional Gemini close, **code 1007**. It came 9 ms after
  an `activity_end` and 5 ms after the client's WebSocket had already closed,
  so it had no user impact. The 2.5 demo session has the same intro-instance
  shape and logged no close. n = 1. See "Reliability".
- **Billing reconciles with telemetry:** telemetry is +3.1% over the bill for
  3.8 and matches exactly for 2.5.
  For 3.8, though, the billed **text output** (137 tokens) roughly matches
  logged text output *minus thoughts* (119). The 1,022 logged thought tokens
  do not show up as a separate billing line that day. See "Cost".

## Method

Project `polyglot-demo-aa709`. Staging and demo share it, so the channel is
the Cloud Run service name:

- `polyglot-backend-staging` = staging;
- `polyglot-backend` = demo.

All calls ran **in-process** from `backend/.venv` Python: google-auth
`AuthorizedSession` against the Logging, Monitoring and Cloud Run v2 REST
APIs, and `google-cloud-bigquery` for BQ. No `gcloud` or `bq` subprocess.
`google-cloud-logging` is not installed in the venv, so the Logging REST API
`entries:list` is called directly.

**Model attribution uses the logged `model` field on each line, never the
date.** Two event types carry no `model` field: `timing_coordinator_roundtrip`
and `form_session_*`. Those take the model of the nearest model-tagged line on
the same service within 10 minutes (`model_attributed` in the script).

The JSON block `model_attribution` makes this checkable:

- 96 rows carry a logged model;
- 8 rows are attributed by proximity;
- **0 rows are unattributed.**

There is one **date-vs-model mismatch, and it is real, not a logging
fault:** the 2026-11-04 demo session ran **2.5 after the 10-21 cutover**
(33 rows). Demo was last deployed on 2026-09-23 and has never been
redeployed. The only 3.8 rows are staging rows on 10-22. No 3.8 row
predates the cutover.

**PII:** the script keeps only numbers, booleans and fixed tokens: event
names, tool names, close codes, model ids and `request_type`. Firm, kit and
form ids, link ids, `error_message` and every free-text field are never
selected. Instance and form-session ids become ordinal labels (`inst0`,
`fsess0`). The BQ form-session grouping key is an MD5 used only in memory.

Sources:

| # | Source | Window | What it gives |
|---|--------|--------|---------------|
| A | Cloud Logging `jsonPayload` (both services) | 2026-10-18 .. 2026-11-17 (30-day retention) | every per-turn / timing / close event |
| B | Cloud Monitoring log-based metrics `ws_close_1011_count`, `ws_close_1013_count` | 120 days | Gemini-side drop count beyond log retention |
| C | BQ `polyglot_telemetry.run_googleapis_com_stdout` (telemetry sink) | sink start (2026-09-15) .. now | per-turn `gemini_api_response` usage + `ws_error` codes -- the only surviving pre-cutover 2.5 deployed data |
| D | BQ Cloud Billing export `polyglot_billing.gcp_billing_export_resource_v1_*` | 2026-09-01 .. now | actual billed Gemini Live tokens/$ per SKU per day (PROJECT-wide: includes local-harness runs) |

### Query text

Cloud Logging. Every filter is prefixed with
`resource.type="cloud_run_revision" AND (resource.labels.service_name="polyglot-backend" OR resource.labels.service_name="polyglot-backend-staging") AND timestamp>="2026-10-18T00:00:00Z" AND (...)`:

```
-- model-tagged + session/timing events
jsonPayload.model:* OR jsonPayload.event=("timing_coordinator_roundtrip"
  OR "form_session_started" OR "form_session_ended"
  OR "gemini_go_away_received" OR "timing_section_switch_total")
  OR jsonPayload.message.event_type="ws_error"

-- WebSocket connection durations (Cloud Run request log; latency = WS lifetime)
logName:"run.googleapis.com%2Frequests" AND httpRequest.requestUrl:"/ws/"
```

Cloud Monitoring: `timeSeries.list` on
`metric.type="logging.googleapis.com/user/ws_close_1011_count"` (and the
`_1013_`) over 120 days, `ALIGN_SUM`, 86400 s.

BigQuery (`{table}` = the sink stdout table / the billing export table):

```sql
-- C1: per-turn live_voice usage
SELECT resource.labels.service_name AS svc,
  JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.metadata.model') AS model,
  DATE(timestamp) AS d,
  TO_HEX(MD5(JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.form_session_id'))) AS fsess_hash,
  SAFE_CAST(JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.metadata.cost_estimate_usd') AS FLOAT64) AS cost,
  SAFE_CAST(JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.metadata.text_input') AS INT64) AS text_in,
  SAFE_CAST(JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.metadata.audio_input') AS INT64) AS audio_in,
  SAFE_CAST(JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.metadata.text_output') AS INT64) AS text_out,
  SAFE_CAST(JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.metadata.audio_output') AS INT64) AS audio_out
FROM `{table}`
WHERE JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.event_type') = 'gemini_api_response'
  AND JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.metadata.usage_kind') = 'live_voice';

-- C2: ws_error close codes (fixed reason tokens only)
SELECT resource.labels.service_name AS svc, DATE(timestamp) AS d,
  JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.metadata.close_code') AS close_code,
  JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.metadata.reason_token') AS reason_token,
  COUNT(*) AS n
FROM `{table}`
WHERE JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.event_type') = 'ws_error'
GROUP BY 1, 2, 3, 4;

-- D: billed Gemini Live SKUs
SELECT DATE(usage_start_time) AS d, sku.description AS sku,
  SUM(cost) AS cost_usd, SUM(usage.amount) AS amount
FROM `{table}`
WHERE usage_start_time >= TIMESTAMP('2026-09-01')
  AND LOWER(sku.description) LIKE '%gemini%live%'
GROUP BY 1, 2;
```

## Inventory: every deployed Live session in reach

| Channel | Model (logged) | Date | Form sessions | Adapter instances | WS lifetimes | Source |
|---------|----------------|------|---------------|-------------------|--------------|--------|
| staging | `gemini-3.8-live` | 2026-10-22 | **1** | 2 | 6.2 s, 61.0 s | A, C, D |
| demo | `gemini-live-2.5-flash-native-audio` | 2026-11-04 | **1** | 2 | 6.7 s, 10.1 s | A, C, D |
| staging | `gemini-live-2.5-flash-native-audio` | 2026-09-15..09-23 | 6 | -- (logs expired) | -- | C, D only |

Every form session in both models runs **2 adapter instances**: a short
intro WebSocket of about 6 s, then the main one. The 2.5 and 3.8 sessions
share this shape, so it is the app's own flow, not a model-driven reconnect.
No session had a `connect_ready` attempt greater than 1.

## Cost

### 3.8 (staging, 1 form session)

| | Intro instance | Main instance | **Form session** |
|---|---|---|---|
| Telemetry `total_cost_usd` | $0.0056 | $0.0752 | **$0.0808** |
| Text input tokens | 5,360 | 61,025 | 66,385 |
| Audio input tokens | 0 | 4,551 | 4,551 |
| Text output tokens (incl. thoughts) | 91 | 1,050 | 1,141 |
| of which thoughts | 91 | 931 | 1,022 |
| Audio output tokens | 100 | 921 | 1,021 |
| Model turns with usage | 1 | 6 | 7 |

Cost split for the form session, at the
[`backend/config.py`](../../backend/config.py) 3.8 rates (0.75 / 3.00 / 4.50 /
12.00 per 1M):

| Modality | Cost | Share |
|---|---|---|
| Text input | $0.0498 | 62% |
| Audio input | $0.0137 | 17% |
| Audio output | $0.0123 | 15% |
| Text output + thoughts | $0.0051 | 6% |

Per turn (n = 7):

| Metric | p50 | p90 |
|---|---|---|
| Turn cost | $0.0116 | $0.0213 |
| Text-in tokens | 7,640 | 15,567 |
| Audio-in tokens | 545 | 2,264 |
| Thoughts | 109 | 257 |
| Audio-out tokens | 124 | 311 |

Every 3.8 turn reported `thoughts_tokens` > 0, between 91 and 257.

### 2.5

- **Demo, 2026-11-04, 1 form session:** $0.0101 in 2 turns. The tokens were
  8,152 text-in and 503 audio-out, with no audio-in and no text-out. The
  user pressed to talk once, over the greeting, and the session ended. There
  were no tool calls.
- **Staging, pre-cutover (BQ sink, 2026-09-15..09-23): 6 form sessions,
  162 usage rows.**
  - Cost per form session: $0.0047, $0.0070, $0.0079, $0.0158, $0.0201 and
    $1.2784. The last is a single 151-turn session on 2026-09-18.
  - Per-turn cost: p50 $0.0087, p90 $0.0111.
  - Per-turn tokens:
    - text-in: p50 6,330, p90 7,106;
    - audio-in: p50 1,678, p90 2,294;
    - text-out: p50 2, p90 26;
    - audio-out: p50 23, p90 131.
  - These predate the 3.8 system-instruction and kit state. Per-turn figures
    are not like-for-like with the 3.8 session.

### Billing reconciliation (source D)

| Day (UTC) | Deployed sessions that day | Billed Gemini Live $ | Telemetry $ | Delta |
|---|---|---|---|---|
| 2026-11-04 | demo 2.5 x1 | $0.010112 | $0.010112 | **0.0%**: tokens match exactly (8,152 text-in, 503 audio-out) |
| 2026-09-18 | staging 2.5 x1 (151 turns) | $1.278439 | $1.278441 | 0.0% |
| 2026-10-22 | staging 3.8 x1 | $0.078410 | $0.080828 | telemetry **+3.1%** |
| 2026-10-21 | none deployed | $0.095597 | -- | 3.8 traffic that day is local-harness / probe work, not deployed |

Token-level detail for **2026-10-22**, the 3.8 day:

| Modality | Billed | Logged |
|---|---|---|
| Text in | 66,403 | 66,385 |
| Audio in | 4,551 | 4,551 (exact) |
| Audio out | 1,195 | 1,021 (+174 billed) |
| Text out | **137** | 1,141 incl. thoughts; **119 excl. thoughts** |

Unit prices implied by billing are exactly the `backend/config.py` table:

- 3.8: 0.75 / 3.00 / 4.50 / 12.00 per 1M;
- 2.5: 0.50 / 3.00 / 2.00 / 12.00 per 1M.

What this means:

- The telemetry `total_cost_usd` is a **trustworthy proxy for the bill**. It
  matched to the cent on both 2.5 days and was +3.1% over the bill on the 3.8
  day.
- **On the one 3.8 day, Vertex did not bill the 1,022 thought tokens as text
  output.** The adapter counts thoughts into text output
  (`text_output_tokens += thoughts_tokens`, `live_ai_gemini.py`), and the
  pricing comment says "Output rates include thinking tokens". That accounts
  for about +$0.0046 of telemetry over-estimate.
- The +174 billed audio-out tokens (about $0.0021) partly offset it. They
  plausibly come from a final or interrupted generation whose usage frame
  never arrived before close.
- One day, one session: **do not change pricing on this.** A second
  reconciliation is needed first, on a day with only known 3.8 traffic.

## Latency

All 3.8 values below come from **one staging session with one tester**.
These numbers are a description of that session, not a distribution.

| Metric (ms) | 3.8 n | 3.8 p50 | 3.8 p90 | 3.8 values | 2.5 (deployed, in window) |
|---|---|---|---|---|---|
| `timing_tool_call_received.since_activity_end_ms` | 3 | 512 | 587 | 458, 512, 587 (2x `update_form_fields`, 1x `confirm_field`) | n = 0 (no tool calls) |
| `timing_coordinator_roundtrip.roundtrip_ms` | 2 | 98 | 105 | 98 (`next_field`), 105 (`confirm_field`) | n = 0 |
| `timing_session_connect_ready.connect_to_ready_ms` | 2 | 100 | 173 | 100, 173 | n = 2: 123, 188 |
| text turn sent -> first Gemini audio chunk (derived from log timestamps) | 2 | 531 | 796 | 531, 796 | n = 2: 600, 605 |
| `activity_end` -> first Gemini audio chunk (derived) | 1 | 957 | 957 | 957 | n = 0 |
| `activity_end` -> turn usage frame (derived; includes the whole spoken reply, so not a latency) | 4 | 5,336 | 12,844 | 4,628 .. 12,844 | n = 0 |

**On first-audio latency:** `_timing_first_inbound_audio` is not a logged
latency. It is the adapter's internal fallback reference for
`since_activity_end_ms` (`live_ai_gemini.py`, used when there is no
`activity_end`). In this push-to-talk session every tool call had a real
`activity_end` reference.

The only first-audio signal in the logs is the
`[audio] [Gemini Audio] First audio chunk received` line. It fires only
sometimes: once per counter reset, not once per turn. That is why the derived
`activity_end -> first audio` value has n = 1.

## Reliability

| | 3.8 staging (1 session) | 2.5 demo (1 session) | 2.5 staging pre-cutover (sink) |
|---|---|---|---|
| 1011 / 1006 Gemini drops | 0 | 0 | 0 |
| `ws_close_1011_count` metric, 120 days, all channels | 0 | (same metric) | (same metric) |
| Other Gemini-side closes | **1x 1007, `intentional_shutdown=false`** | 0 | -- |
| Route `ws_error` closes | 0 | 0 | 5x 1008 on 2026-09-17 (3 `auth_failed`, 1 `origin_refused`, 1 `auth_timeout`): auth refusals, not model |
| `gemini_go_away_received` | 0 | 0 | -- |
| Connect attempts > 1 | 0 | 0 | -- |
| Barge-in interrupts | 2 | 1 | -- |

**The 1007 on 3.8.** This is the intro instance (`inst0`). Sequence, in UTC:

1. 04:46:43.528: `activity_start`. Gemini is interrupted mid-greeting after
   24 audio chunks.
2. 04:46:43.649: `activity_end`, 121 ms later. No mic audio was sent between
   the two.
3. 04:46:43.653: `form_session_ended`. The client WebSocket closes.
4. 04:46:43.658: `gemini_session_connection_closed close_code=1007`.

The 2.5 demo session has the identical intro shape: an empty bracket of
127 ms, then teardown. It logged no close.

- Plausible reading: 3.8 rejects either the empty `activity_start` /
  `activity_end` bracket or the trailing `activity_end` during teardown.
  It does so with 1007 ("invalid argument"), where 2.5 tolerates it.
- No user impact here, because the client had already moved on.
- 1007 is not in the counted spontaneous-drop set, so it never reaches
  `ws_close_1011_count`.
- n = 1. **Filed as a lead, not a finding** (bd `polyglot-pdf-qv3jp`).

**15-minute cap:** untestable from deployed data. The longest 3.8 WebSocket
was 61 s.

## Silent-audio turns

- **Output transcription is OFF on the production path,** so a "transcript
  present, audio empty" turn cannot be observed in deployed logs at all. The
  `event_shape` probe that would record it is `DEV_LOGGING_ENABLED`-gated.
- Proxies used instead:
  - **Usage turns with `audio_output_tokens == 0`:** 3.8 had **0 of 7**.
    2.5 demo had 0 of 2.
  - **`activity_end` with no usage frame before the next press or close:**
    3.8 had 2. Both are explained, and neither is silence.
    - One is the 1007 intro teardown above.
    - The other is a `confirm_field` turn. Its tool call arrived 458 ms after
      `activity_end`. The user barged in 5.8 s after that `activity_end`,
      after 86 audio chunks of reply. The usage frame arrived 50 ms after
      that next press.
- The 2.5 staging sink has **80 of 162** usage rows with zero audio output.
  That is **not** silence evidence. On 2.5, a usage frame lands per
  generation segment, including segments that are only a tool call. The
  matching timing logs have expired, so no individual turn can be checked.
- A turn with no `turn_complete` is not directly logged on the production
  path either. The usage frame is the closest durable marker.

## Caveats

1. **n.** 3.8 deployed means 1 form session, 7 turns and 3 tool calls,
   staging only, from one post-deploy test drive. No p90 here is a real p90.
2. **No 2.5 deployed latency baseline exists** after the 30-day log
   retention. The BQ sink does not carry `timing_*` events, and the only
   in-window 2.5 session had no tool calls.
3. **Billing is project-wide.** It cleanly isolates deployed traffic only on
   days with no local-harness Live runs: 09-18, 10-22 and 11-04 qualify;
   10-21 does not.
4. **The 2.5 staging sink sessions** (September) ran an older system
   instruction and kit state. Per-turn token counts are not like-for-like
   with the 3.8 session.
5. **WebSocket lifetimes come from the Cloud Run request log** (`latency` on
   the `/ws/fill` 101), measured end to end from the client's connection.

## Follow-ups

- **Get real deployed n for 3.8:** deploy to the demo channel, which needs a
  per-instance ask. Until then, deployed 3.8 latency for the pitch should be
  described as "one staging test drive", or not quoted.
- **Keep timing telemetry past 30 days:** extend the telemetry sink, or a
  log bucket's retention, to cover the `timing_*` /
  `gemini_session_connection_closed` events. Filed as bd `polyglot-pdf-beeoh`.
- **3.8 1007 on the intro-instance teardown:** reproduce locally (an empty
  activity bracket, then teardown). Filed as bd `polyglot-pdf-qv3jp`.
- **Thoughts billing:** re-run the reconciliation on another clean
  3.8-only day before touching the pricing table or the adapter's thoughts
  accounting. Tracked as bd `polyglot-pdf-1lks4`.
