"""
Unit tests for how CallbackHandler SHAPES a field-update result into the tool
response sent back to Gemini.

SCOPE (bd polyglot-pdf-nx6g): the classes that inject a mocked
`handle_update_fields` (TestUpdateResponseShaping_Valid /
TestUpdateResponseShaping_Invalid / TestUpdateErrorMessageFormatting /
TestUpdateResponseShaping_SingleField below) test ONLY the response-shaping /
formatter wiring -- given a validator RESULT (applied/unknown/validation_errors),
does on_tool_call produce the right success flag, applied_fields, unknown_fields,
and the "ERRORS:" message envelope. The real validator (backend/utils/field_validator
.validate_updates) is NOT exercised by these classes (it is replaced by the mock),
so any value/pattern string they assert comes from the injected FIXTURE, not from
validating the input. They would stay green if the real validator changed.

The REAL validator behavior IS covered, deliberately, elsewhere:
- `TestANumberNormalization` (this file) calls `validate_updates` directly.
- `backend/tests/unit/test_d24n_dict_option_validation.py` covers enum/option
  validation against the real validator.
So the formatter tests below are honest formatter coverage, not validator coverage.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.services.callback_handler import CallbackHandler
from backend.services.request_coordinator import RequestCoordinator
from fastapi import WebSocket


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket for testing."""
    ws = MagicMock(spec=WebSocket)
    ws.send_json = AsyncMock()
    ws.send_bytes = AsyncMock()
    return ws


@pytest.fixture
def mock_coordinator():
    """Create a mock RequestCoordinator."""
    coordinator = MagicMock(spec=RequestCoordinator)
    coordinator.request_form_state = AsyncMock()
    coordinator.request_next_field_hint = AsyncMock()
    coordinator.request_field_value = AsyncMock()
    coordinator.request_section_info = AsyncMock()
    return coordinator


@pytest.fixture
def validation_handler_valid():
    """Mock handler that accepts valid field updates."""
    handler = MagicMock()
    handler.return_value = {
        "form_state": {"p1_line1_aliennumber": "1234567"},
        "applied_fields": ["p1_line1_aliennumber"],
        "unknown_fields": [],
        "validation_errors": []
    }
    return handler


@pytest.fixture
def validation_handler_invalid_pattern():
    """Mock handler that rejects field with pattern violation (A-number too short)."""
    handler = MagicMock()
    handler.return_value = {
        "form_state": {},  # Empty because validation failed
        "applied_fields": [],  # No fields applied
        "unknown_fields": [],
        "validation_errors": [
            {
                "field_id": "p1_line1_aliennumber",
                "field_name": "Alien Registration Number",
                "value": "1234",
                "constraint": "pattern",
                "constraint_value": "^\\d{7,9}$"
            }
        ]
    }
    return handler


@pytest.fixture
def validation_handler_unknown_field():
    """Mock handler that reports unknown field."""
    handler = MagicMock()
    handler.return_value = {
        "form_state": {},
        "applied_fields": [],
        "unknown_fields": ["nonexistent_field"],
        "validation_errors": []
    }
    return handler


def create_callback_handler(mock_websocket, mock_coordinator, update_handler):
    """Helper to create CallbackHandler with specific validation behavior."""
    handler = CallbackHandler(
        websocket=mock_websocket,
        request_coordinator=mock_coordinator,
        session_id="test-session-validation"
    )

    handler.set_tool_handlers(
        handle_update_fields=update_handler,
        handle_switch_section=AsyncMock(),
        handle_get_field_value=AsyncMock(),
        request_form_state_from_client=AsyncMock(),
        get_next_field_schema_for_jit=MagicMock(return_value=None),
    )

    return handler


class TestUpdateResponseShaping_Valid:
    """FORMATTER-ONLY (mocked validator): given an APPLIED result, on_tool_call
    shapes a success tool response. Does NOT test the validator -- see module
    docstring; the real accept-path is in TestANumberNormalization."""

    @pytest.mark.asyncio
    async def test_applied_result_shapes_success_response(
        self, mock_websocket, mock_coordinator, validation_handler_valid
    ):
        """Given the (mocked) handler reports the field applied, the tool response
        to Gemini is success=True with the field in applied_fields. The '1234567'
        below is the FIXTURE's return value, not a validated input."""
        handler = create_callback_handler(
            mock_websocket, mock_coordinator, validation_handler_valid
        )

        # Gemini sends valid A-number
        tool_response = await handler.on_tool_call(
            tool_name="update_form_fields",
            arguments={"field_id": "p1_line1_aliennumber", "value": "1234567"}
        )

        # Verify tool response to Gemini indicates success
        assert tool_response["success"] is True
        assert "p1_line1_aliennumber" in tool_response["applied_fields"]
        assert "validation_errors" not in tool_response or len(tool_response.get("validation_errors", [])) == 0

        # Note: WebSocket send_json is called asynchronously during execution
        # The key validation logic is verified through the tool response


