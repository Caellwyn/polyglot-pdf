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
_EXPECTED_NAME = {
    "w7": {
        "us_person_name_ssn_itin":
            "If d or e, enter name and SSN/ITIN of U.S. citizen/resident alien",
        "reason_h_details": "If h, other reason (see instructions)",
        "treaty_country":
            "Additional information for a and f: Enter treaty country",
        "treaty_article_number": "Treaty article number",
        "phone_number": "Applicant phone number",
        "name_of_delegate":
            "Name of delegate, if applicable (type or print)",
        "delegate_name": "Acceptance Agent's Use ONLY -- Phone",
        "agent_fax": "Acceptance Agent's Use ONLY -- Fax",
        "agent_ein": "Acceptance Agent's Use ONLY -- EIN",
        "agent_ptin": "Acceptance Agent's Use ONLY -- PTIN",
        "agent_office_code": "Acceptance Agent's Use ONLY -- Office code",
    },
}


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
