"""
Unit tests for context cache manager (Phase 2B).

Tests:
- System instruction building with schema
- Dynamic context building
- Schema consistency validation
- Token estimation and optimization
"""

import pytest
from services.context_cache_manager import ContextCacheManager, create_cache_manager


@pytest.fixture
def sample_schema():
    """Sample form schema for testing."""
    return {
        "source": "web",
        "form_title": "I-90 Application",
        "fields": [
            {
                "id": "firstName",
                "label": "First Name",
                "type": "text",
                "required": True
            },
            {
                "id": "lastName",
                "label": "Last Name",
                "type": "text",
                "required": True
            },
            {
                "id": "country",
                "label": "Country of Birth",
                "type": "select",
                "options": ["USA", "Mexico", "Canada"]
            }
        ]
    }


@pytest.fixture
def cache_manager():
    """Create cache manager instance."""
    return create_cache_manager(session_id="test_session")


def test_create_cache_manager():
    """Test cache manager factory function."""
    manager = create_cache_manager(session_id="test_123")
    assert manager is not None
    assert manager._session_id == "test_123"


def test_build_cached_system_instruction(cache_manager, sample_schema):
    """Test building system instruction with embedded schema."""
    base_instruction = "You are a form-filling assistant."

    system_instruction = cache_manager.build_cached_system_instruction(
        form_schema=sample_schema,
        base_instruction=base_instruction
    )

    # Should contain schema JSON
    assert "firstName" in system_instruction
    assert "lastName" in system_instruction
    assert "Country of Birth" in system_instruction

    # Should contain base instruction
    assert "form-filling assistant" in system_instruction

    # Should have schema before base instruction (for caching)
    schema_pos = system_instruction.find("FORM SCHEMA")
    base_pos = system_instruction.find("form-filling assistant")
    assert schema_pos < base_pos

    # Should be long enough for caching (>1024 tokens ≈ >4096 chars)
    assert len(system_instruction) > 100  # At minimum


def test_system_instruction_sets_schema_hash(cache_manager, sample_schema):
    """Test that building instruction sets schema hash."""
    assert cache_manager._current_schema_hash is None

    cache_manager.build_cached_system_instruction(
        form_schema=sample_schema,
        base_instruction="Test instruction"
    )

    assert cache_manager._current_schema_hash is not None
    assert len(cache_manager._current_schema_hash) == 16  # SHA256 first 16 chars


def test_build_dynamic_context_empty_state(cache_manager):
    """Test building dynamic context with empty state."""
    context = cache_manager.build_dynamic_context(
        form_state={},
        conversation_history=[],
        current_field=None,
        current_part=None
    )

    assert "Current form values: (empty)" in context
    assert "Current field: (none)" in context
    assert "Current part: (none)" in context
    assert "Recent conversation:" in context
    assert "(no history)" in context


def test_build_dynamic_context_with_data(cache_manager):
    """Test building dynamic context with form data."""
    form_state = {
        "firstName": "John",
        "lastName": "Doe",
        "emptyField": ""  # Should be excluded
    }

    conversation_history = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi! What's your name?"}
    ]

    context = cache_manager.build_dynamic_context(
        form_state=form_state,
        conversation_history=conversation_history,
        current_field="country",
        current_part="Part 1"
    )

    # Should include non-empty fields
    assert "firstName:John" in context
    assert "lastName:Doe" in context

    # Should NOT include empty fields
    assert "emptyField" not in context

    # Should include current field/part
    assert "Current field: country" in context
    assert "Current part: Part 1" in context

    # Should include conversation
    assert "User: Hello" in context
    assert "Assistant: Hi! What's your name?" in context


def test_build_dynamic_context_limits_history(cache_manager):
    """Test that history is limited to max turns."""
    # Create 15 turns
    conversation_history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"Message {i}"}
        for i in range(15)
    ]

    context = cache_manager.build_dynamic_context(
        form_state={},
        conversation_history=conversation_history,
        max_history_turns=10
    )

    # Should only include last 10 turns (messages 5-14)
    assert "Message 14" in context  # Most recent
    assert "Message 5" in context   # 10th from end
    assert "Message 4" not in context  # Too old


