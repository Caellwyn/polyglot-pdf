"""ValidatorService -- cross-field contradiction validator (bd polyglot-pdf-jnjj.15, "B3").

Covers the bead's three exit criteria:
  1. Catches the three contradiction classes on fixtures; returns the F3 verdict.
  2. PII-safe logging (no values / reasons in any log event).
  3. Fail-OPEN on flash-lite timeout / error / bad shape.

The fixtures are the G1 corpus (backend/scripts/g1_corpus.py) -- REAL I-90 field
ids/names with fabricated values. The text model is stubbed with a payload-reading
oracle so the test is deterministic (no live Gemini): the stub parses the
fresh_tail the service rendered and flags exactly the corpus ground truth. That
exercises the real render -> call -> parse -> sanitize path and PROVES the service
hands the model the data it needs and faithfully returns the model's verdict --
without coupling the unit test to live-model recall (that is the G1 probe's job).

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

import json

import pytest
import structlog.testing

from backend.scripts.g1_corpus import build_corpus
from backend.services.validator_service import (
    CONTRADICTION_SI,
    ValidatorService,
    render_validator_payload,
    _sanitize_conflicts,
)

TODAY = "2026-06-17"  # fixed so future-DOB judgments are deterministic.


# --------------------------------------------------------------------------
# Stub text models
# --------------------------------------------------------------------------

def _case_key(fields):
    """A unique key for a case from its rendered (id, value) pairs. The field-id
    set alone is NOT unique -- a zip_state case and a clean_us case share the same
    five address field ids and differ only in VALUES -- so the oracle must key on
    values too. Keying on the rendered values also proves the service put the
    values into the payload."""
    return tuple(sorted((f.get("field_id"), str(f.get("value"))) for f in fields))


class _OracleTextAI:
    """ITextAI stub that reads the rendered payload and flags the corpus ground
    truth. It looks the contradiction up by the (field_id, value) pairs present in
    the fresh_tail, so it can only flag correctly if the service actually rendered
    the field values into the payload -- i.e. it tests the render contract, not
    just a hardcoded return."""

    def __init__(self, truth_by_case):
        # _case_key(fields) -> expected_conflicts (list of sets)
        self._truth = truth_by_case
        self.last_payload = None

    async def validate(self, payload, session_ctx=None):
        self.last_payload = payload
        self.last_session_ctx = session_ctx
        tail = "".join(payload.get("fresh_tail", []))
        # Recover the fields the service rendered.
        try:
            state = json.loads(tail.split("FIELDS:\n", 1)[1])
        except (IndexError, json.JSONDecodeError):
            return {"conflicts": []}
        key = _case_key(state.get("fields", []))
        expected = self._truth.get(key, [])
        return {
            "conflicts": [
                {"field_ids": sorted(s), "reason": "stub reason"} for s in expected
            ]
        }


class _RaisingTextAI:
    async def validate(self, payload, session_ctx=None):
        raise RuntimeError("simulated flash-lite outage")


class _FailOpenTextAI:
    """Mirrors the adapter's own fail-open: returns the all-clear on any trouble."""
    async def validate(self, payload, session_ctx=None):
        return {"conflicts": []}


class _BadShapeTextAI:
    def __init__(self, verdict):
        self._verdict = verdict

    async def validate(self, payload, session_ctx=None):
        return self._verdict


def _truth_index(corpus):
    return {_case_key(c.fields): c.expected_conflicts for c in corpus}


# --------------------------------------------------------------------------
# Exit criterion 1 -- catches the three contradiction classes; returns F3 verdict
# --------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("cls", ["zip_state", "state_country", "future_dob"])
async def test_catches_each_contradiction_class(cls):
    """The bead's three named classes: zip-vs-state, contradictory addresses
    (state-vs-country), future birthdays. The service must surface the conflict
    the model flags, in the contract-1 verdict shape."""
    corpus = build_corpus()
    cases = [c for c in corpus if c.cls == cls]
    assert cases, f"no {cls} fixtures in corpus"
    svc = ValidatorService(_OracleTextAI(_truth_index(corpus)))

    for case in cases:
        verdict = await svc.validate(case.fields, today=TODAY)
        # Contract-1 shape.
        assert set(verdict.keys()) == {"conflicts"}
        assert isinstance(verdict["conflicts"], list)
        assert verdict["conflicts"], f"{case.case_id} produced no conflict"
        flagged = {frozenset(c["field_ids"]) for c in verdict["conflicts"]}
        for exp in case.expected_conflicts:
            assert frozenset(exp) in flagged, f"{case.case_id} missed {exp}"
        # Every conflict is the contract-1 dict shape.
        for c in verdict["conflicts"]:
            assert isinstance(c["field_ids"], list) and c["field_ids"]
            assert isinstance(c["reason"], str)


@pytest.mark.asyncio
async def test_clean_case_returns_empty_conflicts():
    """A coherent address yields the explicit all-clear empty list, not a missing
    key -- the deterministic clean signal contract 1 requires."""
    corpus = build_corpus()
    clean = next(c for c in corpus if c.cls == "clean_us")
    svc = ValidatorService(_OracleTextAI(_truth_index(corpus)))
    verdict = await svc.validate(clean.fields, today=TODAY)
    assert verdict == {"conflicts": []}


# --------------------------------------------------------------------------
# Payload render helper
# --------------------------------------------------------------------------

