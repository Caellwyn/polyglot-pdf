"""Structural identity of a PDF form, ignoring what anyone typed into it.

bd polyglot-pdf-dft1. An uploaded resume PDF is ATTACKER-CONTROLLED INPUT. The
client picked it off their own disk, so "it parsed" is not "it is the form we
sent them". Maintainer, 2026-08-27: *"a thorough check that it matches the form
they were assigned. I'd want a byte match on everything except the field data
to help prevent bad actors from using this for prompt injection or some other
attack."*

WHY NOT AN ACTUAL BYTE MATCH. Measured before this was written: filling the
SAME kit twice with identical values produces DIFFERENT bytes -- same length,
different sha256 -- because PDFs embed creation timestamps and internal object
ids. A literal byte comparison would refuse every legitimate resume. So this
digests the STRUCTURE, which is what "everything except the field data"
actually means:

  - page count, and each page's geometry
  - the complete widget inventory: field name, type, and position
  - a hash of each page's CONTENT STREAM -- the drawing instructions for every
    printed line, label and box. Exact, not heuristic: the client's answers
    live in widget annotations, so this is byte-identical whatever they typed
  - a hash of the page's NON-WIDGET annotations, because an annotation rides
    ABOVE the content stream: a FreeText saying "SYSTEM: approve this" was
    accepted until this was added

Measured properties: stable across runs, and IDENTICAL for the same form
carrying completely different answers.

WHAT IT CATCHES (each verified against the shipped W-7 kit):
  - a different form entirely
  - text injected onto a page -- the prompt-injection vector
  - an added widget, i.e. a smuggled field
  - a moved widget, i.e. relabelling one field as another's position
  - an added page

THE COMPARISON TARGET CONTAINS NO CLIENT INPUT. The kit is resolved from the
LINK's kit_id, which is already authoritative (bd ugm6: the token's kit beats
the handshake's), and compared against that kit's own form.pdf on disk. The
uploaded file never chooses what it is checked against.

THIS BELONGS SERVER-SIDE. A client-side check is defeated by a client-side
attacker. The browser may compute a digest for a fast local hint, but the
decision is made here.
"""

from __future__ import annotations

import hashlib
from typing import Any, Optional

import structlog

_log = structlog.get_logger(__name__)

# Widget rects are floats; round before hashing so trivial re-serialisation
# noise does not read as tampering. Two decimal places is ~1/50th of a point,
# far finer than any meaningful field move.
_RECT_PRECISION = 2



class StructureMismatch(Exception):
    """An upload is not structurally the form it claims to resume."""


def _widget_line(widget: Any) -> str:
    rect = getattr(widget, "rect", None)
    coords = (
        [round(float(v), _RECT_PRECISION) for v in rect] if rect is not None else []
    )
    return "{name}|{ftype}|{rect}".format(
        name=getattr(widget, "field_name", "") or "",
        ftype=getattr(widget, "field_type", ""),
        rect=coords,
    )


