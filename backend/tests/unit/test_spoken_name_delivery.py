"""Pins for the tupu.2 spoken-name delivery channels OUTSIDE the guidance
render (bd polyglot-pdf-tupu.2): the direct echo channels in CallbackHandler
(switch success message, candidate lists, secretary fields arrays) and the
next-field-hint substitution, plus the FIELD-NAMES-ALOUD SI rule.

The 6mzi assessment showed English field names reaching non-English users
through channels beyond the guidance block; the adversarial plan review
enumerated these exact sites. Each falls back to English on a miss.
"""
from unittest.mock import MagicMock

from backend.config import Settings
from backend.services.callback_handler import CallbackHandler


def _handler(overrides=None):
    h = MagicMock(spec=CallbackHandler)
    h._get_spoken_name_overrides = (lambda: overrides) if overrides else None
    h._spoken_overrides = lambda: CallbackHandler._spoken_overrides(h)
    return h


def test_translate_spoken_hits_and_misses():
    h = _handler({"family name": "apellido"})
    assert CallbackHandler._translate_spoken(h, "family name") == "apellido"
    assert CallbackHandler._translate_spoken(h, "given name") == "given name"
    assert CallbackHandler._translate_spoken(h, None) is None
    # No getter wired at all: pass-through.
    h2 = _handler(None)
    assert CallbackHandler._translate_spoken(h2, "family name") == "family name"


def test_translate_hint_substitutes_quoted_english_name():
    h = _handler({"current family name": "apellido actual"})
    schema = {"id": "p1_line3a_familyname", "name": "Family Name",
              "spoken_name": "current family name"}
    hint = "Next field to fill is #3: 'Family Name' (type: text)"
    out = CallbackHandler._translate_hint(h, hint, schema)
    assert out == "Next field to fill is #3: 'apellido actual' (type: text)"


def test_translate_hint_miss_or_no_schema_leaves_hint_untouched():
    h = _handler({"something else": "otra cosa"})
    schema = {"id": "f", "name": "Family Name", "spoken_name": "family name"}
    hint = "Next field to fill is #3: 'Family Name'"
    assert CallbackHandler._translate_hint(h, hint, schema) == hint
    assert CallbackHandler._translate_hint(h, hint, None) == hint
    assert CallbackHandler._translate_hint(h, None, schema) is None


def test_dti_and_legacy_si_pin_field_names_aloud_rule():
    """Both SIs must tell the model the guidance name is already localized and
    forbid reading English names/labels aloud in a non-English session (bd
    polyglot-pdf-tupu.2)."""
    dti = Settings().DTI_SYSTEM_INSTRUCTION.lower()
    assert "field names aloud" in dti
    assert "already in the session language" in dti
    assert "never call a tool to translate or fetch a field name" in dti
    legacy = Settings().SYSTEM_INSTRUCTION.lower()
    assert "never read an english field name or label aloud" in legacy
