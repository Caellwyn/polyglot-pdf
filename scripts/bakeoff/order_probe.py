#!/usr/bin/env python3
"""Reading-order probe: let the model call the human order from an annotated page.

bd polyglot-pdf-7a9.10 (maintainer steer, 2026-06-12). The mechanical geometric
sweep (structural_enrich.py's reading-order rank) provably scrambles multi-column
pages -- and asking the model to RECONCILE that sweep against the pixels measurably
hurt extraction. This plays to the model's actual strength instead: give Opus an
annotated page image (each widget tagged with a short numeric marker) plus a
tag->field-name legend, and ask the ONE question it is genuinely good at -- "what
order would a human read these fields in?" The model returns the tags in reading
order; we map tags back to field names and score that order against the gold
schema's authored order (its array order, cross-checked by question_number).

This is a focused ORDERING experiment, not a full extractor arm: it isolates
whether model-judged visual order beats the deterministic sweep. Throwaway
research output (annotated PDFs/PNGs + per-page model answers are gitignored).

Pipeline per page:
  1. annotate_page(): draw a small numbered box at each widget rect; build the
     tag->pdf_field_name legend (tags are page-local: 1..N).
  2. render to PNG (via render_pages helper / fitz).
  3. ask_order(): Claude CLI reads the PNG and returns the tags in human order.
  4. score_order(): compare model tag-order to gold order (Kendall tau + the
     exact-adjacency and head/tail agreement), restricted to fields present on
     that page.

Usage:
  python scripts/bakeoff/order_probe.py --pdf form-kits/i-90/form.pdf \
      --acroform scripts/bakeoff/outputs/i90_acroform.json \
      --truth form-kits/i-90/schema.json \
      --pages 0,2,4 --outdir scripts/bakeoff/outputs/order_probe

ASCII only (cp1252 safe).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from typing import Optional

import fitz  # PyMuPDF


# --------------------------------------------------------------------------- #
# 1. annotate: numbered markers + legend
# --------------------------------------------------------------------------- #

def _page_widgets(dump: dict, page: int) -> list[dict]:
    """Logical fields whose first widget is on `page`, in dump (name) order.

    One marker per LOGICAL field (not per widget) -- a consolidated radio set
    gets a single tag at its first widget, matching how the gold orders fields.
    """
    recs = []
    for f in dump.get("fields", []):
        w0 = f["widgets"][0]
        if w0["rect"]["page"] == page:
            recs.append({"name": f["name"], "rect": w0["rect"]})
    return recs


def annotate_page(pdf_path: str, dump: dict, page: int, out_pdf: str,
                  font_size: int = 9) -> list[dict]:
    """Draw a numbered marker at each field on `page`; return the tag legend.

    Returns a list of {tag, name, x, y} (tag is the 1-based page-local marker).
    Markers are placed at the field's top-left so they do not hide the field
    contents; a colored box border outlines each field.
    """
    recs = _page_widgets(dump, page)
    doc = fitz.open(pdf_path)
    pg = doc[page]
    legend = []
    for i, rec in enumerate(recs, start=1):
        r = rec["rect"]
        rect = fitz.Rect(r["x"], r["y"], r["x"] + r["width"], r["y"] + r["height"])
        # marker box at top-left corner of the field
        tag = str(i)
        bw = 6 + len(tag) * font_size * 0.55
        mk = fitz.Rect(rect.x0 - 1, rect.y0 - 1, rect.x0 - 1 + bw,
                       rect.y0 - 1 + font_size + 3)
        pg.draw_rect(mk, color=(1, 0, 0), fill=(1, 1, 0.7), width=0.4, overlay=True)
        pg.insert_text(fitz.Point(mk.x0 + 2, mk.y0 + font_size),
                       tag, fontsize=font_size, color=(0.8, 0, 0),
                       fontname="helv", overlay=True)
        pg.draw_rect(rect, color=(1, 0, 0), width=0.4, overlay=True)
        legend.append({"tag": i, "name": rec["name"],
                       "x": round(r["x"], 1), "y": round(r["y"], 1)})
    doc.save(out_pdf)
    doc.close()
    return legend


def render_pdf_page(pdf_path: str, page: int, out_png: str, dpi: int = 150) -> None:
    doc = fitz.open(pdf_path)
    pix = doc[page].get_pixmap(dpi=dpi)
    pix.save(out_png)
    doc.close()


# --------------------------------------------------------------------------- #
# 2. ask the model for the human reading order
# --------------------------------------------------------------------------- #

ORDER_PROMPT = """\
You are looking at one page of a government form. Every fillable field on the
page has been outlined in red and labeled with a small numbered marker (a red
number in a yellow box at the field's top-left corner).

Your task: put the markers in the order a HUMAN would naturally fill out this
page -- the intuitive reading/answering order, following the form's visual
layout, columns, numbered questions, and grouping. Use your judgment about how a
person actually reads this page; do not just sweep top-to-bottom ignoring
columns.

Return ONLY a JSON array of the marker numbers in that human order, e.g.
[1, 2, 5, 3, 4, ...]. Include every marker exactly once. No prose, no other keys.

The page image is at: {png}
The markers map to these internal field ids (for your reference only -- you order
by VISUAL layout, not by these names):
{legend}
"""


def _extract_json_array(text: str):
    import re
    t = text.strip()
    m = re.search(r"\[[\s\d,]+\]", t)
    if m:
        return json.loads(m.group(0))
    return json.loads(t)


def ask_order(png_path: str, legend: list[dict], model: str,
              add_dirs: list[str]) -> list[int]:
    """Ask the Claude CLI to return the page's markers in human reading order."""
    exe = shutil.which("claude") or "claude"
    legend_txt = "\n".join(f"  marker {l['tag']} -> {l['name']}" for l in legend)
    prompt = ORDER_PROMPT.format(png=os.path.abspath(png_path), legend=legend_txt)
    cmd = [exe, "-p", "--model", model, "--output-format", "json",
           "--permission-mode", "acceptEdits"]
    for d in add_dirs:
        cmd += ["--add-dir", d]
    timeout_s = int(os.getenv("BAKEOFF_CLAUDE_TIMEOUT_S", "600"))
    proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                          encoding="utf-8", timeout=timeout_s)
    if proc.returncode != 0:
        raise RuntimeError(f"claude CLI exited {proc.returncode}: "
                           f"{(proc.stderr or proc.stdout)[:400]}")
    env = json.loads(proc.stdout)
    if env.get("is_error"):
        raise RuntimeError(f"claude CLI error: {env.get('result')!r}")
    return _extract_json_array(env.get("result", ""))


