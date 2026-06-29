"""B5 (bd polyglot-pdf-jnjj.17): FormFillingService.handle_validation_boundary --
verdict -> live-model steering injection, with the override escape hatch and the
max-resteer bound (validation-delegation.md contracts 1/3).

These exercise the service method directly with a mocked ITextAI (the validator's
verdict) and a mocked ILiveAI (the Live session the steer is injected into), so the
three exit criteria are proven without a real model:
  1. conflict -> steer NAMES both fields + reaches the Live session; clean -> no steer.
  2. the steer carries the user-override escape hatch ("accept ... if they confirm").
  3. an already-steered field suppresses the re-steer (per-field), no infinite loop.

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.form_filling_service import FormFillingService


def _service(verdict):
    """A FormFillingService with a mocked validator (returns `verdict`) and a live
    session that is active and records send_client_content calls."""
    text_ai = MagicMock(name="text_ai")
    text_ai.validate = AsyncMock(return_value=verdict)
    live_ai = MagicMock(name="live_ai")
    live_ai.is_session_active = MagicMock(return_value=True)
    live_ai.send_client_content = AsyncMock()
    svc = FormFillingService(live_ai=live_ai, text_ai=text_ai)
    return svc, live_ai, text_ai


_FIELDS = [
    {"field_id": "addr_state", "name": "State", "value": "West Virginia", "steered": False},
    {"field_id": "addr_zip", "name": "ZIP code", "value": "50301", "steered": False},
]


@pytest.mark.asyncio
async def test_conflict_injects_steer_naming_both_fields():
    verdict = {"conflicts": [
        {"field_ids": ["addr_state", "addr_zip"],
         "reason": "State is West Virginia but ZIP 50301 is in Iowa."},
    ]}
    svc, live_ai, _ = _service(verdict)

    returned = await svc.handle_validation_boundary(_FIELDS)

    # No field is already steered here, so every conflict SURVIVES suppression -- the
    # returned (post-suppression) verdict equals the input. (A suppressed conflict
    # would be omitted; see test_already_steered_field_suppresses_resteer.)
    assert returned == verdict
    # The steer reached the Live session exactly once...
    live_ai.send_client_content.assert_awaited_once()
    steer = live_ai.send_client_content.await_args.args[0]
    # ...naming BOTH fields by their human names (criterion 1)...
    assert "State" in steer and "ZIP code" in steer
    # ...and carrying the reason in-band.
    assert "Iowa" in steer


@pytest.mark.asyncio
async def test_clean_verdict_injects_no_steer():
    svc, live_ai, _ = _service({"conflicts": []})
    returned = await svc.handle_validation_boundary(_FIELDS)
    assert returned == {"conflicts": []}
    live_ai.send_client_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_steer_carries_user_override_escape_hatch():
    verdict = {"conflicts": [
        {"field_ids": ["addr_state", "addr_zip"], "reason": "possible mismatch"},
    ]}
    svc, live_ai, _ = _service(verdict)
    await svc.handle_validation_boundary(_FIELDS)
    steer = live_ai.send_client_content.await_args.args[0].lower()
    # Criterion 2: the legacy "accept the user's answer if they confirm" semantics.
    assert "accept" in steer and "confirm" in steer


@pytest.mark.asyncio
async def test_already_steered_field_suppresses_resteer():
    # addr_state is already steered -> the conflict referencing it is suppressed
    # (per-field, contract 3 invariant 2): no second steer, no infinite loop.
    fields = [
        {"field_id": "addr_state", "name": "State", "value": "WV", "steered": True},
        {"field_id": "addr_zip", "name": "ZIP code", "value": "50301", "steered": False},
    ]
    verdict = {"conflicts": [
        {"field_ids": ["addr_state", "addr_zip"], "reason": "mismatch"},
    ]}
    svc, live_ai, _ = _service(verdict)

    returned = await svc.handle_validation_boundary(fields)

    # A SUPPRESSED conflict must read as CLEAN to the client ({conflicts: []}), NOT
    # the full pre-suppression verdict: the client gates the section switch on this,
    # so returning a suppressed conflict would hold the switch forever with no steer
    # voiced -- trapping a user who already overrode it (fresh-eyes finding). No steer.
    assert returned == {"conflicts": []}
    live_ai.send_client_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_per_field_suppression_covers_a_new_conflict_on_a_steered_field():
    # addr_state already steered; a NEW conflict addr_state+country must ALSO be
    # suppressed (per-field rule, not all-fields) -- the user already adjudicated
    # addr_state once.
    fields = [
        {"field_id": "addr_state", "name": "State", "value": "WV", "steered": True},
        {"field_id": "country", "name": "Country", "value": "Canada", "steered": False},
    ]
    verdict = {"conflicts": [
        {"field_ids": ["addr_state", "country"], "reason": "state not in country"},
    ]}
    svc, live_ai, _ = _service(verdict)
    returned = await svc.handle_validation_boundary(fields)
    live_ai.send_client_content.assert_not_awaited()
    # Suppressed -> reads as clean so the switch is not trapped.
    assert returned == {"conflicts": []}


@pytest.mark.asyncio
async def test_override_does_not_trap_the_user_switch_gate():
    """Criterion 2 (the override escape hatch) end-to-end: a user who confirmed a
    flagged conflict (both fields now steered:true) must be able to ADVANCE. Once
    suppressed, the boundary returns CLEAN so the client resumes the section switch
    -- not a held conflict with no steer. Regression for the user-stranding bug."""
    fields = [
        {"field_id": "addr_state", "name": "State", "value": "WV", "steered": True},
        {"field_id": "addr_zip", "name": "ZIP code", "value": "50301", "steered": True},
    ]
    verdict = {"conflicts": [
        {"field_ids": ["addr_state", "addr_zip"], "reason": "still looks off"},
    ]}
    svc, live_ai, _ = _service(verdict)
    returned = await svc.handle_validation_boundary(fields)
    # No steer (already adjudicated) AND clean to the client (switch proceeds).
    live_ai.send_client_content.assert_not_awaited()
    assert returned == {"conflicts": []}


@pytest.mark.asyncio
async def test_steer_dropped_when_session_inactive_returns_clean():
    # A conflict whose STEER did not reach the Live session (dead session) must read
    # as CLEAN to the client (Codex PR #275): returning it would hold the section with
    # no voiced guidance (the model never got the steer) -- the same trap as a
    # suppressed conflict. Fail-OPEN: advance unchecked.
    verdict = {"conflicts": [{"field_ids": ["addr_state"], "reason": "x"}]}
    svc, live_ai, _ = _service(verdict)
    live_ai.is_session_active = MagicMock(return_value=False)
    returned = await svc.handle_validation_boundary(_FIELDS)
    assert returned == {"conflicts": []}
    live_ai.send_client_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_text_ai_is_all_clear():
    svc = FormFillingService(live_ai=MagicMock(), text_ai=None)
    assert await svc.handle_validation_boundary(_FIELDS) == {"conflicts": []}


@pytest.mark.asyncio
async def test_validator_failure_fails_open_no_steer():
    # The validator raising must fail-OPEN (ValidatorService swallows it) -> clean.
    text_ai = MagicMock()
    text_ai.validate = AsyncMock(side_effect=RuntimeError("boom"))
    live_ai = MagicMock()
    live_ai.is_session_active = MagicMock(return_value=True)
    live_ai.send_client_content = AsyncMock()
    svc = FormFillingService(live_ai=live_ai, text_ai=text_ai)

    returned = await svc.handle_validation_boundary(_FIELDS)
    assert returned == {"conflicts": []}
    live_ai.send_client_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_steer_delivery_failure_returns_clean():
    # The steer was attempted but send_client_content RAISED -> the model never got
    # it, so the conflict must read as clean (no trap). Codex PR #275.
    verdict = {"conflicts": [{"field_ids": ["addr_state", "addr_zip"], "reason": "x"}]}
    svc, live_ai, _ = _service(verdict)
    live_ai.send_client_content = AsyncMock(side_effect=RuntimeError("send failed"))
    returned = await svc.handle_validation_boundary(_FIELDS)
    assert returned == {"conflicts": []}


@pytest.mark.asyncio
async def test_conflict_on_unknown_field_is_dropped():
    # A validator conflict naming a field NOT in the boundary payload (hallucinated /
    # misspelled id) cannot be marked steered client-side -> it would trap the user
    # forever. Drop it (clean), no steer. Codex PR #275.
    verdict = {"conflicts": [
        {"field_ids": ["addr_state", "ghost_field"], "reason": "phantom"},
    ]}
    svc, live_ai, _ = _service(verdict)
    returned = await svc.handle_validation_boundary(_FIELDS)
    assert returned == {"conflicts": []}
    live_ai.send_client_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_validator_timeout_fails_open(monkeypatch):
    # A validator that HANGS past the backend timeout must fail-OPEN (clean, no steer)
    # so the inline await does not block the WS receive loop past the client gate.
    # Codex PR #275.
    import asyncio as _asyncio

    async def _hang(_payload):
        await _asyncio.sleep(10)

    text_ai = MagicMock()
    text_ai.validate = AsyncMock(side_effect=_hang)
    live_ai = MagicMock()
    live_ai.is_session_active = MagicMock(return_value=True)
    live_ai.send_client_content = AsyncMock()
    svc = FormFillingService(live_ai=live_ai, text_ai=text_ai)
    monkeypatch.setattr(svc._settings, "VALIDATOR_TIMEOUT_SEC", 0.05)

    returned = await svc.handle_validation_boundary(_FIELDS)
    assert returned == {"conflicts": []}
    live_ai.send_client_content.assert_not_awaited()
