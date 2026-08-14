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
  - OPTION-LEVEL claims are DELIBERATELY not checked, and _iter_fields enforces
    that by excluding option dicts by object identity. Choice fields carry their
    widget identity on options[]; this reads only a field's own pdf_field_name.
    Consequence: instance #1 of this error class (bd 13vo, i-90 ethnicity options
    on the OPPOSITE boxes) is an option-level defect this oracle cannot see. Use
    the overlay (overlay_field_guesses.py) for those.
    Extending this to options would need more than lifting the exclusion. Option
    label text routinely BEGINS with a numeral that is list-item text, not a line
    number -- f1040 ships "1 Rollover", "2 QCD", "1 Line 3a" -- so _stated_line
    would read those as claims and report false findings on correctly bound
    widgets. A field stating line "3c" also has checkboxes printed "1"/"2", so
    the parent's line number is not the option's marker either.
  - A gutter needs >= _GUTTER_MIN_COL markers to be recognized, so a page with
    one or two numbered rows is not judged at all.
  - The column rules reject a REPEATED-token legend, but they do NOT reject
    VARIED body text. f1040 page 2 prints cross-references ("Add lines 16 and
    17", "Subtract line 21 from line 18"), whose numerals form an accepted column
    at x_right ~159-172. It produces no finding today, but NOT because those
    markers are far from any widget: 18 marker/widget pairs there pass the
    _GUTTER_MAX_DX proximity guard. Every one is then rejected by the ROW guard
    in marker_for_widget -- the prose sits at mid-y 150-548 while the nearby
    widgets span y 50-58 and 504-527, so no pair overlaps vertically.
    So the risk to watch is NOT "an entry column nearer the prose" (already true
    here) but prose numerals sharing a ROW BAND with an entry widget -- a common
    layout, and one _GUTTER_MAX_DX does not guard at all. The abstention contract
    (silence is never a pass) is what bounds the damage.

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
    """Every FIELD dict carrying an id, at any nesting depth (parts/sections/
    fields).

    Option dicts are excluded even when they carry their own `id`, by object
    IDENTITY. Without that, an option is yielded as a field in its own right and
    the oracle reads its label as a stated line -- an option labelled "1 Yes" on a
    correctly bound widget printed on row 6a produces a confident FALSE finding,
    because the "1" is list-item text, not a line number. This is the exclusion
    overlay_field_guesses._claimants makes for the same reason.
    """
    option_dict_ids: set[int] = set()

    def find_options(o: Any) -> None:
        if isinstance(o, dict):
            opts = o.get("options")
            if isinstance(opts, list):
                for opt in opts:
                    if isinstance(opt, dict):
                        option_dict_ids.add(id(opt))
            for v in o.values():
                find_options(v)
        elif isinstance(o, list):
            for v in o:
                find_options(v)

    find_options(schema)

    seen: set[int] = set()

    def walk(o: Any):
        if isinstance(o, dict):
            if id(o) in seen:
                return
            seen.add(id(o))
            if isinstance(o.get("id"), str) and id(o) not in option_dict_ids:
                yield o
            for v in o.values():
                yield from walk(v)
        elif isinstance(o, list):
            for v in o:
                yield from walk(v)

    yield from walk(schema)


def collect_markers(page) -> list[tuple[str, float, float, float]]:
    """Printed line markers on one page: (text, x_right, y_top, y_bottom).

    Only markers in a real GUTTER are returned. Two conditions, and BOTH are
    needed -- recurrence alone is not enough:

      1. the right edges cluster into a column of >= _GUTTER_MIN_COL tokens; and
      2. within that column, any marker text that REPEATS is rejected -- and
         the surviving distinct-text markers must still number
         >= _GUTTER_MIN_COL.

    Condition 2 exists because recurring body text also forms columns, so
    recurrence by itself does not identify a gutter. f1040's line-4c/5a/5b rows
    each print the checkbox legend "1 Rollover 2 QCD 3", so the legend's '1'
    (x_right 278.0) and '2' (x_right 357.2) each recur on three rows and clear
    condition 1 outright. What separates them from a gutter is not position --
    they sit BETWEEN f1040's two real gutters (the left one at x~101-105 and the
    amount column at x~495-500) -- but repetition: a gutter numbers successive
    rows, so its tokens VARY ('2a', '3a', '4a', ...), whereas a legend column
    prints the same token on every row. Counting distinct texts is therefore the
    structural discriminator; a position rule would reject the amount column,
    which is where most f1040 findings come from.

    Condition 2 rejects the repeating TEXT VALUES, not the whole column (bd
    polyglot-pdf-qk97): the earlier whole-column reject was right for a pure
    legend column but also discarded a genuine gutter that happened to cluster
    adjacent to -- or share the exact x_right of -- a repeating legend. Because
    a gutter's own tokens are all distinct, none of them ever land in the
    repeating set, however the legend's repeats interleave with them. The
    survivor re-check preserves the original rule's intent: a mostly-repeating
    column with a few stray distinct tokens is not thereby promoted to a
    gutter. See the body for why a position-based split was tried and rejected.
    """
    cands = []
    for x0, y0, x1, y1, word, *_ in page.get_text("words"):
        m = _MARKER_RE.match(word.strip())
        if m:
            cands.append((_norm_line(m.group(1)), x1, y0, y1))

    # Cluster the CANDIDATES (not bare edges) so each column keeps its own
    # members. Both conditions below must be judged on those members: deriving
    # them from the column's padded band instead lets a single unrelated token
    # sitting just outside the column -- but inside the tolerance -- supply the
    # variety that rescues a pure legend column.
    columns: list[list[tuple[str, float, float, float]]] = []
    for c in sorted(cands, key=lambda c: c[1]):
        if columns and c[1] - columns[-1][-1][1] <= _GUTTER_COL_TOL:
            columns[-1].append(c)
        else:
            columns.append([c])

    kept: list[tuple[str, float, float, float]] = []
    dropped_texts_total = 0
    for col in columns:
        if len(col) < _GUTTER_MIN_COL:
            continue
        # Condition 2: a gutter numbers successive rows, so no text repeats
        # WITHIN ONE COLUMN. Scope matters -- a text may well repeat across the
        # PAGE, because f1040 prints each line number in both the left gutter and
        # the amount column ('2a', '8', '9' all appear twice on page 1, and up to
        # three times on page 2). Hoisting this check to page scope would reject
        # both real gutters and take f1040 from 20 findings to 0.
        #
        # REJECT ONLY THE REPEATING TEXT VALUES, not the whole column (bd
        # polyglot-pdf-qk97). The earlier rule rejected the ENTIRE column the
        # moment any text repeated within it -- correct for a pure legend
        # column, but a genuine gutter clustered adjacent to (or sharing the
        # exact x_right of, e.g. two gutters restarting the same numbering in
        # a continuation table) a repeating legend lost its own markers too.
        # A position-based split (e.g. "split at a y-order discontinuity")
        # was tried and rejected: it only separates gutter from legend when
        # they happen to occupy different x_right bands that column-building
        # sorts apart first, and still re-admits dropped members through any
        # x-tolerance re-scan -- neither holds when gutter and legend
        # genuinely interleave at THE SAME x_right, which f1040-shaped forms
        # can do (a form whose left and right gutters share an x_right, or a
        # continuation table restarting numbering in the same gutter).
        # Rejecting only the TEXT VALUES that repeat is position-independent:
        # a gutter's own tokens are still all distinct (measured on every
        # page of the three real kits: f1040 p1 x=100.8 4/4, x=105.3 7/7,
        # x=495.4 19/19; p2 x=100.8 23/23, x=497.6 22/22; w7 x=123.1 7/7), so
        # none of its markers are ever in the repeating set, however the
        # legend's repeats are interleaved with them.
        texts = [c[0] for c in col]
        text_counts: dict[str, int] = {}
        for t in texts:
            text_counts[t] = text_counts.get(t, 0) + 1
        repeating_texts = {t for t, n in text_counts.items() if n > 1}
        if not repeating_texts:
            kept.extend(col)
            continue
        survivors = [c for c in col if c[0] not in repeating_texts]
        dropped_texts_total += len(repeating_texts)
        # The survivors must STILL clear the minimum-column-size bar: a
        # column that is mostly-repeating with a couple of stray distinct
        # tokens is not thereby promoted to a gutter (mirrors the ORIGINAL
        # rule's intent -- a handful of leftover unique tokens is not
        # "recurs down the page").
        if len(survivors) >= _GUTTER_MIN_COL:
            kept.extend(survivors)
    if dropped_texts_total:
        # Observable drop (exit criterion 2): a repeated marker text is now
        # DISTINGUISHABLE from a page with no gutter at all, rather than
        # silently indistinguishable -- and unlike the whole-column-reject
        # version, this counts DISTINCT repeating text values, not columns,
        # since a column is no longer an atomic accept/reject unit.
        print(
            f"NOTE: dropped {dropped_texts_total} repeated marker text "
            f"value(s) from column candidates (a legend or restarted "
            f"numbering, not a gutter)",
            file=sys.stderr,
        )
    if not kept:
        return []
    # Return the KEPT markers directly, not a re-filter of `cands` by x-tolerance
    # bounds: re-deriving membership from a padded band would re-admit a
    # DROPPED marker whose x1 happens to fall within tolerance of a KEPT run's
    # band (exactly the bug an earlier version of this fix had -- a dropped
    # legend marker close in x to a surviving gutter leaked back in). `kept`
    # is already the exact, correct marker set.
    return kept


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
        # `abstained` is explicit in the payload for the same reason rc 3 exists
        # and the text leads with ABSTAINED: a consumer written to the obvious
        # contract ("no findings means pass") must not read "verified nothing" as
        # clean. Without it the JSON is the ONE channel where abstention is
        # implicit, since {"findings": [], "checked": 0} is shape-identical to a
        # genuinely clean run.
        payload = dict(result, abstained=result["checked"] == 0)
        try:
            with open(args.json_out, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
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