# --------------------------------------------------------------------------- #
# 3. score model order vs gold order vs the deterministic sweep
# --------------------------------------------------------------------------- #

def _kendall_tau(order_a: list, order_b: list) -> Optional[float]:
    """Kendall tau-b over the items common to both orders (range -1..1)."""
    common = [x for x in order_a if x in set(order_b)]
    rank_b = {x: i for i, x in enumerate(order_b)}
    seq = [rank_b[x] for x in common]
    n = len(seq)
    if n < 2:
        return None
    conc = disc = 0
    for i in range(n):
        for j in range(i + 1, n):
            if seq[i] < seq[j]:
                conc += 1
            elif seq[i] > seq[j]:
                disc += 1
    total = conc + disc
    return (conc - disc) / total if total else None


def _leaf(name: str) -> str:
    """Last dotted segment -- the gold uses leaf names (P1_Line1_AlienNumber[0])
    while the dump uses the full XFA path (form1[0].#subform[0].<leaf>)."""
    return name.split(".")[-1] if name else name


def gold_page_order(truth: dict, page_names: list[str]) -> list[str]:
    """Gold LEAF names that appear on this page, in the gold's authored order.

    Returns leaf names (canonicalized) so the result is comparable to the
    sweep/model orders after they are leaf-canonicalized too. The gold lists one
    logical field per entry; match by any of its widget pdf_field_names
    (consolidated fields carry several)."""
    page_leaves = set(_leaf(n) for n in page_names)
    out = []
    for f in truth.get("fields", []):
        pfns = []
        if f.get("pdf_field_name"):
            pfns.append(f["pdf_field_name"])
        for o in (f.get("options") or []):
            if o.get("pdf_field_name"):
                pfns.append(o["pdf_field_name"])
        for w in (f.get("consolidated_widgets") or []):
            if isinstance(w, str):
                pfns.append(w)
            elif isinstance(w, dict) and w.get("pdf_field_name"):
                pfns.append(w["pdf_field_name"])
        leaves = [_leaf(p) for p in pfns]
        first = next((lf for lf in leaves if lf in page_leaves), None)
        if first:
            out.append(first)
    return out


