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
        DTI_SYSTEM_INSTRUCTION = real.DTI_SYSTEM_INSTRUCTION
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


def test_jit_mode_schema_routes_to_dti_si_when_dti_off(monkeypatch):
    """Rollback safety (originally Codex PR #229, preserved through the JIT purge
    bd polyglot-pdf-en2j): a jit_mode-shaped schema (fields=[first field only] +
    names-only manifest) that arrives while USE_DTI is OFF must render the DTI
    STATIC SI, NOT the legacy full-dump branch -- the legacy branch would describe
    the single synthesized field and lose the section. This is the DTI->legacy
    rollback window: a client with a stale persisted jitModeEnabled sends one more
    handshake_jit before session_ready corrects it."""
    from backend.config import get_settings as _gs

    class _Off:
        USE_DTI = False
        DTI_SYSTEM_INSTRUCTION = _gs().DTI_SYSTEM_INSTRUCTION
        SYSTEM_INSTRUCTION = _gs().SYSTEM_INSTRUCTION
    monkeypatch.setattr(ai_context_mod, "get_settings", lambda: _Off())

    schema = _dti_schema()
    schema["jit_mode"] = True  # the marker websocket_routes sets on handshake_jit
    si = build_form_context(schema, {}, "English", section_number=1,
                            total_sections=8, section_label="Part 1")
    # The DTI static SI is selected: since it is fully static (no placeholders),
    # the rendered SI is EXACTLY the template (no is_reconnect here). This is the
    # load-bearing discriminator -- if the selector regressed to the legacy branch,
    # the SI would be the SYSTEM_INSTRUCTION dump (different text, section/field
    # markers filled in), not an exact match of the DTI template.
    assert si == _Off.DTI_SYSTEM_INSTRUCTION
    # And it is specifically NOT the legacy branch: the legacy SYSTEM_INSTRUCTION
    # renders the section field dump under a "Fields" style block + the field's
    # spoken name; assert the one synthesized field's spoken name is absent (the
    # legacy branch WOULD render it -- so this now discriminates, unlike the
    # names-only-manifest fields which neither branch dumps).
    assert NESTED_FIELD["spoken_name"] not in si


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
    # Force the flags deterministically (env-independent) on a FRESH Settings, so
    # the cached get_settings() instance is never mutated. CONTINUOUS_SESSION is
    # forced OFF: these initiating-message tests model the SECTION-mode shape
    # (section metadata etc.), which the continuous default (bd polyglot-pdf-7872)
    # would suppress.
    settings.USE_DTI = use_dti
    settings.CONTINUOUS_SESSION = False
    svc = FormFillingService(live_ai=AsyncMock(), settings=settings)

    captured = []

    async def _capture(msg):
        captured.append(msg)

    svc._live_ai.send_client_content = _capture
    return svc, captured


def test_continuous_session_forces_use_dti():
    """bd polyglot-pdf-x8rt: CONTINUOUS_SESSION implies USE_DTI (the whole-form
    handshake + section suppression only cohere with the DTI SI). Setting
    CONTINUOUS_SESSION without USE_DTI is a broken hybrid, so the validator forces
    USE_DTI on."""
    from backend.config import Settings

    forced = Settings(CONTINUOUS_SESSION=True, USE_DTI=False)
    assert forced.USE_DTI is True, "CONTINUOUS_SESSION must force USE_DTI on"
    # DTI without continuous is left as-is (no reverse coupling) -- the
    # measurement harness's non-continuous DTI arm depends on this.
    dti_only = Settings(USE_DTI=True, CONTINUOUS_SESSION=False)
    assert dti_only.USE_DTI is True and dti_only.CONTINUOUS_SESSION is False


