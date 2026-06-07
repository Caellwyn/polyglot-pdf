# -*- coding: utf-8 -*-
"""Build the i-589 FormSchema (Claude hybrid arm of the bake-off).

Reads the deterministic AcroForm dump (i589_acroform.json) for EXACT widget
names + tooltips, then layers hand-recovered relationship logic (show_if,
controls_fields, copy_to, overflow_to_supplement, repeating tables) derived
from the printed conditional text captured in the /TU tooltips.

ASCII only. Emits one JSON object to i589_claude_hybrid.json.
"""
import json
import os
import re

ROOT = r"C:\Users\caell\code_projects\polyglot-pdf\.claude\worktrees\hopeful-raman-e69ea8"
ACRO = os.path.join(ROOT, "scripts", "bakeoff", "outputs", "i589_acroform.json")
OUT = os.path.join(ROOT, "scripts", "bakeoff", "outputs", "i589_claude_hybrid.json")

with open(ACRO, "r", encoding="utf-8") as fh:
    acro = json.load(fh)

# Map exact widget name -> acro field record (each acro "field" is one logical
# widget here; consolidation of radio/checkbox sets is done by us below).
by_name = {f["name"]: f for f in acro["fields"]}


def w(name):
    """Fetch the acro record for an exact widget name; raise if missing."""
    if name not in by_name:
        raise KeyError("missing widget: " + name)
    return by_name[name]


def page_of(name):
    return w(name)["widgets"][0]["rect"]["page"]


def rect_of(name):
    r = w(name)["widgets"][0]["rect"]
    return {"page": r["page"], "x": r["x"], "y": r["y"],
            "width": r["width"], "height": r["height"]}


def maxlen_of(name):
    wd = w(name)["widgets"][0]
    return wd.get("max_length")


def tu_of(name):
    return w(name)["widgets"][0].get("tu", "")


fields = []          # list of FIELD dicts
sections = []        # list of section dicts
used_widgets = set()  # exact widget names we have consumed

DATE_PATTERN = r"^(0[1-9]|1[0-2])/(0[1-9]|[12]\\d|3[01])/\\d{4}$"
MMYY_PATTERN = r"^(0[1-9]|1[0-2])/\\d{4}$"


def add_text(fid, name, label, spoken, section_id, *, ftype="text",
             required=False, pattern=None, multiline=False, read_only=False,
             max_length=None, extra=None):
    used_widgets.add(name)
    fobj = {
        "id": fid,
        "name": label,
        "spoken_name": spoken,
        "type": ftype,
        "section_id": section_id,
        "pdf_field_name": name,
        "pdf_position": rect_of(name),
    }
    val = {"required": required}
    if pattern:
        val["pattern"] = pattern
    fobj["validation"] = val
    ml = max_length if max_length is not None else maxlen_of(name)
    if ml:
        fobj["max_length"] = ml
    if multiline:
        fobj["multiline"] = True
    if read_only:
        fobj["read_only"] = True
    if extra:
        fobj.update(extra)
    fields.append(fobj)
    return fobj


def add_choice(fid, label, spoken, section_id, options, *, ftype="radio",
               required=False, extra=None):
    for o in options:
        if o.get("pdf_field_name"):
            used_widgets.add(o["pdf_field_name"])
    # anchor position on first option widget
    pos = None
    for o in options:
        if o.get("pdf_field_name") and o["pdf_field_name"] in by_name:
            pos = rect_of(o["pdf_field_name"])
            break
    fobj = {
        "id": fid,
        "name": label,
        "spoken_name": spoken,
        "type": ftype,
        "section_id": section_id,
        "options": options,
        "validation": {"required": required},
    }
    if pos:
        fobj["pdf_position"] = pos
    if extra:
        fobj.update(extra)
    fields.append(fobj)
    return fobj


def add_checkbox(fid, name, label, spoken, section_id, on_value, *,
                 required=False, extra=None):
    used_widgets.add(name)
    fobj = {
        "id": fid,
        "name": label,
        "spoken_name": spoken,
        "type": "checkbox",
        "section_id": section_id,
        "pdf_field_name": name,
        "pdf_position": rect_of(name),
        "validation": {"required": required},
        "options": [{"value": on_value, "label": label, "pdf_field_name": name}],
    }
    if extra:
        fobj.update(extra)
    fields.append(fobj)
    return fobj


P0 = "form1[0].#subform[0]."
P1 = "form1[0].#subform[1]."
P1S = "form1[0].#subform[1].NotMarried[0]."
P3 = "form1[0].#subform[3]."
P4 = "form1[0].#subform[4]."
P5 = "form1[0].#subform[5].#subform[6]."
P7 = "form1[0].#subform[7]."
P8 = "form1[0].#subform[8]."
P9 = "form1[0].#subform[9]."
P10 = "form1[0].#subform[10]."
P11 = "form1[0].#subform[11]."
SA = "form1[0].#subform[12]."
SB = "form1[0].#subform[13]."

# ---------------------------------------------------------------------------
# PART A.I -- Information About You (page 0)
# ---------------------------------------------------------------------------
SEC_AI = "sec_a1_about_you"
add_text("a1_anumber", P0 + "PtAILine1_ANumber[0]",
         "Alien Registration Number (A-Number), if any", "A number", SEC_AI,
         pattern=r"^\\d{1,9}$")
add_text("a1_ssn", P0 + "TextField1[0]",
         "U.S. Social Security Number, if any", "Social Security number", SEC_AI)
add_text("a1_uscis_acct", P0 + "TextField1[8]",
         "USCIS Online Account Number, if any", "USCIS account number", SEC_AI)
add_text("a1_last_name", P0 + "PtAILine4_LastName[0]",
         "Complete Last Name", "last name", SEC_AI, required=True,
         extra={"copy_to": ["d_print_name"]})
add_text("a1_first_name", P0 + "PtAILine5_FirstName[0]",
         "First Name", "first name", SEC_AI, required=True)
add_text("a1_middle_name", P0 + "PtAILine6_MiddleName[0]",
         "Middle Name", "middle name", SEC_AI)
add_text("a1_other_names", P0 + "TextField1[1]",
         "Other names used (include maiden name and aliases)", "other names",
         SEC_AI)
# Item 8 -- residence in the U.S.
add_text("a1_res_street", P0 + "PtAILine8_StreetNumandName[0]",
         "Residence in the U.S.: Street Number and Name", "street", SEC_AI)
add_text("a1_res_apt", P0 + "PtAILine8_AptNumber[0]",
         "Residence: Apartment Number", "apartment", SEC_AI)
add_text("a1_res_city", P0 + "TextField1[2]", "Residence: City", "city", SEC_AI)
add_text("a1_res_state", P0 + "PtAILine8_State[0]", "Residence: State", "state",
         SEC_AI)
add_text("a1_res_zip", P0 + "PtAILine8_Zipcode[0]", "Residence: Zip Code", "zip",
         SEC_AI, pattern=r"^\\d{5}$")
add_text("a1_res_areacode", P0 + "PtAILine8_AreaCode[0]",
         "Residence: Telephone Area Code", "area code", SEC_AI)
add_text("a1_res_phone", P0 + "PtAILine8_TelephoneNumber[0]",
         "Residence: Telephone Number", "phone", SEC_AI)
# Item 9 -- mailing address (if different)
add_text("a1_mail_incareof", P0 + "PtAILine9_InCareOf[0]",
         "Mailing Address: In Care Of Name, if applicable", "in care of", SEC_AI)
add_text("a1_mail_street", P0 + "PtAILine9_StreetNumandName[0]",
         "Mailing Address (if different from residence): Street Number and Name",
         "mailing street", SEC_AI)
add_text("a1_mail_apt", P0 + "PtAILine9_AptNumber[0]",
         "Mailing Address: Apartment Number", "mailing apartment", SEC_AI)
add_text("a1_mail_city", P0 + "PtAILine9_City[0]", "Mailing Address: City",
         "mailing city", SEC_AI)
add_text("a1_mail_state", P0 + "PtAILine9_State[0]", "Mailing Address: State",
         "mailing state", SEC_AI)
add_text("a1_mail_zip", P0 + "PtAILine9_ZipCode[0]", "Mailing Address: Zip Code",
         "mailing zip", SEC_AI, pattern=r"^\\d{5}$")
add_text("a1_mail_areacode", P0 + "PtAILine9_AreaCode[0]",
         "Mailing Address: Telephone Area Code", "mailing area code", SEC_AI)
add_text("a1_mail_phone", P0 + "PtAILine9_TelephoneNumbe[0]",
         "Mailing Address: Telephone Number", "mailing phone", SEC_AI)
# Item 10 sex
add_choice("a1_sex", "Sex", "sex", SEC_AI, [
    {"value": "M", "label": "Male", "pdf_field_name": P0 + "PartALine9Sex[0]"},
    {"value": "F", "label": "Female", "pdf_field_name": P0 + "PartALine9Sex[1]"},
], required=True)
# Item 11 marital status
add_choice("a1_marital", "Marital Status", "marital status", SEC_AI, [
    {"value": "S", "label": "Single", "pdf_field_name": P0 + "Marital[0]"},
    {"value": "M", "label": "Married", "pdf_field_name": P0 + "Marital[1]"},
    {"value": "D", "label": "Divorced", "pdf_field_name": P0 + "Marital[2]"},
    {"value": "W", "label": "Widowed", "pdf_field_name": P0 + "Marital[3]"},
], required=True,
   extra={"controls_fields": ["a2_spouse_anumber"],
          "conditional_behavior": {
              "note": "If Married, complete Your Spouse block in Part A.II; "
                      "otherwise check 'I am not married' and skip to Your Children."}})
# 12 DOB, 13 city/country birth, 14 nationality, 15 nationality at birth,
# 16 race, 17 religion
add_text("a1_dob", P0 + "DateTimeField1[0]", "Date of Birth", "date of birth",
         SEC_AI, ftype="date", required=True, pattern=DATE_PATTERN)
add_text("a1_birth_city_country", P0 + "TextField1[4]",
         "City and Country of Birth", "place of birth", SEC_AI)
add_text("a1_nationality", P0 + "TextField1[3]",
         "Present Nationality (Citizenship)", "nationality", SEC_AI)
add_text("a1_nationality_birth", P0 + "TextField1[5]", "Nationality at Birth",
         "nationality at birth", SEC_AI)
add_text("a1_race", P0 + "TextField1[6]", "Race, Ethnic or Tribal Group", "race",
         SEC_AI)
add_text("a1_religion", P0 + "TextField1[7]", "Religion", "religion", SEC_AI)
# Item 18 immigration court status A/B/C
add_choice("a1_court_status", "Immigration Court proceedings status (A-C)",
           "court status", SEC_AI, [
    {"value": "A", "label": "I have never been in Immigration Court proceedings",
     "pdf_field_name": P0 + "CheckBox3[0]"},
    {"value": "B", "label": "I am now in Immigration Court proceedings",
     "pdf_field_name": P0 + "CheckBox3[2]"},
    {"value": "C", "label": "I am not now in Immigration Court proceedings, but I have been in the past",
     "pdf_field_name": P0 + "CheckBox3[1]"},
], required=True)
# Item 19 A/B/C
add_text("a1_last_left_date", P0 + "DateTimeField6[0]",
         "When did you last leave your country? (Date)", "date you last left",
         SEC_AI, ftype="date", pattern=DATE_PATTERN)
