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

from unittest.mock import AsyncMock

import pytest

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


def test_dti_si_is_static_carries_no_field_guidance(monkeypatch):
    """Static-SI epic (polyglot-pdf-1ac3/13w7): the DTI SI is fully static and
    carries NO field guidance. Field 1's guidance (its exact id, instructions,
    etc.) reaches the model via the dynamic injection, not the SI -- so the SI
    must NOT contain any field's id or instructions, and must NOT be a whole-form
    dump or a names-only manifest block."""
    monkeypatch.setattr(ai_context_mod, "get_settings", _dti_settings)
    si = build_form_context(_dti_schema(), {}, "English",
                            section_number=1, total_sections=8, section_label="Part 1")
    # No field guidance in the SI -- not field 1's id, not its instructions.
    assert "p1_line1_aliennumber" not in si
    assert "ID:" not in si
    assert "Instructions: Your A-Number" not in si
    # ...and not a whole-form dump or a names-only manifest block either.
    assert "FIELD MANIFEST" not in si


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


def test_dti_extra_fields_reset_on_section_switch():
    """_dti_extra_fields (the DTI validation extras) must reset when start_session
    runs for a new section, or previous-section field schemas linger and the
    validator wrongly accepts stale cross-section field ids (fresh-eyes substitute,
    Codex PR #229)."""
    from backend.services.form_filling_service import FormFillingService
    from backend.config import get_settings
    svc = FormFillingService(live_ai=None, settings=get_settings())
    svc._schema = {"fields": [{"id": "sec1_f1", "name": "F1", "type": "text", "section_id": "s1"}]}
    svc.merge_field_schema({"id": "sec1_f2", "name": "F2", "type": "text", "section_id": "s1"})
    assert "sec1_f2" in svc._dti_extra_fields
    # Simulate the reset start_session does at section switch (the line under test).
    svc._dti_extra_fields = {}
    assert svc._dti_extra_fields == {}
    # After reset, validation only sees the new section's schema, not sec1_f2.
    svc._schema = {"fields": [{"id": "sec2_f1", "name": "G1", "type": "text", "section_id": "s2"}]}
    ids = {f.id for f in svc._build_fields_from_schema()}
    assert ids == {"sec2_f1"}
    assert "sec1_f2" not in ids


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


def test_dti_si_is_fully_static_zero_placeholders(monkeypatch):
    """Static-SI epic (polyglot-pdf-1ac3/13w7) exit criteria 1 + 2: the DTI SI is
    a fully static constant -- zero '{' placeholders -- and it instructs the model
    to copy the current field_id VERBATIM from the latest injected guidance and
    NEVER invent it. The rendered SI is identical regardless of the schema (no
    interpolated form/section/field state)."""
    monkeypatch.setattr(ai_context_mod, "get_settings", _dti_settings)
    si = build_form_context(_dti_schema(), {}, "English",
                            section_number=1, total_sections=8, section_label="P1")
    # Criterion 1: no leftover placeholders survive into the rendered SI.
    assert "{" not in si and "}" not in si
    # The static constant itself carries zero placeholders.
    from backend.config import get_settings
    assert "{" not in get_settings().DTI_SYSTEM_INSTRUCTION
    # Criterion 2: the SI tells the model to copy the id verbatim and never invent.
    assert "verbatim" in si.lower()
    assert "never invent" in si.lower() or "never invent, reconstruct" in si.lower()


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


# ---------------------------------------------------------------------------
# Field-1 guidance via the initiating message (bd polyglot-pdf-j748, epic 13w7).
# The static DTI SI carries no field data; field 1's exact id + guidance must
# ride the INITIATING MESSAGE instead.
# ---------------------------------------------------------------------------

def _service_with_settings(use_dti: bool):
    """A FormFillingService with a capturing live_ai stub and a Settings whose
    USE_DTI is forced to `use_dti`, using the REAL initiating-message templates."""
    from backend.services.form_filling_service import FormFillingService
    from backend.config import Settings

    settings = Settings()
    # Force the flag deterministically (env-independent) on a FRESH Settings, so
    # the cached get_settings() instance is never mutated.
    settings.USE_DTI = use_dti
    svc = FormFillingService(live_ai=AsyncMock(), settings=settings)

    captured = []

    async def _capture(msg):
        captured.append(msg)

    svc._live_ai.send_client_content = _capture
    return svc, captured


