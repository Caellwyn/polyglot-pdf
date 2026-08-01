"""W-7 / W-7(SP) field-to-widget mapping regression pin (bd polyglot-pdf-ivh9).

The shipped w7 kit (and its since-deleted w7-2 copy, bd r9a7) had a one-widget off-by-one through the treaty /
name / address / birth / id-document run: e.g. name_1a_first pointed at f1_06
(the treaty-article box) instead of f1_07 (1a First name). The consequence was
a user-visible mis-fill of the printed W-7 -- every value landed one box off
through that region.

These tests pin the CORRECTED mapping against ground truth. The expected
field_id -> widget-leaf table was verified against the AcroForm widget rects and
a render of the filled page (each test value landed in its printed cell). If the
extraction / a re-derivation ever re-scrambles the mapping, these fail.

The table tracks the maintainer's hand-verified gold schema (bd
polyglot-pdf-fjxe), which re-ran extraction and gave several fields longer,
more descriptive ids (dob -> date_of_birth, visa_type ->
us_visa_type_number_expiration, ...). Only the IDS moved: every widget in the
off-by-one run still carries the same semantic field, which is what this pin
exists to defend.

Pure data assertions on the committed schema.json -- no PDF render, no paid API.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]


def _load(kit: str) -> dict:
    path = _REPO / "form-kits" / kit / "schema.json"
    if not path.exists():
        pytest.skip(f"{kit} kit not present")
    return json.loads(path.read_text(encoding="utf-8"))


def _leaf(pfn: str | None) -> str | None:
    return pfn.split(".")[-1] if pfn else None


# Correct field_id -> widget leaf, verified against the AcroForm rects + a
# filled-page render. Covers the full off-by-one run. (Kept per-kit-shaped
# for a future second W-7 edition; the retired w7-2 copy's table was removed
# with the kit, bd polyglot-pdf-r9a7.)
_EXPECTED = {
    "w7": {
        "treaty_country": "f1_05[0]",
        "treaty_article_number": "f1_06[0]",
        "name_1a_first": "f1_07[0]",
        "name_1a_middle": "f1_08[0]",
        "name_1a_last": "f1_09[0]",
        "name_1b_first": "f1_10[0]",
        "name_1b_middle": "f1_11[0]",
        "name_1b_last": "f1_12[0]",
        "mailing_street": "f1_13[0]",
        "mailing_city_state_country": "f1_14[0]",
        "foreign_street": "f1_15[0]",
        "foreign_city_state_country": "f1_16[0]",
        "date_of_birth": "f1_17[0]",
        "country_of_birth": "f1_18[0]",
        "city_state_of_birth": "f1_19[0]",
        "countries_of_citizenship": "f1_20[0]",
        "foreign_tax_id_number": "f1_21[0]",
        "us_visa_type_number_expiration": "f1_22[0]",
        "id_document_issued_by": "f1_24[0]",
        "id_document_number": "f1_25[0]",
        "id_document_expiration_date": "f1_26[0]",
        "date_of_entry_us": "f1_27[0]",
        # Beyond the original ivh9 run. Pinned for the same reason the name
        # table covers every field: `name` and `pdf_field_name` shift
        # INDEPENDENTLY, so a re-extraction that permuted bindings inside the
        # agent block would keep every name correct and pass the whole file.
        # The digit-group and agent runs are adjacent same-shaped widgets --
        # exactly where a swap stays plausible-looking.
        "relationship_to_us_person": "f1_01[0]",
        "us_person_name_ssn_itin": "f1_03[0]",
        "reason_h_details": "f1_04[0]",
        "id_document_other_detail": "f1_23[0]",
        "itin_part1": "f1_28[0]",
        "itin_part2": "f1_29[0]",
        "itin_part3": "f1_30[0]",
        "irsn_part1": "f1_31[0]",
        "irsn_part2": "f1_32[0]",
        "irsn_part3": "f1_33[0]",
        "itin_issued_first_name": "f1_34[0]",
        "itin_issued_middle_name": "f1_35[0]",
        "itin_issued_last_name": "f1_36[0]",
        "college_or_company_name": "f1_37[0]",
        "college_city_and_state": "f1_38[0]",
        "length_of_stay": "f1_39[0]",
        "phone_number": "f1_40[0]",
        "name_of_delegate": "f1_41[0]",
        "delegate_name": "f1_42[0]",
        "agent_fax": "f1_43[0]",
        "agent_name_and_title": "f1_44[0]",
        "agent_company_name": "f1_45[0]",
        "agent_ein": "f1_46[0]",
        "agent_ptin": "f1_47[0]",
        "agent_office_code": "f1_48[0]",
    },
}

# The two "Other" free-text lines (box-h "Other" reason line f1_04; 6d "Other"
# ID-document line f1_23) are real fillable widgets. Before the ivh9 fix they
# were MIS-claimed by treaty_country / id_number, masking the off-by-one; the
# fix parked them unclaimed and left modeling them to a follow-up. The
# maintainer's hand-verified gold pass (bd polyglot-pdf-fjxe) did that
# modeling, so each is now claimed by its OWN dedicated field.
#
# What still matters here is the ANTI-REGRESSION half: neither line may be
# claimed by a field belonging to the off-by-one run above. Pinning the exact
# owner keeps that guarantee -- a re-scramble that walks treaty_country or
# id_document_number back onto these widgets still fails.
_OTHER_LINE_OWNERS = {
    "f1_04[0]": "reason_h_details",
    "f1_23[0]": "id_document_other_detail",
}


@pytest.mark.parametrize("kit", ["w7"])
def test_field_widget_mapping_is_corrected(kit: str) -> None:
    schema = _load(kit)
    by_id = {f["id"]: f for f in schema["fields"]}
    for fid, want_leaf in _EXPECTED[kit].items():
        assert fid in by_id, f"{kit}: field {fid} missing (consolidation regressed?)"
        got = _leaf(by_id[fid].get("pdf_field_name"))
        assert got == want_leaf, (
            f"{kit}: {fid} maps to {got}, expected {want_leaf} "
            f"(field-to-widget off-by-one regressed -- see bd polyglot-pdf-ivh9)"
        )


@pytest.mark.parametrize("kit", ["w7"])
def test_other_lines_keep_their_own_field(kit: str) -> None:
    schema = _load(kit)
    # Collect ALL claimants per widget, not last-write-wins: a dict assignment
    # would hide a second field landing on the same leaf behind whichever came
    # later in the list, and hiding a duplicate claim is exactly the failure
    # this guard exists to catch.
    owners_by_leaf: dict[str, list[str]] = {}
    for f in schema["fields"]:
        leaf = _leaf(f.get("pdf_field_name"))
        if leaf:
            owners_by_leaf.setdefault(leaf, []).append(f["id"])

    for leaf, want_owner in _OTHER_LINE_OWNERS.items():
        got = owners_by_leaf.get(leaf, [])
        assert got == [want_owner], (
            f"{kit}: widget {leaf} is claimed by {got!r}, expected exactly its "
            f"own dedicated 'Other' free-text field [{want_owner!r}]. A field "
            f"from the treaty/name/address/id run landing here reintroduces the "
            f"off-by-one (bd polyglot-pdf-ivh9)"
        )


# The human-facing 'name' for every widget the ivh9-era off-by-one touched,
# plus the signature/agent block that the hand-verified gold pass re-mapped.
# Each string is the caption actually PRINTED above/left of that widget's rect
# in form.pdf (read out of the page text with PyMuPDF, then matched to the
# widget by rect).
#
# WHY this table exists (bd polyglot-pdf-fjxe, Opus outer review): the id ->
# pdf_field_name pin above only defends the mapping. The gold pass shipped a
# SECOND off-by-one one key over -- ids and spoken_names were geometrically
# right, but 'name' lagged by one widget through this run, so phone_number read
# "Date (month / day / year) of applicant signature". That is not cosmetic:
# ai_context.py renders 'name' into the Gemini system instruction, and the
# frontend field components render it as the visible <label>. The full suite was
# green because nothing asserted on 'name'. This closes that hole.
#
# COVERS EVERY f1_* text field, not just the run that was found broken. Pinning
# only the known-bad fields would leave the same hole open exactly where the
# next off-by-one is most likely to hide: runs of adjacent, same-shaped widgets
# (name_1a_*, name_1b_*, itin_part*, irsn_part*, itin_issued_*) where a shift
# still produces plausible-looking text.
_EXPECTED_NAME = {
    "w7": {
        "relationship_to_us_person":
            "If d, enter relationship to U.S. citizen/resident alien",
        "us_person_name_ssn_itin":
            "If d or e, enter name and SSN/ITIN of U.S. citizen/resident alien",
        "reason_h_details": "If h, other reason (see instructions)",
        "treaty_country":
            "Additional information for a and f: Enter treaty country",
        "treaty_article_number": "Treaty article number",
        "name_1a_first": "1a First name",
        "name_1a_middle": "1a Middle name",
        "name_1a_last": "1a Last name",
        "name_1b_first": "1b Name at birth if different -- First name",
        "name_1b_middle": "1b Name at birth if different -- Middle name",
        "name_1b_last": "1b Name at birth if different -- Last name",
        "mailing_street":
            "2 Street address, apartment number, or rural route number. If you "
            "have a P.O. box, see separate instructions.",
        "mailing_city_state_country":
            "2 City or town, state or province, and country. Include ZIP code "
            "or postal code where appropriate.",
        "foreign_street":
            "3 Foreign (non-U.S.) address -- Street address, apartment number, "
            "or rural route number. Don't use a P.O. box number.",
        "foreign_city_state_country":
            "3 Foreign (non-U.S.) address -- City or town, state or province, "
            "and country. Include postal code where appropriate.",
        "date_of_birth": "4 Date of birth (month / day / year)",
        "country_of_birth": "4 Country of birth",
        "city_state_of_birth":
            "4 City and state or province of birth (optional)",
        "countries_of_citizenship": "6a Country(ies) of citizenship",
        "foreign_tax_id_number": "6b Foreign tax I.D. number (if any)",
        "us_visa_type_number_expiration":
            "6c Type of U.S. visa (if any), number, and expiration date",
        "id_document_other_detail":
            "6d Other identification document (specify)",
        "id_document_issued_by": "6d Issued by",
        "id_document_number": "6d Number",
        "id_document_expiration_date": "6d Exp. date",
        "date_of_entry_us":
            "6d Date of entry into the United States (MM/DD/YYYY)",
        "itin_part1": "6f ITIN -- first three digits",
        "itin_part2": "6f ITIN -- middle two digits",
        "itin_part3": "6f ITIN -- last four digits",
        "irsn_part1": "6f IRSN -- first three digits",
        "irsn_part2": "6f IRSN -- middle two digits",
        "irsn_part3": "6f IRSN -- last four digits",
        "itin_issued_first_name":
            "6f Name under which ITIN/IRSN was issued -- First name",
        "itin_issued_middle_name":
            "6f Name under which ITIN/IRSN was issued -- Middle name",
        "itin_issued_last_name":
            "6f Name under which ITIN/IRSN was issued -- Last name",
        "college_or_company_name": "6g Name of college/university or company",
        "college_city_and_state": "6g City and state",
        "length_of_stay": "6g Length of stay",
        "phone_number": "Applicant phone number",
        "name_of_delegate":
            "Name of delegate, if applicable (type or print)",
        "delegate_name": "Acceptance Agent's Use ONLY -- Phone",
        "agent_fax": "Acceptance Agent's Use ONLY -- Fax",
        "agent_name_and_title":
            "Acceptance Agent's Use ONLY -- Name and title (type or print)",
        "agent_company_name":
            "Acceptance Agent's Use ONLY -- Name of company",
        "agent_ein": "Acceptance Agent's Use ONLY -- EIN",
        "agent_ptin": "Acceptance Agent's Use ONLY -- PTIN",
        "agent_office_code": "Acceptance Agent's Use ONLY -- Office code",
    },
}


@pytest.mark.parametrize("kit", ["w7"])
def test_every_text_widget_has_a_pinned_name(kit: str) -> None:
    # Non-vacuity floor: the pin above is only worth anything while it covers
    # the whole f1_* run. A new text field added without a pin entry would
    # otherwise inherit zero name coverage silently.
    schema = _load(kit)
    on_page = {
        f["id"] for f in schema["fields"]
        if (_leaf(f.get("pdf_field_name")) or "").startswith("f1_")
    }
    unpinned = sorted(on_page - set(_EXPECTED_NAME[kit]))
    assert unpinned == [], (
        f"{kit}: these f1_* fields have no pinned 'name': {unpinned}. Add the "
        f"caption printed above each widget to _EXPECTED_NAME -- an unpinned "
        f"field is one an off-by-one can shift undetected."
    )
    # Same floor for the widget-mapping table: `name` and `pdf_field_name`
    # shift independently, so both tables have to stay complete or the pair
    # leaves a blind spot.
    unmapped = sorted(on_page - set(_EXPECTED[kit]))
    assert unmapped == [], (
        f"{kit}: these f1_* fields have no pinned widget: {unmapped}. Add the "
        f"widget leaf each one claims to _EXPECTED."
    )


@pytest.mark.parametrize("kit", ["w7"])
def test_human_facing_name_matches_the_printed_caption(kit: str) -> None:
    schema = _load(kit)
    by_id = {f["id"]: f for f in schema["fields"]}
    for fid, want_name in _EXPECTED_NAME[kit].items():
        assert fid in by_id, f"{kit}: field {fid} missing"
        got = by_id[fid].get("name")
        assert got == want_name, (
            f"{kit}: {fid}.name is {got!r}, expected {want_name!r} -- the "
            f"caption printed above its widget. A shifted 'name' mislabels the "
            f"field for BOTH the voice model (ai_context renders 'Name: ...' "
            f"into the system instruction) and the on-screen <label> "
            f"(bd polyglot-pdf-fjxe)"
        )


@pytest.mark.parametrize("kit", ["w7"])
def test_the_agent_phone_does_not_reuse_the_delegate_guidance(kit: str) -> None:
    """bd polyglot-pdf-im2u exit criterion 1.

    `delegate_name` is the Acceptance Agent PHONE box (f1_42), but it shipped
    `name_of_delegate`'s guidance verbatim -- text about who may SIGN for an
    applicant. Guidance is voice-facing (ai_context / manifest_service ship
    help.instructions to the live model without filtering on hidden/read_only),
    so a copied block makes the assistant explain the wrong thing.
    """
    schema = _load(kit)
    by_id = {f["id"]: f for f in schema["fields"]}
    agent_phone = (by_id["delegate_name"].get("help") or {}).get("instructions")
    delegate = (by_id["name_of_delegate"].get("help") or {}).get("instructions")
    assert agent_phone, "delegate_name lost its guidance entirely"
    assert agent_phone != delegate, (
        "delegate_name (the Acceptance Agent phone widget f1_42) is reusing "
        "name_of_delegate's delegate-signature guidance verbatim -- it must "
        "describe the agent's phone number (bd polyglot-pdf-im2u)"
    )


@pytest.mark.parametrize("kit", ["i-90", "w7", "f1040"])
def test_a_complete_kit_is_never_translation_less(kit: str) -> None:
    """A kit marked `complete` must carry its baked translations.

    `status: complete` is the publish gate -- the deploy ships only complete
    kits to the voice app. The editor's own completion route runs a drift sweep
    that re-translates every missing spoken name / option label / section label
    and REFUSES completion until every supported language is covered
    (editor_kit_routes.py, bd polyglot-pdf-783r), precisely because editing an
    English string in the editor DROPS its baked translations.

    Hand-editing metadata.json bypasses that sweep entirely. This catches it:
    without translations the voice path speaks English field names to every
    non-English user (form_filling_service.py loads spoken_name_translations as
    spoken_name_overrides and threads them into the live model), which is a
    silent, user-visible regression on a multilingual product.
    """
    meta_path = _REPO / "form-kits" / kit / "metadata.json"
    schema_path = _REPO / "form-kits" / kit / "schema.json"
    if not meta_path.exists() or not schema_path.exists():
        pytest.skip(f"{kit} kit not present")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if meta.get("status") != "complete":
        pytest.skip(f"{kit} is not marked complete")

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    untranslated = [
        f["id"] for f in schema.get("fields", [])
        if f.get("spoken_name") and not f.get("spoken_name_translations")
    ]
    assert untranslated == [], (
        f"{kit} is marked status:complete but {len(untranslated)} fields have "
        f"no spoken_name_translations: {untranslated[:8]}... Flip it back to "
        f"draft and complete it THROUGH the editor so the translation drift "
        f"sweep runs, rather than hand-editing metadata.json."
    )


@pytest.mark.parametrize("kit", ["w7"])
def test_no_widget_claimed_twice(kit: str) -> None:
    # A permutation fix must stay a bijection: no two fields on one widget.
    schema = _load(kit)
    seen: dict[str, str] = {}
    for f in schema["fields"]:
        leaf = _leaf(f.get("pdf_field_name"))
        if not leaf or not leaf.startswith("f1_"):
            continue
        assert leaf not in seen, (
            f"{kit}: widget {leaf} claimed by both {seen[leaf]} and {f['id']}"
        )
        seen[leaf] = f["id"]
