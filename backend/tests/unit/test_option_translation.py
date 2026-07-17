"""Spec for runtime option-label translation (bd polyglot-pdf-ow1e).

Multiple-choice option labels reached the voice model English-only and were
translated aloud on the fly, which misfired live. The fix: at session start the
secretary (lite text model) translates the unique option labels into the
session language; guidance renders then substitute the translated labels
(values untouched -- tool-call matching unaffected).

Pins:
  1. Label collection dedupes; kit label_translations take precedence over the
     secretary (accepting name / lowercase / short-code / full-code keys), and
     the secretary is NOT called when every label is kit-covered.
  2. Failure / timeout fails open to {} (English labels) and is NOT cached, so
     the next session retries; successes are cached per (form, language) and
     concurrent sessions share one in-flight build.
  3. get_field_guidance / render_field_guidance substitute overridden labels,
     OMIT spoken_label on overridden options, and never touch values.
  4. FormFillingService fires the background task only when: flag on, language
     known + non-English + code-backed, text model wired.

ASCII only (scar #6): non-ASCII fixture strings use unicode escapes.
"""
import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock

import backend.services.option_translation as ot
from backend.config import Settings
from backend.services.ai_context import render_field_guidance
from backend.services.form_filling_service import FormFillingService
from backend.services.manifest_service import get_field_guidance

ESPANOL_MASCULINO = "Masculino"
ESPANOL_FEMENINO = "Femenino"


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
            # Duplicate labels across fields -- must be deduped.
            {"value": "y2", "label": "Yes"},
            {"value": "n2", "label": "No"},
        ]},
        {"id": "name", "type": "text"},
    ]}


def _text_ai(result):
    ai = MagicMock()
    ai.translate_labels = AsyncMock(return_value=result)
    return ai


# --- 1. Collection, dedupe, kit precedence ------------------------------------

@pytest.mark.asyncio
async def test_build_dedupes_and_batches_one_call():
    ai = _text_ai({"Male": ESPANOL_MASCULINO, "Female": ESPANOL_FEMENINO,
                   "Yes": "Si", "No": "No"})
    overrides = await ot.build_option_label_overrides(_schema(), "Spanish", ai)

    ai.translate_labels.assert_awaited_once()
    labels_arg = ai.translate_labels.await_args.args[0]
    # Unique labels only, order preserved; the text field contributes nothing.
    assert labels_arg == ["Male", "Female", "Yes", "No"]
    assert overrides["Male"] == ESPANOL_MASCULINO
    assert overrides["Yes"] == "Si"


