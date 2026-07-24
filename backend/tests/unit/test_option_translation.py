"""Spec for runtime session-language translation (bd polyglot-pdf-ow1e labels;
bd polyglot-pdf-tupu.2 field spoken names + section labels).

Multiple-choice option labels reached the voice model English-only and were
translated aloud on the fly, which misfired live; field spoken names + section
labels had the same problem (the 6mzi assessment: English jargon read aloud,
per-field secretary spam, English section titles). The fix: at session start
the secretary (lite text model) translates ALL THREE string classes -- option
labels, field spoken names, section labels -- in ONE batched call over the
union of kit-uncovered strings; guidance renders then substitute the
translations (values/ids untouched -- tool-call matching unaffected).

Pins:
  1. Collection dedupes; kit translations (option label_translations + field
     spoken_name_translations) take precedence over the secretary (accepting
     name / lowercase / short-code / full-code keys), and the secretary is NOT
     called when everything is kit-covered. Section labels have no kit
     structure and always ride the call.
  2. Failure / timeout fails open to EMPTY_OVERRIDES (English) and is NOT
     cached, so the next session retries; successes are cached per
     (form, language) and concurrent sessions share one in-flight build.
  3. get_field_guidance / render_field_guidance substitute overridden labels
     AND the spoken name; render_section_metadata substitutes the section
     label + previous spoken names; no-override calls are byte-identical.
  4. FormFillingService fires the background task only when: flag on, language
     known + non-English + code-backed, text model wired; it publishes all
     three maps.

ASCII only (scar #6): non-ASCII fixture strings use unicode escapes.
"""
import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock

import backend.services.option_translation as ot
from backend.config import Settings
from backend.services.ai_context import (
    render_field_guidance,
    render_section_metadata,
)
from backend.services.form_filling_service import FormFillingService
from backend.services.manifest_service import get_field_guidance

ESPANOL_MASCULINO = "Masculino"
ESPANOL_FEMENINO = "Femenino"
ESPANOL_SEXO = "Sexo"
ESPANOL_SECCION = "Informacion del solicitante"


@pytest.fixture(autouse=True)
def _fresh_cache():
    ot._reset_cache_for_tests()
    yield
    ot._reset_cache_for_tests()


def _schema(fields=None, sections=None):
    schema = {"fields": fields if fields is not None else [
        {"id": "sex", "type": "radio", "options": [
            {"value": "M", "label": "Male"},
            {"value": "F", "label": "Female"},
        ]},
        {"id": "confirm1", "type": "radio", "options": [
            {"value": "y1", "label": "Yes"},
            {"value": "n1", "label": "No"},
        ]},
        {"id": "confirm2", "type": "radio", "options": [
            # Duplicate labels across fields -- must be deduped.
            {"value": "y2", "label": "Yes"},
            {"value": "n2", "label": "No"},
        ]},
        {"id": "name", "type": "text"},
    ]}
    if sections is not None:
        schema["sections"] = sections
    return schema


_DEFAULT_TABLE = {"Male": ESPANOL_MASCULINO, "Female": ESPANOL_FEMENINO,
                  "Yes": "Si", "No": "No"}


def _text_ai(result):
    ai = MagicMock()
    ai.translate_labels = AsyncMock(return_value=result)
    return ai


# --- 1. Collection, dedupe, kit precedence ------------------------------------

@pytest.mark.asyncio
async def test_build_dedupes_and_batches_one_call():
    ai = _text_ai(dict(_DEFAULT_TABLE))
    overrides = await ot.build_translation_overrides(_schema(), "Spanish", ai)

    ai.translate_labels.assert_awaited_once()
    labels_arg = ai.translate_labels.await_args.args[0]
    # Unique labels only, order preserved; the bare text field contributes
    # nothing (no name/spoken_name keys, no options).
    assert labels_arg == ["Male", "Female", "Yes", "No"]
    assert overrides.option_labels["Male"] == ESPANOL_MASCULINO
    assert overrides.option_labels["Yes"] == "Si"
    assert overrides.spoken_names == {}
    assert overrides.section_labels == {}


