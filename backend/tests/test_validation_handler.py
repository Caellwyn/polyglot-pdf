"""
Unit tests for validation_handler module.

Tests field matching (exact + fuzzy) and validation orchestration.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from backend.services.validation_handler import ValidationHandler
from backend.models.form_models import FormField, Rect


class TestValidationHandler:
    """Tests for ValidationHandler class."""
    
    @pytest.fixture
    def dummy_rect(self):
        """Dummy rect for web form fields."""
        return Rect(x0=0, y0=0, x1=100, y1=20)
    
    @pytest.fixture
    def sample_fields(self, dummy_rect):
        """Sample fields for testing."""
        return [
            FormField(
                id="first_name",
                name="First Name",
                type="text",
                rect=dummy_rect
            ),
            FormField(
                id="email",
                name="Email Address",
                type="email",
                rect=dummy_rect
            ),
            FormField(
                id="age",
                name="Age",
                type="number",
                rect=dummy_rect
            ),
        ]
    
    def test_initialization(self):
        """Test handler initialization with and without session_id."""
        handler1 = ValidationHandler()
        assert handler1._session_id is None
        
        handler2 = ValidationHandler(session_id="test_123")
        assert handler2._session_id == "test_123"
    
    def test_exact_field_match(self, sample_fields):
        """Test exact field ID matching."""
        handler = ValidationHandler()
        
        updates = {"first_name": "John"}
        
        with patch('backend.services.validation_handler.validate_updates') as mock_validate:
            mock_validate.return_value = {
                "valid_fields": ["first_name"],
                "validation_errors": [],
                "form_state": {"first_name": "John"}
            }
            
            result = handler.validate_field_updates(sample_fields, updates)
            
            assert result is not None
            assert result["applied_fields"] == ["first_name"]
            assert result["unknown_fields"] == []
            assert result["validation_errors"] == []
            assert result["form_state"] == {"first_name": "John"}
    
    def test_unknown_field(self, sample_fields):
        """Test handling of unknown field keys."""
        handler = ValidationHandler()
        
        updates = {"unknown_field": "value"}
        
        with patch('backend.services.validation_handler.validate_updates') as mock_validate:
            mock_validate.return_value = {
                "valid_fields": [],
                "validation_errors": [],
                "form_state": {}
            }
            
            result = handler.validate_field_updates(sample_fields, updates)
            
            assert result is not None
            assert result["applied_fields"] == []
            assert result["unknown_fields"] == ["unknown_field"]
    
    def test_fuzzy_field_match(self, sample_fields):
        """Test fuzzy field matching when exact match fails."""
        handler = ValidationHandler()
        
        # Use "Email Address" (field name) instead of exact "email" ID
        updates = {"Email Address": "test@example.com"}
        
        with patch('backend.services.validation_handler.fuzzy_match_hint') as mock_fuzzy, \
             patch('backend.services.validation_handler.validate_updates') as mock_validate:
            
            # Mock fuzzy match to return the email field
            mock_result = Mock()
            mock_result.status = "resolved"
            mock_result.top_candidate = Mock()
            mock_result.top_candidate.field = sample_fields[1]  # email field
            mock_result.top_candidate.score = 0.95
            mock_fuzzy.return_value = mock_result
            
            mock_validate.return_value = {
                "valid_fields": ["email"],
                "validation_errors": [],
                "form_state": {"email": "test@example.com"}
            }
            
            result = handler.validate_field_updates(sample_fields, updates)
            
            assert result is not None
            assert result["applied_fields"] == ["email"]
            assert result["unknown_fields"] == []
            # Fuzzy match should have been called
            assert mock_fuzzy.called
    
    def test_multiple_updates(self, sample_fields):
        """Test validating multiple field updates at once."""
        handler = ValidationHandler()
        
        updates = {
            "first_name": "John",
            "email": "john@example.com",
            "age": 30
        }
        
        with patch('backend.services.validation_handler.validate_updates') as mock_validate:
            mock_validate.return_value = {
                "valid_fields": ["first_name", "email", "age"],
                "validation_errors": [],
                "form_state": {
                    "first_name": "John",
                    "email": "john@example.com",
                    "age": 30
                }
            }
            
            result = handler.validate_field_updates(sample_fields, updates)
            
            assert result is not None
            assert len(result["applied_fields"]) == 3
            assert result["unknown_fields"] == []
    
    def test_validation_errors(self, sample_fields):
        """Test handling of validation constraint errors."""
        handler = ValidationHandler()
        
        updates = {"age": -5}  # Invalid age
        
        with patch('backend.services.validation_handler.validate_updates') as mock_validate:
            mock_validate.return_value = {
                "valid_fields": [],
                "validation_errors": [{
                    "field_id": "age",
                    "field_name": "Age",
                    "constraint": "min",
                    "message": "Value must be at least 0"
                }],
                "form_state": {}
            }
            
            result = handler.validate_field_updates(sample_fields, updates)
            
            assert result is not None
            assert result["applied_fields"] == []
            assert len(result["validation_errors"]) == 1
            assert result["validation_errors"][0]["field_id"] == "age"
    
    def test_mixed_success_and_failures(self, sample_fields):
        """Test mix of successful, unknown, and invalid fields."""
        handler = ValidationHandler()
        
        updates = {
            "first_name": "John",      # Valid
            "unknown_field": "value",  # Unknown
            "age": -5                  # Invalid
        }
        
        with patch('backend.services.validation_handler.validate_updates') as mock_validate:
            mock_validate.return_value = {
                "valid_fields": ["first_name"],
                "validation_errors": [{
                    "field_id": "age",
                    "message": "Invalid age"
                }],
                "form_state": {"first_name": "John"}
            }
            
            result = handler.validate_field_updates(sample_fields, updates)
            
            assert result is not None
            assert result["applied_fields"] == ["first_name"]
            assert "unknown_field" in result["unknown_fields"]
            assert len(result["validation_errors"]) == 1
    
    def test_empty_updates(self, sample_fields):
        """Test validation with empty updates dict."""
        handler = ValidationHandler()
        
        with patch('backend.services.validation_handler.validate_updates') as mock_validate:
            mock_validate.return_value = {
                "valid_fields": [],
                "validation_errors": [],
                "form_state": {}
            }
            
            result = handler.validate_field_updates(sample_fields, {})
            
            assert result is not None
            assert result["applied_fields"] == []
            assert result["unknown_fields"] == []
    
    def test_none_updates(self, sample_fields):
        """Test validation with None updates."""
        handler = ValidationHandler()
        
        with patch('backend.services.validation_handler.validate_updates') as mock_validate:
            mock_validate.return_value = {
                "valid_fields": [],
                "validation_errors": [],
                "form_state": {}
            }
            
            result = handler.validate_field_updates(sample_fields, None)
            
            assert result is not None
            assert result["applied_fields"] == []
    
    def test_exception_handling(self, sample_fields):
        """Test that exceptions are caught and None is returned."""
        handler = ValidationHandler(session_id="test_123")
        
        with patch('backend.services.validation_handler.validate_updates') as mock_validate:
            mock_validate.side_effect = Exception("Validation crashed")
            
            result = handler.validate_field_updates(sample_fields, {"field": "value"})
            
            assert result is None  # Should return None on exception


class TestFieldMatching:
    """Tests for _match_fields method."""
    
    @pytest.fixture
    def dummy_rect(self):
        return Rect(x0=0, y0=0, x1=100, y1=20)
    
    @pytest.fixture
    def handler(self):
        return ValidationHandler(session_id="test_session")
    
    def test_exact_match_priority(self, handler, dummy_rect):
        """Test that exact ID matches take priority over fuzzy."""
        fields = [
            FormField(id="email", name="Email", type="email", rect=dummy_rect),
            FormField(id="email_alt", name="Alternative Email", type="email", rect=dummy_rect)
        ]
        
        updates = {"email": "test@example.com"}
        
        matched, unknown, field_map = handler._match_fields(fields, updates)
        
        assert "email" in matched
        assert matched["email"] == "test@example.com"
        assert unknown == []
        assert field_map["email"].id == "email"
    
    def test_fuzzy_match_fallback(self, handler, dummy_rect):
        """Test fuzzy matching when exact match not found."""
        fields = [
            FormField(id="first_name", name="First Name", type="text", rect=dummy_rect)
        ]
        
        updates = {"First Name": "John"}  # Use name instead of ID
        
        with patch('backend.services.validation_handler.fuzzy_match_hint') as mock_fuzzy:
            mock_result = Mock()
            mock_result.status = "resolved"
            mock_result.top_candidate = Mock()
            mock_result.top_candidate.field = fields[0]
            mock_result.top_candidate.score = 0.92
            mock_fuzzy.return_value = mock_result
            
            matched, unknown, field_map = handler._match_fields(fields, updates)
            
            assert "first_name" in matched
            assert matched["first_name"] == "John"
            assert unknown == []
    
    def test_no_match_found(self, handler, dummy_rect):
        """Test handling when no match is found."""
        fields = [
            FormField(id="email", name="Email", type="email", rect=dummy_rect)
        ]
        
        updates = {"unknown_field": "value"}
        
        with patch('backend.services.validation_handler.fuzzy_match_hint') as mock_fuzzy:
            mock_result = Mock()
            mock_result.status = "ambiguous"  # Not resolved
            mock_fuzzy.return_value = mock_result
            
            matched, unknown, field_map = handler._match_fields(fields, updates)
            
            assert matched == {}
            assert "unknown_field" in unknown


class TestFieldConversion:
    """Tests for _convert_fields_to_dicts method."""
    
    @pytest.fixture
    def handler(self):
        return ValidationHandler()
    
    @pytest.fixture
    def dummy_rect(self):
        return Rect(x0=0, y0=0, x1=100, y1=20)
    
    def test_basic_field_conversion(self, handler, dummy_rect):
        """Test conversion of basic field without constraints."""
        fields = [
            FormField(
                id="name",
                name="Name",
                type="text",
                rect=dummy_rect
            )
        ]
        
        result = handler._convert_fields_to_dicts(fields)
        
        assert len(result) == 1
        assert result[0]["id"] == "name"
        assert result[0]["name"] == "Name"
        assert result[0]["type"] == "text"
    
    def test_field_with_constraints(self, handler, dummy_rect):
        """Test conversion includes constraint attributes from meta."""
        # FormField doesn't have min/max as direct fields, but handler looks for them
        # This tests that if they were present (e.g., added by field_validator), they'd be included
        # For now, test that conversion works without constraints
        field = FormField(
            id="age",
            name="Age",
            type="number",
            rect=dummy_rect
        )
        
        result = handler._convert_fields_to_dicts([field])
        
        assert len(result) == 1
        assert result[0]["id"] == "age"
        assert result[0]["type"] == "number"
        # Constraints not present, so they shouldn't be in output
    
    def test_field_with_options(self, handler, dummy_rect):
        """Test conversion includes options for select fields."""
        field = FormField(
            id="country",
            name="Country",
            type="select",
            rect=dummy_rect,
            options=["USA", "Canada", "Mexico"]
        )
        
        result = handler._convert_fields_to_dicts([field])
        
        assert len(result) == 1
        assert result[0]["options"] == ["USA", "Canada", "Mexico"]
    
    def test_field_with_pattern(self, handler, dummy_rect):
        """Test conversion works for tel fields (pattern in meta if present)."""
        field = FormField(
            id="phone",
            name="Phone",
            type="tel",
            rect=dummy_rect
        )
        
        result = handler._convert_fields_to_dicts([field])
        
        assert len(result) == 1
        assert result[0]["id"] == "phone"
        assert result[0]["type"] == "tel"
    
    def test_multiple_fields(self, handler, dummy_rect):
        """Test conversion of multiple fields."""
        fields = [
            FormField(id="field1", name="Field 1", type="text", rect=dummy_rect),
            FormField(id="field2", name="Field 2", type="email", rect=dummy_rect),
            FormField(id="field3", name="Field 3", type="number", rect=dummy_rect),
        ]
        
        result = handler._convert_fields_to_dicts(fields)
        
        assert len(result) == 3
        assert result[0]["id"] == "field1"
        assert result[1]["id"] == "field2"
        assert result[2]["id"] == "field3"
    
    def test_none_values_excluded(self, handler, dummy_rect):
        """Test that only existing fields are included in conversion."""
        field = FormField(
            id="test",
            name="Test",
            type="text",
            rect=dummy_rect
        )
        
        result = handler._convert_fields_to_dicts([field])
        
        # Only id, name, type should be present (no min/max constraints)
        assert result[0]["id"] == "test"
        assert result[0]["name"] == "Test"
        assert result[0]["type"] == "text"
        assert "min" not in result[0]
        assert "max" not in result[0]
    
    def test_empty_options_excluded(self, handler, dummy_rect):
        """Test that empty options list is not included."""
        field = FormField(
            id="test",
            name="Test",
            type="select",
            rect=dummy_rect,
            options=[]
        )
        
        result = handler._convert_fields_to_dicts([field])
        
        # Empty list should not be included
        assert "options" not in result[0]
