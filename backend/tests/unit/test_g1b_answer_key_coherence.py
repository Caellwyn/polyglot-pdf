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
    """Coverage, valid option values, copy-field equality, NA bookkeeping, and
    digit-preset pattern/length all hold."""
    problems = validate_answer_key()
    assert problems == [], "answer key invalid:\n  " + "\n  ".join(problems)


def test_validate_answer_key_catches_digit_preset_length_drift(monkeypatch):
    """A digit-preset value that violates the kit's pattern/length (e.g. a 13-digit
    uscis_account under ^[0-9]{12}$) must be flagged, so the next kit drift aborts
    loudly instead of passing silently (bd polyglot-pdf-kpa1)."""
    import backend.scripts.g1b_answer_key as ak
    bad = dict(ak.ANSWER_KEY)
    bad["p1_line2_acctidentifier"] = "1234567890123"  # 13 digits, kit wants 12
    monkeypatch.setattr(ak, "ANSWER_KEY", bad)
    problems = ak.validate_answer_key()
    assert any("p1_line2_acctidentifier" in p for p in problems), (
        "pattern/length drift was not caught:\n  " + "\n  ".join(problems))


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


# The payload resolves option tokens to LABELS (option_label), so these guards
# must compare against the resolved label, NOT the raw token -- a raw-token
# comparison would never fire and the regression guard would be dead (Codex review,
# PR #253). _by_id maps field_id -> schema field so we can resolve the token.
_FIELDS_BY_ID = {f["field_id"]: f for f in load_schema_fields()}


def _label_of(field_id: str, token: str) -> str:
    """The human label the payload would carry for `token` on `field_id`."""
    return option_label(_FIELDS_BY_ID[field_id], token)


def test_name_change_coherence_holds_in_all_cases():
    """If the name-change radio says 'Yes' (option [0]), at least one previous-name
    field must be filled -- otherwise it is the original 'Yes but identical name'
    artifact. The persona is 'No', so this must hold across injected cases too."""
    prev = ("p1_line5a_familyname", "p1_line5b_givenname", "p1_line5c_middlename")
    yes_label = _label_of(
        "p1_checkbox4", "yes_proceed_to_item_numbers_5_a_5_c")  # "Yes (Proceed ...)"
    for size in (20, 40, 132):
        for case in build_corpus(size):
            d = {f["field_id"]: f["value"] for f in case.fields}
            if d.get("p1_checkbox4") == yes_label:
                assert any(d.get(k) for k in prev), (
                    f"{case.case_id}: name-change=Yes but no previous name given")


def test_english_interpreter_coherence_holds_in_all_cases():
    """If the applicant self-certifies 'I can read English' (option [0]), an
    interpreter must NOT be populated -- otherwise it is the self-cert-vs-
    interpreter artifact. The persona uses the interpreter-read-to-me statement."""
    interp = ("p6_line1a_interpretersfamilyname", "p6_line1b_interpretersgivenname")
    eng_label = _label_of(
        "p5_checkbox1a",
        "i_can_read_and_understand_english_and_i_have_read_and_understand_every_"
        "question_and_instruction_on_this_application_and_my_answer_to_every_"
        "question")  # "I can read ..."
    for size in (20, 40, 132):
        for case in build_corpus(size):
            d = {f["field_id"]: f["value"] for f in case.fields}
            if d.get("p5_checkbox1a") == eng_label:
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
    """Part 5 must match the form's REAL conditional logic. p5_checkbox1a is a
    checkbox GROUP; its dependents are gated by the `includes` operator (array
    membership), which bd vq4m fixed to actually match. So the two dependents are
    graded on PERSONA grounds (bd polyglot-pdf-b7ln), not "always hidden":
      - p5_line1b_language show_if `includes` the INTERPRETER-read slug the persona
        selects -> SHOWN -> carries the interpreter's language (Vietnamese).
      - p5_line2_nameofrepresentative show_if `includes` the PREPARER slug the
        interpreter-path persona does NOT select -> hidden -> NA.
    The interpreter STATEMENT is selected; the entire Part 7 preparer block is NA
    (no separate preparer)."""
    interp = "interpreter named in Part 6"
    eng = "I can read and understand English"
    d = {f["field_id"]: f["value"] for f in build_corpus(132)[-1].fields}
    assert interp in d["p5_checkbox1a"]
    assert eng not in d["p5_checkbox1a"]
    # p5_line1b_language is now SHOWN (interpreter slug selected) -> the language.
    assert ANSWER_KEY["p5_line1b_language"] == "Vietnamese"
    assert d.get("p5_line1b_language") == "Vietnamese"
    # p5_line2_nameofrepresentative stays NA: the PREPARER statement is not selected.
    assert ANSWER_KEY["p5_line2_nameofrepresentative"] is None
    assert "p5_line2_nameofrepresentative" not in d
    # no separate preparer -> entire Part 7 NA
    for fid in ("p7_line1a_familyname", "p7_line3d_state", "p7_checkbox7",
                "p7_line8a_signatureofpreparer"):
        assert ANSWER_KEY[fid] is None, f"{fid} should be NA (no preparer)"
        assert fid not in d, f"{fid} should be omitted from the payload"


def test_reason_for_new_card_is_answered_for_plain_lpr():
    """p2_checkbox2[5] (reason for new card) is show_if-gated
    `p2_checkbox1 in [lawful_permanent_resident,
    permanent_resident_in_commuter_status]`, so it is VISIBLE for a plain LPR. The
    persona's documented reason is a lost green card, so it must carry the
    lost/stolen/destroyed option and appear in the payload wherever Part 2 is in the
    size window (bd polyglot-pdf-kpa1; corrects the stale commuter-only NA)."""
    assert ANSWER_KEY["p2_checkbox2[5]"] == "my_previous_card_has_been_lost_stolen_or_destroyed"
    assert ANSWER_KEY["p2_checkbox1"] == "lawful_permanent_resident"  # plain LPR
    assert "p2_checkbox2[5]" not in NA_REASON
    # It is filled (not NA) wherever it appears in a corpus size window.
    seen_in_any = False
    for size in (20, 40, 132):
        for case in build_corpus(size):
            d = {f["field_id"]: f["value"] for f in case.fields}
            if "p2_checkbox2[5]" in d:
                seen_in_any = True
                assert d["p2_checkbox2[5]"] == "My previous card has been lost, stolen, or destroyed"
    assert seen_in_any, "reason-for-new-card field never appeared in any corpus size"


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
