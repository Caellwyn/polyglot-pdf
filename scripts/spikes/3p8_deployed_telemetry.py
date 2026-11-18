"""Deployed telemetry: gemini-3.8-live vs gemini-live-2.5-flash-native-audio.

bd polyglot-pdf-o40eo. READ-ONLY, zero model spend. Pulls aggregates from:

  A. Cloud Logging (structured jsonPayload, 30-day _Default retention) for the
     two Cloud Run backends: polyglot-backend (demo) and
     polyglot-backend-staging (staging). Model is read from each line's own
     `model` field, never inferred from the date.
  B. Cloud Monitoring: the ws_close_1011_count / ws_close_1013_count
     log-based metrics (longer retention than the log bucket).
  C. BigQuery telemetry sink (polyglot_telemetry.run_googleapis_com_stdout):
     per-turn gemini_api_response usage rows + ws_error close codes. This is
     the only place pre-cutover 2.5 per-turn cost survives past 30 days.
  D. BigQuery Cloud Billing export: Gemini Live SKU rows (project-wide, so it
     ALSO contains local-harness spend -- used only to reconcile a day where
     the deployed sessions are the only Live traffic).

PII: only numbers, booleans and fixed tokens (event names, tool names, close
codes, model ids) leave this script. Free-text fields, firm/kit/form ids,
link ids and error messages are never selected or written. Session and
instance ids are replaced with ordinal labels.

Calls the Google APIs in-process (google-auth AuthorizedSession for Logging /
Monitoring / Cloud Run REST; google-cloud-bigquery for BQ) -- never shells
out to gcloud/bq. Run from the backend venv:

    backend/.venv/Scripts/python.exe scripts/spikes/3p8_deployed_telemetry.py

Writes scripts/spikes/data/3p8_deployed_telemetry_aggregates.json.
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import math
import os
import sys
import time

import google.auth
from google.auth.transport.requests import AuthorizedSession
from google.cloud import bigquery

LOG_START = "2026-10-18T00:00:00Z"  # _Default bucket retention is 30 days
CUTOVER = "2026-10-21"
SERVICES = {"polyglot-backend": "demo", "polyglot-backend-staging": "staging"}
STDOUT_TABLE = "polyglot_telemetry.run_googleapis_com_stdout"
# The detailed billing-export table name embeds the Cloud Billing account id,
# which this public repo keeps out of git (same convention as
# scripts/setup-telemetry.sh's BILLING_EXPORT_TABLE argument). Taken from the
# env var if set, else discovered in-process from the dataset at run time.
BILLING_DATASET = "polyglot_billing"
BILLING_TABLE_PREFIX = "gcp_billing_export_resource_v1_"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data",
                   "3p8_deployed_telemetry_aggregates.json")

CREDS, PROJ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
SESSION = AuthorizedSession(CREDS)
SVC_CLAUSE = "(" + " OR ".join(
    'resource.labels.service_name="%s"' % s for s in SERVICES) + ")"

# Logging filters (copied verbatim into the findings doc).
FILTER_MODEL_EVENTS = (
    'jsonPayload.model:* OR jsonPayload.event=("timing_coordinator_roundtrip" '
    'OR "form_session_started" OR "form_session_ended" '
    'OR "gemini_go_away_received" OR "timing_section_switch_total") '
    'OR jsonPayload.message.event_type="ws_error"')
FILTER_WS_REQUESTS = 'logName:"run.googleapis.com%2Frequests" AND httpRequest.requestUrl:"/ws/"'

NUMERIC_KEYS = {
    "total_cost_usd", "total_tokens", "prompt_tokens", "text_input_tokens",
    "audio_input_tokens", "text_output_tokens", "audio_output_tokens",
    "thoughts_tokens", "response_tokens", "turn_cost_usd", "since_activity_end_ms",
    "roundtrip_ms", "connect_to_ready_ms", "attempt", "callback_ms", "close_code",
    "intentional_shutdown", "audio_frames_dropped", "pre_ready_dropped",
    "event_count", "bytes", "chunk_number", "elapsed_since_audio_start_ms",
}
TOKEN_KEYS = {"event", "model", "tool", "request_type", "time_left", "path"}


def log_entries(flt, start=LOG_START):
    body = {
        "resourceNames": ["projects/%s" % PROJ],
        "filter": 'resource.type="cloud_run_revision" AND %s AND timestamp>="%s" AND (%s)'
                  % (SVC_CLAUSE, start, flt),
        "orderBy": "timestamp asc",
        "pageSize": 1000,
    }
    while True:
        for attempt in range(5):
            r = SESSION.post("https://logging.googleapis.com/v2/entries:list", json=body)
            if r.status_code == 429:
                time.sleep(20 * (attempt + 1))
                continue
            break
        r.raise_for_status()
        d = r.json()
        for e in d.get("entries", []):
            yield e
        tok = d.get("nextPageToken")
        if not tok:
            return
        body["pageToken"] = tok
        time.sleep(1.1)  # stay under the 60 read-requests/min quota


def pct(values, p):
    """Nearest-rank percentile; None on empty."""
    v = sorted(x for x in values if x is not None)
    if not v:
        return None
    k = max(1, int(math.ceil(p / 100.0 * len(v))))
    return v[k - 1]


def summary(values):
    v = [x for x in values if x is not None]
    return {"n": len(v), "p50": pct(v, 50), "p90": pct(v, 90),
            "min": min(v) if v else None, "max": max(v) if v else None,
            "values": sorted(v) if len(v) <= 20 else None}


def ts(e):
    return dt.datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00"))


# ---------------------------------------------------------------- A. logging
def pull_logging():
    labels = {}

    def label(kind, raw):
        return labels.setdefault((kind, raw), "%s%d" % (kind, sum(1 for k in labels if k[0] == kind)))

    rows = []
    for e in log_entries(FILTER_MODEL_EVENTS):
        j = e.get("jsonPayload", {}) or {}
        msg = j.get("message") if isinstance(j.get("message"), dict) else None
        row = {"t": ts(e), "svc": e["resource"]["labels"]["service_name"],
               "severity": e.get("severity")}
        if msg is not None:  # StructuredLogger nested shape (ws_error)
            md = msg.get("metadata") or {}
            row.update(event=msg.get("event_type"), close_code=md.get("close_code"),
                       reason_token=md.get("reason_token"), model=md.get("model"))
        else:
            for k, v in j.items():
                if k in NUMERIC_KEYS and (isinstance(v, (int, float, bool)) or v is None):
                    row[k] = v
                elif k in TOKEN_KEYS and isinstance(v, str):
                    row[k] = v
            if "instance_id" in j:
                row["inst"] = label("inst", j["instance_id"])
            if "form_session_id" in j:
                row["fsess"] = label("fsess", j["form_session_id"])
        rows.append(row)

    # Attribute model-less rows (coordinator roundtrip, form_session_*) to the
    # model of the nearest model-tagged row on the same service within 10 min.
    tagged = [r for r in rows if r.get("model")]
    for r in rows:
        if r.get("model"):
            continue
        near = [t for t in tagged if t["svc"] == r["svc"]
                and abs((t["t"] - r["t"]).total_seconds()) < 600]
        if near:
            r["model"] = min(near, key=lambda t: abs((t["t"] - r["t"]).total_seconds()))["model"]
            r["model_attributed"] = True
        else:
            r["model_unattributed"] = True

    ws = []
    for e in log_entries(FILTER_WS_REQUESTS):
        h = e.get("httpRequest", {})
        lat = h.get("latency")
        ws.append({"t": ts(e), "svc": e["resource"]["labels"]["service_name"],
                   "status": h.get("status"),
                   "duration_s": float(lat.rstrip("s")) if lat else None})
    return rows, ws


def per_model(rows, ws):
    out = {}
    keys = sorted({(r["svc"], r.get("model")) for r in rows if r.get("model")})
    for svc, model in keys:
        R = [r for r in rows if r["svc"] == svc and r.get("model") == model]
        ev = lambda name: [r for r in R if r.get("event") == name]
        insts = sorted({r["inst"] for r in R if "inst" in r})
        csum = ev("session_cost_summary")
        usage = ev("token_usage")
        thoughts_by_inst = collections.Counter()
        for u in usage:
            thoughts_by_inst[u.get("inst")] += u.get("thoughts_tokens") or 0

        # Per-turn derived latencies, walked per adapter instance.
        ae_to_audio, ae_to_usage, send_to_audio = [], [], []
        unanswered_turns, silent_usage_turns = 0, 0
        for inst in insts:
            seq = sorted(({**r, "event": r.get("event") or ""} for r in R if r.get("inst") == inst),
                         key=lambda r: r["t"])
            for i, r in enumerate(seq):
                if r["event"] in ("timing_activity_end", "SEND_CLIENT_CONTENT",
                                  "SEND_CLIENT_CONTENT (from queue)"):
                    nxt_audio = nxt_usage = None
                    for s in seq[i + 1:]:
                        if s["event"] == "timing_activity_start":
                            break
                        if nxt_audio is None and s["event"].startswith("[audio] [Gemini Audio] First audio chunk"):
                            nxt_audio = s
                        if nxt_usage is None and s["event"] == "token_usage":
                            nxt_usage = s
                    if r["event"] == "timing_activity_end":
                        if nxt_audio:
                            ae_to_audio.append(round((nxt_audio["t"] - r["t"]).total_seconds() * 1000))
                        if nxt_usage:
                            ae_to_usage.append(round((nxt_usage["t"] - r["t"]).total_seconds() * 1000))
                        else:
                            # no usage (= no turn completion) before the next
                            # press or the end of the adapter instance
                            unanswered_turns += 1
                    elif nxt_audio:
                        send_to_audio.append(round((nxt_audio["t"] - r["t"]).total_seconds() * 1000))
            silent_usage_turns += sum(1 for u in usage if u.get("inst") == inst
                                      and (u.get("audio_output_tokens") or 0) == 0)

        closes = collections.Counter(
            (r.get("close_code"), r.get("intentional_shutdown")) for r in ev("gemini_session_connection_closed"))
        ws_err = collections.Counter((r.get("close_code"), r.get("reason_token")) for r in ev("ws_error"))
        ready = ev("timing_session_connect_ready")
        fs_started = ev("form_session_started")
        sess = []
        for c in csum:
            sess.append({
                "inst": c.get("inst"), "fsess": c.get("fsess"),
                "total_cost_usd": c.get("total_cost_usd"), "total_tokens": c.get("total_tokens"),
                "text_input_tokens": c.get("text_input_tokens"),
                "audio_input_tokens": c.get("audio_input_tokens"),
                "text_output_tokens_incl_thoughts": c.get("text_output_tokens"),
                "thoughts_tokens": thoughts_by_inst.get(c.get("inst"), 0),
                "audio_output_tokens": c.get("audio_output_tokens"),
                "turns_with_usage": sum(1 for u in usage if u.get("inst") == c.get("inst")),
            })
        fsess_cost = collections.defaultdict(float)
        for s in sess:
            fsess_cost[s["fsess"]] += s["total_cost_usd"] or 0
        days = sorted({r["t"].date().isoformat() for r in R})
        out["%s|%s" % (SERVICES[svc], model)] = {
            "service": svc, "channel": SERVICES[svc], "model": model, "days": days,
            "form_sessions_started": len(fs_started),
            "adapter_instances": len(insts),
            "ws_connections": [{"duration_s": w["duration_s"], "status": w["status"]} for w in ws
                               if w["svc"] == svc and w["t"].date().isoformat() in days],
            "cost_summary_rows": sess,
            "cost_per_adapter_instance_usd": summary([s["total_cost_usd"] for s in sess]),
            "cost_per_form_session_usd": summary(list(fsess_cost.values())),
            "per_turn": {
                "turn_cost_usd": summary([u.get("turn_cost_usd") for u in usage]),
                "text_input_tokens": summary([u.get("text_input_tokens") for u in usage]),
                "audio_input_tokens": summary([u.get("audio_input_tokens") for u in usage]),
                "text_output_tokens_incl_thoughts": summary([u.get("text_output_tokens") for u in usage]),
                "thoughts_tokens": summary([u.get("thoughts_tokens") for u in usage]),
                "audio_output_tokens": summary([u.get("audio_output_tokens") for u in usage]),
            },
            "latency_ms": {
                "tool_call_since_activity_end": summary([r.get("since_activity_end_ms") for r in ev("timing_tool_call_received")]),
                "tool_calls_by_tool": dict(collections.Counter(r.get("tool") for r in ev("timing_tool_call_received"))),
                "coordinator_roundtrip": summary([r.get("roundtrip_ms") for r in ev("timing_coordinator_roundtrip")]),
                "connect_to_ready": summary([r.get("connect_to_ready_ms") for r in ready]),
                "activity_end_to_first_audio_chunk_log": summary(ae_to_audio),
                "activity_end_to_turn_usage": summary(ae_to_usage),
                "text_turn_send_to_first_audio_chunk_log": summary(send_to_audio),
            },
            "reliability": {
                "gemini_session_connection_closed": [
                    {"close_code": k[0], "intentional_shutdown": k[1], "n": v} for k, v in closes.items()],
                "ws_error_rows": [{"close_code": k[0], "reason_token": k[1], "n": v} for k, v in ws_err.items()],
                "go_away_received": len(ev("gemini_go_away_received")),
                "connect_attempts_gt1": sum(1 for r in ready if (r.get("attempt") or 1) > 1),
                "adapter_instances_per_form_session": round(len(insts) / len(fs_started), 2) if fs_started else None,
                "interrupts": len(ev("[interrupt] GEMINI_INTERRUPTED")),
            },
            "silent_audio_evidence": {
                "usage_turns": len(usage),
                "usage_turns_with_zero_audio_output": silent_usage_turns,
                "activity_end_without_usage_before_next_press_or_close": unanswered_turns,
                "note": "output transcription is OFF on the production path, so a "
                        "transcript-without-audio turn cannot be observed directly; "
                        "zero audio_output_tokens on a usage row is the proxy.",
            },
        }
    return out


# ------------------------------------------------------------- B. monitoring
def pull_monitoring():
    end = dt.datetime(2026, 11, 17, tzinfo=dt.timezone.utc)
    start = end - dt.timedelta(days=120)
    res = {}
    for mt in ("ws_close_1011_count", "ws_close_1013_count"):
        params = {"filter": 'metric.type="logging.googleapis.com/user/%s"' % mt,
                  "interval.startTime": start.isoformat().replace("+00:00", "Z"),
                  "interval.endTime": end.isoformat().replace("+00:00", "Z"),
                  "aggregation.alignmentPeriod": "86400s",
                  "aggregation.perSeriesAligner": "ALIGN_SUM"}
        r = SESSION.get("https://monitoring.googleapis.com/v3/projects/%s/timeSeries" % PROJ, params=params)
        r.raise_for_status()
        total = 0
        for s in r.json().get("timeSeries", []):
            for p in s.get("points", []):
                total += float(list(p["value"].values())[0])
        res[mt] = {"window_days": 120, "total": total}
    return res


# --------------------------------------------------------------- C/D. bigquery
SQL_SINK_TURNS = """
SELECT
  resource.labels.service_name AS svc,
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
  AND JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.metadata.usage_kind') = 'live_voice'
