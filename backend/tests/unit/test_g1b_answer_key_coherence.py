"""Coherence guard for the G1b clean answer key + corpus (bd polyglot-pdf-wf3q).

The G1b bake-off (probe_g1b_model_size_bakeoff.py) measures a contradiction
checker's PRECISION on "clean" full I-90 form states. Those clean states come
from g1b_answer_key.ANSWER_KEY (a hand-validated coherent persona). If a future
edit reintroduces an UNLABELED contradiction into the clean base -- the exact
failure that made the precision numbers untrustworthy before wf3q (name-change
"Yes" with identical names, English-self-cert with an interpreter populated, full
state names instead of abbreviations) -- a good checker will correctly flag it and
the corpus will wrongly score it as a false positive. These tests turn the wf3q
hand-audit into a durable regression guard so that can't silently come back.

STDLIB-only imports (no google.genai) so this runs without the API SDK.
"""
from backend.scripts.g1b_answer_key import (
    ANSWER_KEY,
    NA_REASON,
    load_schema_fields,
    option_label,
    validate_answer_key,
)
from backend.scripts.g1b_corpus import build_corpus, corpus_fingerprint

_US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT",
    "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
}

# (state_field, country_field, province_field) for each address cluster.
_ADDR_CLUSTERS = [
    ("p1_line6e_state", "p1_line6i_country", "p1_line6g_province"),   # mailing
    ("p1_line7d_state", "p1_line7h_country", "p1_line7f_province"),   # physical
    ("p6_line3d_state", "p6_line3h_country", "p6_line3f_province"),   # interpreter
    ("p7_line3d_state", "p7_line3h_country", "p7_line3f_province"),   # preparer
]


def test_answer_key_is_structurally_valid():
    """Coverage, valid option values, copy-field equality, NA bookkeeping all hold."""
    problems = validate_answer_key()
    assert problems == [], "answer key invalid:\n  " + "\n  ".join(problems)


def test_answer_key_covers_every_schema_field_exactly_once():
    fields = load_schema_fields()
    schema_ids = {f["field_id"] for f in fields}
    assert set(ANSWER_KEY) == schema_ids
    assert len(ANSWER_KEY) == len(fields) == 132


def test_every_na_field_has_a_reason_and_vice_versa():
    na_fields = {fid for fid, v in ANSWER_KEY.items() if v is None}
    assert na_fields == set(NA_REASON)


def test_clean_base_has_no_state_country_or_province_artifact():
    """The named state/country and province/state artifact classes must be absent
    from every clean case at every size (the checker's headline precision traps)."""
    for size in (20, 40, 132):
        for case in build_corpus(size):
            if case.is_contradiction:
                continue
            d = {f["field_id"]: f["value"] for f in case.fields}
            for stk, ck, pvk in _ADDR_CLUSTERS:
                st, co, pv = d.get(stk), d.get(ck), d.get(pvk)
                if st in _US_STATES and co:
                    assert "United States" in co, (
                        f"{case.case_id}: US state {st} paired with non-US "
                        f"country {co!r} ({stk}/{ck})")
                if st in _US_STATES:
                    assert not pv, (
                        f"{case.case_id}: US state {st} paired with foreign "
                        f"province {pv!r} ({stk}/{pvk})")


def test_name_change_coherence_holds_in_all_cases():
    """If the name-change radio says 'Yes' (option [0]), at least one previous-name
    field must be filled -- otherwise it is the original 'Yes but identical name'
    artifact. The persona is 'No', so this must hold across injected cases too."""
    prev = ("p1_line5a_familyname", "p1_line5b_givenname", "p1_line5c_middlename")
    for size in (20, 40, 132):
        for case in build_corpus(size):
            d = {f["field_id"]: f["value"] for f in case.fields}
            if d.get("p1_checkbox4") == "P1_checkbox4[0]":  # "Yes, changed"
                assert any(d.get(k) for k in prev), (
                    f"{case.case_id}: name-change=Yes but no previous name given")


def test_english_interpreter_coherence_holds_in_all_cases():
    """If the applicant self-certifies 'I can read English' (option [0]), an
    interpreter must NOT be populated -- otherwise it is the self-cert-vs-
    interpreter artifact. The persona uses option [1] (interpreter read to me)."""
    interp = ("p6_line1a_interpretersfamilyname", "p6_line1b_interpretersgivenname")
    for size in (20, 40, 132):
        for case in build_corpus(size):
            d = {f["field_id"]: f["value"] for f in case.fields}
            if d.get("p5_checkbox1a") == "P5_Checkbox1a[0]":  # "I read English"
                assert not any(d.get(k) for k in interp), (
                    f"{case.case_id}: English self-cert but interpreter populated")


def test_copy_fields_equal_their_source_in_all_cases():
    """Part 8 page-header repeats (copy_from) must equal their Part 1 source
    wherever both appear in the payload."""
    copies = [
        ("p1_line1_aliennumber[1]", "p1_line1_aliennumber"),
        ("p1_line3a_familyname[1]", "p1_line3a_familyname"),
        ("p1_line3b_givenname[1]", "p1_line3b_givenname"),
        ("p1_line3c_middlename[1]", "p1_line3c_middlename"),
    ]
    for size in (20, 40, 132):
        for case in build_corpus(size):
            d = {f["field_id"]: f["value"] for f in case.fields}
            for cp, src in copies:
                if cp in d and src in d:
                    assert d[cp] == d[src], (
                        f"{case.case_id}: copy {cp}={d[cp]!r} != source "
                        f"{src}={d[src]!r}")


