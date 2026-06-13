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

Per-signal ablation (bd polyglot-pdf-7a9.10): pass disabled={...} to enrich()/
enriched_field_list() (or --disable on the CLI) to drop a signal from both the
computation and the prompt rendering. With tab_order disabled the field list
falls back to dump (name) order -- the same order the baseline hybrid arm uses.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any, Optional

# The ablatable signal names (bd 7a9.10).
SIGNALS = ("name_decomp", "tab_order", "row_cluster")

# Signals DROPPED from the default render after the 7a9.10 ablation on I-90:
# row_cluster earned no (a) accuracy and was a net-negative on (b) relationship
# recall (it correlated with the worst show_if recall when isolated). The other
# two signals stay. The full ablation can still re-enable it: enrich(dump,
# disabled=frozenset()). See docs/research/2026-06-12-7a9.10-*-findings.md.
DEFAULT_DISABLED = frozenset({"row_cluster"})


# --------------------------------------------------------------------------- #
# 1. name-token decomposition (generic, no USCIS mapping)
# --------------------------------------------------------------------------- #

def decompose_name(full_name: str) -> dict[str, Any]:
    """Split an XFA dotted widget name into structural tokens, no interpretation.

    Example: 'form1[0].#subform[0].P1_Line3a_FamilyName[0]' ->
      {
        "path": ["form1", "#subform"],     # container subforms (everything but leaf)
        "leaf": "P1_Line3a_FamilyName",    # the meaningful local name
        "leaf_tokens": ["P", "1", "Line", "3a", "Family", "Name"],  # leaf split
                                           # on _ AND case/digit boundaries
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


def enrich(dump: dict, disabled: frozenset[str] = DEFAULT_DISABLED) -> dict:
    """Augment each field with name tokens, reading-order rank, and (optionally)
    visual-row-cluster ids.

    `disabled` names signals (from SIGNALS) to SKIP -- the ablation knob
    (bd 7a9.10). A disabled signal is neither computed nor rendered. The DEFAULT
    drops `row_cluster` (DEFAULT_DISABLED) per the 7a9.10 trim; pass
    `disabled=frozenset()` to re-enable the full bundle for ablation.
    """
    # Flatten to per-widget records carrying their parent field, for geometry.
    widget_recs: list[dict] = []
    for fi, f in enumerate(dump.get("fields", [])):
        for wi, w in enumerate(f["widgets"]):
            widget_recs.append({"fi": fi, "wi": wi, "rect": w["rect"]})

    # Reading-order sort underpins BOTH geometry signals (rank assignment and
    # deterministic cluster-id numbering), so it always runs.
    widget_recs.sort(key=_reading_order_key)

    # 2. tab order: global reading-order rank.
    if "tab_order" not in disabled:
        for rank, rec in enumerate(widget_recs):
            f = dump["fields"][rec["fi"]]
            f["widgets"][rec["wi"]].setdefault("_tab_order", rank)

    # 3. spatial clusters: same page + same y-band = one visual row cluster.
    #    A monotonically-increasing cluster id per (page, y-band).
    next_cluster = 0
    if "row_cluster" not in disabled:
        row_to_cluster: dict[tuple, int] = {}
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
        if "name_decomp" not in disabled:
            f["_name_decomp"] = decompose_name(f["name"])
        if "tab_order" not in disabled:
            # Field-level tab order = the EARLIEST reading-order rank among its
            # widgets (a multi-widget group is reached when its first widget is).
            f["_tab_order"] = min(w.get("_tab_order", 1 << 30) for w in f["widgets"])
        if "row_cluster" not in disabled:
            f["_row_cluster"] = f["widgets"][0].get("_row_cluster")

    dump["_enriched"] = {
        "signals": [s for s in SIGNALS if s not in disabled],
        "disabled": sorted(disabled),
        "total_widgets": len(widget_recs),
        "total_row_clusters": next_cluster,
    }
    return dump


# --------------------------------------------------------------------------- #
# Prompt rendering: an enriched field list (replaces acroform_field_list)
# --------------------------------------------------------------------------- #

def enriched_field_list(dump: dict, max_fields: int | None = None,
                        order_caveat: bool = True) -> str:
    """Render the enriched dump as a compact text field list for the prompt.

    One line per logical field in geometric-sweep order (NOT name order),
    exposing the generic structural signals: leaf tokens, sweep rank, (optional)
    row cluster, page, geometry, tooltip, choices. `order_caveat` (DEFAULT True
    per the 7a9.10 maintainer steer) labels the sweep rank honestly as a
    mechanical geometric sweep that interleaves columns on multi-column pages,
    rather than claiming it is human reading order. This is the assembled bundle
    the 7a9.9 thesis feeds the LLM in place of the USCIS heuristic output.
    """
    enabled = set(dump.get("_enriched", {}).get("signals", SIGNALS))

    fields = list(dump.get("fields", []))
    # With tab_order disabled every key is the same -> stable sort keeps dump
    # (name) order, matching the baseline hybrid arm's list order.
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
        ]
        if "tab_order" in enabled:
            key = "sweep" if order_caveat else "tab"
            bits.append(f"{key}={f.get('_tab_order')}")
        if "row_cluster" in enabled:
            bits.append(f"row={f.get('_row_cluster')}")
        bits += [
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
    head_bits = [
        f"ENRICHED FIELD LIST ({dump.get('field_count')} fields, "
        f"{dump.get('widget_count')} widgets, {dump.get('page_count')} pages"
    ]
    if "row_cluster" in enabled:
        head_bits.append(f"; {e.get('total_row_clusters','?')} visual rows")
    head_bits.append("). ")
    if "tab_order" not in enabled:
        head_bits.append("Listed in source (name) order. ")
    elif order_caveat:
        # Honest-but-light framing (bd 7a9.10): name the order accurately
        # without telling the model to DISTRUST it. The heavier "this is wrong,
        # re-derive it yourself" caveat measurably raised spurious-field churn
        # on I-90 by suppressing the consolidation cue; this wording keeps the
        # truthful label and the useful locality hint.
        head_bits.append(
            "Listed in GEOMETRIC LAYOUT order (top-to-bottom, then "
            "left-to-right by position); on multi-column pages this may not "
            "match human reading order, so use page + xy as the source of "
            "truth for layout. "
        )
    else:
        head_bits.append("Listed in TAB ORDER (human reading order). ")
    head_bits.append(
        "Per field: exact name (copy verbatim into pdf_field_name), type"
    )
    if "tab_order" in enabled:
        head_bits.append(", sweep=geometric-sweep rank" if order_caveat
                         else ", tab=reading-order rank")
    if "row_cluster" in enabled:
        head_bits.append(
            ", row=shared visual-row cluster id (fields with the SAME row id "
            "sit on one line -- candidates to consolidate or relate)"
        )
    head_bits.append(", page, xy")
    if "name_decomp" in enabled:
        head_bits.append(
            ", tokens=name leaf split into generic tokens (author's own "
            "delimiters; YOU interpret them)"
        )
    head_bits.append(", flags, tooltip, choices.")
    return "".join(head_bits) + "\n" + "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Generic structural enrichment of an AcroForm dump.")
    ap.add_argument("dump", help="path to acroform_dump.py JSON")
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--text", action="store_true", help="print the prompt field list instead of JSON")
    ap.add_argument("--disable", action="append", choices=SIGNALS, default=None,
                    help="ablation: drop this signal on top of the default trim "
                         "(repeatable)")
    ap.add_argument("--full-bundle", action="store_true",
                    help="re-enable ALL signals incl. row_cluster (undo the "
                         "7a9.10 default trim)")
    args = ap.parse_args(argv)

    if args.full_bundle:
        disabled = frozenset(args.disable or [])
    else:
        disabled = DEFAULT_DISABLED | frozenset(args.disable or [])

    with open(args.dump, encoding="utf-8") as fh:
        dump = json.load(fh)
    enriched = enrich(dump, disabled=disabled)

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
