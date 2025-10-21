"""
Manual test script for empty tool call validation.

This script demonstrates what happens when Gemini sends an empty update_form_fields call.
Run this to verify the validation works as expected.
"""
import asyncio
from unittest.mock import Mock, AsyncMock
from backend.services.form_filling_service import FormFillingService


def create_test_schema():
    """Create a simple test schema."""
    return {
        "source": "web",
        "form_metadata": {
            "title": "Adult Intake Form",
            "url": "http://test.example.com"
        },
        "fields": [
            {"id": "firstName", "name": "First Name", "type": "text", "required": True},
            {"id": "lastName", "name": "Last Name", "type": "text", "required": True},
            {"id": "email", "name": "Email Address", "type": "email", "required": True},
        ]
    }


async def test_empty_tool_call():
    """Test what happens when Gemini calls update_form_fields with empty updates."""
    print("\n" + "="*80)
    print("TESTING EMPTY TOOL CALL VALIDATION")
    print("="*80 + "\n")
    
    # Create service
    service = FormFillingService()
    service._schema = create_test_schema()
    service._session_id = "test_123"
    service._websocket = Mock()
    service._websocket.send_json = AsyncMock()
    
    # Simulate Gemini calling update_form_fields with empty updates
    print("Scenario 1: Empty dict {}")
    print("-" * 80)
    
    # This simulates the normalized_updates being empty after parsing
    result = service.handle_update_fields_tool_call("test_123", {})
    
    print("Result from handle_update_fields_tool_call:")
    print(f"  - Applied fields: {result['applied_fields']}")
    print(f"  - Unknown fields: {result['unknown_fields']}")
    print(f"  - Validation errors: {result['validation_errors']}")
    print(f"  - Form state: {result['form_state']}")
    print()
    
    # Now test the actual on_tool_call handler behavior
    # (The validation happens before calling handle_update_fields_tool_call)
    print("\nScenario 2: Non-empty updates (control)")
    print("-" * 80)
    
    result = service.handle_update_fields_tool_call("test_123", {
        "firstName": "John",
        "lastName": "Doe"
    })
    
    print("Result from handle_update_fields_tool_call:")
    print(f"  - Applied fields: {result['applied_fields']}")
    print(f"  - Unknown fields: {result['unknown_fields']}")
    print(f"  - Validation errors: {result['validation_errors']}")
    print(f"  - Form state: {result['form_state']}")
    print()
    
    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80)
    print("\nExpected behavior:")
    print("- Scenario 1: Empty updates should be caught by on_tool_call validation")
    print("              (returns error before calling handle_update_fields_tool_call)")
    print("- Scenario 2: Valid updates should be processed normally")
    print()


if __name__ == "__main__":
    asyncio.run(test_empty_tool_call())
