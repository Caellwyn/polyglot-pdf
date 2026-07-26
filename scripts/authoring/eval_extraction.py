#!/usr/bin/env python3
"""One-command extraction evaluation across the benchmark forms (bd h76m.6, P2.2).

Runs the pipeline  [extract ->] repair -> lint -> roundtrip -> score  over each
benchmark form and prints ONE summary table, so extractor changes (P5.x) are
judged against every form at once instead of the one being tuned.

MANUAL command -- never per-PR CI: full --extract on f1040 alone is >6 minutes
plus paid model tokens. Without --extract it evaluates EXISTING schemas (a
draft dir you point it at, or each kit's gold as the baseline row), which is
fast, free, and what the tests pin.

Benchmark set (see _FORMS): w7, f1040 (kits with gold schemas) + the
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
import tempfile
from typing import Any, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.join(_REPO, "scripts"))
sys.path.insert(0, os.path.join(_REPO, "scripts", "bakeoff"))
sys.path.insert(0, os.path.join(_REPO, "scripts", "authoring"))

import roundtrip_fill  # noqa: E402
import schema_score  # noqa: E402
from backend.services.schema_lint import lint_schema  # noqa: E402
from backend.services import guidance_contract  # noqa: E402


def _kit(name: str) -> str:
    return os.path.join(_REPO, "form-kits", name)


# The benchmark manifest. `gold` None = held out (no truth schema exists, on
# purpose -- see form-kits/w9-heldout/NOTE.md). `widgets` = the structural
# assertion's widget-leaf group for this form.
_FORMS: list[dict[str, Any]] = [
    {
        "name": "i-90",
        "pdf": os.path.join(_kit("i-90"), "form.pdf"),
        "gold": os.path.join(_kit("i-90"), "schema.json"),
        # Part-2 Q3 "reason for application (select only one)" -- 5 separate
        # checkbox widgets consolidated into ONE radio field. This is the exact
        # group the extractor USED to drop 4 of 5 of (bd 0nxh, hand-fixed) and
        # that group-candidates-default-ON + _complete_grouped_families now cover
        # deterministically (bd qmxb). The coverage check is modeling-agnostic: a
        # DROP or de-identification of any of the 5 fails (passed=False -- the
        # regression the qmxb fix prevents); a clean split into 5 standalone
        # checkboxes still passes but reports consolidated=False, so the row shows
        # whether the group was recognized as one field.
        "widgets": [f"P2_checkbox3[{i}]" for i in range(5)],
    },
    {
        "name": "w7",
        "pdf": os.path.join(_kit("w7"), "form.pdf"),
        "gold": os.path.join(_kit("w7"), "schema.json"),
        "widgets": [f"c1_{i}[0]" for i in range(2, 10)],  # reason boxes a-h
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

def _harvest_counts(repairs: list[dict]) -> dict:
    """Trigger-side harvest accounting (bd polyglot-pdf-eprg): how many legacy
    trigger-side edges the repair mirror canonicalized into v2 target-side keys
    (mirrored) vs dropped-with-report (unconverted). Action names are the
    backend/services/schema_repair.py controls_fields step's contract."""
    return {
        "mirrored": sum(1 for r in repairs
                        if r.get("action") == "mirror-controls-fields"),
        "unconverted": sum(1 for r in repairs if r.get("action") in (
            "controls-fields-unmirrored", "controls-fields-dangling",
            "drop-conditional-fields")),
    }


def _try_repair(draft_path: str) -> tuple[str, str, dict]:
    """Run schema_repair when it exists (P5.2); returns (draft_path, note,
    trigger_harvest). The repaired draft goes to a TEMP file (never beside the
    input -- a fixture input must not grow siblings in the repo)."""
    repair_py = os.path.join(_HERE, "schema_repair.py")
    if not os.path.exists(repair_py):
        return draft_path, "-", {}
    spec = importlib.util.spec_from_file_location("schema_repair", repair_py)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with open(draft_path, encoding="utf-8") as fh:
        schema = json.load(fh)
    repaired, repairs = mod.repair(schema)  # the P5.2 contract
    fd, out = tempfile.mkstemp(
        suffix=".repaired.json",
        prefix=os.path.splitext(os.path.basename(draft_path))[0] + "_")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(repaired, fh, indent=2)
    substantive = [r for r in repairs if r["action"] != "alias-hit-rate"]
    return out, f"{len(substantive)} repair(s)", _harvest_counts(repairs)