@pytest.mark.asyncio
async def test_initiating_message_carries_field1_guidance_in_dti():
    """Exit criterion 1: in DTI mode the initiating message carries field 1's
    EXACT field_id + guidance (so the model copies the id verbatim instead of
    reconstructing it from the SI, which no longer holds field data)."""
    svc, captured = _service_with_settings(use_dti=True)
    svc._is_resume_session = False
    svc._schema = {"fields": [NESTED_FIELD]}

    # The real spoken hint embeds the field_id as a quoted parenthetical (the
    # format strip_field_id_from_hint matches, bd dx7).
    await svc.send_initiating_message(
        "Spanish", "alien registration number (field_id: 'p1_line1_aliennumber')"
    )

    assert len(captured) == 1
    msg = captured[0]
    # The exact field_id + guidance is in the injection (the whole point).
    assert "p1_line1_aliennumber" in msg
    assert "ID: p1_line1_aliennumber" in msg
    assert "Instructions: Your A-Number" in msg
    # Single-source identity: the embedded block IS render_field_guidance's output.
    assert render_field_guidance(NESTED_FIELD) in msg
    # The SPOKEN directive still strips the raw "(field_id: ...)" parenthetical so
    # Gemini does not read the id aloud (bd dx7); only the guidance block carries it.
    assert "(field_id:" not in msg
    # Fresh connect still greets.
    assert "greet" in msg.lower()


@pytest.mark.asyncio
async def test_initiating_message_no_guidance_in_non_dti():
    """Legacy/JIT modes keep the SI's field catalog, so the initiating message must
    NOT carry a guidance block -- output is unchanged from before j748."""
    svc, captured = _service_with_settings(use_dti=False)
    svc._is_resume_session = False
    svc._schema = {"fields": [NESTED_FIELD]}

    await svc.send_initiating_message("English", "First Name")

    assert len(captured) == 1
    msg = captured[0]
    assert "p1_line1_aliennumber" not in msg
    assert "ID:" not in msg
    assert "greet" in msg.lower()  # still the normal greeting template


@pytest.mark.asyncio
async def test_resume_initiating_message_carries_field1_guidance():
    """Reconnect/resume: the RESUME template (no greeting) must STILL carry the
    current field's guidance so a mid-section reconnect re-anchors Gemini to the
    field_id the static SI no longer supplies."""
    svc, captured = _service_with_settings(use_dti=True)
    svc._is_resume_session = True
    svc._schema = {"fields": [NESTED_FIELD]}

    await svc.send_initiating_message(
        "English", "alien registration number (field_id: 'p1_line1_aliennumber')"
    )

    msg = captured[0]
    # Resume template -> no greeting...
    assert "greet user warmly" not in msg.lower()
    # ...but the current field's guidance is present.
    assert "ID: p1_line1_aliennumber" in msg


@pytest.mark.asyncio
async def test_initiating_message_resolves_field_from_hint_not_position():
    """The rendered field is the one the HINT points at, NOT schema['fields'][0].
    This is the Codex PR #254 fix: on a mid-form spoken-language change the current
    field is field N (held in _dti_extra_fields), while schema['fields'][0] is the
    stale handshake field 1; rendering fields[0] would inject the WRONG field_id and
    the static SI tells the model to copy that stale id. Would FAIL against the old
    fields[0] code; PASSES against hint-id resolution."""
    svc, captured = _service_with_settings(use_dti=True)
    svc._is_resume_session = False
    # Handshake field 1 (positional fields[0]) is a DIFFERENT field than the hint...
    other = {"id": "p1_line3a_familyname", "spoken_name": "family name", "type": "text"}
    svc._schema = {"fields": [other]}
    # ...and the hint's field lives in the recorded later-field schemas.
    svc._dti_extra_fields = {"p1_line1_aliennumber": NESTED_FIELD}

    await svc.send_initiating_message(
        "English", "alien registration number (field_id: 'p1_line1_aliennumber')"
    )

    msg = captured[0]
    # Renders the HINT's field, not the positional first field.
    assert "ID: p1_line1_aliennumber" in msg
    assert "p1_line3a_familyname" not in msg


