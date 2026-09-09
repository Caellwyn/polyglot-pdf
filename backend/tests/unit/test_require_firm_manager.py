"""The firm-manager rule has ONE home, and both consumers reach it
(bd polyglot-pdf-dmjl5).

Two things are pinned here, and they are different:

  1. THE RULE ITSELF (backend.services.firms.manager_firm_id): exactly which
     claim shapes name a manager, over the WHOLE space of shapes rather than
     a couple of samples.
  2. THE SET OF PLACES THAT DECIDE IT. CLAUDE.md scar #8 -- one rule, one
     home -- is not pinned by testing the helper; it is pinned by proving no
     OTHER module re-derives the same condition. So this file enumerates the
     modules that mention firm_role and asserts the ones that decide manager
     access go through the helper.

ASCII only.
"""
from __future__ import annotations

import ast
import pathlib

import pytest
from fastapi import HTTPException

from backend.services.firms import (
    FIRM_ROLE_EMPLOYEE,
    FIRM_ROLE_MANAGER,
    manager_firm_id,
)

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


# --------------------------------------------------------------------------
# 1. The rule
# --------------------------------------------------------------------------

# The WHOLE space of (firm_id, firm_role) shapes that reach this predicate,
# enumerated rather than sampled: a manager is the ONE accepting cell, so
# every other cell here is a refusal the rule owes us. Parametrized so a
# mutation that widens the rule reddens the specific cell it widened
# (mutation-verify per parametrization, not per file).
_CLAIM_SHAPES = [
    # (claims, expected firm_id or None, why)
    ({"firm_id": "acme", "firm_role": FIRM_ROLE_MANAGER}, "acme",
     "the one accepting shape"),
    ({"firm_id": "acme", "firm_role": FIRM_ROLE_EMPLOYEE}, None,
     "an employee manages nothing"),
    ({"firm_id": "acme", "firm_role": "Manager"}, None,
     "role match is case-SENSITIVE; a near-miss is not a manager"),
    ({"firm_id": "acme", "firm_role": "manager "}, None,
     "a trailing space is not the role string"),
    ({"firm_id": "acme"}, None, "no role at all"),
    ({"firm_id": "acme", "firm_role": None}, None, "an explicit null role"),
    ({"firm_id": "acme", "firm_role": True}, None,
     "a truthy non-string role must not pass"),
    ({"firm_id": "", "firm_role": FIRM_ROLE_MANAGER}, None,
     "an EMPTY firm_id is not a firm -- it would make every firm-scoped "
     "query match nothing while the caller looked authorized"),
    ({"firm_id": None, "firm_role": FIRM_ROLE_MANAGER}, None,
     "an explicit null firm"),
    ({"firm_role": FIRM_ROLE_MANAGER}, None, "manager of no firm"),
    ({"firm_id": 7, "firm_role": FIRM_ROLE_MANAGER}, None,
     "a non-string firm_id"),
    ({"firm_id": ["acme"], "firm_role": FIRM_ROLE_MANAGER}, None,
     "a list firm_id must not be accepted and then used as a doc key"),
    ({}, None, "no claims at all"),
    ({"is_client_link": True, "jti": "j1"}, None,
     "a CLIENT LINK credential carries no firm claims and is never a "
     "manager"),
    ({"vff_dev": True}, None, "a dev with no firm manages no firm"),
    ({"schema_editor_role": "editor"}, None,
     "an editor account is a different surface entirely"),
    ({"app_admin": True}, None,
     "an app admin is not thereby a manager of any particular firm -- the "
     "admin service resolves an admin's target firm from the REQUEST, and "
     "this predicate must not hand one back"),
]


@pytest.mark.parametrize(
    "claims,expected,why", _CLAIM_SHAPES,
    ids=[w[:44].replace(" ", "-") for _, _, w in _CLAIM_SHAPES])
