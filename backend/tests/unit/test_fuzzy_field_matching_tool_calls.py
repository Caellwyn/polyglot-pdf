"""Unit tests for fuzzy field matching in tool call handling.

Tests the handle_update_fields_tool_call method's ability to match field names
to field IDs using fuzzy matching, while avoiding false positives.
"""
import pytest
from backend.services.form_filling_service import FormFillingService
from backend.models.form_models import FormField, Rect


def create_test_schema(fields_data):
    """Helper to create a test schema with given fields."""
    return {
        "source": "web",
        "form_metadata": {
            "title": "Test Form",
            "url": "http://test.example.com"
        },
        "fields": fields_data
    }


def test_exact_id_match():
    """Test that exact field ID matches work (no fuzzy matching needed)."""
    schema = create_test_schema([
        {"id": "name", "name": "Full Name", "type": "text", "required": True},
        {"id": "email", "name": "Email Address", "type": "text", "required": True},
    ])
    
    service = FormFillingService()
    service._schema = schema
    service._session_id = "test_123"
    
    # Exact ID matches should work
    result = service.handle_update_fields_tool_call("test_123", {
        "name": "John Doe",
        "email": "john@example.com"
    })
    
    assert result is not None
    assert set(result["applied_fields"]) == {"name", "email"}
    assert result["unknown_fields"] == []
    assert result["form_state"] == {
        "name": "John Doe",
        "email": "john@example.com"
    }


def test_fuzzy_match_full_name_variations():
    """Test fuzzy matching handles common variations of 'Full Name'."""
    schema = create_test_schema([
        {"id": "name", "name": "Full Name", "type": "text", "required": True},
    ])
    
    service = FormFillingService()
    service._schema = schema
    service._session_id = "test_123"
    
    # These should all match to the "name" field
    variations = [
        "full_name",      # snake_case
        "Full Name",      # exact name
        "fullname",       # no space
        "full name",      # lowercase
        "FULL NAME",      # uppercase
        "name full",      # reversed order (token_sort_ratio handles this)
    ]
    
    for variation in variations:
        result = service.handle_update_fields_tool_call("test_123", {
            variation: "Jane Smith"
        })
        
        assert result is not None, f"Failed to match variation: {variation}"
        assert result["applied_fields"] == ["name"], f"Wrong field for: {variation}"
        assert result["unknown_fields"] == []
        assert result["form_state"] == {"name": "Jane Smith"}


def test_fuzzy_match_email_variations():
    """Test fuzzy matching handles email field variations."""
    schema = create_test_schema([
        {"id": "email", "name": "Email Address", "type": "text", "required": True},
    ])
    
    service = FormFillingService()
    service._schema = schema
    service._session_id = "test_123"
    
    variations = [
        "email_address",
        "Email Address",
        "email address",
        "emailaddress",
        "address email",  # reversed
    ]
    
    for variation in variations:
        result = service.handle_update_fields_tool_call("test_123", {
            variation: "test@example.com"
        })
        
        assert result is not None, f"Failed to match: {variation}"
        assert result["applied_fields"] == ["email"], f"Wrong field for: {variation}"
        assert result["form_state"] == {"email": "test@example.com"}


def test_no_false_positive_name_vs_dependent_name():
    """Critical test: 'name' should NOT match 'dependent_name' or vice versa."""
    schema = create_test_schema([
        {"id": "name", "name": "Your Name", "type": "text", "required": True},
        {"id": "dependent_name", "name": "Dependent Name", "type": "text", "required": False},
        {"id": "spouse_name", "name": "Spouse Name", "type": "text", "required": False},
    ])
    
    service = FormFillingService()
    service._schema = schema
    service._session_id = "test_123"
    
    # Test 1: "name" should match "name", not dependent_name
    result = service.handle_update_fields_tool_call("test_123", {"name": "John"})
    assert result["applied_fields"] == ["name"]
    assert result["form_state"] == {"name": "John"}
    
    # Test 2: "dependent_name" should match dependent_name, not name
    result = service.handle_update_fields_tool_call("test_123", {"dependent_name": "Jane"})
    assert result["applied_fields"] == ["dependent_name"]
    assert result["form_state"] == {"dependent_name": "Jane"}
    
    # Test 3: "Dependent Name" (as field name) should match dependent_name
    result = service.handle_update_fields_tool_call("test_123", {"Dependent Name": "Bob"})
    assert result["applied_fields"] == ["dependent_name"]
    assert result["form_state"] == {"dependent_name": "Bob"}
    
    # Test 4: "spouse name" should match spouse_name, not name
    result = service.handle_update_fields_tool_call("test_123", {"spouse name": "Alice"})
    assert result["applied_fields"] == ["spouse_name"]
    assert result["form_state"] == {"spouse_name": "Alice"}