add_text("a1_i94", P0 + "TextField3[0]", "Current I-94 Number, if any",
         "I-94 number", SEC_AI)
# Item 19.C -- entries table (3 rows on form; overflow to additional sheets)
entry_widgets = {
    1: (P0 + "DateTimeField2[0]", P0 + "TextField4[0]", P0 + "TextField4[1]",
        P0 + "DateTimeField2[1]"),
    2: (P0 + "DateTimeField3[0]", P0 + "TextField4[2]", P0 + "TextField4[3]",
        None),
    3: (P0 + "DateTimeField4[0]", P0 + "TextField4[4]", P0 + "TextField4[5]",
        None),
}
entry_row_ids = []
for n, (d, place, status, exp) in entry_widgets.items():
    rid = "a1_entry%d" % n
    entry_row_ids.append(rid)
    add_text(rid + "_date", d, "U.S. Entry %d: Date" % n, "entry %d date" % n,
             SEC_AI, ftype="date", pattern=DATE_PATTERN)
    add_text(rid + "_place", place, "U.S. Entry %d: Place" % n,
             "entry %d place" % n, SEC_AI)
    add_text(rid + "_status", status, "U.S. Entry %d: Status" % n,
             "entry %d status" % n, SEC_AI)
    if exp:
        add_text(rid + "_expires", exp,
                 "U.S. Entry %d: Date Status Expires" % n,
                 "entry %d expires" % n, SEC_AI, ftype="date",
                 pattern=DATE_PATTERN)
# A table field documenting the repeating-entries structure (overflow note)
fields.append({
    "id": "a1_entries_table",
    "name": "Item 19.C: List each entry into the U.S. (most recent first)",
    "spoken_name": "U.S. entries",
    "type": "table",
    "section_id": SEC_AI,
    "validation": {"required": False},
    "columns": [
        {"id": "date", "label": "Date", "type": "date"},
        {"id": "place", "label": "Place", "type": "text"},
        {"id": "status", "label": "Status", "type": "text"},
        {"id": "expires", "label": "Date Status Expires", "type": "date"},
    ],
    "multi_entry": {"min_rows": 1, "form_rows": 3,
                    "row_field_ids": entry_row_ids,
                    "overflow": "Attach additional sheets as needed"},
})
# Item 20-22 passport / travel doc
add_text("a1_passport_country", P0 + "TextField5[0]",
         "Country that issued your last passport or travel document", "passport country",
         SEC_AI)
add_text("a1_passport_number", P0 + "TextField5[1]", "Passport Number",
         "passport number", SEC_AI)
add_text("a1_traveldoc_number", P0 + "TextField5[2]", "Travel Document Number",
         "travel document number", SEC_AI)
add_text("a1_passport_exp", P0 + "DateTimeField2[2]",
         "Passport/Travel Document Expiration Date", "passport expiration",
         SEC_AI, ftype="date", pattern=DATE_PATTERN)
# Item 23-25 language
add_text("a1_native_language", P0 + "TextField7[0]",
         "Native language (include dialect, if applicable)", "native language",
         SEC_AI)
add_choice("a1_english_fluent", "Are you fluent in English?", "English fluent",
           SEC_AI, [
    {"value": "Yes", "label": "Yes", "pdf_field_name": P0 + "CheckBox4[0]"},
    {"value": "No", "label": "No", "pdf_field_name": P0 + "CheckBox4[1]"},
])
add_text("a1_other_languages", P0 + "TextField7[1]",
         "Other languages you speak fluently", "other languages", SEC_AI)
# CAT checkbox (NOTE box, top of form)
add_checkbox("a1_cat_withholding", P0 + "CheckBox31[0]",
             "Also apply for withholding of removal under the Convention Against Torture",
             "Convention Against Torture", SEC_AI, "1")

# ---------------------------------------------------------------------------
# PART A.II -- Spouse and Children (pages 1-2)
# ---------------------------------------------------------------------------
SEC_SPOUSE = "sec_a2_spouse"
# "I am not married" gate
add_checkbox("a2_not_married", P1 + "CheckBox5[0]",
             "I am not married (skip to Your Children)", "not married",
             SEC_SPOUSE, "1",
             extra={"controls_fields": ["a2_spouse_anumber", "a2_spouse_last"],
                    "conditional_behavior": {
                        "if_checked": "Skip the Your Spouse block; proceed to Your Children."}})
SHOW_IF_MARRIED = {"field": "a2_not_married", "operator": "not_equals", "value": "1"}
add_text("a2_spouse_anumber", P1S + "PtAIILine1_ANumber[0]",
         "Spouse: Alien Registration Number (A-Number), if any", "spouse A number",
         SEC_SPOUSE, extra={"show_if": SHOW_IF_MARRIED})
add_text("a2_spouse_passport", P1S + "TextField10[1]",
         "Spouse: Passport/ID Card Number, if any", "spouse passport",
         SEC_SPOUSE, extra={"show_if": SHOW_IF_MARRIED})
add_text("a2_spouse_dob", P1S + "DateTimeField7[0]", "Spouse: Date of Birth",
         "spouse date of birth", SEC_SPOUSE, ftype="date", pattern=DATE_PATTERN,
         extra={"show_if": SHOW_IF_MARRIED})
add_text("a2_spouse_ssn", P1S + "TextField10[2]",
         "Spouse: U.S. Social Security Number, if any", "spouse SSN", SEC_SPOUSE,
         extra={"show_if": SHOW_IF_MARRIED})
add_text("a2_spouse_last", P1S + "PtAIILine5_LastName[0]",
         "Spouse: Complete Last Name", "spouse last name", SEC_SPOUSE,
         extra={"show_if": SHOW_IF_MARRIED})
add_text("a2_spouse_first", P1S + "PtAIILine6_FirstName[0]",
         "Spouse: First Name", "spouse first name", SEC_SPOUSE,
         extra={"show_if": SHOW_IF_MARRIED})
add_text("a2_spouse_middle", P1S + "PtAIILine7_MiddleName[0]",
         "Spouse: Middle Name", "spouse middle name", SEC_SPOUSE,
         extra={"show_if": SHOW_IF_MARRIED})
add_text("a2_spouse_maiden", P1S + "TextField10[3]", "Spouse: Maiden Name",
         "spouse maiden name", SEC_SPOUSE, extra={"show_if": SHOW_IF_MARRIED})
add_text("a2_spouse_marriage_date", P1S + "DateTimeField8[0]",
         "Spouse: Date of Marriage", "marriage date", SEC_SPOUSE, ftype="date",
         pattern=DATE_PATTERN, extra={"show_if": SHOW_IF_MARRIED})
add_text("a2_spouse_marriage_place", P1S + "TextField10[4]",
         "Spouse: Place of Marriage", "marriage place", SEC_SPOUSE,
         extra={"show_if": SHOW_IF_MARRIED})
add_text("a2_spouse_birth_place", P1S + "TextField10[5]",
         "Spouse: City and Country of Birth", "spouse place of birth",
         SEC_SPOUSE, extra={"show_if": SHOW_IF_MARRIED})
add_text("a2_spouse_nationality", P1S + "TextField10[0]",
         "Spouse: Nationality (Citizenship)", "spouse nationality", SEC_SPOUSE,
         extra={"show_if": SHOW_IF_MARRIED})
add_text("a2_spouse_race", P1S + "TextField10[6]",
         "Spouse: Race, Ethnic or Tribal Group", "spouse race", SEC_SPOUSE,
         extra={"show_if": SHOW_IF_MARRIED})
add_choice("a2_spouse_sex", "Spouse: Sex", "spouse sex", SEC_SPOUSE, [
    {"value": "M", "label": "Male", "pdf_field_name": P1S + "CheckBox14_Sex[0]"},
    {"value": "F", "label": "Female", "pdf_field_name": P1S + "CheckBox14_Sex[1]"},
], extra={"show_if": SHOW_IF_MARRIED})
# Item 15 -- spouse in U.S.? gates blocks 16-24
add_choice("a2_spouse_in_us", "Spouse: Is this person in the U.S.?",
           "spouse in U.S.", SEC_SPOUSE, [
    {"value": "Y", "label": "Yes (Complete Blocks 16 to 24)",
     "pdf_field_name": P1S + "PtAIILine15_CheckBox15[1]"},
    {"value": "N", "label": "No (Specify location)",
     "pdf_field_name": P1S + "PtAIILine15_CheckBox15[0]"},
], extra={"show_if": SHOW_IF_MARRIED,
          "controls_fields": ["a2_spouse_place_entry", "a2_spouse_date_entry",
                              "a2_spouse_i94", "a2_spouse_status",
                              "a2_spouse_current_status", "a2_spouse_exp_stay",
                              "a2_spouse_in_court", "a2_spouse_included"]})
add_text("a2_spouse_location", P1S + "PtAIILine15_Specify[0]",
         "Spouse: If not in U.S., location", "spouse location", SEC_SPOUSE,
         extra={"show_if": {"field": "a2_spouse_in_us", "operator": "equals",
                            "value": "N"}})
SHOW_IF_SPOUSE_US = {"field": "a2_spouse_in_us", "operator": "equals", "value": "Y"}
add_text("a2_spouse_place_entry", P1S + "PtAIILine16_PlaceofLastEntry[0]",
         "Spouse: Place of Last Entry into the U.S.", "spouse entry place",
         SEC_SPOUSE, extra={"show_if": SHOW_IF_SPOUSE_US})
add_text("a2_spouse_date_entry", P1S + "PtAIILine17_DateofLastEntry[0]",
         "Spouse: Date of Last Entry into the U.S.", "spouse entry date",
         SEC_SPOUSE, ftype="date", pattern=DATE_PATTERN,
         extra={"show_if": SHOW_IF_SPOUSE_US})
add_text("a2_spouse_i94", P1S + "PtAIILine18_I94Number[0]",
         "Spouse: I-94 Number, if any", "spouse I-94", SEC_SPOUSE,
         extra={"show_if": SHOW_IF_SPOUSE_US})
add_text("a2_spouse_status", P1S + "PtAIILine19_StatusofLastAdmission[0]",
         "Spouse: Status when Last Admitted (Visa type, if any)",
         "spouse admission status", SEC_SPOUSE,
         extra={"show_if": SHOW_IF_SPOUSE_US})
add_text("a2_spouse_current_status", P1S + "PtAIILine20_SpouseCurrentStatus[0]",
         "Spouse: Current Status", "spouse current status", SEC_SPOUSE,
         extra={"show_if": SHOW_IF_SPOUSE_US})
add_text("a2_spouse_exp_stay", P1S + "PtAIILine21_ExpDateofAuthorizedStay[0]",
         "Spouse: Expiration Date of Authorized Stay, if any", "spouse stay expiration",
         SEC_SPOUSE, ftype="date", pattern=DATE_PATTERN,
         extra={"show_if": SHOW_IF_SPOUSE_US})
