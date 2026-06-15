"""Idle-timeout configuration spec (bd polyglot-pdf-01y6).

This file once held four "idle timeout" tests that read as coverage but never
invoked the route's watchdog -- they constructed the idle_timeout payload and
called mock_ws.send_json/close (or mock_service.end_session) THEMSELVES, then
asserted the mock recorded the call the test had just made, or defined a LOCAL
watchdog_task and tested asyncio rather than our code. They would all stay green
if the real watchdog were deleted (the self-fulfilling-mock anti-pattern;
docs/standards/testing.md). They were removed under bd polyglot-pdf-01y6 (a
finding from the T2.2 WS-lifecycle audit, bd polyglot-pdf-uov.9).

The idle-watchdog behavior they pretended to cover is now GENUINELY specified by
backend/tests/integration/test_websocket_auth_lifecycle.py
::test_idle_watchdog_sends_message_then_closes_1000, which drives the REAL
_handle_fill_session watchdog with a controllable clock and is mutation-verified
(changing the route's close code 1000 -> 4999 fails it).

What remains here is the one real, non-self-fulfilling test: that the idle-timeout
threshold is a configured setting with the expected default. It exercises actual
production config, so it stays.
"""

from backend.config import get_settings


def test_idle_timeout_configuration():
    """WS_IDLE_TIMEOUT_SEC is a real int setting defaulting to 120 seconds.

    The watchdog reads this value (backend/routes/websocket_routes.py); pinning the
    default guards against an accidental change to the close-after-idle window.
    """
    settings = get_settings()

    assert hasattr(settings, "WS_IDLE_TIMEOUT_SEC")
    assert isinstance(settings.WS_IDLE_TIMEOUT_SEC, int)
    assert settings.WS_IDLE_TIMEOUT_SEC == 120  # Default 120 seconds