class TestUpdateResponseShaping_Invalid:
    """FORMATTER-ONLY (mocked validator): given a REJECTED result, on_tool_call
    shapes a failure tool response with the error envelope. Does NOT test the
    validator -- the asserted '1234'/pattern strings come from the injected
    FIXTURE, not from validating '1234'. Real reject-path: TestANumberNormalization."""

    @pytest.mark.asyncio
    async def test_rejected_result_shapes_error_response_for_gemini(
        self, mock_websocket, mock_coordinator, validation_handler_invalid_pattern
    ):
        """Given the (mocked) handler reports a pattern rejection, the tool response
        is success=False with the validation_errors surfaced in an 'ERRORS:'
        message. The '1234' / pattern text below is the FIXTURE's content, asserting
        the FORMATTER passes it through -- not that the validator rejected '1234'."""
        handler = create_callback_handler(
            mock_websocket, mock_coordinator, validation_handler_invalid_pattern
        )

        # Gemini sends invalid A-number (too short)
        tool_response = await handler.on_tool_call(
            tool_name="update_form_fields",
            arguments={"field_id": "p1_line1_aliennumber", "value": "1234"}
        )

        # Verify tool response indicates failure
        assert tool_response["success"] is False, "Validation failure should return success=False"
        assert len(tool_response["applied_fields"]) == 0, "No fields should be applied"
        assert len(tool_response["validation_errors"]) == 1, "Should have exactly one validation error"

        # Verify error message is informative
        error_message = tool_response["message"]
        assert "ERRORS:" in error_message, "Error message should be clearly marked"
        assert "Alien Registration Number" in error_message or "p1_line1_aliennumber" in error_message
        assert "1234" in error_message, "Error should mention the invalid value"
        assert "pattern" in error_message or "\\d{7,9}" in error_message, "Error should explain the pattern requirement"

        # Note: The fix ensures frontend receives empty form_state when validation fails
        # This is verified by the backend fix at callback_handler.py:305

    # NOTE: The old test_a_number_with_letter_prefix_returns_error asserted that
    # an "A"-prefixed A-Number was REJECTED. That behavior was changed under bd
    # polyglot-pdf-0zr: the "A" prefix (and separators) is the natural way users
    # speak/write an A-Number, so the a_number format_preset now NORMALIZES it to
    # the canonical bare-digit form before validation instead of rejecting it. The
    # real normalize+validate behavior is covered by TestANumberNormalization
    # below (against the actual field_validator, not a mocked handler).

    @pytest.mark.asyncio
    async def test_unknown_field_returns_clear_error(
        self, mock_websocket, mock_coordinator, validation_handler_unknown_field
    ):
        """Unknown field should return clear error to Gemini."""
        handler = create_callback_handler(
            mock_websocket, mock_coordinator, validation_handler_unknown_field
        )

        # Gemini sends update to unknown field
        tool_response = await handler.on_tool_call(
            tool_name="update_form_fields",
            arguments={"field_id": "nonexistent_field", "value": "some value"}
        )

        # Verify failure response
        assert tool_response["success"] is False
        assert len(tool_response["applied_fields"]) == 0
        assert "nonexistent_field" in tool_response["unknown_fields"]

        # Verify error message mentions unknown field
        error_message = tool_response["message"]
        assert "ERRORS:" in error_message
        assert "nonexistent_field" in error_message
        assert "unknown" in error_message.lower()


