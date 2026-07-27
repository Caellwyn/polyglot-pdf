"""Spec for extraction-time option-label baking (bd polyglot-pdf-2h9j).

bake_label_translations writes stock translations into a kit schema in place,
so the runtime secretary translation (bd ow1e) short-circuits via the kit
precedence rule and translations become deterministic, reviewable artifacts.

Pins:
  1. One translate_items call per language (bd polyglot-pdf-alry: the
     context-carrying payload -- option labels ride as SETS with their
     parent question, field names / section titles as single items; sets
     dedupe by their ordered label tuple); the result fans out to every
     option carrying that label, under the CANONICAL key (the lowercase
     spoken-language name).
  2. only_missing=True is idempotent: a second run makes zero calls and leaves
     the schema byte-identical; an option covered under ANY accepted key form
     (name / short code / full BCP-47) counts as covered and is not rewritten;
     a pre-existing translation of a duplicate label fans out to uncovered
     twins WITHOUT a model call.
  3. value / label / spoken_label are never touched.
  4. A per-language failure (None or exception) skips that language, reports
     it in failed_languages, and does not disturb the others; a re-run with a
     healthy adapter fills exactly the gap.
  5. End to end: build_translation_overrides on a baked schema makes ZERO
     translate_labels calls (the precedence no-op the design promises).

ASCII only (scar #6): non-ASCII fixture strings use unicode escapes.
"""
import json

import pytest
from unittest.mock import AsyncMock, MagicMock

import backend.services.option_translation as ot

ESPANOL_MASCULINO = "Masculino"
ESPANOL_FEMENINO = "Femenino"
ESPANOL_SI = "S\u00ed"  # "Si" with acute i -- unicode escape keeps this file ASCII
FRANCAIS_OUI = "Oui"

LANGS = {"spanish": "es-US", "french": "fr-FR"}


@pytest.fixture(autouse=True)
def _fresh_cache():
    ot._reset_cache_for_tests()
    yield
    ot._reset_cache_for_tests()


@pytest.fixture(autouse=True)
def _verify_gate_off(monkeypatch):
    """These are the BAKE-mechanics pins; the verify/rectify gate (bd
    polyglot-pdf-9ikj) has its own spec in test_translation_verify.py. With
    the gate off the report is pinned byte-identical to its pre-gate shape
    (no `flags` / `verify` keys), which is itself part of the 9ikj
    contract. The default-ON resolution reads get_settings() at call time,
    so patching the config module covers every call here."""
    from types import SimpleNamespace

    from backend import config
    monkeypatch.setattr(
        config, "get_settings",
        lambda: SimpleNamespace(TRANSLATION_VERIFY_ENABLED=False))


def _schema(fields=None):
    return {"fields": fields if fields is not None else [
        {"id": "sex", "type": "radio", "options": [
            {"value": "M", "label": "Male"},
            {"value": "F", "label": "Female"},
        ]},
        {"id": "confirm1", "type": "radio", "options": [
            {"value": "y1", "label": "Yes"},
            {"value": "n1", "label": "No"},
        ]},
        {"id": "confirm2", "type": "radio", "options": [
            # Duplicate labels across fields -- dedupe + fan-out targets.
            {"value": "y2", "label": "Yes"},
            {"value": "n2", "label": "No"},
        ]},
        {"id": "name", "type": "text"},
    ]}


_TRANSLATIONS = {
    "spanish": {"Male": ESPANOL_MASCULINO, "Female": ESPANOL_FEMENINO,
                "Yes": ESPANOL_SI, "No": "No"},
    "french": {"Male": "Homme", "Female": "Femme",
               "Yes": FRANCAIS_OUI, "No": "Non"},
}


def _items_response(items, table):
    """A translate_items-shaped response answering from a flat table."""
    result = {}
    for item in items:
        if item["kind"] == "option-set":
            options = {src: table[src] for src in item["options"]
                       if src in table}
            if options:
                result[item["id"]] = {"options": options}
        elif item.get("text") in table:
            result[item["id"]] = {"translation": table[item["text"]]}
    return {"items": result, "ambiguous": []}