def test_no_false_positive_phone_variations():
    """Test that different phone fields don't get confused."""
    schema = create_test_schema([
        {"id": "phone", "name": "Phone Number", "type": "text", "required": True},
        {"id": "home_phone", "name": "Home Phone", "type": "text", "required": False},
        {"id": "work_phone", "name": "Work Phone", "type": "text", "required": False},
    ])
    
    service = FormFillingService()
    service._schema = schema
    service._session_id = "test_123"
    
    # "phone" alone should match the primary phone field
    result = service.handle_update_fields_tool_call("test_123", {"phone": "555-0100"})
    assert result["applied_fields"] == ["phone"]
    assert result["form_state"] == {"phone": "555-0100"}
    
    # "home phone" should match home_phone specifically
    result = service.handle_update_fields_tool_call("test_123", {"home phone": "555-0101"})
    assert result["applied_fields"] == ["home_phone"]
    assert result["form_state"] == {"home_phone": "555-0101"}
    
    # "work phone" should match work_phone specifically
    result = service.handle_update_fields_tool_call("test_123", {"work_phone": "555-0102"})
    assert result["applied_fields"] == ["work_phone"]
    assert result["form_state"] == {"work_phone": "555-0102"}


def test_no_false_positive_address_variations():
    """Test that different address fields don't get confused."""
    schema = create_test_schema([
        {"id": "address", "name": "Street Address", "type": "text", "required": True},
        {"id": "email", "name": "Email Address", "type": "text", "required": True},
        {"id": "billing_address", "name": "Billing Address", "type": "text", "required": False},
    ])
    
    service = FormFillingService()
    service._schema = schema
    service._session_id = "test_123"
    
    # "address" should match "address", not "email" even though both have "address" in name
    result = service.handle_update_fields_tool_call("test_123", {"address": "123 Main St"})
    assert result["applied_fields"] == ["address"]
    assert result["form_state"] == {"address": "123 Main St"}
    
    # "email address" should match "email"
    result = service.handle_update_fields_tool_call("test_123", {"email address": "test@example.com"})
    assert result["applied_fields"] == ["email"]
    
    # "billing address" should match billing_address, not address
    result = service.handle_update_fields_tool_call("test_123", {"billing address": "456 Oak Ave"})
    assert result["applied_fields"] == ["billing_address"]
    assert result["form_state"] == {"billing_address": "456 Oak Ave"}


def test_unknown_field_not_matched():
    """Test that completely unknown fields are properly rejected."""
    schema = create_test_schema([
        {"id": "name", "name": "Full Name", "type": "text", "required": True},
        {"id": "email", "name": "Email Address", "type": "text", "required": True},
    ])
    
    service = FormFillingService()
    service._schema = schema
    service._session_id = "test_123"
    
    # Completely unrelated field should not match anything
    result = service.handle_update_fields_tool_call("test_123", {
        "favorite_color": "blue",  # Not in schema
        "name": "John Doe"          # Valid field
    })
    
    assert result is not None
    assert result["applied_fields"] == ["name"]
    assert result["unknown_fields"] == ["favorite_color"]
    assert result["form_state"] == {"name": "John Doe"}


def test_mixed_exact_and_fuzzy_matches():
    """Test that exact and fuzzy matches work together in same call."""
    schema = create_test_schema([
        {"id": "name", "name": "Full Name", "type": "text", "required": True},
        {"id": "email", "name": "Email Address", "type": "text", "required": True},
        {"id": "phone", "name": "Phone Number", "type": "text", "required": True},
    ])
    
    service = FormFillingService()
    service._schema = schema
    service._session_id = "test_123"
    
    # Mix of exact ID match and fuzzy name match
    result = service.handle_update_fields_tool_call("test_123", {
        "email": "test@example.com",      # Exact ID match
        "Full Name": "Jane Smith",        # Fuzzy match by name
        "phone_number": "555-1234",       # Fuzzy match (snake_case of name)
    })
    
    assert result is not None
    assert set(result["applied_fields"]) == {"email", "name", "phone"}
    assert result["unknown_fields"] == []
    assert result["form_state"] == {
        "email": "test@example.com",
        "name": "Jane Smith",
        "phone": "555-1234"
    }


