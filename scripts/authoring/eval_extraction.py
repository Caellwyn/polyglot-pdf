#!/usr/bin/env python3
"""One-command extraction evaluation across the benchmark forms (bd h76m.6, P2.2).

Runs the pipeline  [extract ->] repair -> lint -> roundtrip -> score  over each
benchmark form and prints ONE summary table, so extractor changes (P5.x) are
judged against every form at once instead of the one being tuned.

MANUAL command -- never per-PR CI: full --extract on f1040 alone is >6 minutes
plus paid model tokens. Without --extract it evaluates EXISTING schemas (a
draft dir you point it at, or each kit's gold as the baseline row), which is
fast, free, and what the tests pin.

Benchmark set (see _FORMS): w7, w7-2, f1040 (kits with gold schemas) + the
HELD-OUT w9 (form-kits/w9-heldout/NOTE.md -- no gold on purpose; it only
produces a row under --extract or --draft-dir).

Structural assertions (the re-extraction regression anchor): per-form widget
groups that must survive extraction with their identity intact -- every listed
widget claimed exactly once, with distinct claiming option values. W-7's
"reason for applying" boxes c1_2[0]..c1_9[0] are the canonical case (the live
failure that triggered the epic collapsed them to one field whose 8 options
all had value "1" and no widget mapping). The check is modeling-agnostic: it
passes whether the boxes arrive as one consolidated group (the v2 target) or
as N standalone checkboxes (today's gold), and reports which via the
`consolidated` flag -- what it cannot do is silently drop or de-identify a box.

The repair step imports scripts/authoring/schema_repair.py when it exists
(P5.2 ships it); until then the step reports "-" and the pipeline continues.

Usage:
    python scripts/authoring/eval_extraction.py                    # gold baseline rows
    python scripts/authoring/eval_extraction.py --draft-dir DIR    # score drafts in DIR/<form>.json
    python scripts/authoring/eval_extraction.py --form w7 --draft PATH.json
    python scripts/authoring/eval_extraction.py --extract [--model M]  # full pipeline (slow, paid)
    ... [--json OUT.json]

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
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.join(_REPO, "scripts"))
sys.path.insert(0, os.path.join(_REPO, "scripts", "bakeoff"))

import roundtrip_fill  # noqa: E402
import schema_score  # noqa: E402
from backend.services.schema_lint import lint_schema  # noqa: E402


def _kit(name: str) -> str:
    return os.path.join(_REPO, "form-kits", name)


# The benchmark manifest. `gold` None = held out (no truth schema exists, on
# purpose -- see form-kits/w9-heldout/NOTE.md). `widgets` = the structural
# assertion's widget-leaf group for this form.
_FORMS: list[dict[str, Any]] = [
    {
        "name": "w7",
        "pdf": os.path.join(_kit("w7"), "form.pdf"),
        "gold": os.path.join(_kit("w7"), "schema.json"),
        "widgets": [f"c1_{i}[0]" for i in range(2, 10)],  # reason boxes a-h
    },
    {
        "name": "w7-2",
        "pdf": os.path.join(_kit("w7-2"), "form.pdf"),
        "gold": os.path.join(_kit("w7-2"), "schema.json"),
        "widgets": [f"c1_{i}[0]" for i in range(2, 10)],
    },
    {
        "name": "f1040",
        "pdf": os.path.join(_kit("f1040"), "form.pdf"),
        "gold": os.path.join(_kit("f1040"), "schema.json"),
        # No pinned group YET: the natural anchor (filing status) is exactly
        # the shipped corruption (duplicate option values, bd h76m.5) AND its
        # widget names repeat across PDF pages (c1_8[0]/c1_8[1] appear twice),
        # so a leaf-keyed coverage assertion is ambiguous by construction.
        # Pin it at P6.1 when f1040 is re-extracted with full-path identity.
        "widgets": None,
    },
    {
        "name": "w9-heldout",
        "pdf": os.path.join(_kit("w9-heldout"), "form.pdf"),
        "gold": None,
        # Line 3a federal tax classification (7 radio-kid boxes) + line 3b.
        "widgets": [f"c1_1[{i}]" for i in range(7)] + ["c1_2[0]"],
    },
]


# --------------------------------------------------------------------------- #
# Structural assertion: widget-coverage with distinct identity.
# --------------------------------------------------------------------------- #

def _leaf(name: Optional[str]) -> Optional[str]:
    if not isinstance(name, str) or not name:
        return None
    return name.split(".")[-1]


def check_widget_coverage(schema: dict, widget_leaves: list[str]) -> dict:
    """Every listed widget leaf claimed exactly once, and every claimed box
    ADDRESSABLE the way the filler actually selects it. Modeling-agnostic --
    see module doc. Three rules (semantics settled across two Opus-fallback
    review rounds on PR #304):

    1. Coverage: each pinned widget claimed by exactly one field (via a
       claiming option or a field-level pdf_field_name).
    2. Within-FIELD claim-value distinctness: the filler addresses a choice
       selection by option value WITHIN its field, so two pinned boxes of one
       field sharing a value are indistinguishable (the W-7 all-values-"1"
       collapse). Values may legitimately repeat ACROSS fields (radio kids
       sharing on-value "1", standalone bools -- flagging those was the
       round-2 false positive, bd kak8).
    3. Mapped options on field-level claimants: a field that claims a pinned
       widget at field level but carries dict options with NO pdf mapping is
       broken on the interactive path (the renderer stores option values the
       filler then cannot map to a widget) -- the round-1 bypass shape.
    """
    claims: dict[str, list[tuple[str, Optional[str]]]] = {w: [] for w in widget_leaves}
    problems: list[str] = []
    for f in schema.get("fields", []) or []:
        if not isinstance(f, dict):
            continue
        fid = str(f.get("id"))
        fl = _leaf(f.get("pdf_field_name"))
        options = f.get("options") if isinstance(f.get("options"), list) else []
        option_leaves = set()
        field_claim_values: list[str] = []
        for o in options:
            if not isinstance(o, dict):
                continue
            ol = _leaf(o.get("pdf_field_name"))
            if ol in claims:
                option_leaves.add(ol)
                value = str(o.get("value")) if o.get("value") is not None else None
                claims[ol].append((fid, value))
                if value is not None:
                    field_claim_values.append(value)
        # Rule 2: within-field distinctness of claiming values.
        within_dupes = sorted({v for v in field_claim_values
                               if field_claim_values.count(v) > 1})
        if within_dupes:
            problems.append(
                f"field {fid!r}: claiming option values not distinct within "
                f"the field: {within_dupes}")
        # A field-level claim that merely restates one of its own options'
        # widgets (the groups-of-one convention) is not a second claim.
        if fl in claims and fl not in option_leaves:
            claims[fl].append((fid, None))
            # Rule 3: options on a field-level claimant must be PDF-mapped.
            unmapped = [
                str(o.get("value")) for o in options
                if isinstance(o, dict)
                and not o.get("pdf_field_name") and not o.get("pdf_on_value")
            ]
            if unmapped:
                problems.append(
                    f"field {fid!r} claims {fl!r} at field level but carries "
                    f"unmapped options {sorted(set(unmapped))} -- unfillable "
                    f"on the interactive path")

    for w, claimants in claims.items():
        if not claimants:
            problems.append(f"{w}: not claimed by any field/option")
        elif len(claimants) > 1:
            problems.append(f"{w}: claimed {len(claimants)} times "
                            f"({', '.join(fid for fid, _ in claimants)})")

    owner_fields = {fid for cl in claims.values() for fid, _ in cl}
    consolidated = len(owner_fields) == 1 and all(len(c) == 1 for c in claims.values())
    return {
        "passed": not problems,
        "problems": problems,
        "consolidated": consolidated,
        "widgets": len(widget_leaves),
    }


# --------------------------------------------------------------------------- #
# Pipeline steps.
# --------------------------------------------------------------------------- #

def _try_repair(draft_path: str) -> tuple[str, str]:
    """Run schema_repair when it exists (P5.2); returns (draft_path, note).
    A repaired draft is written next to the input with a .repaired.json suffix."""
    repair_py = os.path.join(_HERE, "schema_repair.py")
    if not os.path.exists(repair_py):
        return draft_path, "-"
    spec = importlib.util.spec_from_file_location("schema_repair", repair_py)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with open(draft_path, encoding="utf-8") as fh:
        schema = json.load(fh)
    repaired, repairs = mod.repair(schema)  # the P5.2 contract
    out = os.path.splitext(draft_path)[0] + ".repaired.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(repaired, fh, indent=2)
    return out, f"{len(repairs)} repair(s)"


def evaluate_form(form: dict, draft_path: Optional[str],
                  extract: bool, model: str,
                  group_candidates: bool = False) -> dict:
    """Run [extract ->] repair -> lint -> roundtrip -> score for one form."""
    name = form["name"]
    row: dict[str, Any] = {"form": name, "draft": draft_path}

    if extract:
        import extract_form  # noqa: E402 (sibling module; heavy deps)
        suffix = "_gc" if group_candidates else ""
        out = os.path.join(_REPO, "scripts", "authoring", "outputs",
                           f"{name}_eval_draft{suffix}.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        extract_form.extract(form["pdf"], out, model=model,
                             group_candidates=group_candidates)
        draft_path = out
        row["draft"] = draft_path
        row["group_candidates"] = group_candidates

    if draft_path is None:
        if form["gold"] is None:
            row["skipped"] = ("no draft to evaluate (held-out form; run "
                              "--extract or --draft-dir)")
            return row
        # Baseline row: score the kit's own gold (what "perfect" looks like).
        draft_path = form["gold"]
        row["draft"] = draft_path
        row["baseline"] = True

    draft_path, repair_note = _try_repair(draft_path)
    row["repair"] = repair_note

    with open(draft_path, encoding="utf-8") as fh:
        draft = json.load(fh)

    findings = lint_schema(draft)
    row["lint_errors"] = sum(1 for f in findings if f.severity == "ERROR")
    row["lint_warnings"] = sum(1 for f in findings if f.severity == "WARNING")
    row["lint_findings"] = [f.as_dict() for f in findings]

    rt = roundtrip_fill.run(draft_path, form["pdf"])
    row["choice_fill"] = rt["choice_fill_success"]
    row["text_fill"] = rt["text_fill_success"]
    row["value_convention"] = rt["value_convention"]

    if form["gold"] and os.path.abspath(draft_path) != os.path.abspath(form["gold"]):
        s = schema_score.score(draft_path, form["gold"], label=name)
        row["field_f1"] = s["field_extraction"]["detection"]["f1"]
        row["score"] = s
    else:
        row["field_f1"] = None  # gold-vs-itself is not a measurement

    if form.get("widgets"):
        row["structural"] = check_widget_coverage(draft, form["widgets"])

    # Verdict: RED on any lint ERROR, a failed structural assertion, a
    # non-conforming value convention, or choice fill below the epic's 95%
    # gate. (Convention/lint are the columns the broken W-7 draft must go
    # RED on -- the P2.2 exit criterion.)
    conv_pct = row["value_convention"].get("pct")
    choice_pct = row["choice_fill"].get("pct")
    red = (
        row["lint_errors"] > 0
        or (row.get("structural") and not row["structural"]["passed"])
        or (conv_pct is not None and conv_pct < 100.0)
        or (choice_pct is not None and choice_pct < 95.0)
    )
    row["verdict"] = "RED" if red else "OK"
    return row


# --------------------------------------------------------------------------- #
# Table rendering.
# --------------------------------------------------------------------------- #

def _pct_cell(t: Optional[dict]) -> str:
    if not t:
        return "   -"
    p = t.get("pct")
    return "  n/a" if p is None else f"{p:5.1f}"


def render_table(rows: list[dict]) -> str:
    header = (f"{'form':<12} {'verdict':<7} {'lint E/W':<9} {'conv%':>6} "
              f"{'choice%':>8} {'text%':>7} {'fieldF1':>8} {'structural':<22} repair")
    L = [header, "-" * len(header)]
    for r in rows:
        if r.get("skipped"):
            L.append(f"{r['form']:<12} {'-':<7} {r['skipped']}")
            continue
        st = r.get("structural")
        if st is None:
            st_cell = "-"
        elif st["passed"]:
            st_cell = f"PASS ({st['widgets']}w" + (", 1 group)" if st["consolidated"] else ", split)")
        else:
            st_cell = f"FAIL ({len(st['problems'])} problem(s))"
        f1 = r.get("field_f1")  # schema_score f1 is already a 0-100 percentage
        f1_cell = "     - " if f1 is None else f"{f1:6.1f} "
        form_cell = r["form"] + ("*" if r.get("baseline") else "")
        L.append(
            f"{form_cell:<12} {r['verdict']:<7} "
            f"{str(r['lint_errors']) + '/' + str(r['lint_warnings']):<9} "
            f"{_pct_cell(r.get('value_convention')):>6} "
            f"{_pct_cell(r.get('choice_fill')):>8} "
            f"{_pct_cell(r.get('text_fill')):>7} "
            f"{f1_cell:>8} {st_cell:<22} {r.get('repair', '-')}"
        )
    return "\n".join(L)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Evaluate extraction quality across the benchmark forms "
                    "(bd h76m.6). Manual command -- not per-PR CI.")
    ap.add_argument("--extract", action="store_true",
                    help="run the full LLM extraction per form (slow; f1040 is "
                         ">6 min + paid tokens). Default: evaluate existing schemas.")
    ap.add_argument("--model", default="claude-opus-4-8",
                    help="extractor model for --extract")
    ap.add_argument("--group-candidates", action="store_true",
                    help="(with --extract) include the deterministic "
                         "pre-grouping candidates block -- the bd h76m.12 "
                         "ablation arm")
    ap.add_argument("--draft-dir", default=None,
                    help="directory of drafts to score, one <form>.json per form")
    ap.add_argument("--form", default=None,
                    help="evaluate a single benchmark form by name")
    ap.add_argument("--draft", default=None,
                    help="explicit draft path (requires --form)")
    ap.add_argument("--json", dest="json_out", default=None,
                    help="write the full row data as JSON")
    args = ap.parse_args(argv)

    if args.draft and not args.form:
        ap.error("--draft requires --form")

    forms = [f for f in _FORMS if not args.form or f["name"] == args.form]
    if not forms:
        ap.error(f"unknown --form {args.form!r} "
                 f"(known: {', '.join(f['name'] for f in _FORMS)})")

    rows = []
    for form in forms:
        draft = args.draft
        if draft is None and args.draft_dir:
            cand = os.path.join(args.draft_dir, f"{form['name']}.json")
            draft = cand if os.path.exists(cand) else None
        rows.append(evaluate_form(form, draft, args.extract, args.model,
                                  group_candidates=args.group_candidates))

    print(render_table(rows))
    if any(r.get("baseline") for r in rows):
        print("\n* = baseline row (the kit's own gold schema; no draft supplied)")
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, indent=2)
        print(f"[wrote {args.json_out}]")

    return 1 if any(r.get("verdict") == "RED" for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
