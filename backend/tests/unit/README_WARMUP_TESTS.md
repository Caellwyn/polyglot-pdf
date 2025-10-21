# Warmup & Pre-Filled Form Tests

## Test File
`test_warmup_and_prefilled.py`

## Test Coverage

### ✅ All 17 Tests Passing

#### 1. Warmup System Instruction (2 tests)
- `test_warmup_instruction_is_minimal` - Verifies warmup instruction is brief (<200 chars)
- `test_warmup_instruction_mentions_waiting` - Verifies AI told to wait for details

#### 2. Pre-Filled Form Context (5 tests)
- `test_upgrade_context_with_empty_form` - All fields show as `(empty)`
- `test_upgrade_context_with_prefilled_fields` - Pre-filled fields show `(ALREADY FILLED: 'value')`
- `test_upgrade_context_with_all_filled` - All fields marked as filled
- `test_upgrade_context_with_required_and_optional` - Shows REQUIRED vs optional labels
- `test_upgrade_context_field_ordering` - Fields maintain order from schema

#### 3. Token Optimization (2 tests)
- `test_initial_message_without_formatted_status` - Works with empty `formatted_status`
- `test_initial_message_formatted_status_optional` - Parameter is optional (backward compat)

#### 4. FormFillingService Warmup (3 tests)
- `test_start_session_warmup_mode` - Uses minimal context when `is_warmup=True`
- `test_start_session_normal_mode` - Uses full context when `is_warmup=False`
- `test_upgrade_session` - Sends upgrade context to Gemini with pre-filled annotations

#### 5. Metadata Status Annotations (3 tests)
- `test_metadata_shows_empty_status` - Empty fields show `(empty)` status
- `test_metadata_shows_filled_status` - Pre-filled fields show `(FILLED: 'value')` status
- `test_metadata_no_current_value_field` - Metadata doesn't include `current_value` (stateless)

#### 6. Stateless Architecture (2 tests)
- `test_service_does_not_cache_current_values` - Service doesn't store values
- `test_update_schema_does_not_store_values` - Schema updated but values not stored

## Test Results
```
============================= 17 passed in X.XXs =============================
```

## What Was Tested

### Components
1. **AI Context Module** (`backend/services/ai_context.py`):
   - `build_warmup_system_instruction()`
   - `build_form_context_for_upgrade()`
   - `build_initial_message()`

2. **Form Filling Service** (`backend/services/form_filling_service.py`):
   - `start_session()` with warmup parameter
   - `upgrade_session()`
   - `update_schema()`
   - Metadata building with status annotations

### Key Behaviors Verified

✅ **Warmup Mode**:
- Minimal system instruction (<200 chars)
- Brief initial message
- Fast connection establishment

✅ **Pre-Filled Forms**:
- Detects filled vs unfilled fields
- Shows values with `(ALREADY FILLED: 'value')` annotation
- Counts filled fields for AI context
- Tells AI to skip already-filled fields

✅ **Token Optimization**:
- No `formatted_status` redundancy
- `status` field in metadata instead of `current_value`
- Backward compatibility with optional parameter

✅ **Stateless Architecture**:
- Backend doesn't cache field values
- `current_values` passed through only
- Client remains source of truth

## Running Tests

```bash
# Run all warmup tests
pytest backend/tests/unit/test_warmup_and_prefilled.py -v

# Run specific test class
pytest backend/tests/unit/test_warmup_and_prefilled.py::TestWarmupSystemInstruction -v

# Run with coverage
pytest backend/tests/unit/test_warmup_and_prefilled.py --cov=backend.services
```

## Test Fixtures

### `mock_settings`
Mock Settings object with:
- `SYSTEM_INSTRUCTIONS`: Normal instruction text
- `INITIAL_MESSAGE_TEMPLATES`: String template (not dict)
- `TOOL_DECLARATIONS`: Empty list

### `sample_schema`
Standard web form schema with:
- 2-3 text fields
- Required/optional variations
- Valid field types (text, checkbox, radio)

## Edge Cases Covered

1. **Empty form** - No pre-filled values
2. **Partially filled** - Some fields filled, others empty
3. **Fully filled** - All fields have values
4. **Mixed required/optional** - Tests labeling
5. **Field ordering** - Maintains schema order
6. **No AI adapter** - Service works without live_ai (unit testing)

## Integration with Existing Tests

These tests complement:
- `test_ai_context.py` - Basic AI context building
- `test_form_filling_service_ephemeral.py` - Web form service tests
- `test_websocket_fill_web.py` - WebSocket endpoint tests

No conflicts - all existing tests still pass.
