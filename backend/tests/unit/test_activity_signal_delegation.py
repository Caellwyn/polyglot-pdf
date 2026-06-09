"""
Unit tests for FormFillingService.send_activity_start / send_activity_end.

Regression coverage for polyglot-pdf-akn: send_activity_end was MISSING from
FormFillingService while websocket_routes.py (the /ws/fill handler) calls
service.send_activity_end() on every vad_activity_end message -- sent after the
disclaimer accept AND after every push-to-talk release. The missing passthrough
raised AttributeError, propagated out of the WebSocket receive loop, crashed the
ASGI handler, and closed the socket; the frontend auto-reconnected and the next
PTT release crashed it again (reset-on-every-turn loop).

These tests guard the WebSocket-to-service contract that regressed: both
activity methods must EXIST on FormFillingService and DELEGATE to the
AudioHandler (mirroring each other). They would fail if either passthrough is
removed or renamed again. They also assert that EVERY service method the route
handler invokes is actually defined on FormFillingService, so the whole class of
"route calls a method the service never grew" bug is caught, not just this one
instance.
"""
import inspect

import pytest
from unittest.mock import AsyncMock

from backend.services.form_filling_service import FormFillingService


def _service_with_mock_audio_handler():
    """Build a service whose AudioHandler is an AsyncMock so we can assert the
    delegation happened (and that the methods are awaited, not sync-called)."""
    service = FormFillingService()
    service._audio_handler = AsyncMock()
    return service


@pytest.mark.asyncio
async def test_send_activity_end_delegates_to_audio_handler():
    """The method that regressed (akn): must exist AND delegate to AudioHandler."""
    service = _service_with_mock_audio_handler()

    await service.send_activity_end()

    service._audio_handler.send_activity_end.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_send_activity_start_delegates_to_audio_handler():
    """The sibling method send_activity_end is modeled on -- guard it too."""
    service = _service_with_mock_audio_handler()

    await service.send_activity_start()

    service._audio_handler.send_activity_start.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_activity_signals_are_noops_without_audio_handler():
    """Both signals must null-guard the AudioHandler (no handler -> no raise)."""
    service = FormFillingService()
    service._audio_handler = None

    # Neither should raise even when the handler is absent.
    await service.send_activity_start()
    await service.send_activity_end()


def test_websocket_route_only_calls_methods_the_service_defines():
    """Catch the whole class of bug akn was an instance of: a /ws/fill handler
    that calls service.<method>() the service never grew. Parse the route module
    for every `service.<name>(` call site and assert each resolves on
    FormFillingService."""
    import re
    from backend.routes import websocket_routes

    source = inspect.getsource(websocket_routes)
    called = set(re.findall(r"\bservice\.([a-zA-Z_][a-zA-Z0-9_]*)\(", source))
    # build_form_context_message is called in the route too; it is a real method.
    missing = sorted(
        name for name in called if not hasattr(FormFillingService, name)
    )
    assert not missing, (
        "websocket_routes.py calls service methods that do not exist on "
        f"FormFillingService: {missing}. This is the akn-class bug (a missing "
        "passthrough crashes the WS receive loop)."
    )
    # Sanity: the method this regression is about must be in the call set.
    assert "send_activity_end" in called


def test_section_switch_surface_is_wired_route_to_service():
    """Guard the section-switch route<->service surface the multi-section voice
    scenario (bd polyglot-pdf-8k8 / epic wpw WS-A) depends on -- the akn-class bug
    applied to switching. The /ws/fill handler dispatches the manual_section_switch
    and section_info_response branches into the service; if the method those
    branches call is ever renamed without updating the route (or vice versa), a
    section switch crashes the receive loop mid-form. Pin the contract by NAME so a
    rename is caught here, not only live."""
    import re
    from backend.routes import websocket_routes

    source = inspect.getsource(websocket_routes)

    # The backend-side switch entry point the route invokes for both the manual
    # switch and the AI-initiated section_info_response path must exist.
    assert hasattr(FormFillingService, "switch_to_section"), (
        "FormFillingService lost switch_to_section -- the manual_section_switch "
        "route branch and the AI switch_section path both call it; a section "
        "switch would crash the WS loop (akn-class)."
    )

    # The route must still handle the section-switch message types the frontend
    # sends. These string literals are the wire contract; their disappearance means
    # the FE can request a switch the backend silently ignores.
    for mtype in ("manual_section_switch", "section_info_response"):
        assert mtype in source, (
            f"websocket_routes.py no longer handles the '{mtype}' message -- the "
            "section-switch wire contract regressed."
        )
