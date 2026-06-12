"""Spec: the backend retains NO field state across connections (bd polyglot-pdf-uov.8, T2.1).

The load-bearing stateless invariant (see CLAUDE.md scar #4): the client owns all
field state in sessionStorage; the backend rebuilds context from the handshake on
every (re)connect and NEVER persists field values server-side. update_schema
takes current_values purely to satisfy the call shape -- it must drop them on the
floor.

These tests assert on the ABSENCE of server-side value state, so they FAIL the
moment anyone introduces per-session field persistence (the exact regression the
invariant guards). They are written against a PLAIN connect / disconnect /
reconnect, deliberately NOT against a section-switch reset: the statelessness
property is independent of how (or whether) the Gemini session is restarted at a
section boundary, so the spec stays valid through any change to that reset path.
"""

from unittest.mock import AsyncMock

import pytest

from backend.config import Settings
from backend.services.form_filling_service import FormFillingService


SCHEMA = {
    "form_metadata": {"form_number": "I-90", "version": "1.0.0"},
    "sections": [{"id": "s1", "label": "Name", "order": 1, "fields": ["f1"]}],
    "fields": [{"id": "f1", "name": "First Name", "type": "text", "section_id": "s1"}],
}

# The PII-shaped values a client might send on the handshake. If ANY of these
# strings can be recovered off the service after update_schema, the backend is
# persisting field state -- the invariant is broken.
CLIENT_VALUES = {
    "f1": {"value": "Jdoe-SECRET-VALUE", "confirmed": True},
}


def _make_service() -> FormFillingService:
    return FormFillingService(live_ai=AsyncMock(), settings=Settings())


def _service_state_blob(service: FormFillingService) -> str:
    # Flatten every instance attribute to a string so an assertion can prove a
    # value did NOT get stashed under ANY attribute name (defends against a
    # future field being added that quietly retains values).
    return repr(vars(service))


def test_update_schema_does_not_retain_client_field_values():
    """current_values handed to update_schema must not be stored anywhere."""
    service = _make_service()

    service.update_schema(SCHEMA, current_values=CLIENT_VALUES, fill_language="English")

    # The schema IS retained (context); the VALUES are not.
    assert service._schema == SCHEMA
    assert "Jdoe-SECRET-VALUE" not in _service_state_blob(service)
    # And there is no values-shaped attribute at all.
    assert not hasattr(service, "_current_values")
    assert not hasattr(service, "_field_values")


def test_no_field_value_survives_a_simulated_reconnect():
    """Connect with values, 'disconnect', reconnect with EMPTY values -> no residue.

    The backend rebuilds context from each handshake. A reconnect that sends no
    values must leave the service holding none -- if a prior connection's values
    leaked, this is where it would show.
    """
    service = _make_service()

    # Connection 1: client sends field values.
    service.update_schema(SCHEMA, current_values=CLIENT_VALUES, fill_language="English")

    # Disconnect: the per-connection handshake state is the only thing that
    # carried values, and the next handshake overwrites it.
    # Connection 2 (reconnect): empty values, as a fresh client handshake would.
    service.update_schema(SCHEMA, current_values={}, fill_language="English")

    assert "Jdoe-SECRET-VALUE" not in _service_state_blob(service)


def test_a_second_distinct_value_set_replaces_not_accumulates():
    """Re-handshaking with DIFFERENT values must not accumulate the prior set.

    Even if a future change started caching the latest handshake's values, it must
    never let an EARLIER connection's values persist -- otherwise cross-connection
    state leaks. With the current stateless contract, neither set is retained.
    """
    service = _make_service()

    service.update_schema(SCHEMA, current_values={"f1": {"value": "FIRST-CONN"}}, fill_language="English")
    service.update_schema(SCHEMA, current_values={"f1": {"value": "SECOND-CONN"}}, fill_language="English")

    blob = _service_state_blob(service)
    assert "FIRST-CONN" not in blob
    assert "SECOND-CONN" not in blob


def test_fields_view_derives_from_schema_only_not_stored_values():
    """The service's view of fields comes from the SCHEMA, never from stored values."""
    service = _make_service()
    service.update_schema(SCHEMA, current_values=CLIENT_VALUES, fill_language="English")

    # _build_fields_from_schema() delegates to build_fields_from_schema(self._schema)
    # -- structural, derived from the schema, carrying no field values.
    fields = service._build_fields_from_schema()
    blob = repr(fields)
    assert "Jdoe-SECRET-VALUE" not in blob