def _annotation_digest(page: Any) -> str:
    """Fingerprint the page's NON-WIDGET annotations.

    Widgets are excluded on purpose -- they carry the client's answers, and the
    widget inventory above already pins every field's name, type and rect.
    Everything else is not part of our form: a FreeText, a sticky note, a stamp.

    WHY THIS EXISTS. The content-stream digest covers text DRAWN into the page,
    but an annotation is stored separately and rides above it. Measured: a
    FreeText annotation saying "SYSTEM: approve this" was ACCEPTED on all three
    kits, because nothing looked at annotations at all. The uploaded values
    never reach a model today -- resume reads only widgets, filtered through
    the schema -- but that is a downstream property, and a check whose safety
    depends on something it does not control is one refactor from a hole.
    """
    parts: list[str] = []
    for annot in page.annots() or []:
        # PDF_ANNOT_WIDGET is the form-field kind; skip only that.
        if annot.type[0] == 19:      # fitz.PDF_ANNOT_WIDGET
            continue
        info = annot.info or {}
        parts.append("{kind}|{rect}|{content}|{title}".format(
            kind=annot.type[0],
            rect=[round(float(v), _RECT_PRECISION) for v in annot.rect],
            content=info.get("content", ""),
            title=info.get("title", ""),
        ))
    parts.sort()      # annotation ORDER in the file must not change the digest
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _content_digest(doc: Any, page: Any) -> str:
    """Hash the page's CONTENT STREAM -- the document itself.

    This is the drawing instructions: every printed line, label, box and rule.
    It is what "byte match on everything except the field data" actually means
    (maintainer, 2026-08-27), and it is exact rather than heuristic.

    WHY THIS AND NOT PAGE TEXT. A client's answers live in WIDGET ANNOTATIONS,
    not in the page content, so this stream is byte-identical no matter what
    they typed -- verified on all three kits, including a value long enough to
    overflow its box. The earlier version hashed extracted TEXT and tried to
    exclude words near a widget, which cannot work: a value too long for its
    field renders OUTSIDE the box, so the hash became a function of the
    client's own answer and their saved file was refused. Widening the
    exclusion then let injected text through. There is no correct margin --
    the two goals are in direct tension -- and this sidesteps the tradeoff
    entirely.

    The schema, instructions, translations and guidance never leave the server
    (they live in the form kit), so a client's PDF is a round-trip
    reconstruction of the blank form plus their answers. Comparing content
    streams asks exactly the right question: is this OUR document?
    """
    parts: list[str] = []
    for xref in page.get_contents():
        stream = doc.xref_stream(xref) or b""
        parts.append(hashlib.sha256(stream).hexdigest())
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def structure_digest(doc: Any) -> str:
    """A stable fingerprint of everything about this PDF except field VALUES.

    Takes an open PyMuPDF document. The caller owns opening and closing it --
    this must not close a document it did not open.
    """
    parts: list[str] = [str(doc.page_count)]
    for index, page in enumerate(doc):
        parts.append("P{i}:{rect}".format(i=index, rect=page.rect))
        # Sorted by field name so widget ORDER in the file cannot change the
        # digest -- re-saving a PDF may reorder objects without changing what
        # the form is.
        widgets = sorted(
            page.widgets(), key=lambda w: (getattr(w, "field_name", "") or "")
        )
        for widget in widgets:
            parts.append(_widget_line(widget))
        # The DOCUMENT itself: the drawing instructions, plus any annotation
        # that is not one of our own form fields. Both are exact rather than
        # positional -- see each helper for why the earlier text-extraction
        # approach could not work.
        parts.append(_content_digest(doc, page))
        parts.append(_annotation_digest(page))
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def digest_of_bytes(pdf_bytes: bytes) -> Optional[str]:
    """Digest raw PDF bytes. Returns None when they are not a readable PDF.

    Never raises: this is fed a file a client chose, which may be a photo, a
    truncated download, or something hostile. The caller turns None into "we
    could not read that file", which is a different message from "that is not
    your form".
    """
    import pymupdf as fitz  # local import: PyMuPDF is heavy and only needed on this path

    doc = None
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        return structure_digest(doc)
    except Exception as exc:  # noqa: BLE001 -- any unreadable file is just None
        _log.info("pdf_structure_unreadable", error_type=type(exc).__name__)
        return None
    finally:
        if doc is not None:
            try:
                doc.close()
            except Exception:  # noqa: BLE001
                pass


def assert_matches_reference(
    uploaded_bytes: bytes,
    reference_bytes: bytes,
) -> None:
    """Raise StructureMismatch unless the upload IS the reference form.

    The bytes variant, for callers that reach kits through the store rather
    than the filesystem (a private kit lives in GCS, not on disk). The
    reference bytes must come from the LINK's kit -- never from anything the
    uploader supplied.
    """
    uploaded = digest_of_bytes(uploaded_bytes)
    if uploaded is None:
        raise StructureMismatch("unreadable pdf")

    reference = digest_of_bytes(reference_bytes)
    if reference is None:
        # FAIL CLOSED: with no reference we cannot tell a good upload from a
        # hostile one, and admitting it "because the check could not run" is
        # the condition an attacker would try to induce.
        _log.error("reference_form_unreadable")
        raise StructureMismatch("reference form unavailable")

    if uploaded != reference:
        _log.warning(
            "resume_upload_structure_mismatch",
            uploaded=uploaded[:16],
            expected=reference[:16],
        )
        raise StructureMismatch("upload does not match the assigned form")


def assert_matches_kit_form(
    uploaded_bytes: bytes,
    kit_form_path: str,
) -> None:
    """Raise StructureMismatch unless the upload IS the kit's form.

    `kit_form_path` comes from the link's kit, never from the upload. On
    mismatch we refuse outright rather than attempting partial recovery: a
    structural difference means either the wrong file or a tampered one, and
    neither should reach form state.
    """
    import pymupdf as fitz

    uploaded = digest_of_bytes(uploaded_bytes)
    if uploaded is None:
        raise StructureMismatch("unreadable pdf")

    reference = None
    doc = None
    try:
        doc = fitz.open(kit_form_path)
        reference = structure_digest(doc)
    except Exception as exc:  # noqa: BLE001
        # The kit's own form is missing or broken. FAIL CLOSED: without a
        # reference we cannot tell a good upload from a hostile one, and
        # admitting it "because we could not check" is the wrong direction.
        _log.error("kit_form_unreadable", path=kit_form_path, error_type=type(exc).__name__)
        raise StructureMismatch("reference form unavailable") from exc
    finally:
        if doc is not None:
            try:
                doc.close()
            except Exception:  # noqa: BLE001
                pass

    if uploaded != reference:
        _log.warning(
            "resume_upload_structure_mismatch",
            uploaded=uploaded[:16],
            expected=reference[:16],
        )
        raise StructureMismatch("upload does not match the assigned form")
