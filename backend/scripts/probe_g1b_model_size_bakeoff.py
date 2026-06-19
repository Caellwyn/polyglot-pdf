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

MODELS (text generateContent; ids verified callable 2026-06-17):
  gemini-2.5-flash-lite, gemini-2.5-flash, gemini-3.1-flash-lite,
  gemini-3-flash-preview.
  NOTE: the voice model (2.5-flash-live / native-audio) is bidi-ONLY (no
  generateContent), so "voice model as text checker" needs the Live-session
  harness and is a SEPARATE probe -- not run here (flagged in the bead).

PII: synthetic fabricated values only (g1b_corpus.py persona). No real PHI.

Usage:
    GEMINI_API_KEY=... PYTHONPATH=. python backend/scripts/probe_g1b_model_size_bakeoff.py
    # --dry-run     validate scoring offline (perfect oracle, no API calls)
    # --sizes 20,40 limit which sizes to run
    # --models a,b  limit which models to run
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

# Per-1M USD text rates (input, output) for the TEXT generateContent models.
# These are the *text* model prices, DISTINCT from config.py's GEMINI_PRICING_BY_FAMILY
# (which is the Live/native-audio audio-tier table). Values per the maintainer's
# brief + ai.google.dev/gemini-api/docs/pricing (2026-06-17). Output includes
# thinking tokens. Pin them here so the cost column is explicit and auditable.
MODELS = {
    "gemini-2.5-flash-lite":  {"in": 0.10, "out": 0.40},
    "gemini-2.5-flash":       {"in": 0.30, "out": 2.50},
    "gemini-3.1-flash-lite":  {"in": 0.25, "out": 2.00},
    "gemini-3-flash-preview": {"in": 0.50, "out": 4.00},
}
_PER_1M = 1_000_000

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
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("NO KEY in env GEMINI_API_KEY", flush=True)
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


async def _run(client, model: str, fields: list) -> dict:
    """One call with retry on transient transport errors + a hard per-call
    timeout. Returns {verdict, latency_s, in_tok, out_tok, error, retries}."""
    prompt = PROMPT.replace("{state}", _payload_json(fields))
    last_exc = "unknown"
    for attempt in range(_MAX_TRIES):
        t = time.time()
        try:
            resp = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=model, contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json"),
                ),
                timeout=_CALL_TIMEOUT_S,
            )
            dt = time.time() - t
            u = resp.usage_metadata
            in_tok = getattr(u, "prompt_token_count", None) if u else None
            out_tok = getattr(u, "candidates_token_count", None) if u else None
            raw = resp.text or ""
            try:
                verdict = json.loads(raw)
                conflicts = verdict.get("conflicts", [])
                if not isinstance(conflicts, list):
                    conflicts = []
            except json.JSONDecodeError:
                # Model returned non-JSON -- a real model behavior, NOT retried.
                return {"verdict": {"conflicts": []}, "latency_s": dt,
                        "in_tok": in_tok, "out_tok": out_tok,
                        "error": "json_error", "retries": attempt}
            return {"verdict": {"conflicts": conflicts}, "latency_s": dt,
                    "in_tok": in_tok, "out_tok": out_tok, "error": "", "retries": attempt}
        except Exception as exc:  # noqa: BLE001
            last_exc = type(exc).__name__
            if last_exc in _RETRYABLE and attempt < _MAX_TRIES - 1:
                await asyncio.sleep(1.5 * (attempt + 1))  # linear backoff
                continue
            return {"verdict": {"conflicts": []}, "latency_s": time.time() - t,
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


def _detected(expected: list, flagged: list) -> bool:
    for exp in expected:
        for fl in flagged:
            if exp & fl:
                return True
    return False


def _cost(model: str, in_tok, out_tok) -> float | None:
    if in_tok is None or out_tok is None:
        return None
    r = MODELS[model]
    return (in_tok * r["in"] + out_tok * r["out"]) / _PER_1M


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
                                "errors": 0})

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
                "latency_s": 0.0, "in_tok": 10, "out_tok": 2, "error": "", "retries": 0}
        async with sem:
            r = await _run(client, model, case.fields)
        return size, case, model, r

    def _record(size, case, model, r):
        flagged = _flagged_sets(r["verdict"])
        det = _detected(case.expected_conflicts, flagged)
        c = cell[(model, size)]
        if case.is_contradiction:
            c["tp" if det else "fn"] += 1
        else:
            c["fp" if flagged else "tn"] += 1
        if r["error"]:
            c["errors"] += 1
        c["lat"].append(r["latency_s"])
        if r["in_tok"] is not None:
            c["in"].append(r["in_tok"])
        if r["out_tok"] is not None:
            c["out"].append(r["out_tok"])
        cost = _cost(model, r["in_tok"], r["out_tok"])
        if cost is not None:
            c["cost"].append(cost)
        rows.append({
            "size": size, "model": model, "case_id": case.case_id,
            "cls": case.cls, "distance": case.distance,
            "is_contradiction": int(case.is_contradiction),
            "detected": int(det), "n_flagged": len(flagged),
            "latency_s": round(r["latency_s"], 3),
            "in_tok": r["in_tok"], "out_tok": r["out_tok"],
            "cost_usd": cost, "error": r["error"], "retries": r.get("retries", 0),
            "flagged_ids": ";".join(sorted({i for s in flagged for i in s})),
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
          f"{'lat_p90':>8} {'cost_mean':>10} {'in_med':>7} {'out_med':>7} {'err':>4}",
          flush=True)
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
            summary[f"{model}@{size}"] = {
                "recall": rec, "precision": prec, "tp": c["tp"], "fn": c["fn"],
                "fp": c["fp"], "tn": c["tn"], "lat_p50": p50, "lat_p90": p90,
                "cost_mean": cost_mean, "in_med": in_med, "out_med": out_med,
                "errors": c["errors"],
            }
            print(f"{model:<24} {size:>5} {rec:>7.3f} {prec:>6.3f} {p50:>8.2f} "
                  f"{p90:>8.2f} {cost_mean*1000:>9.4f}m {in_med:>7.0f} {out_med:>7.0f} "
                  f"{c['errors']:>4}", flush=True)
    print("  (cost_mean shown in milli-dollars per call: 1.0m = $0.001)", flush=True)

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
            "today_for_date_checks": TODAY,
            "sizes": sizes,
            "models": {m: MODELS[m] for m in models},
            "provenance": "SYNTHETIC full-size form states over real I-90 fields",
            "note_voice_model": ("2.5-flash-live/native-audio is bidi-only; not run "
                                 "here as a text checker -- separate probe needed."),
            "summary": summary,
        }), f, indent=2)
    print(f"\nwrote {csv_path}\nwrote {meta_path}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
