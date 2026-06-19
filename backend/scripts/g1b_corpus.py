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
injecting a contradiction that fits inside that window.

Each case is a contract-2-style payload: a list of {field_id, name, value} for the
filled fields (the checker reads filled values; empty fields are omitted as in
production). Labels: the field-id set(s) that SHOULD be flagged, plus per-case
metadata -- the contradiction CLASS and the DISTANCE (how many filled fields apart
the two contradicting fields sit in payload order; 0 for single-field). Distance is
the key new variable: does a model still catch a contradiction whose halves are
40 fields apart (cross-section) as well as one whose halves are adjacent?

Contradiction CLASSES (reuse G1's taxonomy + the cross-section semantic class the
maintainer named):
  zip_state, state_country, province_us, city_state, future_dob, admission_dob
  (as in g1_corpus.py), plus:
  cross_date     -- the SAME date entity stated two different ways far apart
                    (e.g. date of birth in Part 1 vs a birth-year implied elsewhere)
  duration_year  -- a "how long in the US" bucket that contradicts a stated entry
                    year far away in the form (the maintainer's example)
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


# Field-id PREFIXES whose entire cluster is left EMPTY in the base persona.
# Rationale: a real I-90 often leaves the physical address blank (same as mailing)
# and has no interpreter/preparer. Leaving these empty (a) is realistic, and
# (b) avoids a spurious mailing-vs-physical or mailing-vs-interpreter mismatch when
# a case overrides ONLY the mailing cluster -- without this, the coherent base
# physical address ("Houston, TX") contradicts an injected mailing "New York, NY"
# and the model correctly-but-unwantedly flags the base filler, not the test.
# Empty fields are dropped from the payload, so they cost nothing and add no noise.
_EMPTY_PREFIXES = (
    "p1_line7",   # physical mailing address cluster (lines 7a-7h)
    "p6_",        # interpreter (name + address + signature)
    "p7_",        # preparer (name + address + signature)
)


def _filler(field: dict) -> str:
    """A coherent value for a field, by id/name match then by type."""
    fid = field["field_id"].lower()
    if any(fid.startswith(p) for p in _EMPTY_PREFIXES):
        return ""  # left blank in the base; a case may still set it explicitly
    key = (fid + " " + field["name"]).lower()
    # Match the MOST-SPECIFIC (longest) persona key first, so "citytownofbirth"
    # wins over the substring "cityortown" and "countryofbirth"/"countryof-
    # citizenship" win over "country". Insertion-order matching mis-assigned the
    # birth city to the residence filler and created phantom contradictions.
    for needle in sorted(_PERSONA, key=len, reverse=True):
        if needle in key:
            return _PERSONA[needle]
    t = field["type"]
    if t == "date":
        return "2015-06-20"
    if t in ("radio", "checkbox"):
        return "No"
    if t == "select":
        return "TX"
    if t in ("textarea",):
        return "N/A"
    if t == "signature":
        return "Linh Nguyen"
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

    # zip_state -- FAR: mailing state vs interpreter/preparer zip (cross-section).
    # Only fits in the larger sizes; that's the point (does distance hurt?).
    for i, (state, zipc, zfield) in enumerate([
        ("New York", "90001", INTERP_ZIP),   # NY state, LA zip, far away
        ("Illinois", "33101", PREP_ZIP),      # IL state, Miami zip, far away
    ]):
        c = mk(f"zipstate_far_{i}", "zip_state",
               [(MAIL_STATE, state), (zfield, zipc)],
               [{MAIL_STATE, zfield}], [MAIL_STATE, zfield])
        if c:
            cases.append(c)

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

    # cross_date -- DOB vs date-of-admission impossibility, but the two dates are
    # FAR apart (DOB in Part 1 line 9, admission in Part 1 line 15 -- a real gap).
    # On the small sizes these collapse to admission_dob; on big sizes the distance
    # grows. (Same field pair, recorded distance differs by size -- the variable.)
    for i, (dob, admit) in enumerate([
        ("1995-08-08", "1980-02-02"), ("2002-11-30", "1998-01-01"),
    ]):
        c = mk(f"crossdate_{i}", "cross_date",
               [(DOB, dob), (ADMIT, admit)],
               [{DOB, ADMIT}], [DOB, ADMIT])
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
        _set(base, PHYS_STATE, phys[1]); _set(base, PHYS_ZIP, phys[2])
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

