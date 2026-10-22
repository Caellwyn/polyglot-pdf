"""The --check change-detector in scripts/authoring/backfill_option_positions.py
(bd polyglot-pdf-icyi, fresh-eyes Opus round).

That CLI is the documented evidence gate for kit-position work: journal entries
record "--check exits 0 / a second run is a no-op" as the passing criterion. Its
change-detector used to be `fields_filled + options_filled > 0` -- a count of
DERIVATIONS. Once the deterministic widget rect started winning unconditionally,
every resolvable field/option re-derives on every run, so that count became
permanently non-zero: --check returned exit 1 ("this kit needs patching") for
EVERY kit including a fully-positioned one, and the documented exit 0 became
unreachable. The detector now compares the positions themselves.

Synthetic only -- a real 1-page PDF is built with PyMuPDF so the CLI's own
acroform_dump call has genuine widgets to read (mirroring
test_schema_score_derivation.py's precedent of using a real fitz document).

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

fitz = pytest.importorskip("pymupdf")

_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts" / "bakeoff"))
_SCRIPT = _REPO / "scripts" / "authoring" / "backfill_option_positions.py"
_spec = importlib.util.spec_from_file_location("backfill_option_positions", _SCRIPT)
bop = importlib.util.module_from_spec(_spec)
sys.modules["backfill_option_positions"] = bop
_spec.loader.exec_module(bop)


def _one_widget_pdf(tmp_path) -> str:
    """A 1-page PDF carrying a single named text widget."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    widget = fitz.Widget()
    widget.field_name = "fld_a"
    widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    widget.rect = fitz.Rect(100, 200, 250, 220)
    page.add_widget(widget)
    out = tmp_path / "form.pdf"
    doc.save(str(out))
    doc.close()
    return str(out)


def _kit(tmp_path, position) -> tuple[str, str]:
    """Write a kit whose single field carries `position` (or none)."""
    pdf = _one_widget_pdf(tmp_path)
    field: dict = {"id": "a", "name": "A", "type": "text",
                   "pdf_field_name": "fld_a"}
    if position is not None:
        field["pdf_position"] = position
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps({
        "form_metadata": {"title": "T", "version": "1"},
        "fields": [field], "sections": [], "parts": [],
    }), encoding="utf-8")
    return str(schema_path), pdf


def _real_position(pdf_path: str) -> dict:
    """The position the back-fill will derive for fld_a (1-based page)."""
    doc = fitz.open(pdf_path)
    w = next(iter(doc.load_page(0).widgets()))
    return {"page": 1, "x": w.rect.x0, "y": w.rect.y0,
            "width": w.rect.width, "height": w.rect.height}


def test_check_exits_0_on_an_ALREADY_positioned_kit(tmp_path):
    """THE REGRESSION (bd polyglot-pdf-icyi): a kit whose positions already match
    the PDF must report "nothing to patch" -- exit 0 -- even though the
    deterministic pass re-derives every rect. Counting derivations made this
    exit 1 forever."""
    pdf = _one_widget_pdf(tmp_path)
    schema_path, _ = _kit(tmp_path, _real_position(pdf))
    assert bop.backfill_kit(schema_path, pdf, check=True) == 0


def test_check_exits_1_when_a_position_is_genuinely_MISSING(tmp_path):
    """The detector must still fire when a write run really would change the
    file -- otherwise the fix would have traded a false alarm for a blind spot."""
    schema_path, pdf = _kit(tmp_path, None)
    assert bop.backfill_kit(schema_path, pdf, check=True) == 1


def test_check_exits_1_when_a_position_is_genuinely_WRONG(tmp_path):
    """A plausible-but-wrong stored rect (the model-authored shape this bead is
    about) is a real difference, so --check must report it."""
    schema_path, pdf = _kit(tmp_path, {
        "page": 0, "x": 999, "y": 999, "width": 5, "height": 5})
    assert bop.backfill_kit(schema_path, pdf, check=True) == 1


def test_a_write_run_is_a_no_op_the_SECOND_time(tmp_path):
    """The idempotence the docstring promises, verified by BYTES rather than by
    the derivation counter: run 1 patches, run 2 changes nothing."""
    schema_path, pdf = _kit(tmp_path, None)
    assert bop.backfill_kit(schema_path, pdf, check=False) == 0
    after_first = pathlib.Path(schema_path).read_bytes()

    assert bop.backfill_kit(schema_path, pdf, check=False) == 0
    assert pathlib.Path(schema_path).read_bytes() == after_first
    # ...and --check now agrees the kit is settled
    assert bop.backfill_kit(schema_path, pdf, check=True) == 0


