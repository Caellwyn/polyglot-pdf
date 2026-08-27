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
    # require_auth now REDEEMS a client link (Opus cross-surface r1), so a
    # test that does not supply a store fails closed -- correct behavior,
    # pinned separately below. Default to a fresh, unburned link.
    import time as _t
    monkeypatch.setattr(
        "backend.services.link_redemptions.open_link",
        lambda jti, firm_id, kit_id, now=None: {
            "jti": jti, "firm_id": firm_id, "kit_id": kit_id,
            "opened_at": int(_t.time()), "completed_at": None,
        },
    )


async def _auth(token: str) -> dict:
    """Retrieval: verified + kit-scoped, but NOT redeemed."""
    return await require_auth(authorization="Bearer " + token)


async def _paid(token: str) -> dict:
    """Paid work: verified AND redeemed."""
    from backend.services.auth import require_paid_client_work

    return await require_paid_client_work(authorization="Bearer " + token)


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


# --- the r1 hole: HTTP accepted a BURNED link for the rest of its exp -------


def test_a_COMPLETED_link_is_refused_by_PAID_routes(monkeypatch):
    """A burned link buys NO MORE PAID WORK.

    Scoped deliberately (maintainer, 2026-08-24): the TTL bounds a backend
    CONNECTION, not the client's own document. So the refusal lives on
    require_paid_client_work (the two TTS routes) and the socket -- NOT on
    require_auth, which gates retrieval. The sibling test below pins the
    other half: the same burned link still downloads the PDF it produced.

    Mutation: drop the enforce_link_redemption call in
    require_paid_client_work -- red.
    """
    from backend.services.link_redemptions import LinkAlreadyUsed

    def _burned(jti, firm_id, kit_id, now=None):
        raise LinkAlreadyUsed("already completed")

    monkeypatch.setattr("backend.services.link_redemptions.open_link", _burned)
    token, _ = mint_link_token("firm-a", "i-90", "u-emp-7")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(_paid(token))
    assert exc.value.status_code == 401


def test_a_COMPLETED_link_can_STILL_DOWNLOAD_its_own_form(monkeypatch):
    """THE OTHER HALF, and the point of the correction.

    The burn lands at socket teardown -- an idle timeout, a section switch, a
    network blip -- while the client sits in front of live Download, Print
    and Preview buttons. Refusing them there took away the document they had
    just spent 40 minutes filling, for no security benefit: /api/fill-pdf is
    a pure PyMuPDF render with no model call.

    Mutation: make require_auth redeem again -- red.
    """
    from backend.services.link_redemptions import LinkAlreadyUsed

    def _burned(jti, firm_id, kit_id, now=None):
        raise LinkAlreadyUsed("already completed")

    monkeypatch.setattr("backend.services.link_redemptions.open_link", _burned)
    token, _ = mint_link_token("firm-a", "i-90", "u-emp-7")

    claims = asyncio.run(_auth(token))

    assert claims["firm_id"] == "firm-a"
    assert claims["link_kit_id"] == "i-90"


def test_an_ELAPSED_completion_window_is_refused_by_PAID_routes(monkeypatch):
    """The socket enforced the completion clock; HTTP did not, so a link
    could outlive its window on every route except the one that starts the
    paid session.

    Mutation: drop the window check in enforce_link_redemption -- red.
    """
    import time as _t

    monkeypatch.setattr(
        "backend.services.link_redemptions.open_link",
        lambda jti, firm_id, kit_id, now=None: {
            "jti": jti, "firm_id": firm_id, "kit_id": kit_id,
            # Opened well before a short window closed.
            "opened_at": int(_t.time()) - 10_000, "completed_at": None,
        },
    )
    token, _ = mint_link_token("firm-a", "i-90", "u-emp-7",
                               complete_window_s=3600)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(_paid(token))
    assert exc.value.status_code == 401


def test_an_UNREACHABLE_store_refuses_PAID_work(monkeypatch):
    """Fail closed where money is at stake. Mutation: admit on
    RedemptionUnavailable -- red."""
    from backend.services.link_redemptions import RedemptionUnavailable

    def _down(jti, firm_id, kit_id, now=None):
        raise RedemptionUnavailable("firestore down")

    monkeypatch.setattr("backend.services.link_redemptions.open_link", _down)
    token, _ = mint_link_token("firm-a", "i-90", "u-emp-7")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(_paid(token))
    assert exc.value.status_code == 401


# --- the SET of credential doors, not one instance ---------------------------


