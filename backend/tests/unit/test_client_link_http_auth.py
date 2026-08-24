"""A client link authenticates HTTP routes too (bd polyglot-pdf-ugm6).

Fresh-eyes r2 finding 1: the WebSocket was taught to accept a link token but
every HTTP route the session depends on -- the manifest read, the schema
read, the PDF fill -- still required a Firebase ID token. A client has no
account, so every one of those 401'd and the session dead-ended at "Unable to
load forms." The feature was unreachable for a real client in any
environment.

The second half of this file is the leak that fix could have introduced: a
link carries the FIRM's id, and the firm's allowlist is every private kit the
firm owns. Resolving that for a client would hand them a directory of the
firm's intake forms.

ASCII only.
"""
import asyncio

import pytest
from fastapi import HTTPException

from backend.services import kit_gates
from backend.services.auth import require_auth
from backend.services.link_tokens import mint_link_token

_SECRET = "h" * 40


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("LINK_TOKEN_SECRET", _SECRET)
    monkeypatch.setenv("VFF_DISABLE_AUTH", "false")


async def _auth(token: str) -> dict:
    return await require_auth(authorization="Bearer " + token)


# --- the credential is accepted at all ---------------------------------------


def test_a_link_token_authenticates_an_http_route():
    """THE r2 FIX. Without this every client session ends at "Unable to load
    forms" -- the manifest read is SchemaFormDemo's first effect.

    Mutation: remove the one-dot branch from require_auth -- red.
    """
    token, jti = mint_link_token("firm-a", "i-90", "u-emp-7")

    claims = asyncio.run(_auth(token))

    assert claims["firm_id"] == "firm-a"
    assert claims["link_kit_id"] == "i-90"
    assert claims["employee_id"] == "u-emp-7"
    assert claims["jti"] == jti
    assert claims["is_client_link"] is True


def test_a_client_credential_carries_NO_ROLE_and_NO_UID():
    """A client is NOT staff. No firm_role means every role-gated surface --
    the firm retire route today, anything added later -- refuses them by the
    same check that refuses an ordinary employee, with no new code.

    Mutation: add "firm_role": "employee" to the client claims -- red.
    """
    token, _ = mint_link_token("firm-a", "i-90", "u-emp-7")

    claims = asyncio.run(_auth(token))

    assert claims.get("firm_role") is None
    assert claims["uid"] is None


def test_a_forged_link_token_is_401_not_accepted():
    """The one-dot branch VERIFIES; it does not merely parse.
    Mutation: return the decoded payload without verify_link_token -- red."""
    token, _ = mint_link_token("firm-a", "i-90", "u-emp-7")
    forged = token[:-4] + "AAAA"

    with pytest.raises(HTTPException) as exc:
        asyncio.run(_auth(forged))
    assert exc.value.status_code == 401


def test_an_expired_link_token_is_401():
    """The same window the socket enforces. Mutation: skip the exp check --
    red."""
    import time

    token, _ = mint_link_token("firm-a", "i-90", "u-emp-7",
                               open_window_s=60,
                               now=int(time.time()) - 10_000)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(_auth(token))
    assert exc.value.status_code == 401


def test_a_staff_firebase_token_still_takes_the_firebase_path(monkeypatch):
    """Dispatch is on SHAPE. A JWT (two dots) can never be parsed as a link.
    Mutation: send every token to verify_link_token -- red."""
    seen = {}

    def _fake(tok):
        seen["tok"] = tok
        return {"uid": "u-staff", "firm_id": "firm-a", "firm_role": "manager"}

    monkeypatch.setattr("backend.services.auth.verify_token", _fake)

    claims = asyncio.run(_auth("header.payload.signature"))

    assert seen["tok"] == "header.payload.signature"
    assert claims["uid"] == "u-staff"
    assert "is_client_link" not in claims


# --- the leak that fix could have introduced ---------------------------------


def test_a_CLIENT_sees_only_the_kit_their_link_names(monkeypatch):
    """THE LEAK (caught while fixing r2 finding 1, before it shipped).

    A link carries the FIRM's id so the session is firm-keyed for telemetry.
    But the firm's allowlist is every private kit the FIRM may use -- which
    is emphatically not what a CLIENT may read. Resolving it for a client
    would hand them a directory of that firm's private intake forms, and let
    them fetch the schema and blank PDF of forms they were never sent.

    Mutation: drop the is_client_link branch in firm_allowed_kits -- red.
    """
    monkeypatch.setattr(kit_gates, "get_allowed_kits",
                        lambda firm_id: ["i-90", "n-400", "w7-private"])
    client = {"firm_id": "firm-a", "link_kit_id": "i-90",
              "is_client_link": True, "uid": None}

    allowed = asyncio.run(kit_gates.firm_allowed_kits(client))

    assert allowed == frozenset({"i-90"}), (
        "a client must see EXACTLY the kit their link names"
    )


def test_STAFF_still_resolve_the_whole_firm_allowlist(monkeypatch):
    """The narrowing must not leak into the staff path -- an employee
    legitimately sees every kit their firm may use."""
    monkeypatch.setattr(kit_gates, "get_allowed_kits",
                        lambda firm_id: ["i-90", "n-400", "w7-private"])
    staff = {"firm_id": "firm-a", "uid": "u-staff", "firm_role": "employee"}

    allowed = asyncio.run(kit_gates.firm_allowed_kits(staff))

    assert allowed == frozenset({"i-90", "n-400", "w7-private"})


def test_a_client_link_naming_a_kit_the_firm_LOST_resolves_to_nothing(
    monkeypatch,
):
    """The narrowing INTERSECTS with the allowlist rather than trusting the
    token alone: a firm suspended, or a kit retired, since the link was
    minted must still refuse.

    Mutation: return frozenset({link_kit}) without intersecting -- red.
    """
    monkeypatch.setattr(kit_gates, "get_allowed_kits", lambda firm_id: [])
    client = {"firm_id": "firm-a", "link_kit_id": "i-90",
              "is_client_link": True, "uid": None}

    assert asyncio.run(kit_gates.firm_allowed_kits(client)) == frozenset()


def test_a_client_link_with_no_kit_resolves_to_nothing(monkeypatch):
    """Fail closed on a malformed credential rather than falling through to
    the firm's whole allowlist."""
    monkeypatch.setattr(kit_gates, "get_allowed_kits",
                        lambda firm_id: ["i-90", "n-400"])
    for bad in (None, "", 5):
        client = {"firm_id": "firm-a", "link_kit_id": bad,
                  "is_client_link": True, "uid": None}
        assert asyncio.run(kit_gates.firm_allowed_kits(client)) == frozenset()
