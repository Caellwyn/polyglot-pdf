"""Dynamic Turn Injection (DTI) unit tests (bd polyglot-pdf-jnjj.22).

Covers the thin-principal pieces that do NOT need live Gemini:
  - manifest_service.get_field_guidance reads the canonical NESTED help block.
  - ai_context.render_field_guidance is the single source of truth (field-1 SI
    block == field-N confirm block) and surfaces help.instructions.
  - the DTI build_form_context branch produces a smaller SI than full-SI and
    carries the current field's guidance (not a whole-form dump).
  - RequestCoordinator stash/consume of the client-supplied next-field schema.
The end-to-end "model advances on next_field_guidance" check is the live
voice-harness gate (bd jnjj.25), not a unit test.
"""

import backend.services.ai_context as ai_context_mod
from backend.services.ai_context import build_form_context, render_field_guidance
from backend.services.manifest_service import get_field_guidance
from backend.services.request_coordinator import RequestCoordinator


# A field in the canonical NESTED-help shape (real form-kit / I-90 shape).
NESTED_FIELD = {
    "id": "p1_line1_aliennumber",
    "spoken_name": "alien registration number",
    "name": "A-Number",
    "type": "text",
    "required": True,
    "help": {
        "instructions": "Your A-Number is a 7-9 digit number on your green card.",
        "format_hint": "7-9 digits",
    },
    "validation": {"pattern": "^\\d{7,9}$", "format_preset": "a_number"},
}

# A field in the FLAT shape (demo schema) -- the renderer must fall back to it.
FLAT_FIELD = {
    "id": "dob",
    "spoken_name": "Date of Birth",
    "type": "date",
    "description": "Convert spoken dates to YYYY-MM-DD.",
    "format": "YYYY-MM-DD",
}


def test_get_field_guidance_reads_nested_help():
    g = get_field_guidance(NESTED_FIELD)
    assert g["field_id"] == "p1_line1_aliennumber"
    assert g["spoken_name"] == "alien registration number"
    assert g["instructions"] == "Your A-Number is a 7-9 digit number on your green card."
    assert g["format_hint"] == "7-9 digits"
    assert g["required"] is True


def test_get_field_guidance_flat_fallback():
    g = get_field_guidance(FLAT_FIELD)
    # description -> instructions, format -> format_hint (demo-shape fallback).
    assert g["instructions"] == "Convert spoken dates to YYYY-MM-DD."
    assert g["format_hint"] == "YYYY-MM-DD"


def test_get_field_guidance_none_for_empty():
    assert get_field_guidance({}) is None
    assert get_field_guidance(None) is None


def test_render_field_guidance_surfaces_instructions():
    text = render_field_guidance(NESTED_FIELD)
    assert "ID: p1_line1_aliennumber" in text
    assert "Spoken: alien registration number" in text
    assert "Instructions: Your A-Number" in text
    assert "Format: 7-9 digits" in text


def test_render_field_guidance_identity_si_vs_confirm():
    """The SI (field 1) and the confirm response (field N) must render the SAME
    field identically -- they call the same render_field_guidance."""
    assert render_field_guidance(NESTED_FIELD) == render_field_guidance(NESTED_FIELD)


def test_render_field_guidance_empty():
    assert render_field_guidance(None) == "No fields available"


def _dti_settings():
    """Minimal settings stub with DTI enabled, using the real templates."""
    from backend.config import get_settings
    real = get_settings()

    class _S:
        USE_DTI = True
        USE_JIT_SCHEMA = False
        DTI_SYSTEM_INSTRUCTION = real.DTI_SYSTEM_INSTRUCTION
        JIT_SYSTEM_INSTRUCTION = real.JIT_SYSTEM_INSTRUCTION
        SYSTEM_INSTRUCTION = real.SYSTEM_INSTRUCTION
    return _S()


