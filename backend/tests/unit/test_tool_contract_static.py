"""Spec: the DECLARED tool contract matches what the dispatcher handles
(bd polyglot-pdf-uov.14, T3.3).

config.py `TOOL_DECLARATIONS` is the schema handed to Gemini -- the names, params,
and required fields the model is told it may call. `CallbackHandler.on_tool_call`
is the backend dispatcher that routes a tool call to a handler. If these two drift
-- a declared tool with no dispatch branch, or a handler reading an arg the
declaration never promises -- the model emits a call the backend silently drops
(the unknown-tool branch returns {}), which in the demo looks like the assistant
"forgetting" to fill/confirm a field. This module pins that contract.

It is a PURE, in-process unit spec (no live Gemini): it reads the static
declarations and drives `on_tool_call` with mocked tool handlers, so it runs under
the default `pytest -m "not external"`. It is the STATIC counterpart to
backend/tests/contract/test_tool_contracts.py, which A/Bs the live model's tool-call
SEQUENCE (ordering) and is @pytest.mark.external -- the two do not overlap: that
file asserts the model's runtime behavior, this one asserts the
declaration<->dispatcher wiring.

PII: tool args carry field values, but this spec uses synthetic placeholder args
and never logs them.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.config import Settings
from backend.services.callback_handler import CallbackHandler


# The tools the backend declares to Gemini. Kept as a literal here so a rename
# or removal in config.py that this contract does not expect shows up as a diff
# in BOTH places (the test is the second witness).
EXPECTED_TOOL_NAMES = {
    "update_form_fields",
    "get_form_status",
    "switch_section",
    "confirm_field",
    "ask_secretary",
    "skip_field",
    "switch_to_field",
}

# A representative valid argument set per declared tool -- the REQUIRED params from
# each declaration, with synthetic values. Used to drive on_tool_call so each
# declared tool reaches its handler (not the unknown-tool {} fallthrough).
SAMPLE_ARGS = {
    "update_form_fields": {"field_id": "p1_first_name", "value": "Jane"},
    "get_form_status": {"field_ids": ["p1_first_name"]},
    "switch_section": {"section_identifier": "2"},
    "confirm_field": {"field_id": "p1_first_name", "confirmation_method": "verbal"},
    "ask_secretary": {"query": "what is their first name?"},
    "skip_field": {"field_id": "p1_first_name"},
    "switch_to_field": {"field": "p1_first_name"},
}


def _declarations() -> list[dict]:
    return Settings().TOOL_DECLARATIONS


def _decl_by_name() -> dict[str, dict]:
    return {d["name"]: d for d in _declarations()}


# --------------------------------------------------------------------------
# Part A -- the declarations are internally well-formed
# --------------------------------------------------------------------------
def test_declared_tool_names_match_expected_set():
    """The declared tool names are exactly the set the backend supports -- a tool
    added/removed in config.py without updating this contract fails here."""
    names = {d["name"] for d in _declarations()}
    assert names == EXPECTED_TOOL_NAMES


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOL_NAMES))
def test_each_declaration_is_well_formed(name):
    """Every declaration has an object param schema whose `required` entries all
    exist in `properties` and carry a concrete JSON-schema type."""
    decl = _decl_by_name()[name]
    params = decl["parameters"]
    assert params["type"] == "object"

    properties = params["properties"]
    required = params["required"]
    assert required, f"{name}: declares no required params"

    for req in required:
        assert req in properties, f"{name}: required '{req}' missing from properties"
        assert "type" in properties[req], f"{name}: required '{req}' has no type"


def test_confirm_field_method_enum_is_verbal_or_manual():
    """confirm_field.confirmation_method is an enum of exactly verbal/manual --
    the values _handle_confirm_field_tool branches on. A new enum member added to
    the declaration without a handler branch would silently behave like 'verbal'."""
    decl = _decl_by_name()["confirm_field"]
    method = decl["parameters"]["properties"]["confirmation_method"]
    assert set(method["enum"]) == {"verbal", "manual"}


# --------------------------------------------------------------------------
# Part B -- declarations <-> dispatcher wiring (the core invariant)
# --------------------------------------------------------------------------
def _make_handler() -> CallbackHandler:
    """A CallbackHandler with every injected tool handler mocked, so on_tool_call
    can route a call without a live service/Gemini. The handlers return trivial
    dicts; we assert on WHICH handler fired, not on its payload."""
    coordinator = MagicMock()
    # The async requests the confirm path awaits: request_confirm_field records the
    # confirmation, then (on success) request_next_field_hint fetches the next hint.
    coordinator.request_confirm_field = AsyncMock(return_value={"recorded": True})
    coordinator.request_next_field_hint = AsyncMock(return_value=None)
    # skip_field path (bd polyglot-pdf-7yra): request_skip_field records the skip,
    # then the shared advance logic fetches the next hint.
    coordinator.request_skip_field = AsyncMock(return_value={"recorded": True})
    # switch_to_field path (bd polyglot-pdf-jnjj.36): request_switch_field pins
    # the target on the client and acks with its hint.
    coordinator.request_switch_field = AsyncMock(return_value={
        "found": True, "field_id": "p1_first_name",
        "spoken_name": "first name", "next_field_hint": "hint"})
    handler = CallbackHandler(
        websocket=MagicMock(),
        session_id="test_session",
        request_coordinator=coordinator,
    )
    handler.set_tool_handlers(
        handle_update_fields=MagicMock(return_value={
            "applied_fields": ["p1_first_name"],
            "validation_errors": [],
            "unknown_fields": [],
            "form_state": {},
        }),
        handle_switch_section=AsyncMock(return_value={"success": True}),
        request_form_state_from_client=AsyncMock(return_value={}),
        handle_ask_secretary=AsyncMock(return_value="a prose answer"),
    )
    # send_form_update touches the websocket; stub it so update routing is isolated.
    handler.send_form_update = AsyncMock()
    return handler


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(EXPECTED_TOOL_NAMES))
async def test_every_declared_tool_is_dispatched_not_dropped(name):
    """Each DECLARED tool name routes to a real handler -- it must NOT fall through
    to the unknown-tool branch (which returns {} and silently drops the call). We
    detect "dispatched" by the handler returning a non-None, and for the tools that
    delegate to an injected service method, that the method actually fired."""
    handler = _make_handler()

    result = await handler.on_tool_call(name, SAMPLE_ARGS[name])

    assert result is not None, f"{name}: dispatcher returned None"

    # The tools that delegate to an injected service method must have called it --
    # proving the route reached the real handler, not a coincidental {} echo.
    if name == "update_form_fields":
        handler._handle_update_fields.assert_called_once()
    elif name == "switch_section":
        handler._handle_switch_section.assert_awaited_once()
    elif name == "get_form_status":
        handler._request_form_state_from_client.assert_awaited_once()
    elif name == "confirm_field":
        handler._request_coordinator.request_confirm_field.assert_awaited_once()
    elif name == "skip_field":
        handler._request_coordinator.request_skip_field.assert_awaited_once()
    elif name == "switch_to_field":
        handler._request_coordinator.request_switch_field.assert_awaited_once()
    elif name == "ask_secretary":
        handler._handle_ask_secretary.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatcher_reads_the_declared_required_args():
    """The dispatcher reads each tool's DECLARED required arg, not some other key.
    Asserted by checking the injected handler received the value we passed under
    the declared arg name (so a handler that read the wrong key would fail)."""
    handler = _make_handler()

    # update_form_fields reads BOTH declared required args (field_id, value) and
    # hands the service {field_id: value}. Asserting the exact dict catches a
    # rename of either key in _parse_update_arguments (e.g. field_id -> field_name
    # would yield {} and fail this) -- this is the highest-traffic tool, so its
    # arg-reading must be pinned too (fresh-eyes).
    await handler.on_tool_call(
        "update_form_fields", {"field_id": "p1_first_name", "value": "Jane"}
    )
    # multi_field_call=False is passed so the service can skip DTI coercion on a
    # COLLAPSED multi-field call (a single-field call is not collapsed -- bd
    # polyglot-pdf-h1bn / Codex PR #264).
    handler._handle_update_fields.assert_called_once_with(
        handler._session_id, {"p1_first_name": "Jane"}, multi_field_call=False
    )

    await handler.on_tool_call("switch_section", {"section_identifier": "3"})
    handler._handle_switch_section.assert_awaited_once_with("3")

    await handler.on_tool_call("get_form_status", {"field_ids": ["a", "b"]})
    handler._request_form_state_from_client.assert_awaited_once_with(["a", "b"])

    await handler.on_tool_call(
        "confirm_field", {"field_id": "f1", "confirmation_method": "manual"}
    )
    handler._request_coordinator.request_confirm_field.assert_awaited_once_with(
        "f1", "manual"
    )


@pytest.mark.asyncio
async def test_tool_name_is_normalized_case_insensitively():
    """on_tool_call lowercases the tool name, so a differently-cased name from the
    model still routes (the dispatcher compares against lowercase literals)."""
    handler = _make_handler()

    await handler.on_tool_call("Switch_Section", {"section_identifier": "2"})
    handler._handle_switch_section.assert_awaited_once_with("2")


@pytest.mark.asyncio
async def test_get_form_state_alias_routes_to_form_status():
    """The dispatcher tolerates `get_form_state` as an alias of the declared
    `get_form_status` (the model has used both names). The alias is NOT in the
    declarations -- it is a dispatcher-side leniency -- so this pins the
    dispatcher's superset behavior intentionally rather than by accident."""
    handler = _make_handler()

    result = await handler.on_tool_call("get_form_state", {"field_ids": ["x"]})

    handler._request_form_state_from_client.assert_awaited_once_with(["x"])
    assert "state" in result  # the get_form_status response shape