@pytest.mark.asyncio
async def test_initiating_message_unresolvable_hint_renders_no_guidance():
    """If the hint's field_id resolves to no known schema (or there is no id in the
    hint), render NO guidance block -- never a wrong/stale field, never the
    'No fields available' sentinel. The spoken hint + static SI still let Gemini
    proceed for that one turn (it just lacks the verbatim id)."""
    svc, captured = _service_with_settings(use_dti=True)
    svc._is_resume_session = False
    svc._schema = {"fields": [NESTED_FIELD]}

    # (a) hint id that matches nothing known
    await svc.send_initiating_message(
        "English", "some field (field_id: 'nonexistent_id')"
    )
    # (b) hint with no field_id parenthetical at all
    await svc.send_initiating_message("English", "the first unfilled field")

    for msg in captured:
        assert "ID:" not in msg
        assert "No fields available" not in msg


@pytest.mark.asyncio
async def test_initiating_message_logs_only_length(monkeypatch):
    """No-PII guard (bd uov.15): the rendered message embeds field data, so the log
    must record only message_length -- never the field_id, instructions, or guidance
    text. Captures the ACTUAL log-call kwargs by monkeypatching the module logger's
    info(), which is deterministic and ordering-independent (NOT pytest caplog --
    _log is a structlog logger not routed through stdlib in tests; NOT capture_logs
    -- the module-level lazy logger is already realized against the suite's structlog
    config, so global-config swaps do not reliably intercept it. fresh-eyes finding
    on this PR, then a full-suite ordering failure on capture_logs)."""
    import backend.services.form_filling_service as ffs_mod

    calls = []

    class _FakeLog:
        def info(self, event, **kwargs):
            calls.append((event, kwargs))

        # send_initiating_message only calls .info; stub the rest as no-ops so an
        # unrelated log call cannot AttributeError the test.
        def __getattr__(self, _name):
            return lambda *a, **k: None

    monkeypatch.setattr(ffs_mod, "_log", _FakeLog())

    svc, captured = _service_with_settings(use_dti=True)
    svc._is_resume_session = False
    svc._schema = {"fields": [NESTED_FIELD]}

    # Hint carries the id so the guidance block IS rendered (the case that embeds
    # field data into the message -- exactly what must NOT reach the log).
    await svc.send_initiating_message(
        "English", "alien registration number (field_id: 'p1_line1_aliennumber')"
    )

    send_calls = [(e, kw) for (e, kw) in calls if e == "send_initiating_message"]
    assert send_calls, "send_initiating_message was not logged"
    event, kwargs = send_calls[0]
    # message_length is the only size signal logged...
    assert "message_length" in kwargs
    # ...and NO logged kwarg (key or value) carries the field_id or instructions.
    blob = repr((event, kwargs))
    assert "p1_line1_aliennumber" not in blob
    assert "Your A-Number" not in blob


# ---------------------------------------------------------------------------
# Remaining values to injection (bd polyglot-pdf-uogm): fill_language rides every
# field render; form/section metadata rides the initiating message; the SI stays
# fully static (zero per-form value).
# ---------------------------------------------------------------------------

def test_render_field_guidance_appends_fill_language():
    """fill_language rides the field render when set; omitted -> byte-identical to
    the no-arg render (so non-DTI / legacy callers are unaffected)."""
    text = render_field_guidance(NESTED_FIELD, fill_language="Spanish")
    assert "Fill language: Spanish" in text
    assert "Fill language" not in render_field_guidance(NESTED_FIELD)
    assert render_field_guidance(NESTED_FIELD, fill_language=None) == render_field_guidance(NESTED_FIELD)


