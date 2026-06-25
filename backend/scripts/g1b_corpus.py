"""G1b bake-off corpus -- full-size labeled form states with embedded contradictions.

bd polyglot-pdf-0zp3. Unlike the G1 corpus (g1_corpus.py: tiny 3-5 field clusters),
this builds REALISTIC FULL-SIZE form states (20 / 40 / 132 fields) so the
out-of-band checker is measured the way it actually runs: a contradiction buried
in a page- or form-sized payload of coherent noise, not in isolation.

PROVENANCE (same honesty rule as G1): SYNTHETIC. The field IDs / spoken names /
types / section ids are REAL -- the 132 fields of form-kits/i-90/schema.json in
document order. The VALUES are a hand-authored coherent persona; the
contradictions are deliberately injected. No real user transcripts exist (pre-pilot,
no PII logged). Recall numbers are an UPPER BOUND on real-world recall.

132 = the real full I-90 (the realistic worst case; we do NOT synthesize a 200-pad
-- a real form at its real length is the honest worst case). 20 ~ a section, 40 ~ a
page. Sizes are produced by taking the first N fields in document order, then
injecting a contradiction that fits inside that window. The filler fills the
physical/interpreter/preparer clusters coherently (Codex review #8 found those were
left empty and dropped from the payload), so the size-132 payload now genuinely
transmits ~132 filled fields, not the prior ~84.

Each case is a contract-2-style payload: a list of {field_id, name, value} for the
filled fields (the checker reads filled values; empty fields are omitted as in
production). Labels: the field-id set(s) that SHOULD be flagged, plus per-case
metadata -- the contradiction CLASS and the DISTANCE (how many filled fields apart
the two contradicting fields sit in payload order; 0 for single-field). Distance is
the key new variable: does a model still catch a contradiction whose halves are
40 fields apart (cross-section) as well as one whose halves are adjacent?

Contradiction CLASSES (reuse G1's taxonomy + the cross-section semantic classes the
maintainer named):
  zip_state, state_country, province_us, city_state, future_dob, admission_dob
  (as in g1_corpus.py), plus two GENUINE far-apart same-fact classes that pair a
  Part 1 field against a Part 8 "additional information" free-text continuation
  textarea (idx ~115-131, far from Part 1 -- a real cross-section gap, distance >20
  at size 132, so they only fit in the 132-field window):
  cross_date     -- the applicant's DATE OF BIRTH (Part 1 line 9) is RESTATED with a
                    DIFFERENT year in a Part 8 additional-info textarea (e.g.
                    'Applicant was born in 1990.' while line 9 says 1985-04-12)
  duration_year  -- a Part 8 additional-info textarea states a length-of-residence
                    that contradicts the date of admission (Part 1 line 15): e.g.
                    'lived in the United States for over 20 years' while admission is
                    2020 (the maintainer's example)
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field as dc_field

_SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "form-kits", "i-90", "schema.json",
)


def _load_fields() -> list:
    """The real I-90 leaf fields in document order: (id, spoken_name, type)."""
    with open(_SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    out = []
    for fld in schema["fields"]:
        fid = fld.get("id")
        name = fld.get("spoken_name") or fld.get("name") or fid
        ftype = fld.get("type", "text")
        sec = fld.get("section_id", "")
        if fid:
            out.append({"field_id": fid, "name": name, "type": ftype, "section_id": sec})
    return out


# A coherent persona: realistic filler values keyed by a substring of the field id
# or spoken name. The bulk of the form is filled coherently so an injected
# contradiction sits in real noise. Anything not matched gets a generic value by
# type (so the payload is dense, like a near-complete form at a boundary).
_PERSONA = {
    "aliennumber": "A123456789",
    "uscisonlineaccount": "1234567890123",
    "ssn": "123-45-6789",
    "familyname": "Nguyen",
    "lastname": "Nguyen",
    "givenname": "Linh",
    "firstname": "Linh",
    "middlename": "Thi",
    "preferred": "Linh Nguyen",
    "dateofbirth": "1988-04-12",
    # "city and state" combo fields take a COMBINED value, not a bare state --
    # the longest-key-first match makes "cityandstate" win over "state" so a
    # "port of entry city and state" field gets "Houston, TX", not "TX" (which
    # the model flags as incomplete -- same class of filler artifact as the
    # TX-in-radio Codex caught).
    "cityandstate": "Houston, TX",
    "cityortown": "Houston",
    "citytown": "Houston",
    "citytownofbirth": "Hanoi",
    "countryofbirth": "Vietnam",
    "countryofcitizenship": "Vietnam",
    "streetnumbername": "4200 Westheimer Rd",
    "aptsteflrnumber": "12",
    "state": "TX",
    "zipcode": "77027",
    "province": "",
    "postalcode": "",
    "country": "United States",
    "dateofadmission": "2015-06-20",
    "i94": "12345678901",
    "passportnumber": "N1234567",
    "travel": "2015-06-20",
    "classofadmission": "F-1",
    "destination": "Houston, TX",
    "emailaddress": "linh.nguyen@example.com",
    "daytimephone": "713-555-0142",
    "mobilephone": "713-555-0199",
    "dateofsignature": "2026-06-01",
}


# Per-field-id COHERENT values for the physical / interpreter / preparer clusters.
# These were previously left EMPTY (and dropped from the payload), so the "132-field"
# sweep actually transmitted only ~84 filled fields (Codex review #8). Filling them
# with a GLOBALLY COHERENT persona -- physical address = the SAME as mailing (a real
# applicant often has one address), a real interpreter, a real preparer -- means the
# size-132 payload genuinely carries ~132 fields AND introduces no spurious
# contradiction (every filled value is internally consistent). Injection cases
# override only the specific fields their contradiction needs.
_CLUSTER_FILL = {
    # physical address (Part 1, lines 7a-7h) = same city/state/zip as mailing
    "p1_line7a_streetnumbername": "4200 Westheimer Rd",
    "p1_line7c_cityortown": "Houston",
    "p1_line7d_state": "TX",
    "p1_line7e_zipcode": "77027",
    "p1_line7h_country": "United States",
    # interpreter (Part 6)
    "p6_line1a_interpretersfamilyname": "Garcia",
    "p6_line1b_interpretersgivenname": "Maria",
    "p6_line3c_citytown": "Houston",
    "p6_line3d_state": "TX",
    "p6_line3e_zipcode": "77002",
    "p6_line3h_country": "United States",
    "p6_line5_interpretersemailaddress": "maria.garcia@example.com",
    # preparer (Part 7)
    "p7_line1a_familyname": "Smith",
    "p7_line1b_preparersgivenname": "John",
    "p7_line3c_citytown": "Houston",
    "p7_line3d_state": "TX",
    "p7_line3e_zipcode": "77003",
    "p7_line3h_country": "United States",
    "p7_line6_preparersemailaddress": "john.smith@example.com",
}


def _filler(field: dict) -> str:
    """A coherent value for a field, by TYPE first (so a non-option value can never
    land in a radio/checkbox/select -- Codex review #2: 'United States' contains
    'state', so the substring persona used to inject 'TX' into a Yes/No checkbox),
    then by per-id cluster fill, then by id/name persona substring."""
    fid = field["field_id"].lower()
    t = field["type"]
    # TYPE-GATED values win over substring persona for constrained field types.
    if t in ("radio", "checkbox"):
        return "No"
    if t == "select":
        # the only select fields here are US state pickers
        return "TX"
    if t == "signature":
        return "Linh Nguyen"
    # explicit per-id cluster fill (physical/interpreter/preparer)
    if field["field_id"] in _CLUSTER_FILL:
        return _CLUSTER_FILL[field["field_id"]]
    # persona substring match (MOST-SPECIFIC / longest key first, so
    # "citytownofbirth" wins over "cityortown" and "countryofbirth" over "country")
    key = (fid + " " + field["name"]).lower()
    for needle in sorted(_PERSONA, key=len, reverse=True):
        if needle in key:
            return _PERSONA[needle]
    if t == "date":
        return "2015-06-20"
    if t == "textarea":
        return "N/A"
    return "N/A"


@dataclass
class Case:
    case_id: str
    size: int            # target form size (20/40/132)
    cls: str             # contradiction class, or "clean"
    distance: int        # filled-field index gap between the two contra fields (0=single/clean)
    fields: list         # the payload: [{field_id, name, value}, ...]
    expected_conflicts: list = dc_field(default_factory=list)  # list of id-sets; empty=clean

    @property
    def is_contradiction(self) -> bool:
        return len(self.expected_conflicts) > 0


def _base_state(all_fields: list, size: int) -> list:
    """First `size` fields in document order, each filled with coherent filler.
    Returns a list of mutable {field_id, name, value} dicts."""
    chosen = all_fields[:size]
    return [{"field_id": f["field_id"], "name": f["name"], "value": _filler(f)}
            for f in chosen]


def _index_of(payload: list, field_id: str) -> int:
    for i, f in enumerate(payload):
        if f["field_id"] == field_id:
            return i
    return -1


def _set(payload: list, field_id: str, value: str) -> int:
    """Set a field's value in the payload; return its index (-1 if absent)."""
    i = _index_of(payload, field_id)
    if i >= 0:
        payload[i]["value"] = value
    return i


