"""
Unit tests for warmup mode and pre-filled form support.

Tests cover:
- Warmup system instruction building
- Pre-filled form context generation
- Metadata status annotations
- Token optimization (no formatted_status)
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.services.ai_context import (
    build_warmup_system_instruction,
    build_form_context_for_upgrade,
    build_initial_message,
)
from backend.services.form_filling_service import FormFillingService


class TestWarmupSystemInstruction:
    """Test warmup system instruction generation."""

    def test_warmup_instruction_is_minimal(self):
        """Warmup instruction should be brief to reduce tokens."""
        instruction = build_warmup_system_instruction()
        
        assert isinstance(instruction, str)
        assert len(instruction) < 200  # Should be very short
        assert "assistant" in instruction.lower()
        assert "form" in instruction.lower()

    def test_warmup_instruction_mentions_waiting(self):
        """Warmup instruction should indicate AI should wait."""
        instruction = build_warmup_system_instruction()
        
        assert "wait" in instruction.lower() or "receive" in instruction.lower()


class TestPreFilledFormContext:
    """Test pre-filled form context building."""

    def test_upgrade_context_with_empty_form(self):
        """Upgrade context for empty form should show all fields unfilled."""
        schema = {
            "fields": [
                {"id": "name", "name": "Name", "type": "text", "required": True},
                {"id": "email", "name": "Email", "type": "email", "required": True},
            ]
        }
        current_values = {}
        
        context = build_form_context_for_upgrade(schema, current_values)
        
        assert isinstance(context, str)
        assert "Name" in context
        assert "Email" in context
        # JSON format: check for filled: false
        assert '"filled": false' in context
        # Should NOT show any filled status
        assert "(FILLED:" not in context

    def test_upgrade_context_with_prefilled_fields(self):
        """Upgrade context should highlight pre-filled fields."""
        schema = {
            "fields": [
                {"id": "name", "name": "Name", "type": "text", "required": True},
                {"id": "email", "name": "Email", "type": "email", "required": True},
                {"id": "phone", "name": "Phone", "type": "tel", "required": False},
            ]
        }
        current_values = {
            "name": "John Doe",
            "email": "john@example.com"
        }
        
        context = build_form_context_for_upgrade(schema, current_values)
        
        # Should show filled count
        assert "2 of 3 fields" in context or "2 fields" in context
        
        # JSON format: check for current_value in JSON
        assert '"current_value": "John Doe"' in context
        assert '"current_value": "john@example.com"' in context
        # Verify unfilled field doesn't have current_value
        assert context.count('"current_value"') == 2  # Only 2 filled fields
        
        # Should show unfilled field
        assert "Phone" in context
        # Unfilled field has filled: false
        assert '"filled": false' in context

    def test_upgrade_context_with_all_filled(self):
        """Upgrade context when all fields are filled."""
        schema = {
            "fields": [
                {"id": "name", "name": "Name", "type": "text", "required": True},
                {"id": "email", "name": "Email", "type": "email", "required": True},
            ]
        }
        current_values = {
            "name": "John Doe",
            "email": "john@example.com"
        }
        
        context = build_form_context_for_upgrade(schema, current_values)
        
        # Should show all fields filled
        assert "2 of 2 fields" in context or "all fields" in context.lower()
        # JSON format: all fields have filled: true
        assert '"filled": true' in context
        assert context.count('"filled": true') == 2  # Both fields
        # Should NOT have any empty fields
        assert context.count("(empty") == 0

    def test_upgrade_context_with_required_and_optional(self):
        """Upgrade context should distinguish required vs optional."""
        schema = {
            "fields": [
                {"id": "name", "name": "Name", "type": "text", "required": True},
                {"id": "phone", "name": "Phone", "type": "tel", "required": False},
            ]
        }
        current_values = {}
        
        context = build_form_context_for_upgrade(schema, current_values)
        
        # JSON format: check for required: true/false
        assert '"required": true' in context
        assert '"required": false' in context
        # Verify both values exist
        assert context.count('"required"') == 2

    def test_upgrade_context_field_ordering(self):
        """Upgrade context should maintain field order."""
        schema = {
            "fields": [
                {"id": "field1", "name": "First", "type": "text"},
                {"id": "field2", "name": "Second", "type": "text"},
                {"id": "field3", "name": "Third", "type": "text"},
            ]
        }
        current_values = {}
        
        context = build_form_context_for_upgrade(schema, current_values)
        
        # Fields should appear in order
        first_pos = context.index("First")
        second_pos = context.index("Second")
        third_pos = context.index("Third")
        
        assert first_pos < second_pos < third_pos


class TestTokenOptimization:
    """Test token optimization (no formatted_status redundancy)."""

    def test_initial_message_without_formatted_status(self):
        """Initial message should work without formatted_status."""
        class MockSettings:
            # Template is accessed as attribute, not dict
            INITIAL_MESSAGE_TEMPLATES = "Fields: {formatted_metadata}\nBegin."
        
        metadata = json.dumps([{"display_name": "Name", "status": "(empty)"}])
        
        # Should work with empty formatted_status
        msg = build_initial_message(
            settings=MockSettings,
            formatted_metadata=metadata,
            formatted_status="",  # Empty, not used
        )
        
        assert "Fields:" in msg
        assert metadata in msg
        # Should NOT have placeholder artifacts
        assert "{formatted_status}" not in msg

    def test_initial_message_formatted_status_optional(self):
        """formatted_status parameter should be optional."""
        class MockSettings:
            # Template is a string, not dict
            INITIAL_MESSAGE_TEMPLATES = "Meta: {formatted_metadata}"
        
        metadata = json.dumps([{"display_name": "Name"}])
        
        # Should work without formatted_status parameter
        msg = build_initial_message(
            settings=MockSettings,
            formatted_metadata=metadata
        )
        
        assert "Meta:" in msg
        assert isinstance(msg, str)


class TestFormFillingServiceWarmup:
    """Test FormFillingService warmup functionality."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings for testing."""
        settings = MagicMock()
        settings.SYSTEM_INSTRUCTIONS = "Normal system instruction."
        # INITIAL_MESSAGE_TEMPLATES is a string, not dict
        settings.INITIAL_MESSAGE_TEMPLATES = "Fields: {formatted_metadata}\n"
        settings.TOOL_DECLARATIONS = []
        return settings

    @pytest.fixture
    def sample_schema(self):
        """Sample form schema."""
        return {
            "source": "web",
            "fields": [
                {"id": "name", "name": "Name", "type": "text", "required": True},
                {"id": "email", "name": "Email", "type": "text", "required": True},  # Use 'text' for web forms
            ]
        }

    @pytest.mark.asyncio
    async def test_start_session_warmup_mode(self, mock_settings, sample_schema):
        """start_session with is_warmup=True should use minimal context."""
        mock_live_ai = AsyncMock()
        mock_websocket = AsyncMock()
        
        service = FormFillingService(
            live_ai=mock_live_ai,
            settings=mock_settings
        )
        
        await service.start_session(
            websocket=mock_websocket,
            session_id="warm_123",
            is_warmup=True,
            schema=sample_schema
        )
        
        # Verify set_callbacks was called
        assert mock_live_ai.set_callbacks.called
        call_kwargs = mock_live_ai.set_callbacks.call_args.kwargs
        
        # Should use warmup system instruction (minimal)
        system_instruction = call_kwargs.get("system_instruction", "")
        assert len(system_instruction) < 200  # Very brief
        assert "wait" in system_instruction.lower() or "receive" in system_instruction.lower()
        
        # Should NOT send an initial message - context comes via upgrade_session
        initial_message = call_kwargs.get("initial_message")
        assert initial_message is None or initial_message == ""

    @pytest.mark.asyncio
    async def test_start_session_normal_mode(self, mock_settings, sample_schema):
        """start_session with is_warmup=False should use full context."""
        mock_live_ai = AsyncMock()
        mock_websocket = AsyncMock()
        
        service = FormFillingService(
            live_ai=mock_live_ai,
            settings=mock_settings
        )
        
        await service.start_session(
            websocket=mock_websocket,
            session_id="web_123",
            is_warmup=False,
            schema=sample_schema
        )
        
        # Verify set_callbacks was called
        assert mock_live_ai.set_callbacks.called
        call_kwargs = mock_live_ai.set_callbacks.call_args.kwargs
        
        # Should use normal system instruction
        system_instruction = call_kwargs.get("system_instruction", "")
        assert system_instruction == mock_settings.SYSTEM_INSTRUCTIONS
        
        # Should have full initial message with field metadata
        initial_message = call_kwargs.get("initial_message", "")
        assert "Name" in initial_message or "Email" in initial_message

    @pytest.mark.asyncio
    async def test_upgrade_session(self, mock_settings, sample_schema):
        """upgrade_session should send context to Gemini."""
        mock_live_ai = AsyncMock()
        mock_websocket = AsyncMock()
        
        service = FormFillingService(
            live_ai=mock_live_ai,
            settings=mock_settings
        )
        
        # First start in warmup mode
        await service.start_session(
            websocket=mock_websocket,
            session_id="warm_123",
            is_warmup=True,
            schema=sample_schema
        )
        
        # Now upgrade with full schema
        current_values = {"name": "John Doe"}
        await service.upgrade_session(sample_schema, current_values)
        
        # Verify send_text_message was called with upgrade context
        assert mock_live_ai.send_text_message.called
        upgrade_msg = mock_live_ai.send_text_message.call_args.args[0]
        
        assert "Name" in upgrade_msg
        assert "Email" in upgrade_msg
        # JSON format: check for current_value
        assert '"current_value": "John Doe"' in upgrade_msg