@pytest.mark.asyncio
async def test_unknown_tool_returns_empty_ack_not_error():
    """An undeclared tool name is acknowledged with {} so the model can continue
    (the dispatcher's documented fallthrough), and never reaches a real handler."""
    handler = _make_handler()

    result = await handler.on_tool_call("nonexistent_tool", {"foo": "bar"})

    assert result == {}
    handler._handle_update_fields.assert_not_called()
    handler._handle_switch_section.assert_not_awaited()


# --------------------------------------------------------------------------
# Part C -- get_field_value retirement (bd polyglot-pdf-p5h2, epic
# polyglot-pdf-fc7t sprint-11 decision D1): in continuous mode (the only
# production path) recall is ask_secretary's job; switch_to_field already
# returns the current value on navigation. get_field_value must appear in
# ZERO of: TOOL_DECLARATIONS, dispatch tables, SI text.
# --------------------------------------------------------------------------
def test_get_field_value_not_in_tool_declarations():
    """No declared tool is named get_field_value -- covered structurally by
    EXPECTED_TOOL_NAMES/test_declared_tool_names_match_expected_set above, but
    pinned explicitly here as the bead's grep-checkable exit criterion."""
    names = {d["name"] for d in Settings().TOOL_DECLARATIONS}
    assert "get_field_value" not in names


