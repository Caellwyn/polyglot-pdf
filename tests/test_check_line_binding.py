"""Tests for scripts/authoring/check_line_binding.py (bd polyglot-pdf-3ave).

The oracle detects the off-by-N field->widget assignment class that no existing
gate can see (three shipped instances: bd 13vo i-90, bd ivh9 w7, bd 3ave f1040).
It grades a draft against the PDF's own printed line markers -- no gold schema
and no model in the loop.

Pins, in order: the real f1040 corruption is caught, the fresh extraction's
residual shift is caught, a correct binding is silent, the gutter-column rule
that kills body-text false positives holds, and abstention is honest (a form it
cannot verify reports so rather than passing).

Imports by file path (repo precedent: test_eval_extraction).
ASCII only.
"""

import importlib.util
import json
import pathlib
import sys

import pytest

_REPO = pathlib.Path(__file__).resolve().parent.parent
_SCRIPT = _REPO / "scripts" / "authoring" / "check_line_binding.py"
spec = importlib.util.spec_from_file_location("check_line_binding", _SCRIPT)
clb = importlib.util.module_from_spec(spec)
sys.modules["check_line_binding"] = clb
spec.loader.exec_module(clb)

_F1040_PDF = _REPO / "form-kits" / "f1040" / "form.pdf"
_F1040_SCHEMA = _REPO / "form-kits" / "f1040" / "schema.json"
# The CORRUPT specimen these detection tests grade against (bd polyglot-pdf-3ave
# fixed the live kit). They used to read the SHIPPED schema, which meant "the
# oracle detects the shift" was pinned to the shift STAYING UNFIXED -- fixing
# the kit inverted four tests and would have merged CI-red. schema_archived.json
# is the frozen pre-fix binding (20 findings, fld_9 on the printed 6a box), so
# the detection stays pinned forever and the shipped kit is free to be correct.
_F1040_CORRUPT_SCHEMA = _REPO / "form-kits" / "f1040" / "schema_archived.json"

# w7 is the ABSTENTION fixture: it prints markers but has no field that both
# states a line number and claims a widget on a marked row, so the oracle
# verifies nothing on it -- which is what the abstention contract must cover.
_W7_PDF = _REPO / "form-kits" / "w7" / "form.pdf"
_W7_SCHEMA = _REPO / "form-kits" / "w7" / "schema.json"

needs_f1040 = pytest.mark.skipif(
    not _F1040_PDF.exists(), reason="f1040 kit not present")
needs_w7 = pytest.mark.skipif(
    not _W7_PDF.exists(), reason="w7 kit not present")

pytest.importorskip("fitz", reason="PyMuPDF required for the geometry oracle")


# --------------------------------------------------------------------------- #
# Unit: the line number a field claims to be
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("field,expected", [
    ({"id": "fld_1a"}, "1a"),
    ({"id": "line_11a"}, "11a"),
    ({"id": "line_9"}, "9"),
    ({"id": "whatever", "name": "2b Taxable interest"}, "2b"),
    ({"id": "whatever", "name": "Line 16 Other"}, "16"),
    # No stated line -> not judged at all (the conservative contract).
    ({"id": "mailing_street"}, None),
    ({"id": "p1_extra_75"}, None),
    # A year/form number in a label must not be read as a line marker.
    ({"id": "x", "name": "Form 1099-R distributions"}, None),
])
def test_stated_line_parsing(field, expected):
    assert clb._stated_line(field) == expected


def test_iter_fields_walks_nested_parts_and_sections():
    schema = {"parts": [{"sections": [{"fields": [
        {"id": "a", "pdf_field_name": "w1"},
        {"id": "b", "pdf_field_name": "w2"},
    ]}]}]}
    assert {f["id"] for f in clb._iter_fields(schema)} == {"a", "b"}


# --------------------------------------------------------------------------- #
# The real forms: catches the known corruption, stays quiet on correct bindings
# --------------------------------------------------------------------------- #

