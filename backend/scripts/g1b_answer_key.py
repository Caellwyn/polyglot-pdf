"""G1b clean answer key -- a HAND-VALIDATED coherent I-90 (bd polyglot-pdf-wf3q).

WHY THIS EXISTS
The G1b bake-off (probe_g1b_model_size_bakeoff.py) measures a contradiction
checker's PRECISION on "clean" full I-90 form states. The prior filler
(g1b_corpus.py's _filler/_first_option_value) generated those clean states
mechanically -- option[0] for every radio/checkbox, substring-keyed persona
values for the rest. That mechanism KEPT MANUFACTURING UNLABELED CONTRADICTIONS
that a good checker correctly flagged but the corpus scored as false positives,
so the precision numbers were not trustworthy. The three Codex-found artifact
classes (and there were more latent ones):
  - p1_checkbox4 option[0] = "Yes, my name legally changed" while the current and
    previous name fields are identical (a real contradiction the checker caught);
  - p5_checkbox1a option[0] = "I can read and understand English" while a Part 6
    INTERPRETER is fully populated (self-cert vs interpreter -- contradiction);
  - state pickers given full names ("California") instead of the schema's option
    values ("CA").

ROOT PROBLEM: a real I-90 is ~132 densely-INTERRELATED fields where many controls
are semantic assertions that constrain other fields (name-change Yes/No gates the
previous-name fields; the English/interpreter/preparer certification gates which
of Parts 6/7 are populated; LPR-vs-commuter gates the port-of-entry field). Naive
per-field filling cannot be coherent because it ignores those gates.

THE FIX (maintainer-specified, bd wf3q): do BY HAND, with big-picture reasoning,
exactly the validation task we ask the small gemini model to do. Read the schema
(field semantics + option LABELS + conditional logic) together, build ONE coherent
fictional persona, answer every field into a dictionary, mark conditional/NA fields
explicitly, and self-review the dictionary to ZERO unlabeled contradictions. That
validated dictionary IS the clean answer key below.

PERSONA (coherent life history)
  Linh Thi Nguyen -- a lawful permanent resident replacing a lost green card.
  - Born Hanoi, Vietnam, 1985-04-12 (female).
  - Admitted to the US as an LPR on 2015-06-20, class of admission IR1.
  - Lives at 4200 Westheimer Rd, Apt 12, Houston, TX 77027 (mailing == physical:
    one address, which is internally coherent and a legitimate clean situation).
  - Her NAME HAS NOT CHANGED since her card was issued (p1_checkbox4 = "No"), so
    the previous-name fields (5a-5c) are conditional-HIDDEN -> NA.
  - Reason for new card: her previous card was lost/stolen/destroyed
    (p2_checkbox2 option [5]); she is a plain Lawful Permanent Resident
    (p2_checkbox1 option [0]), NOT a commuter, so the commuter port-of-entry
    field (p2_line2h1) is conditional-HIDDEN -> NA, and the conditional-PR card
    (p2_checkbox3) is HIDDEN -> NA.
  - She is NOT fluent in written English, so an INTERPRETER (Maria Garcia,
    Vietnamese) read the form to her: p5_checkbox1a = the interpreter-read-to-me
    slug, which makes the Part 6 interpreter block coherent.
  - BOTH Part-5 dependents (p5_line1b_language, p5_line2_nameofrepresentative) are
    NA. p5_checkbox1a is a checkbox GROUP whose renderer value is a string ARRAY;
    shouldShowField's `equals` does a strict scalar compare (array vs a single
    option token -> always false), so neither dependent is EVER visible regardless
    of selection -- the SAME "a real client cannot send a hidden field" condition
    that makes p2_checkbox2[5] NA (fresh-eyes review on PR #253; the frontend bug is
    bd polyglot-pdf-vq4m). The corpus reflects what a real client sends, so both
    are NA.
  - She did NOT use a separate preparer, so the ENTIRE Part 7 preparer block is NA
    (no preparer name, address, signature, etc.) -- the preparer-statement option is
    not selected, so there is no "Part 7 populated but not certified" contradiction.
  - No disability accommodation requested (p4_checkbox1 = "No"), so the
    accommodation sub-fields are conditional-HIDDEN -> NA.
  - No removal proceedings, no I-407 abandonment (Part 3 = "No"/"No").
  - Simple history -> NO Part 8 additional-information overflow entries are needed,
    so every p8_line[3-5]* page/part/item/additionalinfo entry is NA EXCEPT the
    page-header REPEATS (the copy_from fields), which MUST equal their Part 1
    sources (A-number + name printed at the top of each continuation page).

COHERENCE INVARIANTS the self-review enforced (these are exactly what the checker
looks for, so any violation here would be a corpus artifact):
  1. State pickers use schema OPTION VALUES (two-letter), never full names.
  2. radio/checkbox values are real schema option values, chosen for SEMANTIC
     coherence (the option LABEL must be true of the persona), NOT option[0].
  3. ZIP <-> state <-> city <-> country are mutually consistent (Houston/TX/77027,
     USA). No US state paired with a foreign country; no foreign province paired
     with a US state.
  4. DOB (1985) precedes admission (2015) precedes signature (2025); no future DOB.
  5. Conditional fields whose gate is not satisfied are explicitly NA (value None),
     with the gate recorded in NA_REASON -- they are OMITTED from the payload, as
     production omits empty fields, so they can never be a spurious "incomplete".
  6. copy_from page-header repeats equal their Part 1 source EXACTLY.
  7. Two coherent statements of one fact never disagree (no Part-8 free text
     restating the DOB or residence-length differently -- those textareas are NA
     in the clean key; the bake-off's cross_date / duration_year MUTANTS are the
     only place such a restatement appears, and there it is a LABELED conflict).

This module is STDLIB-ONLY (json + os) so the offline tools can import it without
google.genai. ASCII only (repo rule). PII: synthetic fabricated persona, no PHI.
"""
from __future__ import annotations