add_choice("a2_spouse_in_court", "Spouse: Is your spouse in Immigration Court Proceedings?",
           "spouse in court", SEC_SPOUSE, [
    {"value": "Yes", "label": "Yes", "pdf_field_name": P1S + "PtAIILine22_Yes[0]"},
    {"value": "No", "label": "No", "pdf_field_name": P1S + "PtAIILine22_No[0]"},
], extra={"show_if": SHOW_IF_SPOUSE_US})
add_choice("a2_spouse_included", "Spouse: Is your spouse to be included in this application?",
           "spouse included", SEC_SPOUSE, [
    {"value": "Y", "label": "Yes", "pdf_field_name": P1S + "PtAIILine24_Yes[0]"},
    {"value": "N", "label": "No", "pdf_field_name": P1S + "PtAIILine24_No[0]"},
], extra={"show_if": SHOW_IF_SPOUSE_US})
add_text("a2_spouse_prev_arrival", P1S + "PtAIILine23_PreviousArrivalDate[0]",
         "Spouse: If previously in the U.S., date of previous arrival",
         "spouse previous arrival", SEC_SPOUSE, ftype="date",
         pattern=DATE_PATTERN, extra={"show_if": SHOW_IF_MARRIED})

# ---- Children ----
SEC_CHILD = "sec_a2_children"
add_choice("a2_has_children", "Do you have children?", "have children",
           SEC_CHILD, [
    {"value": "N", "label": "I have children",
     "pdf_field_name": P1 + "ChildrenCheckbox[0]"},
    {"value": "Y", "label": "I do not have any children (Skip to Part A.III)",
     "pdf_field_name": P1 + "ChildrenCheckbox[1]"},
], extra={"controls_fields": ["a2_total_children"],
          "conditional_behavior": {
              "if_no_children": "Skip to Part A.III, Information about your background."}})
add_text("a2_total_children", P1 + "TotalChild[0]",
         "Total Number of Children", "number of children", SEC_CHILD,
         read_only=True,
         extra={"overflow_to_supplement": "supp_a",
                "show_if": {"field": "a2_has_children", "operator": "equals",
                            "value": "N"},
                "conditional_behavior": {
                    "note": "Use Form I-589 Supplement A or attach sheets if more than four children."}})

# Child rows 1-4 (page 1 for child 1, page 2 for children 2-4).
# Field name maps differ per child; build explicitly.
child_widget_maps = {
    1: {
        "alien": P1 + "ChildAlien1[0]", "passport": P1 + "ChildPassport1[0]",
        "marital": P1 + "ChildMarital1[0]", "ssn": P1 + "ChildSSN1[0]",
        "last": P1 + "ChildLast1[0]", "first": P1 + "ChildFirst1[0]",
        "middle": P1 + "ChildMiddle1[0]", "dob": P1 + "ChildDOB1[0]",
        "city": P1 + "ChildCity1[0]", "nat": P1 + "ChildNat1[0]",
        "race": P1 + "ChildRace1[0]",
        "sex_m": P1 + "CheckBox12_Sex[0]", "sex_f": P1 + "CheckBox12_Sex[1]",
        "in_us_y": P1 + "CheckBox17[0]", "in_us_n": P1 + "CheckBox17[1]",
        "location": P1 + "PtAIILine13_Specify[0]",
        "place_entry": P1 + "PtAIILine14_PlaceofLastEntry[0]",
        "date_entry": P1 + "PtAIILine15_ExpirationDate[0]",
        "i94": P1 + "PtAIILine16_I94Number[0]",
        "status": P1 + "PtAIILine17_StatusofLastAdmission[0]",
        "current_status": P1 + "PtAIILine18_CurrentStatusofChild[0]",
        "exp_stay": P1 + "PtAIILine19_ExpDateofAuthorizedStay[0]",
        "court_y": P1 + "PtAIILine20_Yes[0]", "court_n": P1 + "PtAIILine20_No[0]",
        "incl_y": P1 + "PtAIILine21_Yes[0]", "incl_n": P1 + "PtAIILine21_No[0]",
    },
    2: {
        "alien": P3 + "ChildAlien2[0]", "passport": P3 + "ChildPassport2[0]",
        "marital": P3 + "ChildMarital2[0]", "ssn": P3 + "ChildSSN2[0]",
        "last": P3 + "ChildLast2[0]", "first": P3 + "ChildFirst2[0]",
        "middle": P3 + "ChildMiddle2[0]", "dob": P3 + "ChildDOB2[0]",
        "city": P3 + "ChildCity2[0]", "nat": P3 + "ChildNat2[0]",
        "race": P3 + "ChildRace2[0]",
        "sex_m": P3 + "CheckBox26_Sex[0]", "sex_f": P3 + "CheckBox26_Sex[1]",
        "in_us_y": P3 + "CheckBox27[0]", "in_us_n": P3 + "CheckBox27[1]",
        "location": P3 + "PtAIILine13_Specify2[0]",
        "place_entry": P3 + "PtAIILine14_PlaceofLastEntry2[0]",
        "date_entry": P3 + "PtAIILine15_DateofLastEntry2[0]",
        "i94": P3 + "PtAIILine16_I94Number2[0]",
        "status": P3 + "PtAIILine17_StatusofLastAdmission2[0]",
        "current_status": P3 + "PtAIILine18_ChildCurrentStatus2[0]",
        "exp_stay": P3 + "PtAIILine19_ExpDateofAuthorizedStay2[0]",
        "court_y": P3 + "PtAIILine20_Yes2[0]", "court_n": P3 + "PtAIILine20_No2[0]",
        "incl_y": P3 + "PtAIILine21_Yes2[0]", "incl_n": P3 + "PtAIILine21_No2[0]",
    },
    3: {
        "alien": P3 + "ChildAlien3[0]", "passport": P3 + "ChildPassport3[0]",
        "marital": P3 + "ChildMarital3[0]", "ssn": P3 + "ChildSSN3[0]",
        "last": P3 + "ChildLast3[0]", "first": P3 + "ChildFirst3[0]",
        "middle": P3 + "ChildMiddle3[0]", "dob": P3 + "ChildDOB3[0]",
        "city": P3 + "ChildCity3[0]", "nat": P3 + "ChildNat3[0]",
        "race": P3 + "ChildRace3[0]",
        "sex_m": P3 + "CheckBox36_Sex[0]", "sex_f": P3 + "CheckBox36_Sex[1]",
        "in_us_y": P3 + "CheckBox37[0]", "in_us_n": P3 + "CheckBox37[1]",
        "location": P3 + "PtAIILine13_Specify3[0]",
        "place_entry": P3 + "PtAIILine14_PlaceofLastEntry3[0]",
        "date_entry": P3 + "PtAIILine15_DateofLastEntry3[0]",
        "i94": P3 + "PtAIILine16_I94Number3[0]",
        "status": P3 + "PtAIILine17_StatusofLastAdmission3[0]",
        "current_status": P3 + "PtAIILine18_ChildCurrentStatus3[0]",
        "exp_stay": P3 + "PtAIILine19_ExpDateofAuthorizedStay3[0]",
        "court_y": P3 + "PtAIILine20_Yes3[0]", "court_n": P3 + "PtAIILine20_No3[0]",
        "incl_y": P3 + "PtAIILine21_Yes3[0]", "incl_n": P3 + "PtAIILine21_No3[0]",
    },
    4: {
        "alien": P3 + "ChildAlien4[0]", "passport": P3 + "ChildPassport4[0]",
        "marital": P3 + "ChildMarital4[0]", "ssn": P3 + "ChildSSN4[0]",
        "last": P3 + "ChildLast4[0]", "first": P3 + "ChildFirst4[0]",
        "middle": P3 + "ChildMiddle4[0]", "dob": P3 + "ChildDOB4[0]",
        "city": P3 + "ChildCity4[0]", "nat": P3 + "ChildNat4[0]",
        "race": P3 + "ChildRace4[0]",
        "sex_m": P3 + "CheckBox46_Sex[0]", "sex_f": P3 + "CheckBox46_Sex[1]",
        "in_us_y": P3 + "CheckBox47[0]", "in_us_n": P3 + "CheckBox47[1]",
        "location": P3 + "PtAIILine13_Specify4[0]",
        "place_entry": P3 + "PtAIILine14_PlaceofLastEntry4[0]",
        "date_entry": P3 + "PtAIILine15_DateofLastEntry4[0]",
        "i94": P3 + "PtAIILine16_I94Number4[0]",
        "status": P3 + "PtAIILine17_StatusofLastAdmission4[0]",
        "current_status": P3 + "PtAIILine18_ChildCurrentStatus4[0]",
        "exp_stay": P3 + "PtAIILine19_ExpDateofAuthorizedStay4[0]",
        "court_y": P3 + "PtAIILine20_Yes4[0]", "court_n": P3 + "PtAIILine20_No4[0]",
        "incl_y": P3 + "PtAIILine21_Yes4[0]", "incl_n": P3 + "PtAIILine21_No4[0]",
    },
}

child_row_field_ids = []
for n, m in child_widget_maps.items():
    pre = "a2_child%d_" % n
    add_text(pre + "alien", m["alien"], "Child %d: A-Number, if any" % n,
             "child %d A number" % n, SEC_CHILD)
    add_text(pre + "passport", m["passport"],
             "Child %d: Passport/ID Card Number" % n, "child %d passport" % n,
             SEC_CHILD)
    add_text(pre + "marital", m["marital"], "Child %d: Marital Status" % n,
             "child %d marital status" % n, SEC_CHILD)
    add_text(pre + "ssn", m["ssn"], "Child %d: U.S. Social Security Number" % n,
             "child %d SSN" % n, SEC_CHILD)
    add_text(pre + "last", m["last"], "Child %d: Complete Last Name" % n,
             "child %d last name" % n, SEC_CHILD)
    add_text(pre + "first", m["first"], "Child %d: First Name" % n,
             "child %d first name" % n, SEC_CHILD)
    add_text(pre + "middle", m["middle"], "Child %d: Middle Name" % n,
             "child %d middle name" % n, SEC_CHILD)
    add_text(pre + "dob", m["dob"], "Child %d: Date of Birth" % n,
             "child %d date of birth" % n, SEC_CHILD, ftype="date",
             pattern=DATE_PATTERN)
    add_text(pre + "city", m["city"], "Child %d: City and Country of Birth" % n,
             "child %d place of birth" % n, SEC_CHILD)
    add_text(pre + "nat", m["nat"], "Child %d: Nationality (Citizenship)" % n,
             "child %d nationality" % n, SEC_CHILD)
    add_text(pre + "race", m["race"],
             "Child %d: Race, Ethnic or Tribal Group" % n, "child %d race" % n,
             SEC_CHILD)
    add_choice(pre + "sex", "Child %d: Sex" % n, "child %d sex" % n, SEC_CHILD, [
        {"value": "M", "label": "Male", "pdf_field_name": m["sex_m"]},
        {"value": "F", "label": "Female", "pdf_field_name": m["sex_f"]},
    ])
    in_us_id = pre + "in_us"
    add_choice(in_us_id, "Child %d: Is this child in the U.S.?" % n,
               "child %d in U.S." % n, SEC_CHILD, [
        {"value": "Y", "label": "Yes (Complete Blocks 14 to 21)",
         "pdf_field_name": m["in_us_y"]},
        {"value": "N", "label": "No (Specify location)",
         "pdf_field_name": m["in_us_n"]},
    ], extra={"controls_fields": [pre + "place_entry", pre + "date_entry",
                                  pre + "i94", pre + "status",
                                  pre + "current_status", pre + "exp_stay",
                                  pre + "court", pre + "included"]})
    add_text(pre + "location", m["location"],
             "Child %d: If not in U.S., location" % n, "child %d location" % n,
             SEC_CHILD, extra={"show_if": {"field": in_us_id,
                                           "operator": "equals", "value": "N"}})
    show_us = {"field": in_us_id, "operator": "equals", "value": "Y"}
    add_text(pre + "place_entry", m["place_entry"],
             "Child %d: Place of Last Entry into the U.S." % n,
             "child %d entry place" % n, SEC_CHILD, extra={"show_if": show_us})
    add_text(pre + "date_entry", m["date_entry"],
             "Child %d: Date of Last Entry into the U.S." % n,
             "child %d entry date" % n, SEC_CHILD, ftype="date",
             pattern=DATE_PATTERN, extra={"show_if": show_us})
    add_text(pre + "i94", m["i94"], "Child %d: I-94 Number, if any" % n,
             "child %d I-94" % n, SEC_CHILD, extra={"show_if": show_us})
    add_text(pre + "status", m["status"],
             "Child %d: Status when Last Admitted" % n,
             "child %d admission status" % n, SEC_CHILD,
             extra={"show_if": show_us})
    add_text(pre + "current_status", m["current_status"],
             "Child %d: Current Status" % n, "child %d current status" % n,
             SEC_CHILD, extra={"show_if": show_us})
    add_text(pre + "exp_stay", m["exp_stay"],
             "Child %d: Expiration Date of Authorized Stay" % n,
             "child %d stay expiration" % n, SEC_CHILD, ftype="date",
             pattern=DATE_PATTERN, extra={"show_if": show_us})
    add_choice(pre + "court", "Child %d: Is your child in Immigration Court proceedings?" % n,
               "child %d in court" % n, SEC_CHILD, [
        {"value": "Yes", "label": "Yes", "pdf_field_name": m["court_y"]},
        {"value": "No", "label": "No", "pdf_field_name": m["court_n"]},
    ], extra={"show_if": show_us})
    add_choice(pre + "included", "Child %d: Is this child to be included in this application?" % n,
               "child %d included" % n, SEC_CHILD, [
        {"value": "Y", "label": "Yes", "pdf_field_name": m["incl_y"]},
        {"value": "N", "label": "No", "pdf_field_name": m["incl_n"]},
    ], extra={"show_if": show_us})
    child_row_field_ids.append(pre.rstrip("_"))