@pytest.mark.asyncio
async def test_build_unions_spoken_names_and_section_labels_in_one_call():
    """The tupu.2 union: labels + field spoken names + section labels ride ONE
    batched call; membership splits the result into the three maps."""
    fields = [
        {"id": "sex", "type": "radio", "spoken_name": "sex",
         "options": [{"value": "M", "label": "Male"}]},
        {"id": "family", "type": "text", "spoken_name": "family name"},
    ]
    sections = [{"id": "s1", "label": "Applicant Information"}]
    ai = _text_ai({"Male": ESPANOL_MASCULINO, "sex": ESPANOL_SEXO,
                   "family name": "apellido",
                   "Applicant Information": ESPANOL_SECCION})
    overrides = await ot.build_translation_overrides(
        _schema(fields, sections=sections), "Spanish", ai)

    ai.translate_labels.assert_awaited_once()
    assert ai.translate_labels.await_args.args[0] == [
        "Male", "sex", "family name", "Applicant Information"]
    assert overrides.option_labels == {"Male": ESPANOL_MASCULINO}
    assert overrides.spoken_names == {"sex": ESPANOL_SEXO,
                                      "family name": "apellido"}
    assert overrides.section_labels == {
        "Applicant Information": ESPANOL_SECCION}


@pytest.mark.asyncio
async def test_build_pins_language_name_and_code():
    ai = _text_ai({"Male": ESPANOL_MASCULINO})
    await ot.build_translation_overrides(
        _schema([{"id": "sex", "options": [{"value": "M", "label": "Male"}]}]),
        "Spanish", ai)
    args = ai.translate_labels.await_args.args
    assert args[1] == "Spanish"
    assert args[2] == "es-US"


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["Spanish", "spanish", "es", "es-US", "ES-us"])
async def test_kit_translations_win_over_secretary(key):
    fields = [{"id": "sex", "options": [
        {"value": "M", "label": "Male",
         "label_translations": {key: ESPANOL_MASCULINO}},
        {"value": "F", "label": "Female"},
    ]}]
    ai = _text_ai({"Female": ESPANOL_FEMENINO,
                   # A conflicting secretary answer for Male must NOT win.
                   "Male": "WRONG"})
    overrides = await ot.build_translation_overrides(
        _schema(fields), "Spanish", ai)

    assert overrides.option_labels["Male"] == ESPANOL_MASCULINO
    assert overrides.option_labels["Female"] == ESPANOL_FEMENINO
    # Only the non-kit-covered remainder goes to the secretary.
    assert ai.translate_labels.await_args.args[0] == ["Female"]


@pytest.mark.asyncio
async def test_kit_spoken_name_translations_win_over_secretary():
    fields = [
        {"id": "family", "type": "text", "spoken_name": "family name",
         "spoken_name_translations": {"spanish": "apellido"}},
        {"id": "given", "type": "text", "spoken_name": "given name"},
    ]
    ai = _text_ai({"given name": "nombre", "family name": "WRONG"})
    overrides = await ot.build_translation_overrides(
        _schema(fields), "Spanish", ai)

    assert overrides.spoken_names == {"family name": "apellido",
                                      "given name": "nombre"}
    assert ai.translate_labels.await_args.args[0] == ["given name"]