def test_manager_firm_id_over_the_whole_claim_space(claims, expected, why):
    """Mutation: drop the isinstance(firm_id, str) check -- the int and list
    cells go red; drop the `or not firm_id` -- the empty-string cell goes
    red; compare the role with .lower() -- the "Manager" cell goes red."""
    assert manager_firm_id(claims) == expected, why


@pytest.mark.parametrize("bad", [None, "acme", 7, ["firm_id"], object()])
def test_a_non_dict_is_not_a_manager(bad):
    """A caller that passes something other than a claims dict must get a
    refusal, not an AttributeError -- the FastAPI dependency and the retire
    helper both hand it whatever their credential resolver returned."""
    assert manager_firm_id(bad) is None


def test_the_role_constants_are_the_strings_actually_stamped():
    """The claim VALUES are a wire contract: scripts/bootstrap_firm.py
    stamps them, the admin service's user routes write them, and the
    frontend reads them. A rename here is a silent lockout for every already
    stamped account, so the literals are pinned, not just the constants'
    equality to each other."""
    assert FIRM_ROLE_MANAGER == "manager"
    assert FIRM_ROLE_EMPLOYEE == "employee"

    # The bootstrap script keeps its own literals on purpose (it must not
    # import backend.* before initialize_app); pin them against these.
    import scripts.bootstrap_firm as bootstrap_firm

    assert bootstrap_firm.ROLE_MANAGER == FIRM_ROLE_MANAGER
    assert bootstrap_firm.ROLE_EMPLOYEE == FIRM_ROLE_EMPLOYEE

    # The admin service's user routes likewise restate them as a wire
    # contract; same pin, other direction.
    from admin_backend.services import user_admin

    assert user_admin.ROLE_MANAGER == FIRM_ROLE_MANAGER
    assert user_admin.ROLE_EMPLOYEE == FIRM_ROLE_EMPLOYEE
    assert set(user_admin.FIRM_ROLES) == {FIRM_ROLE_MANAGER,
                                          FIRM_ROLE_EMPLOYEE}


# --------------------------------------------------------------------------
# 2. The FastAPI dependency
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_require_firm_manager_returns_the_claims_for_a_manager(
        monkeypatch):
    from backend.services import auth as auth_mod

    async def _fake_require_auth(authorization=None):
        return {"uid": "u1", "firm_id": "acme",
                "firm_role": FIRM_ROLE_MANAGER}

    monkeypatch.setattr(auth_mod, "require_auth", _fake_require_auth)
    claims = await auth_mod.require_firm_manager("Bearer t")
    assert claims["firm_id"] == "acme"


@pytest.mark.parametrize("claims,why", [
    ({"uid": "u1", "firm_id": "acme", "firm_role": FIRM_ROLE_EMPLOYEE},
     "an employee"),
    ({"uid": "u1", "firm_id": "acme"}, "no role"),
    ({"uid": "u1", "vff_dev": True}, "a dev with no firm"),
    ({"uid": "u1", "is_client_link": True}, "a client link"),
], ids=["employee", "no-role", "dev-no-firm", "client-link"])
@pytest.mark.asyncio
async def test_require_firm_manager_refuses_403_for_everyone_else(
        monkeypatch, claims, why):
    """403 and not 404: unlike the kit routes there is no other firm's
    resource whose existence a refusal could leak here, and a manager-only
    console page must be able to tell an employee "not your role".

    Mutation: return the claims instead of raising when manager_firm_id is
    None -- every parametrization goes red."""
    from backend.services import auth as auth_mod

    async def _fake_require_auth(authorization=None):
        return claims

    monkeypatch.setattr(auth_mod, "require_auth", _fake_require_auth)
    with pytest.raises(HTTPException) as exc:
        await auth_mod.require_firm_manager("Bearer t")
    assert exc.value.status_code == 403, why


