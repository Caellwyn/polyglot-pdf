"""bd polyglot-pdf-52qm.4 -- the voice/secretary visibility boundary, asserted on
the shipped W-7 kit.

Two models see the form and they must see DIFFERENT things:

  voice (Live, expensive)  -- per-field guidance only. Per-turn text-in SI is
      95-98% of session cost (docs/standards/logging-and-cost.md), so a
      form-level booklet leak here is a COST bug, not just a tidiness one.
  secretary (text, cheap)  -- the whole-form catalog PLUS the verbatim booklet
      (bd wsao.1), so form-level and orphaned-passage questions are answerable.

Both surfaces exclude PDF mechanics and authoring metadata. These tests pin the
contract in docs/standards/validation-delegation.md against the real kit, so a
future schema key (or a new enrichment pass) cannot silently cross the line.
"""
import json
from pathlib import Path

import pytest

from backend.services.ai_context import render_field_guidance
from backend.services.guidance_contract import DETAILS_INLINE_MAX_CHARS
from backend.services.secretary_context import render_static_catalog

W7_SCHEMA = Path(__file__).resolve().parents[3] / "form-kits" / "w7" / "schema.json"
pytestmark = pytest.mark.skipif(not W7_SCHEMA.exists(), reason="W-7 kit not present")


def _schema():
    return json.loads(W7_SCHEMA.read_text(encoding="utf-8"))


def _all_voice_guidance(schema):
    return "".join(render_field_guidance(f) for f in schema["fields"])


def _booklet(schema):
    return ((schema.get("form_metadata") or {}).get("details") or "").strip()


def test_w7_actually_ships_a_form_level_booklet():
    """Premise guard -- without it the leak tests below prove nothing."""
    assert len(_booklet(_schema())) > 1000


def test_form_level_booklet_never_enters_voice_guidance():
    """THE cost-critical assertion: the booklet must not ride the per-turn SI."""
    schema = _schema()
    booklet = _booklet(schema)
    probe = booklet[:200]

    for field in schema["fields"]:
        rendered = render_field_guidance(field)
        assert probe not in rendered, f"booklet leaked into {field['id']} guidance"


def test_form_level_booklet_does_reach_the_secretary():
    """The other half: excluding it from voice must not drop it entirely."""
    schema = _schema()
    assert _booklet(schema)[:200] in render_static_catalog(schema)


def test_pdf_mechanics_and_authoring_metadata_reach_neither_model():
    """Excluded on BOTH surfaces: PDF plumbing, translation blobs, review notes."""
    schema = _schema()
    voice = _all_voice_guidance(schema)
    secretary = render_static_catalog(schema)

    for token in ("topmostSubform", "pdf_position", "label_translations",
                  "spoken_name_translations", "_review"):
        assert token not in voice, f"{token} leaked to the VOICE model"
        assert token not in secretary, f"{token} leaked to the SECRETARY"


def test_per_field_voice_guidance_stays_within_the_inline_details_budget():
    """No W-7 field exceeds the inline clamp, so nothing ships truncated.

    Guards the enrichment side of the contract: kits are authored to fit, and
    the clamp is a backstop rather than routine behavior.
    """
    schema = _schema()
    for field in schema["fields"]:
        details = ((field.get("help") or {}).get("details") or "")
        assert len(details) <= DETAILS_INLINE_MAX_CHARS, field["id"]


def test_voice_guidance_is_far_smaller_than_the_secretary_catalog():
    """Shape check: the expensive model gets one field, the cheap one gets the form.

    Pins the delegation's whole economic premise -- if a change ever made the
    per-field voice block approach whole-form size, the SI diet would be undone.
    """
    schema = _schema()
    secretary_chars = len(render_static_catalog(schema))
    worst_field_chars = max(
        len(render_field_guidance(f)) for f in schema["fields"]
    )
    assert worst_field_chars * 4 < secretary_chars
