"""G1b bake-off -- model x form-size matrix: speed, cost, accuracy.

bd polyglot-pdf-0zp3. Follow-up to G1 (jnjj.5), which reframed Pillar B from
"replace the in-SI check" to "out-of-band end-of-section + end-of-form text
checker" (maintainer, 2026-06-17). This probe answers the open "what does B look
like" question for the MODEL + the FORM SIZE: it runs a labeled corpus of
full-size form states (20 / 40 / 132 fields -- g1b_corpus.py) through each
candidate TEXT model and records, per (model x size) cell:

  - SPEED:    per-call latency (wall clock around generate_content), p50/p90.
  - COST:     prompt+output tokens x the model's per-token text rate.
  - ACCURACY: recall, precision, plus per-distance and per-class breakdowns.

Generate rich data; analysis later (the report is multiple tables, not one matrix).
The gate is NOT 100%-recall: per the maintainer the checker is ONE layer among
many (per-field read-back, verbal section verify, human translator review, user
review), so this measures "which model, which size, how good/fast/cheap," not a
pass/fail.

MODELS:
  TEXT generateContent path: gemini-2.5-flash-lite, gemini-2.5-flash,
  gemini-3.1-flash-lite, gemini-3-flash-preview, gemini-3.5-flash,
  gemini-2.5-pro (the far-pair coverage candidate, bd W5 / g0w1 -- run with a
  BOUNDED thinking_budget; see THINKING_BUDGET below, it CANNOT be turned off).
  LIVE bidi path (the voice model, gemini-2.5-flash-native-audio): it is bidi-ONLY
  (no generateContent and TEXT modality is rejected, error 1007), so it IS run
  here but via a Live session in tool-calling mode (_run_live) -- it reports the
  verdict through a flat report_conflicts tool call, NOT JSON text. See _run_live.

PII: synthetic fabricated values only (g1b_corpus.py persona). No real PHI.

Usage (Vertex is the DEFAULT -- maintainer directive 2026-07-12: all live-model
work runs on Vertex so costs land on the tracked billing project; ADC +
GOOGLE_CLOUD_PROJECT, e.g. via `gcloud auth application-default login`):
    GOOGLE_CLOUD_PROJECT=... PYTHONPATH=. python backend/scripts/probe_g1b_model_size_bakeoff.py
    # --dry-run     validate scoring offline (perfect oracle, no API calls)
    # --sizes 20,40 limit which sizes to run
    # --models a,b  limit which models to run
    # deliberate AI Studio run (billing NOT on the tracked project):
    VERTEXAI=false GEMINI_API_KEY=... PYTHONPATH=. python backend/scripts/probe_g1b_model_size_bakeoff.py

Converted to Vertex-default for bd polyglot-pdf-rve5; one-shot diagnostic, NOT
re-verified against live Vertex post-conversion. This probe's LIVE bidi path
(_run_live, gemini-2.5-flash-native-audio) may need the Vertex model-id variant
per bd a079.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import datetime
import json
import os
import statistics
import sys
import time
from collections import defaultdict

from google import genai
from google.genai import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.scripts.g1b_corpus import build_corpus  # noqa: E402
from backend.scripts.g1b_corpus import corpus_fingerprint  # noqa: E402

# Stamp every row + the meta with the corpus version so the offline re-scorer
# merges only same-corpus runs (Codex review, PR #253). Computed once at import.
_CORPUS_FP = corpus_fingerprint()

# Per-1M USD text rates (input, output) for the TEXT generateContent models.
# These are the *text* model prices, DISTINCT from config.py's GEMINI_PRICING_BY_FAMILY
# (which is the Live/native-audio audio-tier table). Values per the maintainer's
# brief + ai.google.dev/gemini-api/docs/pricing (2026-06-17). Output includes
# thinking tokens. Pin them here so the cost column is explicit and auditable.
# "live": True marks a bidi Live (native-audio) model that CANNOT do
# generate_content (TEXT modality is rejected, error 1007) -- it is driven over a
# Live session in text-in / AUDIO-out mode and reports its verdict via a TOOL CALL
# (report_conflicts), which we read instead of parsing JSON text. This is the
# exact voice model (USE_PREMIUM_MODEL=false tier). Honest cost note: it emits
# AUDIO, so "out" is the AUDIO-output rate ($2.00/M for 2.5 native-audio, per the
# maintainer + config.py GEMINI_PRICING_BY_FAMILY), NOT a text-out rate -- a
# text-out Live 2.5 model is not available on this API key. Latency includes audio
# synthesis, so it is NOT a pure-text-latency number.
MODELS = {
    "gemini-2.5-flash-lite":  {"in": 0.10, "out": 0.40},
    "gemini-2.5-flash":       {"in": 0.30, "out": 2.50},
    "gemini-3.1-flash-lite":  {"in": 0.25, "out": 2.00},
    "gemini-3-flash-preview": {"in": 0.50, "out": 4.00},
    # gemini-2.5-pro: the far-pair coverage candidate (bd polyglot-pdf-g0w1 / W5).
    # List prices per ai.google.dev/gemini-api/docs/pricing (2026-07-13): $1.25/M
    # in, $10.00/M out for prompts <=200k tokens (the 132-field payload is ~3k
    # tokens, well under 200k). OUTPUT INCLUDES THINKING TOKENS -- and 2.5-pro
    # CANNOT disable thinking (thinking_budget range is 128..32768, budget=0 is
    # rejected; default is DYNAMIC/-1, which dominated a prior day's bill). This
    # arm is therefore ALWAYS run with a BOUNDED thinking_budget (THINKING_BUDGET
    # below) so thinking-output cost is capped and measurable. See _run.
    "gemini-2.5-pro":         {"in": 1.25, "out": 10.00},
    # 3.5-flash: the accuracy tier for the end-of-form sweep. List prices per the
    # AI Studio pricing page (in $1.50/M; out ~$6.00/M) -- VERIFY before quoting a
    # final $/form; the matrix uses them for relative cost. Context caching (cached
    # SI read at a fraction of the input rate) is the intended cost-offset in
    # production but is NOT modeled here (every call pays full input rate).
    "gemini-3.5-flash":       {"in": 1.50, "out": 6.00},
    "gemini-2.5-flash-native-audio-preview-12-2025":
                              {"in": 0.50, "out": 2.00, "live": True},
}
_PER_1M = 1_000_000

# Tool the Live model must call to report its verdict (the structured channel that
# replaces JSON text, since native-audio cannot emit TEXT).
# FLAT tool schema. The native-audio Live endpoint rejects a NESTED
# array-of-objects tool declaration with a 1011 "internal error" (the historical
# 1011 cause is a missing/empty/malformed tool declaration, not endpoint
# flakiness -- maintainer, 2026-06-18; confirmed: nested schema -> 7/8 fail,
# flat schema -> 8/8 succeed). So each conflict is reported as ONE
# semicolon-joined field_id string in a flat array of strings -- the deepest the
# native-audio model reliably accepts. Reasons are dropped (the scorer only needs
# the field-id sets; reason text would also be a PII sink we do not log).
_REPORT_TOOL = {
    "function_declarations": [{
        "name": "report_conflicts",
        "description": "Report every cross-field contradiction found in the form. "
                       "Call this exactly once. Pass an empty array if none.",
        "parameters": {
            "type": "object",
            "properties": {
                "conflict_field_groups": {
                    "type": "array",
                    "description": "One entry per conflict, each a semicolon-joined "
                                   "list of the field_ids implicated in that "
                                   "conflict (e.g. 'addr_state;addr_zip'). Empty "
                                   "array if there is no contradiction.",
                    "items": {"type": "string"},
                },
            },
            "required": ["conflict_field_groups"],
        },
    }],
}


def _live_groups_to_verdict(groups) -> dict:
    """Map the flat report_conflicts args (a list of ';'-joined field-id strings)
    into the standard {"conflicts": [{"field_ids": [...]}]} verdict shape the
    scorer consumes."""
    conflicts = []
    for g in groups or []:
        ids = [x.strip() for x in str(g).split(";") if x.strip()]
        if ids:
            conflicts.append({"field_ids": ids})
    return {"conflicts": conflicts}

SIZES = [20, 40, 132]

OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scripts", "spikes", "data",
)
TODAY = "2026-06-17"

PROMPT = (
    "You are a contradiction checker for a USCIS I-90 immigration form. You are "
    "given the form's currently-filled fields as JSON. Find cross-field "
    "contradictions a human reviewer would flag, using world knowledge:\n"
    "- a US ZIP code that does not belong to the stated US state\n"
    "- a US state filled together with a foreign country\n"
    "- a foreign province filled together with a US state\n"
    "- a US city that is not located in the stated US state\n"
    "- a date of birth in the future (today is " + TODAY + ")\n"
    "- a date of admission that precedes or contradicts the date of birth\n"
    "- the same fact stated two different ways in different places\n\n"
    "Do NOT flag coherent addresses, foreign addresses (province + postal code + "
    "foreign country, no US state), US territories (Puerto Rico, Guam, Virgin "
    "Islands and their ZIPs are valid), or two different but internally-coherent "
    "addresses (a mailing address and a separate physical address). This is an "
    "immigration form: it is NORMAL and NOT a contradiction for the applicant's "
    "COUNTRY OF BIRTH or CITY/TOWN OF BIRTH to differ from their US mailing "
    "address or current country -- an immigrant born abroad living in the US is "
    "expected, never flag it. Only flag a field pair when one is genuinely "
    "impossible or self-contradictory.\n\n"
    "Return JSON ONLY:\n"
    '{"conflicts": [{"field_ids": ["<field_id>", ...], "reason": "<short>"}]}\n'
    "Use the exact field_id values from the input. Empty list if no contradiction.\n\n"
    "FIELDS:\n{state}"
)


def _payload_json(fields: list) -> str:
    # The checker reads only filled fields (drop empties, as in production).
    filled = [{"field_id": f["field_id"], "name": f["name"], "value": f["value"]}
              for f in fields if f["value"] not in ("", None)]
    return json.dumps({"fields": filled}, indent=None)


def _client() -> genai.Client:
    """Vertex by DEFAULT (maintainer directive 2026-07-12: all live-model work
    runs on Vertex so costs land on the tracked billing project). Mirrors the
    production adapter's construction (backend/adapters/text_ai_gemini.py):
    VERTEXAI=true (default) -> ADC + GOOGLE_CLOUD_PROJECT; set VERTEXAI=false
    with GEMINI_API_KEY only for a deliberate AI Studio run.
    """
    if os.environ.get("VERTEXAI", "true").lower() == "true":
        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not project:
            print(
                "VERTEXAI mode but GOOGLE_CLOUD_PROJECT unset; relying on ADC's "
                "default project (gcloud config get-value project).",
                flush=True,
            )
        return genai.Client(
            vertexai=True,
            project=project,
            location=os.environ.get("VERTEX_LOCATION", "us-central1"),
        )
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("VERTEXAI=false but NO KEY in env GEMINI_API_KEY", flush=True)
        sys.exit(2)
    return genai.Client(api_key=key)


# Transient transport/server errors to RETRY (network blips, not model failures).
# A bare-network error must not be scored as a model miss -- it would contaminate
# the accuracy numbers with the test runner's connectivity. json_error (the model
# returned non-JSON) is NOT retried: that IS a model behavior we want to measure.
_RETRYABLE = ("ConnectError", "ReadError", "ServerError", "ServiceUnavailable",
              "DeadlineExceeded", "ResourceExhausted", "ConnectTimeout",
              "ReadTimeout", "RemoteProtocolError",
              # A call that HANGS open (no exception) is the real failure mode that
              # froze the first full sweep: generate_content has no built-in
              # deadline, so a stalled connection blocked the serial loop forever.
              # asyncio.wait_for turns that into a TimeoutError that we retry.
              "TimeoutError", "CancelledError")
_MAX_TRIES = 4
_CALL_TIMEOUT_S = 60  # hard per-attempt deadline; a 132-field call is ~2-5s normally

# Per-model BOUNDED thinking budget (thinking tokens), for the models that think
# by default and would otherwise emit unbounded thinking output (billed at the
# OUTPUT rate). Only models listed here get a thinking_config; every other text
# model keeps the historical behavior (no thinking_config -> the API default),
# so the baseline arms are byte-for-byte comparable to the 6cfu.5 run.
#
# gemini-2.5-pro is the reason this exists (bd W5 / g0w1): on Vertex it thinks by
# default (dynamic, budget=-1) and CANNOT be turned off (budget=0 is rejected;
# valid range 128..32768 -- ai.google.dev/gemini-api/docs/thinking). 512 is a
# small cap suited to a classification/contradiction-check task (not deep math),
# keeping thinking-output cost predictable and low while still allowing the model
# a little reasoning to catch far-apart pairs. Tune upward only with a fresh cost
# estimate. A per-model timeout override lets a thinking model exceed the default
# 60s per-attempt deadline without loosening it for the fast arms.
THINKING_BUDGET = {"gemini-2.5-pro": 512}
_CALL_TIMEOUT_OVERRIDE_S = {"gemini-2.5-pro": 120}


def _text_config(model: str) -> types.GenerateContentConfig:
    """The GenerateContentConfig for a text arm. Adds a BOUNDED thinking_config
    for models in THINKING_BUDGET (2.5-pro) so their thinking-output cost is
    capped and measurable; every other model gets the historical config (JSON
    response, no thinking_config -> API default), keeping the baseline arms
    byte-for-byte comparable to the 6cfu.5 run."""
    budget = THINKING_BUDGET.get(model)
    if budget is not None:
        return types.GenerateContentConfig(
            response_mime_type="application/json",
            thinking_config=types.ThinkingConfig(thinking_budget=budget),
        )
    return types.GenerateContentConfig(response_mime_type="application/json")


async def _run(client, model: str, fields: list) -> dict:
    """One call with retry on transient transport errors + a hard per-call
    timeout. Returns {verdict, latency_s, in_tok, out_tok, think_tok, error,
    retries}. think_tok is the thinking-token count (billed at the OUTPUT rate);
    out_tok is the ANSWER token count -- kept separate so the findings doc can
    report a distinct thinking-output cost line (the W5 cost guard)."""
    prompt = PROMPT.replace("{state}", _payload_json(fields))
    last_exc = "unknown"
    call_timeout = _CALL_TIMEOUT_OVERRIDE_S.get(model, _CALL_TIMEOUT_S)
    config = _text_config(model)
    # latency_s is END-TO-END wall clock from the FIRST attempt, INCLUDING failed
    # attempts and backoff waits (Codex review: timing only the final attempt
    # understated the real user-visible latency in exactly the flaky conditions
    # this probe evaluates). t0 is set once, before the retry loop.
    t0 = time.time()
    for attempt in range(_MAX_TRIES):
        try:
            resp = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=model, contents=prompt, config=config,
                ),
                timeout=call_timeout,
            )
            dt = time.time() - t0
            u = resp.usage_metadata
            in_tok = getattr(u, "prompt_token_count", None) if u else None
            out_tok = getattr(u, "candidates_token_count", None) if u else None
            think_tok = getattr(u, "thoughts_token_count", None) if u else None
            raw = resp.text or ""
            try:
                verdict = json.loads(raw)
                conflicts = verdict.get("conflicts", [])
                if not isinstance(conflicts, list):
                    conflicts = []
            except json.JSONDecodeError:
                # Model returned non-JSON -- a real model behavior, NOT retried.
                return {"verdict": {"conflicts": []}, "latency_s": dt,
                        "in_tok": in_tok, "out_tok": out_tok, "think_tok": think_tok,
                        "error": "json_error", "retries": attempt}
            return {"verdict": {"conflicts": conflicts}, "latency_s": dt,
                    "in_tok": in_tok, "out_tok": out_tok, "think_tok": think_tok,
                    "error": "", "retries": attempt}
        except Exception as exc:  # noqa: BLE001
            last_exc = type(exc).__name__
            if last_exc in _RETRYABLE and attempt < _MAX_TRIES - 1:
                await asyncio.sleep(1.5 * (attempt + 1))  # linear backoff
                continue
            return {"verdict": {"conflicts": []}, "latency_s": time.time() - t0,
                    "in_tok": None, "out_tok": None, "think_tok": None,
                    "error": last_exc, "retries": attempt}
    return {"verdict": {"conflicts": []}, "latency_s": time.time() - t0,
            "in_tok": None, "out_tok": None, "think_tok": None,
            "error": last_exc, "retries": _MAX_TRIES}


# The Live (native-audio) model's system instruction: the SAME checker rules as the
# text PROMPT, but it reports via the report_conflicts TOOL instead of JSON text
# (native-audio cannot emit TEXT). Built by stripping the PROMPT's JSON-output tail
# and the "{state}" placeholder (the payload is sent as a separate turn).
_LIVE_SI = (
    PROMPT.split("Return JSON ONLY:")[0].rstrip()
    + "\n\nYou MUST call the report_conflicts tool EXACTLY ONCE with every "
      "contradiction you find. Use the exact field_id values from the input. "
      "Pass an empty conflicts list if there is no contradiction. Do not speak "
      "your answer; report it only through the tool call."
)


async def _run_live(client, model: str, fields: list) -> dict:
    """One verdict from a bidi Live (native-audio) model, driven text-in /
    tool-out (it cannot emit TEXT). Reads the report_conflicts tool call. Native
    audio occasionally throws 1011 -- retried like a transport error. Latency is
    the full session round-trip (includes audio synthesis); token usage from the
    Live API's usage_metadata when present."""
    payload = "FIELDS:\n" + _payload_json(fields)
    cfg = types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        system_instruction=_LIVE_SI,
        tools=[_REPORT_TOOL],
    )
    # The Live API's streamed messages did NOT carry usage_metadata in testing, so
    # count the INPUT tokens directly (SI + payload) as the cost basis. Output is
    # a tiny tool call BUT the model also synthesizes AUDIO (modality requirement);
    # audio-output tokens are the real output cost and are NOT captured here -- so
    # the Live cost we report is INPUT-ONLY and UNDERSTATES true cost. Noted in the
    # findings. Input dominates anyway (large payload vs a few-field tool call).
    live_in_tok = None
    try:
        ct = await client.aio.models.count_tokens(
            model=model, contents=[_LIVE_SI, payload])
        live_in_tok = getattr(ct, "total_tokens", None)
    except Exception:  # noqa: BLE001
        pass
    # A modest retry budget covers genuinely transient transport hiccups. (The
    # 1011 errors were a malformed-tool-schema bug, now fixed by the flat
    # _REPORT_TOOL above -- NOT endpoint waves -- so a big retry budget is no
    # longer needed.)
    live_tries = 5
    last_exc = "unknown"
    t0 = time.time()  # end-to-end wall clock incl. retries+backoff (Codex review)
    for attempt in range(live_tries):
        try:
            async def _do():
                groups = None
                in_tok = out_tok = None
                async with client.aio.live.connect(model=model, config=cfg) as s:
                    await s.send_realtime_input(text=payload)
                    async for r in s.receive():
                        tc = getattr(r, "tool_call", None)
                        if tc and tc.function_calls:
                            for fc in tc.function_calls:
                                if fc.name == "report_conflicts":
                                    groups = list((dict(fc.args) or {}).get(
                                        "conflict_field_groups", []))
                            break
                        sc = getattr(r, "server_content", None)
                        if sc and getattr(sc, "turn_complete", False):
                            break
                        um = getattr(r, "usage_metadata", None)
                        if um:
                            in_tok = getattr(um, "prompt_token_count", in_tok)
                            out_tok = getattr(um, "response_token_count", None) or \
                                getattr(um, "candidates_token_count", out_tok)
                return groups, in_tok, out_tok

            groups, in_tok, out_tok = await asyncio.wait_for(_do(), timeout=_CALL_TIMEOUT_S)
            dt = time.time() - t0
            # Prefer the streamed usage in_tok if present; else the counted input.
            in_tok = in_tok if in_tok is not None else live_in_tok
            if groups is None:
                # Model never called the tool -- a real model behavior (like a
                # text model emitting non-JSON); NOT retried, scored empty.
                return {"verdict": {"conflicts": []}, "latency_s": dt,
                        "in_tok": in_tok, "out_tok": out_tok,
                        "error": "no_tool_call", "retries": attempt}
            return {"verdict": _live_groups_to_verdict(groups), "latency_s": dt,
                    "in_tok": in_tok, "out_tok": out_tok, "error": "", "retries": attempt}
        except Exception as exc:  # noqa: BLE001
            last_exc = type(exc).__name__
            # transient transport hiccup -- APIError/ConnectionClosed retried.
            retryable = last_exc in _RETRYABLE or "APIError" in last_exc or \
                "ConnectionClosed" in last_exc
            if retryable and attempt < live_tries - 1:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            return {"verdict": {"conflicts": []}, "latency_s": time.time() - t0,
                    "in_tok": None, "out_tok": None,
                    "error": last_exc, "retries": attempt}
    return {"verdict": {"conflicts": []}, "latency_s": 0.0,
            "in_tok": None, "out_tok": None, "error": last_exc, "retries": _MAX_TRIES}


