"""The resume stamp reaches the REAL PDF the client downloads (bd dft1).

Drives the REAL /fill-pdf route against the on-disk W-7 kit, then reopens the
returned bytes -- because that is the only thing that proves the feature.
`build_stamp` can be perfect while the client's file carries nothing.

This is the whole-path test for the "saved PDF is the save file" design: the
client's ANSWERS must come back out of the form fields AND their identity out
of the metadata, from one download.

ASCII only.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import fitz  # PyMuPDF
import pytest

from backend.routes.pdf_fill_routes import PDFFillRequest, fill_pdf
from backend.services.resume_stamp import STAMP_KEY, parse_stamp

_KIT_ROOT = Path(__file__).resolve().parents[2] / "form-kits" / "w7"

pytestmark = pytest.mark.skipif(
    not (_KIT_ROOT / "form.pdf").exists(), reason="w7 kit not present"
)


def _schema() -> dict:
    return json.loads((_KIT_ROOT / "schema.json").read_text(encoding="utf-8"))


def _fill(**extra) -> bytes:
    resp = asyncio.run(fill_pdf(PDFFillRequest(
        kit_id="w7",
        pdf_filename="form.pdf",
        field_values={"date_of_birth": "03/14/1990"},
        form_schema=_schema(),
        **extra,
    )))
    assert resp.status_code == 200
    return resp.body


def test_the_downloaded_PDF_carries_the_resume_stamp():
    """The client's real file, reopened. Nothing else proves this works."""
    doc = fitz.open(stream=_fill(form_session_id="fss_1_abc"), filetype="pdf")
    try:
        stamp = parse_stamp(doc.metadata.get(STAMP_KEY))
    finally:
        doc.close()

    assert stamp is not None, "the downloaded PDF carries no resume stamp"
    assert stamp["fsid"] == "fss_1_abc"
    assert stamp["kit"] == "w7"


def test_the_ANSWERS_and_the_IDENTITY_come_back_from_ONE_download():
    """Both halves of the save file, from the bytes the client keeps.

    If either half is missing, "the saved PDF is the save file" is false and
    resume cannot restore a client's work.
    """
    doc = fitz.open(stream=_fill(form_session_id="fss_1_abc"), filetype="pdf")
    try:
        values = {
            f.field_name: f.field_value
            for page in doc
            for f in page.widgets()
            if f.field_value
        }
        stamp = parse_stamp(doc.metadata.get(STAMP_KEY))
    finally:
        doc.close()

    assert stamp["fsid"] == "fss_1_abc", "identity missing"
    assert any("1990" in str(v) for v in values.values()), (
        "the client's own answer did not survive into the saved PDF"
    )


def test_a_STAFF_download_carries_NO_stamp():
    """No form_session_id -> no stamp.

    A staff member's download must not carry a session id: that document
    leaves the firm, and the stamp is only useful to a client resuming.
    """
    doc = fitz.open(stream=_fill(), filetype="pdf")
    try:
        assert parse_stamp(doc.metadata.get(STAMP_KEY)) is None
    finally:
        doc.close()


def test_an_older_client_that_sends_no_session_id_still_gets_its_PDF():
    """The field is optional: a stale frontend must not break downloading."""
    body = _fill()
    assert body[:4] == b"%PDF"
    assert len(body) > 10_000


def test_a_HOSTILE_session_id_is_stamped_but_refused_on_READ():
    """Defence is at the READ, and that is the honest place for it.

    The client supplies form_session_id, so a traversal string can reach the
    file. What must never happen is that value being TRUSTED when the PDF
    comes back -- parse_stamp refuses it, so a resume treats the file as
    having no hint rather than reaching for ../../etc/passwd.
    """
    doc = fitz.open(
        stream=_fill(form_session_id="../../../etc/passwd"), filetype="pdf"
    )
    try:
        assert parse_stamp(doc.metadata.get(STAMP_KEY)) is None
    finally:
        doc.close()
