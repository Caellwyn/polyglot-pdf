#!/usr/bin/env python3
"""Dependency-inventory bake (bd polyglot-pdf-btbi).

RESEARCH-ONLY harness. Tests the maintainer's hypothesis (2026-07-26): the
extractor's relationship failure is a SEARCH-COVERAGE problem, not a reasoning
problem, so an intermediate structured-reasoning step -- inventory the
conditional dependencies FIRST, then emit the schema using that inventory --
should lift recall.

Why this is not the already-falsified second pass: sprint-15's A2/A4 arms ran a
REFINEMENT pass (fix relationships AFTER extraction) and lost most of the gain.
This is a DERIVATION scaffold inside the SAME single call (maintainer decision
2026-08-01): the model must fill a dependency inventory in its output BEFORE
the fields array, so the inventory conditions the extraction rather than
patching it.

The contract demands one JSON object and nothing else, so the inventory is a
top-level JSON key (`_dependency_inventory`), not prose. FormSchema ignores
extra keys, and this harness pops it before scoring -- it never reaches a kit.

Baseline this measures against (corrected W-7 gold, bd fjxe / PR #519, scored
2026-08-01): field F1 99.1; show_if 10/19 present (10 trigger-correct);
require_if 0/13; combined 10/32 = 31.2% presence AND trigger-correct;
spurious 0. Precision-perfect, recall-poor.

Tune set: w7 (the target) + i-90 (no-regression guard). NOTE: i-90 is the only
OTHER hand-verified kit; f1040 is explicitly NOT trusted as ground truth
(bd memory w7-f1040-gold-not-hand-verified), so there is no clean held-out form
right now -- any w7 gain must be read as tuned-on-target until a fresh verified
kit exists. Stated, not hidden.

Backend: local `claude` CLI (claude-opus-4-8), free in-env -- no metered spend.

Usage:
    python scripts/spikes/dependency_inventory_bake.py --arms B0,B1 --forms w7
    python scripts/spikes/dependency_inventory_bake.py --arms B1 --forms w7,i-90 \
        --repeats 2 --out scripts/spikes/data/dependency_inventory_runs.jsonl

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
for _p in (_REPO, os.path.join(_REPO, "scripts"),
           os.path.join(_REPO, "scripts", "authoring"),
           os.path.join(_REPO, "scripts", "bakeoff")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import arm_llm_native  # noqa: E402
import extract_form  # noqa: E402
import schema_score  # noqa: E402


def _kit(name: str) -> str:
    return os.path.join(_REPO, "form-kits", name)


_FORMS = {
    "w7": {"pdf": os.path.join(_kit("w7"), "form.pdf"),
           "gold": os.path.join(_kit("w7"), "schema.json")},
    "i-90": {"pdf": os.path.join(_kit("i-90"), "form.pdf"),
             "gold": os.path.join(_kit("i-90"), "schema.json")},
}


# --------------------------------------------------------------------------- #
# The scaffold text. Appended to the contract for the inventory arms.
# --------------------------------------------------------------------------- #

# B1: inventory-first. The model must enumerate every conditional dependency it
# can find in the printed text BEFORE emitting fields, then use its own
# inventory when filling show_if/require_if. The enumeration is the point: the
# measured failure is that the model only LOOKS FOR about a third of the
# dependencies a form actually states.
_INVENTORY_SCAFFOLD = """

DEPENDENCY INVENTORY (do this FIRST -- it is the highest-value part of this task):
Before you emit the "fields" array, emit a top-level key
"_dependency_inventory": a list of EVERY conditional dependency the form's
PRINTED text states. Work through the form page by page and hunt specifically
for sentences of these shapes (they are the ones most often missed):
  - "If you check(ed) box X, complete/enter/attach ..."
  - "Complete this line ONLY if ..." / "Skip to line N if ..."
  - "Required if ..." / "You must complete ... if ..."
  - "If yes, ..." / "If no, go to ..."
  - "Applicants selecting reason X must also ..."
  - a parenthetical on a checkbox naming other lines ("(see line 6d)")
  - a line whose label itself is conditional ("If applicable, ...")
One entry per dependency, in this shape:
  {{"printed_text": "<the sentence/label, quoted from the form>",
    "trigger_field": "<the id you will give the controlling field>",
    "trigger_condition": "<e.g. checked / equals yes / any of a,f>",
    "affected_fields": ["<ids of the fields it governs>"],
    "effect": "shows" | "requires" | "shows_and_requires"}}

Rules for the inventory:
- Be EXHAUSTIVE. A typical 2-page government form states 20-40 dependencies.
  If your inventory has under ten entries on such a form, you have not finished
  reading -- go back through the printed instructions and the line labels.
- Include a dependency even when the affected field is obvious or the effect is
  small. Under-listing is the failure this step exists to prevent.
- "requires" and "shows_and_requires" are as important as "shows". A line a
  checkbox makes MANDATORY is a dependency even if the line is always visible.