def test_the_complete_set_of_credential_resolution_sites_is_pinned():
    """PIN THE SET (CLAUDE.md scar #7). This bead taught the client-link
    shape to one door at a time and MISSED ONE THREE TIMES: the socket (r1),
    the require_auth routes (r2), and finally GET /form-kits/{id}/pdf (r6),
    which resolves credentials ITSELF because it is optional-auth and so
    never went through require_auth at all. Each miss was invisible until a
    reviewer walked the client's path.

    Derived from the shipped sources, so a NEW door reddens here instead of
    costing a review round -- which it did on the #643 merge, catching a
    client 401 on the catalogue routes that no other test saw. If you are
    adding one: it must dispatch on token SHAPE and, for a link, call
    resolve_client_link_credential. That resolves ONLY; whether your door
    also redeems depends on whether it can SPEND -- see the split in
    test_the_complete_set_of_link_verifying_sites_is_pinned below.
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    sites = {}
    call = re.compile(r"(?<!def )verify_token\s*\(")
    for rel in ("backend/routes", "backend/services"):
        for path in sorted((root / rel).rglob("*.py")):
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.lstrip()
                if stripped.startswith(("#", "def ", "async def ", "from", "import")):
                    continue
                if call.search(line):
                    key = path.relative_to(root).as_posix()
                    sites[key] = sites.get(key, 0) + 1

    assert sites == {
        # 1. the socket (_verify_ws_credential) -- taught in r1
        "backend/routes/websocket_routes.py": 1,
        # 2. require_auth, which every gated HTTP route inherits -- r2, AND
        #    require_signin, the catalogue's dependency since PR #643. This
        #    guard EARNED ITSELF on that merge: dev moved GET /api/form-kits
        #    and .../schema onto a new dependency that knew nothing about
        #    link tokens, and this count going 1 -> 2 is what surfaced it.
        #    A client 401'd on their FIRST TWO CALLS with every other test
        #    green. If this number changes again, the new site must dispatch
        #    on token shape -- do not just bump the count.
        "backend/services/auth.py": 2,
        # 3. the OPTIONAL-auth pdf route, which bypasses require_auth -- r6
        "backend/routes/form_kit_routes.py": 1,
    }, (
        "the set of credential-resolution sites changed. A new one must "
        "dispatch on token shape and redeem a client link, or the client "
        "tier breaks on that surface only -- silently."
    )


def test_the_complete_set_of_link_verifying_sites_is_pinned():
    """The other half of the door set, and the failure the first half cannot
    see (Opus cross-surface r9).

    The guard above counts `verify_token(` call sites. A new door that
    dispatches on shape and calls `verify_link_token` DIRECTLY -- verifying
    the signature but never redeeming -- adds no `verify_token(` call, so it
    is invisible to that count. The reviewer built exactly that door on
    /api/fill-pdf and the whole backend suite stayed green: a burned link
    would keep rendering PDFs.

    That is the hole this bead has closed three times over (r1 the socket, r2
    require_auth, r6 the pdf route), so the SET that matters is "who verifies
    a link".

    NOT every member redeems, and an earlier version of this docstring said
    otherwise -- following it would re-introduce the r11 regression the
    maintainer reverted (2026-08-24: "There's not really any reason to have a
    time limit on saving or printing"). The real rule is a SPLIT:

      * a door that can SPEND -- a Gemini session, a TTS synthesis -- must
        call enforce_link_redemption. Today: /api/links/open, the WebSocket,
        require_paid_client_work.
      * a door that only RETRIEVES -- the manifest, the schema, the client's
        own finished PDF -- must NOT. Burning a link there takes away work
        the client already did and protects nothing, because those routes
        spend nothing.

    Adding a link-verifying site? Decide which half it is FIRST, wire it
    accordingly, then add it here.
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    sites = {}
    call = re.compile(r"verify_link_token\s*\(")
    for rel in ("backend/routes", "backend/services"):
        for path in sorted((root / rel).rglob("*.py")):
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.lstrip()
                if stripped.startswith(("#", "def ", "async def ", "from", "import")):
                    continue
                if call.search(line):
                    key = path.relative_to(root).as_posix()
                    sites[key] = sites.get(key, 0) + 1

    assert sites == {
        # mint re-reads its own token to return exp; /open verifies before
        # handing the payload to the shared gate. Both redeem via
        # enforce_link_redemption.
        "backend/routes/link_routes.py": 2,
        # the socket, which redeems immediately after.
        "backend/routes/websocket_routes.py": 1,
        # resolve_client_link_credential -- verifies ONLY. It never redeems
        # (a redeem= flag lived here and was removed: nothing could safely
        # turn it on). The paid doors redeem themselves; see the split above.
        "backend/services/auth.py": 1,
    }, (
        "a new site verifies a client link. If it can SPEND, it must also "
        "redeem (enforce_link_redemption) or a COMPLETED link keeps buying "
        "work -- the hole closed three times in this bead. If it only "
        "RETRIEVES, it must NOT redeem, or the client loses the document "
        "they already filled. Decide which, then update this set."
    )