@needs_f1040
def test_catches_the_shipped_f1040_line_shift():
    """The shipped kit's page-1 income block is shifted (bd 3ave). Every finding
    must name a field whose claimed widget is printed on a DIFFERENT line."""
    schema = json.loads(_F1040_CORRUPT_SCHEMA.read_text(encoding="utf-8"))
    result = clb.check(schema, str(_F1040_PDF))
    found = {f["field_id"] for f in result["findings"]}
    # Spot-pin the hand-verified worst cases (see bd 3ave):
    #   fld_9 (total income) sits on the printed line 6a box.
    for expected in ("fld_9", "fld_10", "fld_11a"):
        assert expected in found, f"{expected} no longer detected"
    by_id = {f["field_id"]: f for f in result["findings"]}
    assert by_id["fld_9"]["widget_is_on_line"] == "6a"
    assert by_id["fld_10"]["widget_is_on_line"] == "6b"
    # It is a real detection, not a blanket failure: most fields are fine.
    assert 0 < len(result["findings"]) < result["checked"]


@needs_f1040
def test_a_correct_binding_produces_no_finding():
    """Rebinding a field to the widget printed on its OWN line clears it --
    the oracle keys on the printed marker, not on the field being suspicious."""
    schema = json.loads(_F1040_CORRUPT_SCHEMA.read_text(encoding="utf-8"))
    before = {f["field_id"] for f in clb.check(schema, str(_F1040_PDF))["findings"]}
    assert "fld_9" in before

    # f1_73 is the widget printed on line 9 (verified against the PDF).
    def fix(o):
        if isinstance(o, dict):
            if o.get("id") == "fld_9":
                o["pdf_field_name"] = "topmostSubform[0].Page1[0].f1_73[0]"
            for v in o.values():
                fix(v)
        elif isinstance(o, list):
            for v in o:
                fix(v)
    fix(schema)
    after = {f["field_id"] for f in clb.check(schema, str(_F1040_PDF))["findings"]}
    assert "fld_9" not in after


# --------------------------------------------------------------------------- #
# The false-positive regression that shaped the gutter rule
# --------------------------------------------------------------------------- #

@needs_f1040
def test_body_text_numerals_are_not_read_as_line_markers():
    """f1040's line-4c row prints a checkbox legend '1 Rollover 2 QCD 3' whose
    trailing '3' sits ~50pt left of the row's widget. A proximity-only rule read
    that as 'line 3' and reported three bogus mismatches. Only markers in a
    RECURRING gutter column count, so no finding may claim line '3' here."""
    schema = json.loads(_F1040_SCHEMA.read_text(encoding="utf-8"))
    result = clb.check(schema, str(_F1040_PDF))
    assert all(f["widget_is_on_line"] != "3" for f in result["findings"]), \
        "a body-text numeral was mistaken for a printed gutter marker"


@needs_f1040
def test_an_option_carrying_its_own_id_is_not_judged_as_a_field():
    """_iter_fields yields any dict with a string `id`, so an option with an `id`
    was yielded as a FIELD and its LABEL read as a stated line. An option labelled
    "1 Yes" on a correctly bound widget printed on row 6a produced a confident
    false finding -- the "1" is list-item text, not a line number.

    Dormant on current data (no shipped or fresh schema gives options ids) but
    f1040 already ships option labels that parse as markers ("1 Rollover",
    "2 QCD", "1 Line 3a"); only the `id` was missing, and the sibling overlay's
    tests treat an option `id` as a normal shape.
    """
    schema = json.loads(_F1040_SCHEMA.read_text(encoding="utf-8"))
    base = clb.check(json.loads(json.dumps(schema)), str(_F1040_PDF))

    schema["fields"].append({
        "id": "choice_x", "type": "radio", "options": [
            # Correctly bound: f1_68[0] IS the line-6a widget. Only the label's
            # leading numeral could make this look like a line-1 claim.
            {"id": "opt_yes", "label": "1 Yes",
             "pdf_field_name": "topmostSubform[0].Page1[0].f1_68[0]"},
        ],
    })
    after = clb.check(schema, str(_F1040_PDF))

    assert len(after["findings"]) == len(base["findings"]), \
        "an option was judged as a field and produced a false finding"
    assert after["checked"] == base["checked"], \
        "an option was counted as a verifiable field"
    assert "opt_yes" not in {f["field_id"] for f in after["findings"]}