def _items_ai(tables):
    """Healthy stub: answers translate_items from `tables` by language."""
    ai = MagicMock()

    async def _translate(items, language_name, language_code, *,
                         form_name=None, glossary_context=None):
        return _items_response(items, tables[language_name.lower()])

    ai.translate_items = AsyncMock(side_effect=_translate)
    return ai


def _text_ai():
    return _items_ai(_TRANSLATIONS)


def _payload_kinds(call):
    """(kinds, option_set_tuples, single_texts) of one translate_items call."""
    items = call.args[0]
    kinds = sorted(i["kind"] for i in items)
    sets = sorted(tuple(i["options"]) for i in items
                  if i["kind"] == "option-set")
    texts = sorted(i["text"] for i in items if i["kind"] != "option-set")
    return kinds, sets, texts


def _options(schema, field_id):
    return next(f for f in schema["fields"] if f["id"] == field_id)["options"]


# --- 1. Dedupe, one call per language, canonical-key fan-out -------------------

@pytest.mark.asyncio
async def test_bake_one_call_per_language_over_deduped_missing():
    schema = _schema()
    ai = _text_ai()
    report = await ot.bake_label_translations(schema, ai, LANGS)

    assert ai.translate_items.await_count == 2
    for call in ai.translate_items.await_args_list:
        kinds, sets, texts = _payload_kinds(call)
        # The context payload: two DEDUPED option sets (sex; the identical
        # Yes/No twins collapse to one set), no field names/sections here.
        assert kinds == ["option-set", "option-set"]
        assert sets == [("Male", "Female"), ("Yes", "No")]
        assert texts == []
    names = sorted(call.args[1] for call in ai.translate_items.await_args_list)
    assert names == ["French", "Spanish"]
    assert report["changed"] is True
    assert report["failed_languages"] == []
    assert report["languages"]["spanish"] == {
        "labels": 4, "missing": 4, "translated": 4,
        "options_updated": 6, "failed": False,
        # Spoken-name bake keys (bd polyglot-pdf-tupu.1); this fixture's fields
        # carry no name/spoken_name, so the name half is a no-op here.
        "spoken_names": 0, "names_missing": 0, "names_translated": 0,
        "fields_updated": 0,
        # Section-label bake keys (bd tupu.2); fixture has no sections.
        "section_labels": 0, "sections_missing": 0,
        "sections_translated": 0, "sections_updated": 0,
        # Forward-call attempts (bd polyglot-pdf-783r); default no-retry -> 1.
        "attempts": 1,
    }


@pytest.mark.asyncio
async def test_bake_fans_out_to_every_option_with_same_label():
    schema = _schema()
    await ot.bake_label_translations(schema, _text_ai(), {"spanish": "es-US"})

    yes1 = _options(schema, "confirm1")[0]
    yes2 = _options(schema, "confirm2")[0]
    assert yes1["label_translations"]["spanish"] == ESPANOL_SI
    assert yes2["label_translations"]["spanish"] == ESPANOL_SI


@pytest.mark.asyncio
async def test_bake_writes_lowercase_name_keys():
    schema = _schema()
    await ot.bake_label_translations(schema, _text_ai(), {"Spanish": "es-US"})

    translations = _options(schema, "sex")[0]["label_translations"]
    assert list(translations) == ["spanish"]  # not "es" / "es-US" / "Spanish"


# --- 2. Idempotency + coverage under accepted keys ------------------------------

@pytest.mark.asyncio
async def test_bake_only_missing_is_idempotent():
    schema = _schema()
    await ot.bake_label_translations(schema, _text_ai(), LANGS)
    baked = json.dumps(schema, sort_keys=True)

    ai2 = _text_ai()
    report = await ot.bake_label_translations(schema, ai2, LANGS)

    ai2.translate_items.assert_not_awaited()
    assert report["changed"] is False
    assert json.dumps(schema, sort_keys=True) == baked


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["spanish", "Spanish", "es", "es-US"])
async def test_bake_existing_any_accepted_key_counts_as_covered(key):
    schema = _schema([{"id": "sex", "options": [
        {"value": "M", "label": "Male",
         "label_translations": {key: ESPANOL_MASCULINO}},
    ]}])
    ai = _text_ai()
    report = await ot.bake_label_translations(schema, ai, {"spanish": "es-US"})

    ai.translate_items.assert_not_awaited()
    assert report["changed"] is False
    # No rewrite to the canonical key -- minimal diffs.
    assert _options(schema, "sex")[0]["label_translations"] == {
        key: ESPANOL_MASCULINO}


