"""Secretary Gate 1 RECALL probe -- can flash-lite answer prose form queries?

bd polyglot-pdf-jnjj.26. Renders the I-90 secretary context (secretary_context.py)
from the shared fixture (secretary_recall_corpus.FIELD_VALUES / SHOWN_MAP), asks
gemini-2.5-flash-lite each prose query in the stratified battery
(secretary_recall_corpus.build_corpus), and characterizes the answers:

  - GROUNDING (deterministic): does the answer's `sourced_from` field-id trace
    match the case's expected_field_ids? precision/recall on the id SET, per case,
    plus a STRICT exact-set flag.
  - CONFIDENT-WRONG (the headline legal-harm metric): the answer cites a field NOT
    in expected AND asserts a value (did not hedge/ask). Surfaced per tier.
  - PROSE QUALITY (LLM judge, Step 4): a Sonnet judge subprocess rates synthesis
    correctness, disambiguation behavior, and hallucination per case.

Verdict stance (maintainer, 2026-06-18): CHARACTERIZE, do NOT auto GO/KILL. The
script prints per-tier numbers and writes the artifacts; the human reads them. The
existing human-verification net (principal voices every answer back; user confirms;
UI focus indicator) is the safety mechanism.

PII: the corpus is SYNTHETIC (fabricated values), so the CSV/JSON of answers is an
acceptable measurement artifact (mirrors g1). The probe still logs model name /
counts / scores to stdout, never frames real PHI. In production the rendered
context + answers are PHI and must not be logged.

Usage:
    GEMINI_API_KEY=... PYTHONPATH=. python backend/scripts/probe_secretary_recall.py
    # offline scoring check (perfect-oracle stub, no API calls, no judge):
    GEMINI_API_KEY=... PYTHONPATH=. python backend/scripts/probe_secretary_recall.py --dry-run
    # skip the Sonnet judge (grounding scores only):
    ... python backend/scripts/probe_secretary_recall.py --no-judge

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import datetime
import json
import os
import shutil
import subprocess
import sys
from collections import defaultdict

from google import genai
from google.genai import types

# Allow running as a module from repo root (PYTHONPATH=.).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.scripts.secretary_context import (  # noqa: E402
    render_secretary_context,
    estimate_tokens,
)
from backend.scripts.secretary_recall_corpus import (  # noqa: E402
    build_corpus,
    FIELD_VALUES,
    SHOWN_MAP,
)

MODEL_SECRETARY = "gemini-2.5-flash-lite"
JUDGE_MODEL = "claude-sonnet-4-6"

OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scripts", "spikes", "data",
)

TIERS = ["easy", "aliasing", "ambiguous", "synthesis", "distant", "applicability"]


# --------------------------------------------------------------------------- #
# Secretary prompt -- the "show your work" structure.
# --------------------------------------------------------------------------- #

SECRETARY_PROMPT = (
    "You are the SECRETARY for a USCIS I-90 immigration form-filling assistant. A "
    "colleague (the voice assistant talking to the applicant) asks you prose "
    "questions about the form. You hold the form's fields and the applicant's "
    "current answers below.\n\n"
    "Each field shows: its id, spoken name, type, current value (or <empty>), and "
    "whether it is shown (applicable) to this applicant. A field can be shown but "
    "<empty> (applicable, not answered yet) OR not shown (not applicable to this "
    "applicant) -- treat these as DIFFERENT.\n\n"
    "Answer the colleague's question. Work in this order:\n"
    "1. Find ALL fields relevant to the question (there may be several).\n"
    "2. Copy their current values.\n"
    "3. Answer in natural, brief prose using ONLY those values. If a relevant "
    "field is <empty> but applicable, say it has not been answered yet. If it is "
    "not applicable to this applicant, say so. If the question is genuinely "
    "ambiguous across several fields, either answer for all of them and name each, "
    "or ask a short clarifying question. NEVER invent a value that is not shown.\n\n"
    "Return JSON ONLY, no other text:\n"
    '{"answer": "<your prose answer>", "sourced_from": ["<field_id>", ...]}\n'
    "Put in sourced_from the exact field ids you used to answer (the fields whose "
    "values your answer is grounded in). Use ids exactly as shown.\n\n"
    "FORM:\n{context}\n\n"
    "QUESTION: {query}\n"
)


def _client() -> genai.Client:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("NO KEY in env GEMINI_API_KEY", flush=True)
        sys.exit(2)
    return genai.Client(api_key=key)


async def _ask_secretary(client, context: str, query: str) -> dict:
    """One flash-lite call for one query. Returns {answer, sourced_from} or a
    fail-soft empty with a parse/error marker."""
    prompt = SECRETARY_PROMPT.replace("{context}", context).replace("{query}", query)
    try:
        resp = await client.aio.models.generate_content(
            model=MODEL_SECRETARY,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        raw = resp.text or ""
        v = json.loads(raw)
        answer = v.get("answer", "")
        sourced = v.get("sourced_from", [])
        if not isinstance(sourced, list):
            return {"answer": answer, "sourced_from": [], "_parse": "bad_sourced_type"}
        return {"answer": str(answer), "sourced_from": [str(x) for x in sourced]}
    except json.JSONDecodeError:
        return {"answer": "", "sourced_from": [], "_parse": "json_error"}
    except Exception as exc:  # noqa: BLE001
        return {"answer": "", "sourced_from": [], "_error": type(exc).__name__}


# --------------------------------------------------------------------------- #
# Deterministic grounding scoring.
# --------------------------------------------------------------------------- #

def _score_grounding(expected: list, sourced: list) -> dict:
    """Set precision/recall of cited fields vs expected, plus a strict-match flag.

    expected: ground-truth field-id list (the candidate set).
    sourced:  field ids the answer cited.
    """
    exp = set(expected)
    got = set(sourced)
    tp = len(exp & got)
    prec = tp / len(got) if got else (1.0 if not exp else 0.0)
    rec = tp / len(exp) if exp else (1.0 if not got else 0.0)
    strict = exp == got
    # "hit" = cited at least one correct field (the minimal retrieval success).
    hit = tp > 0 if exp else (len(got) == 0)
    # "wrong-cite" = cited a field NOT in expected (the confident-wrong precondition).
    wrong_cite = len(got - exp) > 0
    return {
        "precision": prec, "recall": rec, "strict": strict, "hit": hit,
        "tp": tp, "n_expected": len(exp), "n_sourced": len(got),
        "wrong_cite": wrong_cite,
    }


def _asserts_value(answer: str) -> bool:
    """Heuristic: does the prose ASSERT a value rather than hedge/ask? Used with
    wrong_cite to flag confident-wrong. Conservative: treats a clarifying question
    or an explicit not-applicable/not-answered as NOT a confident assertion."""
    a = (answer or "").strip().lower()
    if not a:
        return False
    hedges = (
        "?", "could you", "do you mean", "did you mean", "which ", "not applicable",
        "n/a", "not answered", "hasn't been answered", "has not been answered",
        "no value", "not provided", "not been provided", "i'm not sure",
        "unclear", "cannot find", "could not find", "don't have", "do not have",
    )
    return not any(h in a for h in hedges)


# --------------------------------------------------------------------------- #
# Sonnet judge (Step 4) -- CLI subprocess, reproducible from the script.
# --------------------------------------------------------------------------- #

JUDGE_PROMPT = (
    "You are grading a 'secretary' assistant's answer to a question about a "
    "filled USCIS I-90 form. You are given the QUESTION, the expected field ids "
    "the answer should be grounded in, the secretary's ANSWER, and the field ids "
    "the secretary said it used. Judge ONLY these three things and return JSON.\n\n"
    "- synthesis_ok (bool): if the question needs values from several fields, did "
    "the answer gather the right values and attribute each correctly? (true if the "
    "question is single-field and answered correctly).\n"
    "- disambig_ok (bool): if the question is genuinely ambiguous across several "
    "fields, did the answer either cover all candidates and name them, OR ask a "
    "sensible clarifying question -- rather than silently guess one? (true if the "
    "question is not ambiguous).\n"
    "- hallucinated (bool): did the answer assert any value or fact NOT supported "
    "by the expected fields (made something up)? true = it hallucinated.\n"
    "- note (string): one short sentence on the most important issue, or 'ok'.\n\n"
    "Return JSON ONLY:\n"
    '{"synthesis_ok": <bool>, "disambig_ok": <bool>, "hallucinated": <bool>, '
    '"note": "<short>"}\n\n'
    "QUESTION: {query}\n"
    "EXPECTED_FIELD_IDS: {expected}\n"
    "SECRETARY_ANSWER: {answer}\n"
    "SECRETARY_SOURCED_FROM: {sourced}\n"
)


def _judge_case(case, result: dict, timeout_s: int = 180) -> dict:
    """Run the Sonnet judge on one (query, answer) via the claude CLI."""
    exe = shutil.which("claude") or "claude"
    prompt = (JUDGE_PROMPT
              .replace("{query}", case.query)
              .replace("{expected}", json.dumps(case.expected_field_ids))
              .replace("{answer}", result.get("answer", ""))
              .replace("{sourced}", json.dumps(result.get("sourced_from", []))))
    cmd = [exe, "-p", "--model", JUDGE_MODEL, "--output-format", "json"]
    try:
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                              encoding="utf-8", timeout=timeout_s)
        if proc.returncode != 0:
            return {"_judge_error": "cli_exit_%d" % proc.returncode}
        env = json.loads(proc.stdout)
        if env.get("is_error"):
            return {"_judge_error": "cli_is_error"}
        verdict = _extract_json_obj(env.get("result", ""))
        if verdict is None:
            return {"_judge_error": "no_json"}
        return {
            "synthesis_ok": bool(verdict.get("synthesis_ok", False)),
            "disambig_ok": bool(verdict.get("disambig_ok", False)),
            "hallucinated": bool(verdict.get("hallucinated", False)),
            "note": str(verdict.get("note", "")),
        }
    except subprocess.TimeoutExpired:
        return {"_judge_error": "timeout"}
    except Exception as exc:  # noqa: BLE001
        return {"_judge_error": type(exc).__name__}


def _extract_json_obj(text: str):
    """Pull the first {...} JSON object out of a possibly-noisy string."""
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


# --------------------------------------------------------------------------- #
# Main.
# --------------------------------------------------------------------------- #

async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Perfect-oracle stub (no API calls, no judge).")
    ap.add_argument("--no-judge", action="store_true",
                    help="Skip the Sonnet prose judge (grounding scores only).")
    ap.add_argument("--limit", type=int, default=0, help="Cap cases (debug).")
    args = ap.parse_args()

    corpus = build_corpus()
    if args.limit:
        corpus = corpus[: args.limit]

    # Schema + rendered context (one shared render for all queries).
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    schema = json.load(open(os.path.join(root, "form-kits", "i-90", "schema.json"),
                            encoding="utf-8"))
    context = render_secretary_context(schema, FIELD_VALUES, SHOWN_MAP)
    ctx_tokens = estimate_tokens(context)
    print("rendered secretary context: ~%d tokens, %d cases" % (ctx_tokens, len(corpus)),
          flush=True)

    client = None if args.dry_run else _client()

    rows = []
    # per-tier accumulators
    stat = {t: defaultdict(float) for t in TIERS}

    for ci, case in enumerate(corpus):
        if args.dry_run:
            # Perfect oracle: cite exactly the expected fields, assert a value.
            result = {"answer": "stub answer with a value", "sourced_from": list(case.expected_field_ids)}
        else:
            result = await _ask_secretary(client, context, case.query)

        g = _score_grounding(case.expected_field_ids, result.get("sourced_from", []))
        asserts = _asserts_value(result.get("answer", ""))
        confident_wrong = g["wrong_cite"] and asserts

        # judge
        judge = {}
        if not args.dry_run and not args.no_judge:
            judge = _judge_case(case, result)

        s = stat[case.tier]
        s["n"] += 1
        s["precision"] += g["precision"]
        s["recall"] += g["recall"]
        s["strict"] += 1 if g["strict"] else 0
        s["hit"] += 1 if g["hit"] else 0
        s["confident_wrong"] += 1 if confident_wrong else 0
        if judge and "_judge_error" not in judge:
            s["judged"] += 1
            s["synthesis_ok"] += 1 if judge.get("synthesis_ok") else 0
            s["disambig_ok"] += 1 if judge.get("disambig_ok") else 0
            s["hallucinated"] += 1 if judge.get("hallucinated") else 0

        rows.append({
            "case_id": case.case_id,
            "tier": case.tier,
            "query": case.query,
            "answer": result.get("answer", ""),
            "sourced_from": ";".join(result.get("sourced_from", [])),
            "expected": ";".join(case.expected_field_ids),
            "precision": round(g["precision"], 3),
            "recall": round(g["recall"], 3),
            "strict": int(g["strict"]),
            "hit": int(g["hit"]),
            "confident_wrong": int(confident_wrong),
            "synthesis_ok": int(judge.get("synthesis_ok")) if judge.get("synthesis_ok") is not None and "_judge_error" not in judge else "",
            "disambig_ok": int(judge.get("disambig_ok")) if judge.get("disambig_ok") is not None and "_judge_error" not in judge else "",
            "hallucinated": int(judge.get("hallucinated")) if judge.get("hallucinated") is not None and "_judge_error" not in judge else "",
            "judge_note": judge.get("note", judge.get("_judge_error", "")),
            "parse_err": result.get("_parse", result.get("_error", "")),
        })
        print("  [%d/%d] %-26s (%s) hit=%d cw=%d" % (
            ci + 1, len(corpus), case.case_id, case.tier, g["hit"],
            int(confident_wrong)), flush=True)

    # ---- per-tier summary ----
    print("\n=== PER-TIER CHARACTERIZATION (means; counts where noted) ===", flush=True)
    hdr = ("%-14s %4s %6s %6s %7s %5s %10s %9s %9s %8s" %
           ("tier", "n", "prec", "rec", "strict", "hit", "confid_wrong",
            "synth_ok", "disamb_ok", "halluc"))
    print(hdr, flush=True)
    summary = {}
    for t in TIERS:
        s = stat[t]
        n = int(s["n"]) or 1
        judged = int(s["judged"]) or 0
        jd = judged or 1
        summary[t] = {
            "n": int(s["n"]),
            "precision": round(s["precision"] / n, 3),
            "recall": round(s["recall"] / n, 3),
            "strict_rate": round(s["strict"] / n, 3),
            "hit_rate": round(s["hit"] / n, 3),
            "confident_wrong": int(s["confident_wrong"]),
            "judged": judged,
            "synthesis_ok_rate": round(s["synthesis_ok"] / jd, 3) if judged else None,
            "disambig_ok_rate": round(s["disambig_ok"] / jd, 3) if judged else None,
            "hallucinated": int(s["hallucinated"]) if judged else None,
        }
        print("%-14s %4d %6.3f %6.3f %7.3f %5.3f %10d %9s %9s %8s" % (
            t, int(s["n"]), summary[t]["precision"], summary[t]["recall"],
            summary[t]["strict_rate"], summary[t]["hit_rate"],
            summary[t]["confident_wrong"],
            "-" if not judged else "%.3f" % summary[t]["synthesis_ok_rate"],
            "-" if not judged else "%.3f" % summary[t]["disambig_ok_rate"],
            "-" if not judged else str(summary[t]["hallucinated"]),
        ), flush=True)

    total_cw = sum(int(stat[t]["confident_wrong"]) for t in TIERS)
    print("\nHEADLINE -- total confident-wrong cases: %d / %d" % (total_cw, len(corpus)),
          flush=True)

    if args.dry_run:
        print("\n[dry-run] scoring + report assembly verified; no live numbers recorded.",
              flush=True)
        return

    # ---- persist ----
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    csv_path = os.path.join(OUT_DIR, "secretary_recall_%s.csv" % stamp)
    meta_path = os.path.join(OUT_DIR, "secretary_recall_%s.meta.json" % stamp)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "bead": "polyglot-pdf-jnjj.26",
            "stamp": stamp,
            "secretary_model": MODEL_SECRETARY,
            "judge_model": None if args.no_judge else JUDGE_MODEL,
            "context_format": "grouped-by-section (single, feasibility-first)",
            "context_tokens_est": ctx_tokens,
            "corpus": {"total": len(corpus),
                       "provenance": "SYNTHETIC; recall is an UPPER BOUND (clean "
                                     "values + on-distribution queries)"},
            "per_tier": summary,
            "total_confident_wrong": total_cw,
        }, f, indent=2)
    print("\nwrote %s\nwrote %s" % (csv_path, meta_path), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