def score_order(model_tags: list[int], legend: list[dict],
                truth: dict, sweep_names: list[str]) -> dict:
    """Compare model order, sweep order, and gold order by Kendall tau."""
    tag2name = {l["tag"]: l["name"] for l in legend}
    model_leaves = [_leaf(tag2name[t]) for t in model_tags if t in tag2name]
    sweep_leaves = [_leaf(n) for n in sweep_names]
    page_names = [l["name"] for l in legend]
    gold = gold_page_order(truth, page_names)  # already leaves
    return {
        "n_fields_page": len(page_names),
        "n_model": len(model_leaves),
        "n_gold_matched": len(gold),
        "tau_model_vs_gold": _kendall_tau(model_leaves, gold),
        "tau_sweep_vs_gold": _kendall_tau(sweep_leaves, gold),
        "model_order": model_leaves,
        "gold_order": gold,
    }


def sweep_page_order(dump: dict, page: int) -> list[str]:
    """The deterministic geometric-sweep order for this page (the baseline)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from structural_enrich import enrich  # noqa: E402
    enrich(dump, disabled=frozenset())  # full bundle just to get _tab_order
    recs = [f for f in dump["fields"] if f["widgets"][0]["rect"]["page"] == page]
    recs.sort(key=lambda f: f.get("_tab_order", 1 << 30))
    return [f["name"] for f in recs]


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Reading-order probe (bd 7a9.10).")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--acroform", required=True)
    ap.add_argument("--truth", required=True)
    ap.add_argument("--pages", required=True, help="comma-separated 0-based pages")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--model", default="claude-opus-4-8")
    ap.add_argument("--dpi", type=int, default=150)
    args = ap.parse_args(argv)

    os.makedirs(args.outdir, exist_ok=True)
    with open(args.acroform, encoding="utf-8") as fh:
        dump = json.load(fh)
    with open(args.truth, encoding="utf-8") as fh:
        truth = json.load(fh)
    pages = [int(p) for p in args.pages.split(",")]
    pdf_dir = os.path.dirname(os.path.abspath(args.pdf))

    results = []
    for pg in pages:
        ann_pdf = os.path.join(args.outdir, f"page_{pg:02d}_annotated.pdf")
        png = os.path.join(args.outdir, f"page_{pg:02d}_annotated.png")
        legend = annotate_page(args.pdf, json.loads(json.dumps(dump)), pg, ann_pdf)
        render_pdf_page(ann_pdf, 0, png, dpi=args.dpi)
        sweep = sweep_page_order(json.loads(json.dumps(dump)), pg)
        try:
            model_tags = ask_order(png, legend, args.model,
                                   add_dirs=[os.path.abspath(args.outdir), pdf_dir])
            sc = score_order(model_tags, legend, truth, sweep)
            sc["page"] = pg
            sc["status"] = "ok"
        except Exception as e:  # keep going across pages
            sc = {"page": pg, "status": "error", "error": str(e)[:300]}
        results.append(sc)
        tm = sc.get("tau_model_vs_gold")
        ts = sc.get("tau_sweep_vs_gold")
        print(f"[page {pg}] status={sc['status']} "
              f"tau model-vs-gold={tm if tm is None else round(tm,3)} "
              f"sweep-vs-gold={ts if ts is None else round(ts,3)} "
              f"(n={sc.get('n_fields_page')})")

    out_json = os.path.join(args.outdir, "order_probe_results.json")
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)
    print(f"[wrote {out_json}]")
    # headline
    oks = [r for r in results if r["status"] == "ok"
           and r.get("tau_model_vs_gold") is not None]
    if oks:
        import statistics as st
        mm = st.median(r["tau_model_vs_gold"] for r in oks)
        ss = st.median(r["tau_sweep_vs_gold"] for r in oks
                       if r.get("tau_sweep_vs_gold") is not None)
        print(f"MEDIAN tau: model={mm:.3f}  sweep={ss:.3f}  "
              f"(higher = closer to human gold order; {len(oks)} pages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
