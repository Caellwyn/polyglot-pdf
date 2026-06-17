import json

from backend.services.ai_context import build_form_context


def test_nested_help_block_rendered_in_si():
    """The legacy/full SI must render the canonical NESTED help block
    (help.instructions -> Note:, help.format_hint -> Format:), which real form-kit
    schemas use -- previously only the flat 'description' key was read, so the voice
    model got NO authored guidance on real forms (bd polyglot-pdf-jnjj.23)."""
    schema = {
        "form_metadata": {"title": "I-90"},
        "fields": [{
            "id": "p1_line1_aliennumber", "name": "A-Number", "type": "text",
            "help": {"instructions": "Your A-Number is a 7-9 digit number on your green card.",
                     "format_hint": "7-9 digits"},
        }],
    }
    si = build_form_context(schema, {}, "English")
    assert "Note: Your A-Number is a 7-9 digit number" in si
    assert "Format: 7-9 digits" in si


def test_flat_description_still_rendered_backward_compat():
    """A form using the FLAT 'description' key (demo-schema shape) still renders the
    Note: line -- the nested-help change must not regress it (jnjj.23 exit 3)."""
    schema = {
        "form_metadata": {"title": "Demo"},
        "fields": [{"id": "dob", "name": "DOB", "type": "date",
                    "format": "YYYY-MM-DD", "description": "Convert spoken dates."}],
    }
    si = build_form_context(schema, {}, "English")
    assert "Note: Convert spoken dates." in si
    assert "Format: YYYY-MM-DD" in si


def test_real_i90_section_si_carries_help_instructions():
    """Regression on the ACTUAL form-kits/i-90/schema.json (not a hand-rolled
    fixture): a built SI for a real I-90 section must contain its fields'
    help.instructions text. Guards against the deployed schema shape (or section
    extraction) silently dropping the nested help block -- the exact bug
    bd polyglot-pdf-jnjj.23 fixed (Codex PR #230)."""
    from pathlib import Path
    # backend/tests/unit/test_ai_context.py -> parents[3] is the repo root.
    repo_root = Path(__file__).resolve().parents[3]
    schema_path = repo_root / "form-kits" / "i-90" / "schema.json"
    if not schema_path.exists():
        import pytest
        pytest.skip("form-kits/i-90/schema.json not present in this checkout")
    full = json.loads(schema_path.read_text(encoding="utf-8"))
    # First section's fields (legacy/full-SI handshake sends one section's fields).
    sec_id = full["fields"][0].get("section_id")
    sec_fields = [f for f in full["fields"] if f.get("section_id") == sec_id]
    sub = {"form_metadata": full.get("form_metadata", {}), "fields": sec_fields}
    si = build_form_context(sub, {}, "English", section_number=1,
                            total_sections=8, section_label=sec_id)
    # Every field in this section carries help.instructions on the real I-90, so the
    # SI must show Note: lines, and at least one field's actual instruction text.
    assert "Note:" in si
    a_number = next((f for f in sec_fields
                     if (f.get("help") or {}).get("instructions")), None)
    assert a_number is not None, "expected a field with help.instructions in section 1"
    # A distinctive substring of that field's authored instructions appears in the SI.
    instr = a_number["help"]["instructions"]
    assert instr[:30] in si


def test_nested_help_instructions_preferred_over_flat_description():
    """When both nested help.instructions and a flat description exist, the nested
    (canonical) instructions win for the Note: line."""
    schema = {
        "form_metadata": {"title": "X"},
        "fields": [{"id": "f", "name": "F", "type": "text",
                    "description": "flat desc",
                    "help": {"instructions": "nested instructions"}}],
    }
    si = build_form_context(schema, {}, "English")
    assert "Note: nested instructions" in si
    assert "flat desc" not in si


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