THEN emit "fields". Every inventory entry MUST be reflected in the fields you
emit: an entry with effect "shows" puts show_if on each affected field,
"requires" puts require_if, and "shows_and_requires" puts BOTH (same
condition). Cross-check your fields against your inventory before you finish:
an inventory entry with no corresponding show_if/require_if is a bug in your
output."""


ARMS: dict[str, dict[str, Any]] = {
    "B0": {"contract_append": "", "desc": "shipped baseline (control)"},
    "B1": {"contract_append": _INVENTORY_SCAFFOLD,
           "desc": "dependency-inventory scaffold (inventory -> fields)"},
}


def _patch_contract(append_text: str) -> Callable[[], None]:
    """Append to arm_llm_native's SCHEMA_CONTRACT for one run; always restore.
    Research-only: the shipped contract file is never modified (the sprint-15
    isolation rule -- graft a winner in a separate ship bead)."""
    original = arm_llm_native.SCHEMA_CONTRACT
    if append_text:
        arm_llm_native.SCHEMA_CONTRACT = original + append_text

    def _restore() -> None:
        arm_llm_native.SCHEMA_CONTRACT = original
    return _restore


def _rel_summary(score: dict, inventory: Optional[list]) -> dict:
    conds = score["relationships"]["conditionals"]
    keys = ("show_if", "require_if")

    def _sum(field: str) -> int:
        return sum(conds[k].get(field, 0) for k in keys if k in conds)

    tot = _sum("total")
    out = {
        "field_f1": round(score["field_extraction"]["detection"]["f1"], 1),
        "show_if": {k: conds["show_if"][k]
                    for k in ("recovered", "total", "trigger_correct",
                              "spurious")},
        "require_if": {k: conds["require_if"][k]
                       for k in ("recovered", "total", "trigger_correct",
                                 "spurious")},
        "combined_present": f"{_sum('recovered')}/{tot}",
        "combined_present_pct": round(100.0 * _sum("recovered") / tot, 1) if tot else None,
        "combined_trigger_correct": f"{_sum('trigger_correct')}/{tot}",
        "combined_trigger_correct_pct": round(
            100.0 * _sum("trigger_correct") / tot, 1) if tot else None,
        "spurious_total": _sum("spurious"),
        "residue": score["relationships"]["trigger_side_residue"]["total"],
    }
    # The inventory itself is a measurement: did the scaffold make the model
    # LOOK for more dependencies (the hypothesis), separately from whether it
    # then wrote them down correctly?
    if inventory is not None:
        effects: dict[str, int] = {}
        for e in inventory:
            if isinstance(e, dict):
                effects[str(e.get("effect"))] = effects.get(str(e.get("effect")), 0) + 1
        out["inventory_entries"] = len(inventory)
        out["inventory_effects"] = effects
    return out


def run_arm(arm: str, form: str, model: str,
            draft_dir: Optional[str] = None, tag: str = "") -> dict:
    spec = ARMS[arm]
    f = _FORMS[form]
    restore = _patch_contract(spec["contract_append"])
    inventory = None
    try:
        if draft_dir:
            # Keep drafts somewhere durable: the committed JSONL used to point
            # at OS temp paths that vanish, so an individual run could never be
            # re-adjudicated afterwards (fresh-eyes gap, 2026-08-01).
            os.makedirs(draft_dir, exist_ok=True)
            out = os.path.join(draft_dir, f"{form}_{arm}{tag}.json")
        else:
            out = tempfile.mkstemp(suffix=f"_{arm}_{form}.json")[1]
        draft = extract_form.extract(f["pdf"], out, model=model,
                                     translate_options=False)
        # Capture + strip the scaffold key: it is reasoning scaffolding, never
        # part of a kit. (FormSchema ignores extras, so this is belt-and-braces.)
        if isinstance(draft.get("_dependency_inventory"), list):
            inventory = draft.pop("_dependency_inventory")
            with open(out, "w", encoding="utf-8") as fh:
                json.dump(draft, fh, indent=2)
    finally:
        restore()

    score = schema_score.score(out, f["gold"], label=f"{arm}:{form}")
    return {"arm": arm, "form": form, "desc": spec["desc"], "draft": out,
            "summary": _rel_summary(score, inventory),
            "inventory": inventory}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arms", default="B0,B1")
    ap.add_argument("--forms", default="w7")
    ap.add_argument("--model", default="claude-opus-4-8")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--round", type=int, default=1,
                    help="round tag in each JSONL row (rep is per-invocation)")
    ap.add_argument("--out", default=None, help="append runs as JSONL")
    ap.add_argument("--draft-dir", default=None,
                    help="keep each run's draft schema here (recommended: the "
                         "JSONL's draft paths stay resolvable for later "
                         "re-adjudication instead of pointing at OS temp)")
    args = ap.parse_args(argv)

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    forms = [f.strip() for f in args.forms.split(",") if f.strip()]
    for a in arms:
        if a not in ARMS:
            ap.error(f"unknown arm {a!r} (known: {', '.join(ARMS)})")
    for f in forms:
        if f not in _FORMS:
            ap.error(f"unknown form {f!r} (known: {', '.join(_FORMS)})")

    for rep in range(args.repeats):
        for arm in arms:
            for form in forms:
                print(f"[run] {arm}/{form} rep{rep} ({ARMS[arm]['desc']}) ...",
                      flush=True)
                try:
                    row = run_arm(arm, form, args.model,
                                  draft_dir=args.draft_dir,
                                  tag=f"_r{args.round}rep{rep}")
                    row["round"] = args.round
                    row["rep"] = rep
                    s = row["summary"]
                    inv = (f"  inventory {s['inventory_entries']} "
                           f"{s['inventory_effects']}"
                           if "inventory_entries" in s else "")
                    print(f"  F1 {s['field_f1']}  present "
                          f"{s['combined_present']} ({s['combined_present_pct']}%)"
                          f"  trig-correct {s['combined_trigger_correct']}"
                          f"  spurious {s['spurious_total']}{inv}", flush=True)
                    if args.out:
                        os.makedirs(os.path.dirname(os.path.abspath(args.out)),
                                    exist_ok=True)
                        with open(args.out, "a", encoding="utf-8") as fh:
                            fh.write(json.dumps(row) + "\n")
                except Exception as exc:  # noqa: BLE001 -- research harness
                    print(f"  FAILED: {type(exc).__name__}: {exc}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
