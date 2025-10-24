"""
Unit tests for field_utils module.

Tests the pure utility functions for field schema processing,
fuzzy matching, and field name extraction.
"""
import pytest
from backend.services.field_utils import (
    build_fields_from_schema,
    get_available_spoken_names,
    find_similar_field_names,
)
from backend.models.form_models import FormField


class TestBuildFieldsFromSchema:
    """Tests for build_fields_from_schema function."""
    
    def test_empty_schema(self):
        """Should return empty list for empty schema."""
        schema = {}
        result = build_fields_from_schema(schema)
        assert result == []
    
    def test_schema_with_no_fields(self):
        """Should return empty list when fields key is missing."""
        schema = {"name": "Test Form"}
        result = build_fields_from_schema(schema)
        assert result == []
    
    def test_single_field(self):
        """Should build a single FormField correctly."""
        schema = {
            "fields": [
                {
                    "id": "first_name",
                    "name": "First Name",
                    "type": "text",
                    "value": "John"
                }
            ]
        }
        result = build_fields_from_schema(schema)
        
        assert len(result) == 1
        field = result[0]
        assert isinstance(field, FormField)
        assert field.id == "first_name"
        assert field.name == "First Name"
        assert field.spoken_name == "First Name"
        assert field.field_type == "text"
        assert field.type == "text"
        assert field.value == "John"
        assert field.page_index == 0
        # Verify dummy rect
        assert field.rect.x0 == 0
        assert field.rect.y0 == 0
        assert field.rect.x1 == 100
        assert field.rect.y1 == 20
    
    def test_multiple_fields(self):
        """Should build multiple FormFields correctly."""
        schema = {
            "fields": [
                {"id": "first_name", "name": "First Name", "type": "text"},
                {"id": "email", "name": "Email", "type": "email"},
                {"id": "phone", "name": "Phone", "type": "tel"},
            ]
        }
        result = build_fields_from_schema(schema)
        
        assert len(result) == 3
        assert result[0].id == "first_name"
        assert result[1].id == "email"
        assert result[2].id == "phone"
    
    def test_field_with_options(self):
        """Should handle fields with allowed_values/options."""
        schema = {
            "fields": [
                {
                    "id": "country",
                    "name": "Country",
                    "type": "select",
                    "allowed_values": ["USA", "Canada", "Mexico"]
                }
            ]
        }
        result = build_fields_from_schema(schema)
        
        assert len(result) == 1
        field = result[0]
        assert field.options == ["USA", "Canada", "Mexico"]
    
    def test_field_with_options_key(self):
        """Should handle fields using 'options' instead of 'allowed_values'."""
        schema = {
            "fields": [
                {
                    "id": "state",
                    "name": "State",
                    "type": "select",
                    "options": ["CA", "NY", "TX"]
                }
            ]
        }
        result = build_fields_from_schema(schema)
        
        assert len(result) == 1
        field = result[0]
        assert field.options == ["CA", "NY", "TX"]
    
    def test_field_defaults(self):
        """Should use default values for missing fields."""
        schema = {
            "fields": [
                {
                    "id": "minimal_field",
                    "name": "Minimal"
                }
            ]
        }
        result = build_fields_from_schema(schema)
        
        assert len(result) == 1
        field = result[0]
        assert field.field_type == "text"  # Default type
        assert field.type == "text"
        assert field.options == []
        assert field.page_index == 0
        assert field.value is None


class TestGetAvailableSpokenNames:
    """Tests for get_available_spoken_names function."""
    
    def test_none_schema(self):
        """Should return empty list for None schema."""
        result = get_available_spoken_names(None)
        assert result == []
    
    def test_empty_schema(self):
        """Should return empty list for empty schema."""
        result = get_available_spoken_names({})
        assert result == []
    
    def test_schema_with_no_fields(self):
        """Should return empty list when fields key is missing."""
        result = get_available_spoken_names({"name": "Test Form"})
        assert result == []
    
    def test_single_field_name(self):
        """Should extract single field name."""
        schema = {
            "fields": [
                {"id": "first_name", "name": "First Name", "type": "text"}
            ]
        }
        result = get_available_spoken_names(schema)
        assert result == ["First Name"]
    
    def test_multiple_field_names(self):
        """Should extract all field names in order."""
        schema = {
            "fields": [
                {"id": "first_name", "name": "First Name"},
                {"id": "last_name", "name": "Last Name"},
                {"id": "email", "name": "Email Address"},
            ]
        }
        result = get_available_spoken_names(schema)
        assert result == ["First Name", "Last Name", "Email Address"]
    
    def test_field_without_name(self):
        """Should skip fields without name attribute."""
        schema = {
            "fields": [
                {"id": "first_name", "name": "First Name"},
                {"id": "no_name"},  # Missing name
                {"id": "email", "name": "Email"},
            ]
        }
        result = get_available_spoken_names(schema)
        assert result == ["First Name", "Email"]
    
    def test_field_with_none_name(self):
        """Should skip fields with None as name."""
        schema = {
            "fields": [
                {"id": "first_name", "name": "First Name"},
                {"id": "null_name", "name": None},
                {"id": "email", "name": "Email"},
            ]
        }
        result = get_available_spoken_names(schema)
        assert result == ["First Name", "Email"]


