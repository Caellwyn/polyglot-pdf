"""W3 (bd polyglot-pdf-pr3i): FormFillingService.handle_drain_findings -- the
FINDING-DRIVEN drain that composes + injects the steer for the client's queued
conflicts, split OUT of handle_validation_windows (which is report-only since W3).

These exercise the service method directly with a mocked ILiveAI (the steer sink):
  - queued conflicts -> ONE steer composed via the oiok composer + injected, and the
    delivered conflicts are returned (so the client marks them steered + consumes
    them);
  - the steer NAMES the fields (from the client-supplied field_names rider) and
    routes through switch_to_field (the correction rail);
  - fail-OPEN: an un-delivered steer (dead session / send False / raise) returns []
    so the client keeps the finding queued to retry;
  - an empty / malformed drain is a no-op (no steer, empty verdict).

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.form_filling_service import FormFillingService


def _service():
    text_ai = MagicMock(name="text_ai")
    live_ai = MagicMock(name="live_ai")
    live_ai.is_session_active = MagicMock(return_value=True)
    live_ai.send_client_content = AsyncMock(return_value=True)
    svc = FormFillingService(live_ai=live_ai, text_ai=text_ai)
    return svc, live_ai


# The client's drain_findings payload: each conflict carries field_ids + reason +
# the field_names id->name rider (attached by the report-only windows path).
_CONFLICTS = [
    {
        "field_ids": ["addr_state", "addr_zip"],
        "reason": "State is West Virginia but ZIP 50301 is in Iowa.",
        "field_names": {"addr_state": "State", "addr_zip": "ZIP code"},
    },
]


@pytest.mark.asyncio
async def test_drain_injects_one_steer_naming_fields_and_returns_delivered():
    svc, live_ai = _service()
    returned = await svc.handle_drain_findings(_CONFLICTS)

    # The steer reached the live session exactly once...
    live_ai.send_client_content.assert_awaited_once()
    steer = live_ai.send_client_content.await_args.args[0]
    # ...naming both fields by their client-supplied names...
    assert "State" in steer and "ZIP code" in steer
    # ...carrying the reason...
    assert "Iowa" in steer
    # ...and routing through the correction rail.
    assert "switch_to_field" in steer
    # The delivered conflicts come back (contract-1 shape) for the client to consume.
    assert [c["field_ids"] for c in returned["conflicts"]] == [["addr_state", "addr_zip"]]


@pytest.mark.asyncio
async def test_drain_missing_name_falls_back_to_field_id():
    # A conflict with no field_names rider still steers, using the id as the name.
    svc, live_ai = _service()
    await svc.handle_drain_findings([
        {"field_ids": ["dob"], "reason": "future DOB"},
    ])
    steer = live_ai.send_client_content.await_args.args[0]
    assert "dob" in steer  # id used as the label
    assert "future DOB" in steer


@pytest.mark.asyncio
async def test_drain_empty_or_malformed_is_noop():
    svc, live_ai = _service()
    assert await svc.handle_drain_findings([]) == {"conflicts": []}
    assert await svc.handle_drain_findings("not-a-list") == {"conflicts": []}
    # A conflict with no field_ids cannot be steered -> dropped -> empty verdict.
    assert await svc.handle_drain_findings([{"reason": "x"}]) == {"conflicts": []}
    live_ai.send_client_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_drain_undelivered_steer_returns_empty_so_client_retries():
    # send_client_content returns False (queued / no session) -> the model never got
    # the steer, so NOTHING is reported delivered and the client keeps it queued.
    svc, live_ai = _service()
    live_ai.send_client_content = AsyncMock(return_value=False)
    returned = await svc.handle_drain_findings(_CONFLICTS)
    assert returned == {"conflicts": []}
    live_ai.send_client_content.assert_awaited_once()  # it WAS attempted


@pytest.mark.asyncio
async def test_drain_dead_session_returns_empty():
    svc, live_ai = _service()
    live_ai.is_session_active = MagicMock(return_value=False)
    returned = await svc.handle_drain_findings(_CONFLICTS)
    assert returned == {"conflicts": []}
    live_ai.send_client_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_drain_send_raises_returns_empty():
    svc, live_ai = _service()
    live_ai.send_client_content = AsyncMock(side_effect=RuntimeError("send failed"))
    returned = await svc.handle_drain_findings(_CONFLICTS)
    assert returned == {"conflicts": []}


@pytest.mark.asyncio
async def test_drain_batches_multiple_findings_into_one_steer():
    svc, live_ai = _service()
    returned = await svc.handle_drain_findings([
        {"field_ids": ["addr_state", "addr_zip"], "reason": "geo mismatch",
         "field_names": {"addr_state": "State", "addr_zip": "ZIP"}},
        {"field_ids": ["dob", "sig_date"], "reason": "birth after signature",
         "field_names": {"dob": "Date of birth", "sig_date": "Signature date"}},
    ])
    # Both findings ride ONE injection.
    live_ai.send_client_content.assert_awaited_once()
    steer = live_ai.send_client_content.await_args.args[0]
    assert "State" in steer and "Date of birth" in steer
    assert "one finding at a time" in steer
    assert len(returned["conflicts"]) == 2