def evaluate_form(form: dict, draft_path: Optional[str],
                  extract: bool, model: str,
                  group_candidates: bool = False,
                  do_repair: bool = True) -> dict:
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

    # Repair runs on real DRAFTS only (the extract->repair->lint pipeline);
    # a gold-baseline row measures the gold as shipped, and --no-repair lets
    # the harness demonstrate the PRE-repair defect profile (the P2.2
    # broken-draft-scores-RED record).
    repair_ran = False
    if do_repair and not row.get("baseline"):
        draft_path, repair_note, harvest = _try_repair(draft_path)
        row["repair"] = repair_note
        if harvest.get("mirrored") or harvest.get("unconverted"):
            row["trigger_harvest"] = harvest
        repair_ran = repair_note != "-"
    else:
        row["repair"] = "-"

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

        # Sprint-15 headline relationship metrics (bd polyglot-pdf-eprg):
        # sh/rq = the target-side show/require conditionals; logic = the bespoke
        # keys (i-90 gold stores its flag-flips under conditional_behavior).
        conds = s["relationships"]["conditionals"]

        def _combined(keys: tuple[str, ...]) -> dict:
            rec = sum(conds[k]["recovered"] for k in keys if k in conds)
            tot = sum(conds[k]["total"] for k in keys if k in conds)
            out = {"recovered": rec, "total": tot,
                   "pct": (100.0 * rec / tot) if tot else None}
            tc = [conds[k]["trigger_correct"] for k in keys
                  if k in conds and "trigger_correct" in conds[k]]
            if tc:
                out["trigger_correct"] = sum(tc)
                out["trigger_correct_pct"] = (
                    100.0 * sum(tc) / tot) if tot else None
            return out

        row["rel_show_require"] = _combined(("show_if", "require_if"))
        row["rel_logic"] = _combined(("conditional_logic",
                                      "conditional_behavior"))
    else:
        row["field_f1"] = None  # gold-vs-itself is not a measurement

    if form.get("widgets"):
        row["structural"] = check_widget_coverage(draft, form["widgets"])

    # Guidance-content metrics (bd wsao.3, sprint-16): coverage / quality of
    # the two guidance channels, so enrichment progress (wsao.4+) is visible
    # on every eval run with zero model calls. Bounds + heuristics come from
    # the shared guidance_contract module (same source the lint rules use).
    row["guidance"] = guidance_metrics(draft)

    # Verdict: RED on any lint ERROR, a failed structural assertion, a
    # non-conforming value convention, or choice fill below the epic's 95%
    # gate. The value-convention column measures the V1 widget-leaf value
    # convention; a v2 schema (all shipped kits post the P6.2 flip, bd
    # h76m.16) deliberately uses SEMANTIC SLUGS instead, so it "violates" that
    # v1 convention BY DESIGN -- the check therefore only counts toward RED for
    # a v1 draft on which repair did not run (post-repair / for a v2 schema,
    # lint's slug/duplicate/reference rules + roundtrip are the real gates).
    is_v2 = str(draft.get("schema_version")) == "2"
    conv_pct = row["value_convention"].get("pct")
    choice_pct = row["choice_fill"].get("pct")
    red = (
        row["lint_errors"] > 0
        or (row.get("structural") and not row["structural"]["passed"])
        or (not is_v2 and not repair_ran
            and conv_pct is not None and conv_pct < 100.0)
        or (choice_pct is not None and choice_pct < 95.0)
    )
    row["verdict"] = "RED" if red else "OK"
    return row


