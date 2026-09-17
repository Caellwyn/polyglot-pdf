"""Shared pytest fixtures for the backend test suite."""

import os

import pytest

from backend.tests.unit._no_real_firestore import install_no_real_firestore_guard

# bd polyglot-pdf-5xhbb: strip K_SERVICE from the process environment as soon
# as conftest.py is imported -- BEFORE pytest collects any test module. A
# per-test autouse fixture (see _isolate_k_service below) runs too late for
# this: several test files import backend.main at module scope (e.g.
# test_http_route_auth.py:20 -> backend/main.py -> backend/routes/
# websocket_routes.py:18's `settings = get_settings()`), so an ambient
# K_SERVICE + VFF_DISABLE_AUTH=true aborts COLLECTION with a pydantic
# ValidationError before any fixture ever runs (reproduced: `K_SERVICE=...
# VFF_DISABLE_AUTH=true pytest backend/tests/unit/test_http_route_auth.py`
# -> "Interrupted: 1 error during collection" even with the fixture present).
# This module-level delenv runs at IMPORT time, ahead of every collection
# import in this session, which is the only point early enough to prevent
# that. The per-test fixture below stays as defense-in-depth for the (rarer)
# case where something re-sets K_SERVICE mid-session outside a test's own
# monkeypatch.
os.environ.pop("K_SERVICE", None)
# Sprint 23 PF-5 (bd o2fub): the per-instance limiter keys on the caller
# address, and TestClient is ONE address hitting the same doors hundreds of
# times per run. Off for the suite; backend/tests/unit/test_rate_limit.py
# turns it on per test with a tiny budget.
# The default is read when backend.config is IMPORTED (a class-body default),
# and this conftest runs before any test module imports it. tests/ and
# admin_backend/tests/ set the same default in their own conftests.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")


@pytest.fixture(autouse=True)
def _isolate_confirmation_logs(tmp_path, monkeypatch):
    """Redirect confirmation-audit logs to a per-test tmp dir.

    The confirmation logger writes one JSONL file per form session
    (see backend/utils/confirmation_logger.py). Without this, any test that
    exercises field confirmation (e.g. test_section_switching) would append to
    the repo's real `logs/confirmations/` tree and dirty the working tree on
    every run. Pointing CONFIRMATION_LOG_DIR at tmp_path keeps tests hermetic
    and keeps real confirmation logs out of git.
    """
    monkeypatch.setenv("CONFIRMATION_LOG_DIR", str(tmp_path / "confirmations"))


@pytest.fixture(autouse=True)
def _isolate_k_service(monkeypatch):
    """Strip K_SERVICE so a bare Settings() in a test never inherits a
    deployed-service identity from the ambient shell (bd polyglot-pdf-5xhbb).

    backend/config.py's _resolve_model keys two fail-closed guards off
    os.getenv('K_SERVICE') -- the VERTEXAI guard (bd polyglot-pdf-5e6a) and
    the VFF_DISABLE_AUTH guard (bd polyglot-pdf-knmp). Cloud Run sets this
    var; a local shell normally does not, but nothing pinned that, so a
    containerized/CI-in-Cloud-Run run (or any operator who happens to export
    it) would silently flip guard tests that assume it is absent. Tests that
    deliberately exercise the deployed path still work: they call
    monkeypatch.setenv('K_SERVICE', ...) themselves, which layers over (and
    wins against) this fixture's delenv.

    This is defense-in-depth for TEST-TIME Settings() construction; the
    COLLECTION-time exposure (module-scope get_settings() calls, e.g.
    websocket_routes.py:18) is closed by the module-level os.environ.pop
    above, which runs before this fixture -- or any fixture -- ever could.
    """
    monkeypatch.delenv("K_SERVICE", raising=False)


