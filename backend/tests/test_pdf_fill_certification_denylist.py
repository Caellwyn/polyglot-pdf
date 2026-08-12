"""The fill route must NEVER write an interpreter/preparer certification block.

bd polyglot-pdf-oagt. This is a LEGAL invariant, not a correctness nicety: our
position is that we are not the preparer of any form, and the structural version
of that claim ("the tool cannot fill the preparer block") is far stronger than
the asserted one. USCIS I-90 Part 6 is the Interpreter's Certification and Part 7
the Preparer's Declaration -- both signed under penalty of perjury.

WHY THESE TESTS DRIVE THE REAL ROUTE AGAINST THE REAL KIT
---------------------------------------------------------
The obvious test -- assert that is_certification_field() returns True for some
ids -- would pass while the route wrote the fields anyway; it tests a predicate,
not a policy. So every test here calls the actual fill_pdf route with the actual
on-disk I-90 schema and reads the widget values back out of the returned PDF
bytes. The question asked is always "did a value land in the PDF?", never "did a
helper return True?".

The adversarial case matters most: `test_a_hostile_client_cannot_fill_the_
preparer_block` sends the certification fields the way a buggy or malicious
client would -- present in field_values AND present in a client-supplied schema
-- because the route builds its field map from the REQUEST BODY, never from the
kit's stored schema.json. The editor's `_ignored_fields` quarantine cannot
protect this invariant; only a server-side refusal can.

ASCII only.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import fitz  # PyMuPDF
import pytest

from backend.routes.pdf_fill_routes import PDFFillRequest, fill_pdf
from backend.services.certification_denylist import (
    _APPLICANT_FIELD_ALLOWLIST,
    is_certification_field,
)

_KIT_ROOT = Path(__file__).resolve().parents[2] / "form-kits" / "i-90"
_W7_SCHEMA = Path(__file__).resolve().parents[2] / "form-kits" / "w7" / "schema.json"

_KIT_PRESENT = (_KIT_ROOT / "form.pdf").exists()

# Real I-90 Part 6 / Part 7 fields, with the widget leaf each resolves to.
# Every one of these is LIVE and writable in the shipped schema -- the kit does
# NOT mark them ignored, which is precisely why the backend must refuse them.
_CERTIFICATION_TARGETS = [
    # (field_id, widget_suffix, value a client might send)
    ("p6_language", "P6_Language[0]", "Spanish"),
    ("p6_line1a_interpretersfamilyname", "P6_Line1a_InterpretersFamilyName[0]", "Doe"),
    ("p6_line6b_dateofsignature", "P6_Line6b_DateofSignature[0]", "01/01/2026"),
    ("p7_line1a_familyname", "P7_Line1a_FamilyName[0]", "Roe"),
    ("p7_line1b_preparersgivenname", "P7_Line1b_PreparersGivenName[0]", "Jane"),
    ("p7_line8b_dateofsignature", "P7_Line8b_DateofSignature[0]", "01/01/2026"),
]

# A certification field written through the OPTION path (radio), not the text
# path -- the two reach different write primitives, and a guard covering only
# one would leave the other open. p7_checkbox7 is the Preparer's Statement
# itself: the declaration of whether an attorney/accredited rep prepared the
# form.
_CERTIFICATION_RADIO_FIELD = "p7_checkbox7"
_CERTIFICATION_RADIO_WIDGET = "P7_checkbox7[0]"

# A control field: an ordinary applicant field on the SAME form, filled in the
# SAME request. Without it, a route that silently wrote nothing at all would pass
# every assertion below.
_CONTROL_FIELD_ID = "p1_line5a_familyname"
_CONTROL_WIDGET_SUFFIX = "P1_Line5a_FamilyName[0]"
_CONTROL_VALUE = "ApplicantSurname"


def _load_gold_schema() -> dict:
    return json.loads((_KIT_ROOT / "schema.json").read_text(encoding="utf-8"))


def _widget_value(pdf_bytes: bytes, suffix: str):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for pno in range(doc.page_count):
            for w in doc[pno].widgets() or []:
                if w.field_name and w.field_name.endswith(suffix):
                    return w.field_value
    finally:
        doc.close()
    return None


@pytest.mark.skipif(not _KIT_PRESENT, reason="i-90 kit not present")
@pytest.mark.parametrize("field_id,widget_suffix,value", _CERTIFICATION_TARGETS)
def test_certification_field_is_never_written(field_id, widget_suffix, value):
    """Each Part 6/7 field stays empty even though the request supplies a value.

    Parametrized over the WHOLE set rather than a sample: a mutation that
    reddens only one case says nothing about the others.
    """
    schema = _load_gold_schema()

    req = PDFFillRequest(
        kit_id="i-90",
        pdf_filename="form.pdf",
        field_values={field_id: value, _CONTROL_FIELD_ID: _CONTROL_VALUE},
        form_schema=schema,
    )
    resp = asyncio.run(fill_pdf(req))
    assert resp.status_code == 200

    # The control proves the route filled SOMETHING -- otherwise a route that
    # wrote nothing would satisfy the real assertion vacuously.
    assert _widget_value(resp.body, _CONTROL_WIDGET_SUFFIX) == _CONTROL_VALUE, (
        "the control applicant field did not fill -- this test would be vacuous"
    )

    written = _widget_value(resp.body, widget_suffix)
    assert not written, (
        f"{field_id} was written into the PDF as {written!r} -- the tool filled a "
        "certification block signed under penalty of perjury (bd polyglot-pdf-oagt)"
    )


@pytest.mark.skipif(not _KIT_PRESENT, reason="i-90 kit not present")
@pytest.mark.parametrize("field_id,widget_suffix,value", _CERTIFICATION_TARGETS)
def test_each_target_is_a_real_writable_field(field_id, widget_suffix, value):
    """Guard against a VACUOUS parametrization above.

    test_certification_field_is_never_written asserts a widget is EMPTY. That
    assertion also passes when the field id does not exist, when the widget
    suffix matches nothing, or when the value would never have been written for
    an unrelated reason -- it proves the denylist works only if the field would
    OTHERWISE have filled.

    This is not hypothetical: an earlier cut of this file listed
    'p7_line1a_preparersfamilyname', which is not in the schema at all. It
    passed with BOTH guards disabled, silently testing nothing, until this
    check was added.

    So: with the denylist bypassed at the predicate level, each target must
    actually land in the PDF.
    """
    schema = _load_gold_schema()

    assert any(f.get("id") == field_id for f in schema.get("fields", [])), (
        f"{field_id} is not a field in the shipped I-90 schema -- the "
        "corresponding refusal test is vacuous"
    )

    import backend.routes.pdf_fill_routes as routes

    original = routes.is_certification_field
    routes.is_certification_field = lambda *_a, **_k: False
    try:
        req = PDFFillRequest(
            kit_id="i-90",
            pdf_filename="form.pdf",
            field_values={field_id: value},
            form_schema=schema,
        )
        resp = asyncio.run(fill_pdf(req))
    finally:
        routes.is_certification_field = original

    assert resp.status_code == 200
    assert _widget_value(resp.body, widget_suffix) == value, (
        f"{field_id} did not fill even with the denylist bypassed, so the refusal "
        "test for it proves nothing"
    )


@pytest.mark.skipif(not _KIT_PRESENT, reason="i-90 kit not present")
def test_the_preparer_declaration_radio_is_never_selected():
    """The OPTION write path is guarded too, not just the text path.

    p7_checkbox7 is the Preparer's Statement radio. Radio options are written
    via their own pdf_field_name (and, for shared AcroForm fields, direct xref
    surgery) -- a different primitive from the text path every other test here
    exercises.
    """
    schema = _load_gold_schema()

    field = next(
        (f for f in schema.get("fields", []) if f.get("id") == _CERTIFICATION_RADIO_FIELD),
        None,
    )
    assert field is not None, "p7_checkbox7 missing from the shipped schema"
    options = field.get("options") or []
    assert options, "p7_checkbox7 has no options -- this test would be vacuous"

    req = PDFFillRequest(
        kit_id="i-90",
        pdf_filename="form.pdf",
        field_values={
            _CERTIFICATION_RADIO_FIELD: options[0].get("value"),
            _CONTROL_FIELD_ID: _CONTROL_VALUE,
        },
        form_schema=schema,
    )
    resp = asyncio.run(fill_pdf(req))
    assert resp.status_code == 200
    assert _widget_value(resp.body, _CONTROL_WIDGET_SUFFIX) == _CONTROL_VALUE

    selected = _widget_value(resp.body, _CERTIFICATION_RADIO_WIDGET)
    assert not selected or selected in {"Off", "/Off"}, (
        f"the Preparer's Statement radio was set to {selected!r} -- the tool "
        "asserted who prepared this form (bd polyglot-pdf-oagt)"
    )


@pytest.mark.skipif(not _KIT_PRESENT, reason="i-90 kit not present")
def test_a_hostile_client_cannot_fill_the_preparer_block():
    """The refusal does not depend on the client's cooperation.

    The route builds its field map from request.form_schema -- the CLIENT'S copy.
    So the threat model is a client that sends the certification fields anyway:
    stale bundle, buggy build, or hostile caller. Every Part 6/7 field is sent at
    once, in a schema that fully describes them, and none may land.
    """
    schema = _load_gold_schema()

    cert_values = {fid: val for fid, _suffix, val in _CERTIFICATION_TARGETS}
    cert_values[_CONTROL_FIELD_ID] = _CONTROL_VALUE

    req = PDFFillRequest(
        kit_id="i-90",
        pdf_filename="form.pdf",
        field_values=cert_values,
        form_schema=schema,
    )
    resp = asyncio.run(fill_pdf(req))
    assert resp.status_code == 200

    assert _widget_value(resp.body, _CONTROL_WIDGET_SUFFIX) == _CONTROL_VALUE

    leaked = [
        (fid, _widget_value(resp.body, suffix))
        for fid, suffix, _val in _CERTIFICATION_TARGETS
        if _widget_value(resp.body, suffix)
    ]
    assert not leaked, f"certification fields were written despite the denylist: {leaked}"


@pytest.mark.skipif(not _KIT_PRESENT, reason="i-90 kit not present")
def test_every_part_6_and_7_field_on_the_shipped_kit_is_refused():
    """Coverage is the WHOLE block, not the handful named above.

    Exit criterion 2 is "every deployed kit with such a block has it refused".
    A hand-picked list silently misses fields added by a future re-extraction, so
    this enumerates Parts 6 and 7 straight out of the shipped schema and requires
    the denylist to cover all of them -- including options' pdf_field_names, which
    the radio branch writes directly.
    """
    schema = _load_gold_schema()

    part_6_7 = [
        f for f in schema.get("fields", [])
        if str(f.get("id", "")).startswith(("p6_", "p7_"))
    ]
    assert len(part_6_7) >= 30, (
        f"expected the I-90's full interpreter/preparer block, found {len(part_6_7)} "
        "fields -- the schema shape changed and this test is no longer meaningful"
    )

    unprotected = [
        f.get("id") for f in part_6_7
        if not is_certification_field(f.get("id", ""), f.get("pdf_field_name"), "i-90")
    ]
    assert not unprotected, f"Part 6/7 fields NOT covered by the denylist: {unprotected}"

    # Options carry their own pdf_field_names and are written by the radio /
    # checkbox branches, so they need coverage too.
    unprotected_options = [
        (f.get("id"), opt.get("pdf_field_name"))
        for f in part_6_7
        for opt in (f.get("options") or [])
        if opt.get("pdf_field_name")
        and not is_certification_field("", opt.get("pdf_field_name"), "i-90")
    ]
    assert not unprotected_options, (
        f"Part 6/7 OPTION widgets not covered by the denylist: {unprotected_options}"
    )


def test_f1040_paid_preparer_block_is_refused():
    """The invariant is not I-90-specific: F1040's "Paid Preparer Use Only" too."""
    f1040 = Path(__file__).resolve().parents[2] / "form-kits" / "f1040" / "schema.json"
    if not f1040.exists():
        pytest.skip("f1040 kit not present")

    schema = json.loads(f1040.read_text(encoding="utf-8"))
    preparer_fields = [
        f for f in schema.get("fields", [])
        if "preparer" in str(f.get("id", "")).lower()
        or "firm" in str(f.get("id", "")).lower()
    ]
    assert preparer_fields, "expected F1040 to carry a paid-preparer block"

    unprotected = [
        f.get("id") for f in preparer_fields
        if not is_certification_field(f.get("id", ""), f.get("pdf_field_name"), "f1040")
    ]
    assert not unprotected, f"F1040 preparer fields not covered: {unprotected}"