@pytest.mark.asyncio
async def test_bake_reuses_existing_translation_for_uncovered_duplicate():
    schema = _schema([
        {"id": "confirm1", "options": [
            {"value": "y1", "label": "Yes",
             "label_translations": {"spanish": ESPANOL_SI}},
        ]},
        {"id": "confirm2", "options": [
            {"value": "y2", "label": "Yes"},
        ]},
    ])
    ai = _text_ai()
    report = await ot.bake_label_translations(schema, ai, {"spanish": "es-US"})

    ai.translate_items.assert_not_awaited()  # "Yes" is kit-covered
    assert _options(schema, "confirm2")[0]["label_translations"] == {
        "spanish": ESPANOL_SI}
    assert report["changed"] is True
    assert report["languages"]["spanish"]["options_updated"] == 1


@pytest.mark.asyncio
async def test_bake_force_overwrites_canonical_key():
    schema = _schema([{"id": "sex", "options": [
        {"value": "M", "label": "Male",
         "label_translations": {"es": "stale-after-rename"}},
    ]}])
    await ot.bake_label_translations(
        schema, _text_ai(), {"spanish": "es-US"}, only_missing=False)

    translations = _options(schema, "sex")[0]["label_translations"]
    assert translations["spanish"] == ESPANOL_MASCULINO
    assert translations["es"] == "stale-after-rename"  # reader prefers the name key


# --- 3. Untouched surfaces -------------------------------------------------------

@pytest.mark.asyncio
async def test_bake_never_touches_value_label_spoken_label():
    schema = _schema([{"id": "sex", "options": [
        {"value": "M", "label": "Male", "spoken_label": "male"},
    ]}])
    await ot.bake_label_translations(schema, _text_ai(), {"spanish": "es-US"})

    opt = _options(schema, "sex")[0]
    assert (opt["value"], opt["label"], opt["spoken_label"]) == (
        "M", "Male", "male")


@pytest.mark.asyncio
async def test_bake_no_options_schema_is_noop():
    schema = {"fields": [{"id": "name", "type": "text"}]}
    ai = _text_ai()
    report = await ot.bake_label_translations(schema, ai, LANGS)

    ai.translate_items.assert_not_awaited()
    assert report["changed"] is False


@pytest.mark.asyncio
async def test_bake_skips_table_column_options():
    # Parity with the runtime _collect_labels traversal: table-column options
    # are not walked (none exist in the shipped kits either).
    schema = {"fields": [{"id": "t", "type": "table", "columns": [
        {"id": "c1", "options": [{"value": "y", "label": "Yes"}]},
    ]}]}
    ai = _text_ai()
    report = await ot.bake_label_translations(schema, ai, {"spanish": "es-US"})

    ai.translate_items.assert_not_awaited()
    assert report["changed"] is False


@pytest.mark.asyncio
async def test_bake_skips_english():
    schema = _schema()
    ai = _text_ai()
    report = await ot.bake_label_translations(schema, ai, {"english": "en-US"})

    ai.translate_items.assert_not_awaited()
    assert report["changed"] is False
    assert report["languages"]["english"]["labels"] == 0


# --- 4. Per-language failure: skip, report, re-run fills the gap ---------------