@pytest.fixture(autouse=True)
def _no_real_firestore(monkeypatch, request):
    """Fail loudly on any unpatched real-Firestore reach (bd polyglot-pdf-21m1y).

    2026-09-15: backend tests on a developer machine with gcloud ADC and a
    quota project silently wrote 149+ real documents into the shared demo
    project (see the bead body for the inventory) because the stores under
    backend/services/ (alerts, usage_rollups, link_redemptions, links_store,
    credit_ledger) lazily initialize firebase_admin with ADC and construct a
    real google.cloud.firestore.Client the moment a test exercises them
    without patching the store. See backend/tests/unit/_no_real_firestore.py
    for exactly what is patched, why both targets are needed, and why every
    EXISTING store test is untouched by this (they all patch above this
    seam, at get_db()/_collection()/_get_db()).

    OPT OUT: @pytest.mark.external, same marker that already gates the two
    tests requiring the real Gemini Live API.
    """
    install_no_real_firestore_guard(monkeypatch, request)


# bd polyglot-pdf-hn0jq: the editor moved from two shared tokens to per-user
# Firebase identity. 28 test files mount the editor router, and every one of
# them authenticates by sending an X-Editor-Token header -- so without a shim
# they all 401. Rewriting 28 files' auth would be churn; overriding the
# dependency once here is the same trick a single test file was using, hoisted
# to where every file gets it.
#
# bd polyglot-pdf-rhc2v then DELETED that header from the production dependency,
# which broke the shim's other half: patching verify_editor_token is useless if
# nothing reads the header that would call it, and ~225 tests 401'd. So the
# shim now also TRANSLATES the header the suite sends into the
# `Authorization: Bearer` a real client sends (see _editor_bearer_shim). That is
# strictly better than it sounds: the tests now travel the SAME code path
# production does, instead of a retired one kept alive for their benefit.
#
# The two tokens the suite already sends become two DISTINCT PEOPLE, which is
# strictly closer to reality than the shared secret they modelled before.
#
# The second editor and second author exist so SAME-ROLE contention is testable
# at all (bd polyglot-pdf-5tuas: editor B is refused a kit editor A holds, and
# an author can still take it back from another author). The note above used to
# claim tests needing "another editor" had one -- with only two identities that
# was aspirational; these make it true.
_TEST_PEOPLE = {
    "edit-tok": ("uid-maria", "maria@example.com", "editor"),
    "auth-tok": ("uid-josh", "josh@example.com", "author"),
    "edit2-tok": ("uid-sam", "sam@example.com", "editor"),
    "auth2-tok": ("uid-dana", "dana@example.com", "author"),
}


@pytest.fixture(autouse=True)
def _editor_actor_auth(monkeypatch, request):
    """Resolve the suite's X-Editor-Token values to per-user actors.

    Patches the verifier rather than the FastAPI dependency, so it reaches BOTH
    apps built with TestClient AND tests that call a route function directly.
    Anything other than a known token still raises 401, so the tests that
    assert a rejection keep asserting one.
    """
    # OPT OUT with @pytest.mark.real_editor_auth. A test of the verifier ITSELF
    # must run against the real function -- otherwise this shim silently answers
    # for it and the test passes without exercising a line of the code it names.
    if request.node.get_closest_marker("real_editor_auth"):
        return

    from fastapi import HTTPException

    import backend.services.editor_auth as ea

    def _fake_verify(token: str):
        person = _TEST_PEOPLE.get(token or "")
        if person is None:
            raise HTTPException(status_code=401,
                                detail="Invalid or missing access code")
        uid, email, role = person
        return ea.EditorActor(uid=uid, email=email, role=role)

    monkeypatch.setattr(ea, "verify_editor_token", _fake_verify)

    monkeypatch.setattr(ea, "_dev_bypass_allowed", lambda: False)