def test_state_pickers_use_abbreviations_not_full_names():
    """Every filled state-picker value in a clean case is a two-letter code (or ''
    for a foreign/territory address), never a full name like 'California'."""
    state_fields = {stk for stk, _, _ in _ADDR_CLUSTERS}
    for size in (20, 40, 132):
        for case in build_corpus(size):
            if case.is_contradiction:
                continue
            for f in case.fields:
                if f["field_id"] in state_fields and f["value"]:
                    assert f["value"] in _US_STATES, (
                        f"{case.case_id}: state {f['field_id']}={f['value']!r} is "
                        f"not a two-letter abbreviation")


def test_corpus_shapes_are_stable():
    """The bake-off depends on the corpus shape: far-apart classes only at 132,
    every contradiction case carries exactly one expected group."""
    sizes_classes = {}
    for size in (20, 40, 132):
        corpus = build_corpus(size)
        assert corpus, f"empty corpus at size {size}"
        for case in corpus:
            if case.is_contradiction:
                assert len(case.expected_conflicts) == 1, (
                    f"{case.case_id}: expected exactly one conflict group")
        sizes_classes[size] = {c.cls for c in corpus if c.is_contradiction}
    # far-apart same-fact classes require the full-form window
    assert "cross_date" not in sizes_classes[20]
    assert "duration_year" not in sizes_classes[20]
    assert "cross_date" in sizes_classes[132]
    assert "duration_year" in sizes_classes[132]


def test_clean_us_cases_survive_at_size_20():
    """The s20_clean_us_* ids must exist at size 20 (mailing-only) -- the physical
    cluster is out of the size-20 window, but the case is still a coherent clean
    mailing address. If they were dropped, g1b_merge.py would retain stale rows
    from old run files for those ids (Codex review, PR #253)."""
    ids = {c.case_id for c in build_corpus(20)}
    for i in range(5):
        assert f"s20_clean_us_{i}" in ids, f"s20_clean_us_{i} missing at size 20"


def test_option_values_are_resolved_to_human_labels():
    """Opaque option tokens are shown to the checker as their human label (so a
    coherent non-first option is not spuriously flagged), while already-legible
    short codes (states, colors) are left as-is (Codex review, PR #253)."""
    d = {f["field_id"]: f["value"] for f in build_corpus(132)[-1].fields}
    assert d["p1_line8_male"] == "Female"                 # opaque -> label
    assert d["p3_ethnicity"] == "Not Hispanic or Latino"  # opaque (underscore)
    assert d["p3_race"] == "Asian"
    assert d["p1_line6e_state"] == "TX"   # already legible short code -> unchanged
    assert d["p3_eye_color"] == "brown"   # already legible -> unchanged


def test_p5_certification_matches_who_filled_the_form():
    """Part 5 certification must match reality: this persona used an interpreter AND
    a preparer, so p5_checkbox1a selects BOTH statements and the representative-name
    field is filled. Selecting only the interpreter while Part 7 is populated would
    be an unlabeled contradiction (Codex review, PR #253)."""
    interp = "interpreter named in Part 6"
    prep = "preparer named in Part 7"
    d = {f["field_id"]: f["value"] for f in build_corpus(132)[-1].fields}
    assert interp in d["p5_checkbox1a"] and prep in d["p5_checkbox1a"]
    assert d.get("p5_line2_nameofrepresentative") == "John Smith"


def test_show_if_gated_reason_field_is_na_for_plain_lpr():
    """p2_checkbox2[5] (reason for new card) is show_if-gated to commuter status;
    the production renderer hides it for a plain LPR and rejects hidden updates, so
    a real client cannot send it -- it must be NA here (Codex review, PR #253)."""
    assert ANSWER_KEY["p2_checkbox2[5]"] is None
    assert ANSWER_KEY["p2_checkbox1"] == "P2_checkbox1[0]"  # plain LPR
    for size in (20, 40, 132):
        for case in build_corpus(size):
            assert "p2_checkbox2[5]" not in {f["field_id"] for f in case.fields}


def test_injection_cases_carry_no_secondary_address_contradiction():
    """An address-injection case must carry ONLY its labeled contradiction: the
    mailing city is coherent with the injected state, and a US ZIP is not left
    alongside a foreign country / foreign province (Codex review, PR #253)."""
    city_state = {"Charleston": "WV", "Sacramento": "CA", "Austin": "TX",
                  "Orlando": "FL", "Columbus": "OH", "Albany": "NY",
                  "Springfield": "IL"}
    for case in build_corpus(132):
        if case.cls not in ("zip_state", "state_country", "province_us"):
            continue
        d = {f["field_id"]: f["value"] for f in case.fields}
        city = d.get("p1_line6d_cityortown")
        st = d.get("p1_line6e_state")
        assert city != "Houston" or st == "TX", (
            f"{case.case_id}: stale Houston city with state {st}")
        if city in city_state:
            assert city_state[city] == st, (
                f"{case.case_id}: city {city} incoherent with state {st}")
        # foreign country / province cases must not also carry a US ZIP
        if case.cls in ("state_country", "province_us"):
            assert "p1_line6f_zipcode" not in d, (
                f"{case.case_id}: US ZIP left alongside foreign country/province")


def test_corpus_fingerprint_is_stable_and_nonempty():
    """The fingerprint must be deterministic (same value across two builds) and
    non-empty -- g1b_merge.py relies on it to merge only same-corpus runs."""
    fp1 = corpus_fingerprint()
    fp2 = corpus_fingerprint()
    assert fp1 == fp2 and len(fp1) == 12