class TestMetadataStatusAnnotations:
    """Test metadata status field annotations."""

    @pytest.fixture
    def mock_settings(self):
        settings = MagicMock()
        settings.SYSTEM_INSTRUCTIONS = "Test instruction."
        # INITIAL_MESSAGE_TEMPLATES is a string, not dict
        settings.INITIAL_MESSAGE_TEMPLATES = "Fields: {formatted_metadata}\n"
        settings.TOOL_DECLARATIONS = []
        return settings

    @pytest.fixture
    def sample_schema(self):
        return {
            "source": "web",
            "fields": [
                {"id": "name", "name": "Name", "type": "text"},
                {"id": "email", "name": "Email", "type": "text"},  # Use 'text' for web forms
                {"id": "phone", "name": "Phone", "type": "text"},  # Use 'text' for web forms
            ]
        }

    @pytest.mark.asyncio
    async def test_metadata_shows_empty_status(self, mock_settings, sample_schema):
        """Metadata should show (empty) for unfilled fields."""
        mock_live_ai = AsyncMock()
        mock_websocket = AsyncMock()
        
        service = FormFillingService(
            live_ai=mock_live_ai,
            settings=mock_settings
        )
        
        await service.start_session(
            websocket=mock_websocket,
            session_id="web_123",
            schema=sample_schema,
            current_values={}  # No pre-filled values
        )
        
        call_kwargs = mock_live_ai.set_callbacks.call_args.kwargs
        initial_message = call_kwargs.get("initial_message", "")
        
        # Should show empty status for all fields
        assert "(empty)" in initial_message

    @pytest.mark.asyncio
    async def test_metadata_shows_filled_status(self, mock_settings, sample_schema):
        """Metadata should show (FILLED: 'value') for pre-filled fields."""
        mock_live_ai = AsyncMock()
        mock_websocket = AsyncMock()
        
        service = FormFillingService(
            live_ai=mock_live_ai,
            settings=mock_settings
        )
        
        current_values = {
            "name": "Jane Smith",
            "email": "jane@example.com"
        }
        
        await service.start_session(
            websocket=mock_websocket,
            session_id="web_123",
            schema=sample_schema,
            current_values=current_values
        )
        
        call_kwargs = mock_live_ai.set_callbacks.call_args.kwargs
        initial_message = call_kwargs.get("initial_message", "")
        
        # Should show filled status
        assert "(FILLED: 'Jane Smith')" in initial_message
        assert "(FILLED: 'jane@example.com')" in initial_message
        # Phone should still be empty
        assert "(empty)" in initial_message

    @pytest.mark.asyncio
    async def test_metadata_no_current_value_field(self, mock_settings, sample_schema):
        """Metadata should NOT include current_value field (backend is stateless)."""
        mock_live_ai = AsyncMock()
        mock_websocket = AsyncMock()
        
        service = FormFillingService(
            live_ai=mock_live_ai,
            settings=mock_settings
        )
        
        await service.start_session(
            websocket=mock_websocket,
            session_id="web_123",
            schema=sample_schema,
            current_values={"name": "Test"}
        )
        
        call_kwargs = mock_live_ai.set_callbacks.call_args.kwargs
        initial_message = call_kwargs.get("initial_message", "")
        
        # Should NOT have "current_value" field in metadata
        assert "current_value" not in initial_message
        # Should use "status" field instead
        assert "status" in initial_message or "(FILLED:" in initial_message or "(empty)" in initial_message


class TestStatelessArchitecture:
    """Test that backend remains stateless (doesn't store field values)."""

    @pytest.fixture
    def mock_settings(self):
        settings = MagicMock()
        settings.SYSTEM_INSTRUCTIONS = "Test."
        settings.INITIAL_MESSAGE_TEMPLATES = {"web": "{formatted_metadata}"}
        settings.TOOL_DECLARATIONS = []
        return settings

    def test_service_does_not_cache_current_values(self, mock_settings):
        """Service should not store current_values internally."""
        service = FormFillingService(settings=mock_settings)
        
        # Verify no current_values attribute
        assert not hasattr(service, "_current_values")
        assert not hasattr(service, "current_values")

    def test_update_schema_does_not_store_values(self, mock_settings):
        """update_schema should only store schema, not values."""
        service = FormFillingService(settings=mock_settings)
        
        schema = {"fields": [{"id": "test", "name": "Test"}]}
        current_values = {"test": "value"}
        
        service.update_schema(schema, current_values)
        
        # Schema should be stored
        assert service._schema == schema
        
        # Values should NOT be stored
        assert not hasattr(service, "_current_values")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