def test_w7_acceptance_agent_block_is_refused():
    """The W-7's "Acceptance Agent's Use ONLY" block is a third-party attestation.

    An IRS Acceptance Agent signs the W-7 certifying they reviewed the
    applicant's ORIGINAL identity documents -- the same professional act as a
    preparer's declaration, and the block carries the agent's own PTIN and EIN.

    The first cut of this denylist matched NONE of it, on a deployed kit, and
    the false-positive test below asserted "nothing on the W-7 matches" -- which
    passed BECAUSE of the gap and would have blocked the fix. Caught by
    fresh-eyes round 1, which filled the block through the real route.
    """
    if not _W7_SCHEMA.exists():
        pytest.skip("w7 kit not present")

    schema = json.loads(_W7_SCHEMA.read_text(encoding="utf-8"))
    agent_section_ids = {
        s.get("id") for s in schema.get("sections", [])
        if "agent" in str(s.get("id", "")).lower()
        or "agent" in str(s.get("label", "")).lower()
    }
    assert agent_section_ids, "expected the W-7 to carry an acceptance-agent section"

    block = [
        f for f in schema.get("fields", [])
        if f.get("section_id") in agent_section_ids
        or str(f.get("id", "")).lower().startswith(("agent_", "name_of_delegate", "delegate_"))
    ]
    assert len(block) >= 7, (
        f"expected the full acceptance-agent block, found {len(block)} fields -- "
        "the schema changed and this test is no longer meaningful"
    )

    unprotected = [
        f.get("id") for f in block
        if not is_certification_field(f.get("id", ""), f.get("pdf_field_name"), "w7")
    ]
    assert not unprotected, (
        f"W-7 acceptance-agent fields NOT covered by the denylist: {unprotected}"
    )