# Children repeating-table descriptor with overflow to Supplement A
fields.append({
    "id": "a2_children_table",
    "name": "Your Children: list all children regardless of age, location, or marital status",
    "spoken_name": "children",
    "type": "table",
    "section_id": SEC_CHILD,
    "validation": {"required": False},
    "columns": [
        {"id": "alien", "label": "A-Number", "type": "text"},
        {"id": "passport", "label": "Passport/ID Number", "type": "text"},
        {"id": "marital", "label": "Marital Status", "type": "text"},
        {"id": "ssn", "label": "SSN", "type": "text"},
        {"id": "last", "label": "Last Name", "type": "text"},
        {"id": "first", "label": "First Name", "type": "text"},
        {"id": "middle", "label": "Middle Name", "type": "text"},
        {"id": "dob", "label": "Date of Birth", "type": "date"},
        {"id": "city", "label": "City/Country of Birth", "type": "text"},
        {"id": "nat", "label": "Nationality", "type": "text"},
        {"id": "race", "label": "Race/Ethnic/Tribal", "type": "text"},
        {"id": "sex", "label": "Sex", "type": "radio"},
        {"id": "in_us", "label": "In U.S.?", "type": "radio"},
        {"id": "location", "label": "Location if not in U.S.", "type": "text"},
        {"id": "place_entry", "label": "Place of Last Entry", "type": "text"},
        {"id": "date_entry", "label": "Date of Last Entry", "type": "date"},
        {"id": "i94", "label": "I-94 Number", "type": "text"},
        {"id": "status", "label": "Status when Last Admitted", "type": "text"},
        {"id": "current_status", "label": "Current Status", "type": "text"},
        {"id": "exp_stay", "label": "Exp. of Authorized Stay", "type": "date"},
        {"id": "court", "label": "In Immigration Court?", "type": "radio"},
        {"id": "included", "label": "Included in application?", "type": "radio"},
    ],
    "multi_entry": {"min_rows": 0, "form_rows": 4,
                    "row_field_ids": child_row_field_ids,
                    "count_field": "a2_total_children"},
    "overflow_to_supplement": "supp_a",
    "show_if": {"field": "a2_has_children", "operator": "equals", "value": "N"},
})

# ---------------------------------------------------------------------------
# PART A.III -- Background (page 3): residences, education, employment,
# parents/siblings. All NOTE: Use Supplement B for overflow.
# ---------------------------------------------------------------------------
SEC_BG = "sec_a3_background"
# Item 1 -- last address before coming to U.S. (2-line street + city/dept/country + from/to)
add_text("a3_last_addr_street1", P4 + "TextField13[0]",
         "Item 1: Last address before coming to U.S. - Number and Street (line 1)",
         "last address street", SEC_BG, extra={"overflow_to_supplement": "supp_b"})
add_text("a3_last_addr_street2", P4 + "TextField13[1]",
         "Item 1: Last address - Number and Street (line 2)",
         "last address street line 2", SEC_BG)
add_text("a3_last_addr_city", P4 + "TextField13[2]", "Item 1: City/Town",
         "last address city", SEC_BG)
add_text("a3_last_addr_dept", P4 + "TextField13[4]",
         "Item 1: Department, Province or State", "last address province",
         SEC_BG)
add_text("a3_last_addr_country", P4 + "TextField13[6]", "Item 1: Country",
         "last address country", SEC_BG)
add_text("a3_last_addr_from", P4 + "DateTimeField21[0]", "Item 1: From (MM/YYYY)",
         "from date", SEC_BG, ftype="date", pattern=MMYY_PATTERN)
add_text("a3_last_addr_to", P4 + "DateTimeField20[0]", "Item 1: To (MM/YYYY)",
         "to date", SEC_BG, ftype="date", pattern=MMYY_PATTERN)
# the duplicate widgets (TextField13[3,5,7], DateTimeField22/23) are second
# physical line cells; capture them too so nothing is dropped.
add_text("a3_last_addr_city2", P4 + "TextField13[3]", "Item 1: City/Town (cell 2)",
         "last address city cell 2", SEC_BG)
add_text("a3_last_addr_dept2", P4 + "TextField13[5]",
         "Item 1: Department, Province or State (cell 2)", "province cell 2", SEC_BG)
add_text("a3_last_addr_country2", P4 + "TextField13[7]", "Item 1: Country (cell 2)",
         "country cell 2", SEC_BG)
add_text("a3_last_addr_from2", P4 + "DateTimeField22[0]", "Item 1: From (cell 2)",
         "from cell 2", SEC_BG, ftype="date", pattern=MMYY_PATTERN)
add_text("a3_last_addr_to2", P4 + "DateTimeField23[0]", "Item 1: To (cell 2)",
         "to cell 2", SEC_BG, ftype="date", pattern=MMYY_PATTERN)

# Item 2 -- residences past 5 years (5 rows). Build from the TextField13 indices.
res_rows = {
    1: (P4 + "TextField13[8]", P4 + "TextField13[10]", P4 + "TextField13[12]",
        P4 + "TextField13[14]", P4 + "DateTimeField24[0]", P4 + "DateTimeField26[0]"),
    2: (P4 + "TextField13[9]", P4 + "TextField13[11]", P4 + "TextField13[13]",
        P4 + "TextField13[15]", P4 + "DateTimeField25[0]", P4 + "DateTimeField27[0]"),
    3: (P4 + "TextField13[16]", P4 + "TextField13[17]", P4 + "TextField13[18]",
        P4 + "TextField13[19]", P4 + "DateTimeField28[0]", P4 + "DateTimeField29[0]"),
    4: (P4 + "TextField13[20]", P4 + "TextField13[21]", P4 + "TextField13[22]",
        P4 + "TextField13[23]", P4 + "DateTimeField30[0]", P4 + "DateTimeField31[0]"),
    5: (P4 + "TextField13[24]", P4 + "TextField13[25]", P4 + "TextField13[26]",
        P4 + "TextField13[27]", P4 + "DateTimeField32[0]", P4 + "DateTimeField33[0]"),
}
res_row_ids = []
for n, (st, city, dept, country, frm, to) in res_rows.items():
    rid = "a3_res%d" % n
    res_row_ids.append(rid)
    add_text(rid + "_street", st, "Residence %d: Number and Street" % n,
             "residence %d street" % n, SEC_BG)
    add_text(rid + "_city", city, "Residence %d: City/Town" % n,
             "residence %d city" % n, SEC_BG)
    add_text(rid + "_dept", dept, "Residence %d: Department/Province/State" % n,
             "residence %d province" % n, SEC_BG)
    add_text(rid + "_country", country, "Residence %d: Country" % n,
             "residence %d country" % n, SEC_BG)
    add_text(rid + "_from", frm, "Residence %d: From (MM/YYYY)" % n,
             "residence %d from" % n, SEC_BG, ftype="date", pattern=MMYY_PATTERN)
    add_text(rid + "_to", to, "Residence %d: To (MM/YYYY)" % n,
             "residence %d to" % n, SEC_BG, ftype="date", pattern=MMYY_PATTERN)
fields.append({
    "id": "a3_residences_table",
    "name": "Item 2: Residences during the past 5 years (present address first)",
    "spoken_name": "residences",
    "type": "table",
    "section_id": SEC_BG,
    "validation": {"required": False},
    "columns": [
        {"id": "street", "label": "Number and Street", "type": "text"},
        {"id": "city", "label": "City/Town", "type": "text"},
        {"id": "dept", "label": "Dept/Province/State", "type": "text"},
        {"id": "country", "label": "Country", "type": "text"},
        {"id": "from", "label": "From", "type": "date"},
        {"id": "to", "label": "To", "type": "date"},
    ],
    "multi_entry": {"min_rows": 1, "form_rows": 5, "row_field_ids": res_row_ids},
    "overflow_to_supplement": "supp_b",
})

# Item 3 -- education (4 rows). school name, type, location, from/to.
edu_rows = {
    1: (P4 + "TextField13[28]", P4 + "TextField13[30]", P4 + "TextField13[32]",
        P4 + "DateTimeField41[0]", P4 + "DateTimeField40[0]"),
    2: (P4 + "TextField13[29]", P4 + "TextField13[31]", P4 + "TextField13[33]",
        P4 + "DateTimeField38[0]", P4 + "DateTimeField39[0]"),
    3: (P4 + "TextField13[34]", P4 + "TextField13[35]", P4 + "TextField13[36]",
        P4 + "DateTimeField37[0]", P4 + "DateTimeField36[0]"),
    4: (P4 + "TextField13[37]", P4 + "TextField13[38]", P4 + "TextField13[39]",
        P4 + "DateTimeField34[0]", P4 + "DateTimeField35[0]"),
}
edu_row_ids = []
for n, (school, sct, loc, frm, to) in edu_rows.items():
    rid = "a3_edu%d" % n
    edu_row_ids.append(rid)
    add_text(rid + "_school", school, "Education %d: Name of School" % n,
             "school %d name" % n, SEC_BG)
    add_text(rid + "_type", sct, "Education %d: Type of School" % n,
             "school %d type" % n, SEC_BG)
    add_text(rid + "_location", loc, "Education %d: Location (Address)" % n,
             "school %d location" % n, SEC_BG)
    add_text(rid + "_from", frm, "Education %d: Attended From (MM/YYYY)" % n,
             "school %d from" % n, SEC_BG, ftype="date", pattern=MMYY_PATTERN)
    add_text(rid + "_to", to, "Education %d: Attended To (MM/YYYY)" % n,
             "school %d to" % n, SEC_BG, ftype="date", pattern=MMYY_PATTERN)