def test_dti_si_recall_guidance_names_ask_secretary_not_get_field_value():
    """The DTI initiating-message recall guidance (render_section_metadata,
    which carries the 'Available fields from completed sections' line into the
    continuous-mode session/section-start injection) must steer the model to
    ask_secretary and must never mention the retired get_field_value tool."""
    from backend.services.ai_context import render_section_metadata

    block = render_section_metadata(
        form_title="I-90",
        previous_spoken_names=["first name", "last name"],
    )
    assert "ask_secretary" in block
    assert "get_field_value" not in block
    # The names are listed inline, so the block must NOT frame ask_secretary as the
    # way to fetch spoken NAMES -- it recalls the user's ANSWERS only (bd
    # polyglot-pdf-2af7). Guards against the model burning a blocking per-field
    # secretary lookup for metadata it already holds.
    assert "first name" in block and "last name" in block
    assert "ANSWERS" in block


def test_dti_si_forbids_current_field_metadata_and_steers_nav_to_switch_tool():
    """The DTI SI must forbid ask_secretary for the CURRENT field's own name/id
    (always in guidance -- the 2af7 waste), and steer navigation to a DIFFERENT
    field straight through switch_to_field with the user's own words (the tool now
    resolves the field internally -- bd polyglot-pdf-y76q), reserving ask_secretary
    for the user's past answers."""
    si = Settings().DTI_SYSTEM_INSTRUCTION
    assert "ask_secretary" in si
    lowered = si.lower()
    # Forbids the CURRENT field's own metadata specifically (not a blanket ban).
    assert "current field's name or id" in lowered
    # Navigation goes through switch_to_field with the user's words, not a
    # pre-resolution round-trip through ask_secretary.
    assert "switch_to_field" in lowered
    assert "with their own words" in lowered  # switch_to_field resolves it
    # ask_secretary is scoped to the user's past answers.
    assert "past answers" in lowered


