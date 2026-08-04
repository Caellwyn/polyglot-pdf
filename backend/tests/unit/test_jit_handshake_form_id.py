"""form_id must survive the manifest-first (JIT) handshake (bd polyglot-pdf-n0em).

FOUND IN PRODUCTION: the first real deployed W-7 voice run wrote 31
`field_confirmed` events to the durable Firestore sink, every one carrying
`form_id="unknown"` instead of "W-7". The confirmation trail exists for
liability protection, and a record that cannot name the form is materially
weaker evidence -- field ids alone do not identify the form to a third party,
and cross-form field-id collisions grow with the kit catalogue.

Root cause: `FormFillingService.start_session` derives
`form_id = schema["form_metadata"]["form_number"]`, but on the manifest-first
transport (the SHIPPED DEFAULT -- USE_DTI/CONTINUOUS_SESSION default true) the
handshake carries a manifest + first_field_schema, NOT the full schema, so
`form_metadata` was absent and the "unknown" fallback fired.

The fix threads `form_number` through the JIT handshake alongside `form_title`.
These tests pin the backend half: the minimal schema the route builds must
carry `form_metadata.form_number` so the audit lookup resolves.
"""
import backend.routes.websocket_routes as wsr


def _build_jit_schema(handshake: dict) -> dict:
    """Reproduce the route's JIT minimal-schema construction.

    Mirrors the `is_jit_mode` branch of `_handle_fill_session` so the shape
    under test is the one the route actually builds, without standing up a
    WebSocket. If the route's construction changes, this helper must change
    with it -- see the parity assertion in
    test_route_source_still_builds_form_metadata_from_both_keys.
    """
    manifest = handshake.get("manifest")
    first_field_schema = handshake.get("first_field_schema")
    loaded_field_ids = handshake.get("loaded_field_ids", [])
    jit_form_title = handshake.get("form_title")
    jit_form_number = handshake.get("form_number")

    schema = {
        "source": "web",
        "fields": [first_field_schema] if first_field_schema else [],
        "manifest": manifest,
        "loaded_field_ids": loaded_field_ids,
        "jit_mode": True,
        "parts": manifest.get("parts", []) if manifest else [],
    }
    if jit_form_title or jit_form_number:
        schema["form_metadata"] = {}
        if jit_form_title:
            schema["form_metadata"]["title"] = jit_form_title
        if jit_form_number:
            schema["form_metadata"]["form_number"] = jit_form_number
    return schema


def _derive_form_id(schema: dict) -> str:
    """The exact lookup FormFillingService.start_session performs."""
    return schema.get("form_metadata", {}).get("form_number", "unknown") if schema else "unknown"


def test_jit_handshake_carrying_form_number_yields_real_form_id():
    """The regression: a W-7 session must log form_id='W-7', never 'unknown'."""
    schema = _build_jit_schema({
        "manifest": {"parts": []},
        "form_title": "Application for IRS Individual Taxpayer Identification Number",
        "form_number": "W-7",
    })
    assert schema["form_metadata"]["form_number"] == "W-7"
    assert _derive_form_id(schema) == "W-7"


def test_form_number_and_title_are_distinct_keys():
    """form_title is a human label; form_number is the audit identifier.

    Pinning both guards against a 'simplification' that collapses them -- the
    trail would then record a prose title where an identifier belongs.
    """
    schema = _build_jit_schema({
        "manifest": {"parts": []},
        "form_title": "Application for IRS Individual Taxpayer Identification Number",
        "form_number": "W-7",
    })
    assert schema["form_metadata"]["title"] != schema["form_metadata"]["form_number"]
    assert _derive_form_id(schema) == "W-7"


def test_title_only_handshake_still_builds_metadata_and_degrades_to_unknown():
    """An OLDER client that omits form_number must not crash or lose the title.

    Deployed clients update independently of the backend, so the pre-fix
    handshake shape has to keep working -- it simply degrades to the old
    'unknown' audit value rather than erroring.
    """
    schema = _build_jit_schema({
        "manifest": {"parts": []},
        "form_title": "Some Form",
    })
    assert schema["form_metadata"] == {"title": "Some Form"}
    assert _derive_form_id(schema) == "unknown"


def test_form_number_only_handshake_builds_metadata():
    """form_metadata must be built when ONLY form_number is present.

    The pre-fix code keyed construction on the title alone, so a
    title-less handshake produced no form_metadata at all and the audit id was
    lost even when the number had been sent.
    """
    schema = _build_jit_schema({"manifest": {"parts": []}, "form_number": "I-90"})
    assert schema["form_metadata"] == {"form_number": "I-90"}
    assert _derive_form_id(schema) == "I-90"


def test_neither_key_leaves_form_metadata_absent():
    """No metadata keys -> no form_metadata (unchanged legacy behavior)."""
    schema = _build_jit_schema({"manifest": {"parts": []}})
    assert "form_metadata" not in schema
    assert _derive_form_id(schema) == "unknown"


def test_route_source_still_builds_form_metadata_from_both_keys():
    """Guard the helper-vs-route parity this module's other tests rely on.

    The tests above exercise a REPRODUCTION of the route's construction. If the
    route stops reading `form_number` (a revert, or a refactor that drops the
    key), those tests would still pass against the stale helper while
    production silently regressed to form_id="unknown". This asserts the real
    source still does both halves: reads the handshake key AND writes it into
    form_metadata.
    """
    import inspect

    source = inspect.getsource(wsr)
    assert 'handshake.get("form_number")' in source, (
        "the JIT handshake no longer reads form_number -- the confirmation "
        "audit trail will regress to form_id='unknown' (bd polyglot-pdf-n0em)"
    )
    assert '["form_number"] = jit_form_number' in source, (
        "form_number is read but no longer written into form_metadata, so the "
        "audit lookup cannot resolve it (bd polyglot-pdf-n0em)"
    )