def test_applicant_fields_still_fill_and_are_never_refused():
    """The denylist must not become a blanket refusal (false-positive guard).

    Scoped to the APPLICANT'S OWN fields: the W-7 does carry a third-party
    block (the acceptance agent, above), so a bare "nothing on this form
    matches" assertion would pin that gap as correct -- and did, until
    fresh-eyes round 1. This asserts the complement: everything OUTSIDE the
    agent block must still fill.

    A denylist that fails closed on ordinary applicant fields breaks the product
    while looking like caution, so this direction needs a guard too.
    """
    if not _W7_SCHEMA.exists():
        pytest.skip("w7 kit not present")

    schema = json.loads(_W7_SCHEMA.read_text(encoding="utf-8"))
    agent_section_ids = {
        s.get("id") for s in schema.get("sections", [])
        if "agent" in str(s.get("id", "")).lower()
        or "agent" in str(s.get("label", "")).lower()
    }

    applicant_fields = [
        f for f in schema.get("fields", [])
        if f.get("section_id") not in agent_section_ids
        and not str(f.get("id", "")).lower().startswith(("agent_", "name_of_delegate", "delegate_"))
    ]
    assert len(applicant_fields) >= 20, "expected a substantial applicant-field set"

    matched = [
        f.get("id") for f in applicant_fields
        if is_certification_field(f.get("id", ""), f.get("pdf_field_name"), "w7")
    ]
    assert not matched, (
        f"the denylist falsely refuses the applicant's OWN W-7 fields: {matched}"
    )


