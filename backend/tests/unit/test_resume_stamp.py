"""The resume stamp (bd polyglot-pdf-dft1).

Two jobs, and the second is the one that would otherwise rot:

  1. build/parse round-trips, and every hostile input degrades to "no hint"
     rather than raising -- this parses a file the client can hand-edit.
  2. the stamp actually SURVIVES a real PyMuPDF save/reload, which is the
     whole premise. A unit test of build_stamp alone would pass happily while
     the bytes the client keeps carried nothing.
"""

import json

import pymupdf as fitz  # PyMuPDF
import pytest

from backend.services.resume_stamp import (
    MAX_STAMP_BYTES,
    STAMP_KEY,
    STAMP_VERSION,
    build_stamp,
    parse_stamp,
)


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_a_stamp_round_trips():
    raw = build_stamp("fss_1_a", "i-90", ["jti-a", "jti-b"], "3")
    got = parse_stamp(raw)
    assert got == {
        "v": STAMP_VERSION,
        "fsid": "fss_1_a",
        "kit": "i-90",
        "sv": "3",
        "jtis": ["jti-a", "jti-b"],
    }


def test_the_jti_ORDER_is_preserved():
    """The order is the client's link history (bd 1uyof) -- which came first."""
    raw = build_stamp("fss_1_a", "i-90", ["second", "first", "third"])
    assert parse_stamp(raw)["jtis"] == ["second", "first", "third"]


def test_duplicate_jtis_are_collapsed():
    raw = build_stamp("fss_1_a", "i-90", ["a", "a", "b", "a"])
    assert parse_stamp(raw)["jtis"] == ["a", "b"]


def test_a_STAFF_download_is_not_stamped():
    """No form_session_id means no resume hint -- and no session id inside a
    document that leaves the firm."""
    assert build_stamp(None, "i-90") is None
    assert build_stamp("", "i-90") is None


def test_a_minimal_stamp_needs_only_the_session_id():
    got = parse_stamp(build_stamp("fss_1_a", None))
    assert got["fsid"] == "fss_1_a"
    assert "kit" not in got and "jtis" not in got


# ---------------------------------------------------------------------------
# Hostile input -- a client can edit this file
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        None, "", "   ", "not json", "{", "[]", "null", "42", '"a string"',
        "{}",                                    # no version, no fsid
        '{"v":1}',                               # no fsid
        '{"fsid":"fss_1_a"}',                    # no version
        '{"v":"1","fsid":"fss_1_a"}',            # version not an int
        '{"v":true,"fsid":"fss_1_a"}',           # bool is not a version
        '{"v":999,"fsid":"fss_1_a"}',            # unknown FUTURE version
        '{"v":1,"fsid":""}',                     # empty session id
        '{"v":1,"fsid":123}',                    # session id not a string
    ],
)
def test_unusable_input_degrades_to_NO_HINT_and_never_raises(raw):
    assert parse_stamp(raw) is None


@pytest.mark.parametrize(
    "hostile",
    [
        "../../../etc/passwd",
        "..\\\\..\\\\windows\\\\system32",
        "fss/../../secret",
        "CON", "PRN", "NUL", "COM1",          # Windows device names
        "trailing.",                            # Windows strips trailing dots
        "...",
        "a" * 500,                              # length bound
    ],
)
def test_a_hand_edited_session_id_that_reaches_a_FILENAME_is_refused(hostile):
    """confirmation_logger names a per-session FILE from this value.

    So a stamp is a path-traversal vector unless it is validated here. The
    guard is confirmation_logger's own, reused rather than re-implemented --
    it was hardened adversarially and a second copy would drift.
    """
    raw = json.dumps({"v": STAMP_VERSION, "fsid": hostile})
    assert parse_stamp(raw) is None


def test_an_OVERSIZED_stamp_is_refused_before_parsing():
    """A hand-edited file must not feed megabytes into json.loads."""
    raw = json.dumps({"v": STAMP_VERSION, "fsid": "fss_1_a", "pad": "x" * MAX_STAMP_BYTES})
    assert len(raw) > MAX_STAMP_BYTES
    assert parse_stamp(raw) is None


def test_a_pdf_whose_keywords_are_ORDINARY_keywords_is_not_an_error():
    """That field exists for keywords. Not ours is not a failure."""
    assert parse_stamp("immigration, i-90, 2026") is None


def test_junk_jtis_are_dropped_but_the_stamp_still_resumes():
    """A partly-corrupt list must not cost the client their whole resume."""
    raw = json.dumps({"v": STAMP_VERSION, "fsid": "fss_1_a",
                      "jtis": ["good", 42, None, "", {"a": 1}, "also-good"]})
    got = parse_stamp(raw)
    assert got["fsid"] == "fss_1_a"
    assert got["jtis"] == ["good", "also-good"]


# ---------------------------------------------------------------------------
# The premise: it survives a REAL PyMuPDF save/reload
# ---------------------------------------------------------------------------


def test_the_stamp_SURVIVES_a_real_pdf_save_and_reload():
    """The whole design rests on this, so it is asserted on real bytes.

    build_stamp could be perfect and the feature still dead if the metadata
    did not survive the save the client's browser downloads.
    """
    doc = fitz.open()
    doc.new_page()
    raw = build_stamp("fss_1_a", "i-90", ["jti-a"], "3")
    meta = doc.metadata or {}
    meta[STAMP_KEY] = raw
    doc.set_metadata(meta)
    saved = doc.tobytes()
    doc.close()

    reopened = fitz.open(stream=saved, filetype="pdf")
    try:
        got = parse_stamp(reopened.metadata.get(STAMP_KEY))
    finally:
        reopened.close()
    assert got["fsid"] == "fss_1_a"
    assert got["jtis"] == ["jti-a"]


def test_the_client_FIELD_VALUES_survive_alongside_the_stamp():
    """The other half of the save file: their answers.

    The stamp carries identity; the form fields carry the work. Both must
    come back, or "the saved PDF is the save file" is only half true.
    """
    doc = fitz.open()
    page = doc.new_page()
    widget = fitz.Widget()
    widget.field_name = "applicant_last_name"
    widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    widget.rect = fitz.Rect(50, 50, 250, 70)
    widget.field_value = "Okonkwo"
    page.add_widget(widget)
    meta = doc.metadata or {}
    meta[STAMP_KEY] = build_stamp("fss_1_a", "i-90")
    doc.set_metadata(meta)
    saved = doc.tobytes()
    doc.close()

    reopened = fitz.open(stream=saved, filetype="pdf")
    try:
        values = {f.field_name: f.field_value for p in reopened for f in p.widgets()}
        stamp = parse_stamp(reopened.metadata.get(STAMP_KEY))
    finally:
        reopened.close()
    assert values == {"applicant_last_name": "Okonkwo"}
    assert stamp["fsid"] == "fss_1_a"