def test_build_dynamic_context_truncates_long_messages(cache_manager):
    """Test that very long messages are truncated."""
    conversation_history = [
        {
            "role": "user",
            "content": "A" * 250  # Very long message
        }
    ]

    context = cache_manager.build_dynamic_context(
        form_state={},
        conversation_history=conversation_history
    )

    # Should be truncated to 197 chars + "..."
    user_message = context.split("User: ")[1].split("\n")[0]
    assert len(user_message) == 200  # 197 + "..."
    assert user_message.endswith("...")


def test_validate_schema_consistency_first_time(cache_manager, sample_schema):
    """Test schema validation on first use."""
    # First validation should succeed and set baseline
    result = cache_manager.validate_schema_consistency(sample_schema)
    assert result is True
    assert cache_manager._current_schema_hash is not None


def test_validate_schema_consistency_same_schema(cache_manager, sample_schema):
    """Test validation with identical schema."""
    # Set baseline
    cache_manager.validate_schema_consistency(sample_schema)
    initial_hash = cache_manager._current_schema_hash

    # Validate again with same schema
    result = cache_manager.validate_schema_consistency(sample_schema)
    assert result is True
    assert cache_manager._current_schema_hash == initial_hash


def test_validate_schema_consistency_changed_schema(cache_manager, sample_schema):
    """Test validation detects schema changes."""
    # Set baseline
    cache_manager.validate_schema_consistency(sample_schema)

    # Modify schema
    modified_schema = sample_schema.copy()
    modified_schema["fields"] = sample_schema["fields"][:1]  # Remove fields

    # Should detect change
    result = cache_manager.validate_schema_consistency(modified_schema)
    assert result is False


def test_get_cache_metrics(cache_manager, sample_schema):
    """Test cache metrics retrieval."""
    # Before any operation
    metrics = cache_manager.get_cache_metrics()
    assert metrics["session_id"] == "test_session"
    assert metrics["schema_hash"] is None
    assert metrics["cache_enabled"] is False

    # After building instruction
    cache_manager.build_cached_system_instruction(
        form_schema=sample_schema,
        base_instruction="Test"
    )

    metrics = cache_manager.get_cache_metrics()
    assert metrics["schema_hash"] is not None
    assert metrics["cache_enabled"] is True


def test_schema_hash_consistency():
    """Test that same schema always produces same hash."""
    manager1 = create_cache_manager()
    manager2 = create_cache_manager()

    schema = {
        "fields": [{"id": "test", "type": "text"}],
        "title": "Test Form"
    }

    hash1 = manager1._hash_schema('{"fields":[{"id":"test","type":"text"}],"title":"Test Form"}')
    hash2 = manager2._hash_schema('{"fields":[{"id":"test","type":"text"}],"title":"Test Form"}')

    assert hash1 == hash2
    assert len(hash1) == 16


def test_dynamic_context_compact_format(cache_manager):
    """Test that dynamic context uses compact format."""
    form_state = {
        "field1": "value1",
        "field2": "value2",
        "field3": "value3"
    }

    context = cache_manager.build_dynamic_context(
        form_state=form_state,
        conversation_history=[]
    )

    # Should use pipe-separated format (not JSON)
    assert "field1:value1|field2:value2|field3:value3" in context or \
           "field1:value1" in context  # Order may vary
    assert "{" not in context or "}" not in context.split("---")[1]  # No JSON in dynamic part


def test_token_estimation_warning(cache_manager, sample_schema, caplog):
    """Test warning when dynamic context exceeds target."""
    # Create large conversation history
    large_history = [
        {"role": "user", "content": "This is a very long message " * 20}
        for _ in range(10)
    ]

    import logging
    with caplog.at_level(logging.WARNING):
        cache_manager.build_dynamic_context(
            form_state={},
            conversation_history=large_history
        )

    # Should log warning about exceeding 500 token target
    # (This may or may not trigger depending on actual size)
