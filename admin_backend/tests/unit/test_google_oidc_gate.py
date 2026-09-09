"""admin_backend/services/admin_auth.py's require_google_oidc + its
verification seam _verify_google_id_token (bd polyglot-pdf-8vgfh).

Mirrors test_admin_auth.py's verifier-level coverage style: a fake stands in
for google.auth's HTTP-verifying call so the two things otherwise invisible
to a test (which audience/certs endpoint it hit, whether it raised) are
actually pinned. test_sweep_routes.py exercises the SAME gate through the
real route and a real (fake-Firestore) mutation; this file is about the
GATE's own contract in isolation -- lazy config resolution, the 401 vs 403
vs 503 split, and the two-factor (audience + allowlisted email) property
that is this gate's whole reason to exist over a bare audience check.

ASCII only.
"""
import asyncio

import pytest
from fastapi import HTTPException

import admin_backend.services.admin_auth as aa
from admin_backend.services.admin_auth import (
    NO_ADMIN_ACCESS_PREFIX,
    GoogleServiceActor,
    OidcVerificationUnavailable,
    require_google_oidc,
)

SCHEDULER_EMAIL = "scheduler-sa@test-project.iam.gserviceaccount.com"
OTHER_EMAIL = "someone-else@other-project.iam.gserviceaccount.com"
AUDIENCE = "https://polyglot-admin-test.a.run.app/admin/links/sweep-expired"


def _run(coro):
    return asyncio.run(coro)


def _fake_verify(monkeypatch, claims=None, raises=None):
    """Stand in for admin_auth._verify_google_id_token, recording the
    audience it was called with so a test can pin that the RESOLVED
    audience (not the factory's raw argument) is what reaches verification."""
    calls = {"audience": None, "token": None}

    def _verify(token, audience):
        calls["audience"] = audience
        calls["token"] = token
        if raises is not None:
            raise raises
        return claims

    monkeypatch.setattr(aa, "_verify_google_id_token", _verify)
    return calls


# --- exit criterion 2: right audience wrong email is 403; no token is 401 -


def test_a_verified_allowlisted_caller_resolves_to_a_google_service_actor(
        monkeypatch):
    """Mutation: flip the allowlist membership check to `not in` -- this
    goes red (the allowed caller would be refused)."""
    _fake_verify(monkeypatch, {
        "email": SCHEDULER_EMAIL, "email_verified": True})
    gate = require_google_oidc(
        audience=AUDIENCE, allowed_caller_emails=(SCHEDULER_EMAIL,))
    actor = _run(gate(authorization="Bearer valid-token"))
    assert isinstance(actor, GoogleServiceActor)
    assert actor.email == SCHEDULER_EMAIL


def test_a_verified_but_not_allowlisted_caller_is_403_with_the_prefix(
        monkeypatch):
    """THE TWO-FACTOR PROPERTY. A token that verifies perfectly (right
    signature, right audience) but names a DIFFERENT email is not the
    scheduler job this route accepts. Mutation: drop the `email not in
    allowed_caller_emails` half of the guard, leaving only the
    email_verified check -- ANY verified Google service token would then
    pass, defeating the whole reason this gate checks email at all (see the
    module's own "WHY AUDIENCE ALONE DOES NOT PROVE THE CALLER" section)."""
    _fake_verify(monkeypatch, {"email": OTHER_EMAIL, "email_verified": True})
    gate = require_google_oidc(
        audience=AUDIENCE, allowed_caller_emails=(SCHEDULER_EMAIL,))
    with pytest.raises(HTTPException) as exc:
        _run(gate(authorization="Bearer valid-token"))
    assert exc.value.status_code == 403
    assert str(exc.value.detail).startswith(NO_ADMIN_ACCESS_PREFIX)


def test_no_authorization_header_is_401(monkeypatch):
    gate = require_google_oidc(
        audience=AUDIENCE, allowed_caller_emails=(SCHEDULER_EMAIL,))
    with pytest.raises(HTTPException) as exc:
        _run(gate(authorization=None))
    assert exc.value.status_code == 401