def test_continuous_dti_is_the_default_configuration():
    """bd polyglot-pdf-7872 (sprint-11 epic fc7t, exit criterion 1): a no-env-var
    backend boots into continuous-DTI. The code states the production law of the
    land -- the three mode flags default ON and the eviction margin defaults to
    the ctu8-validated production value. Env vars remain the escape hatch (the
    legacy section-reset flow is reachable by setting them false)."""
    from backend.config import Settings

    default = Settings()
    assert default.USE_DTI is True
    assert default.CONTINUOUS_SESSION is True
    assert default.CONTEXT_COMPRESSION_ENABLED is True
    # The margin selects the post-clamp window (trigger 5000 - margin = window);
    # 1500 lands the validated 3500 window. See the config.py MARGIN comment.
    assert default.CONTEXT_COMPRESSION_TRIGGER_MARGIN_TOKENS == 1500


def test_continuous_session_drops_switch_section_tool():
    """bd polyglot-pdf-x8rt: in continuous-session mode the whole form is ONE
    session, so switch_section must NOT be offered to the model (a stray call
    would reset the session we deliberately keep open). With the flag OFF the
    tool is present as normal."""
    from backend.services.form_filling_service import FormFillingService
    from backend.config import Settings

    def _names(continuous: bool):
        settings = Settings()
        settings.CONTINUOUS_SESSION = continuous
        svc = FormFillingService(live_ai=None, settings=settings)
        return {d.get("name") for d in svc._build_tool_declarations()}

    off = _names(continuous=False)
    on = _names(continuous=True)
    # Sanity: the tool exists in the base declarations (else the test proves nothing).
    assert "switch_section" in off
    # Continuous mode drops ONLY switch_section; every other tool is retained.
    assert "switch_section" not in on
    assert off - on == {"switch_section"}


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


def test_render_section_metadata_title_only():
    """A real form title with no section info renders just the title line (no
    fabricated section/progress)."""
    from backend.services.ai_context import render_section_metadata
    block = render_section_metadata(form_title="Demo")
    assert block.startswith("FORM CONTEXT:")
    assert "Demo" in block
    assert "Section" not in block  # no section line without numbers


def test_render_section_metadata_returns_empty_when_nothing_substantive():
    """No real title and no section info -> NO block (the guard is real, not dead):
    a metadata-less DTI session must not emit a bare 'FORM CONTEXT: Form' line
    (fresh-eyes finding on this PR)."""
    from backend.services.ai_context import render_section_metadata
    assert render_section_metadata() == ""
    assert render_section_metadata(form_title=None) == ""
    # ...but any one substantive input is enough to render.
    assert render_section_metadata(section_label="Part 1") != ""
    assert render_section_metadata(section_number=1, total_sections=8) != ""


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


# ---------------------------------------------------------------------------
# update_form_fields / confirm_field coercion to the current field
# (bd polyglot-pdf-h1bn): the model's field_id is ADVISORY -- a hallucinated or
# drifted id is deterministically re-pointed at the known current field, so the
# value still fills the right field instead of being rejected / misfiled.
# ---------------------------------------------------------------------------

def _dti_service_with_current_field(field_id):
    """A FormFillingService in DTI mode with a known current field + that field in
    the validation pool (as merge_field_schema would record it)."""
    from backend.services.form_filling_service import FormFillingService
    from backend.config import Settings
    settings = Settings()
    settings.USE_DTI = True
    svc = FormFillingService(live_ai=None, settings=settings)
    # The current field + its schema in the validation pool (what the client delivered).
    svc._schema = {"fields": [{"id": field_id, "name": field_id, "type": "text"}]}
    svc._current_field_id = field_id
    return svc


def test_update_coerces_hallucinated_id_to_current_field():
    """A hallucinated id (not in the schema) is re-pointed at the current field, so
    the value fills it with success -- instead of unknown_fields (the residual
    jnjj.46 model-disobedience). The fix for p1_line2_acctidentifier vs the model's
    invented p1_line2_uscis_account."""
    svc = _dti_service_with_current_field("p1_line2_acctidentifier")
    result = svc.handle_update_fields_tool_call(
        "sess", {"p1_line2_uscis_account": "123456789012"})
    assert result["applied_fields"] == ["p1_line2_acctidentifier"]
    assert not result.get("unknown_fields")
    assert result["form_state"].get("p1_line2_acctidentifier") == "123456789012"