def test_render_section_metadata_block():
    from backend.services.ai_context import render_section_metadata
    block = render_section_metadata(
        form_title="I-90", section_number=2, total_sections=8,
        section_label="Part 2", previous_spoken_names=["first name", "last name"],
    )
    assert "I-90" in block
    assert "Section 2 of 8" in block
    assert "Part 2" in block
    assert "first name" in block
    # confirmation policy is derived from section_number/total when not passed
    assert "confirmation" in block.lower()


def test_render_section_metadata_empty_inputs_minimal():
    """A single-section form with no metadata still renders cleanly (just the title),
    never crashes, never emits empty section/progress lines."""
    from backend.services.ai_context import render_section_metadata
    block = render_section_metadata(form_title="Demo")
    assert block.startswith("FORM CONTEXT:")
    assert "Demo" in block
    assert "Section" not in block  # no section line without numbers


@pytest.mark.asyncio
async def test_initiating_message_field1_carries_fill_language():
    """The field-1 guidance in the DTI initiating message carries the fill language
    so the model writes VALUES in the configured (non-spoken) language."""
    svc, captured = _service_with_settings(use_dti=True)
    svc._is_resume_session = False
    svc._fill_language = "Spanish"
    svc._schema = {"fields": [NESTED_FIELD]}
    await svc.send_initiating_message(
        "English", "alien registration number (field_id: 'p1_line1_aliennumber')"
    )
    assert "Fill language: Spanish" in captured[0]


@pytest.mark.asyncio
async def test_initiating_message_metadata_from_section_metadata_not_manifest():
    """bd fu1h F1 regression guard: the metadata block is built from
    _last_section_metadata (what the switch path carries), NOT schema["manifest"].
    Here the schema has NO manifest (section-switch shape) yet the block is fully
    populated -- this would render empty if it sourced from the manifest."""
    svc, captured = _service_with_settings(use_dti=True)
    svc._is_resume_session = False
    svc._schema = {"form_metadata": {"title": "I-90"}, "fields": [NESTED_FIELD]}
    svc._last_section_metadata = {
        "section_number": 3, "total_sections": 8, "section_label": "Part 3",
        "previous_spoken_names": ["alien registration number"],
    }
    await svc.send_initiating_message(
        "English", "alien registration number (field_id: 'p1_line1_aliennumber')"
    )
    msg = captured[0]
    assert "FORM CONTEXT:" in msg
    assert "I-90" in msg
    assert "Section 3 of 8" in msg
    assert "Part 3" in msg


@pytest.mark.asyncio
async def test_initiating_message_no_metadata_block_in_non_dti():
    """Non-DTI: no metadata block, no fill_language segment -- byte-identical to
    pre-uogm legacy/JIT output."""
    svc, captured = _service_with_settings(use_dti=False)
    svc._is_resume_session = False
    svc._fill_language = "Spanish"
    svc._schema = {"form_metadata": {"title": "I-90"}, "fields": [NESTED_FIELD]}
    svc._last_section_metadata = {"section_number": 3, "total_sections": 8}
    await svc.send_initiating_message("English", "First Name")
    msg = captured[0]
    assert "FORM CONTEXT:" not in msg
    assert "Fill language" not in msg


def test_dti_si_byte_identical_across_forms(monkeypatch):
    """Exit criterion 2: the DTI SI is byte-identical across two different
    forms/sections -- it carries zero per-form value (all of it moved to injection)."""
    monkeypatch.setattr(ai_context_mod, "get_settings", _dti_settings)

    def si_for(title, field, lang, sec, total, label):
        schema = {
            "form_metadata": {"title": title},
            "fields": [field],
            "manifest": {"current_section": {"section_id": "s", "section_label": label,
                                             "fields": [{"field_id": field["id"],
                                                         "spoken_name": field.get("spoken_name", "x")}]},
                         "previous_sections": []},
        }
        return build_form_context(schema, {}, lang, section_number=sec,
                                  total_sections=total, section_label=label)

    a = si_for("Form A", NESTED_FIELD, "English", 1, 8, "Part 1")
    b = si_for("Form B", FLAT_FIELD, "French", 4, 12, "Part 4")
    assert a == b, "DTI SI must carry no per-form value"
    assert "{" not in a  # criterion 1 holds