def _distance(payload: list, id_a: str, id_b: str) -> int:
    ia, ib = _index_of(payload, id_a), _index_of(payload, id_b)
    if ia < 0 or ib < 0:
        return -1
    return abs(ia - ib)


# Real I-90 field ids used for injection (verified present in schema.json).
# Address clusters live in different SECTIONS, so pairing across them yields a
# large, cross-section distance; pairing within one cluster yields a small one.
MAIL_STATE = "p1_line6e_state"
MAIL_ZIP = "p1_line6f_zipcode"
MAIL_COUNTRY = "p1_line6i_country"
MAIL_CITY = "p1_line6d_cityortown"
MAIL_PROV = "p1_line6g_province"
PHYS_CITY = "p1_line7c_cityortown"
PHYS_STATE = "p1_line7d_state"
PHYS_ZIP = "p1_line7e_zipcode"
PHYS_COUNTRY = "p1_line7h_country"
DOB = "p1_line9_dateofbirth"
ADMIT = "p1_line15_dateofadmission"
# Far-apart clusters (later parts) for cross-section distance.
INTERP_STATE = "p6_line3d_state"
INTERP_ZIP = "p6_line3e_zipcode"
PREP_STATE = "p7_line3d_state"
PREP_ZIP = "p7_line3e_zipcode"
# Part 8 "additional information" free-text continuation textareas (verified
# textarea in schema.json, idx ~115-131 -- far from the Part 1 fields, so a Part-1
# vs Part-8 pair has a large cross-section distance). Distinct ids per case so the
# cross_date / duration_year cases never collide.
P8_INFO_A = "p8_line3d_additionalinfo"        # idx 115
P8_INFO_B = "p8_line5d_additionalinfo[1]"     # idx 119
P8_INFO_C = "p8_line4d_additionalinfo"        # idx 123
P8_INFO_D = "p8_line5d_additionalinfo"        # idx 127
P8_INFO_E = "p8_line5d_additionalinfo[2]"     # idx 131