@pytest.mark.asyncio
async def test_build_pins_language_name_and_code():
    ai = _text_ai({"Male": ESPANOL_MASCULINO})
    await ot.build_option_label_overrides(
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
    overrides = await ot.build_option_label_overrides(_schema(fields), "Spanish", ai)

    assert overrides["Male"] == ESPANOL_MASCULINO
    assert overrides["Female"] == ESPANOL_FEMENINO
    # Only the non-kit-covered remainder goes to the secretary.
    assert ai.translate_labels.await_args.args[0] == ["Female"]


@pytest.mark.asyncio
async def test_secretary_not_called_when_all_labels_kit_covered():
    fields = [{"id": "sex", "options": [
        {"value": "M", "label": "Male",
         "label_translations": {"es": ESPANOL_MASCULINO}},
    ]}]
    ai = _text_ai({})
    overrides = await ot.build_option_label_overrides(_schema(fields), "Spanish", ai)
    assert overrides == {"Male": ESPANOL_MASCULINO}
    ai.translate_labels.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_option_labels_returns_empty_without_call():
    ai = _text_ai({})
    overrides = await ot.build_option_label_overrides(
        _schema([{"id": "name", "type": "text"}]), "Spanish", ai)
    assert overrides == {}
    ai.translate_labels.assert_not_awaited()


# --- 2. Fail-open, timeout, cache ---------------------------------------------

@pytest.mark.asyncio
async def test_translate_failure_fails_open_and_is_not_cached():
    ai = _text_ai(None)  # translate_labels' fail-open signal
    result = await ot.get_option_label_overrides("i-90", _schema(), "Spanish", ai)
    assert result == {}

    # Next session retries: a second call reaches the secretary again.
    ai2 = _text_ai({"Male": ESPANOL_MASCULINO, "Female": ESPANOL_FEMENINO,
                    "Yes": "Si", "No": "No"})
    result2 = await ot.get_option_label_overrides("i-90", _schema(), "Spanish", ai2)
    assert result2["Male"] == ESPANOL_MASCULINO
    ai2.translate_labels.assert_awaited_once()


@pytest.mark.asyncio
async def test_timeout_fails_open_and_is_not_cached(monkeypatch):
    monkeypatch.setattr(ot, "OPTION_TRANSLATION_TIMEOUT_S", 0.01)

    async def _slow(*_a, **_k):
        await asyncio.sleep(1.0)

    ai = MagicMock()
    ai.translate_labels = _slow
    result = await ot.get_option_label_overrides("i-90", _schema(), "Spanish", ai)
    assert result == {}
    assert ("i-90", "spanish") not in ot._build_tasks


@pytest.mark.asyncio
async def test_success_is_cached_one_call_per_form_language():
    ai = _text_ai({"Male": ESPANOL_MASCULINO, "Female": ESPANOL_FEMENINO,
                   "Yes": "Si", "No": "No"})
    # Concurrent sessions share ONE in-flight build...
    r1, r2 = await asyncio.gather(
        ot.get_option_label_overrides("i-90", _schema(), "Spanish", ai),
        ot.get_option_label_overrides("i-90", _schema(), "Spanish", ai),
    )
    # ...and a later session hits the completed result.
    r3 = await ot.get_option_label_overrides("i-90", _schema(), "Spanish", ai)
    assert r1 == r2 == r3
    ai.translate_labels.assert_awaited_once()

    # A DIFFERENT language is its own cache entry.
    ai_fr = _text_ai({"Male": "Homme", "Female": "Femme",
                      "Yes": "Oui", "No": "Non"})
    r_fr = await ot.get_option_label_overrides("i-90", _schema(), "French", ai_fr)
    assert r_fr["Male"] == "Homme"
    ai_fr.translate_labels.assert_awaited_once()


@pytest.mark.asyncio
async def test_awaiter_cancellation_leaves_shared_build_running():
    started = asyncio.Event()
    release = asyncio.Event()

    async def _gated(*_a, **_k):
        started.set()
        await release.wait()
        return {"Male": ESPANOL_MASCULINO, "Female": ESPANOL_FEMENINO,
                "Yes": "Si", "No": "No"}

    ai = MagicMock()
    ai.translate_labels = _gated

    waiter = asyncio.ensure_future(
        ot.get_option_label_overrides("i-90", _schema(), "Spanish", ai))
    await started.wait()
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    # The shared build survives the awaiter's cancellation; a later session
    # gets its result without a second secretary call.
    release.set()
    result = await ot.get_option_label_overrides("i-90", _schema(), "Spanish", ai)
    assert result["Male"] == ESPANOL_MASCULINO


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


def test_get_field_guidance_without_overrides_is_unchanged():
    field = {"id": "sex", "type": "radio", "options": [
        {"value": "M", "label": "Male", "spoken_label": "Male option"},
    ]}
    assert get_field_guidance(field) == get_field_guidance(
        field, option_label_overrides=None)
    assert get_field_guidance(field)["options"][0]["spoken_label"] == "Male option"


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
async def test_start_session_fires_translation_and_publishes_overrides():
    ai = _text_ai({"Male": ESPANOL_MASCULINO, "Female": ESPANOL_FEMENINO,
                   "Yes": "Si", "No": "No"})
    service = _service(text_ai=ai)
    service._spoken_language = "Spanish"  # seeded pre-connect from the handshake
    await _start(service)

    assert service._option_translation_task is not None
    await service._option_translation_task
    assert service._option_translations["Male"] == ESPANOL_MASCULINO
    ai.translate_labels.assert_awaited_once()


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
async def test_translation_failure_session_keeps_english_labels():
    ai = _text_ai(None)
    service = _service(text_ai=ai)
    service._spoken_language = "Spanish"
    await _start(service)
    await service._option_translation_task
    # Fail-open: no overrides published, renders keep English labels.
    assert service._option_translations == {}