fields.append({
    "id": "a3_education_table",
    "name": "Item 3: Education (most recent first)",
    "spoken_name": "education",
    "type": "table",
    "section_id": SEC_BG,
    "validation": {"required": False},
    "columns": [
        {"id": "school", "label": "Name of School", "type": "text"},
        {"id": "type", "label": "Type of School", "type": "text"},
        {"id": "location", "label": "Location", "type": "text"},
        {"id": "from", "label": "From", "type": "date"},
        {"id": "to", "label": "To", "type": "date"},
    ],
    "multi_entry": {"min_rows": 0, "form_rows": 4, "row_field_ids": edu_row_ids},
    "overflow_to_supplement": "supp_b",
})

# Item 4 -- employment (3 rows). employer name/addr, occupation, from/to.
emp_rows = {
    1: (P4 + "TextField13[40]", P4 + "TextField13[42]", P4 + "DateTimeField42[0]",
        P4 + "DateTimeField44[0]"),
    2: (P4 + "TextField13[41]", P4 + "TextField13[43]", P4 + "DateTimeField43[0]",
        P4 + "DateTimeField45[0]"),
    3: (P4 + "TextField13[44]", P4 + "TextField13[45]", P4 + "DateTimeField46[0]",
        P4 + "DateTimeField47[0]"),
}
emp_row_ids = []
for n, (emp, occ, frm, to) in emp_rows.items():
    rid = "a3_emp%d" % n
    emp_row_ids.append(rid)
    add_text(rid + "_employer", emp, "Employment %d: Name and Address of Employer" % n,
             "employer %d" % n, SEC_BG)
    add_text(rid + "_occupation", occ, "Employment %d: Your Occupation" % n,
             "occupation %d" % n, SEC_BG)
    add_text(rid + "_from", frm, "Employment %d: From (MM/YYYY)" % n,
             "employment %d from" % n, SEC_BG, ftype="date", pattern=MMYY_PATTERN)
    add_text(rid + "_to", to, "Employment %d: To (MM/YYYY)" % n,
             "employment %d to" % n, SEC_BG, ftype="date", pattern=MMYY_PATTERN)
fields.append({
    "id": "a3_employment_table",
    "name": "Item 4: Employment during the past 5 years (present employment first)",
    "spoken_name": "employment",
    "type": "table",
    "section_id": SEC_BG,
    "validation": {"required": False},
    "columns": [
        {"id": "employer", "label": "Name/Address of Employer", "type": "text"},
        {"id": "occupation", "label": "Occupation", "type": "text"},
        {"id": "from", "label": "From", "type": "date"},
        {"id": "to", "label": "To", "type": "date"},
    ],
    "multi_entry": {"min_rows": 0, "form_rows": 3, "row_field_ids": emp_row_ids},
    "overflow_to_supplement": "supp_b",
})

# Item 5 -- parents and siblings (mother, father, siblings 1-4). Each: full name,
# city/country birth, current location, deceased checkbox.
fam_rows = {
    "mother": (P4 + "TextField13[46]", P4 + "TextField13[49]",
               P4 + "TextField35[0]", P4 + "CheckBoxAIII5\\.m[0]", "Mother"),
    "father": (P4 + "TextField13[47]", P4 + "TextField13[50]",
               P4 + "TextField35[1]", P4 + "CheckBoxAIII5\\.f[0]", "Father"),
    "sib1": (P4 + "TextField13[48]", P4 + "TextField13[51]",
             P4 + "TextField35[2]", P4 + "CheckBoxAIII5\\.s1[0]", "Sibling 1"),
    "sib2": (P4 + "TextField13[52]", P4 + "TextField13[53]",
             P4 + "TextField35[3]", P4 + "CheckBoxAIII5\\.s2[0]", "Sibling 2"),
    "sib3": (P4 + "TextField13[54]", P4 + "TextField13[55]",
             P4 + "TextField35[4]", P4 + "CheckBoxAIII5\\.s3[0]", "Sibling 3"),
    "sib4": (P4 + "TextField13[56]", P4 + "TextField13[57]",
             P4 + "TextField35[5]", P4 + "CheckBoxAIII5\\.s4[0]", "Sibling 4"),
}
fam_row_ids = []
for key, (name_w, birth_w, loc_w, dec_w, label) in fam_rows.items():
    rid = "a3_fam_" + key
    fam_row_ids.append(rid)
    add_text(rid + "_name", name_w, "%s: Full Name" % label,
             "%s name" % label.lower(), SEC_BG)
    add_text(rid + "_birth", birth_w, "%s: City/Town and Country of Birth" % label,
             "%s birth place" % label.lower(), SEC_BG)
    add_text(rid + "_location", loc_w, "%s: Current Location" % label,
             "%s location" % label.lower(), SEC_BG)
    add_checkbox(rid + "_deceased", dec_w, "%s: Deceased" % label,
                 "%s deceased" % label.lower(), SEC_BG, "1")
fields.append({
    "id": "a3_family_table",
    "name": "Item 5: Parents and siblings (check the box if the person is deceased)",
    "spoken_name": "parents and siblings",
    "type": "table",
    "section_id": SEC_BG,
    "validation": {"required": False},
    "columns": [
        {"id": "name", "label": "Full Name", "type": "text"},
        {"id": "birth", "label": "City/Country of Birth", "type": "text"},
        {"id": "location", "label": "Current Location", "type": "text"},
        {"id": "deceased", "label": "Deceased", "type": "checkbox"},
    ],
    "multi_entry": {"min_rows": 2, "form_rows": 6, "fixed_roles": True,
                    "row_field_ids": fam_row_ids},
    "overflow_to_supplement": "supp_b",
})

# ---------------------------------------------------------------------------
# PART B -- Information About Your Application (pages 4-5)
# ---------------------------------------------------------------------------
SEC_B = "sec_b_application"
# Item 1 -- grounds checkboxes (multi-select)
add_choice("b1_grounds", "Item 1: I am seeking asylum or withholding of removal based on (check all that apply)",
           "grounds for asylum", SEC_B, [
    {"value": "race", "label": "Race",
     "pdf_field_name": P5 + "CheckBoxrace[0]"},
    {"value": "religion", "label": "Religion",
     "pdf_field_name": P5 + "CheckBoxreligion[0]"},
    {"value": "nationality", "label": "Nationality",
     "pdf_field_name": P5 + "CheckBoxnationality[0]"},
    {"value": "social", "label": "Membership in a Particular Social Group",
     "pdf_field_name": P5 + "CheckBoxsocial[0]"},
    {"value": "politics", "label": "Political Opinion",
     "pdf_field_name": P5 + "CheckBoxpolitics[0]"},
    {"value": "torture", "label": "Torture Convention",
     "pdf_field_name": P5 + "CheckBoxtorture[0]"},
], ftype="checkbox", required=True)
# 1.A past harm
add_choice("b1a_past_harm", "Item 1.A: Have you, your family, or close friends/colleagues ever experienced harm, mistreatment, or threats in the past?",
           "past harm", SEC_B, [
    {"value": "Y", "label": "Yes", "pdf_field_name": P5 + "ckboxyn1a[0]"},
    {"value": "N", "label": "No", "pdf_field_name": P5 + "ckboxyn1a[1]"},
], required=True, extra={"controls_fields": ["b1a_explain"]})
add_text("b1a_explain", P5 + "TextField14[0]",
         "Item 1.A: If Yes, explain in detail (what happened, when, who, and why)",
         "explain past harm", SEC_B, ftype="textarea", multiline=True,
         read_only=True,
         extra={"show_if": {"field": "b1a_past_harm", "operator": "equals",
                            "value": "Y"},
                "overflow_to_supplement": "supp_b"})
# 1.B future fear
add_choice("b1b_future_fear", "Item 1.B: Do you fear harm or mistreatment if you return to your home country?",
           "fear of return", SEC_B, [
    {"value": "Y", "label": "Yes", "pdf_field_name": P5 + "ckboxyn1b[0]"},
    {"value": "N", "label": "No", "pdf_field_name": P5 + "ckboxyn1b[1]"},
], required=True, extra={"controls_fields": ["b1b_explain"]})
add_text("b1b_explain", P5 + "TextField15[0]",
         "Item 1.B: If Yes, explain in detail (what harm, who, and why)",
         "explain fear", SEC_B, ftype="textarea", multiline=True,
         read_only=True,
         extra={"show_if": {"field": "b1b_future_fear", "operator": "equals",
                            "value": "Y"},
                "overflow_to_supplement": "supp_b"})
# Item 2 (page 5)
add_choice("b2_accused", "Item 2: Have you or your family members ever been accused, charged, arrested, detained, interrogated, convicted/sentenced, or imprisoned in any country other than the U.S.?",
           "accused or arrested", SEC_B, [
    {"value": "Y", "label": "Yes", "pdf_field_name": P7 + "ckboxyn2[0]"},
    {"value": "N", "label": "No", "pdf_field_name": P7 + "ckboxyn2[1]"},
], required=True, extra={"controls_fields": ["b2_explain"]})
add_text("b2_explain", P7 + "PBL2_TextField[0]",
         "Item 2: If Yes, explain the circumstances and reasons",
         "explain circumstances", SEC_B, ftype="textarea", multiline=True,
         read_only=True,
         extra={"show_if": {"field": "b2_accused", "operator": "equals",
                            "value": "Y"}, "overflow_to_supplement": "supp_b"})
# Item 3.A
add_choice("b3a_org_member", "Item 3.A: Have you or your family members ever belonged to or been associated with any organizations or groups in your home country?",
           "organization member", SEC_B, [
    {"value": "Y", "label": "Yes", "pdf_field_name": P7 + "ckboxyn3a[0]"},
    {"value": "N", "label": "No", "pdf_field_name": P7 + "ckboxyn3a[1]"},
], required=True, extra={"controls_fields": ["b3a_explain"]})
add_text("b3a_explain", P7 + "PBL3A_TextField[0]",
         "Item 3.A: If Yes, describe participation, positions held, and length of involvement",
         "explain organizations", SEC_B, ftype="textarea", multiline=True,
         read_only=True,
         extra={"show_if": {"field": "b3a_org_member", "operator": "equals",
                            "value": "Y"}, "overflow_to_supplement": "supp_b"})
# Item 3.B
add_choice("b3b_org_continue", "Item 3.B: Do you or your family members continue to participate in these organizations or groups?",
           "continue participation", SEC_B, [
    {"value": "Y", "label": "Yes", "pdf_field_name": P7 + "ckboxyn3b[0]"},
    {"value": "N", "label": "No", "pdf_field_name": P7 + "ckboxyn3b[1]"},
], extra={"controls_fields": ["b3b_explain"],
          "show_if": {"field": "b3a_org_member", "operator": "equals",
                      "value": "Y"}})