@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["none", "raise"])
async def test_bake_per_language_failure_skips_and_reports(mode):
    schema = _schema()
    ai = MagicMock()

    async def _flaky(items, language_name, language_code, *,
                     form_name=None, glossary_context=None):
        if language_name.lower() == "french":
            if mode == "raise":
                raise RuntimeError("boom")
            return None
        return _items_response(items, _TRANSLATIONS["spanish"])

    ai.translate_items = AsyncMock(side_effect=_flaky)
    report = await ot.bake_label_translations(schema, ai, LANGS)

    assert report["failed_languages"] == ["french"]
    assert report["languages"]["french"]["failed"] is True
    assert report["languages"]["french"]["options_updated"] == 0
    assert report["languages"]["spanish"]["failed"] is False
    assert _options(schema, "sex")[0]["label_translations"] == {
        "spanish": ESPANOL_MASCULINO}

    # Re-run with a healthy adapter fills exactly the french gap.
    ai2 = _text_ai()
    report2 = await ot.bake_label_translations(schema, ai2, LANGS)
    assert ai2.translate_items.await_count == 1
    assert ai2.translate_items.await_args.args[1] == "French"
    assert report2["failed_languages"] == []
    assert _options(schema, "sex")[0]["label_translations"] == {
        "spanish": ESPANOL_MASCULINO, "french": "Homme"}


@pytest.mark.asyncio
async def test_bake_partial_response_leaves_label_missing_not_failed():
    schema = _schema([{"id": "sex", "options": [
        {"value": "M", "label": "Male"},
        {"value": "F", "label": "Female"},
    ]}])
    ai = MagicMock()

    async def _partial(items, language_name, language_code, *,
                       form_name=None, glossary_context=None):
        return _items_response(items, {"Male": ESPANOL_MASCULINO})

    ai.translate_items = AsyncMock(side_effect=_partial)
    report = await ot.bake_label_translations(schema, ai, {"spanish": "es-US"})

    assert report["failed_languages"] == []
    entry = report["languages"]["spanish"]
    assert (entry["missing"], entry["translated"]) == (2, 1)
    assert "label_translations" not in _options(schema, "sex")[1]


# --- 5. End to end: baked schema short-circuits the runtime secretary ----------

@pytest.mark.asyncio
async def test_baked_schema_makes_runtime_secretary_a_noop():
    schema = _schema()
    await ot.bake_label_translations(schema, _text_ai(), {"spanish": "es-US"})

    runtime_ai = MagicMock()
    runtime_ai.translate_items = AsyncMock(return_value={"items": {}})
    overrides = await ot.build_translation_overrides(
        schema, "Spanish", runtime_ai)

    runtime_ai.translate_items.assert_not_awaited()
    assert overrides.option_labels == {
        "Male": ESPANOL_MASCULINO, "Female": ESPANOL_FEMENINO,
        "Yes": ESPANOL_SI, "No": "No"}


# --- 6. Field spoken-name bake (bd polyglot-pdf-tupu.1) ------------------------

_NAME_TRANSLATIONS = {
    "spanish": {"family name": "apellido", "given name": "nombre",
                "Male": ESPANOL_MASCULINO, "Female": ESPANOL_FEMENINO},
}


def _named_schema():
    return {"fields": [
        {"id": "f1", "type": "text", "spoken_name": "family name"},
        {"id": "f2", "type": "text", "spoken_name": "given name"},
        # Duplicate spoken name across fields -- dedupe + fan-out target.
        {"id": "f3", "type": "text", "spoken_name": "family name"},
        # No spoken_name: falls back to name (the get_field_guidance fallback).
        {"id": "f4", "type": "text", "name": "given name"},
        {"id": "sex", "type": "radio", "spoken_name": "family name", "options": [
            {"value": "M", "label": "Male"},
            {"value": "F", "label": "Female"},
        ]},
    ]}


def _name_text_ai():
    return _items_ai(_NAME_TRANSLATIONS)


