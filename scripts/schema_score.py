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
      conditional dependencies (v2 keys: show_if, require_if, conditional_logic,
      conditional_behavior, copy_to, supplements + overflow_to_supplement,
      tables/multi_entry)?

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
PDF name at all (rare; table sub-columns) fall back to a (section, name) fuzzy key,
then to a section-id-free name-only key so a renamed-section draft still pairs them
(bd polyglot-pdf-zb55).

ASCII-only (cp1252 safe). Usage:

    python scripts/schema_score.py --draft DRAFT.json --truth TRUTH.json [--json OUT.json]

Self-test (ground truth vs itself should score ~100 percent on both halves):

    python scripts/schema_score.py --draft TRUTH.json --truth TRUTH.json
"""
from __future__ import annotations

import argparse
import json
import os
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


def _name_key(f: dict[str, Any]) -> str:
    """Section-id-free fuzzy key: the field name alone (bd polyglot-pdf-zb55).

    Pass 3's key. `_fuzzy_key` bakes in section_id, so a PDF-less field with the
    same name but a RENAMED section (e.g. I-589 table/static/supplement fields --
    ~6 of 303 on i-589, 0 on i-90) goes unmatched, which then leaves the
    naming-agnostic section-GROUPING metric n/a for exactly the fields it means to
    grade. Matching PDF-less-to-PDF-less on name alone rescues those fields so a
    renamed-section draft can still be graded on grouping.
    """
    return _norm_text(f.get("name"))


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
    Pass 3:  section-id-FREE fuzzy name for the PDF-less remainder (bd
             polyglot-pdf-zb55): a field with no pdf_field_name on either side
             matches on name alone, so a draft that RENAMED the section still
             pairs name-identical PDF-less fields -- otherwise the naming-agnostic
             grouping metric leaks section_id through the matcher and goes n/a for
             exactly those fields. Restricted to PDF-less-vs-PDF-less so it can
             never override a real pdf_field_name pairing from Pass 1/2.
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
    leftover_after_fuzzy: list[dict] = []
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
            leftover_after_fuzzy.append(t)

    # Pass 3: section-id-free fuzzy name, PDF-less-vs-PDF-less only (bd zb55).
    # Only reached by fields with no pdf_field_name (a field WITH a pfn that got
    # here genuinely has no widget-name match, and matching it on name alone --
    # ignoring the pdf_field_name it DOES have -- would be a false pair). Same
    # SequenceMatcher>=0.85 bar as Pass 2, applied to the name key alone.
    for t in leftover_after_fuzzy:
        if _field_pfns(t):  # has a PDF name -> not a Pass-3 candidate
            res.unmatched_truth.append(t)
            continue
        tk = _name_key(t)
        if not tk:  # no name to match on -> can't pair (avoid ""=="" ratio 1.0)
            res.unmatched_truth.append(t)
            continue
        best_i, best_score = None, 0.0
        for i, used in enumerate(draft_used):
            if used or draft_pfns[i]:  # skip used + draft fields that HAVE a pfn
                continue
            dk = _name_key(draft[i])
            if not dk:
                continue
            score = SequenceMatcher(None, tk, dk).ratio()
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
    # Match on LABEL first, value second (bd polyglot-pdf-d9lz). In v2 the option
    # `value` is a semantic slug the extractor derives from the label
    # ('new_application'), so two correct extractions of the same option can carry
    # DIFFERENT slugs -- and the v1->v2 gold migration slugged the same labels
    # independently. The `label` is the human-readable text both the gold and any
    # extraction derive verbatim from the PDF, so it is the dialect-stable key;
    # slug-vs-slug (value-first) scored correct v2 extractions as option mismatches.
    t_opts = {(_norm_text(o.get("label")) or _norm_text(o.get("value")))
              for o in (t.get("options") or [])}
    d_opts = {(_norm_text(o.get("label")) or _norm_text(o.get("value")))
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


def _section_grouping_agreement(pairs: list[tuple[dict, dict]]) -> dict[str, Any]:
    """Score section GROUPING, not the section_id STRING (bd polyglot-pdf-7a9.13).

    Exact section_id matching was a broken metric: the I-90 gold section_ids are
    inconsistent hand-authored noise (prose mixed with slugs), so every extractor
    scored 0%, while the LLM's clean-but-different ids were punished for not
    reproducing that noise. What actually matters for the UX is whether the draft
    GROUPS the same fields together -- the partition -- regardless of what the
    section is named.

    Metric: PAIRWISE co-membership F1 over matched fields, scored ONLY on
    same-section pairs (not the Rand index). For every unordered pair of matched
    truth-sectioned fields:
      - a TRUE pair = gold puts the two fields in the same section;
      - a PREDICTED pair = the draft puts them in the same section.
      recall    = (true & predicted) / true       (gold groupings the draft kept)
      precision = (true & predicted) / predicted   (draft groupings that are real)
      f1        = harmonic mean; this is the reported pct.

    Why NOT the Rand index (Codex review, PR #235): Rand also credits
    DIFFERENT-section agreements, so a draft that emits NO sections (everything a
    singleton) scores ~90% on a many-section gold purely from cross-section pairs
    it got "right" by grouping nothing -- inflating the signal and able to reverse
    bake-off conclusions. Co-membership F1 ignores the true-negative cross-section
    pairs: an extractor that reproduces no grouping has recall 0 -> F1 0.

    Naming-agnostic (invariant to relabeling sections). Only fields whose TRUTH
    side carries a section participate (a field the gold never sectioned can't
    inform a grouping judgment). A draft field with NO section_id is a SINGLETON
    (never co-membered with anything), so it can never be a predicted pair.

    Returns {"precision","recall","f1","true_pairs","predicted_pairs",
    "agree_pairs"} (agree_pairs = true & predicted). f1 is NaN (-> n/a) when there
    are no true pairs AND no predicted pairs (nothing to grade).
    """
    # (truth_section, draft_section) for each matched field the gold sectioned.
    sectioned = [
        (_norm_text(t.get("section_id")), _norm_text(d.get("section_id")))
        for t, d in pairs
        if _norm_text(t.get("section_id"))
    ]

    def _draft_same(a: str, b: str) -> bool:
        # Empty draft section = a singleton: never "same" as anything (incl. "").
        return a != "" and a == b

    true_pairs = predicted_pairs = agree_pairs = 0
    for i in range(len(sectioned)):
        t_i, d_i = sectioned[i]
        for j in range(i + 1, len(sectioned)):
            t_j, d_j = sectioned[j]
            gold_same = t_i == t_j  # truth ids always non-empty (filtered above)
            draft_same = _draft_same(d_i, d_j)
            if gold_same:
                true_pairs += 1
            if draft_same:
                predicted_pairs += 1
            if gold_same and draft_same:
                agree_pairs += 1

    precision = (agree_pairs / predicted_pairs) if predicted_pairs else float("nan")
    recall = (agree_pairs / true_pairs) if true_pairs else float("nan")
    if true_pairs == 0 and predicted_pairs == 0:
        f1 = float("nan")  # nothing to grade -> n/a
    elif true_pairs == 0 or predicted_pairs == 0 or agree_pairs == 0:
        f1 = 0.0           # one side empty (or zero overlap) -> no co-membership credit
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return {
        "precision": precision, "recall": recall, "f1": f1,
        "true_pairs": true_pairs, "predicted_pairs": predicted_pairs,
        "agree_pairs": agree_pairs,
    }


def score_fields(match: MatchResult, grouping_basis: str = "draft") -> dict[str, Any]:
    """(a) half: detection P/R/F1 + per-attribute accuracy over matched pairs.

    `grouping_basis` records how the draft's section_id values were obtained
    for the section_grouping metric ("draft" = the extractor's own emitted
    section_id; "derived" = scripts/authoring/derive_sections.py ran on a COPY
    of the draft first -- see score(derive_pdf_path=...), bd polyglot-pdf-mhyt). It
    is a pass-through marker, not a scoring input: match.pairs already carries
    whichever section_id the caller decided to grade.
    """
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
    # section GROUPING: pairwise co-membership F1 (NOT exact section_id, NOT the
    # Rand index -- see _section_grouping_agreement). pct is the F1; the displayed
    # (correct/applicable) is agree_pairs over the UNION of gold-same and
    # draft-same pairs. `applicable` MUST be truthy whenever the metric is gradable
    # (true OR predicted pairs exist) -- the bake-off summary (_attr_avg) drops any
    # attr with falsy applicable, so keying it on true_pairs alone would silently
    # hide an over-grouping 0% from the headline (Codex PR #235 r2).
    sg = _section_grouping_agreement(match.pairs)
    sg_gradable = sg["true_pairs"] + sg["predicted_pairs"] - sg["agree_pairs"]
    attr_scores["section_grouping"] = {
        "correct": sg["agree_pairs"],
        "applicable": sg_gradable,
        "pct": (sg["f1"] * 100.0 if sg["f1"] == sg["f1"] else float("nan")),
        "precision": sg["precision"],
        "recall": sg["recall"],
        "f1": sg["f1"],
        "true_pairs": sg["true_pairs"],
        "predicted_pairs": sg["predicted_pairs"],
        "basis": grouping_basis,
    }

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

    # v2 relationship vocabulary (bd polyglot-pdf-d9lz). Dropped BOTH v1-legacy
    # trigger-side keys `conditional_fields` and `controls_fields`: neither is a
    # v2 FormField model field, both were DELETED at the P6.2 flip and are
    # lint-ERRORed as `legacy-trigger-side-logic` (schema_lint.py), and both are
    # 0/0 across every v2 gold kit -- so a v2 arm can never emit them and they only
    # diluted the conditionals table with dead buckets. Added `require_if`, the v2
    # target-side require path (a live key the scorer was missing). The remaining
    # keys (show_if, conditional_logic, conditional_behavior, copy_to,
    # overflow_to_supplement) are all live v2 model fields / tolerated aliases.
    rel_keys = ["show_if", "require_if", "conditional_logic",
                "conditional_behavior", "copy_to", "overflow_to_supplement"]
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
        # section_grouping's pct is an F1 (pairwise co-membership), so the generic
        # "(correct/applicable)" is NOT pct's fraction -- render it as F1 with its
        # own precision/recall instead of a misleading raw count (Codex PR #235 r3).
        if k == "section_grouping":
            _p = v["precision"] * 100 if v["precision"] == v["precision"] else float("nan")
            _r = v["recall"] * 100 if v["recall"] == v["recall"] else float("nan")
            L.append(f"    {k:18s} {_fmt_pct(v['pct'])}  "
                     f"(F1; P {_fmt_pct(_p)} R {_fmt_pct(_r)}; "
                     f"{v['correct']}/{v['true_pairs']} gold pairs kept)")
        else:
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


def _draft_has_any_section_id(draft: dict[str, Any]) -> bool:
    return any(f.get("section_id") for f in draft.get("fields", []) if isinstance(f, dict))


def derive_divisions_for_grouping(draft: dict[str, Any], pdf_path: str
                                  ) -> tuple[dict[str, Any], str, Optional[str]]:
    """Grouping-scoring input for a draft with NO section_id anywhere (bd
    polyglot-pdf-mhyt).

    The extractor contract (scripts/bakeoff/schema_contract.py) tells LLM-native
    arms NOT to emit parts/sections/section_id -- production derives divisions
    deterministically AFTER extraction instead (scripts/authoring/
    derive_sections.py, bd polyglot-pdf-6cfu.2, wired at scripts/authoring/
    extract_form.py's step 3e via derive_and_apply). Scoring the raw arm output
    as-is makes every field a section_grouping SINGLETON (draft section_id ""),
    so recall/F1 come out ~0 regardless of extraction quality -- a scorer
    artifact, not a real quality signal.

    This mirrors that SAME production entry point on a DEEP COPY of the draft
    (the caller's on-disk arm output is never mutated), so grouping is graded on
    the divisions production would actually derive for this arm's fields.

    Returns (schema_for_grouping, basis, error_reason):
      - basis is "derived" on success.
      - on failure (bad/unreadable PDF, derivation exception, etc.) the ORIGINAL
        draft is returned unchanged, basis is "derivation-error", and
        error_reason names what went wrong -- the caller must surface this as
        n/a, never silently score a 0.
    """
    import copy as _copy

    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(_here, "authoring"))
    try:
        import derive_sections  # noqa: E402 (sibling scripts/ dir)
    except Exception as exc:  # pragma: no cover - exercised only if fitz is absent
        return draft, "derivation-error", f"cannot import derive_sections: {exc}"

    draft_copy = _copy.deepcopy(draft)
    try:
        derive_sections.derive_and_apply(draft_copy, pdf_path)
    except Exception as exc:
        return draft, "derivation-error", f"{type(exc).__name__}: {exc}"
    return draft_copy, "derived", None


def _overlay_derived_section_ids(pairs: list[tuple[dict, dict]],
                                 orig_fields: list,
                                 derived_fields: list) -> list[tuple[dict, dict]]:
    """Rewrite each matched pair's DRAFT side with the derived section_id.

    derive_and_apply mutates fields in place (never adds/removes/reorders), so
    the derived deep copy's fields correspond to the original's by POSITION;
    map each original field object (the exact dicts match.pairs reference) to
    its derived section_id and return pairs whose draft side carries it. The
    pair SET is unchanged by construction -- see the caller's comment for why
    a re-match would not guarantee that (bd polyglot-pdf-mhyt).
    """
    sid_by_obj = {}
    for i, f in enumerate(orig_fields):
        if isinstance(f, dict) and i < len(derived_fields) and isinstance(derived_fields[i], dict):
            sid_by_obj[id(f)] = derived_fields[i].get("section_id")
    out = []
    for t, d in pairs:
        overlay = dict(d)
        if id(d) in sid_by_obj:
            overlay["section_id"] = sid_by_obj[id(d)]
        out.append((t, overlay))
    return out


def score(draft_path: str, truth_path: str, label: Optional[str] = None,
         derive_pdf_path: Optional[str] = None) -> dict:
    """Score a draft against ground truth.

    `derive_pdf_path` (bd polyglot-pdf-mhyt): when given AND the draft carries
    NO section_id on any field (the LLM-native contract's output shape), the
    section_grouping metric is scored against divisions DERIVED from this PDF
    via the same deterministic pass production runs post-extraction, instead of
    silently scoring every field as an ungrouped singleton. A draft that DOES
    carry section_id keeps grading its own (unchanged behavior). If derivation
    itself errors, section_grouping is marked n/a with a reason -- never scored
    as a false 0 (see derive_divisions_for_grouping).
    """
    draft = load_schema(draft_path)
    truth = load_schema(truth_path)

    grouping_basis = "draft"
    grouping_error: Optional[str] = None
    draft_for_grouping = draft
    if derive_pdf_path and not _draft_has_any_section_id(draft):
        draft_for_grouping, grouping_basis, grouping_error = \
            derive_divisions_for_grouping(draft, derive_pdf_path)

    match = match_fields(truth.get("fields", []), draft.get("fields", []))
    a = score_fields(match)
    if draft_for_grouping is not draft:
        # Overlay the DERIVED section_ids onto the ORIGINAL match's pairs.
        # Deliberately NOT a re-match against the derived copy: match_fields'
        # Pass-2 fuzzy key bakes section_id into the match, so re-matching
        # could pair a DIFFERENT field set once derivation stamps section_ids
        # (e.g. a derived slug that string-collides with a gold section_id can
        # rescue a borderline fuzzy match) -- grouping would then be graded
        # over a different population than detection/attrs/relations. The
        # overlay keeps the pair set identical by construction.
        grouping_pairs = _overlay_derived_section_ids(
            match.pairs, draft.get("fields", []),
            draft_for_grouping.get("fields", []))
        sg = _section_grouping_agreement(grouping_pairs)
        sg_gradable = sg["true_pairs"] + sg["predicted_pairs"] - sg["agree_pairs"]
        a["attributes"]["section_grouping"] = {
            "correct": sg["agree_pairs"],
            "applicable": sg_gradable,
            "pct": (sg["f1"] * 100.0 if sg["f1"] == sg["f1"] else float("nan")),
            "precision": sg["precision"],
            "recall": sg["recall"],
            "f1": sg["f1"],
            "true_pairs": sg["true_pairs"],
            "predicted_pairs": sg["predicted_pairs"],
            "basis": grouping_basis,
        }
    elif grouping_error is not None:
        # Derivation was attempted (no section_id + a pdf_path given) and FAILED:
        # mark n/a with a reason, never leave the singleton-vs-nothing 0 in place.
        a["attributes"]["section_grouping"] = {
            "correct": 0, "applicable": 0, "pct": float("nan"),
            "precision": float("nan"), "recall": float("nan"), "f1": float("nan"),
            "true_pairs": 0, "predicted_pairs": 0,
            "basis": grouping_basis, "error": grouping_error,
        }
    else:
        a["attributes"]["section_grouping"]["basis"] = grouping_basis
    b = score_relationships(truth, draft, match)
    return {
        "label": label or truth_path,
        "draft": draft_path,
        "truth": truth_path,
        "field_extraction": a,
        "relationships": b,
    }


# --------------------------------------------------------------------------- #
# --pdf: fill-truth + lint columns (bd polyglot-pdf-h76m.6, P2.2)
# --------------------------------------------------------------------------- #

def score_pdf(draft_path: str, pdf_path: str) -> dict:
    """Run the fill-truth + lint layer over a draft against its real PDF.

    Wires the two safety-net tools in as first-class report columns:
    - scripts/bakeoff/roundtrip_fill.py (bd 7a9.14): synthetic full-coverage
      values through the production filler's exact widget-write semantics,
      verified by /AS read-back;
    - backend/services/schema_lint.py (bd h76m.5): structured findings over
      the raw draft dict (works on drafts Pydantic rejects).
    """
    _here = os.path.dirname(os.path.abspath(__file__))
    _repo = os.path.dirname(_here)
    sys.path.insert(0, os.path.join(_repo, "scripts", "bakeoff"))
    sys.path.insert(0, _repo)
    import roundtrip_fill  # noqa: E402
    from backend.services.schema_lint import lint_schema  # noqa: E402

    draft = load_schema(draft_path)
    rt = roundtrip_fill.run(draft_path, pdf_path)
    findings = lint_schema(draft)
    return {
        "roundtrip": rt,
        "lint": {
            "errors": sum(1 for f in findings if f.severity == "ERROR"),
            "warnings": sum(1 for f in findings if f.severity == "WARNING"),
            "findings": [f.as_dict() for f in findings],
        },
    }


def _fmt_tally(t: dict) -> str:
    """roundtrip_fill tallies carry pct=None (not NaN) when nothing attempted."""
    p = t.get("pct")
    ps = "  n/a" if p is None else f"{p:5.1f}%"
    return f"{ps}  ({t.get('filled', 0)}/{t.get('attempted', 0)})"


def render_pdf_report(p: dict) -> str:
    L = []
    L.append("(c) FILL TRUTH + LINT (--pdf)")
    rt = p["roundtrip"]
    L.append(f"  roundtrip fill: choice {_fmt_tally(rt['choice_fill_success'])}   "
             f"text {_fmt_tally(rt['text_fill_success'])}")
    conv = rt.get("value_convention", {})
    L.append(f"  value convention: {_fmt_tally({'pct': conv.get('pct'), 'filled': conv.get('conforming', 0), 'attempted': conv.get('total', 0)})} "
             f"option values on the widget-leaf convention")
    lint = p["lint"]
    L.append(f"  lint: {lint['errors']} error(s), {lint['warnings']} warning(s)")
    for f in lint["findings"][:8]:
        L.append(f"    {f['severity']} [{f['rule']}] {f['path']}: {f['message'][:90]}")
    if len(lint["findings"]) > 8:
        L.append(f"    ... and {len(lint['findings']) - 8} more")
    L.append("")
    return "\n".join(L)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Score a draft FormSchema vs ground truth.")
    ap.add_argument("--draft", required=True, help="path to the draft (extractor) schema")
    ap.add_argument("--truth", required=True, help="path to the ground-truth schema")
    ap.add_argument("--label", default=None, help="display label for the report")
    ap.add_argument("--pdf", default=None,
                    help="path to the blank form PDF: adds roundtrip-fill + lint "
                         "columns (bd h76m.6)")
    ap.add_argument("--json", dest="json_out", default=None,
                    help="optional path to write the full result JSON")
    args = ap.parse_args(argv)

    result = score(args.draft, args.truth, args.label)
    print(render_report(result["label"], result["field_extraction"],
                        result["relationships"]))
    if args.pdf:
        result["pdf"] = score_pdf(args.draft, args.pdf)
        print(render_pdf_report(result["pdf"]))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
        print(f"[wrote {args.json_out}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