# A SEPARATE, internally-coherent physical address (the applicant's residence),
# deliberately DIFFERENT from the base mailing address (Houston) so that overriding
# the mailing cluster in a contradiction case never creates an UNLABELED
# mailing-vs-physical mismatch (Codex review #5 cousin). Two different-but-each-valid
# addresses is a legitimate clean situation the checker must not flag.
_PHYS_COHERENT = {
    PHYS_CITY: "Austin",
    PHYS_STATE: "TX",
    PHYS_ZIP: "78701",
    PHYS_COUNTRY: "United States",
}


def _set_physical(payload: list) -> None:
    """Set the physical-address cluster to a coherent Austin/TX address (independent
    of any mailing override), when those fields are inside the size window."""
    for fid, val in _PHYS_COHERENT.items():
        _set(payload, fid, val)


def build_corpus(size: int, seed_offset: int = 0) -> list:
    """Build the labeled corpus for one form size.

    Each contradiction case starts from the coherent base state, then injects ONE
    labeled contradiction. Cases are skipped if their fields don't fit in `size`
    (so the 20-field set has fewer far-distance cases than the 132-field set --
    that asymmetry is real and recorded, not hidden).
    """
    all_fields = _load_fields()
    cases: list = []

    # ---- helper to make one contradiction case from a fresh base ----
    def mk(case_suffix, cls, injects, expected, need_ids):
        base = _base_state(all_fields, size)
        # All fields the contradiction depends on must be inside this size window.
        if any(_index_of(base, fid) < 0 for fid in need_ids):
            return None
        # Give the applicant a coherent physical address (Austin) INDEPENDENT of the
        # mailing cluster, so overriding mailing below never creates an unlabeled
        # mailing-vs-physical mismatch (Codex #5 cousin). No-op when physical is out
        # of window. Injects run AFTER, so a case targeting physical still wins.
        _set_physical(base)
        for fid, val in injects:
            _set(base, fid, val)
        # distance = gap between the two implicated fields (first expected pair);
        # single-field => 0.
        ids = list(expected[0])
        dist = _distance(base, ids[0], ids[1]) if len(ids) >= 2 else 0
        return Case(
            case_id=f"s{size}_{case_suffix}",
            size=size, cls=cls, distance=dist,
            fields=base, expected_conflicts=expected,
        )

    # ===== CONTRADICTION CASES =====
    # zip_state -- mailing cluster (small distance, fields adjacent).
    for i, (state, zipc) in enumerate([
        ("West Virginia", "50301"), ("California", "10001"),
        ("Texas", "02134"), ("Florida", "60601"), ("Ohio", "98101"),
    ]):
        c = mk(f"zipstate_near_{i}", "zip_state",
               [(MAIL_STATE, state), (MAIL_ZIP, zipc), (MAIL_COUNTRY, "United States")],
               [{MAIL_STATE, MAIL_ZIP}], [MAIL_STATE, MAIL_ZIP])
        if c:
            cases.append(c)

    # (No "far zip_state" class: pairing the mailing STATE with an interpreter/
    # preparer ZIP is NOT a contradiction -- a preparer's ZIP is a DIFFERENT
    # PERSON's address and can legitimately differ (Codex review #5). Genuine
    # far-distance coverage is the Part-1-vs-Part-8 cross_date / duration_year
    # classes below.)

    # state_country -- the class flash-lite fumbled in G1 (US state + foreign country).
    for i, (state, country) in enumerate([
        ("New York", "Canada"), ("California", "Mexico"),
        ("Texas", "United Kingdom"), ("Illinois", "Germany"),
    ]):
        c = mk(f"statecountry_{i}", "state_country",
               [(MAIL_STATE, state), (MAIL_COUNTRY, country)],
               [{MAIL_STATE, MAIL_COUNTRY}], [MAIL_STATE, MAIL_COUNTRY])
        if c:
            cases.append(c)

    # province_us -- foreign province alongside a US state.
    for i, (prov, state) in enumerate([
        ("Ontario", "New York"), ("Bavaria", "California"), ("Quebec", "Florida"),
    ]):
        c = mk(f"provinceus_{i}", "province_us",
               [(MAIL_STATE, state), (MAIL_PROV, prov), (MAIL_COUNTRY, "United States")],
               [{MAIL_STATE, MAIL_PROV}], [MAIL_STATE, MAIL_PROV])
        if c:
            cases.append(c)

    # city_state -- the genuinely fuzzy world-knowledge class (valid matching zip).
    for i, (city, state, zipc) in enumerate([
        ("Chicago", "Texas", "75001"), ("Miami", "California", "90001"),
        ("Seattle", "Nevada", "89101"), ("Boston", "Ohio", "43201"),
    ]):
        c = mk(f"citystate_{i}", "city_state",
               [(MAIL_CITY, city), (MAIL_STATE, state), (MAIL_ZIP, zipc),
                (MAIL_COUNTRY, "United States")],
               [{MAIL_CITY, MAIL_STATE}], [MAIL_CITY, MAIL_STATE])
        if c:
            cases.append(c)

    # future_dob -- single-field semantic (DOB in the future).
    for i, dob in enumerate(["2031-04-02", "2040-12-25", "2029-01-01"]):
        c = mk(f"futuredob_{i}", "future_dob",
               [(DOB, dob)], [{DOB}], [DOB])
        if c:
            cases.append(c)

    # admission_dob -- admitted before born (cross-field date logic, small dist).
    for i, (dob, admit) in enumerate([
        ("1990-05-10", "1985-01-01"), ("2000-03-15", "1995-07-20"),
    ]):
        c = mk(f"admissiondob_{i}", "admission_dob",
               [(DOB, dob), (ADMIT, admit)],
               [{DOB, ADMIT}], [DOB, ADMIT])
        if c:
            cases.append(c)

    # cross_date (GENUINE) -- the applicant's DATE OF BIRTH (Part 1 line 9) is
    # RESTATED with a DIFFERENT year in a Part 8 additional-info textarea. The two
    # statements of the same fact sit far apart (Part 1 vs Part 8 -> distance >20),
    # so these only fit at size 132 -- the large distance is the whole point.
    for i, (dob, born_year, p8field) in enumerate([
        ("1985-04-12", "1990", P8_INFO_A),
        ("1972-09-30", "1968", P8_INFO_B),
        ("1991-01-05", "1985", P8_INFO_C),
    ]):
        c = mk(f"crossdate_{i}", "cross_date",
               [(DOB, dob), (p8field, f"Applicant was born in {born_year}.")],
               [{DOB, p8field}], [DOB, p8field])
        if c:
            cases.append(c)

    # duration_year (NEW, the maintainer's example) -- a Part 8 additional-info
    # textarea states a length-of-residence that contradicts the date of admission
    # (Part 1 line 15). Also a large Part-1-vs-Part-8 distance; size-132 only.
    for i, (admit, info, p8field) in enumerate([
        ("2020-06-20",
         "I have lived in the United States for over 20 years.", P8_INFO_D),
        ("2022-03-10",
         "I have continuously resided in the U.S. since 1995, more than 25 years.",
         P8_INFO_E),
        ("2021-11-01",
         "Applicant has been a U.S. resident for over 30 years.", P8_INFO_C),
    ]):
        c = mk(f"durationyear_{i}", "duration_year",
               [(ADMIT, admit), (p8field, info)],
               [{ADMIT, p8field}], [ADMIT, p8field])
        if c:
            cases.append(c)

    # ===== CLEAN CASES (precision traps embedded in full state) =====
    # Coherent US mailing address.
    for i, (city, state, zipc) in enumerate([
        ("New York", "New York", "10001"), ("Los Angeles", "California", "90001"),
        ("Houston", "Texas", "77001"), ("Chicago", "Illinois", "60601"),
        ("Seattle", "Washington", "98101"),
    ]):
        base = _base_state(all_fields, size)
        _set_physical(base)
        _set(base, MAIL_CITY, city); _set(base, MAIL_STATE, state)
        _set(base, MAIL_ZIP, zipc); _set(base, MAIL_COUNTRY, "United States")
        cases.append(Case(f"s{size}_clean_us_{i}", size, "clean", 0, base))

    # Coherent foreign mailing address (province + postal + foreign country).
    for i, (city, prov, postal, country) in enumerate([
        ("Toronto", "Ontario", "M5H 2N2", "Canada"),
        ("Munich", "Bavaria", "80331", "Germany"),
        ("Mumbai", "Maharashtra", "400001", "India"),
        ("Manila", "Metro Manila", "1000", "Philippines"),
    ]):
        base = _base_state(all_fields, size)
        _set_physical(base)
        _set(base, MAIL_CITY, city); _set(base, MAIL_STATE, "")
        _set(base, MAIL_PROV, prov); _set(base, MAIL_ZIP, "")
        _set(base, MAIL_COUNTRY, country)
        cases.append(Case(f"s{size}_clean_foreign_{i}", size, "clean", 0, base))

    # US territory ZIPs (valid; naive 50-state checker false-positives).
    for i, (city, state, zipc) in enumerate([
        ("San Juan", "Puerto Rico", "00901"),
        ("Hagatna", "Guam", "96910"),
        ("Charlotte Amalie", "Virgin Islands", "00801"),
    ]):
        base = _base_state(all_fields, size)
        _set_physical(base)
        _set(base, MAIL_CITY, city); _set(base, MAIL_STATE, state)
        _set(base, MAIL_ZIP, zipc); _set(base, MAIL_COUNTRY, "United States")
        cases.append(Case(f"s{size}_clean_territory_{i}", size, "clean", 0, base))

    # Dual coherent addresses (mailing + physical, both valid but different) --
    # only meaningful when the physical cluster fits in the size window.
    for i, (mail, phys) in enumerate([
        (("New York", "New York", "10001"), ("Newark", "New Jersey", "07101")),
        (("Chicago", "Illinois", "60601"), ("Milwaukee", "Wisconsin", "53201")),
    ]):
        base = _base_state(all_fields, size)
        if _index_of(base, PHYS_STATE) < 0:
            continue
        _set(base, MAIL_CITY, mail[0]); _set(base, MAIL_STATE, mail[1]); _set(base, MAIL_ZIP, mail[2])
        # physical = a coherent city/state/zip of its own (distinct from mailing)
        _set(base, PHYS_CITY, phys[0]); _set(base, PHYS_STATE, phys[1]); _set(base, PHYS_ZIP, phys[2])
        _set(base, MAIL_COUNTRY, "United States")
        cases.append(Case(f"s{size}_clean_dual_{i}", size, "clean", 0, base))

    # Plain coherent baseline (the persona as-is, no injection) -- the densest
    # clean case, the strongest false-positive trap at full size.
    cases.append(Case(f"s{size}_clean_baseline_0", size, "clean", 0,
                      _base_state(all_fields, size)))

    return cases


if __name__ == "__main__":
    from collections import Counter
    for size in (20, 40, 132):
        corpus = build_corpus(size)
        nc = sum(1 for c in corpus if c.is_contradiction)
        cl = len(corpus) - nc
        dists = [c.distance for c in corpus if c.is_contradiction]
        print(f"size={size:>3}: {len(corpus)} cases = {nc} contradiction + {cl} clean; "
              f"distances min/max = {min(dists)}/{max(dists)}")
        print(f"          classes: {dict(Counter(c.cls for c in corpus if c.is_contradiction))}")

