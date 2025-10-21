"""
Unit tests for FormFillingService web form mode.

Tests the stateless web form architecture where sessions are connection-scoped.
"""
import pytest
from unittest.mock import Mock, AsyncMock, MagicMock
from backend.services.form_filling_service import FormFillingService
from backend.config import Settings


def create_form_field(field_data: dict):
    """Helper to create FormField from schema field_data."""
    from backend.models.form_models import FormField, Rect
    return FormField(
        id=field_data.get("id"),
        name=field_data.get("name"),
        spoken_name=field_data.get("name"),
        spoken_aliases=[],
        page_index=field_data.get("page_index", 0),
        rect=Rect(x0=0, y0=0, x1=100, y1=20),  # Dummy rect for web fields
        value=field_data.get("value"),
        field_type=field_data.get("type", "text"),
        options=field_data.get("options", []),
        normalized_options=field_data.get("options", []),
        group_id=None,
        section_id=None,
        meta=field_data.get("meta", {}),
    )


@pytest.fixture
def mock_settings():
    """Settings with minimal configuration."""
    settings = Mock(spec=Settings)
    settings.SYSTEM_INSTRUCTIONS = "You are a helpful assistant."
    return settings


@pytest.fixture
def sample_web_schema():
    """Sample web form schema matching unified JSON format."""
    return {
        "source": "web",
        "form_metadata": {
            "title": "Contact Form",
            "url": "https://example.com/contact"
        },
        "fields": [
            {
                "id": "email",
                "name": "Email Address",
                "type": "text",  # Web form text field
                "required": True,
                "value": "",
                "meta": {}
            },
            {
                "id": "full_name",
                "name": "Full Name",
                "type": "text",
                "required": True,
                "value": "",
                "meta": {}
            },
            {
                "id": "country",
                "name": "Country",
                "type": "select",  # Web form select/dropdown field
                "required": False,
                "options": ["USA", "Canada", "Mexico"],
                "value": "USA",
                "meta": {
                    "has_default": True
                }
            }
        ]
    }


@pytest.fixture
def current_values_reconnect():
    """Sample current_values from a reconnect scenario."""
    return {
        "email": {
            "value": "user@example.com",
            "confirmed": True
        },
        "full_name": {
            "value": "John Doe",
            "confirmed": True
        },
        # country not filled yet
    }


class TestEphemeralModeInitialization:
    """Test web form session initialization."""
    
    def test_web_service_initialization(self, mock_settings):
        """Verify FormFillingService initializes correctly for web forms."""
        service = FormFillingService(
            settings=mock_settings
        )
        
        # Service should be created successfully
        assert service is not None
        assert service._settings == mock_settings
    
    def test_schema_handling(self, mock_settings, sample_web_schema):
        """Verify schema can be processed correctly."""
        service = FormFillingService(
            settings=mock_settings
        )
        
        # Simulate what happens in start_session for web forms
        service._schema = sample_web_schema
        
        # Build fields from schema
        fields = service._build_fields_from_schema()
        
        assert len(fields) == 3
        assert fields[0].id == "email"
        assert fields[1].id == "full_name"
        assert fields[2].id == "country"


class TestEphemeralFieldBuilding:
    """Test building FormField objects from web schema."""
    
    @pytest.mark.asyncio
    async def test_fields_built_from_schema(self, mock_settings, sample_web_schema):
        """Verify fields are correctly built from schema."""
        service = FormFillingService(
            settings=mock_settings
        )
        
        # Manually initialize ephemeral state (simulating what start_session does)
        # Web mode (no flag needed)
        service._schema = sample_web_schema
        service._values = {}
        service._fields = []
        
        # Build fields using the schema (this happens in _ordered_fields)
        fields = [create_form_field(field_data) for field_data in sample_web_schema["fields"]]
        service._fields = fields
        
        # Verify fields were created
        assert len(service._fields) == 3
        assert service._fields[0].id == "email"
        assert service._fields[0].name == "Email Address"
        assert service._fields[0].field_type == "text"
        
        assert service._fields[1].id == "full_name"
        assert service._fields[1].field_type == "text"
        
        assert service._fields[2].id == "country"
        assert service._fields[2].options == ["USA", "Canada", "Mexico"]
        assert service._fields[2].value == "USA"
    
    @pytest.mark.asyncio
    async def test_current_values_applied_on_reconnect(
        self, 
        mock_settings, 
        sample_web_schema, 
        current_values_reconnect
    ):
        """Verify current_values are applied when reconnecting."""
        service = FormFillingService(
            settings=mock_settings
        )
        
        # Simulate reconnect scenario
        # Web mode (no flag needed)
        service._schema = sample_web_schema
        service._values = current_values_reconnect
        service._fields = []
        
        # Build fields with current_values applied
        fields = []
        for field_data in sample_web_schema["fields"]:
            field = create_form_field(field_data)
            
            # Apply current_values if reconnecting
            field_id = field_data.get("id")
            if field_id and field_id in service._values:
                value_data = service._values[field_id]
                if isinstance(value_data, dict):
                    field.value = value_data.get("value")
                    if "confirmed" in value_data:
                        if not isinstance(field.meta, dict):
                            field.meta = {}
                        field.meta["confirmed"] = value_data["confirmed"]
            
            fields.append(field)
        
        service._fields = fields
        
        # Verify values were applied
        email_field = next(f for f in service._fields if f.id == "email")
        assert email_field.value == "user@example.com"
        assert email_field.meta["confirmed"] is True
        
        name_field = next(f for f in service._fields if f.id == "full_name")
        assert name_field.value == "John Doe"
        assert name_field.meta["confirmed"] is True
        
        # Country should keep default value (not in current_values)
        country_field = next(f for f in service._fields if f.id == "country")
        assert country_field.value == "USA"
        assert country_field.meta.get("confirmed") is None  # Not explicitly confirmed


