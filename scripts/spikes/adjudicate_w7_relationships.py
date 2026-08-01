#!/usr/bin/env python3
"""Adjudicated W-7 relationship scoring (bd polyglot-pdf-btbi).

The raw `spurious` counter cannot tell a HALLUCINATION from a defensible
reading of the printed form, and the sprint-15 epic's own lesson is that
un-adjudicated "spurious" numbers mislead (several turned out to be gold gaps).
The maintainer adjudicated the dependency-inventory bake's W-7 output field by
field on 2026-08-01; this script encodes those verdicts so every later run is
scored the same way instead of re-litigating them in prose.

Maintainer verdicts (W-7, quoted intent):
  - id_document_expiration_date: the GOLD was wrong (not marked required). The
    extractor caught a real miss; the maintainer fixed the gold. Not counted
    against the extractor.
  - id_document_issued_by, id_document_number: extractor INCORRECT. These are
    ABSOLUTELY required ("no matter what document a person is using, they need
    the issuing agency, number, and expiration date"), so emitting require_if
    downgrades an always-required field to a conditional one. Counted AGAINST
    the extractor (see bd polyglot-pdf-opjo for the fix).
  - itin_part1/2/3 + irsn_part1/2/3 (lines 6f/6g): TECHNICALLY INCORRECT but
    ambiguous-by-construction. The real rule is "exactly one of the ITIN or
    IRSN group is required", which THE SCHEMA CANNOT EXPRESS (bd memory
    no-exactly-one-of-cross-field-constraint). Requiring BOTH groups would
    wrongly force a user to fill both. Counted AGAINST the extractor, but
    reported separately: it is a schema-expressiveness gap, not a model defect,
    and no prompt fix should be judged on it.

Usage:
    python scripts/spikes/adjudicate_w7_relationships.py --draft DRAFT.json
        [--gold form-kits/w7/schema.json] [--json OUT.json]

ASCII only (cp1252 safe).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from typing import Any, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))

_spec = importlib.util.spec_from_file_location(
    "schema_score", os.path.join(_REPO, "scripts", "schema_score.py"))
schema_score = importlib.util.module_from_spec(_spec)
sys.modules["schema_score"] = schema_score
_spec.loader.exec_module(schema_score)


# Field id -> (verdict, note). Verdicts:
#   "extractor-correct-gold-was-wrong" -- not counted against the extractor
#   "extractor-incorrect"              -- counted against (a real defect)
#   "unexpressible"                    -- counted against, reported separately
_W7_VERDICTS: dict[str, tuple[str, str]] = {
    "id_document_expiration_date": (
        "extractor-correct-gold-was-wrong",
        "gold omitted required; maintainer fixed it 2026-08-01"),
    "id_document_issued_by": (
        "extractor-incorrect",
        "absolutely required -- require_if downgrades it (bd opjo)"),
    "id_document_number": (
        "extractor-incorrect",
        "absolutely required -- require_if downgrades it (bd opjo)"),
    **{fid: ("unexpressible",
             "6f/6g: exactly-one-of ITIN|IRSN, inexpressible in the schema")
       for fid in ("itin_part1", "itin_part2", "itin_part3",
                   "irsn_part1", "irsn_part2", "irsn_part3")},
}


def adjudicate(draft_path: str, gold_path: str) -> dict[str, Any]:
    truth = schema_score.load_schema(gold_path)
    draft = schema_score.load_schema(draft_path)
    match = schema_score.match_fields(truth.get("fields", []),
                                      draft.get("fields", []))
    score = schema_score.score(draft_path, gold_path, label="w7-adjudicated")
    conds = score["relationships"]["conditionals"]

    buckets: dict[str, list[dict[str, str]]] = {
        "extractor-correct-gold-was-wrong": [],
        "extractor-incorrect": [],
        "unexpressible": [],
        "unadjudicated": [],
    }
    for t, d in match.pairs:
        for key in ("show_if", "require_if"):
            if d.get(key) and not t.get(key):
                fid = str(t.get("id"))
                verdict, note = _W7_VERDICTS.get(fid, ("unadjudicated", ""))
                buckets[verdict].append({"field": fid, "key": key,
                                         "note": note})

    keys = ("show_if", "require_if")
    total = sum(conds[k]["total"] for k in keys)
    recovered = sum(conds[k]["recovered"] for k in keys)
    trig = sum(conds[k].get("trigger_correct", 0) for k in keys)
    raw_spurious = sum(conds[k].get("spurious", 0) for k in keys)

    # The honest headline: only genuine defects and the unexpressible cases
    # count against precision; a gold error does not.
    charged = len(buckets["extractor-incorrect"]) + len(buckets["unexpressible"])
    uncharged = len(buckets["extractor-correct-gold-was-wrong"])

    return {
        "draft": draft_path,
        "gold": gold_path,
        "field_f1": round(score["field_extraction"]["detection"]["f1"], 1),
        "recall": {"recovered": recovered, "total": total,
                   "pct": round(100.0 * recovered / total, 1) if total else None},
        "trigger_correct": {"count": trig, "total": total,
                            "pct": round(100.0 * trig / total, 1) if total else None},
        "raw_spurious": raw_spurious,
        "charged_spurious": charged,
        "uncharged_gold_errors": uncharged,
        "buckets": buckets,
    }


def render(a: dict[str, Any]) -> str:
    L = ["=" * 66, "ADJUDICATED W-7 RELATIONSHIP SCORE", "=" * 66,
         f"  field F1            {a['field_f1']}",
         f"  conditional recall  {a['recall']['recovered']}/{a['recall']['total']}"
         f"  ({a['recall']['pct']}%)",
         f"  trigger-correct     {a['trigger_correct']['count']}"
         f"/{a['trigger_correct']['total']}  ({a['trigger_correct']['pct']}%)",
         f"  raw spurious        {a['raw_spurious']}",
         f"    charged (defects + unexpressible)  {a['charged_spurious']}",
         f"    NOT charged (gold was wrong)       {a['uncharged_gold_errors']}",
         ""]
    for name, label in (("extractor-incorrect", "EXTRACTOR DEFECTS (bd opjo)"),
                        ("unexpressible", "UNEXPRESSIBLE (schema gap)"),
                        ("extractor-correct-gold-was-wrong",
                         "GOLD WAS WRONG (extractor caught it)"),
                        ("unadjudicated", "UNADJUDICATED (needs a human)")):
        rows = a["buckets"][name]
        if not rows:
            continue
        L.append(f"  {label}:")
        for r in rows:
            L.append(f"    {r['field']:32s} {r['key']:11s} {r['note']}")
        L.append("")
    return "\n".join(L)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--draft", required=True)
    ap.add_argument("--gold",
                    default=os.path.join(_REPO, "form-kits", "w7", "schema.json"))
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args(argv)

    a = adjudicate(args.draft, args.gold)
    print(render(a))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(a, fh, indent=2)
        print(f"[wrote {args.json_out}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