@pytest.mark.parametrize(
    "field_id",
    [
        # An applicant's own documents are full of the word "certificate".
        # Refusing these would break ordinary form-filling on the next
        # immigration kit (N-400 asks for the applicant's own naturalization
        # certificate; I-130 for a marriage certificate).
        "birth_certificate_number",
        "certificate_of_naturalization_number",
        "marriage_certificate_date",
        "police_certificate",
        "fld_id_doc_certified_copy",
    ],
)
def test_applicant_certificate_fields_are_not_refused(field_id):
    """"certificate" is the applicant's DOCUMENT; "certification" is the ACT.

    The first cut used a bare r"certif" prefix, which would have refused every
    field in this list on kits we have not authored yet (fresh-eyes round 1).
    """
    assert not is_certification_field(field_id), (
        f"{field_id} is an applicant's own document reference, not a third-party "
        "attestation -- refusing it would silently blank a legitimate answer"
    )


@pytest.mark.skipif(not _KIT_PRESENT, reason="i-90 kit not present")
def test_each_guard_layer_refuses_on_its_own():
    """BOTH layers must independently refuse -- neither may rely on the other.

    The route guards certification fields twice: once in the dispatch loop (by
    schema field id) and once in fill_widget (by the name on the REAL widget in
    the PDF). The redundancy is deliberate -- a perjury attestation is worth two
    guards -- but redundancy hides regressions: with both live, disabling either
    one leaves every other test in this file green, so neither is actually
    pinned by them.

    This test disables each layer in turn and requires the survivor to hold the
    line alone. Without it, a refactor could delete the loop check and the suite
    would stay green until the day fill_widget was also touched.
    """
    schema = _load_gold_schema()
    field_id, widget_suffix, value = _CERTIFICATION_TARGETS[0]

    import backend.routes.pdf_fill_routes as routes

    def _fill_with(predicate):
        original = routes.is_certification_field
        routes.is_certification_field = predicate
        try:
            req = PDFFillRequest(
                kit_id="i-90",
                pdf_filename="form.pdf",
                field_values={field_id: value, _CONTROL_FIELD_ID: _CONTROL_VALUE},
                form_schema=schema,
            )
            return asyncio.run(fill_pdf(req))
        finally:
            routes.is_certification_field = original

    # LOOP LAYER ALONE: the widget-name check cannot fire, because it passes
    # field_id="" and only the PDF's own field_name. Answering False whenever
    # the field_id is empty disables the fill_widget layer specifically.
    loop_only = _fill_with(
        lambda fid, pfn=None, kit=None: bool(fid) and is_certification_field(fid, pfn, kit)
    )
    assert loop_only.status_code == 200
    assert _widget_value(loop_only.body, _CONTROL_WIDGET_SUFFIX) == _CONTROL_VALUE
    assert not _widget_value(loop_only.body, widget_suffix), (
        "with only the dispatch-loop guard active, a certification field was "
        "written -- the loop guard does not hold the line on its own"
    )

    # WIDGET LAYER ALONE: answering False whenever a field_id IS supplied
    # disables the dispatch-loop check, leaving only the real-widget-name guard.
    widget_only = _fill_with(
        lambda fid, pfn=None, kit=None: not fid and is_certification_field(fid, pfn, kit)
    )
    assert widget_only.status_code == 200
    assert _widget_value(widget_only.body, _CONTROL_WIDGET_SUFFIX) == _CONTROL_VALUE
    assert not _widget_value(widget_only.body, widget_suffix), (
        "with only the widget-name guard active, a certification field was "
        "written -- the second layer does not hold the line on its own"
    )