def bearerize_headers(headers):
    """Rewrite an X-Editor-Token header into `Authorization: Bearer <token>`.

    Module-level rather than a closure inside the fixture SO A TEST CAN IMPORT
    IT. A test that re-implements this logic guards a copy, and a copy drifts --
    which is exactly how the shape bug below would come back unnoticed.

    SHAPE-AGNOSTIC: httpx accepts a mapping OR a list of (name, value) pairs,
    and the fixture is autouse across the WHOLE backend suite -- so a future
    non-editor test using the list form would otherwise crash with an
    AttributeError raised from conftest, nowhere near its own subject
    (cross-surface review, bd polyglot-pdf-rhc2v).

    An existing Authorization always wins: this fills a gap, never overrides a
    credential a test deliberately set.
    """
    pairs = (list(headers.items()) if hasattr(headers, "items")
             else list(headers))
    token = next((v for k, v in pairs
                  if str(k).lower() == "x-editor-token"), None)
    has_auth = any(str(k).lower() == "authorization" for k, _ in pairs)
    if not token or has_auth:
        return headers
    # Preserve the caller's shape: a list stays a list, so a test sending
    # duplicate header names does not silently lose one.
    if hasattr(headers, "items"):
        out = dict(headers)
        out["Authorization"] = f"Bearer {token}"
        return out
    return list(headers) + [("Authorization", f"Bearer {token}")]


@pytest.fixture(autouse=True)
def _editor_bearer_shim(monkeypatch, request):
    """Let the suite keep sending X-Editor-Token after the header was retired.

    bd polyglot-pdf-rhc2v removed `x_editor_token` from `require_editor_actor`,
    so the header the suite has always sent now reaches nothing and every editor
    test 401s. Rather than rewrite ~225 call sites, translate at the boundary:
    if a request carries the suite's header and no Authorization, present it as
    `Authorization: Bearer <token>` -- exactly what the deployed client sends.

    THIS IS A TEST-TRANSPORT SHIM, NOT A REVIVED AUTH PATH. It lives in
    conftest, never in backend/, so the server itself still accepts one header
    only -- `test_the_RETIRED_X_Editor_Token_header_is_refused` asserts the
    parameter is gone, and it runs under `real_editor_auth` so this shim cannot
    answer for it.
    """
    if request.node.get_closest_marker("real_editor_auth"):
        return

    import starlette.testclient as _tc

    original = _tc.TestClient.request

    def _request(self, method, url, *args, **kwargs):
        headers = kwargs.get("headers")
        if headers:
            kwargs["headers"] = bearerize_headers(headers)
        return original(self, method, url, *args, **kwargs)

    monkeypatch.setattr(_tc.TestClient, "request", _request)


@pytest.fixture(autouse=True)
def _reset_acceptance_dedupe():
    """Clear the disclaimer-acceptance dedupe between tests (bd polyglot-pdf-g3kui).

    log_disclaimer_acceptance keeps MODULE-LEVEL state: the first acceptance for
    a form_session_id writes, later ones are silently dropped. Without this
    reset, a test whose session id another test already used has its write
    dropped and then passes or fails depending on COLLECTION ORDER -- the
    ordering flake this repo has been bitten by before.

    It lives HERE rather than in one test file because TWO files reach this
    path: test_confirmation_firestore_sink.py calls the writer directly, and 6
    of the 12 test functions in test_disclaimer_acceptance_route.py post a real
    body without mocking the writer (5 of those reach the writer; the sixth is
    rejected at validation), so they populate the same set.

    SCOPE, measured rather than asserted. The existing tests do not currently
    collide: with every reset removed, all 93 still pass in both file orders,
    because the ids in use happen to differ. But the leak is REAL and I
    reproduced it -- two tests writing the same session id, with no reset, and
    the second write is silently dropped; with this fixture, both land.

    So the failure it prevents is live, not hypothetical, and it is the worst
    shape: SILENT (a dropped write looks like a passing test asserting nothing)
    and order-dependent. A test added later that reuses an existing session id
    hits it with no obvious cause.
    """
    from backend.utils import confirmation_logger

    confirmation_logger._reset_acceptance_dedupe()
    yield
    confirmation_logger._reset_acceptance_dedupe()
