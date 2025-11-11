"""
Tests for JIT (Just-In-Time) Schema Loading - Phase 2.5

Tests cover:
- get_next_field_schema_for_jit() method in FormFillingService
- Integration with callback_handler update_form_fields
- loaded_field_ids tracking
- Feature flag behavior (USE_JIT_SCHEMA)
- Tool response includes next_field_schema

@version 1.0.0
@date 2025-11-10
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from backend.services.form_filling_service import FormFillingService
from backend.services.callback_handler import CallbackHandler
from backend.services.request_coordinator import RequestCoordinator
from backend.config import Settings


@pytest.fixture
def mock_settings_jit_enabled():
    """Settings with JIT schema loading enabled."""
    settings = MagicMock(spec=Settings)
    settings.USE_JIT_SCHEMA = True
    settings.TOOL_DECLARATIONS = []
    return settings


@pytest.fixture
def mock_settings_jit_disabled():
    """Settings with JIT schema loading disabled."""
    settings = MagicMock(spec=Settings)
    settings.USE_JIT_SCHEMA = False
    settings.TOOL_DECLARATIONS = []
    return settings


@pytest.fixture
def sample_schema():
    """Sample form schema with multiple fields."""
    return {
        "id": "test-form",
        "title": "Test Form",
        "fields": [
            {
                "id": "firstName",
                "spoken_name": "first name",
                "type": "text",
                "name": "First Name",
                "required": True
            },
            {
                "id": "lastName",
                "spoken_name": "last name",
                "type": "text",
                "name": "Last Name",
                "required": True
            },
            {
                "id": "email",
                "spoken_name": "email address",
                "type": "email",
                "name": "Email",
                "required": False
            }
        ]
    }


class TestGetNextFieldSchemaForJIT:
    """Test FormFillingService.get_next_field_schema_for_jit() method."""

    def test_returns_next_field_when_jit_enabled(self, mock_settings_jit_enabled, sample_schema):
        """Should return next field schema when USE_JIT_SCHEMA=true."""
        service = FormFillingService(settings=mock_settings_jit_enabled)
        service._schema = sample_schema

        # Get schema for field after firstName
        next_schema = service.get_next_field_schema_for_jit("firstName")

        assert next_schema is not None
        assert next_schema["id"] == "lastName"
        assert next_schema["spoken_name"] == "last name"
        assert next_schema["type"] == "text"

    def test_returns_none_when_jit_disabled(self, mock_settings_jit_disabled, sample_schema):
        """Should return None when USE_JIT_SCHEMA=false."""
        service = FormFillingService(settings=mock_settings_jit_disabled)
        service._schema = sample_schema

        next_schema = service.get_next_field_schema_for_jit("firstName")

        assert next_schema is None

    def test_returns_none_when_no_schema(self, mock_settings_jit_enabled):
        """Should return None when schema not loaded."""
        service = FormFillingService(settings=mock_settings_jit_enabled)
        service._schema = None

        next_schema = service.get_next_field_schema_for_jit("firstName")

        assert next_schema is None

    def test_returns_none_when_last_field(self, mock_settings_jit_enabled, sample_schema):
        """Should return None when current field is the last field."""
        service = FormFillingService(settings=mock_settings_jit_enabled)
        service._schema = sample_schema

        # email is the last field
        next_schema = service.get_next_field_schema_for_jit("email")

        assert next_schema is None

    def test_tracks_loaded_field_ids(self, mock_settings_jit_enabled, sample_schema):
        """Should add field ID to loaded_field_ids set."""
        service = FormFillingService(settings=mock_settings_jit_enabled)
        service._schema = sample_schema

        assert len(service._loaded_field_ids) == 0

        # Get next field
        next_schema = service.get_next_field_schema_for_jit("firstName")

        # Should track the returned field (lastName)
        assert "lastName" in service._loaded_field_ids
        assert len(service._loaded_field_ids) == 1

    def test_tracks_multiple_fields(self, mock_settings_jit_enabled, sample_schema):
        """Should track multiple field IDs as they're loaded."""
        service = FormFillingService(settings=mock_settings_jit_enabled)
        service._schema = sample_schema

        # Get firstName -> lastName
        service.get_next_field_schema_for_jit("firstName")
        assert "lastName" in service._loaded_field_ids

        # Get lastName -> email
        service.get_next_field_schema_for_jit("lastName")
        assert "lastName" in service._loaded_field_ids
        assert "email" in service._loaded_field_ids
        assert len(service._loaded_field_ids) == 2

    def test_does_not_track_when_jit_disabled(self, mock_settings_jit_disabled, sample_schema):
        """Should not track field IDs when JIT is disabled."""
        service = FormFillingService(settings=mock_settings_jit_disabled)
        service._schema = sample_schema

        service.get_next_field_schema_for_jit("firstName")

        assert len(service._loaded_field_ids) == 0


