import json

import pytest

from backend.config import Settings
from backend.services.ai_context import build_form_context


@pytest.fixture(autouse=True)
def _legacy_si_settings(monkeypatch):
    """Every test in this module exercises the LEGACY full-SI renderer (the
    section-reset path), which survives the continuous-DTI defaults flip
    (bd polyglot-pdf-7872) only as the measurement-harness baseline. Request it
    explicitly: patch the consuming module's get_settings (the global one is
    lru_cached) with a fresh legacy-mode Settings. CONTINUOUS_SESSION must be
    off too -- on its own it forces USE_DTI back on."""
    legacy = Settings(USE_DTI=False, CONTINUOUS_SESSION=False)
    monkeypatch.setattr("backend.services.ai_context.get_settings", lambda: legacy)


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


def test_help_format_hint_used_when_flat_format_is_null():
    """A field can carry a present-but-null flat 'format' (e.g. after a round-trip
    through the optional ValidationRules) alongside help.format_hint. The nested
    hint must still render -- a `"format" in field` guard would suppress it and the
    renderer would drop the null, leaving NO Format: line (Codex PR #230 round 2)."""
    schema = {
        "form_metadata": {"title": "X"},
        "fields": [{"id": "f", "name": "F", "type": "text",
                    "format": None,  # present but null
                    "help": {"format_hint": "7-9 digits"}}],
    }
    si = build_form_context(schema, {}, "English")
    assert "Format: 7-9 digits" in si


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

def test_legacy_si_renders_note_and_carries_convey_directive():
    """Two assertions with different strength (bd polyglot-pdf-bo4m):
    (1) WIRING -- the field's help.instructions is rendered into the SI as a
    Note: line (schema-dependent; would catch a regression of the jnjj.23
    nested-help read); (2) TEMPLATE -- the CONSTRAINTS directive telling the
    model to convey that Note while asking is present. The directive lives in
    the static SYSTEM_INSTRUCTION template, so assertion (2) alone is
    schema-independent by design -- it pins the template constant, not the
    help wiring; (1) is the wiring proof."""
    schema = {
        "form_metadata": {"title": "I-90"},
        "fields": [{
            "id": "p1_checkbox4", "name": "Has Your Name Legally Changed?",
            "type": "radio",
            "help": {"instructions": "Indicate if your name has legally changed "
                     "since your Permanent Resident Card was issued."},
        }],
    }
    si = build_form_context(schema, {}, "English")
    # The Note itself is rendered (jnjj.23) AND the directive to convey it exists.
    assert "Note: Indicate if your name has legally changed" in si
    assert "briefly convey that context in your own words WHILE asking" in si
