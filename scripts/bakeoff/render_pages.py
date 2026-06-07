#!/usr/bin/env python3
"""Render PDF pages to PNG -- the OCR/layout input for the multimodal arms.

Throwaway research helper for the extractor bake-off (bd polyglot-pdf-7a9.4). The
multimodal Gemini/Claude arms read what is printed on the rendered page (the
"pixels"); this turns each PDF page into a PNG at a chosen DPI so the models see
the same visual the human author sees.

ASCII-only (cp1252 safe). Usage:

    python scripts/bakeoff/render_pages.py FORM.pdf OUTDIR [--dpi 150]
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

import fitz  # PyMuPDF


def render(path: str, outdir: str, dpi: int = 150) -> list[str]:
    os.makedirs(outdir, exist_ok=True)
    doc = fitz.open(path)
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    paths = []
    for pno in range(doc.page_count):
        pix = doc[pno].get_pixmap(matrix=mat)
        out = os.path.join(outdir, f"page_{pno:02d}.png")
        pix.save(out)
        paths.append(out)
    return paths


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Render PDF pages to PNG.")
    ap.add_argument("pdf")
    ap.add_argument("outdir")
    ap.add_argument("--dpi", type=int, default=150)
    args = ap.parse_args(argv)
    paths = render(args.pdf, args.outdir, args.dpi)
    print(f"[wrote {len(paths)} pages to {args.outdir} @ {args.dpi} dpi]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
