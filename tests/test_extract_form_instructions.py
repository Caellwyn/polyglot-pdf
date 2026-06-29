"""Tests for extract_form.py's help.instructions population (bd polyglot-pdf-s4dp.3).

Two deterministic sources, both targeting field.help.instructions:
  1. /TU baseline: each AcroForm widget's /TU tooltip (already in the dump) is
     mapped onto its field by pdf_field_name (_extract_instructions_from_dump).
  2. OPTIONAL instructions-PDF enrichment: a straightforward per-field text merge
     -- a field whose LABEL appears in the instructions text gets the matched
     paragraph appended on top of the /TU baseline (_enrich_instructions_from_pdf).

These pin the merge contract with synthetic data (no PDF / LLM needed). Imports
extract_form by file path, matching tests/test_extract_form_backfill.py.

ASCII only (cp1252 safe).
"""

import importlib.util
import json
import pathlib
import sys

import pytest


_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts" / "bakeoff"))
_SCRIPT = _REPO / "scripts" / "authoring" / "extract_form.py"
spec = importlib.util.spec_from_file_location("extract_form", _SCRIPT)
ef = importlib.util.module_from_spec(spec)
sys.modules["extract_form"] = ef
spec.loader.exec_module(ef)


# --- _build_name_to_tu ------------------------------------------------------ #

def _write_dump(tmp_path, name_to_widgets):
    """Write a minimal acroform-dump JSON: {fields:[{name, widgets:[...]}]}."""
    dump = {"fields": [
        {"name": n, "widgets": ws} for n, ws in name_to_widgets.items()
    ]}
    p = tmp_path / "dump.json"
    p.write_text(json.dumps(dump), encoding="utf-8")
    return str(p)


def test_build_name_to_tu_maps_first_tu_per_name(tmp_path):
    dump = _write_dump(tmp_path, {
        "fld_a": [{"tu": "Family Name (Last Name)"}],
        "fld_b": [{"tu": ""}, {"tu": "Date of Birth (mm/dd/yyyy)"}],  # first blank
        "fld_c": [{"rect": {}}],  # no tu at all
    })
    m = ef._build_name_to_tu(dump)
    assert m["fld_a"] == "Family Name (Last Name)"
    assert m["fld_b"] == "Date of Birth (mm/dd/yyyy)"  # skips the blank widget
    assert "fld_c" not in m  # no tu -> absent


def test_build_name_to_tu_missing_file_is_empty(tmp_path):
    assert ef._build_name_to_tu(str(tmp_path / "nope.json")) == {}


# --- _extract_instructions_from_dump ---------------------------------------- #

def test_tu_populates_blank_instructions(tmp_path):
    dump = _write_dump(tmp_path, {
        "fld_a": [{"tu": "Enter your A-Number"}]})
    schema = {"fields": [{"id": "anum", "pdf_field_name": "fld_a"}]}
    assert ef._extract_instructions_from_dump(schema, dump) == 1
    assert schema["fields"][0]["help"]["instructions"] == "Enter your A-Number"


def test_tu_does_not_clobber_existing_instructions(tmp_path):
    """A real help.instructions already present (e.g. LLM-written) wins; /TU only
    fills a genuine blank."""
    dump = _write_dump(tmp_path, {"fld_a": [{"tu": "the TU text"}]})
    schema = {"fields": [{
        "id": "x", "pdf_field_name": "fld_a",
        "help": {"instructions": "already here"}}]}
    assert ef._extract_instructions_from_dump(schema, dump) == 0
    assert schema["fields"][0]["help"]["instructions"] == "already here"


def test_tu_uses_first_option_for_consolidated_field(tmp_path):
    """A consolidated options[] field (no top-level pdf_field_name) takes the /TU
    of its first option's widget -- same join as the position back-fill."""
    dump = _write_dump(tmp_path, {"opt1": [{"tu": "Select one"}]})
    schema = {"fields": [{
        "id": "radio",
        "options": [{"value": "a", "pdf_field_name": "opt1"}]}]}
    assert ef._extract_instructions_from_dump(schema, dump) == 1
    assert schema["fields"][0]["help"]["instructions"] == "Select one"


