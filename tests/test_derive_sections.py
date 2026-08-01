"""Unit tests for scripts/authoring/derive_sections.py (bd polyglot-pdf-6cfu.2).

Pins the integration-facing behavior added on top of the 6cfu.1 prototype:

- BALANCED cap-splits (maintainer feedback at the 6cfu.1 checkpoint): an
  oversize section splits into even chunks (22 fields at cap 20 -> 11+11),
  never greedy fill-to-cap (20+2).
- 'To review' gathering: name-pattern strays land in per-page sections with
  the well-known `sec_to_review` id prefix; positionless fields land in a
  pageless 'To review (unplaced)' section; both are recorded in the output's
  to_review block (the editor's review gate keys on it, 6cfu.3).
- apply_to_schema: OVERWRITES the schema's parts/sections and re-files every
  field's section_id from the derivation output.
- Hardening: derive_for_pdf raises a friendly ValueError on a 0-page PDF and
  never leaks a doc handle; PDF-only load skips widget-less dump fields.

All synthetic (no LLM); the real-PDF integration lives in
tests/test_extract_form_sections.py. Imports the script by file path (repo
precedent: test_extract_form_backfill.py). ASCII only.
"""

import importlib.util
import pathlib
import sys

import pytest

_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts" / "bakeoff"))
_SCRIPT = _REPO / "scripts" / "authoring" / "derive_sections.py"
spec = importlib.util.spec_from_file_location("derive_sections", _SCRIPT)
ds = importlib.util.module_from_spec(spec)
sys.modules["derive_sections"] = ds
spec.loader.exec_module(ds)


def _field(fid, page=1, x=10.0, y=10.0, name=None):
    return ds.FieldRec(fid=fid, name=name, page=page, x=x, y=y,
                       current_section=None, label=fid)


def _runs(sizes, page=1):
    """Family runs of the given sizes (each run = one unsplittable group).
    Fields are spaced 10pt apart so _row_family (y/4 rounding) puts every
    field on its own printed row."""
    runs, n = [], 0
    for size in sizes:
        run = []
        for _ in range(size):
            run.append(_field(f"f{n}", page=page, y=float(n * 10)))
            n += 1
        runs.append(run)
    return runs


# --- balanced cap-splits ----------------------------------------------------- #

def test_balanced_chunks_splits_evenly_not_greedy():
    """The maintainer case: 22 single-field runs at cap 20 -> 11+11 (greedy
    fill-to-cap would give 20+2)."""
    chunks = ds._balanced_chunks(_runs([1] * 22), cap=20)
    assert [len(c) for c in chunks] == [11, 11]


def test_balanced_chunks_three_way():
    """45 fields at cap 20 -> 3 chunks of 15, not 20+20+5."""
    chunks = ds._balanced_chunks(_runs([1] * 45), cap=20)
    assert [len(c) for c in chunks] == [15, 15, 15]


def test_balanced_chunks_under_cap_is_one_chunk():
    chunks = ds._balanced_chunks(_runs([1] * 20), cap=20)
    assert [len(c) for c in chunks] == [20]


def test_balanced_chunks_never_splits_a_family_run():
    """Runs are atomic: with runs of 8+8+6 at cap 12, no chunk may cut a run."""
    runs = _runs([8, 8, 6])
    chunks = ds._balanced_chunks(runs, cap=12)
    assert sum(len(c) for c in chunks) == 22
    starts = {c[0].fid for c in chunks}
    assert starts <= {"f0", "f8", "f16"}  # chunk boundaries only at run starts


def test_balanced_chunks_oversize_run_kept_whole():
    """A single run longer than the cap stays whole (its own oversize chunk)."""
    chunks = ds._balanced_chunks(_runs([25, 3]), cap=20)
    assert [len(c) for c in chunks] == [25, 3]


def test_cap_split_labels_and_review_flag_propagate():
    sec = ds.DerivedSection("Dependents", 1, 1, sum(_runs([1] * 22), []),
                            review=False)
    sec.part_label = "Page 1"
    out, notes = ds._cap_split([sec], ds._row_family, cap=20)
    assert [s.label for s in out] == ["Dependents (1 of 2)",
                                      "Dependents (2 of 2)"]
    assert all(s.review is False for s in out)
    assert any("cap-split into 2 (11+11)" in n for n in notes)


# --- 'To review' gathering --------------------------------------------------- #

def _name_convention_fields():
    """Enough USCIS-named fields to trip the name-convention strategy (>=80%),
    plus one stray (no name) and one positionless field."""
    fields = [
        _field(f"p1_line{i}", page=1, y=float(10 + i),
               name=f"P1_Line{i}_Thing[0]")
        for i in range(1, 9)
    ]
    fields.append(_field("stray_on_page_2", page=2, y=50.0, name=None))
    fields.append(_field("unplaced", page=None))
    return fields


def test_strays_and_unplaced_gather_into_to_review_sections():
    fields = _name_convention_fields()
    assert ds.pick_strategy(fields, []) == "name-convention"
    sections, unassigned, _notes = ds.derive(
        fields, [], "name-convention", cap=40, page_count=2, page_width=612.0)
    out = ds.build_output("t", "name-convention", sections, unassigned,
                          [], cap=40)
    by_id = {s["id"]: s for s in out["sections"]}
    # The page-2 stray: a per-page review section with the well-known prefix.
    assert by_id["sec_to_review_p2"]["fields"] == ["stray_on_page_2"]
    assert by_id["sec_to_review_p2"]["page_number"] == 2
    # The positionless field: the pageless unplaced bucket (no page keys).
    assert by_id["sec_to_review_unplaced"]["fields"] == ["unplaced"]
    assert "page_number" not in by_id["sec_to_review_unplaced"]
    # Both are recorded for the editor's review gate (6cfu.3).
    assert out["to_review"]["section_ids"] == ["sec_to_review_p2",
                                               "sec_to_review_unplaced"]
    assert sorted(out["to_review"]["field_ids"]) == ["stray_on_page_2",
                                                     "unplaced"]
    # Review sections group under one 'To review' part.
    review_part = next(p for p in out["parts"] if p["id"] == "part_to_review")
    assert review_part["label"] == "To review"
    assert set(review_part["section_ids"]) == {"sec_to_review_p2",
                                               "sec_to_review_unplaced"}