class TestCallbackHandlerJITIntegration:
    """Test CallbackHandler integration with JIT schema loading."""

    @pytest.fixture
    def mock_websocket(self):
        """Create a mock WebSocket."""
        ws = MagicMock()
        ws.send_json = AsyncMock()
        return ws

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock RequestCoordinator."""
        coordinator = MagicMock(spec=RequestCoordinator)
        coordinator.request_next_field_hint = AsyncMock(return_value="last name")
        return coordinator

    @pytest.fixture
    def callback_handler_with_jit(self, mock_websocket, mock_coordinator, sample_schema):
        """Create CallbackHandler with JIT-enabled service."""
        handler = CallbackHandler(
            websocket=mock_websocket,
            session_id="test-session",
            request_coordinator=mock_coordinator
        )

        # Mock the update fields handler
        mock_update_handler = MagicMock(return_value={
            "form_state": {},
            "applied_fields": ["firstName"],
            "unknown_fields": [],
            "validation_errors": []
        })

        # Mock the JIT schema getter that returns lastName schema
        mock_jit_getter = MagicMock(return_value={
            "id": "lastName",
            "spoken_name": "last name",
            "type": "text",
            "name": "Last Name"
        })

        # Inject handlers
        handler.set_tool_handlers(
            handle_update_fields=mock_update_handler,
            handle_switch_section=AsyncMock(),
            handle_get_field_value=AsyncMock(),
            handle_complete_section=AsyncMock(),
            request_form_state_from_client=AsyncMock(),
            get_next_field_schema_for_jit=mock_jit_getter
        )

        return handler, mock_jit_getter

    @pytest.mark.asyncio
    async def test_update_includes_next_field_schema(self, callback_handler_with_jit):
        """Tool response should include next_field_schema when available."""
        handler, mock_jit_getter = callback_handler_with_jit

        # Call update_form_fields
        response = await handler.on_tool_call("update_form_fields", {
            "field_id": "firstName",
            "value": "John"
        })

        # Should have called JIT getter with updated field ID
        mock_jit_getter.assert_called_once_with("firstName")

        # Response should include next_field_schema
        assert response is not None
        assert response["success"] is True
        assert "next_field_schema" in response
        assert response["next_field_schema"]["id"] == "lastName"
        assert response["next_field_schema"]["spoken_name"] == "last name"

    @pytest.mark.asyncio
    async def test_update_without_jit_schema(self, mock_websocket, mock_coordinator):
        """Tool response should not include schema when JIT returns None."""
        handler = CallbackHandler(
            websocket=mock_websocket,
            session_id="test-session",
            request_coordinator=mock_coordinator
        )

        mock_update_handler = MagicMock(return_value={
            "form_state": {},
            "applied_fields": ["firstName"],
            "unknown_fields": [],
            "validation_errors": []
        })

        # JIT getter returns None (disabled or last field)
        mock_jit_getter = MagicMock(return_value=None)

        handler.set_tool_handlers(
            handle_update_fields=mock_update_handler,
            handle_switch_section=AsyncMock(),
            handle_get_field_value=AsyncMock(),
            handle_complete_section=AsyncMock(),
            request_form_state_from_client=AsyncMock(),
            get_next_field_schema_for_jit=mock_jit_getter
        )

        response = await handler.on_tool_call("update_form_fields", {
            "field_id": "firstName",
            "value": "John"
        })

        # Should not include next_field_schema key
        assert response is not None
        assert response["success"] is True
        assert "next_field_schema" not in response

    @pytest.mark.asyncio
    async def test_validation_error_does_not_call_jit(self, mock_websocket, mock_coordinator):
        """Should not call JIT getter when validation fails."""
        handler = CallbackHandler(
            websocket=mock_websocket,
            session_id="test-session",
            request_coordinator=mock_coordinator
        )

        # Validation error in update
        mock_update_handler = MagicMock(return_value={
            "form_state": {},
            "applied_fields": [],
            "unknown_fields": [],
            "validation_errors": [{
                "field_id": "firstName",
                "field_name": "First Name",
                "value": "",
                "constraint": "required"
            }]
        })

        mock_jit_getter = MagicMock()

        handler.set_tool_handlers(
            handle_update_fields=mock_update_handler,
            handle_switch_section=AsyncMock(),
            handle_get_field_value=AsyncMock(),
            handle_complete_section=AsyncMock(),
            request_form_state_from_client=AsyncMock(),
            get_next_field_schema_for_jit=mock_jit_getter
        )

        response = await handler.on_tool_call("update_form_fields", {
            "field_id": "firstName",
            "value": ""
        })

        # Should NOT call JIT getter on validation error
        mock_jit_getter.assert_not_called()

        # Response should indicate failure
        assert response is not None
        assert response["success"] is False
        assert "next_field_schema" not in response


class TestBackwardCompatibility:
    """Test that JIT changes maintain backward compatibility."""

    def test_service_without_jit_getter_still_works(self, mock_settings_jit_disabled):
        """FormFillingService should work without JIT getter being called."""
        service = FormFillingService(settings=mock_settings_jit_disabled)

        # Should initialize without errors
        assert service._loaded_field_ids == set()

        # Should return None when called (feature disabled)
        result = service.get_next_field_schema_for_jit("any_field")
        assert result is None

    @pytest.mark.asyncio
    async def test_callback_handler_without_jit_method(self):
        """CallbackHandler should work even if JIT method not injected."""
        ws = MagicMock()
        ws.send_json = AsyncMock()
        coordinator = MagicMock()
        coordinator.request_next_field_hint = AsyncMock(return_value="next field")

        handler = CallbackHandler(
            websocket=ws,
            session_id="test",
            request_coordinator=coordinator
        )

        # Inject handlers WITHOUT get_next_field_schema_for_jit
        # (This would be the old code path)
        mock_update = MagicMock(return_value={
            "form_state": {},
            "applied_fields": ["field1"],
            "unknown_fields": [],
            "validation_errors": []
        })

        handler.set_tool_handlers(
            handle_update_fields=mock_update,
            handle_switch_section=AsyncMock(),
            handle_get_field_value=AsyncMock(),
            handle_complete_section=AsyncMock(),
            request_form_state_from_client=AsyncMock(),
            get_next_field_schema_for_jit=None  # Explicitly None
        )

        # Should still work without errors
        response = await handler.on_tool_call("update_form_fields", {
            "field_id": "field1",
            "value": "test"
        })

        assert response is not None
        assert response["success"] is True
        # Should not have schema (JIT not available)
        assert "next_field_schema" not in response