@needs_f1040
def test_the_f1040_checkbox_legend_is_not_read_as_a_gutter():
    """The REAL property, not the accidental survivor.

    f1040's line-4c/5a/5b rows each print the legend "1 Rollover 2 QCD 3", so the
    legend's '1' (x_right 278.0) and '2' (x_right 357.2) each recur on THREE rows
    -- clearing the recurrence threshold outright. Recurrence alone therefore does
    not identify a gutter; the column must also carry DISTINCT marker texts.

    The earlier test only asserted that no finding claimed line '3'. That held by
    coincidence, not by the rule: under the old collector the legend markers WERE
    paired with the legend checkboxes, and no finding fired only because those
    options are labelled "1 Rollover" / "2 QCD", so the parsed line happened to
    EQUAL the legend numeral. This asserts the marker set directly instead, so the
    rule cannot silently rot behind a coincidence.
    """
    import fitz
    markers = clb.collect_markers(fitz.open(str(_F1040_PDF))[0])
    assert markers, "the real gutters must still be found"
    legend = [m for m in markers if abs(m[1] - 278.0) < 3 or abs(m[1] - 357.2) < 3]
    assert not legend, f"legend numerals accepted as gutter markers: {legend}"
    # Both REAL gutters survive: the left row numbers and the amount column
    # (x~495-500), which is where most f1040 findings come from. A position-based
    # rule (e.g. leftmost-column-wins) would drop the amount column and take the
    # finding count from 20 to 0.
    edges = {round(m[1]) for m in markers}
    assert any(e <= 110 for e in edges), "left gutter lost"
    assert any(490 <= e <= 505 for e in edges), "amount-column gutter lost"


def test_collect_markers_rejects_a_column_that_repeats_a_token():
    """A gutter numbers rows and a row number appears ONCE per page, so a gutter
    column's tokens are all distinct. A legend prints the same token on every row
    it labels.

    The stray-token case is the load-bearing one: an earlier version asked for
    ">= 2 distinct texts" and computed that over the column's padded BAND, so a
    single unrelated token near the column supplied the variety and rescued the
    whole legend. Requiring UNIQUENESS closes that -- a neighbour can join a
    cluster, but it cannot remove a repeat.
    """
    class _Page:
        def __init__(self, words):
            self._w = words

        def get_text(self, _kind):
            return self._w

    same = _Page([(0, 100 + 12 * i, 300, 110 + 12 * i, "1", 0, 0, 0)
                  for i in range(4)])
    assert clb.collect_markers(same) == []

    # The same legend plus ONE unrelated token just outside the column but
    # inside the tolerance. Must still be rejected.
    rescued = _Page([(0, 100 + 12 * i, 300, 110 + 12 * i, "1", 0, 0, 0)
                     for i in range(4)]
                    + [(0, 200, 302.4, 210, "7", 0, 0, 0)])
    assert clb.collect_markers(rescued) == [], \
        "a neighbouring token rescued a repeated-token legend column"

    varied = _Page([(0, 100 + 12 * i, 300, 110 + 12 * i, f"{i + 1}a", 0, 0, 0)
                    for i in range(4)])
    assert len(clb.collect_markers(varied)) == 4


@needs_f1040
def test_the_page2_prose_column_is_suppressed_by_the_ROW_guard():
    """Pins WHICH guard suppresses f1040 page 2's accepted prose column, because
    the KNOWN BLIND SPOTS note is prescriptive -- it tells the next maintainer
    which geometry makes this tool go false-positive.

    The proximity guard (_GUTTER_MAX_DX) does NOT do it: 18 marker/widget pairs
    there pass it. The ROW guard does -- the prose and those widgets never share
    a vertical band. So the risk is prose sharing a ROW with an entry widget, not
    prose merely being near one.
    """
    import fitz

    page = fitz.open(str(_F1040_PDF))[1]
    prose = [m for m in clb.collect_markers(page) if 155 <= m[1] <= 175]
    assert prose, "expected f1040 p2's cross-reference numerals to form a column"

    widgets = [w.rect for w in page.widgets()]
    x_ok = row_ok = 0
    for _text, mx1, y0, y1 in prose:
        mid = (y0 + y1) / 2
        for rect in widgets:
            if 0 <= rect.x0 - mx1 <= clb._GUTTER_MAX_DX:
                x_ok += 1
                if rect.y0 - clb._ROW_PAD <= mid <= rect.y1 + clb._ROW_PAD:
                    row_ok += 1

    assert x_ok > 0, "the proximity guard is NOT what suppresses these"
    assert row_ok == 0, "the row guard is what suppresses these"

    # And end to end: no page-2 finding cites one of these prose numerals.
    schema = json.loads(_F1040_SCHEMA.read_text(encoding="utf-8"))
    result = clb.check(schema, str(_F1040_PDF))
    prose_texts = {m[0] for m in prose}
    for f in result["findings"]:
        if f["page"] == 2:
            assert f["widget_is_on_line"] not in prose_texts, \
                f"a page-2 prose numeral produced a finding: {f}"