add_text("b3b_explain", P7 + "PBL3B_TextField[0]",
         "Item 3.B: If Yes, describe current participation, positions, and length",
         "explain current participation", SEC_B, ftype="textarea",
         multiline=True, read_only=True,
         extra={"show_if": {"field": "b3b_org_continue", "operator": "equals",
                            "value": "Y"}, "overflow_to_supplement": "supp_b"})
# Item 4
add_choice("b4_torture_fear", "Item 4: Are you afraid of being subjected to torture in your home country or any other country to which you may be returned?",
           "fear of torture", SEC_B, [
    {"value": "Y", "label": "Yes", "pdf_field_name": P7 + "ckboxyn4[0]"},
    {"value": "N", "label": "No", "pdf_field_name": P7 + "ckboxyn4[1]"},
], required=True, extra={"controls_fields": ["b4_explain"]})
add_text("b4_explain", P7 + "PB4_TextField[0]",
         "Item 4: If Yes, explain why and describe the nature of torture feared, by whom, and why",
         "explain torture fear", SEC_B, ftype="textarea", multiline=True,
         read_only=True,
         extra={"show_if": {"field": "b4_torture_fear", "operator": "equals",
                            "value": "Y"}, "overflow_to_supplement": "supp_b"})

# ---------------------------------------------------------------------------
# PART C -- Additional Information (pages 6-7)
# ---------------------------------------------------------------------------
SEC_C = "sec_c_additional"
add_choice("c1_prior_app", "Item 1: Have you, your spouse, children, parents, or siblings ever applied to the U.S. Government for refugee status, asylum, or withholding of removal?",
           "prior application", SEC_C, [
    {"value": "Y", "label": "Yes", "pdf_field_name": P8 + "ckboxync1[0]"},
    {"value": "N", "label": "No", "pdf_field_name": P8 + "ckboxync1[1]"},
], required=True, extra={"controls_fields": ["c1_explain"]})
add_text("c1_explain", P8 + "PCL1_TextField[0]",
         "Item 1: If Yes, explain the decision and outcome", "explain prior application",
         SEC_C, ftype="textarea", multiline=True, read_only=True,
         extra={"show_if": {"field": "c1_prior_app", "operator": "equals",
                            "value": "Y"}, "overflow_to_supplement": "supp_b"})
add_choice("c2a_travel", "Item 2.A: After leaving the country from which you claim asylum, did you/spouse/children travel through or reside in any other country before entering the U.S.?",
           "travel through other country", SEC_C, [
    {"value": "Y", "label": "Yes", "pdf_field_name": P8 + "ckboxync2a[0]"},
    {"value": "N", "label": "No", "pdf_field_name": P8 + "ckboxync2a[1]"},
], required=True, extra={"controls_fields": ["c2_explain"]})
add_choice("c2b_other_status", "Item 2.B: Have you/spouse/children/other family ever applied for or received lawful status in any country other than the one from which you now claim asylum?",
           "other lawful status", SEC_C, [
    {"value": "Y", "label": "Yes", "pdf_field_name": P8 + "ckboxync2b[0]"},
    {"value": "N", "label": "No", "pdf_field_name": P8 + "ckboxync2b[1]"},
], required=True, extra={"controls_fields": ["c2_explain"]})
add_text("c2_explain", P8 + "PCL2B_TextField[0]",
         "Item 2.A/2.B: If Yes to either, provide details for each person",
         "explain travel and status", SEC_C, ftype="textarea", multiline=True,
         read_only=True,
         extra={"show_if": {"field": "c2a_travel", "operator": "equals",
                            "value": "Y"}, "overflow_to_supplement": "supp_b"})
add_choice("c3_caused_harm", "Item 3: Have you/spouse/children ever ordered, incited, assisted, or otherwise participated in causing harm or suffering to any person because of race, religion, nationality, social group, or political opinion?",
           "caused harm", SEC_C, [
    {"value": "Y", "label": "Yes", "pdf_field_name": P8 + "ckboxync3[0]"},
    {"value": "N", "label": "No", "pdf_field_name": P8 + "ckboxync3[1]"},
], required=True, extra={"controls_fields": ["c3_explain"]})
add_text("c3_explain", P8 + "PCL3_TextField[0]",
         "Item 3: If Yes, describe in detail each incident and your involvement",
         "explain caused harm", SEC_C, ftype="textarea", multiline=True,
         read_only=True,
         extra={"show_if": {"field": "c3_caused_harm", "operator": "equals",
                            "value": "Y"}, "overflow_to_supplement": "supp_b"})
add_choice("c4_returned", "Item 4: After you left the country where you were harmed or fear harm, did you return to that country?",
           "returned to country", SEC_C, [
    {"value": "Y", "label": "Yes", "pdf_field_name": P9 + "PCckboxyn4[0]"},
    {"value": "N", "label": "No", "pdf_field_name": P9 + "PCckboxyn4[1]"},
], required=True, extra={"controls_fields": ["c4_explain"]})
add_text("c4_explain", P9 + "PCL4_TextField[0]",
         "Item 4: If Yes, describe the circumstances of your visit(s)",
         "explain return visits", SEC_C, ftype="textarea", multiline=True,
         read_only=True,
         extra={"show_if": {"field": "c4_returned", "operator": "equals",
                            "value": "Y"}, "overflow_to_supplement": "supp_b"})
add_choice("c5_late_filing", "Item 5: Are you filing this application more than 1 year after your last arrival in the United States?",
           "filing late", SEC_C, [
    {"value": "Y", "label": "Yes", "pdf_field_name": P9 + "ckboxync5[0]"},
    {"value": "N", "label": "No", "pdf_field_name": P9 + "ckboxync5[1]"},
], required=True, extra={"controls_fields": ["c5_explain"]})
add_text("c5_explain", P9 + "PCL5_TextField[0]",
         "Item 5: If Yes, explain why you did not file within the first year",
         "explain late filing", SEC_C, ftype="textarea", multiline=True,
         read_only=True,
         extra={"show_if": {"field": "c5_late_filing", "operator": "equals",
                            "value": "Y"}, "overflow_to_supplement": "supp_b"})
add_choice("c6_us_crime", "Item 6: Have you or any family member included in the application ever committed any crime and/or been arrested, charged, convicted, or sentenced for any crimes in the United States?",
           "US crime", SEC_C, [
    {"value": "Y", "label": "Yes", "pdf_field_name": P9 + "ckboxync6[0]"},
    {"value": "N", "label": "No", "pdf_field_name": P9 + "ckboxync6[1]"},
], required=True, extra={"controls_fields": ["c6_explain"]})
add_text("c6_explain", P9 + "PCL6_TextField[0]",
         "Item 6: If Yes, specify what occurred and the circumstances for each instance",
         "explain US crime", SEC_C, ftype="textarea", multiline=True,
         read_only=True,
         extra={"show_if": {"field": "c6_us_crime", "operator": "equals",
                            "value": "Y"}, "overflow_to_supplement": "supp_b"})

# ---------------------------------------------------------------------------
# PART D -- Your Signature (page 8)
# ---------------------------------------------------------------------------
SEC_D = "sec_d_signature"
add_text("d_print_name", P10 + "TextField20[0]",
         "Print your Complete Name", "your complete name", SEC_D, required=True)
add_text("d_native_alphabet", P10 + "TextField20[1]",
         "Write your Name in your native alphabet", "name in native alphabet",
         SEC_D)
add_choice("d_family_assist", "Did your spouse, parent, or child/children assist you in completing this application?",
           "family assisted", SEC_D, [
    {"value": "2", "label": "Yes (list name and relationship)",
     "pdf_field_name": P10 + "PtD_ckboxynd1[0]"},
    {"value": "1", "label": "No", "pdf_field_name": P10 + "PtD_ckboxynd1[1]"},
], required=True, extra={"controls_fields": ["d_assist_name1", "d_assist_rel1",
                                             "d_assist_name2", "d_assist_rel2"]})
SHOW_IF_ASSIST = {"field": "d_family_assist", "operator": "equals", "value": "2"}
add_text("d_assist_name1", P10 + "PtD_ChildName1[0]", "Assistant 1: Name",
         "assistant name", SEC_D, extra={"show_if": SHOW_IF_ASSIST})
add_text("d_assist_rel1", P10 + "PtD_RelationshipOfChild1[0]",
         "Assistant 1: Relationship", "assistant relationship", SEC_D,
         extra={"show_if": SHOW_IF_ASSIST})
add_text("d_assist_name2", P10 + "PtD_ChildName2[0]", "Assistant 2: Name",
         "second assistant name", SEC_D, extra={"show_if": SHOW_IF_ASSIST})
add_text("d_assist_rel2", P10 + "PtD_RelationshipOfChild2[0]",
         "Assistant 2: Relationship", "second assistant relationship", SEC_D,
         extra={"show_if": SHOW_IF_ASSIST})
add_choice("d_preparer_other", "Did someone other than your spouse, parent, or child/children prepare this application?",
           "preparer other", SEC_D, [
    {"value": "Y", "label": "Yes (complete Part E)",
     "pdf_field_name": P10 + "ckboxynd2[0]"},
    {"value": "N", "label": "No", "pdf_field_name": P10 + "ckboxynd2[1]"},
], required=True, extra={"controls_fields": ["e_preparer_name"],
                          "conditional_behavior": {
                              "if_yes": "Complete Part E (Declaration of Person Preparing Form)."}})
add_choice("d_counsel_list", "Have you been provided with a list of persons who may be available to assist you with your asylum claim?",
           "counsel list", SEC_D, [
    {"value": "Y", "label": "Yes", "pdf_field_name": P10 + "ckboxynd3[0]"},
    {"value": "N", "label": "No", "pdf_field_name": P10 + "ckboxynd3[1]"},
], required=True)
add_text("d_signature", P10 + "TextField22[0]",
         "Signature of Applicant (cannot be signed electronically)",
         "applicant signature", SEC_D, ftype="signature", read_only=True)
add_text("d_sign_date", P10 + "DateTimeField48[0]", "Date of Signature",
         "signature date", SEC_D, ftype="date", pattern=DATE_PATTERN)

# ---------------------------------------------------------------------------
# PART E -- Declaration of Preparer (page 8)
# ---------------------------------------------------------------------------
SEC_E = "sec_e_preparer"
SHOW_IF_PREPARER = {"field": "d_preparer_other", "operator": "equals",
                    "value": "Y"}
add_text("e_preparer_signature", P10 + "PtE_PreparerSignature[0]",
         "Signature of Preparer (cannot be signed electronically)",
         "preparer signature", SEC_E, ftype="signature", read_only=True,
         extra={"show_if": SHOW_IF_PREPARER})
add_text("e_preparer_name", P10 + "PtE_PreparerName[0]",
         "Print Complete Name of Preparer", "preparer name", SEC_E,
         extra={"show_if": SHOW_IF_PREPARER})
add_text("e_preparer_street", P10 + "PtE_StreetNumAndName[0]",
         "Preparer Address: Street Number and Name", "preparer street", SEC_E,
         extra={"show_if": SHOW_IF_PREPARER})
add_text("e_preparer_apt", P10 + "PtE_AptNumber[0]",
         "Preparer Address: Apartment Number", "preparer apartment", SEC_E,
         extra={"show_if": SHOW_IF_PREPARER})
