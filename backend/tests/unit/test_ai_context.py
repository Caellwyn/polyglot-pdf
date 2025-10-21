import json

from backend.services.ai_context import build_form_context


def test_build_form_context_basic():
    """Test that build_form_context generates system instruction without JSON quote issues."""
    schema = {
        'form_metadata': {'title': 'Test Form'},
        'fields': [
            {'id': 'first_name', 'name': 'First Name', 'type': 'text', 'required': True},
            {'id': 'email', 'name': 'Email', 'type': 'email', 'required': False}
        ]
    }
    
    result = build_form_context(schema, {}, 'English')
    
    assert isinstance(result, str)
    assert 'Test Form' in result
    assert 'ID: first_name' in result
    assert 'ID: email' in result
    # Verify no JSON escaped quotes
    assert '\\"' not in result
    

def test_build_form_context_with_special_field_ids():
    """Test that field IDs with special characters (brackets) are not escaped."""
    schema = {
        'form_metadata': {'title': 'Application'},
        'fields': [
            {'id': 'reason[]', 'name': 'Reason', 'type': 'select', 'required': False, 
             'options': ['Option A', 'Option B']},
            {'id': 'items[0][name]', 'name': 'Item Name', 'type': 'text', 'required': False}
        ]
    }
    
    result = build_form_context(schema, {}, 'English')
    
    # Verify field IDs appear unquoted
    assert 'ID: reason[]' in result
    assert 'ID: items[0][name]' in result
    # Verify no JSON escaped quotes
    assert '\\"reason[]' not in result
    assert '"reason[]"' not in result


def test_build_form_context_with_current_values():
    """Test that current values are properly included."""
    schema = {
        'form_metadata': {'title': 'Form'},
        'fields': [
            {'id': 'name', 'name': 'Name', 'type': 'text', 'required': True},
            {'id': 'age', 'name': 'Age', 'type': 'number', 'required': False}
        ]
    }
    current_values = {'name': 'John Doe'}
    
    result = build_form_context(schema, current_values, 'English')
    
    assert 'Filled: True' in result
    assert 'Current: John Doe' in result
    assert 'Filled: False' in result  # age should be unfilled


def test_build_form_context_with_many_options():
    """Test that fields with many options are truncated properly."""
    schema = {
        'form_metadata': {'title': 'Form'},
        'fields': [
            {'id': 'country', 'name': 'Country', 'type': 'select', 'required': True,
             'options': ['USA', 'Canada', 'Mexico', 'UK', 'France', 'Germany', 'Spain', 'Italy']}
        ]
    }
    
    result = build_form_context(schema, {}, 'English')
    
    # Should show first 3 and total count
    assert 'USA, Canada, Mexico, ... (8 total)' in result


def test_build_form_context_with_few_options():
    """Test that fields with few options show all options."""
    schema = {
        'form_metadata': {'title': 'Form'},
        'fields': [
            {'id': 'choice', 'name': 'Choice', 'type': 'select', 'required': False,
             'options': ['Yes', 'No', 'Maybe']}
        ]
    }
    
    result = build_form_context(schema, {}, 'English')
    
    # Should show all 3 options
    assert 'Options: [Yes, No, Maybe]' in result
    assert '...' not in result or '(3 total)' not in result
