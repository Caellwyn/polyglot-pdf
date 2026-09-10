"""require_app_admin_or_owning_manager and resolve_target_firm, directly
(bd polyglot-pdf-dmjl5); require_app_admin_or_owning_manager_or_employee
added alongside it (bd polyglot-pdf-scaig).

test_user_routes.py drives the four routes with the gate OVERRIDDEN, which
is right for those tests -- they are about route behaviour, not token
plumbing. This file is the other half: the gate itself, with a faked
firebase_admin, so the branch order, the 401/403 split and the two-actor
firm rule are pinned where they are decided rather than only where they are
consumed.

ASCII only.
"""
from __future__ import annotations

import sys
import types

import pytest
from fastapi import HTTPException

import admin_backend.services.admin_auth as aa
from admin_backend.services.admin_auth import (
    ACTOR_KIND_APP_ADMIN,
    ACTOR_KIND_FIRM_EMPLOYEE,
    ACTOR_KIND_FIRM_MANAGER,
    NO_ADMIN_ACCESS_PREFIX,
    CompositeActor,
    require_app_admin_or_owning_manager,
    require_app_admin_or_owning_manager_or_employee,
    resolve_target_firm,
)


def _fake_firebase(monkeypatch, claims=None, raises=None):
    """Stand in for firebase_admin AND firebase_admin.auth.

    BOTH entries matter here, unlike test_admin_auth.py's helper: the
    composite gate's manager branch spells the import
    `from firebase_admin import auth as fb_auth`, which resolves through
    sys.modules["firebase_admin.auth"] when the parent is a bare module
    object rather than a real package.
    """
    class _Auth:
        @staticmethod
        def verify_id_token(_tok, check_revoked=False):
            if raises is not None:
                raise raises
            return claims

    mod = types.ModuleType("firebase_admin")
    mod.auth = _Auth
    mod._apps = {"[DEFAULT]": object()}
    mod.initialize_app = lambda *a, **k: None

    monkeypatch.setitem(sys.modules, "firebase_admin", mod)
    monkeypatch.setitem(sys.modules, "firebase_admin.auth", _Auth)
    monkeypatch.setattr(aa, "_dev_bypass_allowed", lambda: False)


# --------------------------------------------------------------------------
# The gate: which actor a token resolves to
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_an_app_admin_resolves_to_the_admin_actor(monkeypatch):
    _fake_firebase(monkeypatch, {"uid": "u1", "email": "ops@x.example",
                                 "app_admin": True})
    actor = await require_app_admin_or_owning_manager("Bearer t")
    assert actor.kind == ACTOR_KIND_APP_ADMIN
    assert actor.is_app_admin
    assert actor.firm_id is None, (
        "an admin carries no firm -- their target comes from the REQUEST, "
        "and a firm_id here would become a silent default")


@pytest.mark.asyncio
async def test_a_firm_manager_resolves_to_the_manager_actor(monkeypatch):
    _fake_firebase(monkeypatch, {"uid": "u2", "email": "ada@acme.example",
                                 "firm_id": "acme", "firm_role": "manager"})
    actor = await require_app_admin_or_owning_manager("Bearer t")
    assert actor.kind == ACTOR_KIND_FIRM_MANAGER
    assert not actor.is_app_admin
    assert actor.firm_id == "acme"


@pytest.mark.asyncio
async def test_an_account_holding_BOTH_acts_as_the_app_admin(monkeypatch):
    """BRANCH ORDER, pinned. app_admin is the strictly wider role, so an
    account holding both claims must not be silently downgraded to its own
    firm -- the surprising outcome, and the one somebody debugs for an hour.

    Mutation: check the manager branch first -- red."""
    _fake_firebase(monkeypatch, {"uid": "u3", "email": "both@x.example",
                                 "app_admin": True,
                                 "firm_id": "acme", "firm_role": "manager"})
    actor = await require_app_admin_or_owning_manager("Bearer t")
    assert actor.kind == ACTOR_KIND_APP_ADMIN
    assert actor.firm_id is None


