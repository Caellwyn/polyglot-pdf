"""Spec for extraction-time option-label baking (bd polyglot-pdf-2h9j).

bake_label_translations writes stock translations into a kit schema in place,
so the runtime secretary translation (bd ow1e) short-circuits via the kit
precedence rule and translations become deterministic, reviewable artifacts.

Pins:
  1. One translate_labels call per language over the DEDUPED missing set; the
     result fans out to every option carrying that label, under the CANONICAL
     key (the lowercase spoken-language name).
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


def _text_ai():
    """Healthy stub: answers from _TRANSLATIONS by language name."""
    ai = MagicMock()

    async def _translate(labels, language_name, language_code):
        table = _TRANSLATIONS[language_name.lower()]
        return {label: table[label] for label in labels if label in table}

    ai.translate_labels = AsyncMock(side_effect=_translate)
    return ai


def _options(schema, field_id):
    return next(f for f in schema["fields"] if f["id"] == field_id)["options"]


# --- 1. Dedupe, one call per language, canonical-key fan-out -------------------

@pytest.mark.asyncio
async def test_bake_one_call_per_language_over_deduped_missing():
    schema = _schema()
    ai = _text_ai()
    report = await ot.bake_label_translations(schema, ai, LANGS)

    assert ai.translate_labels.await_count == 2
    for call in ai.translate_labels.await_args_list:
        assert call.args[0] == ["Male", "Female", "Yes", "No"]
    names = sorted(call.args[1] for call in ai.translate_labels.await_args_list)
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

    ai2.translate_labels.assert_not_awaited()
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

    ai.translate_labels.assert_not_awaited()
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

    ai.translate_labels.assert_not_awaited()  # "Yes" is kit-covered
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

    ai.translate_labels.assert_not_awaited()
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

    ai.translate_labels.assert_not_awaited()
    assert report["changed"] is False


@pytest.mark.asyncio
async def test_bake_skips_english():
    schema = _schema()
    ai = _text_ai()
    report = await ot.bake_label_translations(schema, ai, {"english": "en-US"})

    ai.translate_labels.assert_not_awaited()
    assert report["changed"] is False
    assert report["languages"]["english"]["labels"] == 0


# --- 4. Per-language failure: skip, report, re-run fills the gap ---------------

@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["none", "raise"])
async def test_bake_per_language_failure_skips_and_reports(mode):
    schema = _schema()
    ai = MagicMock()

    async def _flaky(labels, language_name, language_code):
        if language_name.lower() == "french":
            if mode == "raise":
                raise RuntimeError("boom")
            return None
        return {label: _TRANSLATIONS["spanish"].get(label, "") for label in labels}

    ai.translate_labels = AsyncMock(side_effect=_flaky)
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
    assert ai2.translate_labels.await_count == 1
    assert ai2.translate_labels.await_args.args[1] == "French"
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
    ai.translate_labels = AsyncMock(return_value={"Male": ESPANOL_MASCULINO})
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
    runtime_ai.translate_labels = AsyncMock(return_value={})
    overrides = await ot.build_translation_overrides(
        schema, "Spanish", runtime_ai)

    runtime_ai.translate_labels.assert_not_awaited()
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
    ai = MagicMock()

    async def _translate(labels, language_name, language_code):
        table = _NAME_TRANSLATIONS[language_name.lower()]
        return {s: table[s] for s in labels if s in table}

    ai.translate_labels = AsyncMock(side_effect=_translate)
    return ai


@pytest.mark.asyncio
async def test_bake_translates_spoken_names_in_the_same_single_call():
    """Labels + spoken names ride ONE batched call (the union), and the name
    results fan out to every field sharing the spoken name, under the
    canonical lowercase-language-name key."""
    schema = _named_schema()
    ai = _name_text_ai()
    report = await ot.bake_label_translations(schema, ai, {"spanish": "es-US"})

    assert ai.translate_labels.await_count == 1  # ONE call for the union
    sent = ai.translate_labels.await_args.args[0]
    assert sent == ["Male", "Female", "family name", "given name"]

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
    ai2.translate_labels.assert_not_awaited()
    assert json.dumps(schema, sort_keys=True) == before
    assert report2["changed"] is False


@pytest.mark.asyncio
async def test_spoken_name_failure_skips_language_and_rerun_fills_gap():
    """A failed language leaves spoken names unbaked and reported; a healthy
    re-run fills exactly the gap (mirrors the option-label pin)."""
    schema = _named_schema()
    failing = MagicMock()
    failing.translate_labels = AsyncMock(return_value=None)
    report = await ot.bake_label_translations(schema, failing, {"spanish": "es-US"})
    assert report["failed_languages"] == ["spanish"]
    assert "spoken_name_translations" not in schema["fields"][0]

    report2 = await ot.bake_label_translations(
        schema, _name_text_ai(), {"spanish": "es-US"})
    assert report2["failed_languages"] == []
    assert schema["fields"][0]["spoken_name_translations"] == {
        "spanish": "apellido"}


@pytest.mark.asyncio
async def test_shared_string_translates_once_and_lands_in_both_places():
    """A string that is BOTH an option label and a field spoken name rides the
    union once (single call, single deduped entry) and fans out to
    label_translations AND spoken_name_translations (fresh-eyes pin, tupu.1)."""
    schema = {"fields": [
        {"id": "confirm", "type": "radio", "spoken_name": "Yes", "options": [
            {"value": "y", "label": "Yes"},
        ]},
    ]}
    ai = MagicMock()
    ai.translate_labels = AsyncMock(return_value={"Yes": ESPANOL_SI})
    await ot.bake_label_translations(schema, ai, {"spanish": "es-US"})

    ai.translate_labels.assert_awaited_once()
    assert ai.translate_labels.await_args.args[0] == ["Yes"]  # deduped union
    field = schema["fields"][0]
    assert field["options"][0]["label_translations"] == {"spanish": ESPANOL_SI}
    assert field["spoken_name_translations"] == {"spanish": ESPANOL_SI}
