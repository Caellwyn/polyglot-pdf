"""G1b bake-off corpus -- full-size labeled form states over a VALIDATED clean key.

bd polyglot-pdf-0zp3 (the bake-off) + polyglot-pdf-wf3q (the clean answer key).
This builds REALISTIC FULL-SIZE form states (20 / 40 / 132 fields) so the
out-of-band checker is measured the way it actually runs: a contradiction buried
in a page- or form-sized payload of coherent noise, not in isolation.

CLEAN BASE = THE VALIDATED ANSWER KEY (g1b_answer_key.py)
The clean form state is no longer mechanically filled (the old _filler /
option[0] approach manufactured unlabeled contradictions -- name-change="Yes"
with identical names, English-self-cert with an interpreter populated, full state
names instead of abbreviations -- which a good checker correctly flagged but the
corpus scored as false positives, so precision was untrustworthy: 86 of 128
clean-case false positives were these artifacts). The base is now the
HAND-VALIDATED, self-reviewed coherent persona in g1b_answer_key.ANSWER_KEY
(field_id -> value; NA fields explicitly None, omitted from the payload). See that
module's docstring for the persona and the coherence invariants.

PROVENANCE: SYNTHETIC. The field IDs / spoken names / types / section ids are REAL
(the 132 fields of form-kits/i-90/schema.json in document order). The VALUES are a
hand-authored coherent persona; the contradictions are deliberately injected. No
real user transcripts exist (pre-pilot, no PII logged). Recall numbers are an
UPPER BOUND on real-world recall.

132 = the real full I-90 (the realistic worst case; we do NOT synthesize a 200-pad
-- a real form at its real length is the honest worst case). 20 ~ a section, 40 ~ a
page. Sizes are produced by taking the first N fields in document order, then
injecting a contradiction that fits inside that window.

Each case is a contract-2-style payload: a list of {field_id, name, value} for the
FILLED fields (NA / empty fields are omitted, as in production). Labels: the
field-id set(s) that SHOULD be flagged, plus per-case metadata -- the
contradiction CLASS and the DISTANCE (how many filled fields apart the two
contradicting fields sit in payload order; 0 for single-field/clean).

Contradiction CLASSES (the bake-off's taxonomy):
  zip_state, state_country, province_us, city_state, future_dob, admission_dob,
  plus two GENUINE far-apart same-fact classes pairing a Part 1 field against a
  Part 8 "additional information" free-text continuation textarea (a real
  cross-section gap, distance >20 at size 132, so they only fit in the 132-field
  window):
  cross_date     -- the applicant's DATE OF BIRTH (Part 1 line 9) is RESTATED with
                    a DIFFERENT year in a Part 8 additional-info textarea.
  duration_year  -- a Part 8 additional-info textarea states a length-of-residence
                    that contradicts the date of admission (Part 1 line 15).
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field

from backend.scripts.g1b_answer_key import ANSWER_KEY, load_schema_fields


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
    """First `size` fields in document order, filled from the VALIDATED answer key.
    NA fields (ANSWER_KEY value None) are omitted -- exactly as production omits
    empty fields -- so the payload carries only coherent, filled values. Returns a
    list of mutable {field_id, name, value} dicts."""
    out = []
    for f in all_fields[:size]:
        val = ANSWER_KEY.get(f["field_id"])
        if val is None:
            continue  # NA / conditional-hidden -> omitted from the payload
        out.append({"field_id": f["field_id"], "name": f["name"], "value": val})
    return out


def _index_of(payload: list, field_id: str) -> int:
    for i, f in enumerate(payload):
        if f["field_id"] == field_id:
            return i
    return -1


def _set(payload: list, field_id: str, value: str) -> int:
    """Set a field's value in the payload (appending it if absent but the field is
    one that belongs in this window). Returns its index, or -1 if it could not be
    placed. A contradiction injected into a normally-NA field (e.g. a Part 8
    free-text restatement) must be ADDED to the payload, since the clean base omits
    NA fields."""
    i = _index_of(payload, field_id)
    if i >= 0:
        payload[i]["value"] = value
    return i


def _add(payload: list, all_fields: list, field_id: str, value: str, size: int) -> int:
    """Inject a value into a field that the clean base OMITS (it is NA for the
    persona). Only valid if the field is within the first `size` fields in document
    order; inserts it at its document-order position so distance stays meaningful.
    Returns the new index, or -1 if the field is outside the size window."""
    order = {f["field_id"]: idx for idx, f in enumerate(all_fields)}
    if field_id not in order or order[field_id] >= size:
        return -1
    if _index_of(payload, field_id) >= 0:
        return _set(payload, field_id, value)
    name = next((f["name"] for f in all_fields if f["field_id"] == field_id), field_id)
    # insert at the right document-order slot so the payload stays in order
    target_doc = order[field_id]
    insert_at = len(payload)
    for i, f in enumerate(payload):
        if order.get(f["field_id"], 10**9) > target_doc:
            insert_at = i
            break
    payload.insert(insert_at, {"field_id": field_id, "name": name, "value": value})
    return _index_of(payload, field_id)


def _distance(payload: list, id_a: str, id_b: str) -> int:
    ia, ib = _index_of(payload, id_a), _index_of(payload, id_b)
    if ia < 0 or ib < 0:
        return -1
    return abs(ia - ib)


# Real I-90 field ids used for injection (verified present in schema.json).
MAIL_STREET = "p1_line6b_streetnumbername"
MAIL_STATE = "p1_line6e_state"
MAIL_ZIP = "p1_line6f_zipcode"
MAIL_COUNTRY = "p1_line6i_country"
MAIL_CITY = "p1_line6d_cityortown"
MAIL_PROV = "p1_line6g_province"
MAIL_POSTAL = "p1_line6h_postalcode"
PHYS_STREET = "p1_line7a_streetnumbername"
PHYS_CITY = "p1_line7c_cityortown"
PHYS_STATE = "p1_line7d_state"
PHYS_ZIP = "p1_line7e_zipcode"
PHYS_COUNTRY = "p1_line7h_country"
DOB = "p1_line9_dateofbirth"
ADMIT = "p1_line15_dateofadmission"
# Part 8 "additional information" free-text continuation textareas (verified
# textarea in schema.json, idx ~115-131 -- far from the Part 1 fields, so a Part-1
# vs Part-8 pair has a large cross-section distance). In the clean base these are
# NA (omitted); a cross_date / duration_year mutant ADDS one. Distinct ids per
# case so the cases never collide.
P8_INFO_A = "p8_line3d_additionalinfo"        # idx 115
P8_INFO_B = "p8_line5d_additionalinfo[1]"     # idx 119
P8_INFO_C = "p8_line4d_additionalinfo"        # idx 123
P8_INFO_D = "p8_line5d_additionalinfo"        # idx 127
P8_INFO_E = "p8_line5d_additionalinfo[2]"     # idx 131


def build_corpus(size: int) -> list:
    """Build the labeled corpus for one form size.

    Each contradiction case starts from the VALIDATED clean base, then injects ONE
    labeled contradiction. Cases are skipped if their fields don't fit in `size`
    (so the 20-field set has fewer far-distance cases than the 132-field set --
    that asymmetry is real and recorded, not hidden).
    """
    all_fields = load_schema_fields()
    cases: list = []

    def mk(case_suffix, cls, injects, expected, need_ids, add_ids=()):
        """Make one contradiction case. `injects` are (field_id, value) pairs set on
        fields the clean base already fills; `add_ids` lists fields that are NA in
        the clean base and must be ADDED (e.g. a Part 8 free-text restatement).
        Returns None if any needed field is outside the size window."""
        base = _base_state(all_fields, size)
        # NA fields we will ADD must be inside the window.
        for fid, val in injects:
            if fid in add_ids:
                if _add(base, all_fields, fid, val, size) < 0:
                    return None
            else:
                if _set(base, fid, val) < 0:
                    return None
        # All implicated fields must be present in the payload now.
        if any(_index_of(base, fid) < 0 for fid in need_ids):
            return None
        ids = list(expected[0])
        dist = _distance(base, ids[0], ids[1]) if len(ids) >= 2 else 0
        return Case(
            case_id=f"s{size}_{case_suffix}",
            size=size, cls=cls, distance=dist,
            fields=base, expected_conflicts=expected,
        )

    # ===== CONTRADICTION CASES =====
    # Each address-injection case ALSO overrides the mailing CITY to one coherent
    # with the injected state, so the ONLY contradiction is the labeled one. (The
    # validated base city is Houston/TX; injecting a non-TX state while leaving
    # "Houston" would create a SECOND, unlabeled city-vs-state contradiction --
    # fresh-eyes finding, PR for wf3q.) The chosen city is a real city IN the
    # injected state, so {city, state} is coherent and only {state, zip} (or
    # {state, country} / {state, province}) is wrong.

    # zip_state -- mailing cluster (small distance, fields adjacent).
    for i, (city, state, zipc) in enumerate([
        ("Charleston", "WV", "50301"), ("Sacramento", "CA", "10001"),
        ("Austin", "TX", "02134"), ("Orlando", "FL", "60601"),
        ("Columbus", "OH", "98101"),
    ]):
        c = mk(f"zipstate_near_{i}", "zip_state",
               [(MAIL_CITY, city), (MAIL_STATE, state), (MAIL_ZIP, zipc),
                (MAIL_COUNTRY, "United States")],
               [{MAIL_STATE, MAIL_ZIP}], [MAIL_STATE, MAIL_ZIP])
        if c:
            cases.append(c)

    # state_country -- US state filled together with a foreign country. The city is
    # set coherent with the US state; only {state, country} is the contradiction.
    for i, (city, state, country) in enumerate([
        ("Albany", "NY", "Canada"), ("Sacramento", "CA", "Mexico"),
        ("Austin", "TX", "United Kingdom"), ("Springfield", "IL", "Germany"),
    ]):
        c = mk(f"statecountry_{i}", "state_country",
               [(MAIL_CITY, city), (MAIL_STATE, state), (MAIL_COUNTRY, country)],
               [{MAIL_STATE, MAIL_COUNTRY}], [MAIL_STATE, MAIL_COUNTRY])
        if c:
            cases.append(c)

    # province_us -- foreign province alongside a US state (province is NA in the
    # clean base, so it must be ADDED). City coherent with the US state; only
    # {state, province} is the contradiction.
    for i, (city, prov, state) in enumerate([
        ("Albany", "Ontario", "NY"), ("Sacramento", "Bavaria", "CA"),
        ("Orlando", "Quebec", "FL"),
    ]):
        c = mk(f"provinceus_{i}", "province_us",
               [(MAIL_CITY, city), (MAIL_STATE, state), (MAIL_PROV, prov),
                (MAIL_COUNTRY, "United States")],
               [{MAIL_STATE, MAIL_PROV}], [MAIL_STATE, MAIL_PROV],
               add_ids=(MAIL_PROV,))
        if c:
            cases.append(c)

    # city_state -- a US city that is not located in the stated US state (valid
    # matching zip for the WRONG state, so only the city<->state pair is the flag).
    for i, (city, state, zipc) in enumerate([
        ("Chicago", "TX", "75001"), ("Miami", "CA", "90001"),
        ("Seattle", "NV", "89101"), ("Boston", "OH", "43201"),
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

    # cross_date (GENUINE far-apart) -- the applicant's DATE OF BIRTH (Part 1 line
    # 9) is RESTATED with a DIFFERENT year in a Part 8 additional-info textarea
    # (NA in the clean base -> ADDED). Part 1 vs Part 8 -> distance >20, so these
    # only fit at size 132 -- the large distance is the whole point.
    for i, (dob, born_year, p8field) in enumerate([
        ("1985-04-12", "1990", P8_INFO_A),
        ("1972-09-30", "1968", P8_INFO_B),
        ("1991-01-05", "1985", P8_INFO_C),
    ]):
        c = mk(f"crossdate_{i}", "cross_date",
               [(DOB, dob), (p8field, f"Applicant was born in {born_year}.")],
               [{DOB, p8field}], [DOB, p8field], add_ids=(p8field,))
        if c:
            cases.append(c)

    # duration_year (the maintainer's example) -- a Part 8 additional-info textarea
    # (NA in the clean base -> ADDED) states a length-of-residence that contradicts
    # the date of admission (Part 1 line 15). Large Part-1-vs-Part-8 distance.
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
               [{ADMIT, p8field}], [ADMIT, p8field], add_ids=(p8field,))
        if c:
            cases.append(c)

    # ===== CLEAN CASES (precision traps embedded in full validated state) =====
    # Each starts from the validated base and applies a COHERENT address variant
    # (street + city + state + zip + country all mutually consistent), so a good
    # checker must NOT flag it. These are the false-positive traps.
    def clean(case_suffix, mutations):
        base = _base_state(all_fields, size)
        ok = True
        for fid, val in mutations:
            # a clean mutation only ever sets an already-present (filled) field;
            # if it is out of window, skip this case so we never emit a half-applied
            # address (which could itself be an artifact).
            if _set(base, fid, val) < 0:
                ok = False
                break
        if not ok:
            return None
        return Case(f"s{size}_{case_suffix}", size, "clean", 0, base)

    # Coherent US mailing address (street kept consistent with the new city/state).
    for i, (street, city, state, zipc) in enumerate([
        ("123 Main St", "New York", "NY", "10001"),
        ("742 Sunset Blvd", "Los Angeles", "CA", "90001"),
        ("88 Commerce St", "Houston", "TX", "77001"),
        ("400 Michigan Ave", "Chicago", "IL", "60601"),
        ("55 Pine St", "Seattle", "WA", "98101"),
    ]):
        c = clean(f"clean_us_{i}", [
            (MAIL_STREET, street), (MAIL_CITY, city), (MAIL_STATE, state),
            (MAIL_ZIP, zipc), (MAIL_COUNTRY, "United States"),
            # keep physical == mailing so the dual-address invariant stays coherent
            (PHYS_STREET, street), (PHYS_CITY, city), (PHYS_STATE, state),
            (PHYS_ZIP, zipc), (PHYS_COUNTRY, "United States"),
        ])
        if c:
            cases.append(c)

    # Coherent FOREIGN mailing address (province + postal + foreign country, NO US
    # state). State is cleared to "" and province/postal ADDED -- a legitimate
    # foreign-address shape the checker must not flag. (Physical stays the US
    # Houston address: a foreign mailing + US physical is a coherent dual address.)
    def clean_foreign(case_suffix, city, prov, postal, country):
        base = _base_state(all_fields, size)
        if _index_of(base, MAIL_STATE) < 0:
            return None
        _set(base, MAIL_STREET, "10 King St")
        _set(base, MAIL_CITY, city)
        _set(base, MAIL_STATE, "")           # no US state for a foreign address
        _add(base, all_fields, MAIL_PROV, prov, size)
        _add(base, all_fields, MAIL_POSTAL, postal, size)
        _set(base, MAIL_ZIP, "")             # no US zip for a foreign address
        _set(base, MAIL_COUNTRY, country)
        # drop the now-empty US state/zip from the payload (production omits empties)
        base[:] = [f for f in base if f["value"] not in ("", None)]
        return Case(f"s{size}_{case_suffix}", size, "clean", 0, base)

    for i, (city, prov, postal, country) in enumerate([
        ("Toronto", "Ontario", "M5H 2N2", "Canada"),
        ("Munich", "Bavaria", "80331", "Germany"),
        ("Mumbai", "Maharashtra", "400001", "India"),
        ("Manila", "Metro Manila", "1000", "Philippines"),
    ]):
        c = clean_foreign(f"clean_foreign_{i}", city, prov, postal, country)
        if c:
            cases.append(c)

    # US territory ZIPs (valid; a naive 50-state checker false-positives). The
    # territory is carried in the COUNTRY/city free text since the state picker has
    # no territory option -- mirrors how the real form handles territories.
    for i, (city, territory, zipc) in enumerate([
        ("San Juan", "Puerto Rico", "00901"),
        ("Hagatna", "Guam", "96910"),
        ("Charlotte Amalie", "U.S. Virgin Islands", "00801"),
    ]):
        base = _base_state(all_fields, size)
        if _index_of(base, MAIL_STATE) < 0:
            continue
        _set(base, MAIL_STREET, "1 Plaza St")
        _set(base, MAIL_CITY, city)
        _set(base, MAIL_STATE, "")           # territory has no 50-state code
        _set(base, MAIL_ZIP, zipc)
        _set(base, MAIL_COUNTRY, f"United States ({territory})")
        # physical == this territory address (a no-op when the physical cluster is
        # outside the size window -- at size 20 only the mailing territory address
        # is in the payload, which is still coherent)
        _set(base, PHYS_STREET, "1 Plaza St")
        _set(base, PHYS_CITY, city)
        _set(base, PHYS_STATE, "")
        _set(base, PHYS_ZIP, zipc)
        _set(base, PHYS_COUNTRY, f"United States ({territory})")
        base[:] = [f for f in base if f["value"] not in ("", None)]
        cases.append(Case(f"s{size}_clean_territory_{i}", size, "clean", 0, base))

    # Dual coherent addresses (mailing + physical, both valid but DIFFERENT) -- a
    # legitimate clean situation the checker must not flag. Only meaningful when the
    # physical cluster fits in the size window.
    for i, (mail, phys) in enumerate([
        (("123 Main St", "New York", "NY", "10001"),
         ("9 Market St", "Newark", "NJ", "07101")),
        (("400 Michigan Ave", "Chicago", "IL", "60601"),
         ("12 Water St", "Milwaukee", "WI", "53201")),
    ]):
        base = _base_state(all_fields, size)
        if _index_of(base, PHYS_STATE) < 0:
            continue
        _set(base, MAIL_STREET, mail[0]); _set(base, MAIL_CITY, mail[1])
        _set(base, MAIL_STATE, mail[2]); _set(base, MAIL_ZIP, mail[3])
        _set(base, MAIL_COUNTRY, "United States")
        _set(base, PHYS_STREET, phys[0]); _set(base, PHYS_CITY, phys[1])
        _set(base, PHYS_STATE, phys[2]); _set(base, PHYS_ZIP, phys[3])
        _set(base, PHYS_COUNTRY, "United States")
        cases.append(Case(f"s{size}_clean_dual_{i}", size, "clean", 0, base))

    # Plain coherent baseline (the validated persona as-is, no mutation) -- the
    # densest clean case, the strongest false-positive trap at full size.
    cases.append(Case(f"s{size}_clean_baseline_0", size, "clean", 0,
                      _base_state(all_fields, size)))

    return [c for c in cases if c is not None]


if __name__ == "__main__":
    from collections import Counter
    for size in (20, 40, 132):
        corpus = build_corpus(size)
        nc = sum(1 for c in corpus if c.is_contradiction)
        cl = len(corpus) - nc
        dists = [c.distance for c in corpus if c.is_contradiction]
        dmin = min(dists) if dists else 0
        dmax = max(dists) if dists else 0
        print(f"size={size:>3}: {len(corpus)} cases = {nc} contradiction + {cl} clean; "
              f"distances min/max = {dmin}/{dmax}")
        print(f"          classes: {dict(Counter(c.cls for c in corpus if c.is_contradiction))}")