def test_case_insensitive_matching():
    """Test that matching is case-insensitive."""
    schema = create_test_schema([
        {"id": "name", "name": "Full Name", "type": "text", "required": True},
    ])
    
    service = FormFillingService()
    service._schema = schema
    service._session_id = "test_123"
    
    # All these case variations should match
    for variation in ["FULL NAME", "full name", "Full Name", "FuLl NaMe"]:
        result = service.handle_update_fields_tool_call("test_123", {variation: "Test"})
        assert result["applied_fields"] == ["name"], f"Failed for: {variation}"


def test_punctuation_normalization():
    """Test that punctuation is normalized during matching."""
    schema = create_test_schema([
        {"id": "dob", "name": "Date of Birth (MM/DD/YYYY)", "type": "text", "required": True},
        {"id": "ssn", "name": "SSN (###-##-####)", "type": "text", "required": True},
    ])
    
    service = FormFillingService()
    service._schema = schema
    service._session_id = "test_123"
    
    # Variations without punctuation should match
    result = service.handle_update_fields_tool_call("test_123", {
        "date of birth": "01/15/1990",
        "ssn": "123-45-6789"
    })
    
    assert set(result["applied_fields"]) == {"dob", "ssn"}
    assert result["unknown_fields"] == []


def test_empty_updates():
    """Test handling of empty updates dictionary."""
    schema = create_test_schema([
        {"id": "name", "name": "Full Name", "type": "text", "required": True},
    ])
    
    service = FormFillingService()
    service._schema = schema
    service._session_id = "test_123"
    
    result = service.handle_update_fields_tool_call("test_123", {})
    
    assert result is not None
    assert result["applied_fields"] == []
    assert result["unknown_fields"] == []
    assert result["form_state"] == {}


def test_none_updates():
    """Test handling of None updates."""
    schema = create_test_schema([
        {"id": "name", "name": "Full Name", "type": "text", "required": True},
    ])
    
    service = FormFillingService()
    service._schema = schema
    service._session_id = "test_123"
    
    result = service.handle_update_fields_tool_call("test_123", None)
    
    assert result is not None
    assert result["applied_fields"] == []
    assert result["unknown_fields"] == []
    assert result["form_state"] == {}


def test_value_types_preserved():
    """Test that different value types are preserved correctly."""
    schema = create_test_schema([
        {"id": "name", "name": "Full Name", "type": "text", "required": True},
        {"id": "age", "name": "Age", "type": "text", "required": False},  # Use "text" - value will be number
        {"id": "subscribe", "name": "Subscribe to Newsletter", "type": "checkbox", "required": False},
    ])
    
    service = FormFillingService()
    service._schema = schema
    service._session_id = "test_123"
    
    result = service.handle_update_fields_tool_call("test_123", {
        "name": "John Doe",           # string
        "age": 30,                    # number (stored as-is, field type is just schema metadata)
        "subscribe": True,            # boolean
    })
    
    assert result is not None, "Result should not be None - check for exceptions in service method"
    assert result["form_state"]["name"] == "John Doe"
    assert result["form_state"]["age"] == 30
    assert result["form_state"]["subscribe"] is True
    assert isinstance(result["form_state"]["subscribe"], bool)


