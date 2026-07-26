#!/usr/bin/env python3
"""Relationship-extraction bake (bd polyglot-pdf-dsbl, sprint 15 R2).

RESEARCH-ONLY harness. Measures which prompt/pipeline change most lifts
relationship recall + trigger-correctness on the auto-pass, tuned on I-90,
generalizing to W-7. NO production file is modified here: contract-clause arms
monkeypatch a RESEARCH COPY of the extractor's SCHEMA_CONTRACT for the duration
of one run and restore it; the winning change is grafted into
scripts/bakeoff/schema_contract.py by R3, not here (maintainer decision
2026-07-25: isolate research from the shipped prompt).

Backend: the local `claude` CLI (claude-opus-4-8), free in-env -- no metered
Vertex spend (Gate-2 estimate in relationship_bake_findings.md). Option-
translation is disabled (irrelevant to relationship scoring, and it needs
Vertex creds the eval env lacks).

Method per arm x form:
  extract (arm's prompt variant) -> deterministic repair -> score with the
  sprint-15 relationship metrics (scripts/schema_score.py) -> record
  show_if/require_if presence + trigger-correct, conditional_behavior presence,
  and trigger-side residue.

Usage:
    python scripts/spikes/relationship_bake.py --arms A0,A1 --forms i-90,w7 \
        --out scripts/spikes/data/relationship_bake_runs.jsonl
    python scripts/spikes/relationship_bake.py --arms A1 --forms w7 --repeats 2

ASCII only (cp1252 safe).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from typing import Any, Callable, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
for p in (_REPO, os.path.join(_REPO, "scripts"),
          os.path.join(_REPO, "scripts", "authoring"),
          os.path.join(_REPO, "scripts", "bakeoff")):
    if p not in sys.path:
        sys.path.insert(0, p)

import arm_llm_native  # noqa: E402
import extract_form  # noqa: E402
import schema_score  # noqa: E402


def _kit(name: str) -> str:
    return os.path.join(_REPO, "form-kits", name)


_FORMS = {
    "i-90": {"pdf": os.path.join(_kit("i-90"), "form.pdf"),
             "gold": os.path.join(_kit("i-90"), "schema.json")},
    "w7": {"pdf": os.path.join(_kit("w7"), "form.pdf"),
           "gold": os.path.join(_kit("w7"), "schema.json")},
}


# --------------------------------------------------------------------------- #
# Arm definitions. Each arm is (contract_patch, second_pass) where either may
# be None. contract_patch is text APPENDED to the RELATIONSHIP section of the
# research copy of SCHEMA_CONTRACT; second_pass names a relationship-only
# refinement call. A0 is the shipped baseline (no patch, no second pass).
# --------------------------------------------------------------------------- #

# A1: the dual-role clause. The W-7 gap (bd dsbl diagnosis) is that a
# conditionally-SHOWN field is often ALSO conditionally REQUIRED by the same
# trigger, and the extractor recovers show_if but omits the parallel require_if.
# This clause states the distinction and the dual-role pattern explicitly.
_DUAL_ROLE_CLAUSE = """

RELATIONSHIP EMPHASIS (read carefully -- a common miss):
- show_if and require_if are DIFFERENT relationships. show_if = the field only
  APPEARS when the condition holds (conditional VISIBILITY). require_if = the
  field MUST be completed when the condition holds (conditional REQUIREDNESS).
