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


def test_dti_current_field_is_client_selected_field_zero(monkeypatch):
    """DTI's CURRENT FIELD = schema['fields'][0], which the CLIENT pre-selects as the
    first unfilled+visible field (computeNextField). The backend must NOT re-derive
    selection -- an incomplete re-selection mis-picks confirmed/hidden/show_if fields
    (Codex PR #229 round 2). So fields[0] is authoritative, hint agrees by
    construction."""
    monkeypatch.setattr(ai_context_mod, "get_settings", _dti_settings)
    si = build_form_context(_dti_schema(), {}, "English",
                            section_number=1, total_sections=8, section_label="P1")
    # fields[0] (the client's selection) is rendered as CURRENT FIELD.
    assert "ID: p1_line1_aliennumber" in si


def test_merge_field_schema_extends_validation_set_without_mutating_schema():
    """Client-supplied next-field schemas are recorded for validation (so fields
    2..N are not 'unknown'), but kept SEPARATE from _schema['fields'] -- the DTI SI
    branch renders _schema['fields'][0] as the CURRENT field, so growing that list
    would make an SI rebuild describe a stale field (Codex PR #229). Validation set
    = _schema fields + recorded extras."""
    from backend.services.form_filling_service import FormFillingService
    from backend.config import get_settings
    svc = FormFillingService(live_ai=None, settings=get_settings())
    svc._schema = {"fields": [{"id": "f1", "name": "F1", "type": "text", "section_id": "s"}]}
    svc.merge_field_schema({"id": "f2", "name": "F2", "spoken_name": "field two",
                            "type": "text", "section_id": "s"})
    # _schema['fields'] is UNCHANGED (still just field 1 -- the SI's current field).
    assert [f["id"] for f in svc._schema["fields"]] == ["f1"]
    # But validation sees BOTH.
    validation_ids = {f.id for f in svc._build_fields_from_schema()}
    assert validation_ids == {"f1", "f2"}
    # Idempotent; no-op on empty/id-less.
    svc.merge_field_schema({"id": "f2", "name": "F2", "type": "text", "section_id": "s"})
    svc.merge_field_schema({})
    svc.merge_field_schema(None)
    assert {f.id for f in svc._build_fields_from_schema()} == {"f1", "f2"}


def test_jit_shaped_schema_renders_manifest_branch_when_flags_off(monkeypatch):
    """Rollback safety (Codex PR #229): a JIT-shaped schema (jit_mode=True, only
    first_field_schema in fields) must NOT hit the legacy full-dump branch when both
    USE_DTI and USE_JIT_SCHEMA are off -- that would describe one field and lose the
    section. It must render via the manifest-aware JIT branch."""
    from backend.config import get_settings as _gs

    class _Off:
        USE_DTI = False
        USE_JIT_SCHEMA = False
        SYSTEM_INSTRUCTION = _gs().SYSTEM_INSTRUCTION
        JIT_SYSTEM_INSTRUCTION = _gs().JIT_SYSTEM_INSTRUCTION
    monkeypatch.setattr(ai_context_mod, "get_settings", lambda: _Off())

    schema = _dti_schema()
    schema["jit_mode"] = True  # the marker websocket_routes sets on handshake_jit
    si = build_form_context(schema, {}, "English", section_number=1,
                            total_sections=8, section_label="P1")
    # Manifest branch -> the whole section is listed (FIELD MANIFEST present),
    # NOT a one-field legacy dump.
    assert "FIELD MANIFEST" in si
    assert "/3" in si  # progress over the real 3-field section, not "/1"


def test_coordinator_late_response_does_not_stash_stale_schema():
    """A LATE hint response (no matching pending request -> _resolve returns False)
    must NOT stash its schema, or it would leak into the next confirm's consume
    (bd jnjj.22 fresh-eyes race). No request was registered, so request_id is
    unknown -> nothing stashed."""
    coord = RequestCoordinator(websocket=None, session_id="t")
    coord.handle_next_field_hint_response("stale_unknown_id", "hint", NESTED_FIELD)
    assert coord.consume_pending_next_field_schema() is None