@pytest.mark.asyncio
async def test_secretary_not_called_when_everything_kit_covered():
    fields = [{"id": "sex", "spoken_name": "sex",
               "spoken_name_translations": {"es": ESPANOL_SEXO},
               "options": [
                   {"value": "M", "label": "Male",
                    "label_translations": {"es": ESPANOL_MASCULINO}},
               ]}]
    ai = _text_ai({})
    overrides = await ot.build_translation_overrides(
        _schema(fields), "Spanish", ai)
    assert overrides.option_labels == {"Male": ESPANOL_MASCULINO}
    assert overrides.spoken_names == {"sex": ESPANOL_SEXO}
    ai.translate_labels.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_schema_returns_empty_without_call():
    ai = _text_ai({})
    overrides = await ot.build_translation_overrides(
        _schema([{"id": "x", "type": "text"}]), "Spanish", ai)
    assert overrides == ot.EMPTY_OVERRIDES
    assert not overrides
    ai.translate_labels.assert_not_awaited()


# --- 2. Fail-open, timeout, cache ---------------------------------------------

@pytest.mark.asyncio
async def test_translate_failure_fails_open_and_is_not_cached():
    ai = _text_ai(None)  # translate_labels' fail-open signal
    result = await ot.get_translation_overrides("i-90", _schema(), "Spanish", ai)
    assert result == ot.EMPTY_OVERRIDES

    # Next session retries: a second call reaches the secretary again.
    ai2 = _text_ai(dict(_DEFAULT_TABLE))
    result2 = await ot.get_translation_overrides("i-90", _schema(), "Spanish", ai2)
    assert result2.option_labels["Male"] == ESPANOL_MASCULINO
    ai2.translate_labels.assert_awaited_once()


@pytest.mark.asyncio
async def test_timeout_fails_open_and_is_not_cached(monkeypatch):
    monkeypatch.setattr(ot, "OPTION_TRANSLATION_TIMEOUT_S", 0.01)

    async def _slow(*_a, **_k):
        await asyncio.sleep(1.0)

    ai = MagicMock()
    ai.translate_labels = _slow
    result = await ot.get_translation_overrides("i-90", _schema(), "Spanish", ai)
    assert result == ot.EMPTY_OVERRIDES
    assert ("i-90", "spanish") not in ot._build_tasks


@pytest.mark.asyncio
async def test_success_is_cached_one_call_per_form_language():
    ai = _text_ai(dict(_DEFAULT_TABLE))
    # Concurrent sessions share ONE in-flight build...
    r1, r2 = await asyncio.gather(
        ot.get_translation_overrides("i-90", _schema(), "Spanish", ai),
        ot.get_translation_overrides("i-90", _schema(), "Spanish", ai),
    )
    # ...and a later session hits the completed result.
    r3 = await ot.get_translation_overrides("i-90", _schema(), "Spanish", ai)
    assert r1 == r2 == r3
    ai.translate_labels.assert_awaited_once()

    # A DIFFERENT language is its own cache entry.
    ai_fr = _text_ai({"Male": "Homme", "Female": "Femme",
                      "Yes": "Oui", "No": "Non"})
    r_fr = await ot.get_translation_overrides("i-90", _schema(), "French", ai_fr)
    assert r_fr.option_labels["Male"] == "Homme"
    ai_fr.translate_labels.assert_awaited_once()


@pytest.mark.asyncio
async def test_awaiter_cancellation_leaves_shared_build_running():
    started = asyncio.Event()
    release = asyncio.Event()

    async def _gated(*_a, **_k):
        started.set()
        await release.wait()
        return dict(_DEFAULT_TABLE)

    ai = MagicMock()
    ai.translate_labels = _gated

    waiter = asyncio.ensure_future(
        ot.get_translation_overrides("i-90", _schema(), "Spanish", ai))
    await started.wait()
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    # The shared build survives the awaiter's cancellation; a later session
    # gets its result without a second secretary call.
    release.set()
    result = await ot.get_translation_overrides("i-90", _schema(), "Spanish", ai)
    assert result.option_labels["Male"] == ESPANOL_MASCULINO


# --- 3. Guidance substitution ---------------------------------------------------