def _make_shared_radio_pdf(field_name: str) -> bytes:
    """A PDF with ONE true-AcroForm radio whose kids differ only by on-state.

    This is the schema-v2 "shared_pdf_field" shape (bd h76m.17): the field-level
    pdf_field_name names one radio field, and each option carries a pdf_on_value
    instead of its own pdf_field_name. No shipped kit uses this shape for a
    certification field, so without a synthetic fixture the guard on that write
    path never executes.

    Built the same way as test_pdf_fill_v2_group_types.py's fixture -- add plain
    checkbox widgets, then rewrite /T and /AP via xref so they become kids of one
    shared field. PyMuPDF cannot author that shape directly.
    """
    doc = fitz.open()
    page = doc.new_page()
    for idx in range(2):
        w = fitz.Widget()
        w.field_name = f"tmp_cert_{idx}[0]"
        w.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
        w.rect = fitz.Rect(50, 50 + idx * 40, 70, 70 + idx * 40)
        page.add_widget(w)
    xrefs = [w.xref for w in doc[0].widgets() or []]
    assert len(xrefs) == 2, "synthetic radio kids not created"
    for xref, state in zip(xrefs, ("Yes", "No")):
        doc.xref_set_key(xref, "T", f"({field_name})")
        doc.xref_set_key(xref, "AP", f"<< /N << /{state} null /Off null >> >>")
    data = doc.tobytes()
    doc.close()
    return data


def test_the_shared_radio_xref_path_refuses_certification_widgets(monkeypatch):
    """The THIRD guard (direct xref surgery) is exercised, not merely present.

    The shared-field radio branch writes /V and /AS straight onto the kid
    annotation and never calls fill_widget, so it needs its own check. No
    shipped kit puts a certification field on that path, which means deleting
    the guard left all 19 other tests green (fresh-eyes round 1).

    Two things are needed to reach it: a synthetic kit in the v2 shared-radio
    shape, AND suppression of the dispatch-loop guard -- which fires first on
    field_id and `continue`s, so layer 3 is unreachable while layer 1 is live.
    That is the same per-layer isolation
    test_each_guard_layer_refuses_on_its_own does, extended to the third layer:
    the predicate answers False when given a field_id, leaving only the
    widget-name calls active.
    """
    import backend.routes.pdf_fill_routes as routes

    pdf_field = "P7_SharedPreparerDeclaration[0]"
    pdf_bytes = _make_shared_radio_pdf(pdf_field)

    class _Store:
        async def load_pdf_bytes(self, kit_id, pdf_filename):
            return pdf_bytes

    monkeypatch.setattr(routes, "get_form_kit_store", lambda: _Store())

    schema = {
        "fields": [
            {
                "id": "p7_shared_declaration",
                "type": "radio",
                "pdf_field_name": pdf_field,
                "options": [
                    {"value": "yes", "label": "Yes", "pdf_on_value": "Yes"},
                    {"value": "no", "label": "No", "pdf_on_value": "No"},
                ],
            }
        ]
    }

    # Suppress ONLY the dispatch-loop layer (the one that passes a field_id),
    # leaving the widget-name guards -- including the shared-radio xref one --
    # to hold the line alone.
    original = routes.is_certification_field
    routes.is_certification_field = (
        lambda fid, pfn=None, kit=None: not fid and is_certification_field(fid, pfn, kit)
    )
    try:
        req = PDFFillRequest(
            kit_id="synthetic",
            pdf_filename="shared_radio.pdf",
            field_values={"p7_shared_declaration": "yes"},
            form_schema=schema,
        )
        resp = asyncio.run(fill_pdf(req))
    finally:
        routes.is_certification_field = original
    assert resp.status_code == 200

    out = fitz.open(stream=resp.body, filetype="pdf")
    try:
        selected = [
            w.field_value for p in out for w in (p.widgets() or [])
            if w.field_name == pdf_field and w.field_value not in (None, "", "Off", "/Off")
        ]
    finally:
        out.close()
    assert not selected, (
        f"the shared-field radio path selected a certification state {selected!r} -- "
        "the direct-xref guard did not fire (bd polyglot-pdf-oagt)"
    )