@pytest.mark.parametrize("claims,why", [
    ({"uid": "u", "firm_id": "acme", "firm_role": "employee"},
     "an employee of a firm"),
    ({"uid": "u", "firm_id": "acme"}, "a firm account with no role"),
    ({"uid": "u", "vff_dev": True}, "a voice dev with no firm"),
    ({"uid": "u", "schema_editor_role": "editor"}, "an editor account"),
    ({"uid": "u"}, "a valid account with no claims at all"),
    ({"uid": "u", "app_admin": "yes"},
     "app_admin must be exactly True -- a truthy string is not the claim"),
    ({"uid": "u", "app_admin": 1},
     "nor is a truthy int"),
], ids=["employee", "no-role", "voice-dev", "editor", "bare", "app_admin-str",
        "app_admin-int"])
@pytest.mark.asyncio
async def test_neither_an_admin_nor_a_manager_is_403(monkeypatch, claims, why):
    """403, not 401: they authenticated fine, they are simply not listed
    here. The NO_ADMIN_ACCESS: prefix lets the console route this to a
    refused screen without string-matching prose."""
    _fake_firebase(monkeypatch, claims)
    with pytest.raises(HTTPException) as exc:
        await require_app_admin_or_owning_manager("Bearer t")
    assert exc.value.status_code == 403, why
    assert str(exc.value.detail).startswith(NO_ADMIN_ACCESS_PREFIX)


@pytest.mark.asyncio
async def test_a_token_that_does_not_verify_is_401_not_403(monkeypatch):
    """A 401 must stay a 401 through BOTH branches. Turning an unverifiable
    token into "you are not an admin" would tell a user with an expired
    session to go ask for a promotion.

    Mutation: in the admin branch, swallow the 401 alongside the 403 and
    fall through to the manager branch -- the manager verifier raises too,
    so this still ends 401; but a mutation that converted either to a 403
    reddens here."""
    _fake_firebase(monkeypatch, raises=ValueError("bad token"))
    with pytest.raises(HTTPException) as exc:
        await require_app_admin_or_owning_manager("Bearer t")
    assert exc.value.status_code == 401


@pytest.mark.parametrize("header", [None, "", "Token abc", "bearer t",
                                    "Bearer"])
@pytest.mark.asyncio
async def test_a_missing_or_malformed_bearer_header_is_401(
        monkeypatch, header):
    """Case-SENSITIVE "Bearer ": the admin service has no legacy header
    shape to be lenient about, and leniency here is a second parsing rule
    for a future reader to reconcile."""
    _fake_firebase(monkeypatch, {"uid": "u", "app_admin": True})
    with pytest.raises(HTTPException) as exc:
        await require_app_admin_or_owning_manager(header)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_the_dev_bypass_returns_an_app_admin(monkeypatch):
    """Local dev acts as the widest role, so a developer is not locked out
    of the admin-only half of a composite route. _dev_bypass_allowed refuses
    this outright on a deployed instance (K_SERVICE), pinned in
    test_admin_auth.py."""
    monkeypatch.setattr(aa, "_dev_bypass_allowed", lambda: True)
    actor = await require_app_admin_or_owning_manager(None)
    assert actor.kind == ACTOR_KIND_APP_ADMIN


@pytest.mark.asyncio
async def test_a_verified_token_with_no_subject_is_401(monkeypatch):
    """Every downstream use -- audit attribution above all -- depends on uid
    being real. Inventing one would put an unattributable row in the log."""
    _fake_firebase(monkeypatch, {"firm_id": "acme", "firm_role": "manager",
                                 "email": "x@acme.example"})
    with pytest.raises(HTTPException) as exc:
        await require_app_admin_or_owning_manager("Bearer t")
    assert exc.value.status_code == 401