def test_ask_secretary_tool_description_supports_nav_identification_not_current_field():
    """The ask_secretary tool DESCRIPTION must agree with the SI: it advertises the
    two legitimate uses (recall a past answer; identify a field for navigation, with
    a `fields` list) and forbids ONLY the current field's own name/id (bd
    polyglot-pdf-2af7 + polyglot-pdf-3vby)."""
    decls = {d["name"]: d for d in Settings().TOOL_DECLARATIONS}
    desc = decls["ask_secretary"]["description"]
    lowered = desc.lower()
    # Navigation-identification use is advertised, with the fields list.
    assert "identify" in lowered
    assert "`fields`" in desc
    assert "switch_to_field" in lowered
    # Forbids ONLY the current field's own metadata, not a blanket ban.
    assert "current" in lowered and "field's own name or id" in lowered


def test_dti_and_legacy_si_ask_names_by_spelling_and_verify_by_spelling():
    """Person-name fields must be asked for by SPELLING first ('How do you spell
    your <name>?') and verified by reading the spelling back, so an unspelled
    non-Anglo name is not misheard into an Anglo default (bd polyglot-pdf-5roy;
    maintainer directive: spelling is the primary ask, verify by spelling)."""
    # SPELL-BACK IS GONE FROM THE DTI SI (maintainer 2026-08-07): spelling a word
    # aloud desyncs the native-audio model's audio/text layers, so a dedicated TTS
    # tool will own the spoken read-back. The CAPTURE half -- ask for the spelling
    # FIRST -- is what protects an unspelled non-Anglo name, and it stays.
    dti = Settings().DTI_SYSTEM_INSTRUCTION.lower()
    assert "how do they spell their name" in dti
    assert "never build one from the sound" in dti
    # Legacy is unchanged and still verifies by spelling back.
    legacy = Settings().SYSTEM_INSTRUCTION.lower()
    assert "how do you spell" in legacy
    assert "spelling back" in legacy


def test_dti_and_legacy_si_spell_back_uses_english_letter_names():
    """The spell-back must use ENGLISH letter names in every session language --
    the 6mzi ru run read NGUYEN back as Cyrillic letter names, a transliteration
    that verifies nothing about the Latin spelling the form receives, and the
    run's one mis-fill (LIN vs LINH) sailed through exactly that readback
    (bd polyglot-pdf-s39z)."""
    # Legacy only -- see the spell-back note above.
    for si in (Settings().SYSTEM_INSTRUCTION,):
        lowered = si.lower()
        assert "english letter names" in lowered
        assert "every session language" in lowered
        # It must forbid translating the spelling into another alphabet.
        assert "another alphabet" in lowered


