#!/usr/bin/env python3
"""Deterministic form-division derivation -- prototype (bd polyglot-pdf-6cfu.1).

Derives parts/sections for a form kit from the PDF itself, with NO LLM in the
loop. Strategy ladder (auto-selected, recorded in the output):

  1. name-convention (USCIS): widget names like P1_Line3a_FamilyName[0] carry
     part membership + item ordering directly (immune to column layout).
     Printed bold-italic sub-headings subdivide oversize parts, column-aware.
  2. printed-heading (IRS): left-margin bold headings detected from the PDF's
     text spans (per-page style census); each field belongs to the nearest
     heading above it on its page.
  3. page-fallback: no convention, no detectable headings -> page = section.

Rules common to every strategy: a section never spans pages ("(continued)");
sections over --cap fillable fields sub-split at line-item family boundaries
("X (1 of 3)"); labels come from the form's own printed text; derived
sections carry 1-based page numbers matching field pdf_position.page.

Deterministic by construction: same PDF + same schema.json -> byte-identical
output (verify with --check, which runs the derivation twice and diffs).

Usage:
    python scripts/authoring/derive_sections.py --kit form-kits/i-90 \
        [--cap 20] [--out derived.json] [--report report.md] [--check]

If the kit has no schema.json (e.g. form-kits/w9-heldout), fields are taken
straight from the deterministic AcroForm dump instead.

ASCII-only (cp1252 safe).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, OrderedDict
from typing import Any, Optional

import fitz  # PyMuPDF

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO, "scripts", "bakeoff"))
import acroform_dump  # noqa: E402


# --------------------------------------------------------------------------
# Field loading
# --------------------------------------------------------------------------

# USCIS widget-name convention: P1_Line3a_FamilyName[0] / Pt2Line4_...[1].
_USCIS_NAME_RE = re.compile(
    r"^P[t]?(?P<part>\d+)[_.]?Line(?P<item>[0-9]+[a-zA-Z0-9]*)"
    r"(?:_(?P<label>[^\[]*))?(?:\[(?P<idx>\d+)\])?$"
)
# Looser variant for the applicability test and for part-only names like
# P4_checkbox1a[0] / P6_Language[0]: the part prefix is still authoritative.
_USCIS_PART_RE = re.compile(r"^P[t]?(?P<part>\d+)[_.](?P<rest>.*)$")
# IRS widget names carry only a page + sequence counter (f1_04[0] / c2_17[0]);
# the printed-heading strategy orders fields by geometry (page, y, x), which is
# sufficient for the single-column IRS layouts. Name-sequence anchoring is the
# bead 6cfu.2 refinement if boundary precision needs tightening.


class FieldRec:
    """One schema field (or dump field in PDF-only mode) with placement."""

    __slots__ = ("fid", "name", "page", "x", "y", "current_section", "label")

    def __init__(self, fid: str, name: Optional[str], page: Optional[int],
                 x: float, y: float, current_section: Optional[str],
                 label: str) -> None:
        self.fid = fid
        self.name = name or ""
        self.page = page  # 1-based, None if unplaced
        self.x = x
        self.y = y
        self.current_section = current_section
        self.label = label


def load_fields(kit_dir: str, pdf_path: str) -> tuple[list[FieldRec], dict]:
    """Load fields from the kit schema.json, or from the AcroForm dump."""
    schema_path = os.path.join(kit_dir, "schema.json")
    if os.path.exists(schema_path):
        with open(schema_path, "r", encoding="utf-8") as fh:
            schema = json.load(fh)
        fields = []
        for f in schema.get("fields", []):
            pos = f.get("pdf_position") or {}
            fields.append(FieldRec(
                fid=f["id"],
                name=f.get("pdf_field_name"),
                page=pos.get("page"),
                x=float(pos.get("x", 0.0)),
                y=float(pos.get("y", 0.0)),
                current_section=f.get("section_id"),
                label=f.get("label") or f.get("name") or f["id"],
            ))
        return fields, schema
    # PDF-only mode: deterministic dump; dump rect pages are 0-based.
    dump = acroform_dump.dump_pdf(pdf_path)
    fields = []
    for f in dump["fields"]:
        if f["logical_type"] in ("button", "signature"):
            continue
        w0 = f["widgets"][0]["rect"]
        fields.append(FieldRec(
            fid=f["name"],
            name=f["name"],
            page=w0["page"] + 1,
            x=w0["x"],
            y=w0["y"],
            current_section=None,
            label=f["widgets"][0].get("tu") or f["name"],
        ))
    return fields, {}


# --------------------------------------------------------------------------
# Printed-text heading detection
# --------------------------------------------------------------------------

_FLAG_ITALIC = 1 << 1
_FLAG_BOLD = 1 << 4

_PART_HEAD_RE = re.compile(r"^Part\s+(\d+)\s*[.:]?\s*(.*)$")
_CONTINUED_RE = re.compile(r"\s*\(continued\)\s*$", re.IGNORECASE)

# PDF text uses typographic punctuation; labels must be ASCII (cp1252 scar).
_ASCII_MAP = {0x2018: "'", 0x2019: "'", 0x201c: '"', 0x201d: '"',
              0x2013: "-", 0x2014: "--", 0x00a0: " "}


def _ascii(text: str) -> str:
    return text.translate(_ASCII_MAP).encode("ascii", "ignore").decode("ascii")


class Heading:
    __slots__ = ("text", "level", "page", "x", "y", "size", "part_num")

    def __init__(self, text: str, level: int, page: int, x: float, y: float,
                 size: float, part_num: Optional[int] = None) -> None:
        self.text = text
        self.level = level  # 1 = part-level, 2 = section-level
        self.page = page    # 1-based
        self.x = x
        self.y = y
        self.size = size
        self.part_num = part_num


def _page_lines(page: "fitz.Page") -> list[dict]:
    """Merged text lines with style info for one page."""
    out = []
    d = page.get_text("dict")
    for block in d.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans") or []
            if not spans:
                continue
            text = _ascii("".join(s["text"] for s in spans).strip())
            if not text:
                continue
            s0 = spans[0]
            font = s0["font"]
            flags = int(s0.get("flags", 0))
            bold = bool(flags & _FLAG_BOLD) or "Bold" in font or "Bd" in font
            italic = bool(flags & _FLAG_ITALIC) or "Italic" in font or "It" in font
            out.append({
                "text": text,
                "font": font,
                "size": round(float(s0["size"]), 1),
                "bold": bold,
                "italic": italic,
                "x": round(float(line["bbox"][0]), 1),
                "y": round(float(line["bbox"][1]), 1),
            })
    out.sort(key=lambda l: (l["y"], l["x"]))
    return out


def detect_headings(doc: "fitz.Document") -> list[Heading]:
    """Deterministic printed-heading detection across the document.

    Level 1: lines matching 'Part N.' in a bold style at >= body size.
    Level 2: (a) bold-italic lines larger than body text (USCIS sub-headings);
             (b) bold left-margin lines 1-8pt larger than body text (IRS
             margin headings), with vertically adjacent same-style lines
             merged into one multi-line heading.
    """
    headings: list[Heading] = []
    for pno in range(doc.page_count):
        page = doc[pno]
        lines = _page_lines(page)
        if not lines:
            continue
        mass = Counter()
        for l in lines:
            mass[l["size"]] += len(l["text"])
        body_size = mass.most_common(1)[0][0]
        left_edge = min(l["x"] for l in lines)

        candidates = []  # (line, level, part_num)
        for l in lines:
            m = _PART_HEAD_RE.match(l["text"])
            # Strictly larger than body text: inline bold references like
            # "... use Part 8. Additional Information." are body-sized.
            if m and l["bold"] and l["size"] > body_size:
                candidates.append((l, 1, int(m.group(1))))
                continue
            if not l["bold"] or len(l["text"]) > 60:
                continue
            oversize = l["size"] - body_size
            if oversize < 1.0 or oversize > 8.0:
                continue
            if l["italic"]:
                candidates.append((l, 2, None))
            elif l["x"] <= left_edge + 20.0:
                candidates.append((l, 2, None))

        # Merge vertically adjacent same-style candidates: multi-line margin
        # headings ("Applicant's / Mailing / Address") and the wrapped tail of
        # a part heading ("Part 4. Accommodations for Individuals with /
        # Disabilities and/or Impairments").
        merged: list[dict] = []
        for l, level, part_num in candidates:
            # Search back for a mergeable predecessor: a right-column line can
            # interleave (by y) between the lines of a left-column heading.
            target = None
            if level == 2 and part_num is None:
                for prev in reversed(merged):
                    # 1.3x line-height: intra-heading leading runs 1.0-1.2x
                    # (w7 "Applicant's / Mailing / Address"), while two
                    # DISTINCT stacked headings sit >= 1.35x apart (w7 "Birth
                    # Information" vs "Other Information" at 1.37x).
                    if (prev["font"] == l["font"] and prev["size"] == l["size"]
                            and abs(prev["x"] - l["x"]) <= 6.0
                            and 0 < (l["y"] - prev["last_y"]) <= 1.3 * l["size"]):
                        target = prev
                        break
            if target is not None:
                target["text"] += " " + l["text"]
                target["last_y"] = l["y"]
                continue
            merged.append({
                "text": l["text"], "font": l["font"], "size": l["size"],
                "x": l["x"], "y": l["y"], "last_y": l["y"],
                "level": level, "part_num": part_num,
            })

        for m in merged:
            headings.append(Heading(
                text=m["text"], level=m["level"], page=pno + 1,
                x=m["x"], y=m["y"], size=m["size"], part_num=m["part_num"],
            ))
    return headings


# --------------------------------------------------------------------------
# Strategy selection
# --------------------------------------------------------------------------

def pick_strategy(fields: list[FieldRec], headings: list[Heading]) -> str:
    named = [f for f in fields if f.name]
    if named:
        share = sum(1 for f in named if _USCIS_PART_RE.match(f.name)) / len(named)
        if share >= 0.8:
            return "name-convention"
    if any(h.level == 2 for h in headings):
        return "printed-heading"
    return "page-fallback"


# --------------------------------------------------------------------------
# Ordering / family keys
# --------------------------------------------------------------------------

def _item_key(item: str, idx: str) -> tuple:
    """Natural sort key for a Line item like '3a' / '12' / '2g1'."""
    tokens: list = []
    for tok in re.findall(r"\d+|[a-zA-Z]+", item):
        tokens.append(int(tok) if tok.isdigit() else tok.lower())
    line_num = tokens[0] if tokens and isinstance(tokens[0], int) else 0
    return (line_num, int(idx or 0), tuple(tokens[1:]))


def uscis_parse(name: str) -> Optional[dict]:
    m = _USCIS_NAME_RE.match(name or "")
    if m:
        key = _item_key(m.group("item"), m.group("idx") or "0")
        return {
            "part": int(m.group("part")),
            "order_key": key,
            "family": (key[0], key[1]),  # (line number, repeat index)
        }
    # Part-only names (P4_checkbox1a[0], P6_Language[0]): the part prefix is
    # authoritative; take the item from the first digit run in the rest, if
    # any, else sort to the end of the part (geometry breaks the tie).
    m = _USCIS_PART_RE.match(name or "")
    if not m:
        return None
    rest = m.group("rest")
    im = re.search(r"(\d+[a-zA-Z0-9]*?)(?:\[(\d+)\])?$", rest.split("[")[0]) \
        if rest else None
    if im:
        key = _item_key(im.group(1), "0")
    else:
        key = (10 ** 5, 0, ())
    return {
        "part": int(m.group("part")),
        "order_key": key,
        "family": (key[0], key[1]),
    }


def _row_family(f: FieldRec) -> tuple:
    """Family key for IRS/fallback: fields on the same printed row."""
    return (f.page, int(round(f.y / 4.0)))


# --------------------------------------------------------------------------
# Section assembly
# --------------------------------------------------------------------------

def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s[:48] or "section"


class DerivedSection:
    def __init__(self, label: str, page: int, part_key: Any,
                 fields: list[FieldRec]) -> None:
        self.label = label
        self.page = page
        self.part_key = part_key  # groups sections into parts
        self.part_label = ""
        self.fields = fields


def _cap_split(sections: list[DerivedSection], fields_family, cap: int
               ) -> tuple[list[DerivedSection], list[str]]:
    """Split oversize sections at family boundaries. Deterministic."""
    out: list[DerivedSection] = []
    notes: list[str] = []
    for sec in sections:
        if len(sec.fields) <= cap:
            out.append(sec)
            continue
        # Contiguous runs sharing a family key never split.
        runs: list[list[FieldRec]] = []
        for f in sec.fields:
            fam = fields_family(f)
            if runs and fields_family(runs[-1][-1]) == fam:
                runs[-1].append(f)
            else:
                runs.append([f])
        chunks: list[list[FieldRec]] = [[]]
        for run in runs:
            if chunks[-1] and len(chunks[-1]) + len(run) > cap:
                chunks.append([])
            chunks[-1].extend(run)
            if len(run) > cap:
                notes.append(
                    f"family run of {len(run)} fields exceeds cap {cap} in "
                    f"'{sec.label}' (kept whole)")
        n = len(chunks)
        if n == 1:
            out.append(sec)
            continue
        notes.append(f"'{sec.label}' ({len(sec.fields)} fields) cap-split "
                     f"into {n}")
        for i, chunk in enumerate(chunks, start=1):
            part = DerivedSection(f"{sec.label} ({i} of {n})", sec.page,
                                  sec.part_key, chunk)
            part.part_label = sec.part_label
            out.append(part)
    return out, notes


def derive(fields: list[FieldRec], headings: list[Heading], strategy: str,
           cap: int, page_count: int, page_width: float
           ) -> tuple[list[DerivedSection], list[FieldRec], list[str]]:
    """Return (ordered sections, unassigned fields, notes)."""
    notes: list[str] = []
    placed = [f for f in fields if f.page is not None]
    unassigned = [f for f in fields if f.page is None]
    if unassigned:
        notes.append(f"{len(unassigned)} fields have no pdf_position "
                     f"(listed in the report)")

    if strategy == "name-convention":
        part_labels: dict[int, str] = {}
        for h in headings:
            if h.level == 1 and h.part_num is not None:
                text = _CONTINUED_RE.sub("", h.text)
                # Prefer the longest text seen for the part: a heading that
                # wraps at a column edge may be truncated at its first
                # occurrence but printed in full on a continuation page.
                if len(text) > len(part_labels.get(h.part_num, "")):
                    part_labels[h.part_num] = text
        subheads = [h for h in headings if h.level == 2]
        partheads = [h for h in headings if h.level == 1]

        def field_subhead(f: FieldRec) -> Optional[Heading]:
            col = 0 if f.x < page_width / 2 else 1
            best = None
            for h in subheads:
                hcol = 0 if h.x < page_width / 2 else 1
                # Tolerance 0.6x heading size: the first field row of a
                # section often has its rect top a few points above the
                # heading's baseline.
                if h.page == f.page and hcol == col and h.y <= f.y + 0.6 * h.size:
                    if best is None or h.y > best.y:
                        best = h
            if best is None:
                return None
            # A part heading BETWEEN the sub-heading and the field (same
            # column) invalidates it: the field opens a new part whose first
            # items have no sub-heading of their own.
            for h in partheads:
                hcol = 0 if h.x < page_width / 2 else 1
                if (h.page == f.page and hcol == col
                        and best.y < h.y <= f.y + 0.6 * h.size):
                    return None
            return best

        buckets: "OrderedDict[tuple, list[FieldRec]]" = OrderedDict()
        parsed: dict[str, dict] = {}
        strays: list[FieldRec] = []
        for f in placed:
            p = uscis_parse(f.name)
            if p is None:
                strays.append(f)
                continue
            parsed[f.fid] = p
            sub = field_subhead(f)
            key = (p["part"], f.page, sub.text if sub else None)
            buckets.setdefault(key, []).append(f)
        if strays:
            unnamed = sum(1 for f in strays if not f.name)
            notes.append(
                f"{len(strays)} fields filed per page under 'Other items' "
                f"({unnamed} have no pdf_field_name in the kit, "
                f"{len(strays) - unnamed} do not match the USCIS pattern)")
            for f in strays:
                buckets.setdefault((10 ** 6, f.page, None), []).append(f)

        for key, flds in buckets.items():
            flds.sort(key=lambda f: (parsed[f.fid]["order_key"], f.y, f.x, f.fid)
                      if f.fid in parsed else ((10 ** 6,), f.y, f.x, f.fid))

        def bucket_order(item):
            # Page first (sections never span pages; navigation follows the
            # physical document), then part, then the part's item order.
            (part, page, sub), flds = item
            first = flds[0]
            ok = parsed[first.fid]["order_key"] if first.fid in parsed else (10 ** 6,)
            return (page, part, ok, first.y)

        sections: list[DerivedSection] = []
        part_first_page: dict[int, int] = {}
        for (part, page, sub), flds in sorted(buckets.items(), key=bucket_order):
            plabel = part_labels.get(part, f"Part {part}") if part < 10 ** 6 \
                else "Other items"
            first_page = part_first_page.setdefault(part, page)
            if sub:
                label = sub
            elif part >= 10 ** 6:
                label = f"{plabel} (page {page})"
            else:
                label = plabel if page == first_page else f"{plabel} (continued)"
            sec = DerivedSection(label, page, part, flds)
            sec.part_label = plabel
            sections.append(sec)

        def family(f: FieldRec) -> tuple:
            p = parsed.get(f.fid)
            return (f.page,) + p["family"] if p else _row_family(f)

        sections, split_notes = _cap_split(sections, family, cap)
        return sections, unassigned, notes + split_notes

    if strategy == "printed-heading":
        heads = sorted([h for h in headings if h.level == 2],
                       key=lambda h: (h.page, h.y, h.x))

        def field_head(f: FieldRec) -> Optional[Heading]:
            best = None
            for h in heads:
                # Tolerance 0.6x heading size (see field_subhead note).
                if h.page == f.page and h.y <= f.y + 0.6 * h.size:
                    if best is None or h.y > best.y:
                        best = h
            return best

        buckets: "OrderedDict[tuple, list[FieldRec]]" = OrderedDict()
        for f in sorted(placed, key=lambda f: (f.page, f.y, f.x, f.fid)):
            h = field_head(f)
            key = (f.page, h.y if h else -1.0, h.text if h else None)
            buckets.setdefault(key, []).append(f)

        sections = []
        for (page, _hy, text) in sorted(buckets.keys()):
            flds = buckets[(page, _hy, text)]
            label = _CONTINUED_RE.sub("", text) if text else f"Page {page} (top)"
            sec = DerivedSection(label, page, page, flds)
            sec.part_label = f"Page {page}"
            sections.append(sec)
        sections, split_notes = _cap_split(sections, _row_family, cap)
        return sections, unassigned, notes + split_notes

    # page-fallback
    buckets = OrderedDict()
    for f in sorted(placed, key=lambda f: (f.page, f.y, f.x, f.fid)):
        buckets.setdefault(f.page, []).append(f)
    sections = []
    for page, flds in sorted(buckets.items()):
        sec = DerivedSection(f"Page {page}", page, page, flds)
        sec.part_label = f"Page {page}"
        sections.append(sec)
    sections, split_notes = _cap_split(sections, _row_family, cap)
    return sections, unassigned, notes + split_notes


# --------------------------------------------------------------------------
# Output assembly
# --------------------------------------------------------------------------

def build_output(form_id: str, strategy: str, sections: list[DerivedSection],
                 unassigned: list[FieldRec], notes: list[str], cap: int
                 ) -> dict:
    used_ids: set = set()
    parts: "OrderedDict[Any, dict]" = OrderedDict()
    out_sections = []
    for order, sec in enumerate(sections, start=1):
        base = f"sec_{_slug(sec.label)}_p{sec.page}"
        sid = base
        n = 2
        while sid in used_ids:
            sid = f"{base}_{n}"
            n += 1
        used_ids.add(sid)
        if sec.part_key not in parts:
            pid = f"part_{_slug(sec.part_label)}"
            parts[sec.part_key] = {
                "id": pid, "label": sec.part_label,
                "order": len(parts) + 1, "section_ids": [],
            }
        parts[sec.part_key]["section_ids"].append(sid)
        out_sections.append({
            "id": sid,
            "label": sec.label,
            "order": order,
            "page_number": sec.page,
            "page_numbers": [sec.page],
            "fields": [f.fid for f in sec.fields],
        })
    return {
        "form_id": form_id,
        "division_strategy": strategy,
        "cap": cap,
        "parts": list(parts.values()),
        "sections": out_sections,
        "unassigned_fields": [f.fid for f in unassigned],
        "notes": notes,
    }


def compare_report(form_id: str, out: dict, fields: list[FieldRec],
                   schema: dict, headings: list[Heading]) -> str:
    """Markdown comparison of derived vs current kit sections."""
    cur_by_field = {f.fid: (f.current_section or "-") for f in fields}
    cur_labels = {s["id"]: s.get("label", s["id"])
                  for s in schema.get("sections", [])}
    lines = []
    lines.append(f"## {form_id}")
    lines.append("")
    lines.append(f"- strategy: **{out['division_strategy']}**")
    lines.append(f"- derived: {len(out['parts'])} parts / "
                 f"{len(out['sections'])} sections; current kit: "
                 f"{len(schema.get('parts') or [])} parts / "
                 f"{len(schema.get('sections') or [])} sections")
    heads2 = [h for h in headings if h.level == 2]
    heads1 = [h for h in headings if h.level == 1]
    if heads1:
        lines.append(f"- part headings detected: "
                     + "; ".join(f"p{h.page} '{h.text}'" for h in heads1))
    if heads2:
        lines.append(f"- section headings detected: "
                     + "; ".join(f"p{h.page} '{h.text}'" for h in heads2))
    for note in out["notes"]:
        lines.append(f"- NOTE: {note}")
    lines.append("")
    lines.append("| # | derived section | page | fields | drawn from (current kit sections) |")
    lines.append("|---|-----------------|------|--------|-----------------------------------|")
    for sec in out["sections"]:
        srcs = Counter(cur_by_field.get(fid, "-") for fid in sec["fields"])
        src_txt = ", ".join(
            f"{cur_labels.get(sid, sid)} ({n})"
            for sid, n in sorted(srcs.items(), key=lambda kv: (-kv[1], kv[0])))
        lines.append(f"| {sec['order']} | {sec['label']} | {sec['page_number']}"
                     f" | {len(sec['fields'])} | {src_txt} |")
    if out["unassigned_fields"]:
        lines.append("")
        lines.append(f"Unassigned (no pdf_position): "
                     + ", ".join(out["unassigned_fields"]))
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def run(kit_dir: str, cap: int) -> tuple[dict, str]:
    pdf_path = os.path.join(kit_dir, "form.pdf")
    if not os.path.exists(pdf_path):
        raise SystemExit(f"no form.pdf in {kit_dir}")
    form_id = os.path.basename(os.path.normpath(kit_dir))
    fields, schema = load_fields(kit_dir, pdf_path)
    doc = fitz.open(pdf_path)
    headings = detect_headings(doc)
    strategy = pick_strategy(fields, headings)
    sections, unassigned, notes = derive(
        fields, headings, strategy, cap,
        doc.page_count, float(doc[0].rect.width))
    doc.close()
    out = build_output(form_id, strategy, sections, unassigned, notes, cap)
    report = compare_report(form_id, out, fields, schema, headings)
    return out, report


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Deterministic form-division derivation (prototype).")
    ap.add_argument("--kit", required=True, help="form-kit directory")
    ap.add_argument("--cap", type=int, default=20,
                    help="max fillable fields per section (default 20)")
    ap.add_argument("--out", default=None, help="write derived JSON here")
    ap.add_argument("--report", default=None, help="write markdown report here")
    ap.add_argument("--check", action="store_true",
                    help="run twice and verify byte-identical output")
    args = ap.parse_args(argv)

    out, report = run(args.kit, args.cap)
    text = json.dumps(out, indent=2)
    if args.check:
        out2, _ = run(args.kit, args.cap)
        if json.dumps(out2, indent=2) != text:
            print("DETERMINISM CHECK FAILED", file=sys.stderr)
            return 1
        print("[determinism check: byte-identical across two runs]")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"[wrote {args.out}]")
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            fh.write(report)
        print(f"[wrote {args.report}]")
    if not args.out and not args.report:
        print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
