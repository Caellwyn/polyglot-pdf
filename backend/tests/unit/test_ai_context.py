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


def _jit_settings():
    """A minimal settings stub with JIT enabled, mirroring the real templates."""
    from backend.config import Settings, get_settings
    # Build a real Settings then flip the flag, so the actual JIT/legacy templates
    # are used (not a hand-rolled string).
    real = get_settings()

    class _S:
        USE_JIT_SCHEMA = True
        JIT_SYSTEM_INSTRUCTION = real.JIT_SYSTEM_INSTRUCTION
        SYSTEM_INSTRUCTION = real.SYSTEM_INSTRUCTION
    return _S()


def test_jit_context_lists_real_section_not_one_field(monkeypatch):
    """JIT SI must list the whole section (from the handshake manifest) and count
    progress over the real section, not the synthesized one-field schema[fields]
    (bd polyglot-pdf-jnjj.9 gaps A/B/N).
    """
    import backend.services.ai_context as ai_context_mod
    monkeypatch.setattr(ai_context_mod, "get_settings", _jit_settings)

    # JIT-shaped schema as websocket_routes builds it: fields = [first_field only],
    # but manifest carries the FULL section + a previous section.
    schema = {
        "source": "web",
        "jit_mode": True,
        "form_metadata": {"title": "I-90 Test"},
        "fields": [
            {"id": "firstName", "name": "First Name", "spoken_name": "first name",
             "type": "text", "required": True},
        ],
        "manifest": {
            "current_section": {
                "section_id": "sec1", "section_label": "Names",
                "fields": [
                    {"field_id": "firstName", "spoken_name": "first name"},
                    {"field_id": "middleName", "spoken_name": "middle name"},
                    {"field_id": "lastName", "spoken_name": "last name"},
                ],
            },
            "previous_sections": [
                {"section_id": "sec0", "section_label": "Intro",
                 "fields": [{"field_id": "alienNumber", "spoken_name": "alien number"}]},
            ],
        },
    }
    # firstName already filled -> progress should be 1/3, and {next_field_schema}
    # should target the first UNFILLED field (middleName), which the handshake
    # would have sent as fields[0]; here fields[0] is firstName, so we assert the
    # section/progress behavior (the next-field SELECTION is the frontend's job and
    # tested there). current_values marks firstName filled.
    result = build_form_context(schema, {"firstName": "Alice"}, "English")

    # Manifest text lists ALL section fields, not just the first.
    assert "first name" in result
    assert "middle name" in result
    assert "last name" in result
    # Cross-section recall block is populated from previous_sections.
    assert "alien number" in result
    # Progress counts the real section (3 fields, 1 filled), not "1/1".
    assert "1/3" in result
    # Real form title, not the literal "Form".
    assert "I-90 Test" in result


def test_jit_context_empty_section_reports_zero_not_one(monkeypatch):
    """An empty section manifest must read 0/0, not fall back to the one-field
    schema["fields"] "x/1" symptom (fresh-eyes finding on A2; gap N edge case).
    """
    import backend.services.ai_context as ai_context_mod
    monkeypatch.setattr(ai_context_mod, "get_settings", _jit_settings)

    schema = {
        "source": "web",
        "jit_mode": True,
        "form_metadata": {"title": "Empty Section Form"},
        "fields": [
            {"id": "placeholder", "name": "P", "spoken_name": "p", "type": "text"},
        ],
        "manifest": {
            "current_section": {"section_id": "s", "section_label": "Empty", "fields": []},
            "previous_sections": [],
        },
    }
    result = build_form_context(schema, {}, "English")

    # Manifest present but section empty -> 0/0, NOT the "x/1" fallback.
    assert "0/0" in result
    assert "0/1" not in result