@pytest.mark.asyncio
async def test_require_firm_manager_lets_an_auth_refusal_through_unchanged(
        monkeypatch):
    """A 401 from require_auth must stay a 401. Turning every credential
    problem into "not a manager" would tell a signed-out user to ask their
    firm for a promotion."""
    from backend.services import auth as auth_mod

    async def _fake_require_auth(authorization=None):
        raise HTTPException(status_code=401, detail="nope")

    monkeypatch.setattr(auth_mod, "require_auth", _fake_require_auth)
    with pytest.raises(HTTPException) as exc:
        await auth_mod.require_firm_manager(None)
    assert exc.value.status_code == 401


# --------------------------------------------------------------------------
# 3. ONE HOME (CLAUDE.md scar #8) -- the set pin
# --------------------------------------------------------------------------

# Every module allowed to mention the literal manager role string. The rule
# is DECIDED in exactly one of them; the others carry it for a different
# reason, named here so the exemption is a decision rather than an accident.
_MANAGER_LITERAL_ALLOWLIST = {
    # THE ONE HOME.
    "backend/services/firms.py":
        "defines FIRM_ROLE_MANAGER and manager_firm_id -- the rule itself",
    # A wire-contract restatement, pinned against the home above by
    # test_the_role_constants_are_the_strings_actually_stamped.
    "scripts/bootstrap_firm.py":
        "stamps the claim; keeps literals to avoid a backend.* import "
        "before initialize_app",
    "admin_backend/services/user_admin.py":
        "the console's wire vocabulary for firm_role, pinned against the "
        "home",
}


def _python_sources():
    for base in ("backend", "admin_backend", "scripts"):
        for path in (_REPO_ROOT / base).rglob("*.py"):
            rel = path.relative_to(_REPO_ROOT).as_posix()
            if "/tests/" in rel or rel.split("/")[-1].startswith("test_"):
                continue
            yield rel, path


def test_no_module_re_derives_the_manager_rule():
    """THE SET PIN, and the reason this file exists at all.

    ENUMERATE THE SET BEFORE FIXING ANY OF IT (CLAUDE.md scar #8): testing
    manager_firm_id proves the helper works, not that anybody uses it. This
    walks every non-test module under backend/, admin_backend/ and scripts/
    for a comparison against the literal "manager" and fails on any site not
    in the allowlist above -- so the NEXT route that hand-writes
    `claims.get("firm_role") == "manager"` fails here instead of drifting
    from the rule for a release.

    Mutation: restore the inline check in form_kit_routes.
    _require_firm_owns_private_kit -- red, naming that file."""
    offenders = []
    for rel, path in _python_sources():
        if rel in _MANAGER_LITERAL_ALLOWLIST:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover -- not our file to fix
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            operands = [node.left, *node.comparators]
            if any(isinstance(o, ast.Constant) and o.value == "manager"
                   for o in operands):
                offenders.append("{}:{}".format(rel, node.lineno))
    assert not offenders, (
        "these modules compare against the literal manager role instead of "
        "calling backend.services.firms.manager_firm_id -- the rule must "
        "have ONE home (CLAUDE.md scar #8):\n  " + "\n  ".join(offenders))


def test_the_retire_helper_consumes_the_shared_rule():
    """The specific consumer the bead moved, pinned by NAME.

    The set pin above proves no module re-derives the rule; this proves the
    retire path actually CALLS the shared one rather than having simply
    dropped its manager check (which would also pass a "no literal" scan
    while making the route wide open)."""
    from backend.routes import form_kit_routes

    source = pathlib.Path(
        form_kit_routes.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    helper = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef)
        and n.name == "_require_firm_owns_private_kit")
    called = {
        c.func.id for c in ast.walk(helper)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
    }
    assert "manager_firm_id" in called, (
        "_require_firm_owns_private_kit no longer calls manager_firm_id -- "
        "either it re-derived the rule or it dropped the manager check "
        "entirely")


def test_the_allowlist_names_no_file_that_is_gone():
    """The reverse direction: a stale allowlist entry would silently exempt
    nothing while hiding that a real site moved."""
    missing = [rel for rel in _MANAGER_LITERAL_ALLOWLIST
               if not (_REPO_ROOT / rel).exists()]
    assert not missing, "allowlist names files that do not exist: {}".format(
        missing)