import json
import os

_SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "form-kits", "i-90", "schema.json",
)


def load_schema_fields() -> list:
    """The I-90 leaf fields in document order, each a dict with id, spoken_name,
    type, section_id, options (the raw list), and copy_from (so the corpus can
    verify the page-header repeats). One source of truth for field ORDER + names
    so the answer key and the probe agree."""
    with open(_SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    out = []
    for fld in schema["fields"]:
        fid = fld.get("id")
        if not fid:
            continue
        out.append({
            "field_id": fid,
            "name": fld.get("spoken_name") or fld.get("name") or fid,
            "type": fld.get("type", "text"),
            "section_id": fld.get("section_id", ""),
            "options": fld.get("options") or [],
            "copy_from": fld.get("copy_from"),
        })
    return out


# Separator for a multi-select checkbox GROUP value in the answer key (e.g. an
# applicant who selects BOTH the interpreter statement AND the preparer statement
# on p5_checkbox1a). A checkbox group has no schema-defined separator, so the
# corpus uses "; " purely as the answer-key encoding; option_label resolves each
# part to its label so the checker reads the joined human meaning.
MULTI_SEP = "; "


# US state OPTION SLUG -> two-letter USPS abbreviation. Since the schema-v2
# migration (bd polyglot-pdf-c5r8) the state pickers' option VALUES are full-name
# slugs ("texas", "new_york") whose LABELS are the full names ("Texas", "New
# York"). The bead's "state pickers use abbreviations" coherence rule means the
# PAYLOAD must still carry the two-letter code, so option_label resolves a state
# slug to its abbreviation here (pre-migration the schema value WAS "TX", so no
# map was needed). Derived from migration_report.json slug_maps.p1_line6e_state.
_STATE_SLUG_TO_ABBR = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new_hampshire": "NH", "new_jersey": "NJ", "new_mexico": "NM", "new_york": "NY",
    "north_carolina": "NC", "north_dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode_island": "RI",
    "south_carolina": "SC", "south_dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west_virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}


def _field_id(field: dict) -> str:
    return str(field.get("field_id") or field.get("id") or "")


def _is_state_field(field: dict) -> bool:
    """True for the I-90 state pickers (their id ends in '_state')."""
    return _field_id(field).endswith("_state")


def _is_color_field(field: dict) -> bool:
    """True for the I-90 eye/hair color pickers (their id ends in '_color').

    Their schema-v2 slugs ARE already human-legible lowercase words ("brown"),
    equal to the label lowercased, so the payload keeps the slug as-is rather than
    capitalizing it to the label -- the checker reads "brown" fine and the corpus
    guard test pins that."""
    return _field_id(field).endswith("_color")


def option_label(field: dict, value: str) -> str:
    """Resolve an option-typed field's raw VALUE token(s) to its human LABEL(s).

    The answer key stores the schema's raw option value (e.g. "P5_Checkbox1b[0]"
    pre-migration; the schema-v2 semantic slug
    "the_interpreter_named_in_part_6_..." post bd polyglot-pdf-c5r8) so
    validate_answer_key() can check it against the schema. But a contradiction
    checker reading the payload sees only that opaque token and cannot tell whether
    the selected option is coherent -- so a clean case like p1_line8_male =
    "female" or p5_checkbox1a = the interpreter slug gets spuriously flagged (Codex
    review on PR #253: those lone-field FPs were corpus artifacts, not model
    noise). Resolving the value to its LABEL ("Female"; "The interpreter named in
    Part 6 has read to me ...") gives the checker the same meaning a human reader
    has.

    A multi-select checkbox GROUP value is MULTI_SEP-joined raw tokens; each part is
    resolved to its label and re-joined. Falls back to the raw token if the field
    has no options or a token is not among them (so a non-option field or an injected
    free-text value passes through unchanged).

    STATE pickers are special: their schema-v2 option slugs are full-name
    ("texas"), but the bead's coherence rule keeps the payload on two-letter
    abbreviations ("TX"), so a state slug is resolved via _STATE_SLUG_TO_ABBR
    instead of to its full-name label. A value ALREADY a two-letter code (e.g. the
    corpus injection cases set state directly to "TX", or a foreign address leaves
    it "") passes through unchanged.

    COLOR pickers (eye/hair) are ALSO left as-is: their schema-v2 slugs are already
    human-legible lowercase words ("brown"), so the payload keeps the slug.

    Every OTHER known option value is relabeled to its schema LABEL ("female" ->
    "Female", "asian" -> "Asian", the interpreter slug -> its statement), so the
    checker reads the human meaning rather than the opaque slug (Codex review on PR
    #253: those lone-field FPs were corpus artifacts). A token that is NOT a schema
    option value (a non-option field, or an injected free-text value) passes through
    unchanged."""
    opts = {str(o.get("value")): str(o.get("label"))
            for o in (field.get("options") or [])
            if isinstance(o, dict) and o.get("label")}
    if not opts:
        return str(value)

    state_field = _is_state_field(field)
    color_field = _is_color_field(field)

    def _resolve(token: str) -> str:
        if state_field:
            # keep the payload on the two-letter abbreviation; an already-abbreviated
            # or empty value (injection cases / foreign address) passes through.
            return _STATE_SLUG_TO_ABBR.get(token, token)
        if color_field:
            # already-legible lowercase color slug -- leave as-is.
            return token
        # relabel a known option slug to its human label; leave free text unchanged.
        return opts.get(token, token)

    parts = [p.strip() for p in str(value).split(MULTI_SEP) if p.strip()] or [str(value)]
    return MULTI_SEP.join(_resolve(p) for p in parts)


# ===========================================================================
# THE VALIDATED ANSWER KEY: field_id -> value.
#   - A string value is the coherent answer.
#   - None marks a field that is conditional-HIDDEN or genuinely inapplicable for
#     THIS persona (see NA_REASON). NA fields are omitted from the payload, just
#     as production omits empty fields, so a checker never sees them.
# Every option-typed value is a real schema option VALUE chosen so its LABEL is
# true of the persona (see the module docstring). Verified against schema.json by
# validate_answer_key() below (run this module as __main__).
# ===========================================================================
ANSWER_KEY: dict = {
    # ---- Part 1: Information About You ----
    "p1_line1_aliennumber": "A123456789",
    "p1_line2_acctidentifier": "1234567890123",   # USCIS online account number (13 digits)
    "p1_line3a_familyname": "Nguyen",
    "p1_line3b_givenname": "Linh",
    "p1_line3c_middlename": "Thi",
    # Name has NOT changed -> the "No" option; gates 5a-5c HIDDEN.
    "p1_checkbox4": "no_proceed_to_item_numbers_6_a_6_c",
    "p1_line5a_familyname": None,   # NA: name-change gate = No
    "p1_line5b_givenname": None,    # NA: name-change gate = No
    "p1_line5c_middlename": None,   # NA: name-change gate = No

    # ---- Part 1.2: Mailing address (4200 Westheimer Rd, Apt 12, Houston TX) ----
    "p1_line6a_incareofname": None,           # NA: no in-care-of recipient
    "p1_line6b_streetnumbername": "4200 Westheimer Rd",
    # Unit type = Apartment -> unlocks the apt number field.
    "p1_unit_type6c_unit": "apartment",   # Apartment
    "p1_line6c_aptsteflrnumber": "12",
    "p1_line6d_cityortown": "Houston",
    "p1_line6e_state": "texas",   # schema-v2 slug; option_label renders it "TX"
    "p1_line6f_zipcode": "77027",
    "p1_line6g_province": None,    # NA: US address, no foreign province
    "p1_line6h_postalcode": None,  # NA: US address, no foreign postal code
    "p1_line6i_country": "United States",

    # ---- Part 1.2.1: Physical address == mailing (one coherent address) ----
    "p1_line7a_streetnumbername": "4200 Westheimer Rd",
    "p1_unit_type7b_unit": "apartment",   # Apartment
    "p1_line7b_aptsteflrnumber": "12",
    "p1_line7c_cityortown": "Houston",
    "p1_line7d_state": "texas",   # schema-v2 slug; option_label renders it "TX"
    "p1_line7e_zipcode": "77027",
    "p1_line7f_province": None,    # NA: US address
    "p1_line7g_postalcode": None,  # NA: US address
    "p1_line7h_country": "United States",

    # ---- Part 1.3: Additional information about you ----
    "p1_line8_male": "female",   # Female
    "p1_line9_dateofbirth": "1985-04-12",
    "p1_line10_citytownofbirth": "Hanoi",
    "p1_line11_countryofbirth": "Vietnam",
    "p1_line12_mothergivenname": "Lan",
    "p1_line13_fathergivenname": "Minh",
    "p1_line14_classofadmission": "IR1",
    "p1_line15_dateofadmission": "2015-06-20",
    "p1_line16_ssn": "123-45-6789",

    # ---- Part 2: Application type ----
    # Plain Lawful Permanent Resident. (NOT commuter, NOT conditional.)
    "p2_checkbox1": "lawful_permanent_resident",
    # Commuter port-of-entry: gated on commuter reason; NA for a plain LPR.
    "p2_line2h1_cityandstate": None,
    # Reason for new card (p2_checkbox2[5]): NA for THIS persona. The schema is
    # self-inconsistent here -- p2_checkbox1.controls_fields unlocks the reason
    # field for option [0] (plain LPR) too, but p2_checkbox2[5].show_if requires
    # option [1] (commuter). The PRODUCTION renderer gates on show_if
    # (frontend shouldShowField) and HIDES the field for a plain LPR, rejecting any
    # hidden-field update -- so a real client could NOT send this field for this
    # persona. The corpus must reflect what a real client sends, so the field is NA
    # here (Codex review on PR #253). The schema discrepancy itself is tracked in
    # bd polyglot-pdf-zi2s.
    "p2_checkbox2[5]": None,
    # "issued but never received": gated on Conditional-PR (checkbox1 option [2]); NA.
    "p2_checkbox3": None,

    # ---- Part 3: Processing information ----
    "p3_line1_locationappliedvisa": "Ho Chi Minh City, Vietnam",
    "p3_line2_locationissuedvisa": "Ho Chi Minh City, Vietnam",
    "p3_line3a_destination": "Houston, TX",
    "p3_line3a1_cityandstate": "Houston, TX",
    "p3_checkbox4[1]": "select_no",   # removal proceedings? No
    "p3_checkbox5[1]": "select_no",   # filed I-407 / abandoned status? No

    # ---- Part 3: Biographic information ----
    "p3_ethnicity": "not_hispanic_or_latino",
    "p3_race": "asian",     # Asian
    "p3_line8_heightfeet": "5",             # 5 ft 4 in
    "p3_line8_heightinches": "4",
    "p3_line9_heightinches1": "1",          # weight 130 lbs (digits 1,3,0)
    "p3_line9_heightinches2": "3",
    "p3_line9_heightinches3": "0",
    "p3_eye_color": "brown",
    "p3_hair_color": "black",

    # ---- Part 4: Accommodations -- none requested ----
    "p4_checkbox1[1]": "select_no",   # requesting accommodation? No
    "p4_checkbox1a": None,                   # NA: gate = No
    "p4_line1a_accomodationrequested": None,  # NA
    "p4_checkbox1b": None,                    # NA: gate = No
    "p4_line1b_accomodationrequested": None,  # NA
    "p4_checkbox1c": None,                    # NA: gate = No
    "p4_line1c_accomodationrequested": None,  # NA

    # ---- Part 5: Applicant's statement, contact, signature ----
    # Interpreter statement selected -> the "interpreter named in Part 6 read to me"
    # slug, which makes the Part 6 interpreter block coherent. NOT the "I can read
    # and understand English" slug -- that would contradict having an interpreter.
    #
    # Both Part-5 DEPENDENTS are NA. p5_checkbox1a is a checkbox GROUP, so the
    # renderer stores its value as a string ARRAY; shouldShowField's `equals`
    # operator does a strict scalar compare (array vs a single slug -> always
    # false), so p5_line1b_language and p5_line2_nameofrepresentative are NEVER
    # visible regardless of selection -- the SAME "a real client cannot send a hidden
    # field" condition that makes p2_checkbox2[5] NA (fresh-eyes review on PR #253;
    # the underlying frontend bug -- `equals` not handling an array trigger -- is
    # filed as bd polyglot-pdf-vq4m). The corpus reflects what a real client sends,
    # so both dependents are NA. (Selecting BOTH statements would not help: the gate
    # fails for an array regardless of contents.) The entire Part 7 preparer block is
    # likewise NA -- the persona used an interpreter, not a separate preparer, and the
    # preparer-statement option is not selected.
    "p5_checkbox1a": "the_interpreter_named_in_part_6_has_read_to_me_every_question_and_instruction_on_this_application_and_my_answer_to_every_question_in_a_language_in_which_i_am_fluent_and_i_understood_everything",
    "p5_line1b_language": None,
    "p5_line2_nameofrepresentative": None,
    "p5_line3_daytimephonenumber": "713-555-0142",
    "p5_line4_mobilephonenumber": "713-555-0199",
    "p5_line5_emailaddress": "linh.nguyen@example.com",
    "p5_line6a_signatureofapplicant": "Linh Nguyen",
    "p5_line6b_dateofsignature": "2025-06-01",

    # ---- Part 6: Interpreter (Maria Garcia, Vietnamese) ----
    "p6_line1a_interpretersfamilyname": "Garcia",
    "p6_line1b_interpretersgivenname": "Maria",
    "p6_line2_nameofbusinessor": "Bayou City Language Services",
    "p6_line3a_streetnumbername": "1000 Louisiana St",
    "p6_unit_type3b_unit": "suite",   # Suite
    "p6_line3b_aptsteflrnumber": "2300",
    "p6_line3c_citytown": "Houston",
    "p6_line3d_state": "texas",   # schema-v2 slug; option_label renders it "TX"
    "p6_line3e_zipcode": "77002",
    "p6_line3f_province": None,    # NA: US address
    "p6_line3g_postalcode": None,  # NA: US address
    "p6_line3h_country": "United States",
    "p6_line4_interpretersdaytimephonenumber": "713-555-0188",
    "p6_line4_interpretersdaytimephonenumber[1]": "713-555-0177",
    "p6_line5_interpretersemailaddress": "maria.garcia@example.com",
    "p6_language": "Vietnamese",
    "p6_line6a_signature": "Maria Garcia",
    "p6_line6b_dateofsignature": "2025-06-01",

    # ---- Part 7: Preparer -- ENTIRELY NA for this persona ----
    # The persona used an interpreter, NOT a separate preparer (see the Part 5 note
    # + the module docstring). Because Part 5's preparer-statement option is NOT
    # selected, populating Part 7 would be an unlabeled contradiction ("a preparer
    # exists but the applicant did not certify one" -- Codex review on PR #253), so
    # the ENTIRE Part 7 block is NA.
    "p7_line1b_preparersgivenname": None,
    "p7_line1a_familyname": None,
    "p7_line2_nameofbusinessor": None,
    "p7_line3a_streetnumbername": None,
    "p7_unit_type3b_unit": None,
    "p7_line3b_aptsteflrnumber": None,
    "p7_line3c_citytown": None,
    "p7_line3d_state": None,
    "p7_line3e_zipcode": None,
    "p7_line3f_province": None,
    "p7_line3g_postalcode": None,
    "p7_line3h_country": None,
    "p7_line4_preparersdaytimephonenumber": None,
    "p7_line5_preparersfaxnumber": None,
    "p7_line6_preparersemailaddress": None,
    "p7_checkbox7": None,
    "p7_checkbox7extend": None,
    "p7_line8a_signatureofpreparer": None,
    "p7_line8b_dateofsignature": None,

    # ---- Part 8: Additional information ----
    # Page-header REPEATS (copy_from Part 1) MUST equal their source exactly.
    "p1_line1_aliennumber[1]": "A123456789",
    "p1_line3a_familyname[1]": "Nguyen",
    "p1_line3b_givenname[1]": "Linh",
    "p1_line3c_middlename[1]": "Thi",
    # No overflow continuation is needed for this simple, coherent history -> every
    # additional-information ENTRY (page/part/item/free-text) is NA. The bake-off
    # cross_date / duration_year MUTANTS are the only place a Part-8 free-text
    # restatement appears, and there it is a LABELED conflict, not clean.
    "p8_line3a_pagenumber": None,
    "p8_line3b_partnumber": None,
    "p8_line3c_itemnumber": None,
    "p8_line3d_additionalinfo": None,
    "p8_line5a_pagenumber[1]": None,
    "p8_line5b_partnumber[1]": None,
    "p8_line5c_itemnumber[1]": None,
    "p8_line5d_additionalinfo[1]": None,
    "p8_line4a_pagenumber": None,
    "p8_line4b_partnumber": None,
    "p8_line4c_itemnumber": None,
    "p8_line4d_additionalinfo": None,
    "p8_line5a_pagenumber": None,
    "p8_line5b_partnumber": None,
    "p8_line5c_itemnumber": None,
    "p8_line5d_additionalinfo": None,
    "p8_line5a_pagenumber[2]": None,
    "p8_line5b_partnumber[2]": None,
    "p8_line5c_itemnumber[2]": None,
    "p8_line5d_additionalinfo[2]": None,
}


# Why each NA field is inapplicable -- the conditional GATE that hides it, or the
# plain reason it does not apply to this persona. Documented so a reviewer can
# audit that every omission is intentional (not a forgotten field).
NA_REASON: dict = {
    "p1_line5a_familyname": "name-change gate p1_checkbox4 = No",
    "p1_line5b_givenname": "name-change gate p1_checkbox4 = No",
    "p1_line5c_middlename": "name-change gate p1_checkbox4 = No",
    "p1_line6a_incareofname": "no in-care-of recipient",
    "p1_line6g_province": "US mailing address, no foreign province",
    "p1_line6h_postalcode": "US mailing address, no foreign postal code",
    "p1_line7f_province": "US physical address, no foreign province",
    "p1_line7g_postalcode": "US physical address, no foreign postal code",
    "p2_line2h1_cityandstate": "commuter port-of-entry; persona is a plain LPR",
    "p2_checkbox2[5]": "reason-for-new-card field is show_if-gated to commuter (option [1]); production hides it for a plain LPR, so a real client cannot send it (see bd zi2s)",
    "p2_checkbox3": "issued-but-never-received gate p2_checkbox1 = Conditional PR (not selected)",
    "p4_checkbox1a": "accommodation gate p4_checkbox1 = No",
    "p4_line1a_accomodationrequested": "accommodation gate p4_checkbox1 = No (and gated on the p4_checkbox1a checkbox-group trigger, the same never-matching array `equals` as bd vq4m)",
    "p4_checkbox1b": "accommodation gate p4_checkbox1 = No",
    "p4_line1b_accomodationrequested": "accommodation gate p4_checkbox1 = No (and gated on the p4_checkbox1b checkbox-group trigger, the same never-matching array `equals` as bd vq4m)",
    "p4_checkbox1c": "accommodation gate p4_checkbox1 = No",
    "p4_line1c_accomodationrequested": "accommodation gate p4_checkbox1 = No (and gated on the p4_checkbox1c checkbox-group trigger, the same never-matching array `equals` as bd vq4m)",
    "p5_line1b_language": "show_if equals on the p5_checkbox1a checkbox GROUP (array trigger) never matches in the renderer, so the field is always hidden -- a real client cannot send it (see bd vq4m)",
    "p5_line2_nameofrepresentative": "preparer-statement option not selected (interpreter path); also gated by the same never-matching array `equals` (bd vq4m)",
    "p6_line3f_province": "US interpreter address, no foreign province",
    "p6_line3g_postalcode": "US interpreter address, no foreign postal code",
    # Entire Part 7 preparer block NA: persona used an interpreter, not a separate
    # preparer (the Part 5 preparer-statement option is not selected), so populating
    # Part 7 would be an unlabeled contradiction.
    "p7_line1b_preparersgivenname": "no separate preparer (interpreter path)",
    "p7_line1a_familyname": "no separate preparer (interpreter path)",
    "p7_line2_nameofbusinessor": "no separate preparer (interpreter path)",
    "p7_line3a_streetnumbername": "no separate preparer (interpreter path)",
    "p7_unit_type3b_unit": "no separate preparer (interpreter path)",
    "p7_line3b_aptsteflrnumber": "no separate preparer (interpreter path)",
    "p7_line3c_citytown": "no separate preparer (interpreter path)",
    "p7_line3d_state": "no separate preparer (interpreter path)",
    "p7_line3e_zipcode": "no separate preparer (interpreter path)",
    "p7_line3f_province": "no separate preparer (interpreter path)",
    "p7_line3g_postalcode": "no separate preparer (interpreter path)",
    "p7_line3h_country": "no separate preparer (interpreter path)",
    "p7_line4_preparersdaytimephonenumber": "no separate preparer (interpreter path)",
    "p7_line5_preparersfaxnumber": "no separate preparer (interpreter path)",
    "p7_line6_preparersemailaddress": "no separate preparer (interpreter path)",
    "p7_checkbox7": "no separate preparer (interpreter path)",
    "p7_checkbox7extend": "no separate preparer (interpreter path)",
    "p7_line8a_signatureofpreparer": "no separate preparer (interpreter path)",
    "p7_line8b_dateofsignature": "no separate preparer (interpreter path)",
    "p8_line3a_pagenumber": "no additional-information overflow needed",
    "p8_line3b_partnumber": "no additional-information overflow needed",
    "p8_line3c_itemnumber": "no additional-information overflow needed",
    "p8_line3d_additionalinfo": "no additional-information overflow needed",
    "p8_line5a_pagenumber[1]": "no additional-information overflow needed",
    "p8_line5b_partnumber[1]": "no additional-information overflow needed",
    "p8_line5c_itemnumber[1]": "no additional-information overflow needed",
    "p8_line5d_additionalinfo[1]": "no additional-information overflow needed",
    "p8_line4a_pagenumber": "no additional-information overflow needed",
    "p8_line4b_partnumber": "no additional-information overflow needed",
    "p8_line4c_itemnumber": "no additional-information overflow needed",
    "p8_line4d_additionalinfo": "no additional-information overflow needed",
    "p8_line5a_pagenumber": "no additional-information overflow needed",
    "p8_line5b_partnumber": "no additional-information overflow needed",
    "p8_line5c_itemnumber": "no additional-information overflow needed",
    "p8_line5d_additionalinfo": "no additional-information overflow needed",
    "p8_line5a_pagenumber[2]": "no additional-information overflow needed",
    "p8_line5b_partnumber[2]": "no additional-information overflow needed",
    "p8_line5c_itemnumber[2]": "no additional-information overflow needed",
    "p8_line5d_additionalinfo[2]": "no additional-information overflow needed",
}


def validate_answer_key() -> list:
    """Self-check the answer key against schema.json. Returns a list of human
    -readable problem strings; empty list == the key is structurally valid.

    This is the MECHANICAL half of the validation (coverage, valid option values,
    copy-field equality, NA bookkeeping). The SEMANTIC half (the coherence
    invariants in the docstring) is the Opus-level hand review that produced the
    values -- this function guards against drift, it does not replace that review.
    """
    fields = load_schema_fields()
    by_id = {f["field_id"]: f for f in fields}
    problems: list = []

    schema_ids = set(by_id)
    key_ids = set(ANSWER_KEY)

    # 1. Every schema field is answered; no stray keys.
    for fid in sorted(schema_ids - key_ids):
        problems.append(f"MISSING from answer key: {fid}")
    for fid in sorted(key_ids - schema_ids):
        problems.append(f"STRAY key not in schema: {fid}")

    # 2. Every None value has an NA_REASON, and every NA_REASON maps a None field.
    for fid, val in ANSWER_KEY.items():
        if val is None and fid not in NA_REASON:
            problems.append(f"NA field with no NA_REASON: {fid}")
    for fid in NA_REASON:
        if ANSWER_KEY.get(fid) is not None:
            problems.append(f"NA_REASON for a non-NA (or unknown) field: {fid}")

    # 3. Option-typed fields must hold a real schema option VALUE. A checkbox GROUP
    #    may hold several, MULTI_SEP-joined; each part must be a valid option.
    for fid, val in ANSWER_KEY.items():
        if val is None or fid not in by_id:
            continue
        f = by_id[fid]
        if f["type"] in ("radio", "checkbox", "checkbox_group", "select") and f["options"]:
            valid = set()
            for opt in f["options"]:
                if isinstance(opt, dict) and opt.get("value") is not None:
                    valid.add(str(opt["value"]))
                elif not isinstance(opt, dict) and opt is not None:
                    valid.add(str(opt))
            parts = [p.strip() for p in str(val).split(MULTI_SEP) if p.strip()]
            for part in parts:
                if part not in valid:
                    problems.append(
                        f"{fid}: value part {part!r} is not one of the schema "
                        f"options {sorted(valid)}")

    # 4. copy_from page-header repeats must equal their source EXACTLY.
    for fid, f in by_id.items():
        src = f.get("copy_from")
        if src:
            if ANSWER_KEY.get(fid) != ANSWER_KEY.get(src):
                problems.append(
                    f"copy mismatch: {fid}={ANSWER_KEY.get(fid)!r} but its source "
                    f"{src}={ANSWER_KEY.get(src)!r} (must be equal)")

    return problems


if __name__ == "__main__":
    probs = validate_answer_key()
    if probs:
        print(f"ANSWER KEY INVALID -- {len(probs)} problem(s):")
        for p in probs:
            print("  -", p)
        raise SystemExit(1)
    fields = load_schema_fields()
    answered = sum(1 for f in fields if ANSWER_KEY.get(f["field_id"]) is not None)
    na = sum(1 for f in fields if ANSWER_KEY.get(f["field_id"]) is None)
    print(f"answer key VALID: {len(fields)} fields = {answered} filled + {na} NA")
