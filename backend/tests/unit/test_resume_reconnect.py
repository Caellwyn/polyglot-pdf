"""Tests for mid-section reconnect resume behavior (bd polyglot-pdf-vmxx).

A reconnect handshake with resume:true must:
  (a) use RESUME_INITIATING_MESSAGE (no greeting wording)
  (b) NOT use the greeting INITIATING_MESSAGE

A fresh handshake (resume absent or False) must:
  (c) still use the normal INITIATING_MESSAGE with greeting wording

Also verifies that the system instruction carries a RESUME override note
when is_reconnect=True, suppressing the greet directive in the base template.
"""
import pytest
from unittest.mock import AsyncMock, patch

from backend.config import Settings
from backend.services.form_filling_service import FormFillingService
from backend.services.ai_context import build_form_context


# ---------------------------------------------------------------------------
# Config sanity checks
# ---------------------------------------------------------------------------

def test_settings_define_resume_initiating_message():
    settings = Settings()
    assert hasattr(settings, "RESUME_INITIATING_MESSAGE"), (
        "Settings must define RESUME_INITIATING_MESSAGE"
    )
    assert isinstance(settings.RESUME_INITIATING_MESSAGE, str)
    assert settings.RESUME_INITIATING_MESSAGE.strip()


def test_resume_initiating_message_has_no_greeting():
    settings = Settings()
    msg = settings.RESUME_INITIATING_MESSAGE.lower()
    # Must not tell Gemini to greet warmly (the normal template says "greet user warmly")
    assert "greet user warmly" not in msg, (
        "RESUME_INITIATING_MESSAGE must not contain 'greet user warmly'"
    )
    # Must not re-introduce the section
    assert "state section" not in msg, (
        "RESUME_INITIATING_MESSAGE must not re-introduce the section"
    )
    # The word "greet" may appear in negation context ("do not greet") -- that is correct
    assert "do not greet" in msg or "not greet" in msg, (
        "RESUME_INITIATING_MESSAGE must explicitly instruct skipping the greeting"
    )


def test_resume_initiating_message_is_ascii_clean():
    settings = Settings()
    msg = settings.RESUME_INITIATING_MESSAGE
    assert all(ord(c) < 128 for c in msg), (
        "RESUME_INITIATING_MESSAGE contains non-ASCII characters (scar #6)"
    )


def test_initiating_message_has_NO_greeting():
    """The base template must NOT greet (bd polyglot-pdf-s1iex.6).

    This assertion INVERTED. Sol now introduces himself by name in the
    scripted intro clip, on every path where the disclaimer modal is shown,
    so a "greet user warmly" here produced a SECOND greeting seconds after
    the clip. The old test encoded the pre-clip product truth.

    The resume-vs-fresh DISTINCTION this file exists to protect is unchanged
    and still covered below: resume explicitly says "do not greet" and skips
    the section re-introduction, fresh states the section and asks field 1.
    """
    settings = Settings()
    assert "greet user warmly" not in settings.INITIATING_MESSAGE.lower(), (
        "INITIATING_MESSAGE must not greet -- the intro clip already did"
    )
    # It must still open the section and drive field 1; a template that lost
    # its job entirely would also pass the negative assertion above.
    assert "{next_field_hint}" in settings.INITIATING_MESSAGE
    assert "section name" in settings.INITIATING_MESSAGE.lower()


# ---------------------------------------------------------------------------
# send_initiating_message selects the right template
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fresh_connect_uses_the_base_template():
    """A session with _is_resume_session=False must use INITIATING_MESSAGE."""
    settings = Settings()
    service = FormFillingService(live_ai=AsyncMock(), settings=settings)
    service._is_resume_session = False

    captured = []

    async def _capture(msg):
        captured.append(msg)

    service._live_ai.send_client_content = _capture

    await service.send_initiating_message("English", "First Name")

    assert len(captured) == 1
    sent = captured[0]
    # Identify the template by what only IT says (bd polyglot-pdf-s1iex.6:
    # "greet" is gone from both templates now, so it can no longer be the
    # discriminator). The base template states the section; resume explicitly
    # refuses to.
    assert "section name" in sent.lower(), (
        "Fresh connect must use INITIATING_MESSAGE (states the section name)"
    )
    assert "do not greet" not in sent.lower(), (
        "Fresh connect must NOT use RESUME_INITIATING_MESSAGE"
    )


@pytest.mark.asyncio
async def test_resume_connect_uses_resume_template():
    """A session with _is_resume_session=True must use RESUME_INITIATING_MESSAGE."""
    settings = Settings()
    service = FormFillingService(live_ai=AsyncMock(), settings=settings)
    service._is_resume_session = True

    captured = []

    async def _capture(msg):
        captured.append(msg)

    service._live_ai.send_client_content = _capture

    await service.send_initiating_message("English", "First Name")

    assert len(captured) == 1
    sent = captured[0]
    # Must not tell Gemini to "greet user warmly" (the normal template phrase)
    assert "greet user warmly" not in sent.lower(), (
        "Resume connect must NOT use INITIATING_MESSAGE (must not say 'greet user warmly')"
    )
    # Must still ask for the next field
    assert "first name" in sent.lower() or "first" in sent.lower(), (
        "Resume message must still include the next-field hint"
    )


@pytest.mark.asyncio
async def test_resume_template_contains_skip_greeting_instruction():
    """The resume message must explicitly tell Gemini to skip the greeting."""
    settings = Settings()
    service = FormFillingService(live_ai=AsyncMock(), settings=settings)
    service._is_resume_session = True

    captured = []

    async def _capture(msg):
        captured.append(msg)

    service._live_ai.send_client_content = _capture

    await service.send_initiating_message("Spanish", "Last Name")

    sent = captured[0].lower()
    # The resume template should instruct skipping the greeting
    assert "do not greet" in sent or "skip" in sent or "not greet" in sent, (
        "Resume message must contain explicit skip-greeting instruction"
    )


# ---------------------------------------------------------------------------
# build_form_context adds resume override note when is_reconnect=True
# ---------------------------------------------------------------------------

_MINIMAL_SCHEMA = {
    "source": "web",
    "form_metadata": {"title": "Test Form"},
    "fields": [{"id": "f1", "name": "First Name", "type": "text"}],
}


def test_build_form_context_fresh_has_no_resume_override():
    """Fresh connect: system instruction must not carry the RESUME override."""
    result = build_form_context(_MINIMAL_SCHEMA, {}, "English", is_reconnect=False)
    assert "RESUME:" not in result


def test_build_form_context_resume_appends_override():
    """Resume connect: system instruction must carry the no-greet override."""
    result = build_form_context(_MINIMAL_SCHEMA, {}, "English", is_reconnect=True)
    assert "RESUME:" in result
    assert "do not greet" in result.lower() or "not greet" in result.lower()
