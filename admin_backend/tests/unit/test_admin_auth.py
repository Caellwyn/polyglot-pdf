"""admin_backend/services/admin_auth.py verifier unit tests (bd
polyglot-pdf-7w17m).

Mirrors backend/tests/unit/test_editor_identity.py's verifier-level coverage
(NOT its route-attribution tests -- this bead ships no mutating route). A
fake firebase_admin module stands in for the SDK throughout, RECORDING what
it was asked so the two guards that are otherwise invisible to a test
(check_revoked, and the self-init) are actually pinned rather than merely
exercised.
"""
import sys
import types

import pytest
from fastapi import HTTPException

import admin_backend.services.admin_auth as aa
from admin_backend.services.admin_auth import (
    APP_ADMIN_CLAIM,
    NO_ADMIN_ACCESS_PREFIX,
    AdminActor,
    require_app_admin,
    verify_admin_token,
)


def _fake_firebase(monkeypatch, claims=None, raises=None, already_inited=True):
    """Stand in for firebase_admin.auth with a fixed decoded token.

    Mirrors test_editor_identity.py's _fake_firebase: records check_revoked
    and initialize_app call counts, since both guards are otherwise invisible
    to a test that merely returns a fixed claims dict.
    """
    calls = {"check_revoked": None, "initialize_app": 0}

    class _Auth:
        @staticmethod
        def verify_id_token(_tok, check_revoked=False):
            calls["check_revoked"] = check_revoked
            if raises is not None:
                raise raises
            return claims

    mod = types.ModuleType("firebase_admin")
    mod.auth = _Auth
    mod._apps = {"[DEFAULT]": object()} if already_inited else {}

    def _init(*_a, **_k):
        calls["initialize_app"] += 1
        mod._apps["[DEFAULT]"] = object()

    mod.initialize_app = _init
    monkeypatch.setitem(sys.modules, "firebase_admin", mod)
    monkeypatch.setattr(aa, "_dev_bypass_allowed", lambda: False)
    return calls


def _run(coro):
    import asyncio

    return asyncio.run(coro)


# --- exit criterion 1: stamped passes, unstamped 403s, tokenless 401s ------


def test_a_stamped_account_resolves_to_an_admin_actor(monkeypatch):
    """Mutation: flip the APP_ADMIN_CLAIM check from `is not True` to a
    truthy check -- this alone stays green (True is truthy), so the real
    guard is the NEXT test's non-boolean-truthy value."""
    _fake_firebase(monkeypatch, {"uid": "uid-ada", "email": "ada@example.com",
                                 APP_ADMIN_CLAIM: True})
    actor = verify_admin_token("t")
    assert actor.uid == "uid-ada"
    assert actor.email == "ada@example.com"


def test_a_valid_unstamped_account_gets_403_with_the_prefix(monkeypatch):
    """The account is real and verifies, but carries no app_admin claim.
    Mutation: drop the NO_ADMIN_ACCESS_PREFIX concatenation -- red."""
    _fake_firebase(monkeypatch, {"uid": "uid-bo", "email": "bo@example.com"})
    with pytest.raises(HTTPException) as exc:
        verify_admin_token("t")
    assert exc.value.status_code == 403
    assert str(exc.value.detail).startswith(NO_ADMIN_ACCESS_PREFIX)


def test_a_non_boolean_truthy_claim_value_is_refused(monkeypatch):
    """app_admin is documented as BOOLEAN. A claim holding a truthy non-True
    value (a stray string, an old numeric scheme) must not pass -- `is not
    True` is stricter than a bare truthiness check on purpose. Mutation:
    change the guard to `if not claims.get(APP_ADMIN_CLAIM):` -- this test
    goes red because "yes" is truthy."""
    _fake_firebase(monkeypatch, {"uid": "uid-x", APP_ADMIN_CLAIM: "yes"})
    with pytest.raises(HTTPException) as exc:
        verify_admin_token("t")
    assert exc.value.status_code == 403
    assert str(exc.value.detail).startswith(NO_ADMIN_ACCESS_PREFIX)


def test_no_token_via_the_dependency_is_401(monkeypatch):
    """require_app_admin with no Authorization header at all."""
    monkeypatch.setattr(aa, "_dev_bypass_allowed", lambda: False)
    with pytest.raises(HTTPException) as exc:
        _run(require_app_admin(authorization=None))
    assert exc.value.status_code == 401


def test_a_garbage_token_is_401_not_a_crash(monkeypatch):
    """An invalid/expired token must 401, never surface the SDK's internal
    exception shape to the caller."""
    _fake_firebase(monkeypatch, raises=ValueError("bad token"))
    with pytest.raises(HTTPException) as exc:
        verify_admin_token("garbage")
    assert exc.value.status_code == 401


def test_a_verified_token_with_no_subject_is_refused(monkeypatch):
    _fake_firebase(monkeypatch, {"email": "ghost@example.com",
                                 APP_ADMIN_CLAIM: True})
    with pytest.raises(HTTPException) as exc:
        verify_admin_token("t")
    assert exc.value.status_code == 401


