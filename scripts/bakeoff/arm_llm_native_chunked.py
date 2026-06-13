#!/usr/bin/env python3
"""Chunked LLM-native arm for BIG forms (bd polyglot-pdf-7a9.11).

The single-shot llm-native arm completes on I-589 (460 widgets) but
UNDER-CONSOLIDATES badly (433 draft fields vs a 156-field gold, 0/9 tables): the
model loses the consolidation thread across 460 widgets in one call. On I-90's
small pages (<=99 widgets) the SAME arm consolidates near-perfectly. Hypothesis:
chunk the form into page-sized pieces, extract each independently (where the model
consolidates well), then MERGE the per-chunk field lists into one schema.

This is a deliberately-minimal prototype: it reuses arm_llm_native.run() per page
chunk by writing a per-chunk sub-dump (fields filtered to that page range), then
concatenates the resulting field lists and unions the parts/sections. It does NOT
try to resolve cross-chunk relationships (show_if targets on another page) -- that
is left to a later pass; the question THIS prototype answers is narrow: does
per-chunk extraction fix the CONSOLIDATION (field-count / table) collapse?

Chunking unit: one PDF page per chunk (I-589's tables each sit within a page, and
no page exceeds 99 widgets -- I-90 scale). Pages with 0 widgets are skipped.

ASCII only (cp1252 safe).

Usage:
  python scripts/bakeoff/arm_llm_native_chunked.py --pdf FORM.pdf \
      --acroform DUMP.json --out OUT.json [--fewshot-truth OTHER.json]
      [--pages 0,1,2,3]   # default: all non-empty pages
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arm_llm_native as arm  # noqa: E402


def _page_subdump(dump: dict, page: int) -> dict:
    """A copy of the dump with fields filtered to widgets on `page`.

    Field/widget/page COUNTS are recomputed so the enriched header is honest for
    the chunk. The page index is preserved on each rect (the enrichment sorts by
    it), so a single-page chunk still renders correctly."""
    sub = copy.deepcopy(dump)
    sub["fields"] = [f for f in dump.get("fields", [])
                     if f["widgets"][0]["rect"]["page"] == page]
    sub["field_count"] = len(sub["fields"])
    sub["widget_count"] = sum(len(f["widgets"]) for f in sub["fields"])
    sub["page_count"] = 1
    return sub


def _merge(chunks: list[dict]) -> dict:
    """Concatenate per-chunk field lists; union parts/sections by id; collect
    supplements. Later passes resolve cross-chunk relationships -- here we just
    assemble the union so the field-level consolidation can be scored."""
    merged = {"source": "pdf", "fields": []}
    parts: dict[str, dict] = {}
    sections: dict[str, dict] = {}
    supplements: list = []
    meta = None
    for ch in chunks:
        if ch is None:
            continue
        if meta is None and ch.get("form_metadata"):
            meta = ch["form_metadata"]
        merged["fields"].extend(ch.get("fields", []))
        for p in (ch.get("parts") or []):
            if p.get("id") and p["id"] not in parts:
                parts[p["id"]] = p
        for s in (ch.get("sections") or []):
            if s.get("id") and s["id"] not in sections:
                sections[s["id"]] = s
        for sup in (ch.get("supplements") or []):
            supplements.append(sup)
    if meta:
        merged["form_metadata"] = meta
    if parts:
        merged["parts"] = list(parts.values())
    if sections:
        merged["sections"] = list(sections.values())
    if supplements:
        merged["supplements"] = supplements
    return merged


def run_chunked(pdf_path: str, acroform_path: str, model: str,
                fewshot_truth: Optional[str], pages: Optional[list[int]]) -> dict:
    with open(acroform_path, encoding="utf-8") as fh:
        dump = json.load(fh)
    all_pages = sorted({f["widgets"][0]["rect"]["page"]
                        for f in dump.get("fields", [])})
    target = pages if pages is not None else all_pages
    outputs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "outputs")
    # Derive the temp-file stem from the acroform name + PID so two concurrent
    # runs (different forms, or parallel terminals) never clobber each other.
    stem = os.path.splitext(os.path.basename(acroform_path))[0]
    chunks = []
    per_chunk_meta = []
    for pg in target:
        sub = _page_subdump(dump, pg)
        if not sub["fields"]:
            print(f"[page {pg}] 0 widgets -- skipped")
            continue
        sub_path = os.path.join(outputs_dir,
                                f"_chunk_{stem}_{os.getpid()}_p{pg:02d}.json")
        with open(sub_path, "w", encoding="utf-8") as fh:
            json.dump(sub, fh)
        print(f"[page {pg}] {sub['field_count']} widgets -> extracting...")
        try:
            schema = arm.run(pdf_path, sub_path, model,
                             fewshot_truth=fewshot_truth, send_pdf=True)
            nf = len(schema.get("fields", []))
            print(f"[page {pg}] -> {nf} logical fields")
            chunks.append(schema)
            per_chunk_meta.append({"page": pg, "widgets": sub["field_count"],
                                   "fields": nf})
        except Exception as exc:
            print(f"[page {pg}] FAILED: {str(exc)[:200]}")
            per_chunk_meta.append({"page": pg, "widgets": sub["field_count"],
                                   "error": str(exc)[:200]})
        finally:
            if os.path.exists(sub_path):
                os.remove(sub_path)
    merged = _merge(chunks)
    merged.setdefault("_bakeoff", {})
    merged["_bakeoff"].update({
        "arm": "llm-native-chunked", "model": model,
        "fewshot": bool(fewshot_truth), "chunk_unit": "page",
        "chunks": per_chunk_meta,
        "total_fields": len(merged["fields"]),
    })
    return merged


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Chunked LLM-native arm (7a9.11).")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--acroform", required=True)
    ap.add_argument("--fewshot-truth", default=None)
    ap.add_argument("--pages", default=None,
                    help="comma-separated pages (default: all non-empty)")
    ap.add_argument("--model", default="claude-opus-4-8")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    pages = ([int(p) for p in args.pages.split(",")]
             if args.pages else None)
    merged = run_chunked(args.pdf, args.acroform, args.model,
                         args.fewshot_truth, pages)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(merged, fh, indent=2)
    bo = merged["_bakeoff"]
    print(f"[wrote {args.out}] arm=llm-native-chunked fields={bo['total_fields']} "
          f"chunks={len(bo['chunks'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