def test_colliding_part_labels_get_unique_part_ids():
    # Section ids have always been deduped; part ids were not, so two DISTINCT
    # part_keys whose labels slug identically emitted the SAME part id and
    # get_part/get_sections_in_part silently first-matched (bd polyglot-pdf-n2t3).
    labels = ["Part 1. Info", "Part 1 -- Info", "Part 1   Info"]
    sections = []
    for i, label in enumerate(labels, start=1):
        sec = ds.DerivedSection(f"Sec{i}", i, i, [_field(f"f{i}", page=i)])
        sec.part_label = label
        sections.append(sec)

    out = ds.build_output("t", "name-convention", sections, [], [], cap=40)

    pids = [p["id"] for p in out["parts"]]
    assert len(pids) == len(set(pids)) == 3, pids
    # Every part keeps its OWN section -- dedup must not merge the buckets.
    assert [p["section_ids"] for p in out["parts"]] == [
        ["sec_sec1_p1"], ["sec_sec2_p2"], ["sec_sec3_p3"]]
    # Labels are untouched; only the minted id is disambiguated.
    assert [p["label"] for p in out["parts"]] == labels


def test_clean_derivation_has_empty_to_review():
    fields = [_field(f"p1_line{i}", page=1, y=float(i),
                     name=f"P1_Line{i}_Thing[0]") for i in range(1, 6)]
    sections, unassigned, _ = ds.derive(
        fields, [], "name-convention", cap=40, page_count=1, page_width=612.0)
    out = ds.build_output("t", "name-convention", sections, unassigned, [], 40)
    assert out["to_review"] == {"section_ids": [], "field_ids": []}
    assert out["unassigned_fields"] == []


# --- apply_to_schema --------------------------------------------------------- #

def test_apply_to_schema_overwrites_divisions_and_refiles_every_field():
    schema = {
        "sections": [{"id": "llm_sec", "label": "LLM-cut", "order": 1,
                      "fields": ["a", "b"]}],
        "parts": [{"id": "llm_part", "label": "Old", "order": 1,
                   "section_ids": ["llm_sec"]}],
        "fields": [
            {"id": "a", "section_id": "llm_sec"},
            {"id": "b", "section_id": "llm_sec"},
            {"id": "c", "section_id": ""},
        ],
    }
    derived = {
        "division_strategy": "printed-heading",
        "cap": 40,
        "parts": [{"id": "part_page_1", "label": "Page 1", "order": 1,
                   "section_ids": ["sec_x_p1", "sec_to_review_unplaced"]}],
        "sections": [
            {"id": "sec_x_p1", "label": "X", "order": 1, "fields": ["a", "b"],
             "page_number": 1, "page_numbers": [1]},
            {"id": "sec_to_review_unplaced", "label": "To review (unplaced)",
             "order": 2, "fields": ["c"]},
        ],
        "to_review": {"section_ids": ["sec_to_review_unplaced"],
                      "field_ids": ["c"]},
        "notes": ["n1"],
    }
    summary = ds.apply_to_schema(schema, derived)
    assert [s["id"] for s in schema["sections"]] == ["sec_x_p1",
                                                     "sec_to_review_unplaced"]
    assert schema["parts"][0]["id"] == "part_page_1"
    assert {f["id"]: f["section_id"] for f in schema["fields"]} == {
        "a": "sec_x_p1", "b": "sec_x_p1", "c": "sec_to_review_unplaced"}
    # The pageless review section carries no page keys.
    assert "page_number" not in schema["sections"][1]
    assert schema["sections"][0]["page_numbers"] == [1]
    assert summary["strategy"] == "printed-heading"
    assert summary["to_review_field_ids"] == ["c"]
    assert summary["sections"] == 2 and summary["parts"] == 1


# --- hardening ---------------------------------------------------------------- #

def test_derive_with_zero_page_doc_is_a_friendly_error():
    """A 0-page document raises a friendly ValueError instead of the raw
    doc[0] IndexError the prototype crashed with (6cfu.1 outer review).
    fitz cannot SAVE a 0-page file, so the open-doc core is tested directly."""
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    try:
        with pytest.raises(ValueError, match="no pages"):
            ds._derive_with_doc([], doc, cap=40, form_id="t")
    finally:
        doc.close()


def test_derive_for_pdf_unreadable_file_is_a_friendly_error(tmp_path):
    p = tmp_path / "not_a.pdf"
    p.write_text("hello", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot open PDF"):
        ds.derive_for_pdf([], str(p))


def test_fields_from_schema_skips_idless_and_reads_positions():
    schema = {"fields": [
        {"id": "a", "pdf_position": {"page": 2, "x": 1, "y": 3}},
        {"id": "b"},                     # no position -> unplaced
        {"no_id": True},                 # skipped
        "not-a-dict",                    # skipped
    ]}
    recs = ds.fields_from_schema(schema)
    assert [r.fid for r in recs] == ["a", "b"]
    assert recs[0].page == 2 and recs[1].page is None