def test_get_field_guidance_substitutes_labels_and_omits_spoken_label():
    field = {"id": "sex", "type": "radio", "options": [
        {"value": "M", "label": "Male", "spoken_label": "Male option"},
        {"value": "F", "label": "Female"},
        {"value": "X", "label": "Other"},
    ]}
    overrides = {"Male": ESPANOL_MASCULINO, "Female": ESPANOL_FEMENINO}
    guidance = get_field_guidance(field, option_label_overrides=overrides)

    opts = {o["value"]: o for o in guidance["options"]}
    # Overridden: translated label, spoken_label OMITTED, value untouched.
    assert opts["M"] == {"value": "M", "label": ESPANOL_MASCULINO}
    assert opts["F"] == {"value": "F", "label": ESPANOL_FEMENINO}
    # No override -> untouched.
    assert opts["X"] == {"value": "X", "label": "Other"}


def test_get_field_guidance_substitutes_spoken_name():
    field = {"id": "sex", "type": "radio", "spoken_name": "sex",
             "options": [{"value": "M", "label": "Male"}]}
    guidance = get_field_guidance(
        field, spoken_name_overrides={"sex": ESPANOL_SEXO})
    assert guidance["spoken_name"] == ESPANOL_SEXO
    # field_id and option values are untouched (tool-call matching).
    assert guidance["field_id"] == "sex"
    assert guidance["options"][0]["value"] == "M"


def test_get_field_guidance_without_overrides_is_unchanged():
    field = {"id": "sex", "type": "radio", "spoken_name": "sex", "options": [
        {"value": "M", "label": "Male", "spoken_label": "Male option"},
    ]}
    assert get_field_guidance(field) == get_field_guidance(
        field, option_label_overrides=None, spoken_name_overrides=None)
    assert get_field_guidance(field)["options"][0]["spoken_label"] == "Male option"
    assert get_field_guidance(field)["spoken_name"] == "sex"


def test_render_field_guidance_carries_translated_labels_english_values():
    field = {"id": "sex", "type": "radio", "options": [
        {"value": "M", "label": "Male"},
        {"value": "F", "label": "Female"},
    ]}
    rendered = render_field_guidance(
        field, option_label_overrides={"Male": ESPANOL_MASCULINO,
                                       "Female": ESPANOL_FEMENINO})
    assert f'"{ESPANOL_MASCULINO}" (use value: M)' in rendered
    assert f'"{ESPANOL_FEMENINO}" (use value: F)' in rendered
    assert "Male" not in rendered.replace(ESPANOL_MASCULINO, "")


def test_render_field_guidance_carries_translated_spoken_name():
    field = {"id": "sex", "type": "radio", "spoken_name": "sex",
             "options": [{"value": "M", "label": "Male"}]}
    rendered = render_field_guidance(
        field, spoken_name_overrides={"sex": ESPANOL_SEXO})
    assert f"Spoken: {ESPANOL_SEXO}" in rendered
    assert "ID: sex" in rendered  # the id itself is never translated


def test_render_section_metadata_translates_label_and_previous_names():
    block = render_section_metadata(
        form_title="I-90",
        section_number=1, total_sections=3,
        section_label="Applicant Information",
        previous_spoken_names=["family name", "given name"],
        section_label_overrides={"Applicant Information": ESPANOL_SECCION},
        spoken_name_overrides={"family name": "apellido"},
    )
    assert ESPANOL_SECCION in block
    assert "Applicant Information" not in block
    assert "apellido" in block          # translated
    assert "given name" in block        # miss -> English fallback


def test_render_section_metadata_without_overrides_is_unchanged():
    kwargs = dict(form_title="I-90", section_number=1, total_sections=3,
                  section_label="Applicant Information",
                  previous_spoken_names=["family name"])
    assert render_section_metadata(**kwargs) == render_section_metadata(
        **kwargs, section_label_overrides=None, spoken_name_overrides=None)


# --- 4. Service wiring ----------------------------------------------------------

def _service(settings=None, text_ai=None):
    return FormFillingService(
        live_ai=None, settings=settings or Settings(), text_ai=text_ai)