@needs_f1040
def test_uniqueness_is_a_PER_COLUMN_rule_not_a_per_page_one():
    """Pins the SCOPE of the uniqueness rule, because the two readings differ on
    real data and only one of them works.

    Per column: a gutter numbers successive rows, so no text repeats -- true, and
    what the code enforces. Per page: FALSE on f1040, which prints each line
    number in BOTH the left gutter and the amount column ('2a', '8', '9' twice on
    page 1; up to three times on page 2). Hoisting the check to page scope would
    reject both real gutters and take the tool from 20 findings to 0.
    """
    import fitz
    from collections import Counter

    doc = fitz.open(str(_F1040_PDF))
    saw_page_level_repeat = False
    for page in doc:
        markers = clb.collect_markers(page)
        if not markers:
            continue
        # Per-column: must hold everywhere.
        by_col: dict[int, list[str]] = {}
        for text, x1, _y0, _y1 in markers:
            by_col.setdefault(round(x1 / 3), []).append(text)
        for texts in by_col.values():
            assert len(set(texts)) == len(texts), \
                f"accepted a gutter column with a repeated marker: {texts}"
        # Per-page: must NOT be assumed -- record that it genuinely fails.
        if any(n > 1 for n in Counter(t for t, *_ in markers).values()):
            saw_page_level_repeat = True

    assert saw_page_level_repeat, (
        "f1040 is expected to repeat marker texts across columns on a page; if "
        "this ever stops being true, the per-column vs per-page distinction in "
        "collect_markers is no longer load-bearing and the comment should change")


def test_collect_markers_requires_a_recurring_column():
    """A lone marker-shaped token is body text, not a gutter."""
    class _Page:
        def __init__(self, words):
            self._w = words

        def get_text(self, _kind):
            return self._w

    # One stray "3" -> no column -> no markers.
    stray = _Page([(0, 100, 422, 110, "3", 0, 0, 0)])
    assert clb.collect_markers(stray) == []

    # Four tokens sharing a right edge -> a real gutter column.
    col = _Page([(0, 100 + 12 * i, 498, 110 + 12 * i, f"{i + 1}a", 0, 0, 0)
                 for i in range(4)])
    assert len(clb.collect_markers(col)) == 4


# --------------------------------------------------------------------------- #
# Honest abstention: silence is never reported as a clean bill of health
# --------------------------------------------------------------------------- #

def test_a_form_with_no_markers_abstains_loudly():
    result = {"findings": [], "checked": 0, "markers": 0}
    text = clb.render(result)
    assert "NOT a clean bill of health" in text


def test_abstention_does_not_lead_with_the_ok_token():
    """A caller grepping for 'OK:' -- or reading only the first line of a
    truncated log -- must not read abstention as a pass. Text twin of the
    exit-code contract (rc 3)."""
    text = clb.render({"findings": [], "checked": 0, "markers": 10})
    assert text.splitlines()[0].startswith("ABSTAINED:")
    assert "OK:" not in text
    # w7 abstains WITH markers present, so the message must not claim the form
    # prints none -- it reports the marker count and the real precondition.
    assert "10 printed marker(s)" in text


def test_an_unreadable_pdf_is_a_usage_error_not_a_traceback(tmp_path, capsys):
    schema = tmp_path / "s.json"
    schema.write_text(json.dumps({"fields": []}), encoding="utf-8")
    rc = clb.main(["--schema", str(schema),
                   "--pdf", str(tmp_path / "does-not-exist.pdf")])
    capsys.readouterr()
    assert rc == 2, "a missing PDF must exit 2, not raise or collide with rc 1"


@needs_f1040
def test_an_unwritable_json_path_exits_two_without_printing_ok(tmp_path, capsys):
    """The --json write is the third IO path and was unguarded: it raised
    FileNotFoundError AFTER render() had already printed its OK line, and
    Python's rc=1 collided with 'mismatches found'."""
    bad = tmp_path / "no-such-dir" / "deep" / "out.json"
    rc = clb.main(["--schema", str(_F1040_SCHEMA), "--pdf", str(_F1040_PDF),
                   "--json", str(bad)])
    captured = capsys.readouterr()
    assert rc == 2, "an unwritable --json must exit 2, not 1"
    assert "OK:" not in captured.out
    assert "MISMATCH" not in captured.out, \
        "the report must not print before a failed write"


