"""Spec: FormFillingService.update_form_state() -- the web-session form-state
acknowledgment contract (bd polyglot-pdf-uov.7, T1.4).

This file was a 0-line stub that read as coverage but asserted nothing. T1.4
resolves it by specifying the one service-level form-state method with real
branching logic and NO existing coverage: update_form_state().

What the OTHER tests already cover (so this file does NOT duplicate them):
  * test_stateless_reconnect_isolation.py (T2.1) -- the persistence-ABSENCE
    invariant via update_schema (no field value survives a reconnect).
  * test_request_coordinator.py -- the async request/response plumbing
    (request_form_state / handle_form_state_response at the coordinator layer).

The gap this file fills: update_form_state() is the inbound web-acknowledgment
boundary. The AI/route hands it a client-provided list of field updates; the
method's documented contract (form_filling_service.py update_form_state) is:

  1. Validate each field_id against the loaded schema; silently DROP any update
     whose id is unknown or whose shape is not a dict.
  2. Acknowledge accepted ids via {"applied_fields": [...]} -- in input order.
  3. NEVER cache the values. The client stays the single source of truth
     (CLAUDE.md scar #4: stateless backend, client owns all field state).
  4. Accept the id under EITHER the "field_id" or "id" key (the method reads
     both), so a caller using either wire shape is acknowledged.

These assert on the contract, not the current code path, so they FAIL the moment
someone starts caching values here or stops validating ids against the schema --
the exact regressions the stateless invariant guards.

PII: as with the sibling specs, the values handed in are PII-shaped; the
assertions check id acknowledgment and the ABSENCE of the value from service
state -- they never print a value.
"""

from unittest.mock import AsyncMock

from backend.config import Settings
from backend.services.form_filling_service import FormFillingService


SCHEMA = {
    "form_metadata": {"form_number": "I-90", "version": "1.0.0"},
    "sections": [{"id": "s1", "label": "Name", "order": 1, "fields": ["f1", "f2"]}],
    "fields": [
        {"id": "f1", "name": "First Name", "type": "text", "section_id": "s1"},
        {"id": "f2", "name": "Last Name", "type": "text", "section_id": "s1"},
    ],
}

# A PII-shaped value: if this string can be recovered off the service after
# update_form_state, the method cached it -- the stateless contract is broken.
SECRET = "Jdoe-SECRET-VALUE"


def _make_service() -> FormFillingService:
    return FormFillingService(live_ai=AsyncMock(), settings=Settings())


def _with_schema() -> FormFillingService:
    service = _make_service()
    service.update_schema(SCHEMA, current_values={}, fill_language="English")
    return service


def _state_blob(service: FormFillingService) -> str:
    """Flatten every instance attribute to a string so an assertion can prove a
    value was NOT stashed under ANY attribute name."""
    return repr(vars(service))


def test_empty_updates_acknowledge_nothing():
    """No updates -> empty applied_fields (the early-return path)."""
    service = _with_schema()

    assert service.update_form_state([]) == {"applied_fields": []}


def test_known_field_id_is_acknowledged():
    """A field_id present in the schema is echoed back in applied_fields."""
    service = _with_schema()

    result = service.update_form_state([{"field_id": "f1", "value": SECRET}])

    assert result == {"applied_fields": ["f1"]}


def test_id_key_alias_is_accepted():
    """The id may arrive under "id" instead of "field_id" -- both are accepted."""
    service = _with_schema()

    result = service.update_form_state([{"id": "f1", "value": SECRET}])

    assert result == {"applied_fields": ["f1"]}


def test_unknown_field_id_is_dropped():
    """A field_id absent from the schema is silently ignored, not acknowledged."""
    service = _with_schema()

    result = service.update_form_state([{"field_id": "not_in_schema", "value": SECRET}])

    assert result == {"applied_fields": []}


def test_malformed_and_idless_entries_are_dropped():
    """Non-dict entries and entries with no id are skipped without raising."""
    service = _with_schema()

    result = service.update_form_state(
        [
            "not-a-dict",
            {"value": SECRET},  # no field_id / id
            {"field_id": "", "value": SECRET},  # empty id is falsy -> dropped
            {"field_id": "f2", "value": SECRET},  # the one valid entry
        ]
    )

    assert result == {"applied_fields": ["f2"]}


def test_acknowledgment_preserves_input_order():
    """applied_fields lists accepted ids in the order they were supplied."""
    service = _with_schema()

    result = service.update_form_state(
        [
            {"field_id": "f2", "value": SECRET},
            {"field_id": "f1", "value": SECRET},
        ]
    )

    assert result == {"applied_fields": ["f2", "f1"]}


def test_values_are_never_cached():
    """The load-bearing invariant: update_form_state acknowledges ids but stores
    no values. After accepting an update, the PII value must not be recoverable
    off ANY service attribute (CLAUDE.md scar #4)."""
    service = _with_schema()

    service.update_form_state([{"field_id": "f1", "value": SECRET}])

    blob = _state_blob(service)
    assert SECRET not in blob
    # And no values-shaped attribute was introduced to hold them.
    assert not hasattr(service, "_current_values")
    assert not hasattr(service, "_field_values")


def test_validation_uses_schema_so_no_schema_acknowledges_nothing():
    """With no schema loaded, there are no known ids -> every update is dropped.
    Acknowledgment is gated on the schema, never on a cached value set."""
    service = _make_service()  # deliberately no update_schema()

    result = service.update_form_state([{"field_id": "f1", "value": SECRET}])

    assert result == {"applied_fields": []}