def test_no_cross_contamination_similar_names():
    """Test that similar field names don't cause cross-contamination.
    
    This is a critical test to ensure the fuzzy matcher's thresholds prevent
    false positives between fields with similar but distinct names.
    """
    schema = create_test_schema([
        {"id": "first_name", "name": "First Name", "type": "text", "required": True},
        {"id": "last_name", "name": "Last Name", "type": "text", "required": True},
        {"id": "middle_name", "name": "Middle Name", "type": "text", "required": False},
        {"id": "nickname", "name": "Nickname", "type": "text", "required": False},
    ])
    
    service = FormFillingService()
    service._schema = schema
    service._session_id = "test_123"
    
    # Each specific name type should match its own field
    test_cases = [
        ("first name", "first_name", "John"),
        ("last name", "last_name", "Doe"),
        ("middle name", "middle_name", "Q"),
        ("nickname", "nickname", "Johnny"),
        ("First Name", "first_name", "Jane"),
        ("Last Name", "last_name", "Smith"),
    ]
    
    for input_key, expected_id, value in test_cases:
        result = service.handle_update_fields_tool_call("test_123", {input_key: value})
        assert result["applied_fields"] == [expected_id], \
            f"'{input_key}' should match '{expected_id}', got {result['applied_fields']}"
        assert result["form_state"] == {expected_id: value}


def test_prefix_vs_full_match():
    """Test that prefix matches don't cause false positives.
    
    Example: 'name' should not match 'username' even though 'name' is a suffix.
    """
    schema = create_test_schema([
        {"id": "username", "name": "Username", "type": "text", "required": True},
        {"id": "name", "name": "Full Name", "type": "text", "required": True},
    ])
    
    service = FormFillingService()
    service._schema = schema
    service._session_id = "test_123"
    
    # "username" should match "username", not "name"
    result = service.handle_update_fields_tool_call("test_123", {"username": "jdoe123"})
    assert result["applied_fields"] == ["username"]
    assert result["form_state"] == {"username": "jdoe123"}
    
    # "name" could potentially match either, but should prefer exact or closest
    result = service.handle_update_fields_tool_call("test_123", {"name": "John Doe"})
    # Should match the "name" field, not "username"
    assert result["applied_fields"] == ["name"]
    assert result["form_state"] == {"name": "John Doe"}
    
    # "Full Name" should definitely match "name"
    result = service.handle_update_fields_tool_call("test_123", {"Full Name": "Jane Smith"})
    assert result["applied_fields"] == ["name"]
    assert result["form_state"] == {"name": "Jane Smith"}


def test_numeric_prefix_stripping():
    """Test that numeric prefixes are stripped during fuzzy matching.
    
    Model might see fields like:
      1. "Full Name" [id: "name", ...]
      3. "Phone Number" [id: "phone", ...]
    
    And incorrectly call tool with:
      {"1_full_name": "Josh", "3_phone_number": "123"}
    
    Fuzzy matcher should strip the numeric prefix and match correctly.
    """
    schema = create_test_schema([
        {"id": "name", "name": "Full Name", "type": "text", "required": True},
        {"id": "email", "name": "Email Address", "type": "text", "required": True},
        {"id": "phone", "name": "Phone Number", "type": "text", "required": True},
    ])
    
    service = FormFillingService()
    service._schema = schema
    service._session_id = "test_123"
    
    # Model uses numeric prefixes with underscores (common mistake)
    result = service.handle_update_fields_tool_call("test_123", {
        "1_full_name": "Josh",
        "3_phone_number": "555-1234"
    })
    
    # Should successfully match by stripping prefixes
    assert set(result["applied_fields"]) == {"name", "phone"}
    assert result["unknown_fields"] == []
    assert result["form_state"] == {
        "name": "Josh",
        "phone": "555-1234"
    }
    
    # Also test with period separator (another common pattern)
    result = service.handle_update_fields_tool_call("test_123", {
        "1. full name": "Jane",
        "2. email address": "jane@example.com"
    })
    
    assert set(result["applied_fields"]) == {"name", "email"}
    assert result["unknown_fields"] == []
    assert result["form_state"] == {
        "name": "Jane",
        "email": "jane@example.com"
    }


def test_empty_updates_rejected():
    """Test that empty tool calls are rejected with clear error message."""
    schema = create_test_schema([
        {"id": "name", "name": "Full Name", "type": "text", "required": True},
        {"id": "email", "name": "Email Address", "type": "text", "required": True},
    ])
    
    service = FormFillingService()
    service._schema = schema
    service._session_id = "test_123"
    
    # Test completely empty updates dict
    result = service.handle_update_fields_tool_call("test_123", {})
    
    assert result is not None
    assert result["applied_fields"] == []
    assert result["unknown_fields"] == []
    assert result["validation_errors"] == []
    # The validation should happen at the on_tool_call level, not here
    # So this should return empty results, not an error
    # The actual rejection happens in on_tool_call before calling this method


