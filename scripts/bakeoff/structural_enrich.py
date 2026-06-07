#!/usr/bin/env python3
"""Generic structural-enrichment pass over the AcroForm dump (bd polyglot-pdf-7a9.9).

Throwaway research tool. The bake-off's `acroform_dump.py` already captures the
machine-readable field layer (exact widget names, types, flags, /TU tooltips,
rects, choices, on-values). This module adds the *structural signals a strong LLM
can reason over* WITHOUT any USCIS-specific heuristic -- the whole point of the
7a9.9 thesis is to retire the hardcoded "Part. A. 1." / "P1_Line3a" conventions
and feed the model generic, form-agnostic structure instead.

Signals added here, all derived mechanically from the dump (no form knowledge):

  1. name-token decomposition -- split the XFA dotted path + leaf into tokens
     (subform path, leaf, [index]), so the model sees the grouping the author
     encoded in the name WITHOUT us interpreting it. Pure tokenization, no regex
     mapping to "Part"/"Line".
  2. tab order -- the page-then-reading-order index (top-to-bottom, left-to-right)
     each widget falls in. This is the order a human tabs through the form, a
     strong proxy for logical sequence the bare name list loses.
  3. spatial clusters -- group widgets that sit on the same visual row (similar y
     on a page) and the same vertical block, so multi-widget questions (a name
     split into family/given/middle, a date split into m/d/y) are visible as a
     cluster the model can consolidate.

The output is the dump augmented with these per-field keys plus a compact text
rendering for the prompt. ASCII only (cp1252 safe).

Usage:
    python scripts/bakeoff/structural_enrich.py DUMP.json [--json OUT.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any, Optional


# --------------------------------------------------------------------------- #
# 1. name-token decomposition (generic, no USCIS mapping)
# --------------------------------------------------------------------------- #

_TOKEN_SPLIT = re.compile(r"[._\[\]]+")


def decompose_name(full_name: str) -> dict[str, Any]:
    """Split an XFA dotted widget name into structural tokens, no interpretation.

    Example: 'form1[0].#subform[0].P1_Line3a_FamilyName[0]' ->
      {
        "path": ["form1", "#subform"],     # container subforms (everything but leaf)
        "leaf": "P1_Line3a_FamilyName",    # the meaningful local name
        "leaf_tokens": ["P1", "Line3a", "FamilyName"],  # leaf split on _ and case
        "index": 0,                        # trailing [n] on the leaf, if any
      }
    We do NOT map P1->Part 1 or Line3a->question 3a; that interpretation is the
    LLM's job. We only expose the author's own delimiters.
    """
    # Strip a trailing [n] index off the whole name first.
    parts = full_name.split(".")
    leaf_raw = parts[-1] if parts else full_name
    container = parts[:-1]

    m = re.match(r"^(.*?)\[(\d+)\]$", leaf_raw)
    if m:
        leaf = m.group(1)
        index = int(m.group(2))
    else:
        leaf = leaf_raw
        index = None

    # Clean container subform names of their [n] for readability.
    path = [re.sub(r"\[\d+\]$", "", c) for c in container]

    # Tokenize the leaf on underscores AND camelCase boundaries -- generic, since
    # XFA authors use both ('P1_Line3a_FamilyName', 'PtAILine1_ANumber').
    leaf_tokens = _tokenize_leaf(leaf)

    return {
        "path": path,
        "leaf": leaf,
        "leaf_tokens": leaf_tokens,
        "index": index,
    }


def _tokenize_leaf(leaf: str) -> list[str]:
    """Split a leaf name on underscores and camelCase/digit boundaries."""
    out: list[str] = []
    for chunk in leaf.split("_"):
        if not chunk:
            continue
        # Split camelCase + letter/digit transitions into sub-tokens, keeping the
        # delimiters meaningful (FamilyName -> Family, Name; Line3a -> Line, 3a).
        sub = re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z]+|[a-z]+|\d+[a-z]?|\d+", chunk)
        out.extend(sub if sub else [chunk])
    return out


# --------------------------------------------------------------------------- #
# 2. tab order + 3. spatial clusters (geometry only)
# --------------------------------------------------------------------------- #

def _reading_order_key(rec: dict) -> tuple:
    """Sort key approximating human reading order: page, then row, then column.

    Rows are bucketed by y to a tolerance so widgets on the same visual line
    (a name split into 3 boxes) share a row band and then sort left-to-right.
    """
    r = rec["rect"]
    # Bucket y to 8pt bands so jitter within a row collapses; x within the band.
    return (r["page"], round(r["y"] / 8.0), r["x"])


def enrich(dump: dict) -> dict:
    """Augment each field with name tokens, tab order, and spatial-cluster ids."""
    # Flatten to per-widget records carrying their parent field, for geometry.
    widget_recs: list[dict] = []
    for fi, f in enumerate(dump.get("fields", [])):
        for wi, w in enumerate(f["widgets"]):
            widget_recs.append({"fi": fi, "wi": wi, "rect": w["rect"]})

    # 2. tab order: global reading-order rank.
    widget_recs.sort(key=_reading_order_key)
    for rank, rec in enumerate(widget_recs):
        f = dump["fields"][rec["fi"]]
        f["widgets"][rec["wi"]].setdefault("_tab_order", rank)

    # 3. spatial clusters: same page + same y-band = one visual row cluster.
    #    A monotonically-increasing cluster id per (page, y-band).
    row_to_cluster: dict[tuple, int] = {}
    next_cluster = 0
    for rec in widget_recs:  # already in reading order
        r = rec["rect"]
        band = (r["page"], round(r["y"] / 8.0))
        if band not in row_to_cluster:
            row_to_cluster[band] = next_cluster
            next_cluster += 1
        f = dump["fields"][rec["fi"]]
        f["widgets"][rec["wi"]].setdefault("_row_cluster", row_to_cluster[band])

    # 1. name decomposition: per logical field, from its name.
    for f in dump.get("fields", []):
        f["_name_decomp"] = decompose_name(f["name"])
        # Field-level tab order = min of its widgets' (the field's first widget).
        f["_tab_order"] = min(w.get("_tab_order", 1 << 30) for w in f["widgets"])
        f["_row_cluster"] = f["widgets"][0].get("_row_cluster")

    dump["_enriched"] = {
        "signals": ["name_decomp", "tab_order", "row_cluster"],
        "total_widgets": len(widget_recs),
        "total_row_clusters": next_cluster,
    }
    return dump


# --------------------------------------------------------------------------- #
# Prompt rendering: an enriched field list (replaces acroform_field_list)
# --------------------------------------------------------------------------- #

def enriched_field_list(dump: dict, max_fields: int | None = None) -> str:
    """Render the enriched dump as a compact text field list for the prompt.

    One line per logical field in TAB ORDER (not name order), exposing the
    generic structural signals: leaf tokens, reading-order rank, row cluster,
    page, geometry, tooltip, choices. This is the deliberately-assembled bundle
    the 7a9.9 thesis feeds the LLM in place of the USCIS heuristic output.
    """
    fields = list(dump.get("fields", []))
    fields.sort(key=lambda f: f.get("_tab_order", 1 << 30))
    if max_fields:
        fields = fields[:max_fields]

    lines = []
    for f in fields:
        w0 = f["widgets"][0]
        nd = f.get("_name_decomp", {})
        r = w0["rect"]
        bits = [
            f"name={f['name']}",
            f"type={f['logical_type']}",
            f"tab={f.get('_tab_order')}",
            f"row={f.get('_row_cluster')}",
            f"page={r['page']}",
            f"xy=({r['x']:.0f},{r['y']:.0f})",
        ]
        if f["widget_count"] > 1:
            bits.append(f"widgets={f['widget_count']}")
        toks = nd.get("leaf_tokens")
        if toks:
            bits.append("tokens=[" + ",".join(toks) + "]")
        flags = []
        for w in f["widgets"]:
            for k in ("read_only", "required", "multiline", "comb"):
                if w.get(k) and k not in flags:
                    flags.append(k)
        if flags:
            bits.append("flags=" + ",".join(flags))
        if w0.get("max_length"):
            bits.append(f"maxlen={w0['max_length']}")
        if w0.get("tu"):
            bits.append(f"tu={w0['tu']!r}")
        if w0.get("choices"):
            vals = ",".join(c["value"] for c in w0["choices"][:12])
            bits.append(f"choices=[{vals}]")
        ons = [w["on_value"] for w in f["widgets"] if w.get("on_value")]
        if ons:
            bits.append("on=" + ",".join(ons[:8]))
        lines.append("  " + " | ".join(bits))

    e = dump.get("_enriched", {})
    header = (
        f"ENRICHED FIELD LIST ({dump.get('field_count')} fields, "
        f"{dump.get('widget_count')} widgets, {dump.get('page_count')} pages; "
        f"{e.get('total_row_clusters','?')} visual rows). "
        f"Listed in TAB ORDER (human reading order). Per field: exact name "
        f"(copy verbatim into pdf_field_name), type, tab=reading-order rank, "
        f"row=shared visual-row cluster id (fields with the SAME row id sit on "
        f"one line -- candidates to consolidate or relate), page, xy, "
        f"tokens=name leaf split into generic tokens (author's own delimiters; "
        f"YOU interpret them), flags, tooltip, choices."
    )
    return header + "\n" + "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Generic structural enrichment of an AcroForm dump.")
    ap.add_argument("dump", help="path to acroform_dump.py JSON")
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--text", action="store_true", help="print the prompt field list instead of JSON")
    args = ap.parse_args(argv)

    with open(args.dump, encoding="utf-8") as fh:
        dump = json.load(fh)
    enriched = enrich(dump)

    if args.text:
        print(enriched_field_list(enriched))
        return 0

    text = json.dumps(enriched, indent=2)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            fh.write(text)
        e = enriched["_enriched"]
        print(f"[wrote {args.json_out}] {enriched['field_count']} fields, "
              f"{e['total_row_clusters']} row clusters")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