class TestFindSimilarFieldNames:
    """Tests for find_similar_field_names function."""
    
    def test_empty_available_names(self):
        """Should return empty list for empty available names."""
        result = find_similar_field_names("phone", [])
        assert result == []
    
    def test_exact_match(self):
        """Should find exact matches."""
        available = ["Phone Number", "Email Address", "First Name"]
        result = find_similar_field_names("Phone Number", available)
        assert "Phone Number" in result
    
    def test_case_insensitive_match(self):
        """Should match case-insensitively."""
        available = ["Phone Number", "Email Address"]
        result = find_similar_field_names("phone number", available)
        assert "Phone Number" in result
    
    def test_partial_match(self):
        """Should find partial/fuzzy matches."""
        available = ["Phone Number", "Cell Phone", "Email Address", "First Name"]
        result = find_similar_field_names("phone", available)
        # Should return fields with "phone" in them
        assert any("Phone" in name for name in result)
    
    def test_max_suggestions_limit(self):
        """Should respect max_suggestions parameter."""
        available = ["Phone 1", "Phone 2", "Phone 3", "Phone 4", "Phone 5"]
        result = find_similar_field_names("phone", available, max_suggestions=2)
        assert len(result) <= 2
    
    def test_fuzzy_matching_quality(self):
        """Should use fuzzy matching with reasonable threshold."""
        available = ["Phone Number", "Cell Phone", "Email Address", "First Name"]
        # "Phone Number" should match itself and similar variations
        result = find_similar_field_names("Phone Number", available)
        assert len(result) > 0
        assert "Phone Number" in result
        
        # "Cell Phone" query should match "Cell Phone" closely
        result2 = find_similar_field_names("Cell Phone", available)
        assert "Cell Phone" in result2
    
    def test_no_low_quality_matches(self):
        """Should not return matches below 52% threshold."""
        available = ["Phone Number", "Email Address"]
        # Completely unrelated query should return few/no results
        result = find_similar_field_names("xyz123", available)
        # Allow empty or very few results (threshold filtering)
        assert len(result) <= 1
    
    def test_word_order_robustness(self):
        """Should handle different word orders."""
        available = ["Patient First Name", "First Name Patient", "Email"]
        result = find_similar_field_names("First Name", available)
        # Should match variations of "First Name"
        assert len(result) >= 1
    
    def test_fallback_without_rapidfuzz(self, monkeypatch):
        """Should work with simple fallback if rapidfuzz not available."""
        # Mock rapidfuzz to raise ImportError
        import sys
        
        def mock_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == 'rapidfuzz' or (fromlist and 'rapidfuzz' in str(fromlist)):
                raise ImportError("Mocked rapidfuzz unavailable")
            return __import__(name, globals, locals, fromlist, level)
        
        monkeypatch.setattr('builtins.__import__', mock_import)
        
        available = ["Phone Number", "Email Address"]
        result = find_similar_field_names("phone", available)
        
        # Fallback should still find substring matches
        assert "Phone Number" in result


class TestIntegration:
    """Integration tests combining multiple utilities."""
    
    def test_full_workflow(self):
        """Test complete workflow: schema -> fields -> names -> fuzzy match."""
        schema = {
            "fields": [
                {"id": "first_name", "name": "First Name", "type": "text"},
                {"id": "last_name", "name": "Last Name", "type": "text"},
                {"id": "phone", "name": "Phone Number", "type": "tel"},
                {"id": "email", "name": "Email Address", "type": "email"},
            ]
        }
        
        # Build fields
        fields = build_fields_from_schema(schema)
        assert len(fields) == 4
        
        # Extract names
        names = get_available_spoken_names(schema)
        assert len(names) == 4
        assert "Phone Number" in names
        
        # Find similar - use closer match
        similar = find_similar_field_names("Phone Number", names)
        assert "Phone Number" in similar