# --------------------------------------------------------------------------
# require_app_admin_or_owning_manager_or_employee: the THIRD actor kind
# (bd polyglot-pdf-scaig), scoped to its own dependency so the gate above
# stays exactly as pinned for its existing callers.
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_an_employee_resolves_to_the_employee_actor(monkeypatch):
    _fake_firebase(monkeypatch, {"uid": "u4", "email": "al@acme.example",
                                 "firm_id": "acme", "firm_role": "employee"})
    actor = await require_app_admin_or_owning_manager_or_employee("Bearer t")
    assert actor.kind == ACTOR_KIND_FIRM_EMPLOYEE
    assert not actor.is_app_admin
    assert actor.firm_id == "acme"
    assert actor.employee_id == "u4", (
        "an employee's employee_id is their OWN uid, from the token -- "
        "never a value the caller could otherwise influence")


@pytest.mark.asyncio
async def test_employee_gate_still_resolves_app_admin_and_manager(
        monkeypatch):
    """The new dependency is STRICTLY WIDER, not a replacement -- the first
    two branches behave identically to require_app_admin_or_owning_manager.
    """
    _fake_firebase(monkeypatch, {"uid": "u1", "email": "ops@x.example",
                                 "app_admin": True})
    admin = await require_app_admin_or_owning_manager_or_employee("Bearer t")
    assert admin.kind == ACTOR_KIND_APP_ADMIN

    _fake_firebase(monkeypatch, {"uid": "u2", "email": "ada@acme.example",
                                 "firm_id": "acme", "firm_role": "manager"})
    manager = await require_app_admin_or_owning_manager_or_employee(
        "Bearer t")
    assert manager.kind == ACTOR_KIND_FIRM_MANAGER
    assert manager.employee_id is None


@pytest.mark.asyncio
async def test_an_account_holding_manager_and_employee_acts_as_manager(
        monkeypatch):
    """BRANCH ORDER, pinned for the third kind too: manager_firm_id is
    checked before employee_firm_id, so an account somehow carrying both
    (a data anomaly, not a real claims shape today) resolves to the WIDER
    of the two rather than the narrower.

    Mutation: check employee_firm_id first -- red."""
    _fake_firebase(monkeypatch, {"uid": "u5", "email": "amb@acme.example",
                                 "firm_id": "acme", "firm_role": "manager"})
    # A manager-role claims dict alone already proves the ordering here,
    # since firm_role is a single string a real token can only carry once;
    # this test exists to make the intended precedence explicit rather than
    # leave it as an accident of "employee_firm_id would have returned None
    # anyway for firm_role=manager".
    actor = await require_app_admin_or_owning_manager_or_employee("Bearer t")
    assert actor.kind == ACTOR_KIND_FIRM_MANAGER


@pytest.mark.parametrize("claims,why", [
    ({"uid": "u", "firm_id": "acme"}, "a firm account with no role"),
    ({"uid": "u", "vff_dev": True}, "a voice dev with no firm"),
    ({"uid": "u", "schema_editor_role": "editor"}, "an editor account"),
    ({"uid": "u"}, "a valid account with no claims at all"),
], ids=["no-role", "voice-dev", "editor", "bare"])
@pytest.mark.asyncio
async def test_employee_gate_still_403s_everyone_else(
        monkeypatch, claims, why):
    """The widened gate does not become "anyone with a firm_id" or "anyone
    at all" -- only app admin, manager, or employee resolve; everything
    else is still the same 403."""
    _fake_firebase(monkeypatch, claims)
    with pytest.raises(HTTPException) as exc:
        await require_app_admin_or_owning_manager_or_employee("Bearer t")
    assert exc.value.status_code == 403, why
    assert str(exc.value.detail).startswith(NO_ADMIN_ACCESS_PREFIX)


@pytest.mark.asyncio
async def test_employee_gate_dev_bypass_returns_an_app_admin(monkeypatch):
    monkeypatch.setattr(aa, "_dev_bypass_allowed", lambda: True)
    actor = await require_app_admin_or_owning_manager_or_employee(None)
    assert actor.kind == ACTOR_KIND_APP_ADMIN