class TestUpdateErrorMessageFormatting:
    """FORMATTER-ONLY (mocked validator): the 'ERRORS:' message envelope shape --
    prefix, the field identifier, the quoted value, and the constraint text are
    carried through from the (mocked) validation_errors into the Gemini message.
    The pattern/value strings asserted are the FIXTURE's, not a real validation
    outcome. Real validator: TestANumberNormalization."""

    @pytest.mark.asyncio
    async def test_pattern_error_includes_constraint_value(
        self, mock_websocket, mock_coordinator, validation_handler_invalid_pattern
    ):
        """The formatter carries the (fixture-provided) regex pattern into the
        error message so Gemini sees the constraint."""
        handler = create_callback_handler(
            mock_websocket, mock_coordinator, validation_handler_invalid_pattern
        )

        tool_response = await handler.on_tool_call(
            tool_name="update_form_fields",
            arguments={"field_id": "p1_line1_aliennumber", "value": "1234"}
        )

        # Verify constraint value is in error message
        error_message = tool_response["message"]
        assert "pattern=^\\d{7,9}$" in error_message or "\\d{7,9}" in error_message, \
            "Error should include the pattern constraint for Gemini to understand requirements"

    @pytest.mark.asyncio
    async def test_error_message_format_is_parseable(
        self, mock_websocket, mock_coordinator, validation_handler_invalid_pattern
    ):
        """Error messages should follow consistent format for Gemini parsing."""
        handler = create_callback_handler(
            mock_websocket, mock_coordinator, validation_handler_invalid_pattern
        )

        tool_response = await handler.on_tool_call(
            tool_name="update_form_fields",
            arguments={"field_id": "p1_line1_aliennumber", "value": "1234"}
        )

        error_message = tool_response["message"]

        # Verify format: "ERRORS: field_name: 'value' | constraint=constraint_value"
        assert error_message.startswith("ERRORS:"), "Errors should start with 'ERRORS:' prefix"
        assert ":" in error_message, "Error should include field identifier"
        assert "'1234'" in error_message or "1234" in error_message, "Error should quote or show the invalid value"


class TestUpdateResponseShaping_SingleField:
    """FORMATTER-ONLY (mocked validator): the single-field update format shapes a
    success response. (Was named TestMultiFieldRejection /
    test_multiple_fields_rejected_with_clear_message -- a MISLABEL fixed under bd
    polyglot-pdf-nx6g: it sends exactly ONE field and asserts the happy path, never
    a multi-field rejection. update_form_fields only takes one field_id/value, so
    there is no multi-field path to reject.)"""

    @pytest.mark.asyncio
    async def test_single_field_update_shapes_success_response(
        self, mock_websocket, mock_coordinator
    ):
        """The single-field update format (one field_id/value) yields a success
        response with the field applied."""
        # Mock handler that reports the single field applied.
        handler_mock = MagicMock()
        handler_mock.return_value = {
            "form_state": {"field1": "value1"},
            "applied_fields": ["field1"],
            "unknown_fields": [],
            "validation_errors": []
        }

        handler = create_callback_handler(mock_websocket, mock_coordinator, handler_mock)

        # update_form_fields takes a SINGLE field_id/value (the only supported format).
        tool_response = await handler.on_tool_call(
            tool_name="update_form_fields",
            arguments={"field_id": "field1", "value": "value1"}
        )

        # Field is processed successfully (single-field format is correct).
        assert tool_response["success"] is True
        assert "field1" in tool_response["applied_fields"]
        # Success responses don't include validation_errors key
        assert "validation_errors" not in tool_response or len(tool_response.get("validation_errors", [])) == 0


class TestANumberNormalization:
    """Real (non-mocked) validate_updates behavior for the a_number format_preset.

    Exercises backend/utils/field_validator.py directly to prove the A-Number is
    normalized to its canonical bare-digit form before pattern validation, so
    naturally-formatted input (with the "A" prefix and/or separators) is accepted
    and the stored value is bare digits (bd polyglot-pdf-0zr).
    """

    A_NUMBER_FIELD = {
        "id": "p1_line1_aliennumber",
        "name": "Alien Registration Number",
        "type": "text",
        "pattern": r"^\d{7,9}$",
        "maxLength": 9,
        "format_preset": "a_number",
    }

    @pytest.mark.parametrize("raw,expected", [
        ("123456789", "123456789"),    # already canonical
        ("A12345678", "12345678"),     # canonical A-prefix form
        ("a12345678", "12345678"),     # lowercase prefix
        ("A-12345678", "12345678"),    # dashed
        ("A 1234 5678", "12345678"),   # spaced
        ("1234567", "1234567"),        # 7 digits, no prefix
    ])
    def test_a_number_normalized_and_accepted(self, raw, expected):
        from backend.utils.field_validator import validate_updates
        result = validate_updates([self.A_NUMBER_FIELD], {"p1_line1_aliennumber": raw})
        assert "p1_line1_aliennumber" in result["valid_fields"], f"{raw!r} should be accepted"
        assert result["form_state"]["p1_line1_aliennumber"] == expected, \
            f"{raw!r} should store canonical {expected!r}"
        assert result["validation_errors"] == []

    @pytest.mark.parametrize("raw", [
        "A1234",            # too short after stripping the A
        "12345",            # too short
        "A1234567890",      # too long after stripping
    ])
    def test_a_number_still_rejects_wrong_digit_count(self, raw):
        from backend.utils.field_validator import validate_updates
        result = validate_updates([self.A_NUMBER_FIELD], {"p1_line1_aliennumber": raw})
        assert "p1_line1_aliennumber" not in result["valid_fields"], f"{raw!r} should be rejected"
        assert result["validation_errors"], f"{raw!r} should produce a validation error"

    @pytest.mark.parametrize("raw", [
        "A",        # just the prefix, no digits
        "A---",     # prefix + separators, no digits
        "ABCDEF",   # all letters
        "A-",       # prefix + separator
    ])
    def test_a_number_with_no_digits_is_rejected_not_stored_empty(self, raw):
        # A non-empty input that normalizes to "" must be REJECTED, not silently
        # stored as empty (which would write blank to the PDF). bd 0zr / PR #98
        # fresh-eyes finding.
        from backend.utils.field_validator import validate_updates
        result = validate_updates([self.A_NUMBER_FIELD], {"p1_line1_aliennumber": raw})
        assert "p1_line1_aliennumber" not in result["valid_fields"], f"{raw!r} should be rejected"
        assert "p1_line1_aliennumber" not in result["form_state"], f"{raw!r} must NOT be stored"
        assert result["validation_errors"], f"{raw!r} should produce a validation error"