def _flagged_sets(verdict: dict) -> list:
    out = []
    for c in verdict.get("conflicts", []):
        if isinstance(c, dict):
            ids = c.get("field_ids", [])
            if isinstance(ids, list):
                out.append({str(i) for i in ids})
    return out


# Scoring lives in the STDLIB-ONLY g1b_scoring module so the offline tools can
# import it without google.genai. `_detected` here is full-group matching (every
# expected conflict group must be COVERED by some flagged group) -- Codex review:
# any-overlap matching inflated far-distance recall.
from backend.scripts.g1b_scoring import detected as _detected  # noqa: E402
from backend.scripts.g1b_scoring import is_model_format_error as _is_model_format_error  # noqa: E402


def _cost(model: str, in_tok, out_tok, think_tok=None) -> float | None:
    r = MODELS[model]
    if in_tok is None:
        return None
    # Live (native-audio) path has no measurable out_tok (audio-output tokens not
    # streamed) -- report INPUT-ONLY cost, an UNDERSTATEMENT (see _run_live note).
    # Text path requires both in and out.
    if out_tok is None:
        if r.get("live"):
            return (in_tok * r["in"]) / _PER_1M
        return None
    # THINKING tokens bill at the OUTPUT rate (ai.google.dev/gemini-api/docs/
    # thinking: "response pricing is the sum of output tokens and thinking
    # tokens"). candidates_token_count (out_tok) does NOT include the thinking
    # tokens (thoughts_token_count is a separate field), so add them explicitly
    # or the pro arm's cost is understated. think_tok is None/0 for the arms that
    # do not think, leaving their cost unchanged.
    think = think_tok or 0
    return (in_tok * r["in"] + (out_tok + think) * r["out"]) / _PER_1M


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sizes", default="")
    ap.add_argument("--models", default="")
    ap.add_argument("--concurrency", type=int, default=8,
                    help="max in-flight calls; lower (3-4) for big 132-field "
                         "payloads to avoid the rate-limit -> timeout spiral")
    args = ap.parse_args()

    sizes = [int(s) for s in args.sizes.split(",")] if args.sizes else SIZES
    models = [m.strip() for m in args.models.split(",")] if args.models else list(MODELS)
    for m in models:
        if m not in MODELS:
            print(f"unknown model {m}; known: {list(MODELS)}", flush=True)
            sys.exit(2)

    client = None if args.dry_run else _client()

    rows = []  # per (model, size, case) record
    # (model,size) -> accumulators
    cell = defaultdict(lambda: {"tp": 0, "fn": 0, "fp": 0, "tn": 0,
                                "lat": [], "cost": [], "in": [], "out": [],
                                "think": [], "errors": 0})

    # Stamp + paths fixed up front so we can CHECKPOINT the CSV after each size --
    # a long sweep that dies mid-run (the first attempt hung ~2h on a stuck call)
    # still leaves every COMPLETED size on disk instead of losing everything.
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    csv_path = os.path.join(OUT_DIR, f"g1b_bakeoff_{stamp}.csv")
    meta_path = os.path.join(OUT_DIR, f"g1b_bakeoff_{stamp}.meta.json")

    def _checkpoint_csv():
        if not rows or args.dry_run:
            return
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    # Bounded concurrency: run (case x model) calls in parallel so the slow
    # models (2.5-flash, 3-flash-preview at ~8-11s/call) don't serialize the whole
    # sweep into a 3-hour run. A semaphore caps in-flight calls so we don't trip
    # rate limits. Each _run still measures its OWN latency, so per-call speed
    # numbers stay accurate under concurrency.
    sem = asyncio.Semaphore(args.concurrency)

    async def _one(size, case, model):
        if args.dry_run:
            flagged = [set(s) for s in case.expected_conflicts]
            return size, case, model, {
                "verdict": {"conflicts": [{"field_ids": sorted(s)} for s in flagged]},
                "latency_s": 0.0, "in_tok": 10, "out_tok": 2, "think_tok": None,
                "error": "", "retries": 0}
        async with sem:
            if MODELS[model].get("live"):
                r = await _run_live(client, model, case.fields)
            else:
                r = await _run(client, model, case.fields)
        return size, case, model, r

    def _record(size, case, model, r):
        flagged = _flagged_sets(r["verdict"])
        det = _detected(case.expected_conflicts, flagged)
        c = cell[(model, size)]
        # TWO kinds of "error" must be scored DIFFERENTLY (Codex review):
        #  - TRANSPORT failure (timeout / 5xx / connect) = "no measurement";
        #    excluded from tp/fn/fp/tn, only the error rate tracks it.
        #  - MODEL-FORMAT failure (json_error / no_tool_call) = the model produced
        #    no usable verdict = an empty verdict = a MISS on a contradiction (FN),
        #    a clean-pass on a clean case (TN). Excluding it would inflate recall.
        if r["error"] and not _is_model_format_error(r["error"]):
            c["errors"] += 1
        else:
            # scored: a model-format error has flagged=[] -> det=False already.
            if case.is_contradiction:
                c["tp" if det else "fn"] += 1
            else:
                c["fp" if flagged else "tn"] += 1
        think_tok = r.get("think_tok")
        c["lat"].append(r["latency_s"])
        if r["in_tok"] is not None:
            c["in"].append(r["in_tok"])
        if r["out_tok"] is not None:
            c["out"].append(r["out_tok"])
        if think_tok is not None:
            c["think"].append(think_tok)
        cost = _cost(model, r["in_tok"], r["out_tok"], think_tok)
        if cost is not None:
            c["cost"].append(cost)
        rows.append({
            "size": size, "model": model, "case_id": case.case_id,
            "cls": case.cls, "distance": case.distance,
            "is_contradiction": int(case.is_contradiction),
            "detected": int(det), "n_flagged": len(flagged),
            "latency_s": round(r["latency_s"], 3),
            "in_tok": r["in_tok"], "out_tok": r["out_tok"],
            "think_tok": think_tok,
            "cost_usd": cost, "error": r["error"], "retries": r.get("retries", 0),
            # flat union (back-compat) + per-GROUP structure (so a re-score can do
            # full-group matching without re-running): groups '|'-separated,
            # fields within a group ';'-separated.
            "flagged_ids": ";".join(sorted({i for s in flagged for i in s})),
            "flagged_groups": "|".join(";".join(sorted(s)) for s in flagged),
            # corpus version: lets g1b_merge.py combine ONLY same-corpus runs, so a
            # clean-corpus run is never blended with older contaminated runs that
            # share case_ids (Codex review, PR #253).
            "corpus_fp": _CORPUS_FP,
        })

    for size in sizes:
        corpus = build_corpus(size)
        nc = sum(1 for c in corpus if c.is_contradiction)
        print(f"\n=== size {size}: {len(corpus)} cases ({nc} contra) x {len(models)} models ===",
              flush=True)
        tasks = [_one(size, case, model) for case in corpus for model in models]
        done = 0
        for coro in asyncio.as_completed(tasks):
            size_, case_, model_, r = await coro
            _record(size_, case_, model_, r)
            done += 1
            if done % len(models) == 0:
                print(f"  size {size}: {done}/{len(tasks)} calls done", flush=True)
            if done % 16 == 0:
                _checkpoint_csv()  # incremental flush (not just per-size) -- the
                # per-size-only checkpoint lost a near-complete 132 cell when the
                # last few straggler retries kept the process alive past the size.
        _checkpoint_csv()  # final flush for this size
        if not args.dry_run:
            print(f"  [checkpoint] size {size} written to {os.path.basename(csv_path)}",
                  flush=True)

    # ---- matrix summary ----
    def pct(n, d):
        return n / d if d else float("nan")

    print("\n\n=== MATRIX: recall / precision / median-latency / mean-cost ===", flush=True)
    print(f"{'model':<24} {'size':>5} {'recall':>7} {'prec':>6} {'lat_p50':>8} "
          f"{'lat_p90':>8} {'cost_mean':>10} {'in_med':>7} {'out_med':>7} "
          f"{'think_med':>9} {'err':>4}", flush=True)
    summary = {}
    for model in models:
        for size in sizes:
            c = cell.get((model, size))
            if not c:
                continue
            rec = pct(c["tp"], c["tp"] + c["fn"])
            prec = pct(c["tp"], c["tp"] + c["fp"])
            lat = sorted(c["lat"])
            p50 = statistics.median(lat) if lat else float("nan")
            p90 = lat[int(0.9 * (len(lat) - 1))] if lat else float("nan")
            cost_mean = statistics.mean(c["cost"]) if c["cost"] else float("nan")
            in_med = statistics.median(c["in"]) if c["in"] else float("nan")
            out_med = statistics.median(c["out"]) if c["out"] else float("nan")
            # think_med: median thinking tokens/call (the cost line the W5 guard
            # tracks). NaN for arms that do not report thoughts_token_count.
            think_med = statistics.median(c["think"]) if c["think"] else float("nan")
            summary[f"{model}@{size}"] = {
                "recall": rec, "precision": prec, "tp": c["tp"], "fn": c["fn"],
                "fp": c["fp"], "tn": c["tn"], "lat_p50": p50, "lat_p90": p90,
                "cost_mean": cost_mean, "in_med": in_med, "out_med": out_med,
                "think_med": think_med, "errors": c["errors"],
            }
            print(f"{model:<24} {size:>5} {rec:>7.3f} {prec:>6.3f} {p50:>8.2f} "
                  f"{p90:>8.2f} {cost_mean*1000:>9.4f}m {in_med:>7.0f} {out_med:>7.0f} "
                  f"{think_med:>9.0f} {c['errors']:>4}", flush=True)
    print("  (cost_mean shown in milli-dollars per call: 1.0m = $0.001; "
          "think_med = median thinking tokens/call, billed at the output rate)",
          flush=True)

    if args.dry_run:
        print("\n[dry-run] scoring matrix verified; no live numbers recorded.", flush=True)
        return

    # Final CSV write (the per-size checkpoints already wrote completed sizes;
    # this is the complete, final flush using the same path).
    _checkpoint_csv()

    import math

    def _nan_to_none(o):
        if isinstance(o, float) and math.isnan(o):
            return None
        if isinstance(o, dict):
            return {k: _nan_to_none(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_nan_to_none(v) for v in o]
        return o

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(_nan_to_none({
            "bead": "polyglot-pdf-0zp3",
            "stamp": stamp,
            "corpus_fp": _CORPUS_FP,
            "today_for_date_checks": TODAY,
            "sizes": sizes,
            "models": {m: MODELS[m] for m in models},
            "provenance": "SYNTHETIC full-size form states over real I-90 fields",
            "note_voice_model": ("2.5-flash-native-audio is bidi-only (TEXT modality "
                                 "rejected); when run, it goes via a Live session in "
                                 "tool-calling mode (_run_live), not generate_content."),
            "summary": summary,
        }), f, indent=2)
    print(f"\nwrote {csv_path}\nwrote {meta_path}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