# --- the underlying SDK-interaction guards ----------------------------------


def test_the_verifier_does_NOT_ask_firebase_to_check_revocation(monkeypatch):
    """Mirrors editor_auth's scar: check_revoked forces a Firebase
    USER-RECORD FETCH (firebaseauth.users.get). This service's SA DOES hold
    that permission (unlike the public backend / editor), but the verifier
    stays symmetric with its siblings until a real need is measured (module
    docstring). Mutation: pass check_revoked=True -- red."""
    calls = _fake_firebase(monkeypatch, {"uid": "uid-ada",
                                         "email": "ada@example.com",
                                         APP_ADMIN_CLAIM: True})
    verify_admin_token("t")
    assert calls["check_revoked"] is False


def test_the_admin_service_initialises_firebase_itself_when_nothing_has(
        monkeypatch):
    calls = _fake_firebase(monkeypatch, {"uid": "uid-ada",
                                         "email": "ada@example.com",
                                         APP_ADMIN_CLAIM: True},
                           already_inited=False)
    verify_admin_token("t")
    assert calls["initialize_app"] == 1


def test_an_already_initialised_app_is_not_re_initialised(monkeypatch):
    calls = _fake_firebase(monkeypatch, {"uid": "uid-ada",
                                         "email": "ada@example.com",
                                         APP_ADMIN_CLAIM: True},
                           already_inited=True)
    verify_admin_token("t")
    assert calls["initialize_app"] == 0


# --- the dev bypass ----------------------------------------------------------


def test_the_dev_bypass_is_refused_on_a_deployed_instance(monkeypatch):
    monkeypatch.setenv("VFF_DISABLE_AUTH", "true")
    monkeypatch.setenv("K_SERVICE", "admin-backend")
    assert aa._dev_bypass_allowed() is False

    monkeypatch.delenv("K_SERVICE", raising=False)
    assert aa._dev_bypass_allowed() is True


def test_the_bypass_works_with_no_header_via_the_dependency(monkeypatch):
    monkeypatch.setattr(aa, "_dev_bypass_allowed", lambda: True)
    actor = _run(require_app_admin(authorization=None))
    assert isinstance(actor, AdminActor)
    assert actor.label()


def test_the_bypass_is_checked_before_the_header_is_read(monkeypatch):
    """A local caller sending NO header must still pass under the bypass --
    same trap editor_auth's require_editor_actor fixed (checking the bypass
    behind the header check made a header-less local request 401 even with
    the bypass on)."""
    monkeypatch.setattr(aa, "_dev_bypass_allowed", lambda: True)
    actor = _run(require_app_admin(authorization=None))
    assert actor.uid == "dev_admin"


def test_a_real_token_still_works_when_the_bypass_is_off(monkeypatch):
    monkeypatch.setenv("VFF_DISABLE_AUTH", "false")
    _fake_firebase(monkeypatch, {"uid": "uid-ada", "email": "ada@example.com",
                                 APP_ADMIN_CLAIM: True})
    actor = _run(require_app_admin(authorization="Bearer t"))
    assert actor.uid == "uid-ada"


# --- AdminActor.label() ------------------------------------------------------


def test_label_prefers_email_but_falls_back_to_uid():
    with_email = AdminActor(uid="u1", email="ada@example.com")
    assert with_email.label() == "ada@example.com"

    no_email = AdminActor(uid="u2")
    assert no_email.label() == "u2"


# --- isolation from the other two claim namespaces --------------------------


def test_the_admin_claim_is_not_shared_with_editor_or_voice(monkeypatch):
    """If APP_ADMIN_CLAIM ever collided with EDITOR_ROLE_CLAIM or a voice-app
    claim name, granting one would silently grant the other."""
    from backend.services.editor_auth import EDITOR_ROLE_CLAIM

    assert APP_ADMIN_CLAIM == "app_admin"
    assert APP_ADMIN_CLAIM not in ("firm_id", "firm_role", EDITOR_ROLE_CLAIM)


def test_a_voice_app_or_editor_account_gets_no_admin_access(monkeypatch):
    """A fully valid account from either sibling surface -- real uid, real
    email, real claims for THAT surface -- is refused here because it carries
    no app_admin claim."""
    _fake_firebase(monkeypatch, {"uid": "uid-x", "email": "x@example.com",
                                 "firm_id": "acme", "firm_role": "manager",
                                 "schema_editor_role": "editor"})
    with pytest.raises(HTTPException) as exc:
        verify_admin_token("t")
    assert exc.value.status_code == 403
    assert str(exc.value.detail).startswith(NO_ADMIN_ACCESS_PREFIX)


def test_admin_auth_does_not_import_the_other_two_auth_modules():
    """Keeps this surface liftable, same constraint editor_auth documents for
    itself relative to backend.services.auth."""
    text = open(aa.__file__, encoding="utf-8").read()
    assert "from backend.services.auth import" not in text
    assert "import backend.services.auth" not in text
    assert "from backend.services.editor_auth import" not in text
    assert "import backend.services.editor_auth" not in text
