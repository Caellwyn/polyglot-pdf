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
  window/validation logic, and kit_gates.firm_allowed_kits. AND, since Epic 2
  bead A3, the MONEY journey over the real routes:
  test_the_whole_MONEY_journey_works_over_real_HTTP drives POST
  /api/links/mint -> POST /api/links/open against one Firestore, which is
  the only test that proves the record the mint WRITES is the record the
  open gate READS (a channel mismatch or a collection-name drift passes
  every other test in the repo).

  NOT COVERED, and each needs its own test elsewhere:
    - the routes' own refusal matrix -- the 402/403 mint refusals, the
      uniform-404 open refusals, the eight channel-vs-kind cases
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

from fastapi.testclient import TestClient

from backend.main import app
from backend.services import kit_gates
from backend.services.auth import require_auth

client = TestClient(app)
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
            # open_link is reached only from PAID paths now (the socket,
            # /open, the TTS routes), so refusing a completed link here is
            # correct -- and retrieval never calls it at all.
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

    # 3. The redemption record is created by the PAID path (the socket), not
    #    by retrieval -- require_auth no longer redeems. Open it the way the
    #    socket does, then check the record's shape: no client identifier
    #    anywhere.
    journey.open_link(jti, _FIRM, _KIT)
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

    # A reload re-authenticates, repeatedly, and keeps working.
    for _ in range(3):
        assert asyncio.run(_auth(token))["jti"] == jti

    # AND THE CLIENT'S FIRST TWO CALLS GO OVER REAL HTTP. Asserting on a
    # dependency function is what let this break: the catalogue routes were
    # moved onto require_signin (PR #643), which knew nothing about link
    # tokens, so a client 401'd on the form list -- while this test, calling
    # require_auth directly, still passed. Drive the ROUTES, so moving them
    # to another dependency reddens here instead of dead-ending a client.
    auth = {"Authorization": "Bearer " + token}
    listed = client.get("/api/form-kits", headers=auth)
    assert listed.status_code == 200, listed.text
    # The schema route shares that dependency. This fixture's kit is
    # synthetic and has no schema FILE, so 404 (the handler ran and found
    # nothing) is the pass here -- what must never come back is 401/403,
    # which would mean the credential was refused at the door again.
    schema = client.get("/api/form-kits/" + _KIT + "/schema", headers=auth)
    assert schema.status_code not in (401, 403), schema.text

    journey.open_link(jti, _FIRM, _KIT)   # the socket opened the session
    journey.complete_link(jti)

    # RETRIEVAL still works: the client downloads the form they just filled,
    # for as long as their tab is open. An earlier version asserted the
    # opposite ("now burned, is refused everywhere") and pinned a real bug as
    # correct -- refusing here took away 40 minutes of the client's work for
    # no security benefit, since /api/fill-pdf spends nothing.
    assert asyncio.run(_auth(token))["jti"] == jti

    # But PAID work is refused: no second Gemini session, no more synthesis.
    from backend.services.auth import require_paid_client_work

    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_paid_client_work(authorization="Bearer " + token))
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


def test_the_whole_MONEY_journey_works_over_real_HTTP(journey, monkeypatch):
    """MINT -> OPEN, over the real routes, with the money path live (Epic 2
    bead A3).

    THIS IS THE ONE THAT WOULD HAVE CAUGHT THE ORDERING BUG. Every other
    test in this file drives require_auth or a helper directly, and the tests
    in test_link_routes.py drive the routes with a redemption stub -- so a
    version where the mint wrote a record the OPEN GATE then could not find
    (a channel mismatch, a collection-name drift, a jti that differed between
    the record and the token) would pass all of them. Only walking mint's
    output into open's input, through both routes, over one Firestore, proves
    the two halves of the reserve-before-sign contract actually meet.

    The four assertions are the contract stated end to end:
      1. the mint debits the firm's balance,
      2. it writes a ledger entry and a mint record,
      3. the token it returns OPENS -- so the record it wrote is the record
         the gate reads,
      4. and the SAME token stops opening the moment that record is revoked.

    Mutation: pass a literal "demo" as _reserve_mint's channel while
    LINK_CHANNEL is staging -- red at step 3 (the record is written where the
    gate does not look). Mutation: drop the _require_mint_record call -- red
    at step 4.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import backend.routes.link_routes as lr
    from backend.services import links_store
    from backend.tests.unit._fake_firestore import (
        _FakeDb,
        _FakeFirestoreModule,
    )

    monkeypatch.setenv("LINK_BASE_URL", "https://forms.example.com")
    monkeypatch.setenv("LINK_CHANNEL", "staging")
    monkeypatch.setattr(lr, "_rc_minting_enabled", lambda: True)
    monkeypatch.setattr(lr, "_rc_credits_enforced", lambda: True)
    monkeypatch.setattr(
        "backend.services.auth.verify_token",
        lambda tok: {"uid": _EMPLOYEE, "firm_id": _FIRM,
                     "firm_role": "employee"},
    )
    monkeypatch.setattr(lr, "get_allowed_kits", lambda firm_id: [_KIT])

    db = _FakeDb({("firms", _FIRM): {"name": "Firm A", "status": "active",
                                     "kind": "mock", "balance_credits": 5}})
    monkeypatch.setattr(lr, "get_db", lambda: db)
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)
    import firebase_admin
    monkeypatch.setattr(firebase_admin, "firestore", _FakeFirestoreModule(),
                        raising=False)
    # The redemption store stays the journey fixture's in-memory one -- this
    # test is about the MINT RECORD reaching the open gate, and a second
    # fake store would only add noise.

    app = FastAPI()
    app.include_router(lr.router)
    http = TestClient(app)

    # 1 + 2. MINT over HTTP: the balance moves, and both documents exist.
    minted = http.post("/api/links/mint", json={"kit_id": _KIT},
                       headers={"Authorization": "Bearer staff-token"})
    assert minted.status_code == 200, minted.text
    jti = minted.json()["jti"]
    assert db.firm(_FIRM)["balance_credits"] == 4
    assert [e["link_jti"] for e in db.ledger_rows(_FIRM)] == [jti]
    # The STAGING collection, because that is the running channel.
    assert set(db.link_rows("links_staging")) == {jti}
    assert db.link_rows("links") == {}

    # 3. OPEN over HTTP with the token the mint just handed back.
    token = minted.json()["url"].split("#t=", 1)[1]
    opened = http.post("/api/links/open", json={"token": token})
    assert opened.status_code == 200, opened.text
    assert opened.json()["jti"] == jti
    assert opened.json()["kit_id"] == _KIT

    # 4. REVOKE the record, and the very same token stops working.
    db.docs[("links_staging", jti)]["status"] = links_store.STATUS_REVOKED
    revoked = http.post("/api/links/open", json={"token": token})
    assert revoked.status_code == 404
    assert revoked.json()["detail"] == "This link is not valid."
