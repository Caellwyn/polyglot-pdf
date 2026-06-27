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
    validate_answer_key,
)
from backend.scripts.g1b_corpus import build_corpus

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