class TestANumberNestedFormatPreset:
    """Regression for bd polyglot-pdf-cn0e: normalize_value must resolve
    format_preset from the CANONICAL nested location (validation.format_preset),
    not only the top level.

    The pre-cn0e tests (TestANumberNormalization) only used a TOP-LEVEL
    format_preset -- the already-working flattened shape produced by
    validation_handler -- so they never caught that a field shaped like the real
    schema (format_preset nested under `validation`) had normalization silently
    no-op, making a genuine "A12345678" A-Number fail the digits-only pattern. These
    tests exercise the SCHEMA shape directly.
    """

    # Field shaped exactly like form-kits/i-90/schema.json: format_preset lives
    # under `validation`, with NO top-level format_preset.
    SCHEMA_SHAPED_FIELD = {
        "id": "p1_line1_aliennumber",
        "name": "Alien Registration Number",
        "type": "text",
        "validation": {"pattern": r"^\d{7,9}$", "format_preset": "a_number"},
        "maxLength": 9,
    }

    @pytest.mark.parametrize("raw,expected", [
        ("A12345678", "12345678"),     # the maintainer-reported live failure
        ("a12345678", "12345678"),     # lowercase prefix
        ("A-12345678", "12345678"),    # dashed
        ("123456789", "123456789"),    # already canonical
    ])
    def test_nested_preset_normalizes_and_accepts(self, raw, expected):
        from backend.utils.field_validator import validate_updates
        result = validate_updates([self.SCHEMA_SHAPED_FIELD],
                                  {"p1_line1_aliennumber": raw})
        assert "p1_line1_aliennumber" in result["valid_fields"], \
            f"{raw!r} should be accepted with a nested format_preset"
        assert result["form_state"]["p1_line1_aliennumber"] == expected
        assert result["validation_errors"] == []

    def test_real_i90_schema_field_normalizes_a_number(self):
        """Load the ACTUAL i-90 schema field and prove A12345678 now validates."""
        import json
        import os
        schema_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..",
            "form-kits", "i-90", "schema.json")
        with open(schema_path, encoding="utf-8") as f:
            schema = json.load(f)
        anum = next(fld for fld in schema["fields"]
                    if fld["id"] == "p1_line1_aliennumber")
        # Sanity: confirm the schema really nests it (guards the test's premise).
        assert anum.get("format_preset") is None
        assert anum["validation"]["format_preset"] == "a_number"

        from backend.utils.field_validator import validate_updates
        result = validate_updates([anum], {"p1_line1_aliennumber": "A12345678"})
        assert "p1_line1_aliennumber" in result["valid_fields"]
        assert result["form_state"]["p1_line1_aliennumber"] == "12345678"
        assert result["validation_errors"] == []