def test_a_certification_widget_is_never_UNLOCKED():
    """Clearing the read-only bit is itself a write we must not make.

    apply_field_flag_changes unlocks read-only widgets so they can be filled
    (bd 7a9.16), and several call sites run it BEFORE the value-write guard, so
    a certification widget could be left permanently EDITABLE in the emitted
    PDF even though its value write was refused (fresh-eyes round 1).

    NOT reachable end-to-end today, and the honest reason matters: every I-90
    certification signature has `conditional_logic: null`, so the unlock returns
    early on its own, and the dispatch-loop guard `continue`s before this code
    runs anyway. An earlier cut of this test drove the real route and asserted
    the read-only bit survived -- which it did, for those two unrelated reasons.
    It passed with the guard DELETED, describing the status quo rather than
    specifying the rule.

    So this tests the guard directly instead: a field object that DOES carry an
    unlock descriptor, the shape a future kit could author, must not unlock a
    certification widget.
    """
    if not _KIT_PRESENT:
        pytest.skip("i-90 kit not present")

    import backend.routes.pdf_fill_routes as routes

    schema = _load_gold_schema()

    # RECORD every call the route makes, so we can prove the unlock guard
    # actually CONSULTS the predicate rather than merely existing. Round 2
    # deleted this guard and all 27 tests stayed green, because the previous
    # version of this test only asserted what the predicate RETURNS -- never
    # that apply_field_flag_changes calls it. The per-layer harness cannot
    # isolate this one either: it splits layers on bool(field_id), and this
    # guard passes a real field id, so it is live in one arm and dead in the
    # other with no arm testing it alone.
    calls = []
    original = routes.is_certification_field

    def _recording(fid, pfn=None, kit=None):
        calls.append((fid, pfn, kit))
        return original(fid, pfn, kit)

    routes.is_certification_field = _recording
    try:
        req = PDFFillRequest(
            kit_id="i-90",
            pdf_filename="form.pdf",
            field_values={_CONTROL_FIELD_ID: _CONTROL_VALUE},
            form_schema=schema,
        )
        resp = asyncio.run(fill_pdf(req))
    finally:
        routes.is_certification_field = original

    assert resp.status_code == 200

    # Distinguishing the unlock guard from the dispatch loop: BOTH pass a
    # non-empty field_id, but the loop passes the SCHEMA's pdf_field_name while
    # the unlock guard passes the name read off the REAL widget in the PDF.
    # Those differ whenever the schema stores a leaf and the PDF a
    # fully-qualified name -- so compare against the schema's own value rather
    # than looking for a marker string.
    #
    # An earlier cut matched on '#subform' appearing in the widget name, which
    # is true of the I-90 (an XFA form) and FALSE of w7 and f1040, whose widgets
    # are named topmostSubform[0].Page1[0].f1_44[0]. That discriminator would
    # have gone vacuous the moment this test was retargeted at another kit --
    # vacuous in the direction that hides a deleted guard (fresh-eyes round 3).
    #
    # The cut before THAT matched "non-empty id + any widget name", which the
    # dispatch loop also satisfies, so it passed with the guard deleted.
    schema_pdf_name = next(
        (f.get("pdf_field_name") for f in schema.get("fields", [])
         if f.get("id") == _CONTROL_FIELD_ID),
        None,
    )
    unlock_calls = [
        c for c in calls
        if c[0] == _CONTROL_FIELD_ID and c[1] and c[1] != schema_pdf_name
    ]
    assert unlock_calls, (
        "apply_field_flag_changes never consulted is_certification_field -- the "
        "unlock guard is absent or unreachable, so a certification widget could "
        "be left permanently editable in the emitted PDF (bd polyglot-pdf-oagt)"
    )

    # The ordinary applicant unlock must still work: the guard sits inside the
    # read-only unlock feature (bd 7a9.16) and must not break it.
    doc = fitz.open(stream=resp.body, filetype="pdf")
    try:
        readonly = next(
            (
                bool(w.field_flags & 1)
                for p in doc
                for w in (p.widgets() or [])
                if w.field_name and w.field_name.endswith(_CONTROL_WIDGET_SUFFIX)
            ),
            None,
        )
    finally:
        doc.close()
    assert readonly is False, (
        "the applicant control field did NOT unlock -- the certification guard "
        "broke the read-only unlock feature (bd 7a9.16)"
    )

    # And the decision it makes must be right in both directions.
    assert routes.is_certification_field(
        "p6_line6a_signature", "P6_Line6a_Signature[0]", "i-90"
    ), "a certification signature must be refused an unlock"
    assert not routes.is_certification_field(
        _CONTROL_FIELD_ID, _CONTROL_WIDGET_SUFFIX, "i-90"
    ), "an ordinary applicant field must still unlock (bd 7a9.16 must keep working)"