add_text("e_preparer_city", P10 + "PtE_City[0]", "Preparer Address: City",
         "preparer city", SEC_E, extra={"show_if": SHOW_IF_PREPARER})
add_text("e_preparer_state", P10 + "PtE_State[0]", "Preparer Address: State",
         "preparer state", SEC_E, extra={"show_if": SHOW_IF_PREPARER})
add_text("e_preparer_zip", P10 + "PtE_ZipCode[0]", "Preparer Address: Zip Code",
         "preparer zip", SEC_E, pattern=r"^\\d{5}$",
         extra={"show_if": SHOW_IF_PREPARER})
add_text("e_preparer_areacode", P10 + "TextField25[1]",
         "Preparer Daytime Telephone: Area Code", "preparer area code", SEC_E,
         extra={"show_if": SHOW_IF_PREPARER})
add_text("e_preparer_phone", P10 + "TextField25[0]",
         "Preparer Daytime Telephone Number", "preparer phone", SEC_E,
         extra={"show_if": SHOW_IF_PREPARER})
add_checkbox("e_attorney_flag", P10 + "CheckBox1[0]",
             "To be completed by an attorney or accredited representative",
             "attorney representative", SEC_E, "1")
add_text("e_attorney_bar", P10 + "AttorneyStateBarNumber[0]",
         "Attorney or State Bar Number, if applicable", "bar number", SEC_E)
add_text("e_attorney_uscis_acct", P10 + "USCISOnlineAcctNumber[0]",
         "Attorney/Accredited Rep USCIS Online Account Number, if any",
         "attorney USCIS account", SEC_E)

# ---------------------------------------------------------------------------
# PART F -- Asylum Interview (page 9) -- read-only, completed by officer
# ---------------------------------------------------------------------------
SEC_F = "sec_f_interview"
add_text("f_corr_first", P11 + "TextField26[0]",
         "Corrections numbered (first)", "first correction", SEC_F,
         read_only=True)
add_text("f_corr_last", P11 + "TextField26[1]",
         "Corrections numbered (last)", "last correction", SEC_F,
         read_only=True)
add_text("f_sign_date", P11 + "DateTimeField49[0]",
         "Signed and sworn date (before asylum officer)", "interview sign date",
         SEC_F, ftype="date", pattern=DATE_PATTERN, read_only=True)
add_text("f_officer_signature", P11 + "TextField27[0]",
         "Signature of Asylum Officer", "officer signature", SEC_F,
         ftype="signature", read_only=True)
add_text("f_applicant_native", P11 + "TextField27[1]",
         "Write Your Name in Your Native Alphabet", "name native alphabet",
         SEC_F, read_only=True)
add_text("f_applicant_signature", P11 + "TextField27[2]",
         "Signature of Applicant", "applicant signature interview", SEC_F,
         ftype="signature", read_only=True)
add_choice("f_truth", "I swear (affirm) that the contents of this application are:",
           "interview truth", SEC_F, [
    {"value": "Y", "label": "All true",
     "pdf_field_name": P11 + "CheckBox32[0]"},
    {"value": "N", "label": "Not all true",
     "pdf_field_name": P11 + "CheckBox32[1]"},
], extra={"read_only": True})

# ---------------------------------------------------------------------------
# PART G -- Removal Hearing (page 9) -- read-only, completed by judge
# ---------------------------------------------------------------------------
SEC_G = "sec_g_hearing"
add_text("g_corr_first", P11 + "TextField26[2]",
         "Corrections numbered (first)", "first correction", SEC_G,
         read_only=True)
add_text("g_corr_last", P11 + "TextField26[3]",
         "Corrections numbered (last)", "last correction", SEC_G,
         read_only=True)
add_text("g_sign_date", P11 + "DateTimeField50[0]",
         "Signed and sworn date (before immigration judge)", "hearing sign date",
         SEC_G, ftype="date", pattern=DATE_PATTERN, read_only=True)
add_text("g_judge_signature", P11 + "TextField27[3]",
         "Signature of Immigration Judge", "judge signature", SEC_G,
         ftype="signature", read_only=True)
add_text("g_applicant_native", P11 + "TextField27[4]",
         "Write Your Name in Your Native Alphabet", "name native alphabet",
         SEC_G, read_only=True)
add_text("g_applicant_signature", P11 + "TextField27[5]",
         "Signature of Applicant", "applicant signature hearing", SEC_G,
         ftype="signature", read_only=True)
add_choice("g_truth", "I swear (affirm) that the contents of this application are:",
           "hearing truth", SEC_G, [
    {"value": "Y", "label": "All true",
     "pdf_field_name": P11 + "PG_CheckBox[0]"},
    {"value": "N", "label": "Not all true",
     "pdf_field_name": P11 + "PG_CheckBox[1]"},
], extra={"read_only": True})

# ---------------------------------------------------------------------------
# SUPPLEMENT A -- additional children (page 10). Two additional-child blocks.
# ---------------------------------------------------------------------------
SEC_SUPPA = "sec_supp_a"
add_text("sa_anumber", SA + "PtAILine1_ANumber[1]",
         "Supplement A: Alien Registration Number (A-Number)",
         "supplement A number", SEC_SUPPA, read_only=True,
         extra={"copy_to": []})
add_text("sa_applicant_name", SA + "ApplicantName[0]",
         "Supplement A: Applicant's Name", "applicant name", SEC_SUPPA,
         read_only=True)
add_text("sa_signature", SA + "TextField28[0]",
         "Supplement A: Applicant's Signature", "supplement A signature",
         SEC_SUPPA, ftype="signature", read_only=True)
add_text("sa_date", SA + "DateTimeField57[0]", "Supplement A: Date", "date",
         SEC_SUPPA, ftype="date", pattern=DATE_PATTERN)

supp_a_child_maps = {
    1: {
        "alien": SA + "TextField12[6]", "passport": SA + "TextField12[7]",
        "marital": SA + "TextField12[8]", "ssn": SA + "TextField12[9]",
        "last": SA + "TextField12[0]", "first": SA + "TextField12[2]",
        "middle": SA + "TextField12[3]", "dob": SA + "DateTimeField14[0]",
        "city": SA + "TextField12[1]", "nat": SA + "TextField12[4]",
        "race": SA + "TextField12[5]",
        "sex_m": SA + "CheckBox12_Sex[2]", "sex_f": SA + "CheckBox12_Sex[3]",
        "in_us_y": SA + "CheckBox57[0]", "in_us_n": SA + "CheckBox57[1]",
        "location": SA + "SuppLALine13_Specify[0]",
        "place_entry": SA + "ChildEntry5[0]", "date_entry": SA + "ChildExp5[0]",
        "i94": SA + "ChildINum5[0]", "status": SA + "ChildStatus5[0]",
        "current_status": SA + "ChildCurrent5[0]",
        "exp_stay": SA + "ChildExpAuth5[0]",
        "court_y": SA + "SuppA_CheckBox20[0]", "court_n": SA + "SuppA_CheckBox20[1]",
        "incl_y": SA + "SuppA_CheckBox21[0]", "incl_n": SA + "SuppA_CheckBox21[1]",
    },
    2: {
        "alien": SA + "TextField12[16]", "passport": SA + "TextField12[17]",
        "marital": SA + "TextField12[18]", "ssn": SA + "TextField12[19]",
        "last": SA + "TextField12[10]", "first": SA + "TextField12[12]",
        "middle": SA + "TextField12[13]", "dob": SA + "DateTimeField14[1]",
        "city": SA + "TextField12[11]", "nat": SA + "TextField12[14]",
        "race": SA + "TextField12[15]",
        "sex_m": SA + "SuppAL12_CheckBox[0]", "sex_f": SA + "SuppAL12_CheckBox[1]",
        "in_us_y": SA + "SuppAL13_CheckBox[0]", "in_us_n": SA + "SuppAL13_CheckBox[1]",
        "location": SA + "SuppLALine13_Specify2[0]",
        "place_entry": SA + "ChildEntry6[0]", "date_entry": SA + "ChildExp6[0]",
        "i94": SA + "ChildINum6[0]", "status": SA + "ChildStatus6[0]",
        "current_status": SA + "ChildCurrent6[0]",
        "exp_stay": SA + "ChildExpAuth6[0]",
        "court_y": SA + "SuppALine20_CheckBox2[0]",
        "court_n": SA + "SuppALine20_CheckBox2[1]",
        "incl_y": SA + "SuppALine21_CheckBox[0]",
        "incl_n": SA + "SuppALine21_CheckBox[1]",
    },
}
supp_a_row_ids = []
for n, m in supp_a_child_maps.items():
    pre = "sa_child%d_" % n
    add_text(pre + "alien", m["alien"], "Additional Child %d: A-Number" % n,
             "add child %d A number" % n, SEC_SUPPA)
    add_text(pre + "passport", m["passport"],
             "Additional Child %d: Passport/ID Number" % n,
             "add child %d passport" % n, SEC_SUPPA)
    add_text(pre + "marital", m["marital"],
             "Additional Child %d: Marital Status" % n,
             "add child %d marital" % n, SEC_SUPPA)
    add_text(pre + "ssn", m["ssn"], "Additional Child %d: SSN" % n,
             "add child %d SSN" % n, SEC_SUPPA)
    add_text(pre + "last", m["last"], "Additional Child %d: Last Name" % n,
             "add child %d last name" % n, SEC_SUPPA)
    add_text(pre + "first", m["first"], "Additional Child %d: First Name" % n,
             "add child %d first name" % n, SEC_SUPPA)
    add_text(pre + "middle", m["middle"], "Additional Child %d: Middle Name" % n,
             "add child %d middle name" % n, SEC_SUPPA)
    add_text(pre + "dob", m["dob"], "Additional Child %d: Date of Birth" % n,
             "add child %d DOB" % n, SEC_SUPPA, ftype="date", pattern=DATE_PATTERN)
    add_text(pre + "city", m["city"],
             "Additional Child %d: City/Country of Birth" % n,
             "add child %d birth place" % n, SEC_SUPPA)
    add_text(pre + "nat", m["nat"], "Additional Child %d: Nationality" % n,
             "add child %d nationality" % n, SEC_SUPPA)
    add_text(pre + "race", m["race"],
             "Additional Child %d: Race/Ethnic/Tribal Group" % n,
             "add child %d race" % n, SEC_SUPPA)
    add_choice(pre + "sex", "Additional Child %d: Sex" % n,
               "add child %d sex" % n, SEC_SUPPA, [
        {"value": "M", "label": "Male", "pdf_field_name": m["sex_m"]},
        {"value": "F", "label": "Female", "pdf_field_name": m["sex_f"]},
    ])
    in_us_id = pre + "in_us"
    add_choice(in_us_id, "Additional Child %d: Is this child in the U.S.?" % n,
               "add child %d in U.S." % n, SEC_SUPPA, [
        {"value": "Y", "label": "Yes (Complete Blocks 14 to 21)",
         "pdf_field_name": m["in_us_y"]},
        {"value": "N", "label": "No (Specify location)",
         "pdf_field_name": m["in_us_n"]},
    ], extra={"controls_fields": [pre + "place_entry", pre + "date_entry",
                                  pre + "i94", pre + "status",
                                  pre + "current_status", pre + "exp_stay",
                                  pre + "court", pre + "included"]})
    add_text(pre + "location", m["location"],
             "Additional Child %d: If not in U.S., location" % n,
             "add child %d location" % n, SEC_SUPPA,
             extra={"show_if": {"field": in_us_id, "operator": "equals",
                                "value": "N"}})
    show_us = {"field": in_us_id, "operator": "equals", "value": "Y"}
    add_text(pre + "place_entry", m["place_entry"],
             "Additional Child %d: Place of Last Entry" % n,
             "add child %d entry place" % n, SEC_SUPPA,
             extra={"show_if": show_us})
    add_text(pre + "date_entry", m["date_entry"],
             "Additional Child %d: Date of Last Entry" % n,
             "add child %d entry date" % n, SEC_SUPPA, ftype="date",
             pattern=DATE_PATTERN, extra={"show_if": show_us})
    add_text(pre + "i94", m["i94"], "Additional Child %d: I-94 Number" % n,
             "add child %d I-94" % n, SEC_SUPPA, extra={"show_if": show_us})
    add_text(pre + "status", m["status"],
             "Additional Child %d: Status when Last Admitted" % n,
             "add child %d status" % n, SEC_SUPPA, extra={"show_if": show_us})
    add_text(pre + "current_status", m["current_status"],
             "Additional Child %d: Current Status" % n,
             "add child %d current status" % n, SEC_SUPPA,
             extra={"show_if": show_us})
    add_text(pre + "exp_stay", m["exp_stay"],
             "Additional Child %d: Exp. of Authorized Stay" % n,
             "add child %d stay exp" % n, SEC_SUPPA, ftype="date",
             pattern=DATE_PATTERN, extra={"show_if": show_us})
    add_choice(pre + "court", "Additional Child %d: In Immigration Court proceedings?" % n,
               "add child %d in court" % n, SEC_SUPPA, [
        {"value": "Y", "label": "Yes", "pdf_field_name": m["court_y"]},
        {"value": "N", "label": "No", "pdf_field_name": m["court_n"]},
    ], extra={"show_if": show_us})
    add_choice(pre + "included", "Additional Child %d: Included in application?" % n,
               "add child %d included" % n, SEC_SUPPA, [
        {"value": "Y", "label": "Yes", "pdf_field_name": m["incl_y"]},
        {"value": "N", "label": "No", "pdf_field_name": m["incl_n"]},
    ], extra={"show_if": show_us})
    supp_a_row_ids.append(pre.rstrip("_"))