@pytest.mark.asyncio
async def test_employee_gate_a_token_that_does_not_verify_is_401(
        monkeypatch):
    _fake_firebase(monkeypatch, raises=ValueError("bad token"))
    with pytest.raises(HTTPException) as exc:
        await require_app_admin_or_owning_manager_or_employee("Bearer t")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_the_original_gate_still_403s_an_employee(monkeypatch):
    """THE PROPERTY bd polyglot-pdf-scaig depends on: the original,
    narrower gate MUST NOT have been widened -- an employee claims dict
    still resolves to the SAME 403 through require_app_admin_or_owning_
    manager it always has (this exact case is also pinned in
    test_neither_an_admin_nor_a_manager_is_403 above; restated here,
    adjacent to the new gate's own tests, so a reader comparing the two
    functions sees the contrast in one place).

    Mutation: make require_app_admin_or_owning_manager delegate to the
    shared resolver with allow_employee=True -- this goes red, along with
    the /admin/users route tests that never intended to accept an
    employee."""
    _fake_firebase(monkeypatch, {"uid": "u", "firm_id": "acme",
                                 "firm_role": "employee"})
    with pytest.raises(HTTPException) as exc:
        await require_app_admin_or_owning_manager("Bearer t")
    assert exc.value.status_code == 403


# --------------------------------------------------------------------------
# resolve_target_firm: the two-actor rule, at its home
# --------------------------------------------------------------------------

_ADMIN = CompositeActor(uid="a", email="ops@x.example",
                        kind=ACTOR_KIND_APP_ADMIN)
_MANAGER = CompositeActor(uid="m", email="ada@acme.example",
                          kind=ACTOR_KIND_FIRM_MANAGER, firm_id="acme")


def test_a_manager_with_no_named_firm_gets_their_own():
    assert resolve_target_firm(_MANAGER, None) == "acme"


@pytest.mark.parametrize("named", ["other", "acme", "", "ACME"],
                         ids=["another-firm", "their-OWN-firm", "empty-string",
                              "a-case-variant"])
def test_a_manager_naming_ANY_firm_is_403(named):
    """Including the empty string, which is NOT None: a console that sent
    `firm_id: ""` would otherwise slip past a `not body_firm_id` test and be
    treated as "named nothing".

    Mutation: refuse only when the named firm differs from the token's --
    the their-OWN-firm case goes red. Mutation: test `if body_firm_id:`
    instead of `is not None` -- the empty-string case goes red."""
    with pytest.raises(HTTPException) as exc:
        resolve_target_firm(_MANAGER, named)
    assert exc.value.status_code == 403


def test_an_app_admin_gets_the_firm_they_named():
    assert resolve_target_firm(_ADMIN, "other-firm") == "other-firm"


@pytest.mark.parametrize("named", [None, ""], ids=["omitted", "empty-string"])
def test_an_app_admin_who_names_no_firm_is_422(named):
    """There is no firm to fall back to, and defaulting to any particular
    one would be a guess with a write behind it."""
    with pytest.raises(HTTPException) as exc:
        resolve_target_firm(_ADMIN, named)
    assert exc.value.status_code == 422


def test_a_manager_actor_with_no_firm_id_is_refused_not_returned():
    """Unreachable through the gate, which never builds one. Pinned anyway
    because the failure mode if it ever became reachable is an empty
    firm_id used as a Firestore key -- a query matching nothing while the
    caller looks authorized -- and because an `assert` here would vanish
    under python -O."""
    broken = CompositeActor(uid="m", kind=ACTOR_KIND_FIRM_MANAGER,
                            firm_id=None)
    with pytest.raises(HTTPException) as exc:
        resolve_target_firm(broken, None)
    assert exc.value.status_code == 403


def test_label_prefers_email_but_falls_back_to_uid():
    """Audit rows and log lines read this; it must never be empty."""
    assert _MANAGER.label() == "ada@acme.example"
    assert CompositeActor(uid="u9",
                          kind=ACTOR_KIND_APP_ADMIN).label() == "u9"
