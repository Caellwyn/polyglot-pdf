"""THE CLIENT'S WHOLE JOURNEY, in one test (bd polyglot-pdf-ugm6).

WHY THIS FILE EXISTS. Four review rounds each found the client path broken
end-to-end, every time at a different layer, every time with the full suite
green:

  r1  the redeemed token was captured and DISCARDED, so the socket got no
      credential at all.
  r2  every HTTP route still demanded a Firebase account, so the client's
      first call (the form list) 401'd.
  r3  the token was written to storage and never read back, so a reload
      stranded the client.
  r4  the fetch was built from the WEBSOCKET url helper, so the redemption
      request went to an unfetchable address and EVERY valid link showed
      "this link is not valid".

Each layer had tests. Each test asserted something ADJACENT to the behavior
-- that a module round-trips a value, that a component wrote a key, that a
URL contained a substring -- and each passed while the feature was dead.

The generalizable rule, and the reason for this file: FOR A FEATURE WITH A
NEW KIND OF ACTOR, only a test that walks the actor's whole path proves the
actor can act. Component tests prove components.

This is the backend half of that walk: mint -> redeem -> authenticate a real
gated route -> complete -> refuse the replay. The frontend half is
ClientLinkEntry.test.tsx (which drives the gate, not a mock of it) plus
sessionCredential.test.ts. What is deliberately NOT covered here is the
browser's own wiring; that gap is what r4 lived in, and it is pinned by the
URL-parsing assertion in ClientLinkEntry.test.tsx.

ASCII only.
"""
import asyncio

import pytest
from fastapi import HTTPException

from backend.services import kit_gates
from backend.services.auth import require_auth
from backend.services.link_redemptions import LinkAlreadyUsed
from backend.services.link_tokens import mint_link_token

_SECRET = "j" * 40
_FIRM = "firm-a"
_KIT = "firm-a-intake"
_EMPLOYEE = "u-emp-7"


class _Store:
    """One in-memory redemption store for the whole journey, so each step
    sees what the previous step actually wrote -- the point of the test."""

    def __init__(self):
        self.records = {}

    def open_link(self, jti, firm_id, kit_id, now=None):
        import time as _t

        rec = self.records.get(jti)
        if rec is not None:
            if rec.get("completed_at"):
                raise LinkAlreadyUsed("already completed")
            return rec
        rec = {"jti": jti, "firm_id": firm_id, "kit_id": kit_id,
               "opened_at": int(now if now is not None else _t.time()),
               "completed_at": None}
        self.records[jti] = rec
        return rec

    def complete_link(self, jti, now=None):
        import time as _t

        if jti in self.records:
            self.records[jti]["completed_at"] = int(
                now if now is not None else _t.time())


@pytest.fixture
def journey(monkeypatch):
    monkeypatch.setenv("LINK_TOKEN_SECRET", _SECRET)
    monkeypatch.setenv("VFF_DISABLE_AUTH", "false")
    store = _Store()
    monkeypatch.setattr("backend.services.link_redemptions.open_link",
                        store.open_link)
    monkeypatch.setattr("backend.services.link_redemptions.complete_link",
                        store.complete_link)
    # The firm holds this kit; the allowlist read is what refuses a kit the
    # firm has since lost.
    monkeypatch.setattr(kit_gates, "get_allowed_kits",
                        lambda firm_id: [_KIT, "firm-a-other"])
    return store


async def _auth(token):
    return await require_auth(authorization="Bearer " + token)


def test_the_whole_client_journey_works_with_NO_ACCOUNT(journey):
    """MINT -> REDEEM -> READ -> the kit is scoped to the link.

    Every step uses ONLY the link token. There is no Firebase account
    anywhere in this test, which is the product requirement: a firm's client
    never signs in and never uses a staff-signed-in machine.
    """
    token, jti = mint_link_token(_FIRM, _KIT, _EMPLOYEE)

    # 1. The credential authenticates a real gated route's dependency.
    claims = asyncio.run(_auth(token))
    assert claims["firm_id"] == _FIRM
    assert claims["jti"] == jti
    assert claims["employee_id"] == _EMPLOYEE
    assert claims["uid"] is None, "a client has no account"
    assert claims.get("firm_role") is None, "a client is not staff"

    # 2. That credential resolves to EXACTLY the kit the link names -- not
    #    the firm's other kits, which is what the visibility gate would hand
    #    a staff member.
    allowed = asyncio.run(kit_gates.firm_allowed_kits(claims))
    assert allowed == frozenset({_KIT})

    # 3. The redemption record exists and names the firm + kit, with no
    #    client identifier anywhere.
    record = journey.records[jti]
    assert set(record) == {"jti", "firm_id", "kit_id", "opened_at",
                           "completed_at"}


def test_the_journey_survives_a_RELOAD_and_then_burns_on_completion(journey):
    """The client re-authenticates repeatedly (reloads, more reads) and it
    keeps working -- then ONE completion ends it.

    r3's bug lived here: a reload must not strand a client mid-form. The
    backend half of that is simply that re-authenticating an UNFINISHED link
    keeps succeeding.
    """
    token, jti = mint_link_token(_FIRM, _KIT, _EMPLOYEE)

    for _ in range(4):        # the manifest, the schema, the PDF, a reload
        assert asyncio.run(_auth(token))["jti"] == jti

    journey.complete_link(jti)

    # The SAME token, now burned, is refused everywhere.
    with pytest.raises(HTTPException) as exc:
        asyncio.run(_auth(token))
    assert exc.value.status_code == 401


def test_a_link_for_a_kit_the_firm_LOSES_stops_working_mid_journey(
    journey, monkeypatch
):
    """Entitlement is re-checked on every request, not trusted from mint
    time: a firm suspended, or a kit retired, must cut off a client who is
    already part-way through."""
    token, _jti = mint_link_token(_FIRM, _KIT, _EMPLOYEE)
    claims = asyncio.run(_auth(token))
    assert asyncio.run(kit_gates.firm_allowed_kits(claims)) == frozenset({_KIT})

    monkeypatch.setattr(kit_gates, "get_allowed_kits", lambda firm_id: [])

    assert asyncio.run(kit_gates.firm_allowed_kits(claims)) == frozenset()


def test_a_STAFF_journey_is_untouched_by_any_of_this(journey, monkeypatch):
    """The client path must not have changed what staff get. A staff token
    still takes the Firebase path and still resolves the firm's WHOLE
    allowlist."""
    monkeypatch.setattr(
        "backend.services.auth.verify_token",
        lambda tok: {"uid": "u-staff", "firm_id": _FIRM,
                     "firm_role": "manager"},
    )

    claims = asyncio.run(_auth("header.payload.signature"))

    assert claims["uid"] == "u-staff"
    assert "is_client_link" not in claims
    assert asyncio.run(kit_gates.firm_allowed_kits(claims)) == frozenset(
        {_KIT, "firm-a-other"}
    )