@pytest.mark.asyncio
async def test_bake_translates_spoken_names_in_the_same_single_call():
    """Labels + spoken names ride ONE batched call (the union), and the name
    results fan out to every field sharing the spoken name, under the
    canonical lowercase-language-name key."""
    schema = _named_schema()
    ai = _name_text_ai()
    report = await ot.bake_label_translations(schema, ai, {"spanish": "es-US"})

    assert ai.translate_items.await_count == 1  # ONE call for everything
    kinds, sets, texts = _payload_kinds(ai.translate_items.await_args)
    assert kinds == ["field-name", "field-name", "option-set"]
    assert sets == [("Male", "Female")]
    assert texts == ["family name", "given name"]
    # The option set carries its field's spoken name as the parent question.
    set_item = next(i for i in ai.translate_items.await_args.args[0]
                    if i["kind"] == "option-set")
    assert set_item["parent_question"] == "family name"

    fields = {f["id"]: f for f in schema["fields"]}
    for fid in ("f1", "f3", "sex"):
        assert fields[fid]["spoken_name_translations"] == {"spanish": "apellido"}
    for fid in ("f2", "f4"):
        assert fields[fid]["spoken_name_translations"] == {"spanish": "nombre"}
    entry = report["languages"]["spanish"]
    assert entry["spoken_names"] == 2       # deduped unique names
    assert entry["names_missing"] == 2
    assert entry["names_translated"] == 2
    assert entry["fields_updated"] == 5


@pytest.mark.asyncio
async def test_spoken_name_bake_is_idempotent_and_respects_existing_keys():
    """Second run: zero calls, schema byte-identical. A field covered under an
    accepted alternate key (full BCP-47) is not rewritten."""
    schema = _named_schema()
    schema["fields"][1]["spoken_name_translations"] = {"es-US": "nombre de pila"}
    ai = _name_text_ai()
    await ot.bake_label_translations(schema, ai, {"spanish": "es-US"})

    # f2 was covered under the es-US key: untouched, no canonical rewrite.
    assert schema["fields"][1]["spoken_name_translations"] == {
        "es-US": "nombre de pila"}

    before = json.dumps(schema, sort_keys=True)
    ai2 = _name_text_ai()
    report2 = await ot.bake_label_translations(schema, ai2, {"spanish": "es-US"})
    ai2.translate_items.assert_not_awaited()
    assert json.dumps(schema, sort_keys=True) == before
    assert report2["changed"] is False


@pytest.mark.asyncio
async def test_spoken_name_failure_skips_language_and_rerun_fills_gap():
    """A failed language leaves spoken names unbaked and reported; a healthy
    re-run fills exactly the gap (mirrors the option-label pin)."""
    schema = _named_schema()
    failing = MagicMock()
    failing.translate_items = AsyncMock(return_value=None)
    report = await ot.bake_label_translations(schema, failing, {"spanish": "es-US"})
    assert report["failed_languages"] == ["spanish"]
    assert "spoken_name_translations" not in schema["fields"][0]

    report2 = await ot.bake_label_translations(
        schema, _name_text_ai(), {"spanish": "es-US"})
    assert report2["failed_languages"] == []
    assert schema["fields"][0]["spoken_name_translations"] == {
        "spanish": "apellido"}


@pytest.mark.asyncio
async def test_bake_payload_carries_form_name_from_form_metadata():
    """Criterion-1 form-name clause (outer-review catch: previously no test
    exercised _form_name, so a broken derivation would have passed): the
    bake passes the form_metadata-derived reference as the form_name kwarg."""
    schema = _schema() | {"form_metadata": {
        "title": "U.S. Individual Income Tax Return", "form_number": "1040"}}
    ai = _text_ai()
    await ot.bake_label_translations(schema, ai, {"spanish": "es-US"})
    call = ai.translate_items.await_args
    assert call.kwargs["form_name"] \
        == "U.S. Individual Income Tax Return (Form 1040)"


@pytest.mark.asyncio
async def test_bake_form_name_absent_metadata_is_none():
    schema = _schema()  # no form_metadata
    ai = _text_ai()
    await ot.bake_label_translations(schema, ai, {"spanish": "es-US"})
    assert ai.translate_items.await_args.kwargs["form_name"] is None


