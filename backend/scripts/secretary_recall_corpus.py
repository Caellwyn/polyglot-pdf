"""Secretary RECALL probe corpus -- a labeled, stratified prose-query battery.

bd polyglot-pdf-jnjj.26 (Secretary Gate 1, RECALL). The probe
(probe_secretary_recall.py) renders the I-90 secretary context from the FIXTURE
below, then asks gemini-2.5-flash-lite each QUERY here and scores its answer's
grounding (the field ids it cites) against the query's expected_field_ids.

PROVENANCE -- state it, don't fudge it (mirrors g1_corpus.py):
  This corpus is SYNTHETIC. There is no captured-transcript corpus for this
  project (pre-pilot; no field values logged server-side per the PII policy). The
  field IDs, spoken names, types, and help text are REAL -- pulled verbatim from
  form-kits/i-90/schema.json. The VALUES in the fixture and the QUERIES are
  hand-authored.

  TWO stacking inflation sources push recall UP, so every number is an UPPER
  BOUND on real-world recall:
    (a) the fixture VALUES are clean and coherent, unlike messy half-filled
        mid-correction real state; and
    (b) the QUERIES are authored to map onto fields, more on-distribution than
        real spontaneous speech.
  Read the findings doc with both caveats in mind.

THE FIXTURE (one shared form state for all queries, so answers are consistent):
  A name-changed applicant (so the previous-name green-card fields are applicable
  AND filled), with a mailing address and a SEPARATE physical address (different,
  both coherent), date of birth + date of admission, parents named, and an
  interpreter used (interpreter fields filled). NO preparer (the applicant
  prepared their own form) -> preparer fields are hidden=false (not applicable):
  the tier-6 hidden-vs-empty contrast.

  shown_map carries applicability INDEPENDENTLY of value (the real frontend tracks
  shown/hidden separately from filled). Only entries that DIFFER from the default
  (shown=true) are listed: the preparer block is hidden; one applicable-but-empty
  field (current middle name) is left empty-but-shown for the tier-6 "answered?"
  contrast.

DIFFICULTY TIERS (the report slices by these):
  easy          single-field direct lookup
  aliasing      prose that does not match spoken_name; leans on help.instructions
  ambiguous     query maps to several candidate fields (the name cluster + the
                street-"name" distractors); expected = the candidate SET
  synthesis     2-field then 3+-field gather
  distant       fields far apart that must be related
  applicability value-vs-applicability (hidden vs empty-but-applicable)

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field


# ----------------------------------------------------------------------------
# Fixture: shared form state (field_values) + applicability (shown_map).
# ----------------------------------------------------------------------------

FIELD_VALUES = {
    # Numbers
    "p1_line1_aliennumber": "123456789",
    # Current name (the name the card will be issued in)
    "p1_line3a_familyname": "Okafor",
    "p1_line3b_givenname": "Adaeze",
    # current middle name left EMPTY but applicable (tier-6 "answered?" contrast)
    # Name changed -> previous (green-card) name applicable AND filled
    "p1_checkbox4": "P1_checkbox4[0]",  # Yes, name changed
    "p1_line5a_familyname": "Eze",
    "p1_line5b_givenname": "Adaeze",
    "p1_line5c_middlename": "Ngozi",
    # Mailing address
    "p1_line6b_streetnumbername": "742 Evergreen Terrace",
    "p1_line6d_cityortown": "Springfield",
    "p1_line6e_state": "Illinois",
    "p1_line6f_zipcode": "62704",
    "p1_line6i_country": "United States",
    # Physical address (DIFFERENT from mailing, both coherent)
    "p1_line7a_streetnumbername": "1600 Pennsylvania Avenue",
    "p1_line7c_cityortown": "Chicago",
    "p1_line7d_state": "Illinois",
    "p1_line7e_zipcode": "60601",
    "p1_line7h_country": "United States",
    # Dates + birth
    "p1_line9_dateofbirth": "1990-04-02",
    "p1_line10_citytownofbirth": "Lagos",
    "p1_line11_countryofbirth": "Nigeria",
    "p1_line15_dateofadmission": "2015-09-20",
    # Parents
    "p1_line12_mothergivenname": "Chioma",
    "p1_line13_fathergivenname": "Emeka",
    # Contact
    "p5_line3_daytimephonenumber": "3125550148",
    "p5_line5_emailaddress": "adaeze.okafor@example.com",
    # Interpreter used -> the applicant did NOT self-certify English proficiency,
    # so p5_checkbox1a ("I can read and understand English") is left UNCHECKED
    # (absent from field_values), and the Part 6 interpreter block is filled.
    # These two facts are consistent (no-English-self-cert => interpreter used);
    # the app_interpreter_used case tests whether the secretary reads the Part 6
    # VALUE fields rather than guessing from the unchecked Part 5 checkbox.
    "p6_line1a_interpretersfamilyname": "Garcia",
    "p6_line1b_interpretersgivenname": "Maria",
    "p6_line3d_state": "Illinois",
    "p6_line5_interpretersemailaddress": "maria.garcia@example.com",
}

# Applicability overrides (everything else defaults to shown=true).
# The preparer block is NOT applicable (applicant self-prepared) -- hide the WHOLE
# Part 7 block (every p7_* field), so the "self-prepared" context is clean and the
# applicability tier is not muddied by leaked secondary preparer fields.
_P7_HIDDEN = {
    "p7_line1b_preparersgivenname": False,
    "p7_line1a_familyname": False,
    "p7_line2_nameofbusinessor": False,
    "p7_line3a_streetnumbername": False,
    "p7_unit_type3b_unit": False,
    "p7_line3b_aptsteflrnumber": False,
    "p7_line3c_citytown": False,
    "p7_line3d_state": False,
    "p7_line3e_zipcode": False,
    "p7_line3f_province": False,
    "p7_line3g_postalcode": False,
    "p7_line3h_country": False,
    "p7_line4_preparersdaytimephonenumber": False,
    "p7_line5_preparersfaxnumber": False,
    "p7_line6_preparersemailaddress": False,
    "p7_checkbox7": False,
    "p7_checkbox7extend": False,
    "p7_line8a_signatureofpreparer": False,
    "p7_line8b_dateofsignature": False,
}
SHOWN_MAP = {
    **_P7_HIDDEN,
    # current middle name: applicable (shown) but left empty -> tier-6 contrast
    "p1_line3c_middlename": True,
}


@dataclass
class Case:
    case_id: str
    tier: str  # easy|aliasing|ambiguous|synthesis|distant|applicability
    query: str
    # Ground-truth set of field ids the answer should be grounded in.
    expected_field_ids: list = dc_field(default_factory=list)
    notes: str = ""


def build_corpus() -> list:
    C = []

    # ===================== easy (single-field lookup) =====================
    C += [
        Case("easy_dob", "easy", "What's their date of birth?",
             ["p1_line9_dateofbirth"]),
        Case("easy_email", "easy", "What email address did they give?",
             ["p5_line5_emailaddress"]),
        Case("easy_country_birth", "easy", "What country were they born in?",
             ["p1_line11_countryofbirth"]),
        Case("easy_mother", "easy", "What is their mother's given name?",
             ["p1_line12_mothergivenname"]),
        Case("easy_anumber", "easy", "What's their alien registration number?",
             ["p1_line1_aliennumber"]),
    ]

    # ===================== aliasing (prose != spoken_name) =====================
    C += [
        Case("alias_greencard_name", "aliasing",
             "What was their name as printed on their green card?",
             ["p1_line5a_familyname", "p1_line5b_givenname", "p1_line5c_middlename"],
             "green card = previous Permanent Resident Card name (help.instructions)"),
        Case("alias_anumber", "aliasing",
             "What's their A-number?", ["p1_line1_aliennumber"],
             "A-number alias for alien registration number"),
        Case("alias_phone", "aliasing",
             "What number can we reach them at during the day?",
             ["p5_line3_daytimephonenumber"]),
        Case("alias_admission", "aliasing",
             "When were they admitted to the United States?",
             ["p1_line15_dateofadmission"]),
        Case("alias_hometown", "aliasing",
             "Where were they born -- which city?",
             ["p1_line10_citytownofbirth"]),
        Case("alias_zip_mailing", "aliasing",
             "What's the postal code on their mailing address?",
             ["p1_line6f_zipcode"],
             "US zip is the 'postal code' for a US mailing address"),
    ]

    # ===================== ambiguous (candidate SET) =====================
    C += [
        Case("amb_previous_name", "ambiguous",
             "What did they say their previous name was?",
             ["p1_line5a_familyname", "p1_line5b_givenname", "p1_line5c_middlename"],
             "the green-card previous-name cluster"),
        Case("amb_last_name", "ambiguous",
             "What's their last name?",
             ["p1_line3a_familyname"],
             "current family name is the issued-card name; distractor: previous family name"),
        Case("amb_their_name", "ambiguous",
             "What name did they give me?",
             ["p1_line3a_familyname", "p1_line3b_givenname"],
             "current full name; ambiguous across current/previous clusters"),
        Case("amb_street_vs_person_name", "ambiguous",
             "What's the name on their mailing address?",
             ["p1_line6b_streetnumbername"],
             "DISTRACTOR: 'name' here is street number AND name, not a person name"),
        Case("amb_middle_name", "ambiguous",
             "What's their middle name?",
             ["p1_line3c_middlename", "p1_line5c_middlename"],
             "current (empty) vs previous (Ngozi) middle name -- genuinely ambiguous"),
        Case("amb_state", "ambiguous",
             "What state are they in?",
             ["p1_line6e_state", "p1_line7d_state"],
             "mailing vs physical state (both Illinois) -- which address?"),
        Case("amb_phone", "ambiguous",
             "What's their phone number?",
             ["p5_line3_daytimephonenumber"],
             "only daytime phone filled; mobile empty"),
        Case("amb_interpreter_name", "ambiguous",
             "What's the interpreter's name?",
             ["p6_line1a_interpretersfamilyname", "p6_line1b_interpretersgivenname"]),
        Case("amb_father_or_mother", "ambiguous",
             "What did they put for their parent's name?",
             ["p1_line12_mothergivenname", "p1_line13_fathergivenname"],
             "both parents named -- candidate set"),
        Case("amb_country", "ambiguous",
             "What country is on file?",
             ["p1_line11_countryofbirth", "p1_line6i_country", "p1_line7h_country"],
             "country of birth vs mailing vs physical country -- ambiguous"),
    ]

    # ===================== synthesis (2-field then 3+-field) =====================
    C += [
        Case("syn_full_name", "synthesis",
             "What's their full current name?",
             ["p1_line3a_familyname", "p1_line3b_givenname"],
             "family + given (current middle empty)"),
        Case("syn_married_maiden", "synthesis",
             "Tell me both their current and previous family names.",
             ["p1_line3a_familyname", "p1_line5a_familyname"],
             "the married/maiden-style 2-field gather"),
        Case("syn_mailing_addr", "synthesis",
             "Summarize their mailing address.",
             ["p1_line6b_streetnumbername", "p1_line6d_cityortown",
              "p1_line6e_state", "p1_line6f_zipcode", "p1_line6i_country"],
             "5-field gather"),
        Case("syn_physical_addr", "synthesis",
             "Read back their physical address.",
             ["p1_line7a_streetnumbername", "p1_line7c_cityortown",
              "p1_line7d_state", "p1_line7e_zipcode", "p1_line7h_country"],
             "5-field gather, different cluster"),
        Case("syn_birth_info", "synthesis",
             "What do we have for where and when they were born?",
             ["p1_line9_dateofbirth", "p1_line10_citytownofbirth",
              "p1_line11_countryofbirth"],
             "3-field gather across date + city + country"),
        Case("syn_parents", "synthesis",
             "What are both parents' given names?",
             ["p1_line12_mothergivenname", "p1_line13_fathergivenname"]),
        Case("syn_previous_fullname", "synthesis",
             "What was their full name on the green card?",
             ["p1_line5a_familyname", "p1_line5b_givenname", "p1_line5c_middlename"],
             "3-field gather of the previous-name cluster"),
        Case("syn_contact", "synthesis",
             "What contact details do we have for them?",
             ["p5_line3_daytimephonenumber", "p5_line5_emailaddress"]),
        Case("syn_interpreter_block", "synthesis",
             "What do we know about the interpreter?",
             ["p6_line1a_interpretersfamilyname", "p6_line1b_interpretersgivenname",
              "p6_line3d_state", "p6_line5_interpretersemailaddress"],
             "interpreter is partially filled -- gather what exists"),
        Case("syn_name_change_summary", "synthesis",
             "Did their name change, and from what to what?",
             ["p1_checkbox4", "p1_line5a_familyname", "p1_line3a_familyname"],
             "reason cross checkbox + previous + current"),
    ]

    # ===================== distant (far-apart, must relate) =====================
    C += [
        Case("dist_mailing_vs_physical", "distant",
             "Is their mailing address the same as their physical address?",
             ["p1_line6b_streetnumbername", "p1_line6d_cityortown",
              "p1_line7a_streetnumbername", "p1_line7c_cityortown"],
             "must compare two address clusters -> NO (different)"),
        Case("dist_admission_after_birth", "distant",
             "Were they admitted to the US after they were born?",
             ["p1_line9_dateofbirth", "p1_line15_dateofadmission"],
             "relate two dates far apart -> yes (2015 after 1990)"),
        Case("dist_born_abroad", "distant",
             "Were they born outside the United States?",
             ["p1_line11_countryofbirth"],
             "Nigeria != US -> yes"),
        Case("dist_same_state", "distant",
             "Do their mailing and physical addresses share a state?",
             ["p1_line6e_state", "p1_line7d_state"],
             "both Illinois -> yes, despite different cities"),
        Case("dist_interpreter_same_state", "distant",
             "Is the interpreter in the same state as the applicant's mailing address?",
             ["p6_line3d_state", "p1_line6e_state"],
             "both Illinois -> yes; fields far apart (Part 6 vs Part 1)"),
        Case("dist_name_consistency", "distant",
             "Does the family name on the card match the previous family name?",
             ["p1_line3a_familyname", "p1_line5a_familyname"],
             "Okafor != Eze -> no (consistent with name-changed=yes)"),
        Case("dist_age_at_admission", "distant",
             "Roughly how old were they when admitted?",
             ["p1_line9_dateofbirth", "p1_line15_dateofadmission"],
             "1990 -> 2015 = ~25; relate two dates"),
        Case("dist_country_birth_vs_residence", "distant",
             "Do they currently live in the country they were born in?",
             ["p1_line11_countryofbirth", "p1_line6i_country"],
             "Nigeria vs United States -> no"),
        Case("dist_full_legal_history", "distant",
             "What names has this person gone by, current and former?",
             ["p1_line3a_familyname", "p1_line3b_givenname",
              "p1_line5a_familyname", "p1_line5b_givenname", "p1_line5c_middlename"],
             "gather across current + previous clusters (distant + multi)"),
    ]

    # ===================== applicability (hidden vs empty) =====================
    C += [
        Case("app_preparer_name", "applicability",
             "Did they list a preparer's name?",
             ["p7_line1a_familyname", "p7_line1b_preparersgivenname"],
             "preparer block hidden=false -> NOT APPLICABLE (self-prepared), not 'empty'"),
        Case("app_current_middle", "applicability",
             "Have they answered their current middle name yet?",
             ["p1_line3c_middlename"],
             "applicable (shown) but EMPTY -> 'not answered yet', distinct from N/A"),
        Case("app_preparer_phone", "applicability",
             "What's the preparer's phone number?",
             ["p7_line4_preparersdaytimephonenumber"],
             "hidden -> should say not applicable, NOT invent a value"),
        Case("app_previous_name_answered", "applicability",
             "Have they given their previous name?",
             ["p1_line5a_familyname", "p1_line5b_givenname", "p1_line5c_middlename"],
             "applicable AND filled -> yes (Eze Adaeze Ngozi)"),
        Case("app_mobile_phone", "applicability",
             "Did they provide a mobile phone number?",
             ["p5_line4_mobilephonenumber"],
             "applicable but empty -> not provided"),
        Case("app_interpreter_used", "applicability",
             "Was an interpreter used?",
             ["p6_line1a_interpretersfamilyname", "p6_line1b_interpretersgivenname",
              "p5_checkbox1a"],
             "interpreter NAME fields filled -> yes; the Part 5 English-proficiency "
             "checkbox (p5_checkbox1a) is UNCHECKED, consistent with interpreter "
             "used -- the trap is inferring 'no' from the unchecked checkbox"),
        Case("app_preparer_used", "applicability",
             "Did someone else prepare this form for them?",
             ["p7_line1a_familyname"],
             "preparer block hidden -> no (self-prepared)"),
        Case("app_middle_vs_previous_middle", "applicability",
             "Do we have a middle name for them?",
             ["p1_line3c_middlename", "p1_line5c_middlename"],
             "current empty, previous filled -> nuance: yes on the green-card name"),
        Case("app_uscis_account", "applicability",
             "Did they give a USCIS online account number?",
             ["p1_line2_acctidentifier"],
             "applicable but empty -> not provided"),
    ]

    return C


if __name__ == "__main__":
    corpus = build_corpus()
    from collections import Counter

    by_tier = Counter(c.tier for c in corpus)
    print("corpus: %d cases" % len(corpus))
    for tier in ["easy", "aliasing", "ambiguous", "synthesis", "distant",
                 "applicability"]:
        print("  %-14s %d" % (tier, by_tier[tier]))
    # Sanity: every expected field id is a real schema field id.
    import json
    import os

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    schema = json.load(open(os.path.join(root, "form-kits", "i-90", "schema.json"),
                            encoding="utf-8"))
    ids = {f["id"] for f in schema["fields"]}
    bad = []
    for c in corpus:
        for fid in c.expected_field_ids:
            if fid not in ids:
                bad.append((c.case_id, fid))
    if bad:
        print("\nUNKNOWN expected field ids (FIX THESE):")
        for cid, fid in bad:
            print("  %s -> %s" % (cid, fid))
    else:
        print("\nall expected_field_ids resolve to real schema fields: OK")
    # Sanity: fixture values + shown_map keys are real ids too.
    for label, d in [("FIELD_VALUES", FIELD_VALUES), ("SHOWN_MAP", SHOWN_MAP)]:
        bk = [k for k in d if k not in ids]
        print("%s unknown keys: %s" % (label, bk if bk else "none"))