async def _start(service, schema=None):
    ws = MagicMock()
    ws.accept = AsyncMock()
    await service.start_session(
        ws, "ow1e-test", accept_connection=False,
        schema=schema or _schema() | {"form_metadata": {"form_number": "I-90"}},
    )


@pytest.mark.asyncio
async def test_start_session_fires_translation_and_publishes_all_maps():
    fields = [
        {"id": "sex", "type": "radio", "spoken_name": "sex",
         "options": [{"value": "M", "label": "Male"}]},
    ]
    sections = [{"id": "s1", "label": "Applicant Information"}]
    ai = _text_ai({"Male": ESPANOL_MASCULINO, "sex": ESPANOL_SEXO,
                   "Applicant Information": ESPANOL_SECCION})
    service = _service(text_ai=ai)
    service._spoken_language = "Spanish"  # seeded pre-connect from the handshake
    await _start(service, schema=_schema(fields, sections=sections)
                 | {"form_metadata": {"form_number": "I-90"}})

    assert service._option_translation_task is not None
    await service._option_translation_task
    assert service._option_translations["Male"] == ESPANOL_MASCULINO
    assert service._spoken_name_translations["sex"] == ESPANOL_SEXO
    assert service._section_label_translations[
        "Applicant Information"] == ESPANOL_SECCION
    ai.translate_labels.assert_awaited_once()


@pytest.mark.asyncio
async def test_cache_key_uses_full_schema_form_number():
    """The cache key must come from the schema the labels are collected from
    (the full-form catalog): on a DTI manifest-first handshake the per-section
    schema has NO form_metadata and resolves to 'unknown', which would make two
    different forms share one cache entry (observed live on the W-7)."""
    ai = _text_ai(dict(_DEFAULT_TABLE))
    service = _service(text_ai=ai)
    service._spoken_language = "Spanish"

    ws = MagicMock()
    ws.accept = AsyncMock()
    await service.start_session(
        ws, "ow1e-key-test", accept_connection=False,
        schema={"fields": []},  # manifest-first: no form_metadata -> 'unknown'
        full_schema=_schema() | {"form_metadata": {"form_number": "W-7"}},
    )
    await service._option_translation_task
    assert ("W-7", "spanish") in ot._build_tasks
    assert ("unknown", "spanish") not in ot._build_tasks


@pytest.mark.asyncio
async def test_english_session_makes_no_translation_call():
    ai = _text_ai({})
    service = _service(text_ai=ai)
    service._spoken_language = "English"
    await _start(service)
    assert service._option_translation_task is None
    ai.translate_labels.assert_not_awaited()


@pytest.mark.asyncio
async def test_flag_off_makes_no_translation_call():
    settings = Settings()
    settings.RUNTIME_OPTION_TRANSLATION_ENABLED = False
    ai = _text_ai({})
    service = _service(settings=settings, text_ai=ai)
    service._spoken_language = "Spanish"
    await _start(service)
    assert service._option_translation_task is None
    ai.translate_labels.assert_not_awaited()


@pytest.mark.asyncio
async def test_uncoded_language_or_missing_text_ai_skips():
    ai = _text_ai({})
    service = _service(text_ai=ai)
    service._spoken_language = "Klingon"  # not code-backed
    await _start(service)
    assert service._option_translation_task is None

    service2 = _service(text_ai=None)
    service2._spoken_language = "Spanish"
    await _start(service2)
    assert service2._option_translation_task is None


@pytest.mark.asyncio
async def test_translation_failure_session_keeps_english_text():
    ai = _text_ai(None)
    service = _service(text_ai=ai)
    service._spoken_language = "Spanish"
    await _start(service)
    await service._option_translation_task
    # Fail-open: no overrides published, renders keep English everywhere.
    assert service._option_translations == {}
    assert service._spoken_name_translations == {}
    assert service._section_label_translations == {}