@pytest.mark.parametrize(
    "pattern_source,example_id",
    [
        # TIER 1 -- global roles. Each entry names the pattern's own reason for
        # existing, so deleting that pattern reddens exactly one case.
        ("interpreter", "interpreters_family_name"),
        ("preparer", "preparer_signature"),
        ("ptin", "fld_ptin_number"),
        ("attorney", "attorney_state_bar_number"),
        ("accredited[_\\-]?rep", "accredited_representative_name"),
        ("g28[_\\-]", "fld_g28_signature"),
        ("notary", "notary_public_signature"),
        ("civil[_\\-]?surgeon", "civil_surgeon_name"),
        # "acceptanceagent" with no separator: the tier-2 w7 rule is
        # "agent[_\\-]", which needs a separator AFTER "agent", so it cannot
        # catch this -- leaving the global pattern as the only match. With
        # "acceptance_agent_office" the w7 rule caught it and this pattern was
        # unpinned (found by my own deletion sweep, post round 3).
        ("acceptance[_\\-]?agent", "acceptanceagentblock"),
        ("certification", "certification_block_signature"),
        ("certifies", "who_certifies_this"),
        ("certifying", "certifying_official_name"),
        ("attest", "attestation_signature"),
        ("under[_\\-]?penalty", "signed_under_penalty_of_perjury"),
        # Third-party roles added in round 3. Each id below is chosen so ONLY
        # its own pattern matches -- e.g. NOT "translator_certification_name",
        # which "certification" would also catch.
        ("translator", "translator_family_name"),
        ("translated[_\\-]?by", "translated_by_whom"),
        ("\\bwitness", "witness_signature_date"),
        ("affiant", "affiant_printed_name"),
        ("deponent", "deponent_address"),
        ("commission[_\\-]?expires", "my_commission_expires"),
        ("subscribed[_\\-]?and[_\\-]?sworn", "subscribed_and_sworn_before_me"),
        ("guardian[_\\-]?ad[_\\-]?litem", "guardian_ad_litem_name"),
        ("panel[_\\-]?physician", "panel_physician_license"),
        ("authorized[_\\-]?rep", "authorized_representative_phone"),
        ("joint[_\\-]?sponsor", "joint_sponsor_income"),
        ("household[_\\-]?member", "household_member_relationship"),
    ],
)
def test_every_global_pattern_is_pinned(pattern_source, example_id):
    """Each pattern must be the ONLY thing catching at least one id.

    Round 2 measured that 9 of 16 patterns could be deleted individually with
    the whole suite still green -- including r"ptin\\b", the pattern round 1 was
    fixed FOR. An unpinned pattern is either dead (as ptin was, silently, while
    its comment claimed otherwise) or redundant, and both round-1 escapes lived
    in exactly that blind spot.

    So every global pattern gets an id that only IT matches. Delete the pattern,
    and this test names it.
    """
    assert is_certification_field(example_id), (
        f"{example_id!r} is not refused -- the {pattern_source!r} pattern is dead "
        "or was removed"
    )


@pytest.mark.parametrize(
    "kit_id,example_id,other_kit",
    [
        # TIER 2 -- kit-scoped. Each must fire on ITS kit and NOT on another,
        # which is the whole reason the tier exists: on the N-400, Part 6 is the
        # applicant's employment history and Part 7 their travel history.
        # Each id carries NO global role word, so ONLY the kit-scoped tier can
        # refuse it -- which is what makes these real pins. (An id like
        # fld_preparer_self_employed would be caught by the global "preparer"
        # regardless, pinning nothing: fresh-eyes round 3, finding 2.)
        ("i-90", "p6_line3c_citytown", "n-400"),
        ("i-90", "p7_line1a_familyname", "n-400"),
        ("f1040", "fld_firm_ein", "n-400"),
        ("f1040", "is_self_employed_box", "n-400"),
        ("w7", "agent_office_code", "n-400"),
        ("w7", "name_of_delegate", "n-400"),
    ],
)
def test_kit_scoped_patterns_fire_only_on_their_kit(kit_id, example_id, other_kit):
    """A form-specific rule must not leak onto another form.

    The failure this prevents is silent and client-facing: `\\bp6[_-]` protects
    the I-90's Interpreter's Certification, but applied globally it would blank
    a client's spoken answers about their employer and schools on the N-400
    (fresh-eyes round 2).
    """
    assert is_certification_field(example_id, None, kit_id), (
        f"{example_id!r} must be refused on kit {kit_id!r}"
    )
    # Whether the SAME id is refused on another kit is tested separately, by the
    # N-400 cases below -- several of these ids also carry a global role word
    # ("interpretersfamilyname" contains "interpreter"), so asserting a blanket
    # False here would be wrong. The ids that carry NO role word --
    # p7_line1a_familyname, fld_firm_ein, agent_office_code -- are the ones the
    # kit scoping actually decides, and they are covered below.


@pytest.mark.parametrize(
    "n400_applicant_field",
    [
        # On the N-400, Part 6 is "Information About Your Employment and
        # Schools" and Part 7 is "Time Outside the United States" -- the
        # APPLICANT'S OWN answers. A global p6_/p7_ prefix would silently blank
        # every one of these after the client spoke and confirmed them.
        "p6_line1_employer_name",
        "p6_school_name",
        "p7_line1_country_visited",
        "p7_total_days_outside_us",
        # Words that are a professional block on ONE form and an ordinary
        # applicant answer on another.
        "are_you_self_employed",          # N-400 asks the applicant directly
        "self_employed_income",           # 1040 Schedule SE
        "declaration_of_intent_number",   # the applicant's own Declaration
        "agent_orange_exposure",          # VA / medical history
        "travel_agent_name",
        "real_estate_agent_income",
        # Role-word-free ids that the KIT SCOPING alone decides. These are the
        # sharpest cases: identical in shape to real I-90 / F1040 / W-7
        # certification fields, but on a kit with no scoped rules they must
        # fill. If kit scoping regressed to a global list, only these would
        # catch it.
        "p7_line1a_familyname",
        "p6_line3c_citytown",
        "fld_firm_ein",
        "agent_office_code",
    ],
)
def test_applicant_fields_are_not_refused_once_their_kit_is_REGISTERED(
    n400_applicant_field,
):
    """The false-positive direction -- for a kit we have registered.

    Every id here returned True before the two-tier split (fresh-eyes round 2):
    refusing them would silently blank answers the client already gave aloud.

    The kit must be REGISTERED for this to hold, and that is the deliberate
    shape of the design. An UNRECOGNIZED kit_id applies every kit's rules, so
    these would be over-refused there -- see
    test_an_unrecognized_kit_fails_SAFE. That direction is correct for a legal
    invariant: an over-refusal leaves a blank a human completes; an
    under-refusal fills a perjury attestation. Registering the kit (which means
    someone read the form) buys the precision back.

    'n-400' is registered here with NO patterns, standing in for a real future
    kit entry -- these ids are then decided by the global role tier alone.
    """
    import backend.services.certification_denylist as denylist

    original = dict(denylist._KIT_SCOPED_RE)
    denylist._KIT_SCOPED_RE[denylist._normalize_kit_id("n-400")] = re.compile(
        r"(?!x)x"  # matches nothing: an N-400 has no third-party block of its own
    )
    try:
        refused = is_certification_field(n400_applicant_field, None, "n-400")
    finally:
        denylist._KIT_SCOPED_RE.clear()
        denylist._KIT_SCOPED_RE.update(original)

    assert not refused, (
        f"{n400_applicant_field!r} is the applicant's OWN answer -- refusing it "
        "would silently blank a value the client spoke and confirmed"
    )


