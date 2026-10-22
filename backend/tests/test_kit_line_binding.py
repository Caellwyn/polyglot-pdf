"""Widget-ASSIGNMENT correctness gate for shipped kits (bd polyglot-pdf-3ave).

The gap this closes, named in 3ave's own investigation: every existing gate
measures whether a claimed widget EXISTS (dump-widget-unclaimed catches orphan
widgets, the ledger catches hallucinated claims). NONE measured whether the
claimed widget is the RIGHT one. A field claiming a real, fillable widget that
belongs to a DIFFERENT printed line is invisible -- coverage reads 100%, lint
reports zero findings -- which is exactly how f1040's page-1 amount column
shipped shifted by one row through Line 11a, putting wage/interest/dividend
amounts on the wrong tax lines.

That error class has now appeared three times (bd 13vo on i-90, bd ivh9 on w7,
bd 3ave on f1040), each found by accident rather than by a gate. This test is
the gate.

The oracle is `scripts/authoring/check_line_binding.py`: for every field that
STATES a line number and claims a widget sitting on a row whose printed gutter
marker is unambiguous, it compares the two. It is deterministic, costs nothing,
and reads the PDF's own printed text -- not field-name plausibility, which is
what made the shift look reasonable in review.

DELIBERATELY NOT A UNIVERSAL PASS: the oracle ABSTAINS on forms without a
printed gutter (w7 has none, so it verifies nothing there). Abstention must
never read as success, so this test asserts a per-kit MINIMUM verified count
alongside zero mismatches -- a kit that silently stops being checkable fails
here instead of passing vacuously.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

# Kits whose PDFs carry a printed line gutter the oracle can read, with the
# number of fields it could verify when the binding was corrected. The count is
# a FLOOR, not an equality: adding fields may raise it, but a DROP means the
# form stopped being verifiable and the zero-mismatch assertion below went
# vacuous. w7 / i-90 are absent on purpose -- they have no gutter markers, so
# the oracle abstains completely there (their equivalent coverage is the
# overlay review surface, scripts/authoring/overlay_field_guesses.py).
_MIN_VERIFIED = {"f1040": 56}


def _check(kit: str) -> dict:
    import json

    from scripts.authoring.check_line_binding import check

    kit_dir = _REPO / "form-kits" / kit
    schema, pdf = kit_dir / "schema.json", kit_dir / "form.pdf"
    if not schema.exists() or not pdf.exists():
        pytest.skip(f"{kit} kit or PDF not present")
    return check(json.loads(schema.read_text(encoding="utf-8")), str(pdf))


@pytest.mark.parametrize("kit", sorted(_MIN_VERIFIED))
def test_kit_fields_bind_to_the_widget_on_their_own_printed_line(kit):
    result = _check(kit)
    assert not result.get("error"), result["error"]

    findings = result["findings"]
    assert not findings, (
        f"{kit}: {len(findings)} field(s) claim a widget printed on a DIFFERENT "
        f"line -- a silent misfill (the value prints on the wrong line of the "
        f"real form). "
        + "; ".join(
            f"{f['field_id']} says line {f['field_says_line']} but its widget "
            f"is on line {f['widget_is_on_line']}"
            for f in findings[:8]
        )
    )


def test_f1040_income_lines_fill_onto_their_own_printed_rows():
    """End-to-end proof through the PRODUCTION filler (bd 3ave crit 2, lha9 crit 2).

    The oracle above compares the schema against the PDF. This drives the real
    `pdf_fill_routes.fill_pdf` with a distinct sentinel per income line and then
    reads the OUTPUT PDF back, asking the form itself which printed row each
    value landed on. That is the assertion the bug's impact statement demands:
    "a filled f1040 puts wage/interest/dividend amounts on the wrong tax lines".
    """
    import asyncio
    import json

    import pymupdf as fitz

    from backend.routes.pdf_fill_routes import PDFFillRequest, fill_pdf
    from scripts.authoring.check_line_binding import collect_markers, marker_for_widget

    kit_dir = _REPO / "form-kits" / "f1040"
    if not (kit_dir / "form.pdf").exists():
        pytest.skip("f1040 kit not present")
    schema = json.loads((kit_dir / "schema.json").read_text(encoding="utf-8"))

    lines = ["1a", "1b", "1c", "1d", "1e", "1f", "1g", "1h", "1z", "2a", "2b",
             "3a", "3b", "4a", "4b", "5a", "5b", "6a", "6b", "7a", "8", "9",
             "10", "11a"]
    values = {f"fld_{ln}": str(1000 + i) for i, ln in enumerate(lines)}
    by_sentinel = {v: k for k, v in values.items()}

    # asyncio.run (not new_event_loop) -- matches every sibling fill test and
    # closes the loop instead of leaking a selector handle per run.
    resp = asyncio.run(
        fill_pdf(PDFFillRequest(kit_id="f1040", pdf_filename="form.pdf",
                                field_values=values, form_schema=schema))
    )

    landed: dict[str, str | None] = {}
    with fitz.open(stream=resp.body, filetype="pdf") as doc:
        for page in doc:
            markers = collect_markers(page)
            for w in page.widgets():
                v = w.field_value
                if isinstance(v, str) and v in by_sentinel:
                    landed[by_sentinel[v]] = marker_for_widget(markers, w.rect)

    missing = sorted(set(values) - set(landed))
    assert not missing, (
        f"values never reached the filled PDF: {missing} -- a field claiming a "
        f"non-existent widget fills silently into nothing (the bd lha9 defect)"
    )
    misplaced = {f: got for f, got in landed.items()
                 if got != f.removeprefix("fld_")}
    assert not misplaced, (
        "filled values printed on the WRONG tax line: "
        + "; ".join(
            f"{f} printed on line {got}" if got is not None
            # None = the value landed on a row with no readable marker, i.e. a
            # write-in/checkbox row -- NOT simply "line None" (Opus fresh-eyes).
            else f"{f} landed on an unmarked row (a write-in/checkbox box)"
            for f, got in sorted(misplaced.items())
        )
    )


def test_f1040_write_in_boxes_bind_by_geometry_not_by_row():
    """The write-ins the row oracle CANNOT settle (bd 3ave).

    Four page-1 fields share a printed line with an amount box, so
    `marker_for_widget` returns the same marker for both and cannot tell them
    apart -- three of the oracle's own suggestions were wrong here, and taking
    them literally would have collided `fld_1h_type` onto `fld_1h`'s widget.
    Geometry is what distinguishes them: the amount column is x=504-576, and
    each write-in sits in its own narrower band. Nothing else in this file
    covers these fields, so without this test a future edit could re-collide
    them with every other test still green.
    """
    import json

    import pymupdf as fitz

    kit_dir = _REPO / "form-kits" / "f1040"
    if not (kit_dir / "form.pdf").exists():
        pytest.skip("f1040 kit not present")
    schema = json.loads((kit_dir / "schema.json").read_text(encoding="utf-8"))
    by_id = {f["id"]: f for f in schema["fields"]}

    # field id -> (expected widget leaf, expected x0, expected y0)
    expected = {
        "fld_1h_type": ("f1_54[0]", 344, 534),    # "Other earned income" type
        "fld_1i": ("f1_56[0]", 410, 546),         # combat-pay election
        "fld_4c_other": ("f1_64[0]", 439, 618),   # 4c "Check if" write-in
        "fld_5c_other": ("f1_67[0]", 439, 642),   # 5c "Check if" write-in
        "fld_1h": ("f1_55[0]", 504, 534),         # the AMOUNT box on 1h
    }
    rects = {}
    with fitz.open(kit_dir / "form.pdf") as doc:
        for pno, page in enumerate(doc):
            for w in page.widgets():
                if isinstance(w.field_name, str):
                    rects.setdefault(w.field_name, (pno + 1, w.rect))

    for fid, (leaf, x0, y0) in expected.items():
        claim = by_id[fid]["pdf_field_name"]
        assert claim.endswith(leaf), f"{fid} claims {claim}, expected ...{leaf}"
        _, rect = rects[claim]
        assert abs(rect.x0 - x0) <= 2 and abs(rect.y0 - y0) <= 2, (
            f"{fid} -> {leaf} is at ({round(rect.x0)},{round(rect.y0)}), "
            f"expected ~({x0},{y0}) -- the kit or the PDF moved"
        )

    claims = [by_id[f]["pdf_field_name"] for f in expected]
    assert len(set(claims)) == len(claims), (
        "two of the write-in/amount fields collided onto one widget: "
        f"{sorted(claims)}"
    )


# Per-kit floor for the pdf_position guard below, mirroring _MIN_VERIFIED.
# WITHOUT this the guard can go silently vacuous: i-90 stores LEAF widget names
# (`P1_Line1_AlienNumber[0]`) while its PDF uses fully-qualified ones
# (`form1[0].#subform[0].P1_Line1_AlienNumber[0]`), so an exact-match-only
# lookup skipped all 132 of its fields and passed green even with every
# position corrupted (Opus fresh-eyes on this PR).
# i-90's floor moved 114 -> 79 for the applicant-only v2 kit: 79 is the count of
# fields carrying a pdf_field_name there, so every resolvable field still
# resolves and the drop is the deliberate removal of Parts 6/7, not a regression.
#
# UNVERIFIABLE IN CI, and say so rather than let the number look load-bearing:
# kits are bucket-canonical (CLAUDE.md scar #10) and no i-90 is tracked, so this
# parametrization SKIPS everywhere except a machine that pulled that kit. The
# value is measured and correct as of 2026-09-03; it pins nothing until this
# guard runs against a pulled or synthetic corpus (bd polyglot-pdf-2r1ku).
_MIN_POSITIONS_CHECKED = {"f1040": 167, "i-90": 79, "w7": 47}


def _resolve_widget(claim: str, rects: dict, by_suffix: dict):
    """Resolve a schema claim to a widget: exact match first, then a
    DOT-BOUNDARY suffix match that must be UNAMBIGUOUS.

    Deliberately STRICTER than production's `find_widget`
    (`backend/routes/pdf_fill_routes.py`), which does a bare `endswith` and
    takes the first page-order hit. Here an ambiguous suffix resolves to
    `None` (skipped) rather than to a guessed widget -- f1040 has genuine leaf
    collisions (`Checkbox_ReadOrder[0].c1_8[0]` vs a separate bare `c1_8[0]`),
    and a guard must never assert a position against a widget it only guessed.
    Verified: on all three shipped kits the two resolvers agree on 100% of
    fields, so the strictness costs no coverage today (Opus outer review).
    """
    if claim in rects:
        return rects[claim]
    hits = by_suffix.get(claim)
    return hits[0] if hits and len(hits) == 1 else None


@pytest.mark.parametrize("kit", ["f1040", "i-90", "w7"])
def test_stored_pdf_position_agrees_with_the_claimed_widget(kit):
    """`pdf_position` must describe the widget `pdf_field_name` claims.

    The two keys are siblings that a rebind can silently desynchronize: the
    fill path reads `pdf_field_name`, but the preview overlay
    (`frontend/src/pdf-view/FieldOverlay.tsx` -> `pdfToScreenCoords`) reads
    `pdf_position` and never re-derives it from the PDF at runtime. So a
    correct fill can coexist with a highlight box drawn on the wrong row --
    which is exactly what bd polyglot-pdf-3ave's rebind produced until this
    guard was added (fresh-eyes finding on that PR; the stale positions
    carried the SAME one-row shift the bindings did).
    """
    import json

    import pymupdf as fitz

    kit_dir = _REPO / "form-kits" / kit
    if not (kit_dir / "form.pdf").exists():
        pytest.skip(f"{kit} kit not present")
    schema = json.loads((kit_dir / "schema.json").read_text(encoding="utf-8"))

    rects: dict[str, tuple[int, object]] = {}
    by_suffix: dict[str, list] = {}
    with fitz.open(kit_dir / "form.pdf") as doc:
        for pno, page in enumerate(doc):
            for w in page.widgets():
                if isinstance(w.field_name, str):
                    rects.setdefault(w.field_name, (pno + 1, w.rect))
    for full, hit in rects.items():
        leaf = full.rsplit(".", 1)[-1]
        by_suffix.setdefault(leaf, []).append(hit)

    drift, checked = [], 0
    for f in schema.get("fields", []):
        claim, pos = f.get("pdf_field_name"), f.get("pdf_position")
        if not isinstance(claim, str) or not pos:
            continue  # position-less fields: not this gate's business
        hit = _resolve_widget(claim, rects, by_suffix)
        if hit is None:
            continue  # unresolvable / ambiguous claims: other gates own those
        page, rect = hit
        checked += 1
        # width/height are checked too, not just the origin: the overlay draws
        # a BOX, and a stored size that drifts from the widget is the same
        # class of schema-vs-PDF desync this guard exists to stop.
        if (pos.get("page") != page
                or abs(pos.get("x", 0) - rect.x0) > 2
                or abs(pos.get("y", 0) - rect.y0) > 2
                or abs(pos.get("width", 0) - rect.width) > 2
                or abs(pos.get("height", 0) - rect.height) > 2):
            drift.append(
                f"{f.get('id')}: stored ({pos.get('x')},{pos.get('y')}) "
                f"{pos.get('width')}x{pos.get('height')} p{pos.get('page')} but "
                f"{claim.rsplit('.', 1)[-1]} is at ({round(rect.x0)},{round(rect.y0)}) "
                f"{round(rect.width, 2)}x{round(rect.height, 2)} p{page}"
            )

    assert not drift, (
        f"{kit}: {len(drift)} field(s) whose pdf_position does not describe the "
        f"widget they claim -- the preview overlay will highlight the wrong box. "
        + "; ".join(drift[:6])
    )
    # Anti-vacuity floor (see _MIN_POSITIONS_CHECKED): a name-scheme or parser
    # change that stops resolving claims must FAIL here, not silently reduce
    # this test to asserting nothing.
    assert checked >= _MIN_POSITIONS_CHECKED[kit], (
        f"{kit}: the position guard verified only {checked} field(s), below the "
        f"floor of {_MIN_POSITIONS_CHECKED[kit]} -- claims stopped resolving to "
        f"widgets, so the drift assertion above is checking less than it should."
    )


@pytest.mark.parametrize("kit", sorted(_MIN_VERIFIED))
def test_line_binding_oracle_still_verifies_the_kit(kit):
    # Guards the assertion above from going vacuous: the oracle abstains
    # per-field whenever a marker is unreadable, so a PDF/parser change that
    # stopped finding markers would make "zero mismatches" trivially true.
    result = _check(kit)
    assert not result.get("error"), result["error"]
    assert result["checked"] >= _MIN_VERIFIED[kit], (
        f"{kit}: the line-binding oracle verified only {result['checked']} "
        f"field(s), below the floor of {_MIN_VERIFIED[kit]}. Fewer verifiable "
        f"fields means the zero-mismatch test above is checking less than it "
        f"used to -- find out why before lowering this floor."
    )