def test_dti_and_legacy_si_carry_register_and_title_translation_guidance():
    """Register must not depend on the session language (the 6mzi ru run got
    telegraphic two-word questions and an untranslated English form title while
    fr got full courteous sentences); both SIs pin the language-agnostic
    register rule + title translation (bd polyglot-pdf-zmlo / h1me)."""
    for si in (Settings().DTI_SYSTEM_INSTRUCTION, Settings().SYSTEM_INSTRUCTION):
        lowered = si.lower()
        assert ("register (how you speak" in lowered
                or "register (what you say" in lowered)
        assert "never a bare two-word demand" in lowered
        assert "do not become terse or formal" in lowered
        # The title rule lives in different blocks now: v4 states it in
        # LANGUAGE ("field name, option label, form or section title -- you
        # translate yourself"); the legacy SI states it in REGISTER. Assert the
        # RULE, not the block it happens to sit in.
        assert ("form or section title" in lowered
                or "never read an english title aloud" in lowered)


def test_dti_and_legacy_si_pin_declines_to_empty_never_literal_na():
    """A decline/not-applicable stores the EMPTY value, never the literal text
    'N/A' -- the 6mzi zh run wrote literal 'N/A' into in-care-of-name and middle
    name while every other language correctly stored empty; what prints on the
    PDF must not depend on the session language (bd polyglot-pdf-nb2c)."""
    for si in (Settings().DTI_SYSTEM_INSTRUCTION, Settings().SYSTEM_INSTRUCTION):
        lowered = si.lower()
        assert ("never the literal text \"n/a\"" in lowered
                or "never 'n/a'" in lowered)
        assert "any equivalent in any language" in lowered
        assert "every language" in lowered


def test_dti_and_legacy_si_forbid_checking_a_declined_optional_checkbox():
    """Declining an optional checkbox must map to value \"\" (unchecked), never
    \"true\"/\"false\" -- writing \"true\" wrongly checks a box the user declined, a
    wrong answer on a legal form (bd polyglot-pdf-cx23). Both the live DTI SI and
    the legacy harness-baseline SI must carry the rule."""
    for si in (Settings().DTI_SYSTEM_INSTRUCTION, Settings().SYSTEM_INSTRUCTION):
        lowered = si.lower()
        assert "declined checkbox" in lowered
        assert ("unchecked" in lowered
                or "wrongly checks the box" in lowered)
        # It must explicitly forbid the wrong write.
        assert ("never write \"true\"" in lowered
                or "never write 'true'" in lowered)


def test_switch_to_field_desc_steers_back_nav_to_spoken_name_not_guessed_id():
    """switch_to_field's description must let the model pass the user's own
    words (spoken name or a rough description), forbid reconstructing/guessing
    a field_id from memory, and tell the model the tool resolves the target
    internally rather than the model or ask_secretary doing so (resolution
    moved inside the tool; bd polyglot-pdf-y76q)."""
    decls = {d["name"]: d for d in Settings().TOOL_DECLARATIONS}
    desc = decls["switch_to_field"]["description"].lower()
    assert "spoken name" in desc or "description" in desc
    assert "guess" in desc or "invent" in desc  # never reconstruct/guess a field_id
    assert "figures out" in desc or "resolves" in desc  # the tool resolves it for you


def test_legacy_si_recall_guidance_does_not_mention_get_field_value():
    """The legacy full-SI template (harness-only baseline, Settings.SYSTEM_INSTRUCTION)
    has no ask_secretary tool declared for it, so it must not steer the model to
    a tool -- it must simply never name the retired get_field_value tool."""
    from backend.services.ai_context import build_form_context

    legacy_settings = Settings(USE_DTI=False, CONTINUOUS_SESSION=False)
    schema = {
        "form_metadata": {"title": "I-90"},
        "fields": [{"id": "f1", "name": "First name", "type": "text"}],
    }
    # build_form_context reads get_settings() from its own module scope, so
    # patch it the same way test_ai_context.py's legacy fixture does.
    import backend.services.ai_context as ai_context_mod
    original_get_settings = ai_context_mod.get_settings
    try:
        ai_context_mod.get_settings = lambda: legacy_settings
        si = build_form_context(
            schema, {}, "English", previous_spoken_names=["first name"]
        )
    finally:
        ai_context_mod.get_settings = original_get_settings
    assert "get_field_value" not in si