def test_render_payload_shape_and_today():
    secret = "ZZsecretvalueZZ"  # distinctive, won't collide with prompt prose.
    fields = [{"field_id": "afield", "name": "A", "value": secret, "steered": False}]
    payload = render_validator_payload(fields, today=TODAY)
    assert set(payload.keys()) == {"stable_prefix", "fresh_tail", "field_count"}
    assert payload["field_count"] == 1
    # today is in the value-free prefix; the values are in the fresh tail.
    assert TODAY in payload["stable_prefix"][0]
    assert "today is {today}" not in payload["stable_prefix"][0]  # substituted
    tail = "".join(payload["fresh_tail"])
    assert '"field_id": "afield"' in tail
    assert secret in tail
    # Prefix is value-free (cacheable): the field value must NOT leak into it.
    assert secret not in payload["stable_prefix"][0]


def test_render_payload_today_defaults_to_real_date():
    """today=None must not raise and must produce an ISO date in the prefix
    (module load never calls datetime.now())."""
    payload = render_validator_payload([], today=None)
    prefix = payload["stable_prefix"][0]
    import re
    assert re.search(r"today is \d{4}-\d{2}-\d{2}", prefix)


def test_render_payload_non_list_fields_is_empty_state():
    payload = render_validator_payload(None)  # type: ignore[arg-type]
    assert payload["field_count"] == 0
    assert json.loads("".join(payload["fresh_tail"]).split("FIELDS:\n", 1)[1]) == {
        "fields": []
    }


def test_contradiction_si_matches_probe_prompt():
    """The deployed SI must reproduce the G1-probe FLASH_LITE_PROMPT (minus the
    trailing FIELDS template, which moves to the fresh tail) so the deployed
    validator matches what the GO gate measured."""
    from backend.scripts.probe_g1_contradiction_recall import FLASH_LITE_PROMPT
    probe_head = FLASH_LITE_PROMPT.split("\n\nFIELDS:")[0]
    # The probe pins TODAY inline; our SI templates it. Compare with today filled.
    deployed = CONTRADICTION_SI.format(today="2026-06-17")
    assert deployed == probe_head


# --------------------------------------------------------------------------
# Sanitizer -- contract-1 shape enforcement
# --------------------------------------------------------------------------

def test_sanitize_keeps_well_formed_and_drops_malformed():
    raw = [
        {"field_ids": ["a", "b"], "reason": "ok"},        # kept
        {"field_ids": ["x"], "reason": "single-field ok"},  # kept (1 id valid)
        {"field_ids": [], "reason": "no ids"},            # dropped (empty)
        {"reason": "no field_ids key"},                   # dropped
        {"field_ids": "not-a-list", "reason": "r"},       # dropped
        "not-a-dict",                                     # dropped
        {"field_ids": [1, 2], "reason": "ints coerced"},  # kept, ids -> str
    ]
    out = _sanitize_conflicts(raw)
    assert [c["field_ids"] for c in out] == [
        ["a", "b"], ["x"], ["1", "2"],
    ]
    assert all(isinstance(c["reason"], str) for c in out)


@pytest.mark.asyncio
async def test_malformed_conflict_dropped_not_raised():
    svc = ValidatorService(_BadShapeTextAI({"conflicts": [
        {"field_ids": ["a"], "reason": "good"},
        {"junk": True},
    ]}))
    verdict = await svc.validate([{"field_id": "a", "name": "A", "value": "v"}])
    assert verdict["conflicts"] == [{"field_ids": ["a"], "reason": "good"}]


# --------------------------------------------------------------------------
# Exit criterion 3 -- FAIL-OPEN
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fail_open_on_text_ai_exception():
    svc = ValidatorService(_RaisingTextAI())
    verdict = await svc.validate([{"field_id": "a", "name": "A", "value": "v"}])
    assert verdict == {"conflicts": []}


@pytest.mark.asyncio
async def test_fail_open_on_adapter_fail_open():
    svc = ValidatorService(_FailOpenTextAI())
    verdict = await svc.validate([{"field_id": "a", "name": "A", "value": "v"}])
    assert verdict == {"conflicts": []}


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [
    None,
    [],
    "a string",
    {"no_conflicts_key": True},
    {"conflicts": "not-a-list"},
    {"conflicts": 42},
])
async def test_fail_open_on_bad_verdict_shape(bad):
    svc = ValidatorService(_BadShapeTextAI(bad))
    verdict = await svc.validate([{"field_id": "a", "name": "A", "value": "v"}])
    assert verdict == {"conflicts": []}


# --------------------------------------------------------------------------
# Exit criterion 2 -- PII-safe logging
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_pii_in_logs_on_conflict():
    """No field value or reason text may appear in any log event -- only ids /
    counts / lengths (callback_handler discipline, contract 6)."""
    corpus = build_corpus()
    case = next(c for c in corpus if c.cls == "zip_state")
    svc = ValidatorService(_OracleTextAI(_truth_index(corpus)))
    with structlog.testing.capture_logs() as logs:
        await svc.validate(case.fields, today=TODAY)

    values = {f["value"] for f in case.fields}
    assert logs, "expected at least one log event"
    for entry in logs:
        for v in entry.values():
            text = str(v)
            for val in values:
                assert val not in text, f"leaked value {val!r} in log {entry!r}"
            # The verdict reason text must never be logged.
            assert "stub reason" not in text


@pytest.mark.asyncio
async def test_no_pii_in_logs_on_fail_open():
    svc = ValidatorService(_RaisingTextAI())
    secret = "123-45-6789-secret-value"
    with structlog.testing.capture_logs() as logs:
        await svc.validate([{"field_id": "ssn", "name": "SSN", "value": secret}])
    for entry in logs:
        for v in entry.values():
            assert secret not in str(v)