def test_a_non_bearer_authorization_header_is_401(monkeypatch):
    """Mutation: drop the `.startswith("Bearer ")` check -- a Basic-auth
    header would then be sliced as if it were a bearer token and passed to
    verification with garbage, which could raise a DIFFERENT exception
    shape than the clean 401 this test pins."""
    gate = require_google_oidc(
        audience=AUDIENCE, allowed_caller_emails=(SCHEDULER_EMAIL,))
    with pytest.raises(HTTPException) as exc:
        _run(gate(authorization="Basic dXNlcjpwYXNz"))
    assert exc.value.status_code == 401


def test_a_token_that_fails_verification_is_401_not_403(monkeypatch):
    """A bad signature / expired / wrong-audience token never even reaches
    the allowlist check -- it is 401 (retrying with a fresh token might
    help), distinctly from the 403 a verified-but-disallowed caller gets.
    Mutation: catch ValueError and raise 403 -- this goes red."""
    _fake_verify(monkeypatch, raises=ValueError("bad signature"))
    gate = require_google_oidc(
        audience=AUDIENCE, allowed_caller_emails=(SCHEDULER_EMAIL,))
    with pytest.raises(HTTPException) as exc:
        _run(gate(authorization="Bearer bad-token"))
    assert exc.value.status_code == 401


def test_an_unverified_email_claim_is_refused_even_if_the_address_matches(
        monkeypatch):
    """email_verified is not True -> refused, even when the email string
    itself is on the allowlist. A service-account token's email is ALWAYS
    verified by construction; a token claiming otherwise is malformed or
    not actually a service-account token, either way not one this gate
    should accept. Mutation: drop the email_verified check entirely --
    this test goes red."""
    _fake_verify(monkeypatch, {
        "email": SCHEDULER_EMAIL, "email_verified": False})
    gate = require_google_oidc(
        audience=AUDIENCE, allowed_caller_emails=(SCHEDULER_EMAIL,))
    with pytest.raises(HTTPException) as exc:
        _run(gate(authorization="Bearer valid-token"))
    assert exc.value.status_code == 403


# --- fail-closed configuration + verification-unavailable handling --------


def test_verification_unavailable_is_503_not_401(monkeypatch):
    """The certs endpoint could not be reached (or google-auth is not
    importable): the caller may be legitimate and retrying might work, so
    this must be 503, never 401 (a 401 tells Cloud Scheduler its identity
    is bad, which is false) and never a silent pass-through. Mutation:
    catch OidcVerificationUnavailable the same way as ValueError (both ->
    401) -- this goes red."""
    _fake_verify(monkeypatch, raises=OidcVerificationUnavailable("no net"))
    gate = require_google_oidc(
        audience=AUDIENCE, allowed_caller_emails=(SCHEDULER_EMAIL,))
    with pytest.raises(HTTPException) as exc:
        _run(gate(authorization="Bearer some-token"))
    assert exc.value.status_code == 503


def test_an_empty_audience_refuses_with_503_never_falls_through(monkeypatch):
    """An unconfigured audience must refuse EVERY caller, not verify
    against an empty string (which google-auth might treat as "do not
    check the audience at all" -- see verify_oauth2_token's own
    audience=None meaning). Mutation: change the empty-check from `not
    resolved_audience` to `resolved_audience is None` -- an empty STRING
    (as opposed to a missing env var read as "") would then fall through to
    verification instead of refusing."""
    calls = _fake_verify(monkeypatch, {
        "email": SCHEDULER_EMAIL, "email_verified": True})
    gate = require_google_oidc(
        audience="", allowed_caller_emails=(SCHEDULER_EMAIL,))
    with pytest.raises(HTTPException) as exc:
        _run(gate(authorization="Bearer valid-token"))
    assert exc.value.status_code == 503
    assert calls["audience"] is None, (
        "verification must never even be attempted against an empty "
        "audience")


