"""Unit tests for the deterministic mechanical translation lint (bd
polyglot-pdf-ch7j).

Pure functions, zero live calls. Non-ASCII fixture strings are built with
chr() so this file stays ASCII (CLAUDE.md scar #6).

The two review-round-3 tolerances are pinned hard here because they are what
keeps the lint from flagging everything:
- expected-script is PRESENT/DOMINANT after stripping DNT/masks/digits,
  never "no Latin present";
- pin checks are substring/case-insensitive (with the inflection caveat
  documented, not enforced).
"""
import json
from pathlib import Path

import pytest

from backend.services.schema_lint import SEVERITY_WARNING
from backend.services.translation_lint import (
    CHECK_DIGIT_RUN,
    CHECK_DNT,
    CHECK_EMPTY,
    CHECK_MASK,
    CHECK_NON_ASCII_DIGITS,
    CHECK_PIN,
    CHECK_SCRIPT,
    DEFAULT_GLOSSARY_PATH,
    RULE_MECHANICAL,
    glossary_language,
    glossary_prompt_context,
    iter_translation_entries,
    lint_kit_schema,
    lint_kits,
    lint_translation,
    load_glossary,
    main,
)


def _chrs(*codes):
    return "".join(chr(c) for c in codes)


# Cyrillic "Nomer" (an arbitrary real Russian word for fixtures).
RU_WORD = _chrs(0x041D, 0x043E, 0x043C, 0x0435, 0x0440)
# Han "hu zhu" -- the pinned zh rendering of "head of household".
ZH_HEAD_OF_HOUSEHOLD = _chrs(0x6237, 0x4E3B)
# Arabic-Indic digits "12".
ARABIC_INDIC_12 = _chrs(0x0661, 0x0662)
# Devanagari sample word.
HI_WORD = _chrs(0x0928, 0x093E, 0x092E)

# A minimal controlled glossary so check tests do not depend on the real
# file's contents.
_G = {
    "digits_policy": "ASCII digits only.",
    "do_not_translate": ["USCIS", "ITIN"],
    "form_number_pattern": "\\b[A-Z]{1,3}-\\d+[A-Z]{0,3}\\b",
    "format_mask_pattern":
        "(?i)\\b(?:mm|dd|yy|yyyy)(?:[/\\-.](?:mm|dd|yy|yyyy))+\\b",
    "languages": {
        "russian": {"register": "formal", "script": "cyrillic", "pins": {}},
        "spanish": {
            "register": "usted", "script": "latin",
            "pins": {"head of household": "cabeza de familia"},
        },
        "chinese": {
            "register": "nin", "script": "han",
            "pins": {"head of household": ZH_HEAD_OF_HOUSEHOLD},
        },
        "urdu": {"register": "aap", "script": "arabic", "pins": {}},
    },
}


def _checks(failures):
    return sorted(f.check for f in failures)


# ---------------------------------------------------------------------------
# The committed glossary file
# ---------------------------------------------------------------------------

def test_real_glossary_loads_and_covers_all_17_languages():
    """Exit criterion 2 of the bead: register + script entries for ALL 17
    non-English languages, pins for es + zh, DNT + digits policy present."""
    from backend.utils.language_codes import SPOKEN_LANGUAGE_BCP47

    glossary = load_glossary()
    assert glossary is not None
    languages = glossary["languages"]
    expected = {n for n in SPOKEN_LANGUAGE_BCP47 if n != "english"}
    assert set(languages) == expected and len(expected) == 17
    valid_scripts = {"latin", "cyrillic", "han", "hangul", "devanagari",
                     "arabic"}
    for name, entry in languages.items():
        assert entry["register"].strip(), name
        assert entry["script"] in valid_scripts, name
        assert isinstance(entry["pins"], dict), name
    assert languages["spanish"]["pins"]["head of household"] \
        == "cabeza de familia"
    assert languages["chinese"]["pins"]
    assert "USCIS" in glossary["do_not_translate"]
    assert glossary["digits_policy"].strip()
    assert glossary["form_number_pattern"]
    assert glossary["format_mask_pattern"]


