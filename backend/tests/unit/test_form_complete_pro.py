"""W6 (bd polyglot-pdf-gbus): FormFillingService.handle_form_complete_pro -- the
whole-form gemini-2.5-pro contradiction pass at form_complete (the SOLE end-of-form
report, catching cross-page far pairs the lite windows miss).

Exercises the service method with a mocked pro ITextAI, proving the W6 exit
criterion at the service layer:
  - wired + emits: a far-pair conflict is returned in the report-only shape
    (field_ids + reason + field_names rider), ready for the client's drain path;
  - a previously-STEERED contradiction is NOT re-flagged (suppressed by the shared
    _suppress_already_steered dedupe) -- the required not-re-flag assertion;
  - the pro pass is FED the steered field ids as prompt context (adjudicated slot);
  - fail-OPEN: no pro wired (flag off) / timeout / error all return clean;
  - the anti-over-flag prompt (Part 5/6 cert block + bracketed-repeat) shipped in
    WHOLE_FORM_PRO_SI (deterministic prompt-content assertion, in lieu of live spend).

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.form_filling_service import FormFillingService
from backend.services.validator_service import WHOLE_FORM_PRO_SI


def _service(pro_verdict=None, pro_wired=True):
    """A FormFillingService with a mocked PRO validator (text_ai_pro). The pro
    adapter's validate(payload) is what's mocked; ValidatorService wraps it and
    sanitizes the verdict, so the mock returns the raw {conflicts:[...]} shape the
    adapter would."""
    pro = MagicMock(name="text_ai_pro")
    pro.validate = AsyncMock(return_value=pro_verdict or {"conflicts": []})
    svc = FormFillingService(
        live_ai=MagicMock(),
        text_ai=MagicMock(),
        text_ai_pro=pro if pro_wired else None,
    )
    return svc, pro


# A whole-form far-pair contradiction (a DOB restated with a different year far away).
_FAR = {"field_ids": ["p1_dob", "p8_dob_restated"], "reason": "DOB stated as 1990 in Part 1 but 1991 in Part 8"}
_FIELDS = [
    {"field_id": "p1_dob", "name": "Date of birth", "value": "1990-04-02", "steered": False},
    {"field_id": "p8_dob_restated", "name": "DOB (restated)", "value": "1991-04-02", "steered": False},
]


@pytest.mark.asyncio
async def test_pro_pass_wired_returns_report_only_conflict_with_field_names():
    svc, pro = _service(pro_verdict={"conflicts": [_FAR]})
    returned = await svc.handle_form_complete_pro(_FIELDS)

    # Report-only shape: field_ids + reason + a field_names id->name rider.
    assert len(returned["conflicts"]) == 1
    c = returned["conflicts"][0]
    assert set(c["field_ids"]) == {"p1_dob", "p8_dob_restated"}
    assert c["field_names"] == {"p1_dob": "Date of birth", "p8_dob_restated": "DOB (restated)"}
    # It ran the pro validator once (no injection here -- report-only).
    pro.validate.assert_awaited_once()


@pytest.mark.asyncio
async def test_previously_steered_contradiction_is_NOT_reflagged():
    # The far-pair fields were already flagged + adjudicated mid-form (steered:true).
    # The pro pass returns the same conflict, but it must be SUPPRESSED (exit crit 2).
    steered_fields = [
        {"field_id": "p1_dob", "name": "Date of birth", "value": "1990-04-02", "steered": True},
        {"field_id": "p8_dob_restated", "name": "DOB (restated)", "value": "1991-04-02", "steered": True},
    ]
    svc, _ = _service(pro_verdict={"conflicts": [_FAR]})
    returned = await svc.handle_form_complete_pro(steered_fields)
    assert returned == {"conflicts": []}  # suppressed -> not re-flagged


@pytest.mark.asyncio
async def test_pro_pass_is_fed_the_steered_ids_as_context():
    # The steered field ids ride into the pro SI's adjudicated slot (prompt-layer feed).
    steered_fields = [
        {"field_id": "addr_state", "name": "State", "value": "WV", "steered": True},
        {"field_id": "p1_dob", "name": "DOB", "value": "1990-04-02", "steered": False},
    ]
    svc, pro = _service(pro_verdict={"conflicts": []})
    await svc.handle_form_complete_pro(steered_fields)
    # The payload the pro adapter received carries the adjudicated instruction with
    # the steered id in its stable_prefix (the rendered SI).
    (payload,) = pro.validate.await_args.args
    si_text = "".join(payload.get("stable_prefix", []))
    assert "ALREADY ADJUDICATED" in si_text
    assert "addr_state" in si_text          # the steered id is named
    assert "p1_dob" not in si_text.split("ALREADY ADJUDICATED")[1].split("\n")[0]  # the unsteered one is not


@pytest.mark.asyncio
async def test_no_pro_wired_is_a_clean_noop():
    svc, _ = _service(pro_wired=False)  # FORM_COMPLETE_PRO_VALIDATOR off
    assert await svc.handle_form_complete_pro(_FIELDS) == {"conflicts": []}


@pytest.mark.asyncio
async def test_pro_validator_error_fails_open():
    svc, pro = _service()
    pro.validate = AsyncMock(side_effect=RuntimeError("pro boom"))
    assert await svc.handle_form_complete_pro(_FIELDS) == {"conflicts": []}


@pytest.mark.asyncio
async def test_pro_validator_timeout_fails_open(monkeypatch):
    import asyncio as _asyncio

    async def _hang(_payload, session_ctx=None):
        await _asyncio.sleep(10)

    svc, pro = _service()
    pro.validate = AsyncMock(side_effect=_hang)
    monkeypatch.setattr(svc._settings, "VALIDATOR_PRO_TIMEOUT_SEC", 0.05)
    assert await svc.handle_form_complete_pro(_FIELDS) == {"conflicts": []}


@pytest.mark.asyncio
async def test_empty_fields_is_clean():
    svc, pro = _service()
    assert await svc.handle_form_complete_pro([]) == {"conflicts": []}
    assert await svc.handle_form_complete_pro("not-a-list") == {"conflicts": []}
    pro.validate.assert_not_awaited()


# --------------------------------------------------------------------------- #
# The anti-over-flag prompt content (the W5 precision condition). Deterministic
# assertion in lieu of a live re-measure (which is orchestrator-gated Vertex spend).
# --------------------------------------------------------------------------- #

def test_pro_si_carries_the_far_pair_rule():
    si = WHOLE_FORM_PRO_SI.lower()
    assert "same fact stated two different ways" in si


def test_pro_si_carries_the_anti_over_flag_items():
    si = WHOLE_FORM_PRO_SI.lower()
    # The two W5-measured over-flag buckets must be explicitly excluded.
    assert "preparer" in si and "interpreter" in si and "certification" in si
    assert "bracket" in si and ("continuation" in si or "same logical field" in si)


def test_pro_si_carries_the_g1c_anti_hedging_block():
    si = WHOLE_FORM_PRO_SI.lower()
    assert "anti-hedging" in si
    assert "genuinely impossible" in si
    # It has an {adjudicated} slot for the steered-field feed.
    assert "{adjudicated}" in WHOLE_FORM_PRO_SI