@pytest.mark.asyncio
async def test_ambiguous_self_flags_surface_as_warning_findings():
    """The translator's `ambiguous` self-flag (bd alry, exit criterion 3)
    becomes a translation-ambiguous-source WARNING finding in the report,
    path-resolved to the kit location -- even with the verify gate OFF
    (the flag comes from the FORWARD call, not the verify loop)."""
    schema = {"fields": [
        {"id": "status", "type": "radio", "spoken_name": "marital status",
         "options": [{"value": "single", "label": "Single"}]},
    ]}
    ai = MagicMock()

    async def _translate(items, language_name, language_code, *,
                         form_name=None, glossary_context=None):
        # Full table (spoken name included) so the coverage rule (bd x41u)
        # stays silent -- this test pins the ambiguous flag alone.
        response = _items_response(items, {
            "Single": "Soltero(a)", "marital status": "estado civil"})
        # The translator flags the option-set item as under-determined.
        response["ambiguous"] = [
            i["id"] for i in items if i["kind"] == "option-set"]
        return response

    ai.translate_items = AsyncMock(side_effect=_translate)
    report = await ot.bake_label_translations(
        schema, ai, {"spanish": "es-US"})

    flags = report["flags"]
    assert len(flags) == 1
    assert flags[0]["rule"] == "translation-ambiguous-source"
    assert flags[0]["severity"] == "WARNING"
    assert flags[0]["field_id"] == "status"
    assert flags[0]["path"].endswith(
        ".options[single].label_translations.spanish")
    # The translation itself still baked (the flag is advisory).
    opt = schema["fields"][0]["options"][0]
    assert opt["label_translations"]["spanish"] == "Soltero(a)"


@pytest.mark.asyncio
async def test_shared_string_rides_one_call_and_lands_in_both_places():
    """A string that is BOTH an option label and a field spoken name rides
    ONE translate_items call -- once per KIND (an option-set entry + a
    field-name entry; same text, different context, deliberately -- bd
    alry) -- and the results fan out to label_translations AND
    spoken_name_translations."""
    schema = {"fields": [
        {"id": "confirm", "type": "radio", "spoken_name": "Yes", "options": [
            {"value": "y", "label": "Yes"},
        ]},
    ]}
    ai = _items_ai({"spanish": {"Yes": ESPANOL_SI}})
    await ot.bake_label_translations(schema, ai, {"spanish": "es-US"})

    ai.translate_items.assert_awaited_once()
    kinds, sets, texts = _payload_kinds(ai.translate_items.await_args)
    assert kinds == ["field-name", "option-set"]
    assert sets == [("Yes",)] and texts == ["Yes"]
    field = schema["fields"][0]
    assert field["options"][0]["label_translations"] == {"spanish": ESPANOL_SI}
    assert field["spoken_name_translations"] == {"spanish": ESPANOL_SI}


@pytest.mark.asyncio
async def test_verify_counts_vs_flags_fanout_semantics(monkeypatch):
    """bd polyglot-pdf-kpar: entry['verify'] counts tally verified SOURCE
    STRINGS while report['flags'] carries one finding per KIT LOCATION --
    a source repeated on several fields fans one VerifyFlag out to several
    findings, so len(flags) >= counts, with equality after deduping
    findings by (rule, source). This pins that relationship (the V5
    artifact's apparent i-90 'undercount' was exactly this)."""
    from backend.services.translation_verify import VerifyFlag, VerifyResult

    # 'Yes' appears as an option label on TWO fields -> one flagged source,
    # two kit locations.
    schema = {"fields": [
        {"id": "c1", "type": "radio",
         "options": [{"value": "y1", "label": "Yes"}]},
        {"id": "c2", "type": "radio",
         "options": [{"value": "y2", "label": "Yes"}]},
    ]}
    ai = _items_ai({"spanish": {"Yes": "Si"}})

    async def _fake_verify(*, language_name, language_code, fresh, pro_ai,
                           lite_ai, glossary):
        return VerifyResult(
            available=True,
            final=fresh,
            flags=[VerifyFlag(
                taxonomy="translation-drift-rectified", kind="option-label",
                source="Yes", message="judge: drift; rectified clean")],
            counts={"checked": 1, "mechanical": 0, "judge_flagged": 1,
                    "rectified": 1, "unresolved": 0},
        )

    monkeypatch.setattr(ot, "verify_fresh_translations", _fake_verify)
    report = await ot.bake_label_translations(
        schema, ai, {"spanish": "es-US"}, verify=True,
        verify_lite_ai=object())

    rectified = [f for f in report["flags"]
                 if f["rule"] == "translation-drift-rectified"]
    # One verified source string -> counts say 1 ...
    assert report["languages"]["spanish"]["verify"]["rectified"] == 1
    # ... but TWO kit locations -> two findings, distinct field ids.
    assert len(rectified) == 2
    assert {f["field_id"] for f in rectified} == {"c1", "c2"}
    # The reconciliation rule: dedup by (rule, source-location-independent)
    # -- here both findings trace to the single source 'Yes'.
    assert len({f["rule"] for f in rectified}) == 1