def test_positions_differ_helper_ignores_untouched_schemas():
    """The comparison is position-only: unrelated edits must not read as a
    position change (and identical schemas must not either)."""
    base = {"fields": [{"id": "a", "pdf_position": {"page": 1, "x": 1, "y": 2,
                                                   "width": 3, "height": 4}}]}
    same = json.loads(json.dumps(base))
    assert bop._positions_differ(base, same) is False

    renamed = json.loads(json.dumps(base))
    renamed["fields"][0]["name"] = "changed elsewhere"
    assert bop._positions_differ(base, renamed) is False

    moved = json.loads(json.dumps(base))
    moved["fields"][0]["pdf_position"]["x"] = 99
    assert bop._positions_differ(base, moved) is True

    dropped = json.loads(json.dumps(base))
    del dropped["fields"][0]["pdf_position"]
    assert bop._positions_differ(base, dropped) is True


def test_a_VALUELESS_option_cannot_mask_a_changed_field_position():
    """KEY-COLLISION REGRESSION (bd polyglot-pdf-icyi, fresh-eyes Opus round 2).

    The first version keyed the map by (field_id, option_value), so an option
    with no `value` produced (field_id, None) -- the SAME key as the field's own
    entry -- and silently overwrote it. A genuinely wrong field rect then
    compared EQUAL, so --check reported exit 0 AND a patch run skipped the write
    entirely, discarding the corrected positions it had just computed. Keys are
    positional indices now, collision-free by construction."""
    base = {"fields": [{
        "id": "a",
        "pdf_position": {"page": 1, "x": 1, "y": 2, "width": 3, "height": 4},
        "options": [{"label": "no value key here"}],
    }]}
    moved = json.loads(json.dumps(base))
    moved["fields"][0]["pdf_position"]["x"] = 999
    assert bop._positions_differ(base, moved) is True


def test_duplicate_field_ids_cannot_mask_a_change():
    """Same collision class via a different route: two fields sharing an id used
    to overwrite each other's entry."""
    base = {"fields": [
        {"id": "dup", "pdf_position": {"page": 1, "x": 1, "y": 1,
                                       "width": 1, "height": 1}},
        {"id": "dup", "pdf_position": {"page": 1, "x": 2, "y": 2,
                                       "width": 2, "height": 2}},
    ]}
    moved = json.loads(json.dumps(base))
    moved["fields"][0]["pdf_position"]["x"] = 50
    assert bop._positions_differ(base, moved) is True


def test_a_null_position_routes_through_backfill_kit_END_TO_END(tmp_path):
    """The null case through the REAL CLI entry point, not just the comparison
    helper (bd polyglot-pdf-8i9u criterion 2; fresh-eyes Opus round 5 caught that
    the shipped pin only called _positions_differ directly).

    A field whose widget does not resolve AND whose pdf_position is an explicit
    null: the key gets popped, which IS a file change, so --check must report 1
    and a write run must actually rewrite the file with the key gone."""
    pdf = _one_widget_pdf(tmp_path)
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps({
        "form_metadata": {"title": "T", "version": "1"},
        "fields": [{"id": "a", "name": "A", "type": "text",
                    "pdf_field_name": "no_such_widget",
                    "pdf_position": None}],
        "sections": [], "parts": [],
    }), encoding="utf-8")

    assert bop.backfill_kit(str(schema_path), pdf, check=True) == 1
    # --check wrote nothing
    assert json.loads(schema_path.read_text(encoding="utf-8"))["fields"][0][
        "pdf_position"] is None

    assert bop.backfill_kit(str(schema_path), pdf, check=False) == 0
    written = json.loads(schema_path.read_text(encoding="utf-8"))
    assert "pdf_position" not in written["fields"][0]
    # ...and it has settled: a second run is a no-op
    assert bop.backfill_kit(str(schema_path), pdf, check=True) == 0


def test_an_explicit_null_position_is_not_the_same_as_an_absent_key():
    """NULL-vs-ABSENT (bd polyglot-pdf-8i9u, fresh-eyes Opus round 3).

    `.get()` returns None for both, so popping a null placeholder -- a real edit
    to the written file -- used to read as unchanged: --check said exit 0 and a
    patch run skipped the write, discarding the positions it had just computed.
    Same symptom as the key collision, different route."""
    with_null = {"fields": [{"id": "a", "pdf_position": None}]}
    without_key = {"fields": [{"id": "a"}]}
    assert bop._positions_differ(with_null, without_key) is True
    # ...and the sentinel is stable across separate calls (a per-call object()
    # would make every schema differ from itself)
    assert bop._positions_differ(without_key,
                                 json.loads(json.dumps(without_key))) is False


def test_option_positions_are_compared_too():
    """A per-option rect change counts: the CLI exists primarily for options."""
    base = {"fields": [{"id": "a", "options": [
        {"value": "v", "pdf_position": {"page": 1, "x": 1, "y": 2,
                                        "width": 3, "height": 4}}]}]}
    moved = json.loads(json.dumps(base))
    moved["fields"][0]["options"][0]["pdf_position"]["y"] = 77
    assert bop._positions_differ(base, moved) is True