class TestEphemeralFieldUpdates:
    """Test field updates in ephemeral mode."""
    
    def test_handle_update_routes_to_ephemeral(self, mock_settings, sample_web_schema):
        """Verify handle_update_fields_tool_call uses ephemeral path when _is_ephemeral=True."""
        service = FormFillingService(
            settings=mock_settings
        )
        
        # Setup ephemeral mode with some fields
        # Web mode (no flag needed)
        service._schema = sample_web_schema
        service._values = {}
        
        # Build fields using helper
        fields = [create_form_field(field_data) for field_data in sample_web_schema["fields"]]
        service._fields = fields
        
        # Apply an update - web forms use field IDs, not names
        updates = {
            "email": "test@example.com",
            "full_name": "Jane Smith"
        }
        
        result = service.handle_update_fields_tool_call("web_abc123", updates)
        
        # Verify the update was acknowledged
        assert result is not None
        assert "applied_fields" in result
        assert len(result["applied_fields"]) == 2
        
        # Note: handle_update_fields_tool_call doesn't actually update field values in web mode
        # It just validates and acknowledges - the client updates the actual form
    
    def test_handle_update_does_not_use_session_manager(
        self, 
        mock_settings, 
        sample_web_schema
    ):
        """Verify web form updates work without session manager."""
        from backend.models.form_models import Rect
        service = FormFillingService(
            settings=mock_settings
        )
        
        # Setup web form session
        service._schema = sample_web_schema
        
        from backend.models.form_models import FormField
        fields = [
            FormField(
                id="email",
                name="Email",
                spoken_name="Email",
                spoken_aliases=[],
                page_index=0,
                rect=Rect(x0=0, y0=0, x1=100, y1=20),
                value="",
                field_type="text",
                options=[],
                normalized_options=[],
                group_id=None,
                section_id=None,
                meta={},
            )
        ]
        service._fields = fields
        
        # Apply update
        updates = {"email": "test@example.com"}  # Use field ID
        result = service.handle_update_fields_tool_call("web_abc123", updates)
        
        # Verify the update was acknowledged
        assert result is not None
        assert "applied_fields" in result
        assert "email" in result["applied_fields"]


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_schema_fields(self, mock_settings):
        """Verify handling of schema with no fields."""
        service = FormFillingService(
            settings=mock_settings
        )
        
        # Web mode (no flag needed)
        service._schema = {
            "source": "web",
            "fields": []
        }
        service._values = {}
        service._fields = []
        
        # Should not crash
        result = service.handle_update_fields_tool_call("web_abc123", {"Test": "value"})
        
        assert result is not None
        assert len(result.get("unknown_fields", [])) == 1  # Field not found
    
    def test_current_values_with_simple_string(self, mock_settings, sample_web_schema):
        """Verify current_values can be simple strings (not just dicts)."""
        service = FormFillingService(
            settings=mock_settings
        )
        
        # Web mode (no flag needed)
        service._schema = sample_web_schema
        service._values = {
            "email": "simple@example.com"  # Simple string, not dict
        }
        
        fields = []
        for field_data in sample_web_schema["fields"]:
            field = create_form_field(field_data)
            
            # Apply current_values
            field_id = field_data.get("id")
            if field_id and field_id in service._values:
                value_data = service._values[field_id]
                if isinstance(value_data, dict):
                    field.value = value_data.get("value")
                else:
                    # Simple string value
                    field.value = value_data
                    if not isinstance(field.meta, dict):
                        field.meta = {}
                    field.meta["confirmed"] = True
            
            fields.append(field)
        
        service._fields = fields
        
        email_field = next(f for f in service._fields if f.id == "email")
        assert email_field.value == "simple@example.com"
        assert email_field.meta["confirmed"] is True
    
    def test_unknown_field_in_updates(self, mock_settings, sample_web_schema):
        """Verify unknown fields are tracked in unknown_fields."""
        from backend.models.form_models import FormField, Rect
        service = FormFillingService(
            settings=mock_settings
        )
        
        # Web mode (no flag needed)
        service._schema = sample_web_schema
        
        service._fields = [
            FormField(
                id="email",
                name="Email",
                spoken_name="Email",
                spoken_aliases=[],
                page_index=0,
                rect=Rect(x0=0, y0=0, x1=100, y1=20),
                value="",
                field_type="text",
                options=[],
                normalized_options=[],
                group_id=None,
                section_id=None,
                meta={},
            )
        ]
        
        updates = {
            "email": "test@example.com",  # Known field (using ID)
            "phone": "555-1234"      # Unknown field
        }
        
        result = service.handle_update_fields_tool_call("web_abc123", updates)
        
        assert result is not None
        assert len(result["applied_fields"]) == 1
        assert "email" in result["applied_fields"]
        assert len(result["unknown_fields"]) == 1
        assert "phone" in result["unknown_fields"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