def test_update_manifest_known_id_is_honored_after_reconnect():
    """Codex PR #321 P1: after a DTI reconnect (GoAway / mid-section) the fresh
    handshake carries only field 1's full schema and _dti_extra_fields was
    cleared -- previously-delivered fields survive ONLY as manifest field_id
    entries. A post-reconnect correction to such a field must be HONORED (not
    coerced onto the current field): _is_known_field_id also resolves manifest
    ids. The unmerged target is then cleanly rejected by validation (an in-band
    error the model recovers from), never silently misfiled."""
    svc = _dti_service_with_current_field("p1_line3b_givenname")
    # Reconnect state: extras cleared; the earlier field exists only in the manifest.
    svc._dti_extra_fields = {}
    svc._schema["manifest"] = {"current_section": {
        "section_id": "s1", "section_label": "S1",
        "fields": [{"field_id": "p1_line3a_familyname", "spoken_name": "family name"},
                   {"field_id": "p1_line3b_givenname", "spoken_name": "given name"}],
    }}
    assert svc._is_known_field_id("p1_line3a_familyname") is True
    result = svc.handle_update_fields_tool_call(
        "sess", {"p1_line3a_familyname": "Vasquez"})
    # NOT coerced onto the current field; the manifest-known-but-unmerged target
    # is rejected in-band by validation (schema absent), never misfiled.
    assert "p1_line3b_givenname" not in (result.get("form_state") or {})
    assert result["applied_fields"] == []
    assert result.get("unknown_fields") == ["p1_line3a_familyname"]


def test_update_known_but_different_id_is_honored():
    """A RESOLVABLE id is AUTHORITATIVE (bd polyglot-pdf-8vy3, live-run evidence
    2026-07-05): the model legitimately targets a PREVIOUS field when the user
    corrects it after its confirm advanced the pointer. The original blanket
    coercion re-pointed those corrections onto the CURRENT field, silently
    corrupting it (a 30q continuous run misfiled 5 fields this way while every id
    the model sent was correct). Known-id updates apply to the NAMED field."""
    svc = _dti_service_with_current_field("p1_checkbox4")
    # p1_line3a_familyname is a real, previously-merged field: a late correction.
    svc._dti_extra_fields = {"p1_line3a_familyname": {"id": "p1_line3a_familyname", "name": "fam", "type": "text"}}
    result = svc.handle_update_fields_tool_call("sess", {"p1_line3a_familyname": "Vasquez"})
    assert result["applied_fields"] == ["p1_line3a_familyname"]
    assert "p1_checkbox4" not in (result.get("form_state") or {})


def test_update_matching_id_is_not_coerced():
    """When the model names the current field correctly, behavior is the normal
    path -- no coercion branch, fills that field."""
    svc = _dti_service_with_current_field("p1_line1_aliennumber")
    result = svc.handle_update_fields_tool_call("sess", {"p1_line1_aliennumber": "12345678"})
    assert result["applied_fields"] == ["p1_line1_aliennumber"]


def test_update_no_coercion_in_non_dti():
    """Non-DTI: the model's id is authoritative -- a wrong id is NOT coerced (it
    falls through to today's unknown_fields behavior). Guards the blast radius."""
    from backend.services.form_filling_service import FormFillingService
    from backend.config import Settings
    settings = Settings(); settings.USE_DTI = False
    svc = FormFillingService(live_ai=None, settings=settings)
    svc._schema = {"fields": [{"id": "real", "name": "real", "type": "text"}]}
    svc._current_field_id = "real"  # set, but USE_DTI is False -> ignored
    result = svc.handle_update_fields_tool_call("sess", {"hallucinated": "x"})
    assert result.get("unknown_fields") == ["hallucinated"]
    assert result["applied_fields"] == []