def test_tu_no_match_leaves_field_untouched(tmp_path):
    dump = _write_dump(tmp_path, {"other": [{"tu": "x"}]})
    schema = {"fields": [{"id": "a", "pdf_field_name": "missing"}]}
    assert ef._extract_instructions_from_dump(schema, dump) == 0
    assert "help" not in schema["fields"][0]


def test_tu_empty_dump_returns_zero(tmp_path):
    dump = _write_dump(tmp_path, {})
    schema = {"fields": [{"id": "a", "pdf_field_name": "f"}]}
    assert ef._extract_instructions_from_dump(schema, dump) == 0


# --- _instructions_paragraphs ----------------------------------------------- #

def test_paragraphs_split_on_blank_lines_and_formfeeds():
    text = "Para one.\n\nPara two line a\nstill two.\n\f\nPage two para."
    paras = ef._instructions_paragraphs(text)
    assert paras == ["Para one.", "Para two line a\nstill two.", "Page two para."]


def test_paragraphs_empty_text():
    assert ef._instructions_paragraphs("") == []


# --- _match_instruction_for_label ------------------------------------------- #

def test_match_picks_shortest_containing_paragraph():
    paras = [
        "Part 2. This whole section is about names and Family Name and much more text here.",
        "Family Name: enter your last name exactly as on your passport.",
    ]
    got = ef._match_instruction_for_label("Family Name", paras)
    assert got == "Family Name: enter your last name exactly as on your passport."


def test_match_is_case_insensitive():
    paras = ["ALIEN REGISTRATION NUMBER: the 9-digit A-Number."]
    assert ef._match_instruction_for_label("Alien Registration Number", paras) == paras[0]


def test_match_returns_none_when_no_paragraph_mentions_label():
    paras = ["Something unrelated entirely."]
    assert ef._match_instruction_for_label("Family Name", paras) is None


def test_match_skips_too_short_labels():
    """A label under 4 non-space chars matches too loosely; we skip it."""
    paras = ["a b c contains the letter a everywhere"]
    assert ef._match_instruction_for_label("A.", paras) is None


def test_match_is_whitespace_normalized(monkeypatch):
    """PyMuPDF wraps text mid-label, so a label "Family Name (Last Name)" must match
    a paragraph rendered "Family Name\n(Last Name): ..." -- both sides are collapsed
    to single spaces before matching (Codex PR #274). The ORIGINAL paragraph (with
    its line breaks) is returned so appended help keeps its layout."""
    para_with_breaks = "Family Name\n(Last Name): enter it exactly as on your card."
    got = ef._match_instruction_for_label("Family Name (Last Name)", [para_with_breaks])
    assert got == para_with_breaks  # original layout preserved


# --- _collapse_ws / _field_match_label -------------------------------------- #

def test_collapse_ws_collapses_newlines_and_runs():
    assert ef._collapse_ws("Family Name\n (Last  Name) ") == "Family Name (Last Name)"
    assert ef._collapse_ws("") == ""


def test_field_match_label_prefers_name_over_label():
    """The backend FormField makes `name` the display label; `label` is optional /
    a verbose breadcrumb. Match on `name` first (Codex PR #274)."""
    assert ef._field_match_label({"name": "Family Name", "label": "Part 1. ..."}) == "Family Name"


def test_field_match_label_falls_back_to_label():
    assert ef._field_match_label({"label": "Date of Birth"}) == "Date of Birth"


def test_field_match_label_empty_when_neither():
    assert ef._field_match_label({"id": "x"}) == ""


# --- _enrich_instructions_from_pdf (via monkeypatched _parse_instructions_pdf) #

def test_enrich_appends_to_tu_baseline(tmp_path, monkeypatch):
    """The instructions paragraph is APPENDED after the /TU baseline (both survive),
    separated by a blank line."""
    monkeypatch.setattr(ef, "_parse_instructions_pdf",
                        lambda _p: "Family Name: enter your last name here.")
    schema = {"fields": [{
        "id": "fam", "label": "Family Name",
        "help": {"instructions": "TU baseline text"}}]}
    assert ef._enrich_instructions_from_pdf(schema, "ignored.pdf") == 1
    assert schema["fields"][0]["help"]["instructions"] == (
        "TU baseline text\n\nFamily Name: enter your last name here.")