- A field is FREQUENTLY BOTH: when the printed instruction says a field both
  appears and must be filled under the same trigger ("if you checked box d,
  complete lines 1-3"), emit BOTH show_if AND require_if with the SAME
  condition on that field. Recovering only show_if and dropping require_if is
  the most common relationship error -- do not make it.
- require_if can also stand alone (a field always visible but required only
  under a condition) and can carry a BROADER condition than show_if (required
  if ANY of several boxes, shown if one). Read the printed text for which
  boxes make the field mandatory."""

# A3: generic dual-role few-shot addendum -- a cross-form-safe example (not
# I-90 / W-7 content) showing a field with show_if AND require_if on the same
# trigger. Appended after the clause so the model sees the shape, not just the
# rule.
_DUAL_ROLE_FEWSHOT = """

EXAMPLE (shape only, not from any target form) -- a field shown AND required by
the same trigger:
  {"id": "spouse_details", "type": "text",
   "show_if":    {"field": "is_married", "operator": "is_checked"},
   "require_if": {"field": "is_married", "operator": "is_checked"}}"""


ARMS: dict[str, dict[str, Any]] = {
    "A0": {"contract_append": "", "second_pass": False,
           "desc": "shipped baseline (control)"},
    "A1": {"contract_append": _DUAL_ROLE_CLAUSE, "second_pass": False,
           "desc": "contract dual-role clause"},
    "A2": {"contract_append": "", "second_pass": True,
           "desc": "relationship-only second pass"},
    "A3": {"contract_append": _DUAL_ROLE_CLAUSE + _DUAL_ROLE_FEWSHOT,
           "second_pass": False, "desc": "dual-role clause + generic few-shot"},
    # A4: the round-1 synthesis -- A2's architecture (relationship-only second
    # pass never perturbs the i-90 first pass) carrying A3's few-shot shape (the
    # biggest w7 require_if lift). No contract change at all.
    "A4": {"contract_append": "", "second_pass": True, "second_pass_fewshot": True,
           "desc": "second pass + dual-role few-shot"},
}


# --------------------------------------------------------------------------- #
# Contract patching (research copy; always restored).
# --------------------------------------------------------------------------- #

def _patch_contract(append_text: str) -> Callable[[], None]:
    """Append `append_text` to arm_llm_native.SCHEMA_CONTRACT for one run and
    return a restore thunk. arm_llm_native holds its own module-level reference
    (build_prompt reads it by name), so patching the attribute on that module is
    sufficient -- but restore in a finally so no arm leaks into the next."""
    original = arm_llm_native.SCHEMA_CONTRACT
    if append_text:
        arm_llm_native.SCHEMA_CONTRACT = original + append_text

    def _restore() -> None:
        arm_llm_native.SCHEMA_CONTRACT = original
    return _restore


# --------------------------------------------------------------------------- #
# Relationship-only second pass (arm A2).
# --------------------------------------------------------------------------- #

_SECOND_PASS_INSTRUCTIONS = """You are refining ONLY the conditional-relationship
keys of an already-extracted form schema. Do NOT add, remove, rename, or
re-type any field, option, or pdf_field_name -- field identity is FROZEN. Your
ONLY job is to correct and complete the relationship keys (show_if, require_if,
conditional_behavior, conditional_logic) on the existing fields, by reading the
form's printed conditional instructions.

Focus:
- A field that both APPEARS and MUST BE COMPLETED under a condition needs BOTH
  show_if AND require_if with that condition. Recovering only show_if is the
  most common error.
- require_if may stand alone or carry a broader condition than show_if.
- Point each condition at the correct trigger field id.

Return the FULL schema JSON with only relationship keys changed."""

# A4: append a concrete dual-role shape example to the second-pass prompt (the
# few-shot that gave A3 its biggest w7 require_if lift), cross-form-safe.
_SECOND_PASS_FEWSHOT = """

EXAMPLE (shape only, not from any target form) -- a field shown AND required by
the same trigger:
  {"id": "spouse_details", "type": "text",
   "show_if":    {"field": "is_married", "operator": "is_checked"},
   "require_if": {"field": "is_married", "operator": "is_checked"}}"""


def _run_second_pass(draft: dict, pdf_path: str, model: str,
                     fewshot: bool = False) -> dict:
    """A relationship-only refinement call over the just-extracted draft. Sends
    the field ids + current relationship keys + the PDF; the model returns the
    schema with only relationship keys adjusted. Field identity is frozen by
    instruction AND re-guarded after (any field id the second pass dropped or
    renamed is restored from the first-pass draft)."""
    from llm_providers import resolve_provider  # noqa: PLC0415

    # A compact view: ids + labels + current relationship keys only (never the
    # full field bodies -- keeps the prompt about relationships).
    rel_keys = ("show_if", "require_if", "conditional_behavior",
                "conditional_logic")
    view = []
    for f in draft.get("fields", []):
        entry = {"id": f.get("id"), "name": f.get("name"),
                 "type": f.get("type")}
        for k in rel_keys:
            if f.get(k):
                entry[k] = f[k]
        view.append(entry)

    prompt = (_SECOND_PASS_INSTRUCTIONS
              + (_SECOND_PASS_FEWSHOT if fewshot else "")
              + "\n\nThe source PDF is at: " + os.path.abspath(pdf_path)
              + " -- READ IT for the printed conditional text.\n\n"
              + "CURRENT FIELDS (id, name, type, current relationship keys):\n"
              + json.dumps(view, ensure_ascii=True, indent=1))

    provider = resolve_provider(model)
    refined, _tok = provider.run(prompt, model, pdf_path)
    refined = arm_llm_native._normalize_schema(refined)

    # Freeze-guard: overlay refined relationship keys onto the ORIGINAL fields
    # by id, so a second pass that dropped/renamed a field cannot corrupt
    # identity. Only the four relationship keys transfer.
    # Key by id, skipping id-less fields entirely: an id-less field cannot be
    # matched back to an original, and collapsing several under a shared "None"
    # key would let one field's refined keys overlay a DIFFERENT original.
    refined_by_id = {str(f.get("id")): f for f in refined.get("fields", [])
                     if isinstance(f, dict) and f.get("id") is not None}
    for f in draft.get("fields", []):
        if f.get("id") is None:
            continue  # unmatchable original; never touched by the refine overlay
        r = refined_by_id.get(str(f.get("id")))
        if not r:
            continue
        for k in rel_keys:
            if r.get(k):
                f[k] = r[k]
            elif k in f and not r.get(k):
                # second pass deliberately cleared it -> honor a clear only when
                # the field was matched (avoid a dropped-field false clear).
                f.pop(k, None)
    return draft


# --------------------------------------------------------------------------- #
# One arm x form run.
# --------------------------------------------------------------------------- #

def _rel_summary(score: dict) -> dict:
    conds = score["relationships"]["conditionals"]

    def combined(keys: tuple[str, ...], field: str) -> Any:
        return sum(conds[k].get(field, 0) for k in keys if k in conds)

    sr_keys = ("show_if", "require_if")
    return {
        "field_f1": round(score["field_extraction"]["detection"]["f1"], 1),
        "show_if": {k: conds["show_if"][k]
                    for k in ("recovered", "total", "trigger_correct")},
        "require_if": {k: conds["require_if"][k]
                       for k in ("recovered", "total", "trigger_correct")},
        "sh_rq_present": f"{combined(sr_keys, 'recovered')}/"
                         f"{combined(sr_keys, 'total')}",
        "sh_rq_trigger_correct": f"{combined(sr_keys, 'trigger_correct')}/"
                                 f"{combined(sr_keys, 'total')}",
        "conditional_behavior": {
            k: conds["conditional_behavior"][k]
            for k in ("recovered", "total")},
        "trigger_side_residue":
            score["relationships"]["trigger_side_residue"]["total"],
    }


def run_arm(arm: str, form: str, model: str, keep_draft: Optional[str]) -> dict:
    spec = ARMS[arm]
    f = _FORMS[form]
    restore = _patch_contract(spec["contract_append"])
    try:
        out = (keep_draft if keep_draft
               else tempfile.mkstemp(suffix=f"_{arm}_{form}.json")[1])
        draft = extract_form.extract(
            f["pdf"], out, model=model, translate_options=False,
            group_candidates=True)
        if spec["second_pass"]:
            draft = _run_second_pass(draft, f["pdf"], model,
                                     fewshot=spec.get("second_pass_fewshot", False))
            with open(out, "w", encoding="utf-8") as fh:
                json.dump(draft, fh, indent=2)
    finally:
        restore()

    score = schema_score.score(out, f["gold"], label=f"{arm}:{form}")
    return {"arm": arm, "form": form, "desc": spec["desc"],
            "draft": out, "summary": _rel_summary(score)}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arms", default="A0,A1,A2,A3")
    ap.add_argument("--forms", default="i-90,w7")
    ap.add_argument("--model", default="claude-opus-4-8")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--round", type=int, default=1,
                    help="round tag written into each JSONL row -- distinguishes "
                         "separate invocations (rep is per-invocation only)")
    ap.add_argument("--out", default=None,
                    help="append each run as a JSONL row")
    args = ap.parse_args(argv)

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    forms = [f.strip() for f in args.forms.split(",") if f.strip()]
    for a in arms:
        if a not in ARMS:
            ap.error(f"unknown arm {a!r} (known: {', '.join(ARMS)})")
    for f in forms:
        if f not in _FORMS:
            ap.error(f"unknown form {f!r} (known: {', '.join(_FORMS)})")

    rows = []
    for rep in range(args.repeats):
        for arm in arms:
            for form in forms:
                label = f"{arm}/{form}" + (f" rep{rep}" if args.repeats > 1
                                           else "")
                print(f"[run] {label} ({ARMS[arm]['desc']}) ...", flush=True)
                try:
                    row = run_arm(arm, form, args.model, keep_draft=None)
                    row["round"] = args.round
                    row["rep"] = rep
                    rows.append(row)
                    s = row["summary"]
                    print(f"  fieldF1 {s['field_f1']}  "
                          f"sh/rq present {s['sh_rq_present']}  "
                          f"trig-correct {s['sh_rq_trigger_correct']}  "
                          f"cond_behavior {s['conditional_behavior']['recovered']}"
                          f"/{s['conditional_behavior']['total']}  "
                          f"residue {s['trigger_side_residue']}", flush=True)
                    if args.out:
                        os.makedirs(os.path.dirname(os.path.abspath(args.out)),
                                    exist_ok=True)
                        with open(args.out, "a", encoding="utf-8") as fh:
                            fh.write(json.dumps(row) + "\n")
                except Exception as exc:  # noqa: BLE001 -- research harness: log + continue
                    print(f"  FAILED: {type(exc).__name__}: {exc}", flush=True)
                    rows.append({"arm": arm, "form": form, "round": args.round,
                                 "rep": rep,
                                 "error": f"{type(exc).__name__}: {exc}"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
