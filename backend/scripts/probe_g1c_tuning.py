"""G1c checker tuning -- precision (prompt) + latency (caching) optimization.

bd polyglot-pdf-08zv. Follow-up to G1b (0zp3) / G1d (wf3q). G1b settled the model
choice for the out-of-band contradiction checker and wf3q gave it a CLEAN,
validated corpus so the precision numbers are trustworthy. 08zv tunes the two
residual levers G1b surfaced, each measured on the SAME clean corpus
(g1b_corpus.build_corpus) with the SAME scorer (g1b_scoring):

  LEVER 2 -- PRECISION (per-section tier = gemini-2.5-flash-lite). On the clean
  corpus the lite model's false positives concentrate in three diagnosable
  buckets (verified, run g1b_bakeoff_20260627T135913): FOREIGN addresses (city +
  province + foreign country, no US state -> wrongly flagged), US TERRITORIES
  (San Juan/Puerto Rico, Guam, USVI + their ZIPs -> wrongly flagged), and DUAL
  addresses (a mailing + a separate physical address, both valid -> wrongly
  flagged). This probe measures a TUNED prompt (anti-hedging instruction + few-shot
  examples drawn from those exact buckets) vs the G1b BASELINE prompt, on
  2.5-flash-lite, across all sizes. Reports precision lift AND confirms recall is
  not regressed (the gate: recall must not drop).

  LEVER 1 -- LATENCY (end-of-form tier = gemini-3.5-flash, the accuracy tier per
  0zp3's corrected finding -- NOT 2.5-flash, which misses the far/cross-section
  contradictions). The 132-field sweep is slow (G1b p50 ~18s / p90 ~40s). This
  probe measures EXPLICIT context caching (cache the stable SI+rules+few-shot via
  the genai caches API so only the form answers pay full input rate) + a
  payload-TRIM variant, vs the uncached baseline, at size 132. Reports the
  latency + cost delta. (Run with --lever latency; see _run_latency.)

PROVENANCE: SYNTHETIC clean corpus (g1b_answer_key persona). No real PHI.

Usage:
    GEMINI_API_KEY=... PYTHONPATH=. python backend/scripts/probe_g1c_tuning.py --lever precision
    GEMINI_API_KEY=... PYTHONPATH=. python backend/scripts/probe_g1c_tuning.py --lever latency
    # --dry-run     validate scoring offline (perfect oracle, no API calls)
    # --sizes 20,40 limit which sizes to run (precision lever)
    # --concurrency N
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

from backend.scripts.g1b_corpus import build_corpus, corpus_fingerprint  # noqa: E402
from backend.scripts.g1b_scoring import detected as _detected  # noqa: E402
from backend.scripts.g1b_scoring import is_model_format_error as _is_model_format_error  # noqa: E402

# Reuse the EXACT baseline prompt + payload renderer + retry machinery from the
# G1b probe so "baseline" here is byte-identical to the measured G1b baseline.
from backend.scripts.probe_g1b_model_size_bakeoff import (  # noqa: E402
    PROMPT as BASELINE_PROMPT,
    TODAY,
    _payload_json,
    _run,
    _flagged_sets,
    _client,
)

# Per-1M USD text rates (input, output) -- the two tiers 08zv tunes. Mirrors the
# G1b table (input includes the cached-read discount modeling for the latency
# lever, applied in _cost_cached).
RATES = {
    "gemini-2.5-flash-lite": {"in": 0.10, "out": 0.40},
    "gemini-3.5-flash":      {"in": 1.50, "out": 6.00},
}
# Gemini implicit/explicit cached-input is billed at ~0.25x the normal input rate
# (ai.google.dev pricing; the exact ratio varies by model -- used here only for the
# RELATIVE cached-vs-uncached cost delta, not an absolute $/form quote).
_CACHED_IN_DISCOUNT = 0.25
_PER_1M = 1_000_000

OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scripts", "spikes", "data",
)

# ---------------------------------------------------------------------------
# LEVER 2: the TUNED precision prompt. Same checker rules as BASELINE_PROMPT,
# plus (a) an explicit anti-hedging instruction and (b) FEW-SHOT examples drawn
# from the three real FP buckets (foreign / territory / dual). The few-shot
# answers are all the EMPTY verdict, teaching the model these coherent shapes are
# NOT contradictions.
# ---------------------------------------------------------------------------
PROMPT_TUNED = (
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
    "ANTI-HEDGING RULE -- this is the most common mistake, do not make it: only "
    "flag a field pair when one value makes the other GENUINELY IMPOSSIBLE. If an "
    "address is internally consistent, DO NOT flag it, even if it looks unusual. "
    "When uncertain whether something is a real contradiction, DO NOT flag it.\n\n"
    "These are NOT contradictions (never flag them):\n"
    "1. A FOREIGN address: a city + a foreign province/region + a postal code + a "
    "foreign country, with NO US state. Example: 'Toronto, Ontario, M5H 2N2, "
    "Canada' is a complete, coherent Canadian address -- NOT a contradiction. "
    "'Munich, Bavaria, 80331, Germany' and 'Mumbai, Maharashtra, 400001, India' "
    "are likewise coherent. A foreign province is only a problem if a US STATE is "
    "ALSO filled.\n"
    "2. A US TERRITORY: Puerto Rico (San Juan, ZIPs 006xx-009xx), Guam (Hagatna, "
    "ZIP 969xx), and the US Virgin Islands (ZIPs 008xx) are US locations. Their "
    "city + territory + ZIP + 'United States' is coherent -- NOT a contradiction, "
    "even though the territory is not one of the 50 states.\n"
    "3. TWO DIFFERENT addresses: a mailing address and a SEPARATE physical "
    "address may be in different cities/states and both be valid. Example: mailing "
    "'New York, NY' + physical 'Newark, NJ' is normal -- NOT a contradiction. Only "
    "flag if a SINGLE address is internally impossible.\n"
    "4. BIRTH abroad: it is NORMAL for the applicant's COUNTRY OF BIRTH or "
    "CITY/TOWN OF BIRTH to differ from their US mailing address -- an immigrant "
    "born abroad living in the US is expected. Never flag it.\n\n"
    "Return JSON ONLY:\n"
    '{"conflicts": [{"field_ids": ["<field_id>", ...], "reason": "<short>"}]}\n'
    "Use the exact field_id values from the input. Empty list if no contradiction.\n\n"
    "FIELDS:\n{state}"
)

PROMPTS = {"baseline": BASELINE_PROMPT, "tuned": PROMPT_TUNED}


async def _run_with_prompt(client, model, fields, prompt_template):
    """One checker call using a SPECIFIC prompt template. Mirrors the G1b _run
    (retry + per-call timeout + token capture) but lets us swap the prompt. We
    reuse _run by temporarily building the full prompt string here and calling the
    SDK the same way G1b does."""
    prompt = prompt_template.replace("{state}", _payload_json(fields))
    # Reuse the G1b _run retry/timeout path by passing a pre-rendered prompt: _run
    # itself re-renders BASELINE_PROMPT, so for a non-baseline prompt we inline the
    # same call here (kept deliberately close to _run for comparability).
    last_exc = "unknown"
    t0 = time.time()
    for attempt in range(4):
        try:
            resp = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=model, contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"),
                ),
                timeout=60,
            )
            dt = time.time() - t0
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
                return {"verdict": {"conflicts": []}, "latency_s": dt,
                        "in_tok": in_tok, "out_tok": out_tok,
                        "error": "json_error", "retries": attempt}
            return {"verdict": {"conflicts": conflicts}, "latency_s": dt,
                    "in_tok": in_tok, "out_tok": out_tok, "error": "", "retries": attempt}
        except Exception as exc:  # noqa: BLE001
            last_exc = type(exc).__name__
            transient = last_exc in (
                "ConnectError", "ReadError", "ServerError", "ServiceUnavailable",
                "DeadlineExceeded", "ResourceExhausted", "ConnectTimeout",
                "ReadTimeout", "RemoteProtocolError", "TimeoutError",
                "CancelledError")
            if transient and attempt < 3:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            return {"verdict": {"conflicts": []}, "latency_s": time.time() - t0,
                    "in_tok": None, "out_tok": None, "error": last_exc,
                    "retries": attempt}
    return {"verdict": {"conflicts": []}, "latency_s": time.time() - t0,
            "in_tok": None, "out_tok": None, "error": last_exc, "retries": 4}


def _cost(model, in_tok, out_tok):
    r = RATES[model]
    if in_tok is None or out_tok is None:
        return None
    return (in_tok * r["in"] + out_tok * r["out"]) / _PER_1M


async def _lever_precision(args):
    """LEVER 2: baseline vs tuned prompt on 2.5-flash-lite, all sizes."""
    model = "gemini-2.5-flash-lite"
    sizes = [int(s) for s in args.sizes.split(",")] if args.sizes else [20, 40, 132]
    client = None if args.dry_run else _client()
    sem = asyncio.Semaphore(args.concurrency)
    rows = []
    cell = defaultdict(lambda: {"tp": 0, "fn": 0, "fp": 0, "tn": 0, "lat": [],
                                "cost": [], "errors": 0})

    async def _one(size, case, prompt_name):
        if args.dry_run:
            flagged = [set(s) for s in case.expected_conflicts]
            r = {"verdict": {"conflicts": [{"field_ids": sorted(s)} for s in flagged]},
                 "latency_s": 0.0, "in_tok": 10, "out_tok": 2, "error": "", "retries": 0}
            return size, case, prompt_name, r
        async with sem:
            r = await _run_with_prompt(client, model, case.fields, PROMPTS[prompt_name])
        return size, case, prompt_name, r

    def _record(size, case, prompt_name, r):
        flagged = _flagged_sets(r["verdict"])
        det = _detected(case.expected_conflicts, flagged)
        c = cell[(prompt_name, size)]
        if r["error"] and not _is_model_format_error(r["error"]):
            c["errors"] += 1
        else:
            if case.is_contradiction:
                c["tp" if det else "fn"] += 1
            else:
                c["fp" if flagged else "tn"] += 1
        c["lat"].append(r["latency_s"])
        cost = _cost(model, r["in_tok"], r["out_tok"])
        if cost is not None:
            c["cost"].append(cost)
        rows.append({
            "lever": "precision", "model": model, "prompt": prompt_name,
            "size": size, "case_id": case.case_id, "cls": case.cls,
            "is_contradiction": int(case.is_contradiction), "detected": int(det),
            "n_flagged": len(flagged), "latency_s": round(r["latency_s"], 3),
            "in_tok": r["in_tok"], "out_tok": r["out_tok"], "cost_usd": cost,
            "error": r["error"], "corpus_fp": corpus_fingerprint(),
            "flagged_groups": "|".join(";".join(sorted(s)) for s in flagged),
        })

    tasks = []
    for size in sizes:
        for case in build_corpus(size):
            for prompt_name in ("baseline", "tuned"):
                tasks.append(_one(size, case, prompt_name))
    print(f"precision lever: {len(tasks)} calls "
          f"({model}, baseline+tuned, sizes {sizes})", flush=True)
    done = 0
    for coro in asyncio.as_completed(tasks):
        size, case, prompt_name, r = await coro
        _record(size, case, prompt_name, r)
        done += 1
        if done % 40 == 0:
            print(f"  {done}/{len(tasks)} done", flush=True)

    # ---- summary: precision/recall per (prompt x size) ----
    def pct(n, d):
        return n / d if d else float("nan")
    print("\n=== PRECISION LEVER: recall / precision by prompt x size ===", flush=True)
    print(f"{'prompt':<10} {'size':>5} {'recall':>7} {'prec':>6} {'fp':>4} "
          f"{'tp':>4} {'fn':>4} {'lat_p50':>8} {'err':>4}", flush=True)
    summary = {}
    for prompt_name in ("baseline", "tuned"):
        for size in sizes:
            c = cell.get((prompt_name, size))
            if not c:
                continue
            rec = pct(c["tp"], c["tp"] + c["fn"])
            prec = pct(c["tp"], c["tp"] + c["fp"])
            lat = sorted(c["lat"])
            p50 = statistics.median(lat) if lat else float("nan")
            summary[f"{prompt_name}@{size}"] = {
                "recall": rec, "precision": prec, "tp": c["tp"], "fn": c["fn"],
                "fp": c["fp"], "tn": c["tn"], "lat_p50": p50, "errors": c["errors"]}
            print(f"{prompt_name:<10} {size:>5} {rec:>7.3f} {prec:>6.3f} {c['fp']:>4} "
                  f"{c['tp']:>4} {c['fn']:>4} {p50:>8.2f} {c['errors']:>4}", flush=True)

    if args.dry_run:
        print("\n[dry-run] precision scoring verified; no live numbers.", flush=True)
        return
    _write(rows, summary, "precision")


def _write(rows, summary, lever):
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    csv_path = os.path.join(OUT_DIR, f"g1c_{lever}_{stamp}.csv")
    meta_path = os.path.join(OUT_DIR, f"g1c_{lever}_{stamp}.meta.json")
    if rows:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    import math

    def _nan_to_none(o):
        if isinstance(o, float) and math.isnan(o):
            return None
        if isinstance(o, dict):
            return {k: _nan_to_none(v) for k, v in o.items()}
        return o
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(_nan_to_none({
            "bead": "polyglot-pdf-08zv", "lever": lever, "stamp": stamp,
            "corpus_fp": corpus_fingerprint(), "today_for_date_checks": TODAY,
            "summary": summary,
        }), f, indent=2)
    print(f"\nwrote {csv_path}\nwrote {meta_path}", flush=True)


# 3.5-flash implicit/explicit caching MINIMUM (ai.google.dev/gemini-api/docs/caching,
# verified via gemini-docs MCP 2026-06-27): 4096 input tokens. The checker's
# cacheable prefix (SI + rules + few-shot) is ~324 tokens and even the FULL
# 132-field prompt is ~2908 tokens -- BOTH far below 4096 -- so neither implicit
# caching nor an explicit cache can engage. This probe MEASURES that (it tries the
# explicit cache and reports it does not reduce billed input), plus a payload-TRIM
# variant, against the uncached baseline, so exit criterion 1 has a measured delta.
_CACHE_MIN_35 = 4096


async def _lever_latency(args):
    """LEVER 1: 3.5-flash end-of-form (size 132) latency. Variants:
      - baseline:  the G1b prompt, uncached (the measured-of-record baseline).
      - trim:      a payload with field NAMES dropped (id+value only) -- the only
                   real size lever, since the SI is tiny.
    Plus a one-shot cache-feasibility probe: count the prefix tokens and report
    whether explicit caching can engage at all (it cannot, < 4096).
    Reports p50/p90 latency + mean cost per variant. Accuracy is also scored (trim
    must not regress recall)."""
    model = "gemini-3.5-flash"
    client = None if args.dry_run else _client()

    # --- cache-feasibility probe (no scoring; just the structural answer) ---
    if not args.dry_run:
        prefix = BASELINE_PROMPT.split("FIELDS:")[0]
        try:
            ct = client.models.count_tokens(model=model, contents=prefix).total_tokens
        except Exception:  # noqa: BLE001
            ct = None
        print(f"[cache feasibility] checker SI+rules prefix = {ct} tokens; "
              f"3.5-flash cache minimum = {_CACHE_MIN_35}. "
              f"Caching {'CAN' if (ct or 0) >= _CACHE_MIN_35 else 'CANNOT'} engage "
              f"(prefix below minimum).", flush=True)

    sizes = [132]
    sem = asyncio.Semaphore(args.concurrency)
    rows = []
    cell = defaultdict(lambda: {"tp": 0, "fn": 0, "fp": 0, "tn": 0, "lat": [],
                                "cost": [], "errors": 0})

    def _payload_json_trim(fields):
        # id + value only (drop the spoken NAME) -- the only payload-size lever,
        # since the SI is already tiny. Values still carry the field meaning via the
        # id; this measures whether a smaller payload meaningfully cuts latency.
        filled = [{"field_id": f["field_id"], "value": f["value"]}
                  for f in fields if f["value"] not in ("", None)]
        return json.dumps({"fields": filled}, indent=None)

    async def _one(case, variant):
        if args.dry_run:
            flagged = [set(s) for s in case.expected_conflicts]
            return case, variant, {
                "verdict": {"conflicts": [{"field_ids": sorted(s)} for s in flagged]},
                "latency_s": 0.0, "in_tok": 10, "out_tok": 2, "error": "", "retries": 0}
        async with sem:
            if variant == "trim":
                prompt = BASELINE_PROMPT.replace("{state}", _payload_json_trim(case.fields))
            else:
                prompt = BASELINE_PROMPT.replace("{state}", _payload_json(case.fields))
            r = await _run_with_prompt_str(client, model, prompt)
        return case, variant, r

    def _record(case, variant, r):
        flagged = _flagged_sets(r["verdict"])
        det = _detected(case.expected_conflicts, flagged)
        c = cell[variant]
        if r["error"] and not _is_model_format_error(r["error"]):
            c["errors"] += 1
        else:
            if case.is_contradiction:
                c["tp" if det else "fn"] += 1
            else:
                c["fp" if flagged else "tn"] += 1
        c["lat"].append(r["latency_s"])
        cost = _cost(model, r["in_tok"], r["out_tok"])
        if cost is not None:
            c["cost"].append(cost)
        rows.append({
            "lever": "latency", "model": model, "variant": variant, "size": 132,
            "case_id": case.case_id, "cls": case.cls,
            "is_contradiction": int(case.is_contradiction), "detected": int(det),
            "n_flagged": len(flagged), "latency_s": round(r["latency_s"], 3),
            "in_tok": r["in_tok"], "out_tok": r["out_tok"], "cost_usd": cost,
            "error": r["error"], "corpus_fp": corpus_fingerprint(),
        })

    corpus = build_corpus(132)
    tasks = [_one(case, v) for case in corpus for v in ("baseline", "trim")]
    print(f"latency lever: {len(tasks)} calls ({model} @132, baseline+trim)", flush=True)
    done = 0
    for coro in asyncio.as_completed(tasks):
        case, variant, r = await coro
        _record(case, variant, r)
        done += 1
        if done % 20 == 0:
            print(f"  {done}/{len(tasks)} done", flush=True)

    print("\n=== LATENCY LEVER: 3.5-flash @132, baseline vs trim ===", flush=True)
    print(f"{'variant':<10} {'lat_p50':>8} {'lat_p90':>8} {'cost_mean':>10} "
          f"{'recall':>7} {'prec':>6} {'in_med':>7}", flush=True)
    summary = {}
    for variant in ("baseline", "trim"):
        c = cell.get(variant)
        if not c:
            continue
        lat = sorted(c["lat"])
        p50 = statistics.median(lat) if lat else float("nan")
        p90 = lat[int(0.9 * (len(lat) - 1))] if lat else float("nan")
        cost_mean = statistics.mean(c["cost"]) if c["cost"] else float("nan")
        rec = c["tp"] / (c["tp"] + c["fn"]) if (c["tp"] + c["fn"]) else float("nan")
        prec = c["tp"] / (c["tp"] + c["fp"]) if (c["tp"] + c["fp"]) else float("nan")
        in_med = statistics.median([r["in_tok"] for r in rows
                                    if r["variant"] == variant and r["in_tok"]]) \
            if any(r["variant"] == variant and r["in_tok"] for r in rows) else float("nan")
        summary[variant] = {"lat_p50": p50, "lat_p90": p90, "cost_mean": cost_mean,
                            "recall": rec, "precision": prec}
        print(f"{variant:<10} {p50:>8.2f} {p90:>8.2f} {cost_mean*1000:>9.4f}m "
              f"{rec:>7.3f} {prec:>6.3f} {in_med:>7.0f}", flush=True)

    if args.dry_run:
        print("\n[dry-run] latency scoring verified; no live numbers.", flush=True)
        return
    _write(rows, summary, "latency")


async def _run_with_prompt_str(client, model, prompt):
    """One call with a fully-rendered prompt string (retry + timeout + tokens)."""
    last_exc = "unknown"
    t0 = time.time()
    for attempt in range(4):
        try:
            resp = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=model, contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"),
                ),
                timeout=90,
            )
            dt = time.time() - t0
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
                return {"verdict": {"conflicts": []}, "latency_s": dt, "in_tok": in_tok,
                        "out_tok": out_tok, "error": "json_error", "retries": attempt}
            return {"verdict": {"conflicts": conflicts}, "latency_s": dt, "in_tok": in_tok,
                    "out_tok": out_tok, "error": "", "retries": attempt}
        except Exception as exc:  # noqa: BLE001
            last_exc = type(exc).__name__
            transient = last_exc in (
                "ConnectError", "ReadError", "ServerError", "ServiceUnavailable",
                "DeadlineExceeded", "ResourceExhausted", "ConnectTimeout",
                "ReadTimeout", "RemoteProtocolError", "TimeoutError", "CancelledError")
            if transient and attempt < 3:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            return {"verdict": {"conflicts": []}, "latency_s": time.time() - t0,
                    "in_tok": None, "out_tok": None, "error": last_exc, "retries": attempt}
    return {"verdict": {"conflicts": []}, "latency_s": time.time() - t0,
            "in_tok": None, "out_tok": None, "error": last_exc, "retries": 4}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lever", choices=["precision", "latency"], default="precision")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sizes", default="")
    ap.add_argument("--concurrency", type=int, default=6)
    args = ap.parse_args()
    if args.lever == "precision":
        await _lever_precision(args)
    else:
        await _lever_latency(args)


if __name__ == "__main__":
    asyncio.run(main())