def guidance_metrics(schema: dict) -> dict:
    """Deterministic guidance-channel metrics (bd wsao.3): instructions
    coverage %, median instructions length, label-restatement rate, and
    details containment % (None when no field carries details or the schema
    has no booklet floor to check against)."""
    fields = [f for f in schema.get("fields", []) if isinstance(f, dict)]
    askable = [f for f in fields
               if not f.get("read_only") and f.get("type") != "signature"]
    meta = schema.get("form_metadata")
    booklet = (meta.get("booklet_text") if isinstance(meta, dict) else None) or ""

    lengths: list[int] = []
    restatements = 0
    covered = 0
    paras_total = 0
    paras_contained = 0
    for f in askable:
        help_obj = f.get("help") if isinstance(f.get("help"), dict) else {}
        instr = (help_obj.get("instructions") or "").strip()
        if instr:
            covered += 1
            lengths.append(len(instr))
            labels = [o.get("label", "") for o in f.get("options") or []
                      if isinstance(o, dict)]
            if guidance_contract.is_label_restatement(
                    instr, f.get("name"), labels):
                restatements += 1
        details = (help_obj.get("details") or "").strip()
        if details and booklet:
            for para in guidance_contract.details_paragraphs(details):
                paras_total += 1
                if guidance_contract.check_containment(para, booklet).contained:
                    paras_contained += 1

    lengths.sort()
    return {
        "askable": len(askable),
        "covered": covered,
        "coverage_pct": (100.0 * covered / len(askable)) if askable else None,
        "median_len": lengths[len(lengths) // 2] if lengths else None,
        "restatement_pct": (100.0 * restatements / covered) if covered else None,
        "containment_pct": (100.0 * paras_contained / paras_total)
                           if paras_total else None,
    }


# --------------------------------------------------------------------------- #
# Table rendering.
# --------------------------------------------------------------------------- #

def _pct_cell(t: Optional[dict]) -> str:
    if not t:
        return "   -"
    p = t.get("pct")
    return "  n/a" if p is None else f"{p:5.1f}"


def render_table(rows: list[dict]) -> str:
    # Column width fits the widest cell: longest form name (w9-heldout, 10) +
    # the '*' baseline marker (1) + the ' [gc]' ablation suffix (5) = 16.
    header = (f"{'form':<16} {'verdict':<7} {'lint E/W':<9} {'conv%':>6} "
              f"{'choice%':>8} {'text%':>7} {'fieldF1':>7} {'sh/rq%':>7} "
              f"{'logic%':>7} {'guid%':>6} {'gLen':>5} {'cont%':>6} "
              f"{'structural':<22} repair")
    L = [header, "-" * len(header)]
    for r in rows:
        if r.get("skipped"):
            L.append(f"{r['form']:<16} {'-':<7} {r['skipped']}")
            continue
        st = r.get("structural")
        if st is None:
            st_cell = "-"
        elif st["passed"]:
            st_cell = f"PASS ({st['widgets']}w" + (", 1 group)" if st["consolidated"] else ", split)")
        else:
            st_cell = f"FAIL ({len(st['problems'])} problem(s))"
        f1 = r.get("field_f1")  # schema_score f1 is already a 0-100 percentage
        f1_cell = "-" if f1 is None else f"{f1:.1f}"
        form_cell = r["form"] + ("*" if r.get("baseline") else "")
        if r.get("group_candidates"):
            form_cell += " [gc]"  # the candidates-block ablation arm
        repair_cell = r.get("repair", "-")
        th = r.get("trigger_harvest")
        if th:
            # ts = trigger-side edges the repair mirror saw: m(irrored)/
            # u(nconverted, dropped-with-report).
            repair_cell += f" [ts {th['mirrored']}m/{th['unconverted']}u]"
        L.append(
            f"{form_cell:<16} {r['verdict']:<7} "
            f"{str(r['lint_errors']) + '/' + str(r['lint_warnings']):<9} "
            f"{_pct_cell(r.get('value_convention')):>6} "
            f"{_pct_cell(r.get('choice_fill')):>8} "
            f"{_pct_cell(r.get('text_fill')):>7} "
            f"{f1_cell:>7} "
            f"{_pct_cell(r.get('rel_show_require')):>7} "
            f"{_pct_cell(r.get('rel_logic')):>7} "
            f"{_pct_cell({'pct': (r.get('guidance') or {}).get('coverage_pct')}):>6} "
            f"{str((r.get('guidance') or {}).get('median_len') or '-'):>5} "
            f"{_pct_cell({'pct': (r.get('guidance') or {}).get('containment_pct')}):>6} "
            f"{st_cell:<22} {repair_cell}"
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
    ap.add_argument("--no-repair", action="store_true",
                    help="skip the P5.2 repair step (measure the raw draft's "
                         "pre-repair defect profile)")
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
                                  group_candidates=args.group_candidates,
                                  do_repair=not args.no_repair))

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