fields.append({
    "id": "sa_children_table",
    "name": "Supplement A: List all additional children (continuation of Part A.II Your Children)",
    "spoken_name": "additional children",
    "type": "table",
    "section_id": SEC_SUPPA,
    "validation": {"required": False},
    "columns": fields[-1]["columns"] if False else [
        {"id": "last", "label": "Last Name", "type": "text"},
        {"id": "first", "label": "First Name", "type": "text"},
        {"id": "dob", "label": "Date of Birth", "type": "date"},
        {"id": "nat", "label": "Nationality", "type": "text"},
        {"id": "in_us", "label": "In U.S.?", "type": "radio"},
        {"id": "included", "label": "Included?", "type": "radio"},
    ],
    "multi_entry": {"min_rows": 0, "form_rows": 2,
                    "row_field_ids": supp_a_row_ids,
                    "continues": "a2_children_table"},
})

# ---------------------------------------------------------------------------
# SUPPLEMENT B -- additional info (page 11). Continuation page, copy as needed.
# ---------------------------------------------------------------------------
SEC_SUPPB = "sec_supp_b"
add_text("sb_anumber", SB + "PtAILine1_ANumber[2]",
         "Supplement B: Alien Registration Number (A-Number)",
         "supplement B number", SEC_SUPPB, read_only=True)
add_text("sb_applicant_name", SB + "SupBApplicantName[0]",
         "Supplement B: Applicant's Name", "applicant name", SEC_SUPPB,
         read_only=True)
add_text("sb_signature", SB + "TextField30[0]",
         "Supplement B: Applicant's Signature", "supplement B signature",
         SEC_SUPPB, ftype="signature", read_only=True)
add_text("sb_date", SB + "DateTimeField58[0]", "Supplement B: Date", "date",
         SEC_SUPPB, ftype="date", pattern=DATE_PATTERN)
add_text("sb_part_number", SB + "TextField31[0]",
         "Supplement B: Part Number this entry continues", "part number",
         SEC_SUPPB)
add_text("sb_question_number", SB + "TextField31[1]",
         "Supplement B: Question Number this entry continues", "question number",
         SEC_SUPPB)
add_text("sb_additional_info", SB + "TextField32[0]",
         "Supplement B: Additional Information (continuation; copy and complete as needed)",
         "additional information", SEC_SUPPB, ftype="textarea", multiline=True)

# ---------------------------------------------------------------------------
# Barcodes (read-only, machine) -- capture so no widget is silently dropped.
# ---------------------------------------------------------------------------
SEC_META = "sec_meta_barcodes"
bc_n = 0
for f in acro["fields"]:
    if f["name"].endswith("PDF417BarCode1[0]"):
        bc_n += 1
        add_text("barcode_%d" % bc_n, f["name"],
                 "PDF417 Barcode (page %d)" % page_of(f["name"]),
                 "barcode", SEC_META, multiline=True, read_only=True)
# EOIR / USCIS use-only boxes on page 1
add_text("meta_eoir", P1 + "TextField8[0]", "For EOIR use only", "EOIR box",
         SEC_META, multiline=True, read_only=True)
add_text("meta_uscis_officer", P1 + "TextField9[0]",
         "USCIS use only: Asylum Officer ID Number", "officer ID", SEC_META,
         read_only=True)
add_text("meta_approval_date", P1 + "DateTimeField2[3]",
         "USCIS use only: Approval Date", "approval date", SEC_META,
         ftype="date", read_only=True)
add_text("meta_denial_date", P1 + "DateTimeField2[4]",
         "USCIS use only: Denial Date", "denial date", SEC_META, ftype="date",
         read_only=True)
add_text("meta_referral_date", P1 + "DateTimeField2[5]",
         "USCIS use only: Referral Date", "referral date", SEC_META,
         ftype="date", read_only=True)
add_text("meta_interview_date", P1 + "DateTimeField2[6]",
         "USCIS use only: Interview Date", "interview date", SEC_META,
         ftype="date", read_only=True)

# ---------------------------------------------------------------------------
# Verify coverage: every acro widget consumed exactly once.
# ---------------------------------------------------------------------------
all_widget_names = set(by_name.keys())
missing = sorted(all_widget_names - used_widgets)
if missing:
    raise SystemExit("UNCONSUMED WIDGETS (%d):\n  %s" % (len(missing),
                     "\n  ".join(missing)))

# ---------------------------------------------------------------------------
# Build sections + parts.
# ---------------------------------------------------------------------------
section_defs = [
    (SEC_AI, "Part A.I - Information About You", [0]),
    (SEC_SPOUSE, "Part A.II - Information About Your Spouse", [1]),
    (SEC_CHILD, "Part A.II - Information About Your Children", [1, 2]),
    (SEC_BG, "Part A.III - Information About Your Background", [3]),
    (SEC_B, "Part B - Information About Your Application", [4, 5]),
    (SEC_C, "Part C - Additional Information About Your Application", [6, 7]),
    (SEC_D, "Part D - Your Signature", [8]),
    (SEC_E, "Part E - Declaration of Person Preparing Form", [8]),
    (SEC_F, "Part F - To Be Completed at Asylum Interview", [9]),
    (SEC_G, "Part G - To Be Completed at Removal Hearing", [9]),
    (SEC_SUPPA, "Supplement A - Additional Children", [10]),
    (SEC_SUPPB, "Supplement B - Additional Information About Your Claim", [11]),
    (SEC_META, "Form Metadata / Official Use Only", list(range(12))),
]
sec_show_if = {
    SEC_SPOUSE: {"field": "a2_not_married", "operator": "not_equals",
                 "value": "1"},
    SEC_CHILD: {"field": "a2_has_children", "operator": "equals", "value": "N"},
    SEC_E: {"field": "d_preparer_other", "operator": "equals", "value": "Y"},
    SEC_SUPPA: {"field": "a2_total_children", "operator": "greater_than",
                "value": 4},
}
field_ids_by_section = {}
for f in fields:
    field_ids_by_section.setdefault(f["section_id"], []).append(f["id"])

for order, (sid, label, pages) in enumerate(section_defs, start=1):
    sec = {
        "id": sid,
        "label": label,
        "order": order,
        "fields": field_ids_by_section.get(sid, []),
        "page_numbers": pages,
    }
    if sid in sec_show_if:
        sec["show_if"] = sec_show_if[sid]
    sections.append(sec)

parts = [
    {"id": "part_a", "label": "Part A - Information About You, Your Spouse, Children, and Background",
     "order": 1, "section_ids": [SEC_AI, SEC_SPOUSE, SEC_CHILD, SEC_BG]},
    {"id": "part_b", "label": "Part B - Information About Your Application",
     "order": 2, "section_ids": [SEC_B]},
    {"id": "part_c", "label": "Part C - Additional Information About Your Application",
     "order": 3, "section_ids": [SEC_C]},
    {"id": "part_d", "label": "Part D - Your Signature", "order": 4,
     "section_ids": [SEC_D]},
    {"id": "part_e", "label": "Part E - Declaration of Person Preparing Form",
     "order": 5, "section_ids": [SEC_E]},
    {"id": "part_f", "label": "Part F - To Be Completed at Asylum Interview",
     "order": 6, "section_ids": [SEC_F]},
    {"id": "part_g", "label": "Part G - To Be Completed at Removal Hearing",
     "order": 7, "section_ids": [SEC_G]},
    {"id": "part_supp", "label": "Supplements", "order": 8,
     "section_ids": [SEC_SUPPA, SEC_SUPPB]},
    {"id": "part_meta", "label": "Official Use / Metadata", "order": 9,
     "section_ids": [SEC_META]},
]

supplements = [
    {"id": "supp_a", "label": "Supplement A (Form I-589) - List of additional children"},
    {"id": "supp_b", "label": "Supplement B (Form I-589) - Additional information about your claim"},
]

schema = {
    "source": "pdf",
    "form_metadata": {
        "title": "Application for Asylum and for Withholding of Removal",
        "form_number": "I-589",
        "page_count": acro["page_count"],
        "edition_date": "",
    },
    "parts": parts,
    "sections": sections,
    "fields": fields,
    "supplements": supplements,
}

with open(OUT, "w", encoding="ascii") as fh:
    json.dump(schema, fh, indent=2, ensure_ascii=True)

# Report stats
n_showif = sum(1 for f in fields if "show_if" in f)
n_table = sum(1 for f in fields if f["type"] == "table")
n_controls = sum(1 for f in fields if "controls_fields" in f)
n_copyto = sum(1 for f in fields if "copy_to" in f and f["copy_to"])
n_overflow = sum(1 for f in fields if "overflow_to_supplement" in f)
print("fields=%d sections=%d parts=%d supplements=%d" % (
    len(fields), len(sections), len(parts), len(supplements)))
print("show_if=%d table=%d controls_fields=%d copy_to=%d overflow=%d" % (
    n_showif, n_table, n_controls, n_copyto, n_overflow))
print("widgets_consumed=%d / %d" % (len(used_widgets), len(all_widget_names)))