@pytest.mark.asyncio
async def test_failed_language_surfaces_coverage_flags():
    """bd polyglot-pdf-x41u: a language whose batch call fails leaves its
    strings falling back to ENGLISH labels mid-session -- the report must
    flag the gap through the same flags channel, scoped to the languages
    this bake addressed."""
    schema = _schema()
    ai = MagicMock()

    async def _flaky(items, language_name, language_code, *,
                     form_name=None, glossary_context=None):
        if language_name.lower() == "french":
            return None
        return _items_response(items, _TRANSLATIONS[language_name.lower()])

    ai.translate_items = AsyncMock(side_effect=_flaky)
    report = await ot.bake_label_translations(schema, ai, LANGS)

    assert report["failed_languages"] == ["french"]
    coverage = [f for f in report.get("flags", [])
                if f["rule"] == "translation-coverage"]
    assert len(coverage) == 1
    assert coverage[0]["path"] == "coverage.french"
    assert "ENGLISH" in coverage[0]["message"]
    # Spanish succeeded and is fully covered -> no coverage flag for it,
    # and the deliberate two-language scope is not judged against the
    # other 15 supported languages.
    assert not any("spanish" in f["path"] for f in coverage)


@pytest.mark.asyncio
async def test_fully_successful_bake_has_no_coverage_flags():
    schema = _schema()
    report = await ot.bake_label_translations(
        schema, _items_ai(_TRANSLATIONS), LANGS)
    assert not any(
        f["rule"] == "translation-coverage"
        for f in report.get("flags", []))


@pytest.mark.asyncio
async def test_totally_failed_scoped_bake_still_surfaces_coverage():
    """fresh-eyes gap (bd x41u): when EVERY requested language fails, the
    report must still carry coverage findings -- previously the
    untranslated-kit silence swallowed exactly this outage case."""
    schema = _schema()
    ai = MagicMock()
    ai.translate_items = AsyncMock(return_value=None)

    report = await ot.bake_label_translations(
        schema, ai, {"french": "fr-FR"})

    assert report["failed_languages"] == ["french"]
    coverage = [f for f in report.get("flags", [])
                if f["rule"] == "translation-coverage"]
    assert [f["path"] for f in coverage] == ["coverage.french"]


# --- 8. Per-language retry with backoff (bd polyglot-pdf-783r) ------------------


@pytest.mark.asyncio
async def test_bake_retries_a_failing_language_with_backoff(monkeypatch):
    """A language whose forward call fails twice then succeeds is retried per
    the attempt_delays, sleeping between tries; the third attempt lands and the
    language is NOT reported failed. The sleeps are the given delays in order."""
    slept = []

    async def _fake_sleep(secs):
        slept.append(secs)

    monkeypatch.setattr(ot.asyncio, "sleep", _fake_sleep)

    schema = _schema([{"id": "sex", "options": [
        {"value": "M", "label": "Male"},
        {"value": "F", "label": "Female"},
    ]}])
    ai = MagicMock()
    calls = {"n": 0}

    async def _fail_twice(items, language_name, language_code, *,
                          form_name=None, glossary_context=None):
        calls["n"] += 1
        if calls["n"] < 3:
            return None  # transient failure
        return _items_response(items, _TRANSLATIONS["spanish"])

    ai.translate_items = AsyncMock(side_effect=_fail_twice)
    report = await ot.bake_label_translations(
        schema, ai, {"spanish": "es-US"}, attempt_delays=(1.0, 5.0))

    assert calls["n"] == 3                       # two failures + the success
    assert slept == [1.0, 5.0]                   # backoff in order
    assert report["failed_languages"] == []      # recovered
    assert report["languages"]["spanish"]["attempts"] == 3
    assert _options(schema, "sex")[0]["label_translations"] == {
        "spanish": ESPANOL_MASCULINO}


