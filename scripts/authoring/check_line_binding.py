#!/usr/bin/env python3
"""Line-marker binding oracle: does each field claim the widget on ITS printed line?

The failure class this exists for (three shipped instances so far -- bd 13vo
i-90, bd ivh9 w7, bd polyglot-pdf-3ave f1040) is a field->widget assignment that
is OFF BY ONE OR MORE: the claimed widget is real, fillable, and claimed exactly
once, but it belongs to a DIFFERENT printed line than the field means. Every
existing gate is blind to it:

  - _check_dump_coverage / the l1a9 ledger catch UNCLAIMED and HALLUCINATED
    widgets. A mis-assigned widget is neither -- coverage reads 100%.
  - schema_lint's dump rules catch multiclaim and unresolvable claims. A shift
    that is a clean permutation trips neither.
  - scripts/schema_score.py MATCHES a draft field to its gold counterpart BY
    pdf_field_name, so the claim is the matching KEY, not a scored dimension --
    a draft reproducing a shifted gold scores as agreement.

So this checks the draft against the PDF ITSELF, with no gold and no model.

How it works. Many government forms number their rows in a gutter immediately
left of the entry column ("1a", "2b", "11a"). Those markers are printed text at
known coordinates, and each aligns vertically with exactly one widget row. If a
field's id/label says line 2b and the widget it claims sits on the row printed
"1g", that is the bug -- reported with both line numbers.

Deliberately CONSERVATIVE: it reports only fields whose own text states a line
number AND whose claimed widget sits on a marked row. A form with no gutter
markers yields no findings rather than false ones, and a field whose intent is
unstated is skipped, not guessed at. Silence means "found nothing it can prove",
never "verified correct" -- the summary says so explicitly.

KNOWN BLIND SPOTS (stated so they are not mistaken for coverage):
  - OPTION-LEVEL claims are not checked. Choice fields carry their widget
    identity on options[], and this reads only a field's own pdf_field_name.
    That is load-bearing: instance #1 of this error class (bd 13vo, i-90
    ethnicity options on the OPPOSITE boxes) is an option-level defect this
    oracle structurally cannot see. Extending it naively WOULD misfire -- an
    f1040 field stating line "3c" has checkboxes printed "1"/"2", so the
    field's line number is not the option's marker. Use the overlay
    (overlay_field_guesses.py) for those.
  - A gutter needs >= _GUTTER_MIN_COL markers to be recognized, so a page with
    one or two numbered rows is not judged at all.

Usage:
    python scripts/authoring/check_line_binding.py --schema DRAFT.json --pdf FORM.pdf
    ... [--json OUT.json]   machine-readable findings
    ... [--require-verified] treat total abstention as failure (for CI)
Exit: 0 = verified, nothing mismatched. 1 = mismatch(es) found. 2 = usage/IO
error. 3 = ABSTAINED (nothing was verifiable) -- distinct from 0 on purpose, so
a caller gating on `rc == 0` can never read "I checked nothing" as "it is
clean"; --require-verified folds 3 into a hard failure.

ASCII only (cp1252 safe).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any, Optional

# A printed gutter marker: "1", "1a", "11a" -- at most 2 digits + optional letter.
_MARKER_RE = re.compile(r"^(\d{1,2}[a-z]?)$")
# A line number stated by a field's own id or label: line_1a / fld_1a / "1a ..." /
# "Line 11a". The letter must not run on into a word ("1 a Total" is fine,
# "1099-R" is not a marker).
_ID_LINE_RE = re.compile(r"^(?:fld_|line_)(\d{1,2}[a-z]?)$", re.I)
_LABEL_LINE_RE = re.compile(r"^\s*(?:line\s+)?(\d{1,2}[a-z]?)\b", re.I)

# A marker sits in the gutter just LEFT of the entry column. Rather than pin a
# form-specific x, we take markers within this many points to the left of the
# widget's left edge -- wide enough for the ~30pt f1040 gutter, tight enough to
# exclude body text.
_GUTTER_MAX_DX = 60.0
# ...but proximity ALONE is not enough: body text contains marker-shaped numerals
# (f1040's "1 Rollover 2 QCD 3" checkbox legend sits ~50pt left of the line-4c
# widget and was read as "line 3"). A REAL gutter is a column: its markers share
# a right edge and RECUR down the page. So we keep only markers whose right edge
# falls in a column shared by at least this many markers, within this tolerance.
_GUTTER_COL_TOL = 2.5
_GUTTER_MIN_COL = 3
# A marker belongs to a widget row when their vertical spans overlap. Rows are
# ~12pt; require the marker's midpoint to fall inside the widget's span, grown
# slightly so a 1-2pt typographic offset does not break the pairing.
_ROW_PAD = 3.0


def _norm_line(s: str) -> str:
    return s.strip().lower().replace(" ", "")


def _stated_line(field: dict) -> Optional[str]:
    """The line number the FIELD claims to be, from its id or its label."""
    fid = field.get("id")
    if isinstance(fid, str):
        m = _ID_LINE_RE.match(fid.strip())
        if m:
            return _norm_line(m.group(1))
    for key in ("name", "label"):
        v = field.get(key)
        if isinstance(v, str) and v.strip():
            m = _LABEL_LINE_RE.match(v)
            if m:
                return _norm_line(m.group(1))
    return None


def _iter_fields(schema: dict):
    """Every dict carrying an id, at any nesting depth (parts/sections/fields)."""
    seen: set[int] = set()

    def walk(o: Any):
        if isinstance(o, dict):
            if id(o) in seen:
                return
            seen.add(id(o))
            if isinstance(o.get("id"), str):
                yield o
            for v in o.values():
                yield from walk(v)
        elif isinstance(o, list):
            for v in o:
                yield from walk(v)

    yield from walk(schema)


def collect_markers(page) -> list[tuple[str, float, float, float]]:
    """Printed line markers on one page: (text, x_right, y_top, y_bottom).

    Only markers that live in a real GUTTER COLUMN are returned -- a right edge
    shared by >= _GUTTER_MIN_COL marker-shaped tokens. This is what separates a
    printed row number from a numeral inside body text (see _GUTTER_COL_TOL).
    """
    cands = []
    for x0, y0, x1, y1, word, *_ in page.get_text("words"):
        m = _MARKER_RE.match(word.strip())
        if m:
            cands.append((_norm_line(m.group(1)), x1, y0, y1))

    # Cluster right edges; keep only columns that recur.
    edges = sorted(c[1] for c in cands)
    columns: list[list[float]] = []
    for e in edges:
        if columns and e - columns[-1][-1] <= _GUTTER_COL_TOL:
            columns[-1].append(e)
        else:
            columns.append([e])
    keep = [(min(c), max(c)) for c in columns if len(c) >= _GUTTER_MIN_COL]
    if not keep:
        return []
    return [c for c in cands
            if any(lo - _GUTTER_COL_TOL <= c[1] <= hi + _GUTTER_COL_TOL
                   for lo, hi in keep)]


def marker_for_widget(markers, rect) -> Optional[str]:
    """The gutter marker printed on this widget's row, if exactly one matches.

    Ambiguity is reported as None (no finding) rather than a guess: two markers
    on one row means the layout is not the simple gutter this check understands.
    """
    hits = []
    for text, mx1, my0, my1 in markers:
        if not (0 <= rect.x0 - mx1 <= _GUTTER_MAX_DX):
            continue  # not in the gutter immediately left of this widget
        mid = (my0 + my1) / 2.0
        if rect.y0 - _ROW_PAD <= mid <= rect.y1 + _ROW_PAD:
            hits.append(text)
    uniq = sorted(set(hits))
    return uniq[0] if len(uniq) == 1 else None


def check(schema: dict, pdf_path: str) -> dict:
    try:
        import fitz  # PyMuPDF
    except ImportError:  # pragma: no cover - env-dependent
        return {"error": "PyMuPDF (fitz) is required", "findings": [],
                "checked": 0, "markers": 0}

    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:  # unreadable/missing PDF is a USAGE error (rc 2)
        return {"error": f"cannot open PDF {pdf_path!r}: {exc}",
                "findings": [], "checked": 0, "markers": 0}
    widgets: dict[str, tuple[int, Any]] = {}
    markers_by_page: dict[int, list] = {}
    for pno, page in enumerate(doc):
        markers_by_page[pno] = collect_markers(page)
        for w in page.widgets():
            if isinstance(w.field_name, str):
                widgets.setdefault(w.field_name, (pno, w.rect))

    findings, checked = [], 0
    for f in _iter_fields(schema):
        claim = f.get("pdf_field_name")
        if not isinstance(claim, str) or not claim:
            continue
        stated = _stated_line(f)
        if stated is None:
            continue  # field does not state a line -- nothing to verify against
        hit = widgets.get(claim)
        if hit is None:
            continue  # unresolvable claims are already an existing lint ERROR
        pno, rect = hit
        printed = marker_for_widget(markers_by_page.get(pno, []), rect)
        if printed is None:
            continue  # no unambiguous marker on that row -- cannot prove anything
        checked += 1
        if printed != stated:
            findings.append({
                "field_id": f.get("id"),
                "claims_widget": claim,
                "field_says_line": stated,
                "widget_is_on_line": printed,
                "page": pno + 1,
            })

    return {
        "findings": findings,
        "checked": checked,
        "markers": sum(len(v) for v in markers_by_page.values()),
    }


def render(result: dict) -> str:
    if result.get("error"):
        return f"ERROR: {result['error']}"
    fs = result["findings"]
    lines = []
    if not fs:
        if result["checked"] == 0:
            # Must NOT lead with "OK:" -- a caller grepping for it, or reading
            # only the first line of a truncated log, would read abstention as
            # a pass. That is the text twin of the exit-code bug (rc 3).
            lines.append(
                "ABSTAINED: verified NOTHING -- no field/widget pair was "
                "checkable.")
            lines.append(
                f"  ({result['markers']} printed marker(s) found; a field is "
                f"only checkable when it states a line number AND its claimed "
                f"widget sits on a marked row.)")
            lines.append("  This is NOT a clean bill of health.")
            return "\n".join(lines)
        lines.append(
            f"OK: no line-binding mismatch found "
            f"({result['checked']} field(s) verifiable against a printed line "
            f"marker).")
        return "\n".join(lines)
    lines.append(f"MISMATCH: {len(fs)} field(s) claim a widget printed on a "
                 f"different line ({result['checked']} checked):")
    for f in fs:
        lines.append(
            f"  {f['field_id']}: says line {f['field_says_line']}, but "
            f"{f['claims_widget'].split('.')[-1]} is printed on line "
            f"{f['widget_is_on_line']} (page {f['page']})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--schema", required=True, help="draft/kit schema.json")
    ap.add_argument("--pdf", required=True, help="the form PDF")
    ap.add_argument("--json", dest="json_out", default=None,
                    help="write findings as JSON here")
    ap.add_argument("--require-verified", action="store_true",
                    help="exit non-zero when NOTHING was verifiable (CI use): "
                         "an abstained run must not pass as clean")
    args = ap.parse_args(argv)

    try:
        with open(args.schema, encoding="utf-8") as fh:
            schema = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"ERROR: cannot read schema: {exc}", file=sys.stderr)
        return 2

    result = check(schema, args.pdf)
    if result.get("error"):
        print(render(result), file=sys.stderr)
        return 2
    # Write the JSON BEFORE the success text: a failed write must not be
    # preceded by an OK line, and must exit 2 rather than let Python's rc=1
    # collide with "mismatches found".
    if args.json_out:
        try:
            with open(args.json_out, "w", encoding="utf-8") as fh:
                json.dump(result, fh, indent=2)
        except OSError as exc:
            print(f"ERROR: cannot write {args.json_out!r}: {exc}", file=sys.stderr)
            return 2
    print(render(result))
    if result["findings"]:
        return 1
    if result["checked"] == 0:
        # Nothing was verifiable. The rendered text already says so, but the
        # EXIT CODE must say it too -- a lint-style caller gating on `rc == 0`
        # would otherwise read total abstention as a clean pass, which is the
        # exact failure mode this tool exists to prevent.
        return 1 if args.require_verified else 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
