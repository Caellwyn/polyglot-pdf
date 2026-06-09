"""Spec for send_recovery_prompt (bd polyglot-pdf-zy3 / epic wpw, WS-C1).

The activity watchdog escalates a stalled conversation through three recovery
levels (1 = re-ask the current field, 2 = "are you still there?", 3 = farewell
before close). Each level maps to a RECOVERY_PROMPT_LEVEL_* script on Settings
that Gemini reads aloud. Those settings were dropped from backend/config.py in
commit 7a30ad4, so every recovery level raised AttributeError -- caught by
websocket_routes and turned into a recovery_prompt_failed message the frontend
silently drops. The user heard nothing (bd polyglot-pdf-zy3).

These tests use a REAL Settings() on purpose: the zy3 failure was invisible to
any test that mocked settings.
"""
import pytest
from unittest.mock import AsyncMock

from backend.config import Settings
from backend.services.form_filling_service import FormFillingService


def test_settings_define_all_three_recovery_prompts():
    settings = Settings()
    for level in (1, 2, 3):
        prompt = getattr(settings, f"RECOVERY_PROMPT_LEVEL_{level}")
        assert isinstance(prompt, str) and prompt.strip(), (
            f"RECOVERY_PROMPT_LEVEL_{level} must be a non-empty script"
        )


def test_recovery_prompts_are_ascii_clean():
    # The scripts are spoken aloud and flow through code paths that can reach
    # stdout on Windows (cp1252) -- ASCII-only per CLAUDE.md scar #6.
    settings = Settings()
    for level in (1, 2, 3):
        prompt = getattr(settings, f"RECOVERY_PROMPT_LEVEL_{level}")
        prompt.encode("ascii")


@pytest.mark.asyncio
@pytest.mark.parametrize("level", [1, 2, 3])
async def test_send_recovery_prompt_delivers_the_configured_script(level):
    """Each watchdog level must deliver its configured script to the send path.

    With the settings missing, this raised AttributeError before any send --
    the red-first repro for zy3.
    """
    settings = Settings()
    service = FormFillingService(live_ai=AsyncMock(), settings=settings)
    service.send_context_hint = AsyncMock()

    await service.send_recovery_prompt(level)

    expected = getattr(settings, f"RECOVERY_PROMPT_LEVEL_{level}")
    service.send_context_hint.assert_awaited_once_with(expected)


@pytest.mark.asyncio
async def test_send_recovery_prompt_invalid_level_is_a_noop():
    service = FormFillingService(live_ai=AsyncMock(), settings=Settings())
    service.send_context_hint = AsyncMock()

    await service.send_recovery_prompt(99)

    service.send_context_hint.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_recovery_prompt_without_live_ai_is_a_noop():
    service = FormFillingService(live_ai=None, settings=Settings())
    service.send_context_hint = AsyncMock()

    await service.send_recovery_prompt(1)

    service.send_context_hint.assert_not_awaited()