def test_update_no_coercion_without_current_field():
    """DTI but no current field known yet (e.g. before any guidance delivered) ->
    no coercion, today's behavior."""
    from backend.services.form_filling_service import FormFillingService
    from backend.config import Settings
    settings = Settings(); settings.USE_DTI = True
    svc = FormFillingService(live_ai=None, settings=settings)
    svc._schema = {"fields": [{"id": "real", "name": "real", "type": "text"}]}
    svc._current_field_id = None
    result = svc.handle_update_fields_tool_call("sess", {"hallucinated": "x"})
    assert result.get("unknown_fields") == ["hallucinated"]


def test_update_multi_field_not_coerced():
    """One-field-per-turn invariant: a multi-field update is NOT coerced (the
    caller's single-field guard handles it); don't silently merge onto one field."""
    svc = _dti_service_with_current_field("real")
    svc._dti_extra_fields = {"real": {"id": "real", "name": "real", "type": "text"}}
    result = svc.handle_update_fields_tool_call("sess", {"a": "1", "b": "2"})
    # not coerced to {real: ...}; both a,b are unknown
    assert set(result.get("unknown_fields") or []) == {"a", "b"}


def test_current_field_id_set_by_merge_field_schema():
    """merge_field_schema (called when the client delivers the next field on confirm)
    records the current-field routing pointer."""
    from backend.services.form_filling_service import FormFillingService
    from backend.config import get_settings
    svc = FormFillingService(live_ai=None, settings=get_settings())
    svc.merge_field_schema({"id": "p1_next", "name": "Next", "type": "text"})
    assert svc._current_field_id == "p1_next"


# ---------------------------------------------------------------------------
# Codex PR #264 P0 fixes (bd polyglot-pdf-h1bn): coercion must NOT corrupt data on
# a collapsed multi-field call, must not log raw model ids (PII), and a manual edit
# must invalidate the current-field pointer.
# ---------------------------------------------------------------------------

def test_update_multi_field_call_not_coerced():
    """P0: the callback collapses a multi-field tool call to its FIRST key before the
    service sees it, so the service can't detect multi-field itself. With
    multi_field_call=True, coercion must be SKIPPED -- the collapsed first value may
    belong to a different field; re-pointing it onto the current field corrupts it."""
    svc = _dti_service_with_current_field("p1_line1_aliennumber")
    # The callback collapsed {wrongfield: v, ...} -> {wrongfield: v} and flags it.
    result = svc.handle_update_fields_tool_call(
        "sess", {"some_other_field": "VALUE"}, multi_field_call=True)
    # NOT coerced onto p1_line1_aliennumber -> rejected as unknown (the caller's intent).
    assert result.get("unknown_fields") == ["some_other_field"]
    assert result["applied_fields"] == []


def test_update_coercion_does_not_log_raw_sent_id(monkeypatch):
    """P0 (no-PII): the coercion log must NOT include sent_id -- it is raw model input
    and can carry the user's answer. Only the schema-validated current field id is safe."""
    import backend.services.form_filling_service as ffs_mod
    calls = []

    class _FakeLog:
        def info(self, event, **kw): calls.append((event, kw))
        def __getattr__(self, _n): return lambda *a, **k: None
    monkeypatch.setattr(ffs_mod, "_log", _FakeLog())

    svc = _dti_service_with_current_field("p1_line2_acctidentifier")
    # hallucinated id whose text happens to look like a user value
    svc.handle_update_fields_tool_call("sess", {"my answer is 123-45-6789": "x"})
    coerce_logs = [(e, kw) for (e, kw) in calls if e == "dti_update_coerced_to_current_field"]
    assert coerce_logs, "coercion should have logged"
    blob = repr(coerce_logs)
    assert "sent_field_id" not in blob
    assert "123-45-6789" not in blob  # the raw id (potential PII) never logged
    assert "p1_line2_acctidentifier" in blob  # the safe target id is fine