@pytest.mark.asyncio
async def test_bake_retry_exhausted_reports_failed(monkeypatch):
    """When every attempt fails, the language is reported failed after
    len(attempt_delays)+1 tries and the schema is left uncovered (the caller's
    coverage gate then blocks / re-runs)."""
    async def _fake_sleep(_secs):
        return None

    monkeypatch.setattr(ot.asyncio, "sleep", _fake_sleep)

    schema = _schema([{"id": "sex", "options": [
        {"value": "M", "label": "Male"},
        {"value": "F", "label": "Female"},
    ]}])
    ai = MagicMock()
    ai.translate_items = AsyncMock(return_value=None)  # always fails

    report = await ot.bake_label_translations(
        schema, ai, {"spanish": "es-US"}, attempt_delays=(1.0, 5.0))

    assert ai.translate_items.await_count == 3    # 1 + 2 retries
    assert report["failed_languages"] == ["spanish"]
    assert report["languages"]["spanish"]["attempts"] == 3
    assert "label_translations" not in _options(schema, "sex")[0]


@pytest.mark.asyncio
async def test_bake_no_retry_by_default_single_attempt(monkeypatch):
    """attempt_delays defaults to () -- one attempt, no sleep (the pre-783r
    shape / the runtime path's behavior)."""
    sleeps = []

    async def _fake_sleep(secs):
        sleeps.append(secs)

    monkeypatch.setattr(ot.asyncio, "sleep", _fake_sleep)

    schema = _schema([{"id": "sex", "options": [
        {"value": "M", "label": "Male"},
    ]}])
    ai = MagicMock()
    ai.translate_items = AsyncMock(return_value=None)

    report = await ot.bake_label_translations(schema, ai, {"spanish": "es-US"})

    assert ai.translate_items.await_count == 1
    assert sleeps == []
    assert report["languages"]["spanish"]["attempts"] == 1


# --- 9. Whole-kit coverage summary for the completion gate (bd 783r) -----------


def test_coverage_summary_empty_kit_is_trivially_complete():
    """A kit with nothing to translate is complete (never traps it in draft)."""
    summary = ot.translation_coverage_summary({"fields": [], "sections": []})
    assert summary.complete
    assert summary.incomplete_languages == []
    assert summary.covered_languages == summary.total_languages


@pytest.mark.asyncio
async def test_coverage_summary_flags_a_partially_covered_kit():
    """A kit missing ONE language is incomplete, names that language, and the
    N-of-M message counts it."""
    schema = _schema([{"id": "sex", "type": "radio", "options": [
        {"value": "M", "label": "Male"},
        {"value": "F", "label": "Female"},
    ]}])
    # Cover every supported language EXCEPT one.
    langs = {n: c for n, c in ot.SPOKEN_LANGUAGE_BCP47.items() if n != "english"}
    dropped = sorted(langs)[0]
    await ot.bake_label_translations(
        schema, _items_ai({n: {"Male": "x", "Female": "y"} for n in langs}),
        {n: c for n, c in langs.items() if n != dropped})

    summary = ot.translation_coverage_summary(schema)
    assert not summary.complete
    assert summary.incomplete_languages == [dropped]
    assert summary.covered_languages == summary.total_languages - 1
    assert "%d of %d" % (summary.total_languages - 1, summary.total_languages) \
        in summary.message()


@pytest.mark.asyncio
async def test_coverage_summary_complete_after_full_bake():
    """A fully baked kit reads complete across every supported language."""
    schema = _schema([{"id": "sex", "type": "radio", "options": [
        {"value": "M", "label": "Male"},
        {"value": "F", "label": "Female"},
    ]}])
    langs = {n: c for n, c in ot.SPOKEN_LANGUAGE_BCP47.items() if n != "english"}
    await ot.bake_label_translations(
        schema, _items_ai({n: {"Male": "x", "Female": "y"} for n in langs}),
        langs)

    summary = ot.translation_coverage_summary(schema)
    assert summary.complete
    assert summary.covered_languages == summary.total_languages
