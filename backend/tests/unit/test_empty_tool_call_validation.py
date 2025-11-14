"""Unit tests for FormFillingService.handle_update_fields_tool_call."""

from __future__ import annotations

from backend.services.form_filling_service import FormFillingService


def build_service(fields):
    service = FormFillingService()
    service._schema = {"fields": fields}
    service._session_id = "test_session"
    return service


def test_empty_updates_dict_rejected():
    service = build_service([
        {"id": "name", "name": "Full Name", "type": "text", "required": True},
        {"id": "email", "name": "Email", "type": "text", "required": True},
    ])

    result = service.handle_update_fields_tool_call("test_session", {})

    assert result is not None
    assert result["applied_fields"] == []
    assert result["unknown_fields"] == []


def test_empty_updates_from_gemini_format():
    service = build_service([
        {"id": "firstName", "name": "First Name", "type": "text", "required": True},
    ])

    result = service.handle_update_fields_tool_call("test_session", {})

    assert result is not None
    assert result["applied_fields"] == []


def test_non_empty_updates_accepted():
    service = build_service([
        {"id": "name", "name": "Full Name", "type": "text", "required": True},
    ])

    result = service.handle_update_fields_tool_call("test_session", {"name": "John Doe"})

    assert result is not None
    assert result["applied_fields"] == ["name"]
    assert result["unknown_fields"] == []
    assert result["form_state"] == {"name": "John Doe"}


def test_empty_string_values_accepted():
    service = build_service([
        {"id": "middleName", "name": "Middle Name", "type": "text", "required": False},
    ])

    result = service.handle_update_fields_tool_call("test_session", {"middleName": ""})

    assert result is not None
    assert result["applied_fields"] == ["middleName"]
    assert result["form_state"] == {"middleName": ""}