class TestUSCISAccountNormalization:
    """uscis_account format_preset strips punctuation before the length check
    (bd polyglot-pdf-jnjj.40).

    The DTI stall was triggered because Gemini's speech-to-text transcribed a
    spoken USCIS online account number with a "$" and commas (the original 10-digit
    fixture transcribed as "$1,234,567,890"; a 12-digit value corrupts the same way,
    e.g. "$1,234,567,890,12"), which then failed the exactly-12-character length
    check and the model refused the field, derailing the section. Normalizing to
    bare digits BEFORE validation accepts the value, so the punctuation can never
    re-trigger the stall.
    """

    ACCT_FIELD = {
        "id": "p1_line2_acctidentifier",
        "name": "USCIS Online Account Number",
        "type": "text",
        "minLength": 12,
        "maxLength": 12,
        "pattern": r"^[0-9]{12}$",   # mirrors the I-90 schema -- ASCII digits only (Codex PR #249)
        "format_preset": "uscis_account",
    }

    @pytest.mark.parametrize("raw,expected", [
        ("123456789012", "123456789012"),       # already canonical 12 digits
        ("$1,234,567,890,12", "123456789012"),   # the STT-mangled form (jnjj.40)
        ("1,234,567,890,12", "123456789012"),    # commas only
        ("1 2 3 4 5 6 7 8 9 0 1 2", "123456789012"),  # spaced digit-by-digit
    ])
    def test_uscis_account_normalized_and_accepted(self, raw, expected):
        from backend.utils.field_validator import validate_updates
        result = validate_updates([self.ACCT_FIELD], {"p1_line2_acctidentifier": raw})
        assert "p1_line2_acctidentifier" in result["valid_fields"], f"{raw!r} should be accepted"
        assert result["form_state"]["p1_line2_acctidentifier"] == expected, \
            f"{raw!r} should store canonical {expected!r}"
        assert result["validation_errors"] == []

    @pytest.mark.parametrize("raw", [
        "1234567890",       # 10 digits -- too short (the old harness-fixture value)
        "1234567890123",    # 13 digits -- too long
    ])
    def test_uscis_account_still_enforces_length_after_normalizing(self, raw):
        # Stripping punctuation must NOT relax the exactly-12-digit rule -- a wrong
        # digit COUNT is still rejected (so the fix tolerates formatting, not bad data).
        from backend.utils.field_validator import validate_updates
        result = validate_updates([self.ACCT_FIELD], {"p1_line2_acctidentifier": raw})
        assert "p1_line2_acctidentifier" not in result["valid_fields"], f"{raw!r} should be rejected"
        assert result["validation_errors"], f"{raw!r} should produce a validation error"

    def test_uscis_account_rejects_non_ascii_digits(self):
        # The pattern is ^[0-9]{12}$ (ASCII), NOT ^\d{12}$ -- Python re's \d matches
        # Unicode digits (Arabic-Indic, fullwidth), which the frontend mirror and the
        # PDF comb field do not accept. 12 fullwidth digits must be REJECTED so the
        # backend can't apply a value the client/PDF would refuse (Codex PR #249).
        from backend.utils.field_validator import validate_updates
        # 12 fullwidth digits (U+FF10..U+FF19); written as escapes to keep this
        # source file ASCII-only (CLAUDE.md scar #6 -- cp1252 crash risk).
        fullwidth = "".join(chr(0xFF10 + d) for d in [1, 2, 3, 4, 5, 6, 7, 8, 9, 0, 1, 2])
        result = validate_updates([self.ACCT_FIELD], {"p1_line2_acctidentifier": fullwidth})
        assert "p1_line2_acctidentifier" not in result["valid_fields"]
        assert result["validation_errors"]

    @pytest.mark.parametrize("raw", [
        "ABC123456789012",   # letters + 12 digits -- letters are NOT punctuation
        "12345678901A",      # 11 digits + a trailing letter (exactly 12 chars)
        "ABCDEFGHIJKL",      # all letters, 12 chars
    ])
    def test_uscis_account_rejects_letters_not_strips_them(self, raw):
        # Normalization strips PUNCTUATION only -- embedded LETTERS are KEPT so a
        # genuinely wrong value stays invalid instead of being silently coerced to
        # digits (Codex PR #249). The kept letters fail the ^\d{12}$ pattern.
        from backend.utils.field_validator import normalize_value, validate_updates
        # The letter must survive normalization (not be stripped to digits).
        assert any(c.isalpha() for c in str(normalize_value(self.ACCT_FIELD, raw))), \
            f"{raw!r} letters must be KEPT, not stripped"
        result = validate_updates([self.ACCT_FIELD], {"p1_line2_acctidentifier": raw})
        assert "p1_line2_acctidentifier" not in result["valid_fields"], f"{raw!r} should be rejected"
        assert result["validation_errors"], f"{raw!r} should produce a validation error"


# Run with: pytest backend/tests/unit/test_field_validation_responses.py -v
