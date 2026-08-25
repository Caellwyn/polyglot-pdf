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

WHAT THIS FILE ACTUALLY COVERS, stated precisely, because a coverage map
that flatters itself is worse than none (an earlier version of this docstring
claimed "a real gated route" and "complete", and both were false):

  COVERED -- mint_link_token, the require_auth DEPENDENCY FUNCTION (called
  directly, not through a route), enforce_link_redemption including its real
  window/validation logic, and kit_gates.firm_allowed_kits.

  NOT COVERED, and each needs its own test elsewhere:
    - POST /api/links/mint and POST /api/links/open (the routes themselves)
      -> test_link_routes.py
    - the /ws/fill handshake and the claims -> telemetry wiring
      -> test_websocket_ephemeral.py (r5 found that wiring UNPINNED: severing
         it passed 104 tests)
    - complete_link's production call site (the guard
      `if session_completed and link_jti`)
      -> test_proactive_complete_events.py. `journey.complete_link` below is
         the FIXTURE's method, not production code.
    - the real Firestore client -> nothing; the store is in-memory here.
    - the browser's wiring (the fetch URL, the reload recovery)
      -> ClientLinkEntry.test.tsx, where r4's bug lived.

ASCII only.
"""
import asyncio
import time

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
            # Mirror the REAL grace window (Opus r11): a completed link keeps
            # working briefly, because the burn lands at socket teardown
            # while the client is still downloading their finished form. A
            # fake that refuses instantly would make this journey test assert
            # the bug as correct -- which the earlier version did.
            from backend.services.link_redemptions import COMPLETION_GRACE_S

            done = rec.get("completed_at")
            if isinstance(done, int) and not isinstance(done, bool):
                stamp = int(now if now is not None else _t.time())
                if stamp >= done + COMPLETION_GRACE_S:
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

    # The manifest, the schema, and a reload -- all three go through
    # require_auth. NOT the PDF: that route is optional-auth and resolves
    # credentials itself, which is exactly why it broke separately (r6).
    # Its behavior is pinned in test_http_route_auth.py, by a test that
    # drives the real route.
    for _ in range(3):
        assert asyncio.run(_auth(token))["jti"] == jti

    journey.complete_link(jti)

    # THE SAME TOKEN STILL WORKS BRIEFLY -- and that is the requirement, not
    # a leak. An earlier version of this test asserted the opposite ("now
    # burned, is refused everywhere"), which pinned a real bug as correct:
    # the burn lands at socket teardown while the client is still looking at
    # Download/Print buttons, so refusing instantly made their finished form
    # unreachable (Opus r11).
    assert asyncio.run(_auth(token))["jti"] == jti

    # Past the grace window it IS refused -- the replay guarantee, measured
    # from the burn.
    from backend.services.link_redemptions import COMPLETION_GRACE_S

    journey.records[jti]["completed_at"] = int(time.time()) - COMPLETION_GRACE_S - 1
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