@pytest.mark.parametrize(
    "kit_id_variant",
    [
        # The spellings kit onboarding actually produces. _derive_kit_id builds
        # ids from PDF filenames, so the standard "Form I-90.pdf" download
        # becomes "form-i-90".
        "i-90", "I-90", "i90", "form-i-90", "  I-90  ", "Form-I-90",
        # And the ones nobody anticipated.
        "totally-unknown-kit", "", None,
    ],
)
def test_an_unrecognized_kit_fails_SAFE(kit_id_variant):
    """A kit_id we do not recognize must apply MORE rules, never fewer.

    kit_id arrives in the same untrusted request body as everything else. The
    first cut of the two-tier design looked it up by exact match, so
    kit_id="I-90" instead of "i-90" silently dropped 27 of the I-90's 37
    protections -- no error, no log line -- and the reviewer wrote a preparer's
    family name into a real I-90 through the real route with it (fresh-eyes
    round 3).

    p7_line1a_familyname is the sharpest probe: it is a genuine I-90 Preparer's
    Declaration field carrying NO global role word, so ONLY the kit-scoped tier
    can refuse it.
    """
    assert is_certification_field("p7_line1a_familyname", None, kit_id_variant), (
        f"kit_id={kit_id_variant!r} left the I-90 Preparer's Declaration writable. "
        "An unrecognized kit must fall back to ALL kits' rules, not none."
    )


@pytest.mark.parametrize(
    "kit_id,schema_name,expected",
    [("i-90", "i-90", 37), ("f1040", "f1040", 7), ("w7", "w7", 9)],
)
def test_the_documented_match_counts_are_accurate(kit_id, schema_name, expected):
    """The counts in certification_denylist.py's comment must stay true.

    That comment is load-bearing: it is the stated justification for the
    allowlist being empty, and test_the_allowlist_stays_empty_or_justified
    points readers at it. It said "ZERO W-7" for two rounds -- true only while
    the acceptance-agent block was unprotected, and it survived the fix. A
    future author reading it would conclude the W-7 has no third-party block and
    could delete the agent patterns, reopening the exact hole round 1 found
    (fresh-eyes round 2, finding 5).

    An exact count, not a floor: a DROP means coverage regressed, and a RISE
    means the denylist started matching something new, which deserves a look
    either way.
    """
    path = Path(__file__).resolve().parents[2] / "form-kits" / schema_name / "schema.json"
    if not path.exists():
        pytest.skip(f"{schema_name} kit not present")

    schema = json.loads(path.read_text(encoding="utf-8"))
    matched = sum(
        1 for f in schema.get("fields", [])
        if is_certification_field(f.get("id", ""), f.get("pdf_field_name"), kit_id)
    )
    assert matched == expected, (
        f"{kit_id} now matches {matched} fields, not the documented {expected}. "
        "Update the count in backend/services/certification_denylist.py AND here, "
        "after confirming the change is intended -- a drop means coverage regressed."
    )


def test_the_allowlist_stays_empty_or_justified():
    """Every allowlist entry is a hole in a legal invariant.

    The allowlist is empty today, measured against all three shipped kits. This
    test does not forbid adding to it -- it forces the addition to be deliberate,
    so nobody widens the hole to make a failing test pass without deciding to.
    """
    assert _APPLICANT_FIELD_ALLOWLIST == frozenset(), (
        "the certification allowlist gained an entry. That is a deliberate hole in "
        "a legal invariant (bd polyglot-pdf-oagt): confirm the field is an "
        "APPLICANT's own answer and not a third party's attestation, document why "
        "in certification_denylist.py, then update this test's expected set."
    )