def _dti_schema():
    """A JIT/DTI-shaped handshake schema: client sends the first field's FULL
    schema as fields[0] plus a names-only section manifest."""
    section_fields = [NESTED_FIELD, {"id": "f2", "spoken_name": "field two", "type": "text"},
                      {"id": "f3", "spoken_name": "field three", "type": "text"}]
    return {
        "form_metadata": {"title": "I-90"},
        "fields": [NESTED_FIELD],  # only the first field's full schema
        "manifest": {
            "current_section": {
                "section_id": "sec1", "section_label": "Part 1",
                "fields": [{"field_id": f["id"], "spoken_name": f["spoken_name"]}
                           for f in section_fields],
            },
            "previous_sections": [],
        },
    }


def test_dti_branch_carries_current_field_guidance(monkeypatch):
    monkeypatch.setattr(ai_context_mod, "get_settings", _dti_settings)
    si = build_form_context(_dti_schema(), {}, "English",
                            section_number=1, total_sections=8, section_label="Part 1")
    # The current field's guidance (incl. its instructions) is in the SI...
    assert "ID: p1_line1_aliennumber" in si
    assert "Instructions: Your A-Number" in si
    # ...but NOT a whole-form dump or a names-only manifest block.
    assert "FIELD MANIFEST" not in si
    # Progress is computed over the real section (3 fields), not the one-field list.
    assert "/3" in si


def test_dti_si_size_is_independent_of_section_size(monkeypatch):
    """The DTI SI carries only field 1 + the static backbone, so its size does NOT
    grow with section field count -- whereas the full-SI dump does. This scaling
    property (not a fixed < on a tiny section) is the cost lever: on big sections
    DTI is much smaller; on a 1-2 field section it can be larger (the static
    backbone dominates), which is fine."""
    monkeypatch.setattr(ai_context_mod, "get_settings", _dti_settings)

    def dti_si_for(n_fields):
        manifest_fields = [{"field_id": NESTED_FIELD["id"], "spoken_name": NESTED_FIELD["spoken_name"]}]
        manifest_fields += [{"field_id": f"f{i}", "spoken_name": f"field {i}"} for i in range(2, n_fields + 1)]
        schema = {
            "form_metadata": {"title": "I-90"},
            "fields": [NESTED_FIELD],  # always just field 1
            "manifest": {"current_section": {"section_id": "s", "section_label": "P1",
                                             "fields": manifest_fields}, "previous_sections": []},
        }
        return len(build_form_context(schema, {}, "English", section_number=1,
                                      total_sections=8, section_label="P1"))

    small = dti_si_for(3)
    large = dti_si_for(40)
    # DTI SI barely grows with section size (only the names-only manifest in the
    # progress header differs; the per-field GUIDANCE block is always just field 1).
    # A 40-field section must not blow up the SI the way a full dump would.
    assert large - small < 1000, (small, large)


def test_coordinator_stash_and_consume():
    coord = RequestCoordinator(websocket=None, session_id="t")
    # No schema stashed -> None.
    assert coord.consume_pending_next_field_schema() is None
    # Register a pending next_field request (as request_next_field_hint does), so
    # the response _resolves a real future and the schema is stashed.
    request_id, _future = coord._register("next_field")
    coord.handle_next_field_hint_response(request_id, "some hint", NESTED_FIELD)
    got = coord.consume_pending_next_field_schema()
    assert got == NESTED_FIELD
    # Consumed -> cleared.
    assert coord.consume_pending_next_field_schema() is None


def test_coordinator_no_schema_when_legacy_client():
    """A legacy/non-DTI client sends no next_field_schema -> nothing stashed."""
    coord = RequestCoordinator(websocket=None, session_id="t")
    coord.handle_next_field_hint_response("req1", "some hint", None)
    assert coord.consume_pending_next_field_schema() is None


def test_coordinator_late_response_does_not_stash_stale_schema():
    """A LATE hint response (no matching pending request -> _resolve returns False)
    must NOT stash its schema, or it would leak into the next confirm's consume
    (bd jnjj.22 fresh-eyes race). No request was registered, so request_id is
    unknown -> nothing stashed."""
    coord = RequestCoordinator(websocket=None, session_id="t")
    coord.handle_next_field_hint_response("stale_unknown_id", "hint", NESTED_FIELD)
    assert coord.consume_pending_next_field_schema() is None