def test_an_empty_allowlist_refuses_with_503_never_falls_through(monkeypatch):
    """Mirrors the audience case: SWEEP_SCHEDULER_SA_EMAIL unset resolves to
    an empty tuple, which must refuse rather than be read as "no allowlist,
    accept anyone"."""
    _fake_verify(monkeypatch, {
        "email": SCHEDULER_EMAIL, "email_verified": True})
    gate = require_google_oidc(audience=AUDIENCE, allowed_caller_emails=())
    with pytest.raises(HTTPException) as exc:
        _run(gate(authorization="Bearer valid-token"))
    assert exc.value.status_code == 503


def test_audience_and_allowlist_accept_callables_resolved_per_request(
        monkeypatch):
    """The lazy-resolution contract: a route wires require_google_oidc with
    FUNCTIONS (env-var readers), not resolved strings, because the route
    module imports before deploy-time env vars are guaranteed to be set.
    Mutation: call `audience` and `allowed_caller_emails` directly instead
    of through _resolve's `callable(value)` check -- a callable passed in
    would then be compared/used as a function object instead of invoked,
    and this test's audience assertion would fail loudly rather than
    silently, but the POINT this pins is that changing the underlying
    value between requests (as an env var changing at runtime would)
    actually takes effect without rebuilding the gate."""
    calls = _fake_verify(monkeypatch, {
        "email": SCHEDULER_EMAIL, "email_verified": True})
    state = {"audience": "https://first.example/route"}
    gate = require_google_oidc(
        audience=lambda: state["audience"],
        allowed_caller_emails=lambda: (SCHEDULER_EMAIL,),
    )
    _run(gate(authorization="Bearer valid-token"))
    assert calls["audience"] == "https://first.example/route"

    state["audience"] = "https://second.example/route"
    _run(gate(authorization="Bearer valid-token"))
    assert calls["audience"] == "https://second.example/route", (
        "a callable audience must be re-read on every request, not cached "
        "from the first call")


# --- the FACTORY's returned closure must present as require_google_oidc --


def test_the_returned_dependency_is_named_require_google_oidc():
    """test_admin_route_auth.py's route/gate set pin reads a dependency's
    bare __name__ to learn which of the four known gates a route carries.
    require_google_oidc is a FACTORY: the callable FastAPI actually wires is
    an inner closure, which Python would otherwise name "_dependency". This
    pins the rename that keeps the two test files' detection uniform across
    all four gates. Mutation: delete the `_dependency.__name__ =
    "require_google_oidc"` line in admin_auth.py -- this goes red, and so
    does test_admin_route_auth.py's set pin for the sweep route."""
    gate = require_google_oidc(
        audience=AUDIENCE, allowed_caller_emails=(SCHEDULER_EMAIL,))
    assert gate.__name__ == "require_google_oidc"


# --- _verify_google_id_token's own error-classification seam --------------


def test_verify_raises_verification_unavailable_when_google_auth_missing(
        monkeypatch):
    """A broken dependency install (google-auth not importable) must be
    503-shaped (OidcVerificationUnavailable), never surfaced as a plain
    ImportError that would 500 the route."""
    import builtins

    real_import = builtins.__import__

    def _blocking_import(name, *args, **kwargs):
        if name in ("google.auth.transport", "google.oauth2"):
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocking_import)
    with pytest.raises(OidcVerificationUnavailable):
        aa._verify_google_id_token("t", AUDIENCE)


def test_verify_raises_value_error_on_a_bad_token_via_the_real_library(
        monkeypatch):
    """Exercises the REAL google.oauth2.id_token.verify_oauth2_token call
    path (not a fake) with an actually-malformed token, to prove the
    library's own failure surfaces as ValueError (which require_google_oidc
    maps to 401) rather than propagating some other exception type this
    module does not know how to classify. A garbage string can never
    produce a valid JWT structure, so this needs no network access -- the
    library rejects it before any certs fetch."""
    with pytest.raises(ValueError):
        aa._verify_google_id_token("not-a-real-jwt", AUDIENCE)