def test_load_glossary_fail_open(tmp_path):
    assert load_glossary(tmp_path / "missing.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    assert load_glossary(bad) is None
    wrong_shape = tmp_path / "shape.json"
    wrong_shape.write_text(json.dumps(["list"]), encoding="utf-8")
    assert load_glossary(wrong_shape) is None


def test_glossary_language_resolves_name_and_code_aliases():
    entry = glossary_language(_G, "spanish")
    assert entry is not None and entry["register"] == "usted"
    assert glossary_language(_G, "Spanish") == entry
    assert glossary_language(_G, "es") == entry
    assert glossary_language(_G, "es-US") == entry
    assert glossary_language(_G, "klingon") is None
    assert glossary_language(None, "spanish") is None


def test_glossary_prompt_context_slice():
    context = glossary_prompt_context(_G, "spanish")
    assert context == {
        "register": "usted",
        "pins": {"head of household": "cabeza de familia"},
        "do_not_translate": ["USCIS", "ITIN"],
        "digits_policy": "ASCII digits only.",
    }
    assert glossary_prompt_context(None, "spanish") is None
    # Unknown language still yields the language-independent parts.
    context = glossary_prompt_context(_G, "klingon")
    assert context["do_not_translate"] == ["USCIS", "ITIN"]
    assert context["register"] == "" and context["pins"] == {}


# ---------------------------------------------------------------------------
# Per-string checks
# ---------------------------------------------------------------------------

def test_empty_translation_short_circuits():
    assert _checks(lint_translation("Name", "", "russian", _G)) \
        == [CHECK_EMPTY]
    assert _checks(lint_translation("Name", "   ", "russian", _G)) \
        == [CHECK_EMPTY]


def test_native_digits_flagged_ascii_digits_clean():
    # Urdu rendering "12" with Arabic-Indic digits: the digits policy case
    # (plan A.2(d)) -- flagged for native digits AND the missing ASCII run.
    failures = lint_translation(
        "Apartment 12", "Apartment " + ARABIC_INDIC_12, "urdu", _G)
    assert CHECK_NON_ASCII_DIGITS in _checks(failures)
    assert CHECK_DIGIT_RUN in _checks(failures)
    # Same string with ASCII digits: clean (Latin text is fine for ur -- the
    # script check only needs arabic to DOMINATE what remains, and 'Apartment'
    # is the only letters here... so use an Arabic-script word).
    ur_word = _chrs(0x0645, 0x06A9, 0x0627, 0x0646)  # "makaan"
    assert lint_translation("Apartment 12", ur_word + " 12", "urdu", _G) == []


def test_digit_runs_must_survive():
    assert _checks(lint_translation(
        "Line 6", RU_WORD, "russian", _G)) == [CHECK_DIGIT_RUN]
    assert lint_translation("Line 6", RU_WORD + " 6", "russian", _G) == []


def test_format_masks_byte_exact():
    source = "Date of birth (mm/dd/yyyy)"
    assert lint_translation(
        source, RU_WORD + " (mm/dd/yyyy)", "russian", _G) == []
    failures = lint_translation(
        source, RU_WORD + " (dd/mm/yyyy)", "russian", _G)
    assert CHECK_MASK in _checks(failures)


def test_dnt_terms_and_form_numbers_must_survive():
    # Kept byte-identical: clean.
    assert lint_translation(
        "USCIS Form I-90", RU_WORD + " USCIS I-90", "russian", _G) == []
    # Translated-away USCIS: flagged.
    failures = lint_translation(
        "USCIS Form I-90", RU_WORD + " I-90", "russian", _G)
    assert CHECK_DNT in _checks(failures)
    # Mangled form number (I90 instead of I-90): flagged (digit run "90"
    # still present, so this is the DNT/form-number check specifically).
    failures = lint_translation(
        "Form I-90", RU_WORD + " I90", "russian", _G)
    assert CHECK_DNT in _checks(failures)


def test_script_tolerance_is_present_dominant_never_no_latin():
    """The review-round-3 case: a correct Russian string legitimately keeps
    Latin DNT terms, form numbers, and masks -- must NOT flag."""
    translation = RU_WORD + " USCIS I-90 (mm/dd/yyyy)"
    assert lint_translation(
        "USCIS number I-90 (mm/dd/yyyy)", translation, "russian", _G) == []


def test_wrong_script_flagged_only_when_expected_absent():
    # Fully-Latin non-identical "translation" for Russian (the model
    # answered in English words): flagged.
    failures = lint_translation("Given name", "First name", "russian", _G)
    assert _checks(failures) == [CHECK_SCRIPT]
    # Latin-heavy but expected script PRESENT: clean. Presence-only is the
    # measured tolerance (piloted dominance flagged correct translations
    # keeping un-DNT'd Latin acronyms like 'ZIP' -- see _check_script).
    failures = lint_translation(
        "Given name", "ZIP code " + RU_WORD, "russian", _G)
    assert failures == []
    # Cyrillic translation for SPANISH: flagged the other way around.
    failures = lint_translation("Name", RU_WORD, "spanish", _G)
    assert _checks(failures) == [CHECK_SCRIPT]


def test_script_check_skips_identity_kept_strings():
    """Identity (translation == source) is a translator CHOICE the lint
    cannot prove wrong -- the shipped i-90 keeps ~600 US state names
    Latin-identical in ar/hi/ur ('Alabama' -> 'Alabama'), sanctioned by the
    translate prompt's proper-noun rule. The judge (V3) owns that call."""
    assert lint_translation("Alabama", "Alabama", "hindi", _G) == []
    assert lint_translation("Given name", "Given name", "russian", _G) == []
    assert lint_translation("Alabama", " Alabama ", "urdu", _G) == []


def test_script_check_skips_all_dnt_strings_and_unknown_languages():
    # A translation that IS just the DNT token: nothing left -> no check.
    assert lint_translation("USCIS", "USCIS", "russian", _G) == []
    # Unknown language key: no script expectation -> no script finding.
    assert lint_translation("Name", "anything", "klingon", _G) == []


def test_pins_case_insensitive_hit_and_miss():
    assert lint_translation(
        "Head of Household", "Cabeza de Familia", "spanish", _G) == []
    failures = lint_translation(
        "Head of household", "Jefe de hogar", "spanish", _G)
    assert _checks(failures) == [CHECK_PIN]
    # zh pin: Han rendering present -> clean (script check also satisfied).
    assert lint_translation(
        "Head of household", ZH_HEAD_OF_HOUSEHOLD, "chinese", _G) == []
    failures = lint_translation(
        "Head of household", HI_WORD, "chinese", _G)
    assert CHECK_PIN in _checks(failures)
    assert CHECK_SCRIPT in _checks(failures)


def test_lint_translation_survives_absent_glossary():
    """Fail-open: no glossary -> only the glossary-independent checks run
    (empty + digits), and nothing crashes."""
    assert lint_translation("Line 6", "text 6", "russian", None) == []
    assert _checks(lint_translation("Line 6", "text", "russian", None)) \
        == [CHECK_DIGIT_RUN]


# ---------------------------------------------------------------------------
# Kit-schema traversal + sweep
# ---------------------------------------------------------------------------

_SCHEMA = {
    "fields": [
        {
            "id": "f_name",
            "spoken_name": "Given name",
            "spoken_name_translations": {
                "russian": "First name",          # non-identical English ->
                                                  # script flag
                "es": "Nombre de pila",           # alias key resolves; clean
                "english": "Given name",          # skipped
                "klingon": "qoSlIj",              # unknown key skipped
            },
            "options": [
                {
                    "value": "opt_a",
                    "label": "USCIS office",
                    "label_translations": {
                        "russian": RU_WORD,       # dropped USCIS -> DNT flag
                    },
                },
            ],
        },
    ],
    "sections": [
        {
            "id": "sec_1",
            "label": "Part 1",
            "label_translations": {
                "russian": RU_WORD + " 1",        # clean (digit survives)
            },
        },
    ],
}


def test_iter_translation_entries_paths_and_coverage():
    from backend.services.schema_lint import field_id_of

    entries = list(iter_translation_entries(_SCHEMA))
    paths = [e[0] for e in entries]
    assert "fields[0] (id=f_name).spoken_name_translations.russian" in paths
    assert "fields[0] (id=f_name).options[opt_a].label_translations.russian" \
        in paths
    assert "sections[sec_1].label_translations.russian" in paths
    # Field-level paths round-trip through schema_lint.field_id_of so the
    # editor can focus the offending field (fresh-eyes finding: the first
    # cut's format parsed to None); section paths deliberately do not.
    for path, lang, source, translation in entries:
        assert isinstance(path, str) and isinstance(lang, str)
        assert isinstance(source, str) and isinstance(translation, str)
        if path.startswith("fields["):
            assert field_id_of(path) == "f_name", path
        else:
            assert field_id_of(path) is None, path


def test_lint_kit_schema_flags_and_skips():
    # The synthetic kit covers only a couple of the 17 supported languages,
    # so the coverage rule (bd x41u) legitimately fires alongside; this test
    # pins the STRING checks, so filter to the mechanical rule.
    all_findings = lint_kit_schema(_SCHEMA, _G)
    from backend.services.translation_lint import RULE_COVERAGE as _RC
    findings = [f for f in all_findings if f.rule != _RC]
    by_path = {}
    for finding in findings:
        assert finding.severity == SEVERITY_WARNING
        assert finding.rule == RULE_MECHANICAL
        assert finding.as_dict()["field_id"] in ("f_name", None)
        by_path.setdefault(finding.path, []).append(finding.message)
    spoken_path = "fields[0] (id=f_name).spoken_name_translations.russian"
    assert spoken_path in by_path
    assert any("no cyrillic-alphabet characters" in m for m in by_path[spoken_path])
    assert "fields[0] (id=f_name).options[opt_a].label_translations.russian" \
        in by_path
    # The es alias entry, the english entry, the unknown key, and the clean
    # section entry produce no findings.
    flagged_paths = set(by_path)
    assert not any(".es" in p or ".english" in p or ".klingon" in p
                   for p in flagged_paths)
    assert "sections[sec_1].label_translations.russian" not in flagged_paths


def test_lint_kit_schema_empty_and_none_schema():
    assert lint_kit_schema(None, _G) == []
    assert lint_kit_schema({}, _G) == []


def test_lint_kits_sweeps_real_repo_kits():
    """Exit criterion 3: the sweep over the committed kits completes without
    error. Findings are allowed (the shipped bake predates the lint); the
    pin is completion + coverage, not zero findings."""
    kits_root = DEFAULT_GLOSSARY_PATH.parents[1]
    glossary = load_glossary()
    results = lint_kits(kits_root, glossary)
    assert {"f1040", "i-90", "w7"} <= set(results)
    assert "_translation" not in results
    for findings in results.values():
        for finding in findings:
            assert finding.severity == SEVERITY_WARNING
            assert finding.rule == RULE_MECHANICAL


def test_lint_kits_unreadable_schema_fail_open(tmp_path):
    kit = tmp_path / "broken-kit"
    kit.mkdir()
    (kit / "schema.json").write_text("not json", encoding="utf-8")
    results = lint_kits(tmp_path, _G)
    assert len(results["broken-kit"]) == 1
    assert "could not be read" in results["broken-kit"][0].message


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _write_kit(root, kit_id, schema):
    kit = root / kit_id
    kit.mkdir()
    (kit / "schema.json").write_text(
        json.dumps(schema, ensure_ascii=False), encoding="utf-8")


def test_main_exit_codes(tmp_path, capsys):
    glossary_path = tmp_path / "glossary.json"
    glossary_path.write_text(json.dumps(_G, ensure_ascii=False),
                             encoding="utf-8")
    # Fully covered across the supported set so the coverage rule (bd x41u)
    # stays silent -- this test pins the exit-code contract, not coverage.
    # Identity-kept values (translation == source) are the sanctioned way to
    # be clean in EVERY language at once (script + wrong-language checks
    # skip identity by design).
    clean_schema = {
        "fields": [{
            "id": "f1", "spoken_name": "Part one",
            "spoken_name_translations": _all_langs("Part one"),
        }],
    }
    _write_kit(tmp_path, "clean-kit", clean_schema)
    assert main(["--kits-root", str(tmp_path),
                 "--glossary", str(glossary_path)]) == 0
    _write_kit(tmp_path, "dirty-kit", _SCHEMA)
    code = main(["--kits-root", str(tmp_path),
                 "--glossary", str(glossary_path), "--verbose"])
    assert code == 1
    out = capsys.readouterr().out
    assert "dirty-kit" in out and "TOTAL" in out
    # Console output stays ASCII (cp1252 scar): every printed char < 128.
    assert all(ord(c) < 128 for c in out)


def test_main_errors_without_glossary(tmp_path):
    assert main(["--kits-root", str(tmp_path),
                 "--glossary", str(tmp_path / "nope.json")]) == 2


# ---------------------------------------------------------------------------
# Pin check: English-side word boundaries (bd polyglot-pdf-m6w5)
# ---------------------------------------------------------------------------

_G_REFUND = {
    "languages": {
        "spanish": {
            "register": "usted", "script": "latin",
            "pins": {"refund": "reembolso"},
        },
    },
}


def test_pin_check_ignores_english_derivational_morphology():
    """'Refundable credit' contains 'refund' only as a stem; the correct es
    'reembolsable' does not contain 'reembolso' -- must NOT flag."""
    failures = lint_translation(
        "Refundable credit", "Credito reembolsable", "spanish", _G_REFUND)
    assert CHECK_PIN not in _checks(failures)


def test_pin_check_still_fires_on_the_standalone_term():
    failures = lint_translation(
        "Refund amount", "Cantidad devuelta", "spanish", _G_REFUND)
    assert CHECK_PIN in _checks(failures)
    # And the pinned rendering satisfies it.
    ok = lint_translation(
        "Refund amount", "Cantidad del reembolso", "spanish", _G_REFUND)
    assert CHECK_PIN not in _checks(ok)


def test_pin_check_matches_term_at_punctuation_boundaries():
    # Word boundary = non-letter, so 'refund.' / '(refund)' still match.
    failures = lint_translation(
        "Amount (refund)", "Cantidad devuelta", "spanish", _G_REFUND)
    assert CHECK_PIN in _checks(failures)


# ---------------------------------------------------------------------------
# Wrong-language markers (bd polyglot-pdf-za4p)
# ---------------------------------------------------------------------------

from backend.services.translation_lint import (  # noqa: E402
    CHECK_WRONG_LANGUAGE,
    RULE_COVERAGE,
    coverage_findings,
)

# Portuguese "Nao e elegivel" with a-tilde (U+00E3).
PT_IN_ES = "N" + chr(0x00E3) + "o elegivel"
# Russian word with yery (U+044B): "Vyberite" (choose).
RU_YERY_WORD = _chrs(0x0412, 0x044B, 0x0431, 0x043E, 0x0440)
# Ukrainian word with i (U+0456): "imia".
UK_I_WORD = _chrs(0x0406, 0x043C, 0x2019, 0x044F)


def test_wrong_language_flags_portuguese_in_a_spanish_slot():
    failures = lint_translation("Not eligible", PT_IN_ES, "spanish", _G)
    assert CHECK_WRONG_LANGUAGE in _checks(failures)
    msg = next(f.message for f in failures
               if f.check == CHECK_WRONG_LANGUAGE)
    assert "portuguese" in msg


def test_wrong_language_flags_russian_in_a_ukrainian_slot():
    failures = lint_translation("Choose", RU_YERY_WORD, "ukrainian", _G)
    assert CHECK_WRONG_LANGUAGE in _checks(failures)
    assert "russian" in next(
        f.message for f in failures if f.check == CHECK_WRONG_LANGUAGE)


def test_wrong_language_flags_ukrainian_in_a_russian_slot():
    failures = lint_translation("Name", UK_I_WORD, "russian", _G)
    assert CHECK_WRONG_LANGUAGE in _checks(failures)


def test_wrong_language_flags_persian_letters_in_an_arabic_slot():
    # Persian pe (U+067E) inside an otherwise-Arabic string.
    text = _chrs(0x0627, 0x0633, 0x0645) + " " + chr(0x067E)
    failures = lint_translation("Name", text, "arabic", _G)
    assert CHECK_WRONG_LANGUAGE in _checks(failures)


def test_wrong_language_tolerates_legit_orthography():
    # Spanish enye/accents are fine in spanish...
    ok = lint_translation(
        "Year", "A" + chr(0x00F1) + "o", "spanish", _G)
    assert CHECK_WRONG_LANGUAGE not in _checks(ok)
    # ...and the enye is NOT a wrong-language marker for tagalog (Spanish
    # loans are standard Tagalog orthography).
    ok = lint_translation(
        "Mr.", "Se" + chr(0x00F1) + "or", "tagalog", _G)
    assert CHECK_WRONG_LANGUAGE not in _checks(ok)
    # Plain Russian in a russian slot: no marker hit.
    ok = lint_translation("Number", RU_WORD, "russian", _G)
    assert CHECK_WRONG_LANGUAGE not in _checks(ok)


def test_wrong_language_skips_identity_kept_strings():
    # A deliberately untranslated proper noun (translation == source) is the
    # translator's sanctioned identity choice -- never flagged, even when it
    # carries a marker character.
    src = "S" + chr(0x00E3) + "o Paulo"
    ok = lint_translation(src, src, "spanish", _G)
    assert CHECK_WRONG_LANGUAGE not in _checks(ok)


# ---------------------------------------------------------------------------
# Per-language coverage gaps (bd polyglot-pdf-x41u)
# ---------------------------------------------------------------------------

def _all_langs(value):
    from backend.utils.language_codes import SPOKEN_LANGUAGE_BCP47
    return {n: value for n in SPOKEN_LANGUAGE_BCP47 if n != "english"}


def _coverage_schema(drop_french_from_second=True):
    full = _all_langs("x")
    partial = dict(full)
    if drop_french_from_second:
        partial.pop("french")
    return {
        "fields": [
            {"id": "a", "spoken_name": "First name",
             "spoken_name_translations": dict(full),
             "options": [{"value": "y", "label": "Yes",
                          "label_translations": dict(full)}]},
            {"id": "b", "spoken_name": "Last name",
             "spoken_name_translations": partial},
        ],
        "sections": [
            {"id": "s1", "label": "Part 1", "label_translations": dict(full)},
        ],
    }


def test_coverage_flags_the_partial_language_only():
    findings = coverage_findings(_coverage_schema())
    assert len(findings) == 1
    f = findings[0]
    assert f.rule == RULE_COVERAGE
    assert f.severity == SEVERITY_WARNING
    assert f.path == "coverage.french"
    # 4 translation-bearing items, 3 covered for french.
    assert "french covers 3/4" in f.message
    assert "ENGLISH" in f.message
    assert "fields[1] (id=b).spoken_name_translations" in f.message


def test_coverage_counts_a_fully_failed_language_as_a_gap():
    # A language with ZERO coverage in an otherwise-translated kit is the
    # failed-batch case -- flagged, not treated as 'not attempted'.
    schema = _coverage_schema(drop_french_from_second=False)
    for field in schema["fields"]:
        field.get("spoken_name_translations", {}).pop("urdu", None)
        for opt in field.get("options") or []:
            opt.get("label_translations", {}).pop("urdu", None)
    schema["sections"][0]["label_translations"].pop("urdu")
    findings = coverage_findings(schema)
    assert [f.path for f in findings] == ["coverage.urdu"]
    assert "urdu covers 0/4" in findings[0].message


def test_coverage_treats_a_present_but_empty_value_as_not_covered():
    # bd polyglot-pdf-z3rs: a translation key present with an empty/whitespace/
    # non-string VALUE is not a translation -- it must NOT count as covered, so
    # the hard completion gate (bd 783r) does not pass a form that would speak
    # the ENGLISH label aloud in that session. Parity with
    # option_translation._kit_translation's non-empty-string filter.
    for bad in ("", "   ", None, 123):
        schema = _coverage_schema(drop_french_from_second=False)
        # Corrupt ONLY french on the second field's spoken name.
        schema["fields"][1]["spoken_name_translations"]["french"] = bad
        findings = coverage_findings(schema)
        assert [f.path for f in findings] == ["coverage.french"], bad
        assert "french covers 3/4" in findings[0].message, bad
    # And it flips the whole-kit summary gate (bd 783r) to incomplete.
    from backend.services.option_translation import (
        translation_coverage_summary,
    )
    schema = _coverage_schema(drop_french_from_second=False)
    schema["fields"][1]["spoken_name_translations"]["french"] = ""
    summary = translation_coverage_summary(schema)
    assert not summary.complete
    assert "french" in summary.incomplete_languages


def test_coverage_silent_on_untranslated_and_full_kits():
    # No baked translations at all: an untranslated draft is not a gap.
    bare = {"fields": [{"id": "a", "spoken_name": "Name"}]}
    assert coverage_findings(bare) == []
    assert coverage_findings(None) == []
    # Fully covered: nothing to flag.
    assert coverage_findings(
        _coverage_schema(drop_french_from_second=False)) == []


def test_coverage_rides_lint_kit_schema():
    findings = lint_kit_schema(_coverage_schema(), _G)
    assert [f.rule for f in findings if f.rule == RULE_COVERAGE] \
        == [RULE_COVERAGE]


def test_coverage_attempted_flags_a_totally_failed_scoped_set():
    """fresh-eyes gap (bd x41u): a bake that ATTEMPTED languages and ended
    with zero coverage is the every-batch-failed outage -- with the bake's
    attestation it flags; without it (kit-level sweep) an untranslated
    draft stays silent."""
    bare = {"fields": [{"id": "a", "spoken_name": "Name"}]}
    flagged = coverage_findings(bare, ["french"], attempted=True)
    assert [f.path for f in flagged] == ["coverage.french"]
    assert "french covers 0/1" in flagged[0].message
    # Same kit without the attestation: an untranslated draft, not a gap.
    assert coverage_findings(bare, ["french"]) == []
