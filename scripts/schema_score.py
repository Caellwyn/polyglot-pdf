#!/usr/bin/env python3
"""Score a draft FormSchema against a hand-authored ground-truth schema.

Throwaway research harness for the PDF->JSON authoring bake-off
(bd polyglot-pdf-7a9.3). It reports the TWO halves of the extraction problem
SEPARATELY:

  (a) FIELD extraction -- did the extractor find the right fields, with the right
      per-field attributes (type, pdf_field_name, pdf_position, options,
      validation) and section GROUPING (which fields share a section -- a
      partition-agreement metric, NOT exact section_id string match; bd
      polyglot-pdf-7a9.13)?
  (b) RELATIONSHIP/logic -- did it recover the parts/sections structure and the
      conditional dependencies (show_if, controls_fields, conditional_fields,
      copy_to, supplements + overflow_to_supplement, tables/multi_entry)?

The two halves are scored independently and printed as separate tables, because
the bake-off needs to see WHERE a given extractor fails -- the working hypothesis
(see bd remember extraction-feed-pymupdf-acroform-to-llm) is that OCR tools win
(a) and need an LLM partner for (b).

Field matching is EXTRACTOR-ID-AGNOSTIC: a draft field's `id` is whatever the
extractor invented, so we never match on it. We match on `pdf_field_name` (the
AcroForm widget name, the one thing both schemas derive from the same PDF), using
the same exact-then-endswith logic the production filler uses
(backend/routes/pdf_fill_routes.py). For radio/checkbox fields whose name lives on
their options, we match on the set of option-level pdf_field_names. Fields with no
PDF name at all (rare; table sub-columns) fall back to a (section, name) fuzzy key.

ASCII-only (cp1252 safe). Usage:

    python scripts/schema_score.py --draft DRAFT.json --truth TRUTH.json [--json OUT.json]

Self-test (ground truth vs itself should score ~100 percent on both halves):

    python scripts/schema_score.py --draft TRUTH.json --truth TRUTH.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field as dc_field
from difflib import SequenceMatcher
from typing import Any, Optional


# --------------------------------------------------------------------------- #
# Loading + small helpers
# --------------------------------------------------------------------------- #

def load_schema(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _norm_pfn(name: Optional[str]) -> Optional[str]:
    """Normalize a pdf_field_name for comparison: trim + lowercase, KEEP the path.

    We deliberately do NOT reduce to the dotted leaf here. The production filler
    matches exact-first, then endswith-fallback (pdf_fill_routes.py), precisely
    because leaf names collide -- e.g. I-90 has 5 leaf-name collisions
    (`p4_checkbox1a[0]` appears field-level AND option-level). Matching on the
    full normalized path avoids pairing two unrelated fields that share a leaf;
    the endswith fallback in `match_fields` recovers the XFA-vs-short-name case.
    """
    if not name:
        return None
    return name.strip().lower() or None


def _field_pfns(f: dict[str, Any]) -> list[str]:
    """All normalized (full-path) pdf_field_names a field is associated with.

    Returns a SORTED, de-duplicated list, not a set: the matcher iterates this in
    Pass 1a/1b, and Python randomizes set iteration order per process (the
    PYTHONHASHSEED), which made field pairing -- and therefore the scores --
    non-deterministic run-to-run (observed +-1 on I-90 controls_fields). A stable
    order makes the bake-off reproducible (bd polyglot-pdf-7a9.4 fresh-eyes/Copilot).
    """
    out: set[str] = set()
    n = _norm_pfn(f.get("pdf_field_name"))
    if n:
        out.add(n)
    for opt in (f.get("options") or []):
        n = _norm_pfn(opt.get("pdf_field_name"))
        if n:
            out.add(n)
    return sorted(out)


def _pfn_equiv(a: str, b: str) -> bool:
    """Two normalized pdf_field_names refer to the same widget?

    Exact, or one is the XFA full path ending in the other's short name -- the
    same exact-then-endswith rule the production filler uses. The endswith is
    anchored on a `.` boundary so `p4_checkbox1a[0]` does NOT match
    `p4_checkbox1[0]` (substring) -- only a true path-suffix counts.
    """
    if a == b:
        return True
    longer, shorter = (a, b) if len(a) >= len(b) else (b, a)
    return longer.endswith("." + shorter)


def _norm_text(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s.strip().lower())


def _fuzzy_key(f: dict[str, Any]) -> str:
    return _norm_text(f.get("section_id")) + "||" + _norm_text(f.get("name"))


# --------------------------------------------------------------------------- #
# Field matching (extractor-id-agnostic)
# --------------------------------------------------------------------------- #

@dataclass
class MatchResult:
    pairs: list[tuple[dict, dict]] = dc_field(default_factory=list)  # (truth, draft)
    unmatched_truth: list[dict] = dc_field(default_factory=list)     # missed (FN)
    unmatched_draft: list[dict] = dc_field(default_factory=list)     # spurious (FP)


def match_fields(truth: list[dict], draft: list[dict]) -> MatchResult:
    """Pair truth fields to draft fields without trusting either side's `id`.

    Pass 1a: exact normalized pdf_field_name overlap (fast, via an index).
    Pass 1b: endswith-equivalent pdf_field_name (XFA full-path vs short name),
             scanned among still-unused draft fields -- the production filler's
             exact-then-endswith rule, robust to colliding leaf names.
    Pass 2:  fuzzy (section, name) for whatever still has no PDF-name match.
    Each draft field is consumed at most once (`draft_used`).
    """
    res = MatchResult()
    draft_used = [False] * len(draft)
    draft_pfns = [_field_pfns(d) for d in draft]

    # Index draft by exact normalized pdf_field_name.
    draft_by_pfn: dict[str, list[int]] = {}
    for i, pfns in enumerate(draft_pfns):
        for pfn in pfns:
            draft_by_pfn.setdefault(pfn, []).append(i)

    leftover_truth: list[dict] = []

    for t in truth:
        t_pfns = _field_pfns(t)
        hit = None
        # 1a: exact.
        for pfn in t_pfns:
            for i in draft_by_pfn.get(pfn, []):
                if not draft_used[i]:
                    hit = i
                    break
            if hit is not None:
                break
        # 1b: endswith-equivalent (only if no exact hit and this field has a pfn).
        if hit is None and t_pfns:
            for i, used in enumerate(draft_used):
                if used or not draft_pfns[i]:
                    continue
                if any(_pfn_equiv(tp, dp) for tp in t_pfns for dp in draft_pfns[i]):
                    hit = i
                    break
        if hit is not None:
            draft_used[hit] = True
            res.pairs.append((t, draft[hit]))
        else:
            leftover_truth.append(t)

    # Pass 2: fuzzy (section, name) for the remainder.
    for t in leftover_truth:
        tk = _fuzzy_key(t)
        best_i, best_score = None, 0.0
        for i, used in enumerate(draft_used):
            if used:
                continue
            score = SequenceMatcher(None, tk, _fuzzy_key(draft[i])).ratio()
            if score > best_score:
                best_i, best_score = i, score
        if best_i is not None and best_score >= 0.85:
            draft_used[best_i] = True
            res.pairs.append((t, draft[best_i]))
        else:
            res.unmatched_truth.append(t)

    res.unmatched_draft = [draft[i] for i, used in enumerate(draft_used) if not used]
    return res


# --------------------------------------------------------------------------- #
# (a) FIELD-extraction scoring
# --------------------------------------------------------------------------- #

def _pct(num: int, den: int) -> float:
    return 100.0 * num / den if den else float("nan")


def _opts_match(t: dict, d: dict) -> bool:
    """Options recovered? Jaccard >= 0.8 (NOT recall-only).

    Recall-only would reward an extractor that hallucinates 50 options for a
    3-option field as long as the 3 correct ones are present. Jaccard penalizes
    both misses AND spurious extras, so a conservative extractor isn't unfairly
    beaten by a noisy one.
    """
    t_opts = {(_norm_text(o.get("value")) or _norm_text(o.get("label")))
              for o in (t.get("options") or [])}
    d_opts = {(_norm_text(o.get("value")) or _norm_text(o.get("label")))
              for o in (d.get("options") or [])}
    t_opts.discard("")
    d_opts.discard("")
    if not t_opts:
        return True  # nothing to recover
    if not d_opts:
        return False
    union = len(t_opts | d_opts)
    return (len(t_opts & d_opts) / union) >= 0.8 if union else True


def _pos_match(t: dict, d: dict, tol: float = 5.0) -> Optional[bool]:
    tp, dp = t.get("pdf_position"), d.get("pdf_position")
    if not tp:
        return None  # not applicable for this form/field
    if not dp:
        return False
    return (tp.get("page") == dp.get("page")
            and abs((tp.get("x") or 0) - (dp.get("x") or 0)) <= tol
            and abs((tp.get("y") or 0) - (dp.get("y") or 0)) <= tol)


def _section_grouping_agreement(pairs: list[tuple[dict, dict]]) -> tuple[int, int]:
    """Score section GROUPING, not the section_id STRING (bd polyglot-pdf-7a9.13).

    Exact section_id matching was a broken metric: the I-90 gold section_ids are
    inconsistent hand-authored noise (prose mixed with slugs), so every extractor
    scored 0%, while the LLM's clean-but-different ids were punished for not
    reproducing that noise. What actually matters for the UX is whether the draft
    GROUPS the same fields together -- the partition -- regardless of what the
    section is named.

    This is the Rand index of the two partitions over matched fields: for every
    unordered pair of matched fields, draft and gold AGREE if they either both put
    the two fields in the same section or both put them in different sections.
    Naming-agnostic, symmetric, robust to any future id convention.

    Only fields whose TRUTH side carries a section participate (a field the gold
    never sectioned can't inform a grouping judgment). Returns
    (agreeing_pairs, comparable_pairs); comparable_pairs is 0 (-> n/a) when fewer
    than two such fields matched.
    """
    # (truth_section, draft_section) for each matched field the gold sectioned.
    sectioned = [
        (_norm_text(t.get("section_id")), _norm_text(d.get("section_id")))
        for t, d in pairs
        if _norm_text(t.get("section_id"))
    ]
    agree = comparable = 0
    for i in range(len(sectioned)):
        t_i, d_i = sectioned[i]
        for j in range(i + 1, len(sectioned)):
            t_j, d_j = sectioned[j]
            comparable += 1
            if (t_i == t_j) == (d_i == d_j):
                agree += 1
    return agree, comparable


def score_fields(match: MatchResult) -> dict[str, Any]:
    """(a) half: detection P/R/F1 + per-attribute accuracy over matched pairs."""
    tp = len(match.pairs)
    fn = len(match.unmatched_truth)
    fp = len(match.unmatched_draft)
    precision = _pct(tp, tp + fp)
    recall = _pct(tp, tp + fn)
    f1 = (2 * precision * recall / (precision + recall)
          if precision + recall else float("nan"))

    # Per-attribute accuracy across matched pairs only (you can't grade an
    # attribute of a field that wasn't detected).
    attrs = {k: [0, 0] for k in
             ("type", "pdf_field_name", "options", "validation")}
    pos = [0, 0]  # [correct, applicable]

    for t, d in match.pairs:
        # type
        attrs["type"][1] += 1
        if _norm_text(t.get("type")) == _norm_text(d.get("type")):
            attrs["type"][0] += 1
        # pdf_field_name (exact-or-endswith-equivalent overlap counts)
        t_pfns, d_pfns = _field_pfns(t), _field_pfns(d)
        if t_pfns:
            attrs["pdf_field_name"][1] += 1
            if any(_pfn_equiv(a, b) for a in t_pfns for b in d_pfns):
                attrs["pdf_field_name"][0] += 1
        # options
        if t.get("options"):
            attrs["options"][1] += 1
            if _opts_match(t, d):
                attrs["options"][0] += 1
        # validation: BOTH required-ness AND pattern must agree (an OR let a draft
        # pass by getting only one right; and `str(None)` made two missing patterns
        # compare equal as the string "none", masking a required mismatch).
        if t.get("validation"):
            attrs["validation"][1] += 1
            tv, dv = t.get("validation") or {}, d.get("validation") or {}
            req_ok = bool(tv.get("required")) == bool(dv.get("required"))
            pat_ok = _norm_text(tv.get("pattern")) == _norm_text(dv.get("pattern"))
            if dv and req_ok and pat_ok:
                attrs["validation"][0] += 1
        # section grouping is scored AFTER the loop (it is a pairwise partition
        # metric over all matched fields, not a per-field attribute) -- see
        # _section_grouping_agreement and bd polyglot-pdf-7a9.13.
        # pdf_position
        pm = _pos_match(t, d)
        if pm is not None:
            pos[1] += 1
            if pm:
                pos[0] += 1

    attr_scores = {k: {"correct": c, "applicable": n, "pct": _pct(c, n)}
                   for k, (c, n) in attrs.items()}
    attr_scores["pdf_position"] = {"correct": pos[0], "applicable": pos[1],
                                   "pct": _pct(pos[0], pos[1])}
    # section GROUPING (partition agreement), replacing exact section_id matching.
    sg_correct, sg_applicable = _section_grouping_agreement(match.pairs)
    attr_scores["section_grouping"] = {"correct": sg_correct,
                                       "applicable": sg_applicable,
                                       "pct": _pct(sg_correct, sg_applicable)}

    return {
        "detection": {"true_positive": tp, "false_negative": fn,
                      "false_positive": fp, "precision": precision,
                      "recall": recall, "f1": f1},
        "attributes": attr_scores,
    }


# --------------------------------------------------------------------------- #
# (b) RELATIONSHIP/logic scoring
# --------------------------------------------------------------------------- #

def _resolve_to_truth(match: MatchResult) -> dict[str, dict]:
    """Map each truth field id -> its matched draft field (or None)."""
    out: dict[str, Optional[dict]] = {}
    for t, d in match.pairs:
        out[t.get("id")] = d
    for t in match.unmatched_truth:
        out[t.get("id")] = None
    return out


def score_relationships(truth: dict, draft: dict, match: MatchResult) -> dict[str, Any]:
    """(b) half: recall of structural + conditional relationships.

    Recall (not precision) is the headline: the bake-off question is "how much of
    the real dependency structure did the extractor recover?" Each relationship
    type is counted in the ground truth and checked for presence in the matched
    draft field. We score by COUNT recovered, per type.
    """
    t_to_d = _resolve_to_truth(match)

    def field_has_rel(t_field: dict, key: str) -> bool:
        """Did the draft field matched to this truth field carry the same rel kind?"""
        d_field = t_to_d.get(t_field.get("id"))
        if not d_field:
            return False
        return bool(d_field.get(key))

    rel_keys = ["show_if", "controls_fields", "conditional_fields",
                "conditional_logic", "conditional_behavior", "copy_to",
                "overflow_to_supplement"]
    field_rels: dict[str, list[int]] = {k: [0, 0] for k in rel_keys}  # [recovered, total]
    for t in truth.get("fields", []):
        for k in rel_keys:
            if t.get(k):
                field_rels[k][1] += 1
                if field_has_rel(t, k):
                    field_rels[k][0] += 1

    # Structural: parts, sections, tables, supplements (schema-level counts).
    struct = {}
    struct["parts"] = [len(draft.get("parts") or []), len(truth.get("parts") or [])]
    struct["sections"] = [len(draft.get("sections") or []),
                          len(truth.get("sections") or [])]
    struct["supplements"] = [len(draft.get("supplements") or []),
                             len(truth.get("supplements") or [])]
    t_tables = sum(1 for f in truth.get("fields", [])
                   if f.get("type") == "table" or f.get("multi_entry"))
    d_tables = sum(1 for f in draft.get("fields", [])
                   if f.get("type") == "table" or f.get("multi_entry"))
    struct["tables/multi_entry"] = [d_tables, t_tables]

    rel_scores = {k: {"recovered": c, "total": n, "pct": _pct(c, n)}
                  for k, (c, n) in field_rels.items()}
    struct_scores = {k: {"draft": d, "truth": n,
                         "pct": _pct(min(d, n), n) if n else float("nan")}
                     for k, (d, n) in struct.items()}

    return {"conditionals": rel_scores, "structure": struct_scores}


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #

def _fmt_pct(p: float) -> str:
    return "  n/a" if p != p else f"{p:5.1f}%"  # p!=p detects NaN


def render_report(name: str, a: dict, b: dict) -> str:
    L = []
    L.append("=" * 64)
    L.append(f"SCHEMA SCORE: {name}")
    L.append("=" * 64)
    det = a["detection"]
    L.append("")
    L.append("(a) FIELD EXTRACTION")
    L.append(f"  detection: precision {_fmt_pct(det['precision'])}  "
             f"recall {_fmt_pct(det['recall'])}  f1 {_fmt_pct(det['f1'])}")
    L.append(f"             TP={det['true_positive']} "
             f"FN(missed)={det['false_negative']} "
             f"FP(spurious)={det['false_positive']}")
    L.append("  per-attribute accuracy (over matched fields):")
    for k, v in a["attributes"].items():
        L.append(f"    {k:18s} {_fmt_pct(v['pct'])}  "
                 f"({v['correct']}/{v['applicable']})")
    L.append("")
    L.append("(b) RELATIONSHIP / LOGIC")
    L.append("  conditional recall (recovered / total in ground truth):")
    for k, v in b["conditionals"].items():
        if v["total"] == 0:
            L.append(f"    {k:22s}   n/a   (0 in ground truth)")
        else:
            L.append(f"    {k:22s} {_fmt_pct(v['pct'])}  "
                     f"({v['recovered']}/{v['total']})")
    L.append("  structure (draft vs truth count):")
    for k, v in b["structure"].items():
        L.append(f"    {k:22s} {_fmt_pct(v['pct'])}  "
                 f"(draft {v['draft']} / truth {v['truth']})")
    L.append("")
    return "\n".join(L)


def score(draft_path: str, truth_path: str, label: Optional[str] = None) -> dict:
    draft = load_schema(draft_path)
    truth = load_schema(truth_path)
    match = match_fields(truth.get("fields", []), draft.get("fields", []))
    a = score_fields(match)
    b = score_relationships(truth, draft, match)
    return {
        "label": label or truth_path,
        "draft": draft_path,
        "truth": truth_path,
        "field_extraction": a,
        "relationships": b,
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Score a draft FormSchema vs ground truth.")
    ap.add_argument("--draft", required=True, help="path to the draft (extractor) schema")
    ap.add_argument("--truth", required=True, help="path to the ground-truth schema")
    ap.add_argument("--label", default=None, help="display label for the report")
    ap.add_argument("--json", dest="json_out", default=None,
                    help="optional path to write the full result JSON")
    args = ap.parse_args(argv)

    result = score(args.draft, args.truth, args.label)
    print(render_report(result["label"], result["field_extraction"],
                        result["relationships"]))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
        print(f"[wrote {args.json_out}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