def test_enrich_sets_instructions_when_no_tu_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr(ef, "_parse_instructions_pdf",
                        lambda _p: "Date of Birth: use mm/dd/yyyy format.")
    schema = {"fields": [{"id": "dob", "label": "Date of Birth"}]}
    assert ef._enrich_instructions_from_pdf(schema, "x.pdf") == 1
    assert schema["fields"][0]["help"]["instructions"] == "Date of Birth: use mm/dd/yyyy format."


def test_enrich_matches_on_name_when_no_label(tmp_path, monkeypatch):
    """A contract-minimal field carries only `name` (no `label`). Enrichment must
    still match on `name` -- the bug Codex PR #274 caught (the loop keyed on
    `label`, so real extractor output got zero enrichment)."""
    monkeypatch.setattr(ef, "_parse_instructions_pdf",
                        lambda _p: "Family Name (Last Name): enter exactly as on your card.")
    schema = {"fields": [{"id": "fam", "name": "Family Name (Last Name)"}]}  # no label
    assert ef._enrich_instructions_from_pdf(schema, "x.pdf") == 1
    assert schema["fields"][0]["help"]["instructions"] == (
        "Family Name (Last Name): enter exactly as on your card.")


def test_enrich_skips_when_passage_already_in_baseline(tmp_path, monkeypatch):
    """If the /TU baseline already CONTAINS the matched passage (a form reusing the
    instructions sentence as its /TU), do not duplicate it (passage in existing)."""
    monkeypatch.setattr(ef, "_parse_instructions_pdf",
                        lambda _p: "Family Name: your last name.")
    schema = {"fields": [{
        "id": "fam", "label": "Family Name",
        "help": {"instructions": "Family Name: your last name. (extra context)"}}]}
    assert ef._enrich_instructions_from_pdf(schema, "x.pdf") == 0
    assert schema["fields"][0]["help"]["instructions"] == (
        "Family Name: your last name. (extra context)")


def test_enrich_appends_when_tu_is_a_substring_of_the_passage(tmp_path, monkeypatch):
    """The richer case: the /TU baseline is just a SUBSTRING of the instructions
    paragraph (the paragraph has MORE than the /TU). We must APPEND the richer
    passage, NOT skip it -- skipping here was the fresh-eyes bug (the old
    `existing in passage` arm silently dropped richer help, contradicting Crit 2)."""
    monkeypatch.setattr(
        ef, "_parse_instructions_pdf",
        lambda _p: "Family Name: enter exactly as on your Permanent Resident Card.")
    schema = {"fields": [{
        "id": "fam", "label": "Family Name",
        "help": {"instructions": "Family Name"}}]}  # /TU is a prefix of the passage
    assert ef._enrich_instructions_from_pdf(schema, "x.pdf") == 1
    assert schema["fields"][0]["help"]["instructions"] == (
        "Family Name\n\nFamily Name: enter exactly as on your Permanent Resident Card.")


def test_enrich_no_label_match_leaves_field(tmp_path, monkeypatch):
    monkeypatch.setattr(ef, "_parse_instructions_pdf",
                        lambda _p: "Totally unrelated instructions paragraph.")
    schema = {"fields": [{
        "id": "fam", "label": "Family Name",
        "help": {"instructions": "TU only"}}]}
    assert ef._enrich_instructions_from_pdf(schema, "x.pdf") == 0
    assert schema["fields"][0]["help"]["instructions"] == "TU only"


def test_enrich_empty_instructions_text_returns_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(ef, "_parse_instructions_pdf", lambda _p: "")
    schema = {"fields": [{"id": "fam", "label": "Family Name"}]}
    assert ef._enrich_instructions_from_pdf(schema, "x.pdf") == 0
    assert "help" not in schema["fields"][0]


def test_parse_instructions_pdf_unreadable_returns_empty(tmp_path):
    """A missing/bad instructions PDF yields "" (no enrichment), never a crash."""
    assert ef._parse_instructions_pdf(str(tmp_path / "nope.pdf")) == ""