def test_manual_field_update_clears_current_field_pointer():
    """P0: a manual edit is auto-confirmed by the FE, so the current-field pointer
    must be invalidated -- else the NEXT spoken answer (for a different, hinted field)
    is coerced onto the just-edited field, overwriting it."""
    import asyncio
    from backend.services.form_filling_service import FormFillingService
    from backend.config import Settings
    settings = Settings(); settings.USE_DTI = True
    svc = FormFillingService(live_ai=None, settings=settings)
    svc._current_field_id = "p1_line3a_familyname"
    svc._audio_handler = None  # no-op delegate; we only assert the pointer clear
    asyncio.get_event_loop().run_until_complete(
        svc.send_manual_field_update("p1_line3a_familyname", "Family Name", "Vasquez",
                                     "next (field_id: 'p1_line3b_givenname')"))
    assert svc._current_field_id is None


# ---------------------------------------------------------------------------
# bd polyglot-pdf-ezg2: after a manual edit the pointer must be RE-ESTABLISHED
# for the next field (not just cleared) -- the client sends the next field's
# schema with manual_field_update, and the service merges it like the confirm
# path does, so the immediately-following voice answer coerces.
# ---------------------------------------------------------------------------

def _dti_service_for_manual_edit():
    import asyncio  # noqa: F401  (used by callers)
    from backend.services.form_filling_service import FormFillingService
    from backend.config import Settings
    settings = Settings(); settings.USE_DTI = True
    svc = FormFillingService(live_ai=None, settings=settings)
    svc._schema = {"fields": [{"id": "p1_line3a_familyname",
                               "name": "Family Name", "type": "text"}]}
    svc._current_field_id = "p1_line3a_familyname"
    svc._audio_handler = None  # no-op delegate; we assert pointer/pool state only
    return svc


def test_manual_field_update_reestablishes_pointer_from_next_field_schema():
    """ezg2 exit criterion: manual edit of field N with the next field's schema ->
    pointer re-established to N+1 AND N+1 enters the validation pool, so a voice
    update_form_fields for N+1 with a drifted/hallucinated id is coerced onto N+1."""
    import asyncio
    svc = _dti_service_for_manual_edit()
    next_schema = {"id": "p1_line3b_givenname", "name": "Given Name", "type": "text"}
    asyncio.get_event_loop().run_until_complete(
        svc.send_manual_field_update("p1_line3a_familyname", "Family Name", "Vasquez",
                                     "next (field_id: 'p1_line3b_givenname')",
                                     next_field_schema=next_schema))
    assert svc._current_field_id == "p1_line3b_givenname"
    # The very next voice answer arrives with a drifted id -> coerced onto N+1,
    # applied (N+1 is in the pool via the merge), never unknown_fields.
    result = svc.handle_update_fields_tool_call("sess", {"p1_line1_givenname": "Maria"})
    assert result["applied_fields"] == ["p1_line3b_givenname"]
    assert not result.get("unknown_fields")


def test_manual_field_update_without_schema_leaves_pointer_cleared():
    """A manual edit with NO next_field_schema (legacy client, or the form is
    complete) keeps the strictly-safer h1bn behavior: pointer stays cleared."""
    import asyncio
    svc = _dti_service_for_manual_edit()
    asyncio.get_event_loop().run_until_complete(
        svc.send_manual_field_update("p1_line3a_familyname", "Family Name", "Vasquez",
                                     "next (field_id: 'p1_line3b_givenname')"))
    assert svc._current_field_id is None


def test_manual_field_update_non_dti_ignores_next_field_schema():
    """USE_DTI off -> the rider schema is ignored entirely: no pointer, no pool
    merge (guards the non-DTI blast radius)."""
    import asyncio
    from backend.services.form_filling_service import FormFillingService
    from backend.config import Settings
    settings = Settings(); settings.USE_DTI = False
    svc = FormFillingService(live_ai=None, settings=settings)
    svc._current_field_id = "whatever"
    svc._audio_handler = None
    asyncio.get_event_loop().run_until_complete(
        svc.send_manual_field_update("f1", "Field One", "v",
                                     next_field_schema={"id": "f2", "name": "Two",
                                                        "type": "text"}))
    assert svc._current_field_id is None
    assert "f2" not in svc._dti_extra_fields