"""

SQL_SINK_WS_ERRORS = """
SELECT
  resource.labels.service_name AS svc, DATE(timestamp) AS d,
  JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.metadata.close_code') AS close_code,
  JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.metadata.reason_token') AS reason_token,
  COUNT(*) AS n
FROM `{table}`
WHERE JSON_VALUE(TO_JSON_STRING(jsonPayload), '$.message.event_type') = 'ws_error'
GROUP BY 1, 2, 3, 4 ORDER BY 2
"""

SQL_BILLING_LIVE = """
SELECT
  DATE(usage_start_time) AS d,
  sku.description AS sku,
  SUM(cost) AS cost_usd,
  SUM(usage.amount) AS amount
FROM `{table}`
WHERE usage_start_time >= TIMESTAMP('2026-09-01')
  AND LOWER(sku.description) LIKE '%gemini%live%'
GROUP BY 1, 2 ORDER BY 1, 2
"""


def billing_table(bq):
    """Resolve the billing-export table without ever writing its name out."""
    env = os.environ.get("BILLING_EXPORT_TABLE")
    if env:
        return env.strip("`")
    names = [t.table_id for t in bq.list_tables(BILLING_DATASET)
             if t.table_id.startswith(BILLING_TABLE_PREFIX)]
    if len(names) != 1:
        raise SystemExit("expected exactly one %s* table in %s, found %d; set BILLING_EXPORT_TABLE"
                         % (BILLING_TABLE_PREFIX, BILLING_DATASET, len(names)))
    return "%s.%s.%s" % (PROJ, BILLING_DATASET, names[0])


def pull_bigquery():
    bq = bigquery.Client(project=PROJ)
    turns = [dict(r) for r in bq.query(SQL_SINK_TURNS.format(table="%s.%s" % (PROJ, STDOUT_TABLE))).result()]
    res = {"sink_live_voice": {}}
    for key in sorted({(t["svc"], t["model"]) for t in turns}):
        T = [t for t in turns if (t["svc"], t["model"]) == key]
        by_sess = collections.defaultdict(float)
        for t in T:
            by_sess[t["fsess_hash"]] += t["cost"] or 0
        res["sink_live_voice"]["%s|%s" % (SERVICES.get(key[0], key[0]), key[1])] = {
            "days": sorted({t["d"].isoformat() for t in T}),
            "turns": len(T),
            "form_sessions": len(by_sess),
            "turn_cost_usd": summary([t["cost"] for t in T]),
            "form_session_cost_usd": summary(list(by_sess.values())),
            "turn_text_input_tokens": summary([t["text_in"] for t in T]),
            "turn_audio_input_tokens": summary([t["audio_in"] for t in T]),
            "turn_text_output_tokens": summary([t["text_out"] for t in T]),
            "turn_audio_output_tokens": summary([t["audio_out"] for t in T]),
            "turns_with_zero_audio_output": sum(1 for t in T if (t["audio_out"] or 0) == 0),
            "cost_share": {
                "total_usd": round(sum(t["cost"] or 0 for t in T), 6),
            },
        }
    res["sink_ws_errors"] = [
        {k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in dict(r).items()}
        for r in bq.query(SQL_SINK_WS_ERRORS.format(table="%s.%s" % (PROJ, STDOUT_TABLE))).result()]
    bill = [dict(r) for r in bq.query(SQL_BILLING_LIVE.format(table=billing_table(bq))).result()]
    res["billing_live_skus"] = [
        {"d": b["d"].isoformat(), "sku": b["sku"].strip(), "cost_usd": round(b["cost_usd"], 6),
         "amount": b["amount"],
         "usd_per_1m": round(b["cost_usd"] / b["amount"] * 1e6, 3) if b["amount"] else None}
        for b in bill if (b["cost_usd"] or b["amount"])]
    return res


def pull_services():
    out = {}
    for svc in SERVICES:
        r = SESSION.get("https://run.googleapis.com/v2/projects/%s/locations/us-central1/services/%s" % (PROJ, svc))
        r.raise_for_status()
        d = r.json()
        envs = {e["name"]: e.get("value") for c in d.get("template", {}).get("containers", [])
                for e in c.get("env", []) if e["name"] in ("USE_PREMIUM_MODEL", "LINK_CHANNEL")}
        out[svc] = {"latest_ready_revision": d.get("latestReadyRevision", "").split("/")[-1],
                    "update_time": d.get("updateTime"),
                    "image_tag": [c.get("image", "").split(":")[-1][:12]
                                  for c in d.get("template", {}).get("containers", [])],
                    "env": envs}
    return out


def model_attribution(rows):
    """Exit-criterion-3 evidence: how every row got its model, per channel and
    UTC day, plus any model that appears on the 'wrong' side of the cutover
    (3.8 before it, or 2.5 on/after it -- the latter is expected on a channel
    that was never redeployed, so it is reported, not treated as an error)."""
    by_day = collections.Counter()
    for r in rows:
        how = ("logged" if r.get("model") and not r.get("model_attributed")
               else "attributed" if r.get("model_attributed") else "unattributed")
        by_day[(SERVICES[r["svc"]], r["t"].date().isoformat(), r.get("model"), how)] += 1
    out = [{"channel": k[0], "day": k[1], "model": k[2], "source": k[3], "rows": v}
           for k, v in sorted(by_day.items(), key=lambda kv: tuple(str(x) for x in kv[0]))]
    off_cutover = [o for o in out if o["model"] and o["source"] != "unattributed" and (
        ("3.8" in o["model"] and o["day"] < CUTOVER) or ("2.5" in o["model"] and o["day"] >= CUTOVER))]
    return {"rows_by_channel_day_model": out,
            "unattributed_rows": sum(o["rows"] for o in out if o["source"] == "unattributed"),
            "model_vs_date_cutover_mismatches": off_cutover}


def main():
    rows, ws = pull_logging()
    result = {
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "project": PROJ, "log_window_start": LOG_START, "cutover": CUTOVER,
        "services_now": pull_services(),
        "model_attribution": model_attribution(rows),
        "logging_by_channel_model": per_model(rows, ws),
        "monitoring_log_metrics": pull_monitoring(),
    }
    result.update(pull_bigquery())
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    print("wrote", OUT)


if __name__ == "__main__":
    sys.exit(main())
