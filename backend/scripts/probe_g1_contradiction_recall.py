"""G1 keystone probe -- flash-lite contradiction recall vs the in-SI check.

bd polyglot-pdf-jnjj.5. The offline GO/NO-GO gate for Pillar B (the cheap-model
validator) AND for removing the incumbent in-system-instruction ADDRESS
CONSISTENCY check. Scores 3 arms BLIND on a labeled set (backend/scripts/g1_corpus.py):

  (i)  in_si_check   the voice model's sibling text model (gemini-2.5-flash) given
                     the VERBATIM in-SI ADDRESS CONSISTENCY prose as its rule, over
                     the full-state payload.
  (ii) flash_lite    gemini-2.5-flash-lite given a dedicated contradiction prompt
                     over the SAME full-state payload (the proposed replacement).
  (iii) no_check      the floor: catches nothing (recall 0). Quantifies what the
                     contradictions cost if NO check runs at all.

FAIRNESS (bead constraint 2): arm (i) fires mid-conversation with only
fields-so-far in production; arm (ii) fires at a section/form boundary over full
state. A naive static-set comparison is structurally biased toward GO. This probe
removes the variable by evaluating BOTH live arms at the SAME boundary over the
SAME full-state payload -- so the comparison isolates "which model+prompt detects
contradictions better," not "who saw more fields." The RESIDUAL bias that remains
(arm i in production also has the conversational/audio channel and fires more
often, incrementally) is recorded in the findings doc, not silently dropped.

PROVENANCE (bead constraint 1): the corpus is SYNTHETIC INJECTION over REAL I-90
field structure -- see g1_corpus.py's module docstring. Recall numbers are an
UPPER BOUND on real-world recall.

PII: this probe sends fabricated values only (no real PII). It still follows the
no-PHI-logged discipline -- it logs case ids, classes, counts, and verdict field
ids, never prints values to a persistent log sink (CSV/JSON output of fabricated
values is the measurement artifact, acceptable per the synthetic corpus).

Usage (Vertex is the DEFAULT -- maintainer directive 2026-07-12: all live-model
work runs on Vertex so costs land on the tracked billing project; ADC +
GOOGLE_CLOUD_PROJECT, e.g. via `gcloud auth application-default login`):
    GOOGLE_CLOUD_PROJECT=... PYTHONPATH=. python backend/scripts/probe_g1_contradiction_recall.py
    # add --dry-run to validate scoring offline with a stub model (no API calls)
    # deliberate AI Studio run (billing NOT on the tracked project):
    VERTEXAI=false GEMINI_API_KEY=... PYTHONPATH=. python backend/scripts/probe_g1_contradiction_recall.py

Converted to Vertex-default for bd polyglot-pdf-rve5; one-shot diagnostic, NOT
re-verified against live Vertex post-conversion.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import datetime
import json
import os
import sys
from collections import defaultdict

from google import genai
from google.genai import types

# Allow running as a module from repo root (PYTHONPATH=.).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.scripts.g1_corpus import build_corpus  # noqa: E402
from backend.scripts.lite_probe_textai import RecordingTextAI, new_record  # noqa: E402
from backend.services.validator_service import render_validator_payload  # noqa: E402

MODEL_IN_SI = "gemini-2.5-flash"        # voice model's text sibling (2.5 tier)
MODEL_FLASH_LITE = "gemini-2.5-flash-lite"

OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scripts", "spikes", "data",
)

# A fixed "today" so future-dob judgments are deterministic and reproducible.
# (Passed to BOTH live arms identically -- a matched input, not an arm advantage.)
TODAY = "2026-06-17"


# The in-SI ADDRESS CONSISTENCY prose, VERBATIM from backend/config.py:380-385,
# is what incumbent arm (i) is scored against (so arm (i) tests the REAL incumbent
# address rule, not a paraphrase). Two faithful additions, both also given to arm
# (ii) so the comparison stays symmetric and fair:
#   - an EXPLICIT date-sanity instruction (DOB-not-future, admission-not-before-DOB).
#     config.py carries date checking only as the vague CONSTRAINTS line "Sanity
#     check dates/phones/ZIP codes" (config.py:375), NOT in the ADDRESS CONSISTENCY
#     block; this probe spells it out so the 6 date-class cases are actually
#     exercised. Both arms get the identical instruction, so it cannot bias the
#     in_si-vs-flash_lite comparison.
#   - a JSON-output instruction so the probe can parse the decision into the
#     contract-1 verdict shape (in production the live model VOICES the steer;
#     here we score the detection decision the prose drives).
IN_SI_PROMPT = (
    "You are a form-filling assistant filling a USCIS I-90 immigration form by "
    "voice. After filling any address-cluster field (state, zip, province, "
    "country), check coherence with other address fields already filled using "
    "world knowledge (zip-to-state, US state vs. foreign province, country vs. "
    "state/province). If a conflict exists, name both fields and ask the user to "
    "verify: e.g. 'You said West Virginia but that zip code is in Iowa -- are "
    "both correct?' Accept the user's answer if they confirm.\n\n"
    "You are reviewing the CURRENT form state below at a section boundary. "
    "Today's date is " + TODAY + ". Also sanity-check dates (a date of birth must "
    "not be in the future; a date of admission cannot precede the date of "
    "birth).\n\n"
    "Report every conflict you find as JSON ONLY, no prose:\n"
    '{"conflicts": [{"field_ids": ["<id>", ...], "reason": "<short reason>"}]}\n'
    "Use the exact field_id values from the state. If there is no conflict, "
    'return {"conflicts": []}.\n\n'
    "FORM STATE:\n{state}"
)

# Arm (ii): a dedicated, purpose-built contradiction prompt for the cheap
# validator. This is the prompt B3 will own; the probe pins a faithful candidate
# so the GO/NO-GO scores the validator as it would actually be deployed.
FLASH_LITE_PROMPT = (
    "You are a contradiction checker for a USCIS I-90 immigration form. You are "
    "given the form's currently-filled fields as JSON. Find cross-field "
    "contradictions a human reviewer would flag, using world knowledge:\n"
    "- a US ZIP code that does not belong to the stated US state\n"
    "- a US state filled together with a foreign country\n"
    "- a foreign province filled together with a US state\n"
    "- a US city that is not located in the stated US state\n"
    "- a date of birth in the future (today is " + TODAY + ")\n"
    "- a date of admission that precedes the date of birth\n\n"
    "Do NOT flag coherent addresses, foreign addresses (province + postal code + "
    "foreign country, no US state), US territories (Puerto Rico, Guam, Virgin "
    "Islands and their ZIPs are valid), two different but internally-coherent "
    "addresses (a mailing address and a separate physical address), or sparse "
    "state with too little to compare.\n\n"
    "Return JSON ONLY:\n"
    '{"conflicts": [{"field_ids": ["<field_id>", ...], "reason": "<short>"}]}\n'
    "Use the exact field_id values from the input. Empty list if no contradiction.\n\n"
    "FIELDS:\n{state}"
)


def _state_json(fields: list) -> str:
    """Render the contract-2 payload as the JSON the model reads."""
    return json.dumps({"fields": fields}, indent=2)


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
            location=os.environ.get("VERTEX_LOCATION", "global"),
        )
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("VERTEXAI=false but NO KEY in env GEMINI_API_KEY", flush=True)
        sys.exit(2)
    return genai.Client(api_key=key)


async def _run_arm(client, model: str, prompt_tmpl: str, fields: list) -> dict:
    """One model call for one case. Returns parsed verdict or fail-open empty."""
    prompt = prompt_tmpl.replace("{state}", _state_json(fields))
    try:
        resp = await client.aio.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        raw = resp.text or ""
        verdict = json.loads(raw)
        conflicts = verdict.get("conflicts", [])
        if not isinstance(conflicts, list):
            return {"conflicts": [], "_parse": "bad_conflicts_type"}
        return {"conflicts": conflicts}
    except json.JSONDecodeError:
        return {"conflicts": [], "_parse": "json_error"}
    except Exception as exc:  # noqa: BLE001
        return {"conflicts": [], "_error": type(exc).__name__}


async def _run_prod_arm(ai, fields: list) -> dict:
    """bd u0kcc: one call through the SHIPPED validator path -- the production
    render_validator_payload (CONTRADICTION_SI + FIELDS tail) into
    TextAIGemini.validate() with the production generate config. The adapter
    fail-opens every failure to an empty verdict, so the outcome (transport error
    vs json_error vs verdict) plus latency/usage is read from the RecordingTextAI
    record. One retry budget for a transient transport error, as a 5xx blip is
    "no measurement", not a miss."""
    payload = render_validator_payload(fields, today=TODAY)
    for attempt in range(3):
        rec = new_record()
        await ai.validate(payload)
        if rec["error"] and attempt < 2:
            await asyncio.sleep(2 * (attempt + 1))
            continue
        meta = {"latency_s": rec["latency_s"], "usage": rec["usage"] or {},
                "retries": attempt}
        if rec["error"]:
            return {"conflicts": [], "_error": rec["error"], "_meta": meta}
        try:
            verdict = json.loads(rec["raw"] or "")
        except json.JSONDecodeError:
            return {"conflicts": [], "_parse": "json_error", "_meta": meta}
        conflicts = verdict.get("conflicts", []) if isinstance(verdict, dict) else None
        if not isinstance(conflicts, list):
            return {"conflicts": [], "_parse": "bad_conflicts_type", "_meta": meta}
        return {"conflicts": conflicts, "_meta": meta}
    return {"conflicts": [], "_error": "unreachable"}


def _flagged_sets(verdict: dict) -> list:
    """Extract the set of field_ids per reported conflict (defensive parse)."""
    out = []
    for c in verdict.get("conflicts", []):
        if isinstance(c, dict):
            ids = c.get("field_ids", [])
            if isinstance(ids, list):
                out.append({str(i) for i in ids})
    return out


def _case_detected(expected: list, flagged: list) -> bool:
    """Case-level detection: did the arm flag ANY conflict overlapping an
    expected conflict? This is the SAFETY-relevant signal -- the validator's job
    is to surface the contradiction so the model can steer; exact field-set
    membership is secondary (scored separately as strict match)."""
    for exp in expected:
        for fl in flagged:
            if exp & fl:  # any overlap on the implicated fields
                return True
    return False


def _case_strict(expected: list, flagged: list) -> bool:
    """Strict: every expected conflict's exact field set appears in the flags."""
    flagged_frozen = {frozenset(s) for s in flagged}
    return all(frozenset(exp) in flagged_frozen for exp in expected)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Score offline with a perfect-oracle stub (no API calls).")
    ap.add_argument("--limit", type=int, default=0, help="Cap cases (debug).")
    ap.add_argument("--lite-model", default=MODEL_FLASH_LITE,
                    help="model for the flash_lite arm (bd u0kcc; the 3.x lite "
                         "tier is served at Vertex location global)")
    ap.add_argument("--lite-prompt", choices=["probe", "prod"], default="probe",
                    help="probe = this file's FLASH_LITE_PROMPT via a raw call; "
                         "prod = the SHIPPED CONTRADICTION_SI via TextAIGemini")
    ap.add_argument("--skip-in-si", action="store_true",
                    help="drop the 2.5-flash in_si_check arm")
    ap.add_argument("--repeats", type=int, default=1,
                    help="run the corpus this many times (pooled counts)")
    args = ap.parse_args()

    corpus = build_corpus()
    if args.limit:
        corpus = corpus[: args.limit]

    n_contra = sum(1 for c in corpus if c.is_contradiction)
    n_clean = len(corpus) - n_contra
    print(f"corpus: {len(corpus)} cases = {n_contra} contradiction + {n_clean} clean",
          flush=True)

    client = None if args.dry_run else _client()

    # arm -> (model, prompt) ; no_check arm is computed, not called.
    # bd u0kcc: --lite-model swaps the flash_lite arm's model, --lite-prompt prod
    # routes it through the SHIPPED validator path (_run_prod_arm), and
    # --skip-in-si drops the 2.5-flash incumbent arm (not the u0kcc question).
    lite_model = args.lite_model
    arms = {}
    if not args.skip_in_si:
        arms["in_si_check"] = (MODEL_IN_SI, IN_SI_PROMPT)
    arms["flash_lite"] = (lite_model, FLASH_LITE_PROMPT)
    prod_ai = (RecordingTextAI(lite_model)
               if (args.lite_prompt == "prod" and not args.dry_run) else None)

    # Per-arm, per-case results.
    rows = []  # for CSV
    # arm -> counters
    stat = {a: defaultdict(int) for a in list(arms) + ["no_check"]}

    work = [(r, c) for r in range(args.repeats) for c in corpus]
    for ci, (rep_i, case) in enumerate(work):
        verdicts = {}
        for arm, (model, tmpl) in arms.items():
            if args.dry_run:
                # Perfect oracle: flag exactly the expected conflicts.
                v = {"conflicts": [{"field_ids": sorted(s), "reason": "stub"}
                                   for s in case.expected_conflicts]}
            elif arm == "flash_lite" and prod_ai is not None:
                v = await _run_prod_arm(prod_ai, case.fields)
            else:
                v = await _run_arm(client, model, tmpl, case.fields)
            verdicts[arm] = v
        verdicts["no_check"] = {"conflicts": []}

        for arm in stat:
            flagged = _flagged_sets(verdicts[arm])
            detected = _case_detected(case.expected_conflicts, flagged)
            strict = _case_strict(case.expected_conflicts, flagged)
            if verdicts[arm].get("_error"):
                # transport failure = no measurement (excluded), never a miss
                stat[arm]["errors"] += 1
            elif case.is_contradiction:
                # recall side
                if detected:
                    stat[arm]["tp"] += 1
                else:
                    stat[arm]["fn"] += 1
                if strict:
                    stat[arm]["tp_strict"] += 1
            elif not case.is_contradiction:
                # precision side: a clean case flagged is a false positive
                if flagged:
                    stat[arm]["fp"] += 1
                else:
                    stat[arm]["tn"] += 1
            meta = verdicts[arm].get("_meta") or {}
            usage = meta.get("usage") or {}
            rows.append({
                "repeat": rep_i,
                "model": arms[arm][0] if arm in arms else "",
                "error": verdicts[arm].get("_error") or verdicts[arm].get("_parse") or "",
                "latency_s": (round(meta["latency_s"], 3)
                              if meta.get("latency_s") is not None else ""),
                "prompt_tok": usage.get("prompt", ""),
                "cached_tok": usage.get("cached", ""),
                "output_tok": usage.get("output", ""),
                "thoughts_tok": usage.get("thoughts", ""),
                "case_id": case.case_id,
                "cls": case.cls,
                "is_contradiction": int(case.is_contradiction),
                "arm": arm,
                "detected": int(detected),
                "strict": int(strict),
                "n_flagged": len(flagged),
                "flagged_ids": ";".join(sorted({i for s in flagged for i in s})),
            })
        print(f"  [{ci+1}/{len(work)}] {case.case_id} ({case.cls}) done", flush=True)

    # ---- score ----
    def _prec_rec(c):
        tp, fp, fn = c["tp"], c["fp"], c["fn"]
        prec = tp / (tp + fp) if (tp + fp) else float("nan")
        rec = tp / (tp + fn) if (tp + fn) else float("nan")
        return prec, rec

    print("\n=== 3-ARM PRECISION / RECALL (case-level detection) ===", flush=True)
    print(f"{'arm':<14} {'recall':>8} {'precision':>10} {'TP':>4} {'FN':>4} "
          f"{'FP':>4} {'TN':>4} {'strict_recall':>14}", flush=True)
    summary = {}
    for arm in [a for a in ("in_si_check", "flash_lite", "no_check") if a in stat]:
        c = stat[arm]
        prec, rec = _prec_rec(c)
        n_scored = c["tp"] + c["fn"]
        strict_rec = c["tp_strict"] / n_scored if n_scored else float("nan")
        summary[arm] = {
            "recall": rec, "precision": prec,
            "tp": c["tp"], "fn": c["fn"], "fp": c["fp"], "tn": c["tn"],
            "strict_recall": strict_rec, "errors": c["errors"],
        }
        print(f"{arm:<14} {rec:>8.3f} {prec:>10.3f} {c['tp']:>4} {c['fn']:>4} "
              f"{c['fp']:>4} {c['tn']:>4} {strict_rec:>14.3f}", flush=True)
        if c["errors"]:
            print(f"  ({arm}: {c['errors']} transport error(s) EXCLUDED from the "
                  f"counts above -- no measurement, not a miss)", flush=True)

    # GO/NO-GO (exit criterion 3): GO iff flash_lite recall >= in_si recall at
    # acceptable precision. Print the comparison; the human verdict goes in the
    # findings doc (the precision bar is a judgment call).
    fl = summary["flash_lite"]
    if "in_si_check" in summary:
        insi = summary["in_si_check"]
        print("\n=== GATE COMPARISON ===", flush=True)
        print(f"flash_lite recall {fl['recall']:.3f} vs in_si recall {insi['recall']:.3f} "
              f"-> flash_lite {'>=' if fl['recall'] >= insi['recall'] else '<'} in_si",
              flush=True)
    print(f"flash_lite precision {fl['precision']:.3f} "
          f"(false positives: {fl['fp']}/{n_clean * args.repeats} clean cases)", flush=True)

    if args.dry_run:
        print("\n[dry-run] scoring harness verified; no live numbers recorded.",
              flush=True)
        return

    # ---- persist ----
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    csv_path = os.path.join(OUT_DIR, f"g1_contradiction_recall_{stamp}.csv")
    meta_path = os.path.join(OUT_DIR, f"g1_contradiction_recall_{stamp}.meta.json")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    # NaN is not valid JSON (RFC 8259) -- json.dump writes the bare token `NaN`,
    # which strict parsers (JS JSON.parse) reject. Undefined precision/recall
    # (e.g. no_check precision, 0/0) is recorded as null, not NaN (fresh-eyes
    # finding 3). math.isnan guards only floats; ints/strs pass through.
    import math

    def _nan_to_none(obj):
        if isinstance(obj, float) and math.isnan(obj):
            return None
        if isinstance(obj, dict):
            return {k: _nan_to_none(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_nan_to_none(v) for v in obj]
        return obj

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(_nan_to_none({
            "bead": "polyglot-pdf-jnjj.5 / polyglot-pdf-u0kcc",
            "stamp": stamp,
            "today_for_date_checks": TODAY,
            "models": {a: m for a, (m, _t) in arms.items()},
            "lite_prompt": args.lite_prompt,
            "repeats": args.repeats,
            "vertex_location": os.environ.get("VERTEX_LOCATION", "global"),
            "corpus": {"total": len(corpus), "contradiction": n_contra, "clean": n_clean,
                       "provenance": "SYNTHETIC injection over real I-90 field structure"},
            "summary": summary,
        }), f, indent=2)
    print(f"\nwrote {csv_path}\nwrote {meta_path}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
