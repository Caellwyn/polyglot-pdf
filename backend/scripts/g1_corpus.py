"""G1 keystone probe corpus -- labeled contradiction / clean cases.

PROVENANCE (state it, don't fudge it -- bd polyglot-pdf-jnjj.5):
  This corpus is **SYNTHETIC INJECTION**, NOT real user transcripts. There is no
  captured-transcript corpus for this project yet (the demo is pre-pilot; we log
  NO field values server-side per the PII policy, so there is nothing to mine).
  Every case here is hand-authored. The field IDs, spoken names, and field types
  are REAL -- pulled verbatim from form-kits/i-90/schema.json (the address and
  date clusters in Parts 1/6/7) -- but the VALUES and the contradictions are
  fabricated.

  Implication for the GO decision (the bead's own warning): textbook
  zip-vs-state cases OVERSTATE flash-lite recall, because a synthetic injection
  is cleaner and more on-distribution for a world-knowledge model than the messy,
  half-filled, mid-correction state a real session produces. Read every recall
  number here as an UPPER BOUND on real-world recall, not an estimate of it. The
  GO threshold is set with that inflation in mind (see the findings doc).

Each case is a contract-2 minimal client-state payload
(docs/standards/validation-delegation.md contract 2): a list of
{field_id, name, value, steered} dicts -- exactly what the validator reads at a
boundary. The label is the SET of field_id-sets that SHOULD be flagged
(ground truth). A clean case has an empty label set.

Contradiction CLASSES covered (the classes the in-SI prose claims to catch, plus
the single-field semantic class the verdict shape explicitly allows):
  - zip_state      US ZIP that does not belong to the stated US state
  - state_country  US state filled but country is foreign (or vice versa)
  - province_us    foreign-style province filled alongside a US state/ZIP
  - city_state     US city that is not in the stated state (weaker world-knowledge)
  - future_dob     single-field: date of birth in the future
  - admission_dob  date of admission earlier than date of birth (cross-field, dates)

CLEAN classes (the precision traps -- cases that look address-y but are coherent,
including ones a naive checker might false-positive on):
  - coherent US address
  - coherent foreign address (province + postal + country, NO us state/zip)
  - sparse address (only city filled -- nothing to contradict)
  - US territory ZIP (PR/GU/VI -- valid, a naive 50-state checker may trip)
  - dual address blocks (mailing + physical both coherent but different)
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field


def _f(field_id: str, name: str, value: str, steered: bool = False) -> dict:
    return {"field_id": field_id, "name": name, "value": value, "steered": steered}


@dataclass
class Case:
    case_id: str
    cls: str  # contradiction/clean class label
    fields: list  # contract-2 payload
    # Ground truth: list of field-id SETS that should be flagged. Empty => clean.
    expected_conflicts: list = dc_field(default_factory=list)

    @property
    def is_contradiction(self) -> bool:
        return len(self.expected_conflicts) > 0


# Real I-90 mailing-address cluster (Part 1, lines 6b-6i).
M_STREET = ("p1_line6b_streetnumbername", "mailing address street number and name")
M_CITY = ("p1_line6d_cityortown", "mailing city or town")
M_STATE = ("p1_line6e_state", "mailing state")
M_ZIP = ("p1_line6f_zipcode", "mailing zip code")
M_PROV = ("p1_line6g_province", "mailing province")
M_POSTAL = ("p1_line6h_postalcode", "mailing postal code")
M_COUNTRY = ("p1_line6i_country", "mailing country")
# Physical-address cluster (Part 1, lines 7a-7h).
P_CITY = ("p1_line7c_cityortown", "physical city or town")
P_STATE = ("p1_line7d_state", "physical state")
P_ZIP = ("p1_line7e_zipcode", "physical zip code")
P_COUNTRY = ("p1_line7h_country", "physical country")
# Dates.
DOB = ("p1_line9_dateofbirth", "date of birth")
ADMIT = ("p1_line15_dateofadmission", "date of admission")
BIRTH_COUNTRY = ("p1_line11_countryofbirth", "country of birth")


def build_corpus() -> list:
    cases: list = []

    # ===================== CONTRADICTION CASES =====================

    # --- zip_state: US ZIP not in the stated US state (the canonical case) ---
    zip_state_data = [
        # (state, wrong-zip, real-zip-state) -- ZIP belongs to a DIFFERENT state.
        ("West Virginia", "50301", "Iowa"),      # the doc's own example
        ("California", "10001", "New York"),
        ("Texas", "02134", "Massachusetts"),
        ("Florida", "60601", "Illinois"),
        ("Ohio", "98101", "Washington"),
        ("Georgia", "85001", "Arizona"),
        ("Michigan", "30301", "Georgia"),
        ("Virginia", "97201", "Oregon"),
        ("Colorado", "33101", "Florida"),
        ("Arizona", "43201", "Ohio"),
        ("New York", "90001", "California"),
        ("Pennsylvania", "77001", "Texas"),
        ("North Carolina", "80201", "Colorado"),
        ("Tennessee", "10002", "New York"),
    ]
    for i, (state, zipc, _real) in enumerate(zip_state_data):
        cases.append(Case(
            case_id=f"zip_state_{i}",
            cls="zip_state",
            fields=[
                _f(*M_STREET, "123 Main St"),
                _f(*M_CITY, "Springfield"),
                _f(*M_STATE, state),
                _f(*M_ZIP, zipc),
                _f(*M_COUNTRY, "United States"),
            ],
            expected_conflicts=[{M_STATE[0], M_ZIP[0]}],
        ))

    # --- state_country: a US state filled but country is foreign ---
    state_country_data = [
        ("New York", "Canada"),
        ("California", "Mexico"),
        ("Texas", "United Kingdom"),
        ("Illinois", "Germany"),
        ("Arizona", "India"),
    ]
    for i, (state, country) in enumerate(state_country_data):
        cases.append(Case(
            case_id=f"state_country_{i}",
            cls="state_country",
            fields=[
                _f(*M_CITY, "Toronto" if country == "Canada" else "Citytown"),
                _f(*M_STATE, state),
                _f(*M_COUNTRY, country),
            ],
            expected_conflicts=[{M_STATE[0], M_COUNTRY[0]}],
        ))

    # --- province_us: foreign province filled alongside a US state ---
    province_us_data = [
        ("Ontario", "New York"),
        ("Bavaria", "California"),
        ("Quebec", "Florida"),
        ("Jalisco", "Texas"),
        ("Maharashtra", "Illinois"),
    ]
    for i, (prov, state) in enumerate(province_us_data):
        cases.append(Case(
            case_id=f"province_us_{i}",
            cls="province_us",
            fields=[
                _f(*M_CITY, "Citytown"),
                _f(*M_STATE, state),
                _f(*M_PROV, prov),
                _f(*M_COUNTRY, "United States"),
            ],
            expected_conflicts=[{M_STATE[0], M_PROV[0]}],
        ))

    # --- city_state: US city not in the stated state (weaker world knowledge).
    #     The ZIP here MATCHES the stated state, so the ONLY contradiction is
    #     city-vs-state -- a checker cannot "detect" via a ZIP-vs-state path and
    #     get credit for the wrong capability (fresh-eyes finding 1, PR re-run).
    city_state_data = [
        # (city, state, state-matching ZIP)  -- city is NOT in that state.
        ("Chicago", "Texas", "75001"),         # TX zip, but Chicago is in IL
        ("Miami", "California", "90001"),       # CA zip, but Miami is in FL
        ("Seattle", "Nevada", "89101"),         # NV zip, but Seattle is in WA
        ("Boston", "Ohio", "43201"),            # OH zip, but Boston is in MA
    ]
    for i, (city, state, zipc) in enumerate(city_state_data):
        cases.append(Case(
            case_id=f"city_state_{i}",
            cls="city_state",
            fields=[
                _f(*M_CITY, city),
                _f(*M_STATE, state),
                _f(*M_ZIP, zipc),
                _f(*M_COUNTRY, "United States"),
            ],
            expected_conflicts=[{M_CITY[0], M_STATE[0]}],
        ))

    # --- future_dob: single-field semantic error (verdict allows 1 field_id) ---
    for i, dob in enumerate(["2031-04-02", "2040-12-25", "2029-01-01"]):
        cases.append(Case(
            case_id=f"future_dob_{i}",
            cls="future_dob",
            fields=[
                _f(*DOB, dob),
                _f(*BIRTH_COUNTRY, "Mexico"),
            ],
            expected_conflicts=[{DOB[0]}],
        ))

    # --- admission_dob: admitted before born (cross-field date logic) ---
    admission_dob_data = [
        ("1990-05-10", "1985-01-01"),  # admitted 1985, born 1990 -> impossible
        ("2000-03-15", "1995-07-20"),
        ("1988-11-30", "1980-02-02"),
    ]
    for i, (dob, admit) in enumerate(admission_dob_data):
        cases.append(Case(
            case_id=f"admission_dob_{i}",
            cls="admission_dob",
            fields=[
                _f(*DOB, dob),
                _f(*ADMIT, admit),
                _f(*BIRTH_COUNTRY, "Philippines"),
            ],
            expected_conflicts=[{DOB[0], ADMIT[0]}],
        ))

    # ===================== CLEAN CASES (precision traps) =====================

    # --- coherent US addresses (ZIP matches state) ---
    coherent_us = [
        ("New York", "New York", "10001"),
        ("Los Angeles", "California", "90001"),
        ("Houston", "Texas", "77001"),
        ("Chicago", "Illinois", "60601"),
        ("Phoenix", "Arizona", "85001"),
        ("Seattle", "Washington", "98101"),
        ("Boston", "Massachusetts", "02134"),
        ("Miami", "Florida", "33101"),
        ("Denver", "Colorado", "80201"),
        ("Atlanta", "Georgia", "30301"),
        ("Portland", "Oregon", "97201"),
        ("Columbus", "Ohio", "43201"),
        ("Philadelphia", "Pennsylvania", "19101"),
        ("Detroit", "Michigan", "48201"),
        ("Nashville", "Tennessee", "37201"),
        ("Charlotte", "North Carolina", "28201"),
    ]
    for i, (city, state, zipc) in enumerate(coherent_us):
        cases.append(Case(
            case_id=f"clean_us_{i}",
            cls="clean_us",
            fields=[
                _f(*M_STREET, "123 Main St"),
                _f(*M_CITY, city),
                _f(*M_STATE, state),
                _f(*M_ZIP, zipc),
                _f(*M_COUNTRY, "United States"),
            ],
        ))

    # --- coherent foreign addresses (province + postal + country, NO us state) ---
    coherent_foreign = [
        ("Toronto", "Ontario", "M5H 2N2", "Canada"),
        ("Munich", "Bavaria", "80331", "Germany"),
        ("Mumbai", "Maharashtra", "400001", "India"),
        ("Manila", "Metro Manila", "1000", "Philippines"),
        ("London", "England", "SW1A 1AA", "United Kingdom"),
        ("Sydney", "New South Wales", "2000", "Australia"),
        ("Guadalajara", "Jalisco", "44100", "Mexico"),
        ("Lagos", "Lagos", "100001", "Nigeria"),
        ("Paris", "Ile-de-France", "75001", "France"),
        ("Tokyo", "Tokyo", "100-0001", "Japan"),
        ("Sao Paulo", "Sao Paulo", "01000-000", "Brazil"),
        ("Seoul", "Seoul", "04524", "South Korea"),
    ]
    for i, (city, prov, postal, country) in enumerate(coherent_foreign):
        cases.append(Case(
            case_id=f"clean_foreign_{i}",
            cls="clean_foreign",
            fields=[
                _f(*M_CITY, city),
                _f(*M_PROV, prov),
                _f(*M_POSTAL, postal),
                _f(*M_COUNTRY, country),
            ],
        ))

    # --- sparse: only a couple of fields, nothing to contradict ---
    sparse = [
        [_f(*M_CITY, "Springfield")],
        [_f(*M_STREET, "456 Oak Ave"), _f(*M_CITY, "Madison")],
        [_f(*M_COUNTRY, "United States")],
        [_f(*DOB, "1990-05-10")],
        [_f(*BIRTH_COUNTRY, "Mexico")],
    ]
    for i, fields in enumerate(sparse):
        cases.append(Case(case_id=f"clean_sparse_{i}", cls="clean_sparse", fields=fields))

    # --- US territory ZIPs (valid; a naive 50-state checker false-positives) ---
    territory = [
        ("San Juan", "Puerto Rico", "00901"),
        ("Hagatna", "Guam", "96910"),
        ("Charlotte Amalie", "Virgin Islands", "00801"),
    ]
    for i, (city, state, zipc) in enumerate(territory):
        cases.append(Case(
            case_id=f"clean_territory_{i}",
            cls="clean_territory",
            fields=[
                _f(*M_CITY, city),
                _f(*M_STATE, state),
                _f(*M_ZIP, zipc),
                _f(*M_COUNTRY, "United States"),
            ],
        ))

    # --- dual address blocks: mailing + physical both coherent but different
    #     (the validator must NOT flag two coherent-but-distinct addresses) ---
    dual = [
        (("New York", "New York", "10001"), ("Newark", "New Jersey", "07101")),
        (("Chicago", "Illinois", "60601"), ("Milwaukee", "Wisconsin", "53201")),
        (("Los Angeles", "California", "90001"), ("Phoenix", "Arizona", "85001")),
        (("Boston", "Massachusetts", "02134"), ("Providence", "Rhode Island", "02901")),
        (("Seattle", "Washington", "98101"), ("Portland", "Oregon", "97201")),
    ]
    for i, (mail, phys) in enumerate(dual):
        cases.append(Case(
            case_id=f"clean_dual_{i}",
            cls="clean_dual",
            fields=[
                _f(*M_CITY, mail[0]), _f(*M_STATE, mail[1]), _f(*M_ZIP, mail[2]),
                _f(*P_CITY, phys[0]), _f(*P_STATE, phys[1]), _f(*P_ZIP, phys[2]),
                _f(*M_COUNTRY, "United States"),
            ],
        ))

    # --- coherent dates (born before admitted, both in the past) ---
    coherent_dates = [
        ("1985-01-01", "2005-06-15"),
        ("1990-07-20", "2010-03-01"),
        ("1978-12-31", "1999-08-08"),
        ("1965-03-12", "1990-11-05"),
        ("1995-09-09", "2018-01-20"),
    ]
    for i, (dob, admit) in enumerate(coherent_dates):
        cases.append(Case(
            case_id=f"clean_dates_{i}",
            cls="clean_dates",
            fields=[
                _f(*DOB, dob),
                _f(*ADMIT, admit),
                _f(*BIRTH_COUNTRY, "Vietnam"),
            ],
        ))

    return cases


if __name__ == "__main__":
    corpus = build_corpus()
    n_contra = sum(1 for c in corpus if c.is_contradiction)
    n_clean = len(corpus) - n_contra
    print(f"corpus: {len(corpus)} cases = {n_contra} contradiction + {n_clean} clean")
    from collections import Counter
    print("by class:", dict(Counter(c.cls for c in corpus)))
