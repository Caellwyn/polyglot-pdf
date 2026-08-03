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

    import fitz

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

    resp = asyncio.new_event_loop().run_until_complete(
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
        + "; ".join(f"{f} printed on line {got}" for f, got in sorted(misplaced.items()))
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