def test_a_verified_clean_form_says_so():
    result = {"findings": [], "checked": 12, "markers": 30}
    text = clb.render(result)
    assert "OK:" in text and "NOT a clean bill of health" not in text


def test_total_abstention_does_not_exit_zero(tmp_path, capsys, monkeypatch):
    """rc==0 must mean VERIFIED-clean, never 'I checked nothing'. A lint-style
    caller gating on `rc == 0` would otherwise read total abstention as a pass --
    the exact failure mode this tool exists to prevent."""
    monkeypatch.setattr(clb, "check",
                        lambda *a, **k: {"findings": [], "checked": 0,
                                         "markers": 0})
    schema = tmp_path / "s.json"
    schema.write_text(json.dumps({"fields": []}), encoding="utf-8")

    rc = clb.main(["--schema", str(schema), "--pdf", "unused.pdf"])
    capsys.readouterr()
    assert rc == 3, "abstention must be distinguishable from a verified pass"

    rc_ci = clb.main(["--schema", str(schema), "--pdf", "unused.pdf",
                      "--require-verified"])
    capsys.readouterr()
    assert rc_ci == 1, "--require-verified must make abstention a hard failure"


def test_a_verified_clean_run_exits_zero(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(clb, "check",
                        lambda *a, **k: {"findings": [], "checked": 7,
                                         "markers": 20})
    schema = tmp_path / "s.json"
    schema.write_text(json.dumps({"fields": []}), encoding="utf-8")
    rc = clb.main(["--schema", str(schema), "--pdf", "unused.pdf",
                   "--require-verified"])
    capsys.readouterr()
    assert rc == 0


@needs_w7
def test_the_json_payload_marks_abstention_explicitly(tmp_path, capsys):
    """The JSON is the one machine-readable channel, so abstention must be
    EXPLICIT there too -- {"findings": [], "checked": 0} is otherwise
    shape-identical to a verified-clean run, and a consumer written to "no
    findings means pass" would reproduce the exact failure rc 3 prevents."""
    out = tmp_path / "w7.json"
    rc = clb.main(["--schema", str(_W7_SCHEMA), "--pdf", str(_W7_PDF),
                   "--json", str(out)])
    capsys.readouterr()
    assert rc == 3
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["abstained"] is True


@needs_f1040
def test_the_json_payload_marks_a_verified_run_not_abstained(tmp_path, capsys):
    out = tmp_path / "f1040.json"
    clb.main(["--schema", str(_F1040_CORRUPT_SCHEMA), "--pdf", str(_F1040_PDF),
              "--json", str(out)])
    capsys.readouterr()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["abstained"] is False
    assert payload["findings"]


@needs_f1040
def test_exit_code_signals_findings(tmp_path, capsys):
    rc = clb.main(["--schema", str(_F1040_CORRUPT_SCHEMA), "--pdf", str(_F1040_PDF),
                   "--json", str(tmp_path / "out.json")])
    capsys.readouterr()
    assert rc == 1  # the ARCHIVED pre-fix kit is known-corrupt
    payload = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    assert payload["findings"] and payload["checked"] > 0
@needs_f1040
def test_the_corrupt_specimen_is_still_the_pre_fix_binding():
    """Pin the identity of the file the four detection tests grade against.

    `schema_archived.json` is the MIGRATION TOOL's backup convention
    (`scripts/migrate_schema_v2.py --archive`), not a review-owned fixture --
    re-running that migration on f1040 would overwrite it and silently gut the
    detection tests above, which would then abstain or invert with nobody
    noticing. This asserts the specimen still exhibits the exact bd
    polyglot-pdf-3ave shift it is supposed to represent. (Same guard shape as
    `test_archived_i90_is_the_v1_original` in tests/test_i90_migrated_baseline.py.)
    """
    schema = json.loads(_F1040_CORRUPT_SCHEMA.read_text(encoding="utf-8"))
    result = clb.check(schema, str(_F1040_PDF))
    assert len(result["findings"]) == 20, (
        f"the corrupt specimen now yields {len(result['findings'])} findings, "
        f"not the 20 of the pre-fix kit -- schema_archived.json was probably "
        f"regenerated, which would leave the detection tests toothless"
    )
    by_id = {f["field_id"]: f for f in result["findings"]}
    assert by_id["fld_9"]["widget_is_on_line"] == "6a"
    assert by_id["fld_11a"]["widget_is_on_line"] == "7a"
