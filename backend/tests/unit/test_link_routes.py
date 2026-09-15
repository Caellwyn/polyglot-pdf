"""Client magic-link routes: mint + open (bd polyglot-pdf-ugm6, extended by
Epic 2 bead A3 polyglot-pdf-jecrl).

`/open` is the only UNAUTHENTICATED endpoint that starts a paid session, so
its refusal behavior is the security surface: every rejection must be
indistinguishable, or the endpoint becomes an oracle for probing which links
and firms exist.

BEAD A3 ADDED MONEY TO BOTH HALVES, and the two rules are one invariant seen
from each end:

  MINT reserves BEFORE signing. The debit, the ledger entry and the
  links/{jti} mint record commit in ONE transaction, and only then is a
  token signed. A refusal (402 out of credits, 403 live firm off the demo
  channel) therefore leaves NO token, NO ledger entry and NO record.

  OPEN requires that record. A token with no mint record, or one whose
  record is revoked/refunded, gets the same uniform 404 as every other
  refusal.

Consequently the fixture below now carries a REAL fake Firestore (shared
with test_credit_ledger.py, see _fake_firestore.py) rather than only a
redemption stub: a mint that does not actually write a firm's balance cannot
be asserted against, and an open whose mint record was never written would
pass a test that stubbed the gate out.

Each test's docstring names the mutation that must turn it red
(docs/standards/testing.md#test-the-tests).

ASCII only.
"""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import backend.routes.link_routes as lr
import backend.services.links_store as links_store
from backend.services.link_redemptions import (
    LinkAlreadyUsed,
    RedemptionUnavailable,
)
from backend.tests.unit._fake_firestore import _FakeDb, _FakeFirestoreModule

_SECRET = "s" * 40

_TOKENS = {
    # emp-a carries an email claim (bd polyglot-pdf-cpsi0): every REAL
    # Firebase account has one, so this is the representative case the
    # existing (pre-cpsi0) tests already exercise unchanged -- none of them
    # assert on the claims dict's exact key set, only on the fields they
    # name.
    "emp-a": {"uid": "u-emp-a", "firm_id": "firm-a", "firm_role": "employee",
              "email": "emp-a@firm-a.example.com"},
    "mgr-a": {"uid": "u-mgr-a", "firm_id": "firm-a", "firm_role": "manager"},
    "emp-b": {"uid": "u-emp-b", "firm_id": "firm-b", "firm_role": "employee"},
    "nofirm": {"uid": "u-solo"},
    "nouid": {"firm_id": "firm-a", "firm_role": "employee"},
    # No email claim at all -- the degraded-but-real case (bd
    # polyglot-pdf-cpsi0): a token missing the claim must not crash the
    # mint, and both new fields must simply come back None.
    "emp-noemail": {"uid": "u-emp-noemail", "firm_id": "firm-a",
                    "firm_role": "employee"},
}

_ALLOWED = {"firm-a": ["firm-a-intake"], "firm-b": ["firm-b-intake"]}

# The default fixture firm is MOCK on purpose. Every pre-A3 test in this file
# mints with LINK_CHANNEL unset, and A3's gate refuses a LIVE firm on any
# channel that is not explicitly "demo" -- so a live default would have made
# the whole file about the new gate rather than about the routes. The gate's
# own eight cases get their own firm docs, below.
_START_BALANCE = 50


class _Redemptions:
    """In-memory stand-in for the Firestore redemption store."""

    def __init__(self):
        self.records = {}
        self.fail = None          # set to an exception class to simulate

    def open_link(self, jti, firm_id, kit_id, now=None):
        if self.fail is not None:
            raise self.fail("simulated")
        import time as _t
        rec = self.records.get(jti)
        if rec is not None:
            if rec.get("completed_at"):
                raise LinkAlreadyUsed("already completed")
            return rec
        # REAL wall-clock: the completion deadline is opened_at + window, so
        # a fixed epoch stamp would make every link look decades expired.
        rec = {"jti": jti, "firm_id": firm_id, "kit_id": kit_id,
               "opened_at": int(_t.time()), "completed_at": None}
        self.records[jti] = rec
        return rec


def _wire_db(monkeypatch, db):
    """Point every Firestore consumer on the mint/open path at one fake db.

    THREE call sites, not one, and they are patched separately on purpose:
    link_routes imported get_db at module load (the mint transaction's
    client), while links_store and kit_commercials import it LAZILY inside
    their functions. Patching only the module-level name would leave the
    mint record and the kit price reading a real (absent) client, which is
    exactly the shape of failure that looks like "the feature works" in a
    test and 503s in production.
    """
    monkeypatch.setattr(lr, "get_db", lambda: db)
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)
    import firebase_admin
    monkeypatch.setattr(firebase_admin, "firestore", _FakeFirestoreModule(),
                        raising=False)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LINK_TOKEN_SECRET", _SECRET)
    monkeypatch.setenv("LINK_BASE_URL", "https://forms.example.com")
    monkeypatch.setenv("VFF_DISABLE_AUTH", "false")
    monkeypatch.delenv("LINK_CHANNEL", raising=False)
    # LINK_MINTING_ENABLED moved off os.getenv to runtime_config (bd
    # polyglot-pdf-bg313): patch the resolver these tests actually exercise
    # rather than an env var the route no longer reads. CREDITS_ENFORCED
    # (bd polyglot-pdf-jecrl) is patched the same way and defaults ON here,
    # because the enforced path is the one with the interesting refusals --
    # test_credits_enforced_flag_gates_refusal drives the off case.
    monkeypatch.setattr(lr, "_rc_minting_enabled", lambda: True)
    monkeypatch.setattr(lr, "_rc_credits_enforced", lambda: True)

    def _verify(token):
        claims = _TOKENS.get(token)
        if claims is None:
            raise HTTPException(status_code=401, detail="bad token")
        return dict(claims)

    monkeypatch.setattr("backend.services.auth.verify_token", _verify)
    monkeypatch.setattr(lr, "get_allowed_kits",
                        lambda firm_id: list(_ALLOWED.get(firm_id, [])))
    db = _FakeDb({
        ("firms", "firm-a"): {"name": "Firm A", "status": "active",
                              "kind": "mock",
                              "balance_credits": _START_BALANCE},
        ("firms", "firm-b"): {"name": "Firm B", "status": "active",
                              "kind": "mock",
                              "balance_credits": _START_BALANCE},
    })
    _wire_db(monkeypatch, db)
    store = _Redemptions()
    # /open now goes through enforce_link_redemption, which calls open_link
    # inside link_redemptions -- patch it THERE so these tests exercise the
    # REAL gate (completion-window check included) rather than standing in
    # for the whole thing. The MINT-RECORD half of that gate is deliberately
    # NOT stubbed: it reads the fake db above, so an open only succeeds when
    # the mint actually wrote a record.
    monkeypatch.setattr("backend.services.link_redemptions.open_link",
                        store.open_link)

    app = FastAPI()
    app.include_router(lr.router)
    store.db = db
    return TestClient(app), store


def _mint(c, token="emp-a", **body):
    body.setdefault("kit_id", "firm-a-intake")
    return c.post("/api/links/mint", json=body,
                  headers={"Authorization": "Bearer " + token})


# --- minting -----------------------------------------------------------------


def test_an_employee_mints_a_link_for_their_own_firms_kit(client):
    """Exit criterion 1's first half. Note the ROLE: an EMPLOYEE mints links
    -- that is their job in the four-level model. Unlike retiring a form,
    this is not manager-only."""
    c, _store = client

    resp = _mint(c)

    assert resp.status_code == 200
    body = resp.json()
    assert body["url"].startswith("https://forms.example.com/f#t=")
    assert body["jti"]
    assert body["expires_at"] > 0


def test_the_token_rides_in_the_URL_FRAGMENT(client):
    """Browsers do not send the fragment to servers, so the credential stays
    out of access logs, referrer headers, and proxy logs. A query string
    would put a working credential in every log between here and the client.

    Mutation: build the URL with "?t=" -- red.
    """
    c, _store = client

    url = _mint(c).json()["url"]

    assert "#t=" in url, "the token must ride in the fragment, not the query"
    assert "?" not in url


def test_the_link_is_attributed_to_the_MINTING_EMPLOYEE_from_the_token(client):
    """The telemetry requirement: every session traces to the employee who
    sent the link. employee_id comes from the VERIFIED uid -- never the
    request body, which a caller could forge to blame a colleague.

    Mutation: read employee_id from the body -- red (there is nowhere in the
    request model to put it, so the route would not even build).
    """
    from backend.services.link_tokens import verify_link_token

    c, _store = client

    url = _mint(c, token="emp-a").json()["url"]
    payload = verify_link_token(url.split("#t=", 1)[1])

    assert payload["employee_id"] == "u-emp-a"
    assert payload["firm_id"] == "firm-a"


def test_a_mint_stamps_actor_email_on_the_ledger_and_employee_email_on_the_record(
        client):
    """EXIT CRITERION 1: a mint on staging writes actor_email on the
    mint_debit ledger entry AND employee_email on the links/{jti} mint
    record -- both from the verified token's email claim, never the
    request body (there is nowhere in MintLinkRequest to put one).

    Mutation: drop `actor_email=employee_email` from the append_entry() call
    in _reserve_mint -- the ledger assertion goes red. Mutation: drop
    `employee_email=employee_email` from the build_mint_record() call --
    the mint-record assertion goes red. Verified 2026-09-15."""
    c, store = client

    resp = _mint(c, token="emp-a")

    assert resp.status_code == 200
    jti = resp.json()["jti"]
    rows = _ledger(store)
    assert len(rows) == 1
    assert rows[0]["actor"] == "u-emp-a"
    assert rows[0]["actor_email"] == "emp-a@firm-a.example.com"
    records = store.db.link_rows()
    assert records[jti]["employee_id"] == "u-emp-a"
    assert records[jti]["employee_email"] == "emp-a@firm-a.example.com"


def test_a_mint_with_no_email_claim_leaves_both_fields_none(client):
    """A token missing the email claim (should not happen for a real
    Firebase account, but is not assumed) must not crash the mint, and must
    not invent a placeholder -- both new fields come back None, exactly the
    pre-cpsi0 shape.

    Mutation: default employee_email to "" instead of None when the claim
    is absent -- red (the stored value is "" instead of None)."""
    c, store = client

    resp = _mint(c, token="emp-noemail")

    assert resp.status_code == 200
    jti = resp.json()["jti"]
    rows = _ledger(store)
    assert rows[0]["actor_email"] is None
    records = store.db.link_rows()
    assert records[jti]["employee_email"] is None


def test_minting_a_kit_the_firm_does_not_hold_is_a_404(client):
    """Not 403: the response must not reveal which kits other firms hold --
    the same existence rule as the kit read gates."""
    c, _store = client

    resp = _mint(c, token="emp-a", kit_id="firm-b-intake")

    assert resp.status_code == 404


def test_a_caller_with_no_firm_claim_cannot_mint(client):
    c, _store = client
    assert _mint(c, token="nofirm").status_code == 403


def test_a_caller_with_no_uid_cannot_mint(client):
    """An unattributable link would silently break the telemetry
    requirement, so refuse rather than mint one."""
    c, _store = client
    assert _mint(c, token="nouid").status_code == 403


def test_minting_is_OFF_unless_explicitly_enabled(client, monkeypatch):
    """THE SAFETY INTERLOCK. A live link is an unauthenticated door to a paid
    Gemini session, and the spend ceiling is a separate bead (ik7e). This
    flag is what stops this bead shipping a mintable link before that lands.

    404 rather than 503: a disabled endpoint should not advertise itself.

    Mutation: default the flag to "true" -- red.
    """
    c, _store = client
    monkeypatch.setattr(lr, "_rc_minting_enabled", lambda: False)

    assert _mint(c).status_code == 404


def test_the_minting_flag_check_runs_OFF_the_event_loop(client, monkeypatch):
    """bd polyglot-pdf-bg313, Opus cross-surface r1 (blocker).

    _minting_enabled() now resolves runtime_config, which on a cache miss is
    a SYNC Admin-SDK Firestore read -- exactly the hazard services/auth.py's
    require_auth already documents: a sync read inside an async route blocks
    the SHARED Cloud Run loop, stalling every concurrent request (in-flight
    audio included). Every other test here stubs the resolver to return
    instantly, which makes a missing to_thread wrapper invisible -- this one
    pins that the route dispatches the check through asyncio.to_thread (the
    same mechanism the sibling get_allowed_kits/enforce_link_redemption calls
    in this file already use) instead of calling it directly.

    TestClient runs the whole ASGI app in its own worker thread regardless of
    what mint_link does internally, so comparing thread identities against
    the pytest test-function thread is not a reliable signal here -- spying
    on asyncio.to_thread itself is.

    Mutation: replace `await asyncio.to_thread(_minting_enabled)` in
    link_routes.mint_link with a direct `_minting_enabled()` call -- red,
    because to_thread is then never invoked for this check.
    """
    import asyncio as _asyncio

    c, _store = client
    calls = []
    real_to_thread = _asyncio.to_thread

    async def spy_to_thread(func, *a, **kw):
        calls.append(func)
        return await real_to_thread(func, *a, **kw)

    monkeypatch.setattr(_asyncio, "to_thread", spy_to_thread)

    resp = _mint(c)

    assert resp.status_code == 200
    assert lr._minting_enabled in calls, (
        "_minting_enabled was not dispatched via asyncio.to_thread -- a "
        "Firestore cache miss on the mint route now blocks the shared "
        "Cloud Run event loop for every concurrent request"
    )


def test_minting_refuses_when_no_base_url_is_configured(client, monkeypatch):
    """Deriving it from the Host header would let a caller mint links
    pointing at a domain THEY control, carrying our valid signature."""
    c, _store = client
    monkeypatch.setenv("LINK_BASE_URL", "")

    assert _mint(c).status_code == 503


def test_the_requested_windows_are_CAPPED(client):
    """A mis-set console must not be able to mint a near-permanent link.
    Mutation: pass body.open_window_s straight through -- red."""
    from backend.services.link_tokens import verify_link_token

    c, _store = client

    resp = _mint(c, open_window_s=10 ** 9, complete_window_s=10 ** 9)
    payload = verify_link_token(resp.json()["url"].split("#t=", 1)[1])

    assert payload["exp"] - payload["iat"] <= lr._MAX_OPEN_WINDOW_S
    assert payload["cw"] <= lr._MAX_COMPLETE_WINDOW_S


# --- opening (the unauthenticated surface) -----------------------------------


def _open(c, token):
    return c.post("/api/links/open", json={"token": token})


def test_a_client_opens_a_valid_link_with_NO_ACCOUNT(client):
    """Exit criterion 1: a minted link reaches exactly the one kit it names,
    for the firm it names, with no sign-in whatsoever. Note there is no
    Authorization header anywhere in this test."""
    c, _store = client

    url = _mint(c).json()["url"]
    resp = _open(c, url.split("#t=", 1)[1])

    assert resp.status_code == 200
    body = resp.json()
    assert body["kit_id"] == "firm-a-intake"
    assert body["firm_id"] == "firm-a"
    assert body["complete_by"] > 0


def test_the_FIRST_OPEN_record_names_the_kit(client):
    """The record the firm joins on must name the form.

    /open normalizes the token's `kit_id` into the `link_kit_id` the shared
    gate reads. Removing that normalization passed all 110 link tests while
    writing `kit_id=None` into the first-open record -- silently corrupting
    the audit record the split-key design exists to produce (Opus r7).

    Mutation: drop the `link_kit_id` normalization in open_client_link -- red.
    """
    c, store = client

    token = _mint(c).json()["url"].split("#t=", 1)[1]
    jti = _open(c, token).json()["jti"]

    assert store.records[jti]["kit_id"] == "firm-a-intake"
    assert store.records[jti]["firm_id"] == "firm-a"


def test_the_open_response_carries_NO_client_identifier_and_NO_kit_list(client):
    """Exit criterion 2, at the response boundary: the client sees exactly
    their one form. Leaking the firm's kit list here would hand every client
    a directory of that firm's private forms.

    Mutation: add the allowlist to the response -- red.
    """
    c, _store = client

    url = _mint(c).json()["url"]
    body = _open(c, url.split("#t=", 1)[1]).json()

    assert set(body) == {"kit_id", "firm_id", "jti", "complete_by"}


@pytest.mark.parametrize(
    "mangle, why",
    [
        (lambda t: t[:-4] + "AAAA", "a forged signature"),
        (lambda t: "garbage", "a non-token string"),
        (lambda t: "", "an empty token"),
        (lambda t: t.replace(".", "", 1), "a malformed shape"),
    ],
    ids=["forged-sig", "garbage", "empty", "malformed"],
)
def test_every_bad_token_gets_the_SAME_refusal(client, mangle, why):
    """The refusals must be indistinguishable -- status AND body. Differences
    between "bad signature", "expired", and "already used" would let an
    outsider probe which links exist.

    Mutation: return a distinct detail for any one branch -- red.
    """
    c, _store = client
    url = _mint(c).json()["url"]
    good = url.split("#t=", 1)[1]

    resp = _open(c, mangle(good))

    assert resp.status_code == 404, why
    assert resp.json()["detail"] == "This link is not valid."


def test_a_REPLAYED_link_is_refused_after_completion(client):
    """ONE completion per link (maintainer, 2026-08-17). Mutation: drop the
    completed_at check in the store -- red."""
    c, store = client

    url = _mint(c).json()["url"]
    token = url.split("#t=", 1)[1]
    first = _open(c, token)
    assert first.status_code == 200

    import time as _t
    store.records[first.json()["jti"]]["completed_at"] = int(_t.time())
    replayed = _open(c, token)

    assert replayed.status_code == 404
    assert replayed.json()["detail"] == "This link is not valid."


def test_reopening_an_UNFINISHED_link_still_works(client):
    """A refresh, a dropped connection, or coming back after lunch must not
    lock the client out -- that turns a network blip into "your link is dead,
    call the firm". Only COMPLETION burns the link.

    Mutation: refuse any second open -- red.
    """
    c, _store = client

    token = _mint(c).json()["url"].split("#t=", 1)[1]
    assert _open(c, token).status_code == 200
    assert _open(c, token).status_code == 200


def test_entitlement_is_RECHECKED_at_open_not_trusted_from_mint(client,
                                                                monkeypatch):
    """A firm can be suspended, or a kit retired, in the 48 hours between
    minting and opening. Trusting the mint-time snapshot would keep serving a
    suspended firm's links.

    Mutation: drop the get_allowed_kits call in open -- red.
    """
    c, _store = client
    token = _mint(c).json()["url"].split("#t=", 1)[1]

    # The firm loses the kit (suspended, or the kit was retired).
    monkeypatch.setattr(lr, "get_allowed_kits", lambda firm_id: [])

    assert _open(c, token).status_code == 404


def test_an_unreachable_redemption_store_FAILS_CLOSED(client):
    """Unable to confirm a link is unredeemed means we must NOT admit it --
    the failure being guarded is a replayed link starting a second paid
    session. This is the opposite polarity from the firm allowlist read,
    which fails closed by returning an empty list.

    Mutation: treat RedemptionUnavailable as "fresh link, proceed" -- red.
    """
    c, store = client
    token = _mint(c).json()["url"].split("#t=", 1)[1]
    store.fail = RedemptionUnavailable

    assert _open(c, token).status_code == 404


def test_opening_requires_no_authorization_header_at_all(client):
    """Explicit: the client tier has no account, so the route must not be
    behind require_auth. Mutation: add the dependency -- red (401)."""
    c, _store = client
    token = _mint(c).json()["url"].split("#t=", 1)[1]

    resp = c.post("/api/links/open", json={"token": token})

    assert resp.status_code == 200


@pytest.mark.parametrize(
    "bad_stamp",
    [0, -1, None, "yesterday", True, 99_999_999_999],
    ids=["epoch", "negative", "missing", "string", "bool", "far-future"],
)
def test_an_IMPLAUSIBLE_opened_at_does_not_lock_a_client_out(client, bad_stamp):
    """The completion deadline is opened_at + window, so a corrupt stamp is
    not cosmetic: 0 computes a deadline in 1970 and refuses a client who just
    opened their link, while a far-future stamp would extend the window
    indefinitely. Neither is acceptable, so an implausible value falls back to
    NOW -- the conservative reading that this open is the first one.

    Found while writing these tests: my own fake returned a fixed epoch
    stamp, every open 404'd, and the route had trusted the stored value
    without question.

    Mutation: use record["opened_at"] directly -- the epoch/negative/missing
    cases go red.
    """
    c, store = client
    token = _mint(c).json()["url"].split("#t=", 1)[1]

    first = _open(c, token)
    assert first.status_code == 200
    store.records[first.json()["jti"]]["opened_at"] = bad_stamp

    assert _open(c, token).status_code == 200


def test_a_caller_CANNOT_forge_attribution_through_the_request_body(client):
    """Attribution must come from the verified token, never the request.

    Pinned at the MODEL, because that is where the property actually lives:
    MintLinkRequest has no employee_id/firm_id field, so a client supplying
    one is ignored by pydantic and cannot reach the mint call. Trying to
    mutate the route into reading it (`getattr(body, "employee_id", ...)`)
    is a NO-OP for exactly that reason -- which is why asserting the field
    SET is the honest pin, not a route-level mutation that cannot bite.
    """
    from backend.routes.link_routes import MintLinkRequest

    assert set(MintLinkRequest.model_fields) == {
        "kit_id", "open_window_s", "complete_window_s",
    }, "a new request field could become a forged-attribution vector"

    c, _store = client
    url = _mint(c, token="emp-a", employee_id="u-mgr-a",
                firm_id="firm-b").json()["url"]

    from backend.services.link_tokens import verify_link_token
    payload = verify_link_token(url.split("#t=", 1)[1])

    assert payload["employee_id"] == "u-emp-a", "attribution came from the body"
    assert payload["firm_id"] == "firm-a"


def test_a_link_from_ANOTHER_CHANNEL_is_a_404_at_the_route(client, monkeypatch):
    """Channel isolation, end to end (bd polyglot-pdf-3q9qn).

    Maintainer, 2026-09-01: "staging links only work for staging firms on the
    staging site, and same with demo." The unit tests pin verify_link_token's
    refusal; this pins that the REFUSAL REACHES THE ROUTE -- a link minted on
    staging must not open here, and must be indistinguishable from any other
    invalid link (the same 404 as a bad signature or an expired window, so the
    response cannot be used to probe which channel minted a token).
    """
    c, _store = client

    monkeypatch.setenv("LINK_CHANNEL", "staging")
    url = _mint(c).json()["url"]
    token = url.split("#t=", 1)[1]

    monkeypatch.setenv("LINK_CHANNEL", "demo")
    resp = _open(c, token)

    assert resp.status_code == 404
    assert resp.json()["detail"] == "This link is not valid."
    # The channel name must NOT leak into the response -- the diagnosis is
    # logged for the operator, never returned to the caller.
    assert "staging" not in resp.text


# --- Epic 2 bead A3: reserve before signing ----------------------------------


def _ledger(store, firm_id="firm-a"):
    return store.db.ledger_rows(firm_id)


def _balance(store, firm_id="firm-a"):
    return store.db.firm(firm_id)["balance_credits"]


def test_a_funded_mint_debits_the_ledger_and_writes_the_record(client):
    """EXIT CRITERION 1, the happy half: one mint costs exactly credit_cost,
    writes exactly one mint_debit entry, and leaves exactly one links/{jti}
    record naming the same jti the caller was handed.

    Mutation: drop extra_writes=_extra_writes from _reserve_mint's
    append_entry call -- red (the record is gone while the debit stands).
    """
    c, store = client

    resp = _mint(c)

    assert resp.status_code == 200
    jti = resp.json()["jti"]
    assert _balance(store) == _START_BALANCE - 1
    rows = _ledger(store)
    assert len(rows) == 1
    assert rows[0]["type"] == "mint_debit"
    assert rows[0]["amount"] == -1
    assert rows[0]["link_jti"] == jti
    assert rows[0]["kit_id"] == "firm-a-intake"
    assert rows[0]["actor"] == "u-emp-a"
    records = store.db.link_rows()
    assert set(records) == {jti}
    assert records[jti]["status"] == "minted"
    assert records[jti]["credit_cost"] == 1
    assert records[jti]["firm_id"] == "firm-a"


def test_mint_refuses_at_zero_balance(client):
    """EXIT CRITERION 1. A firm with nothing left cannot mint: 402, the
    staff-facing status (this door is authenticated, so it may say why --
    the uniform-404 oracle rule guards the UNAUTHENTICATED /open).

    Mutation: pass require_sufficient_balance=False unconditionally in
    _reserve_mint -- red (the mint succeeds and the balance goes to -1).
    """
    c, store = client
    store.db.docs[("firms", "firm-a")]["balance_credits"] = 0

    resp = _mint(c)

    assert resp.status_code == 402


def test_refused_mint_leaves_no_openable_token(client):
    """EXIT CRITERION 1, and the WHOLE POINT of reserve-before-sign: a
    refused mint leaves NO signed token, NO ledger entry and NO mint record.

    The assertions are separate on purpose. A version that signed first and
    refused second would return a token in the body (caught by the first),
    and a version that wrote the debit outside the transaction would leave
    an entry behind a refusal (caught by the second) -- both are ways of
    failing that "nothing was reserved" alone would not catch.

    Mutation: move the mint_link_token call ABOVE the _reserve_mint call and
    return its url on refusal -- red.
    """
    c, store = client
    store.db.docs[("firms", "firm-a")]["balance_credits"] = 0

    resp = _mint(c)

    assert resp.status_code == 402
    assert "url" not in resp.json(), "a refused mint must not return a token"
    assert _ledger(store) == [], "a refused mint must write no ledger entry"
    assert store.db.link_rows() == {}, "a refused mint must write no record"
    assert _balance(store) == 0, "a refused mint must not move the balance"


def test_credits_enforced_flag_gates_refusal(client, monkeypatch):
    """EXIT CRITERION 1's third test. With CREDITS_ENFORCED OFF the debit is
    STILL written and the balance may go negative -- the metered soft-launch
    mode that runs until seeds are granted (Epic 2 bead A6). Turning the flag
    on is what makes a zero balance a 402.

    Both halves are asserted in one test because the flag's whole meaning is
    the DIFFERENCE between them: a test of the off case alone would pass
    against a route that never enforced at all.

    Mutation: hard-code enforced=True in mint_link -- the off half goes red.
    Mutation: hard-code enforced=False -- the on half goes red.
    """
    c, store = client
    store.db.docs[("firms", "firm-a")]["balance_credits"] = 0

    # OFF: the mint succeeds, the debit is written, the balance goes negative.
    monkeypatch.setattr(lr, "_rc_credits_enforced", lambda: False)
    off = _mint(c)
    assert off.status_code == 200
    assert _balance(store) == -1
    assert len(_ledger(store)) == 1
    assert _ledger(store)[0]["amount"] == -1

    # ON: the same negative balance now refuses, and writes nothing more.
    monkeypatch.setattr(lr, "_rc_credits_enforced", lambda: True)
    on = _mint(c)
    assert on.status_code == 402
    assert _balance(store) == -1, "the refused mint must not move it again"
    assert len(_ledger(store)) == 1, "the refused mint must add no entry"


@pytest.mark.parametrize(
    "channel, kind, expect_ok",
    [
        # channel demo -- the ONE deployment a live firm may be charged from
        ("demo", "mock", True),
        ("demo", "live", True),
        ("demo", None, True),
        # channel staging -- never a live firm, never a kindless firm
        ("staging", "mock", True),
        ("staging", "live", False),
        # channel UNSET -- link_channel() would call this "demo"; the gate
        # reads the RAW env var and does not
        (None, "mock", True),
        (None, "live", False),
        (None, None, False),
    ],
    ids=["demo-mock", "demo-live", "demo-nokind",
         "staging-mock", "staging-live",
         "unset-mock", "unset-live", "unset-nokind"],
)
def test_live_firm_mints_only_on_explicit_demo_channel(
    client, monkeypatch, channel, kind, expect_ok
):
    """EXIT CRITERION 2, all eight cases (plan: "channel demo/staging/unset x
    kind mock/live, plus demo/unset x missing kind").

    THE POINT OF THE THREE UNSET ROWS: link_channel() defaults to demo
    (services/link_tokens.py, so an unconfigured deploy keeps working), so a
    gate asking IT would treat a laptop or a misconfigured revision as the
    demo and let it debit a paying firm. _live_firm_channel_ok reads
    os.environ LINK_CHANNEL raw instead, which is why unset-live and
    unset-nokind refuse while unset-mock still mints.

    A firm with NO kind is treated as live -- the fail-closed polarity
    firms.firm_kind() uses, because a mis-defaulted mock firm merely blocks
    staging while a mis-defaulted live firm mints for free. So demo-nokind
    MINTS (demo is the one channel a live firm may be charged from) while
    unset-nokind REFUSES: kindless behaves exactly like live, in both
    directions, which is the whole content of "treated as live".

    Mutation: swap os.environ.get("LINK_CHANNEL") for link_channel() in
    _live_firm_channel_ok -- the two unset-refusing rows go red. Mutation:
    default a missing kind to mock -- unset-nokind goes red.
    """
    c, store = client
    if channel is None:
        monkeypatch.delenv("LINK_CHANNEL", raising=False)
    else:
        monkeypatch.setenv("LINK_CHANNEL", channel)
    firm = store.db.docs[("firms", "firm-a")]
    if kind is None:
        firm.pop("kind", None)
    else:
        firm["kind"] = kind

    resp = _mint(c)

    if expect_ok:
        assert resp.status_code == 200, resp.text
        assert _balance(store) == _START_BALANCE - 1
    else:
        assert resp.status_code == 403, resp.text
        assert _balance(store) == _START_BALANCE, "a refused mint must not debit"
        assert _ledger(store) == []
        assert store.db.link_rows() == {}
        assert store.db.link_rows("links_staging") == {}


def test_unset_channel_still_mints_demo_audience(client, monkeypatch):
    """EXIT CRITERION 2's other half, and the reason the gate does NOT call
    link_channel(). Both behaviours must hold at once on an unset channel: a
    live firm is REFUSED (the test above), and a mock firm still mints a
    token whose aud is demo -- today's behaviour, deliberately unchanged, so
    an unconfigured deploy keeps opening the links it already minted.

    Mutation: make the gate refuse whenever LINK_CHANNEL is unset (rather
    than only for live/kindless firms) -- red. Mutation: change
    link_tokens.DEFAULT_CHANNEL away from demo -- red.
    """
    from backend.services.link_tokens import verify_link_token

    c, _store = client
    monkeypatch.delenv("LINK_CHANNEL", raising=False)

    resp = _mint(c)

    assert resp.status_code == 200
    payload = verify_link_token(resp.json()["url"].split("#t=", 1)[1])
    assert payload["aud"] == "demo"


def test_the_signed_token_carries_the_kits_resolved_cap_usd(client):
    """The A4 half of the same mint: burn_cap_usd is resolved ONCE, here, and
    signed in -- so the socket needs no per-connect kit read.

    Mutation: drop cap_usd=cap_usd from the mint_link_token call -- red.
    """
    from backend.services.link_tokens import verify_link_token

    c, store = client
    store.db.docs[("kits", "firm-a-intake")] = {
        "credit_cost": 3, "burn_cap_usd": 4.5,
    }

    resp = _mint(c)

    payload = verify_link_token(resp.json()["url"].split("#t=", 1)[1])
    assert payload["cap_usd"] == 4.5
    # ... and the SAME resolved numbers are snapshotted on the record, so the
    # sweep and the console do not have to decode a token to price a link.
    record = store.db.link_rows()[resp.json()["jti"]]
    assert record["cap_usd"] == 4.5
    assert record["credit_cost"] == 3
    assert _balance(store) == _START_BALANCE - 3, "the kit's price, not 1"


def test_an_unpriced_kit_rides_the_defaults_rather_than_minting_free(client):
    """A kit with NO commercial doc must cost the default credit and carry
    the global ceiling -- never zero and never no-cap. A mis-priced mint that
    charges a credit is recoverable with an adjustment entry; one that
    charges nothing is invisible revenue loss.

    Mutation: default kit_commercials.DEFAULT_CREDIT_COST to 0 -- red (the
    ledger refuses a zero amount, so the mint 503s). Mutation: return
    cap_usd=None for a missing doc -- red (no cap claim on the token).
    """
    from backend.services.link_budget import default_cost_ceiling_usd
    from backend.services.link_tokens import verify_link_token

    c, store = client
    assert ("kits", "firm-a-intake") not in store.db.docs

    resp = _mint(c)

    assert resp.status_code == 200
    record = store.db.link_rows()[resp.json()["jti"]]
    assert record["credit_cost"] == 1
    assert record["cap_usd"] == default_cost_ceiling_usd()
    payload = verify_link_token(resp.json()["url"].split("#t=", 1)[1])
    assert payload["cap_usd"] == default_cost_ceiling_usd()


def test_the_mint_record_deadline_equals_the_tokens_exp(client):
    """The A5 expiry sweep queries Firestore on open_deadline to decide what
    to refund. If it drifted from the token's exp the sweep would either
    refund a link that can still open, or leave a dead link unrefunded -- so
    the route pins both to ONE clock.

    Mutation: drop now=issued from the mint_link_token call and let it read
    time.time() again -- red whenever the two calls straddle a second.
    """
    from backend.services.link_tokens import verify_link_token

    c, store = client

    resp = _mint(c)
    payload = verify_link_token(resp.json()["url"].split("#t=", 1)[1])
    record = store.db.link_rows()[resp.json()["jti"]]

    assert record["open_deadline"] == payload["exp"]


def test_the_mint_record_shape_matches_links_store(client):
    """ONE record shape, two writers. The route's transaction writes through
    links_store.build_mint_record(); links_store.record_mint()'s plain set()
    writes the same builder's output. A transactional copy that drifted would
    produce records the sweep, the open gate and the console read
    differently.

    Mutation: inline a hand-built dict in _reserve_mint's _extra_writes --
    red as soon as build_mint_record gains or loses a key.
    """
    c, store = client

    jti = _mint(c).json()["jti"]

    written = store.db.link_rows()[jti]
    expected = links_store.build_mint_record(
        jti=jti, firm_id="firm-a", kit_id="firm-a-intake",
        employee_id="u-emp-a", credit_cost=written["credit_cost"],
        cap_usd=written["cap_usd"],
        open_deadline=written["open_deadline"],
        now=written["minted_at"],
        # emp-a's token carries an email claim (bd polyglot-pdf-cpsi0) --
        # see _TOKENS' own comment. Omitting this here would fail for the
        # SAME reason the docstring names: a drift between the transactional
        # writer and this builder.
        employee_email="emp-a@firm-a.example.com",
    )
    assert written == expected


def test_a_staging_mint_writes_the_staging_collection(client, monkeypatch):
    """Channel isolation reaches the MINT RECORD too, not just the token's
    aud. A staging mint that wrote the demo links collection would let a
    staging token open on the demo (the open gate reads links[_<channel>]),
    which is the whole failure channel isolation exists to prevent.

    Mutation: pass a literal "demo" as _reserve_mint's channel -- red.
    """
    c, store = client
    monkeypatch.setenv("LINK_CHANNEL", "staging")

    jti = _mint(c).json()["jti"]

    assert set(store.db.link_rows("links_staging")) == {jti}
    assert store.db.link_rows("links") == {}


def test_the_reservation_runs_OFF_the_event_loop(client, monkeypatch):
    """The reservation is a MULTI-ROUND-TRIP sync Admin-SDK transaction -- by
    far the longest Firestore call on this route. Running it inline in the
    coroutine would block the SHARED Cloud Run loop for the whole
    transaction, stalling every concurrent request including in-flight audio.

    Mutation: call _reserve_mint(...) directly instead of via
    asyncio.to_thread -- red.
    """
    import asyncio as _asyncio

    c, _store = client
    calls = []
    real_to_thread = _asyncio.to_thread

    async def spy_to_thread(func, *a, **kw):
        calls.append(func)
        return await real_to_thread(func, *a, **kw)

    monkeypatch.setattr(_asyncio, "to_thread", spy_to_thread)

    assert _mint(c).status_code == 200
    assert lr._reserve_mint in calls, (
        "the mint reservation transaction was not dispatched via "
        "asyncio.to_thread -- it blocks the shared Cloud Run event loop"
    )
    assert lr.resolve_commercial in calls, (
        "the kit commercial read was not dispatched via asyncio.to_thread"
    )


# --- Epic 2 bead A3: open requires a mint record ------------------------------


def test_open_refuses_without_mint_record(client):
    """EXIT CRITERION 3. A token that verifies perfectly but has NO mint
    record cannot open -- the deliberate one-time cutover for tokens minted
    before the record existed, and the enforcement half of reserve-before-
    sign (no reservation, no session).

    The refusal is the UNIFORM 404, byte-identical to a forged signature, so
    it adds no oracle.

    Mutation: delete the _require_mint_record call from
    enforce_link_redemption -- red.
    """
    c, store = client

    token = _mint(c).json()["url"].split("#t=", 1)[1]
    # Exactly the pre-cutover state: a valid signed token, no record.
    jti = [k[1] for k in store.db.docs if k[0] == "links"][0]
    del store.db.docs[("links", jti)]

    resp = _open(c, token)

    assert resp.status_code == 404
    assert resp.json()["detail"] == "This link is not valid."


@pytest.mark.parametrize("status", ["revoked", "refunded"])
def test_revoked_link_cannot_open(client, status):
    """EXIT CRITERION 3. A link an operator revoked, or one the expiry sweep
    already refunded, is refused with the same uniform 404.

    Parametrized over BOTH blocking statuses rather than just revoked,
    because they are one rule (links_store.OPEN_BLOCKING_STATUSES) and a
    single-status test would pass against a gate that hard-coded the other
    one -- and a refunded link that could still open would buy a session
    whose credit had already been given back.

    Mutation: check status == "revoked" instead of the set -- the refunded
    case goes red. Mutation: empty OPEN_BLOCKING_STATUSES -- both go red.
    """
    c, store = client

    resp = _mint(c)
    jti = resp.json()["jti"]
    token = resp.json()["url"].split("#t=", 1)[1]
    store.db.docs[("links", jti)]["status"] = status

    refused = _open(c, token)

    assert refused.status_code == 404
    assert refused.json()["detail"] == "This link is not valid."


@pytest.mark.parametrize("status", ["minted", "opened", "completed",
                                    "budget_exhausted"])
def test_every_other_status_falls_through_to_the_redemption_gate(client,
                                                                 status):
    """The complement of the rule above, and it is load-bearing: opened and
    completed are BEST-EFFORT MIRRORS, so refusing on them would let a failed
    mirror write lock a client out of a form they are part-way through --
    exactly the reopen-an-unfinished-link behaviour the seven-day completion
    window exists to provide. budget_exhausted is telemetry only (the
    socket's own spend ceiling is what stops the spending).

    Parametrized over the WHOLE remainder of links_store.ALL_STATUSES, not a
    sample: a test of one status would say nothing about the others, and the
    rule being pinned is precisely "every other status".

    Mutation: add any of these to OPEN_BLOCKING_STATUSES -- that row goes
    red.
    """
    c, store = client

    resp = _mint(c)
    jti = resp.json()["jti"]
    token = resp.json()["url"].split("#t=", 1)[1]
    store.db.docs[("links", jti)]["status"] = status

    assert _open(c, token).status_code == 200


def test_the_blocking_and_falling_through_sets_cover_every_status():
    """DERIVE THE COVERAGE, do not hand-list it. The two parametrized tests
    above split links_store.ALL_STATUSES between them; this asserts the split
    is exhaustive, so a NEW status added to the store cannot slip in
    untested and un-decided.

    Mutation: add a seventh status to ALL_STATUSES without deciding which
    side it belongs on -- red.
    """
    blocked = set(links_store.OPEN_BLOCKING_STATUSES)
    falls_through = {"minted", "opened", "completed", "budget_exhausted"}

    assert blocked | falls_through == set(links_store.ALL_STATUSES)
    assert not (blocked & falls_through)


def test_the_mint_record_gate_runs_BEFORE_the_redemption_write(client):
    """ORDER MATTERS. enforce_link_redemption calls _require_mint_record
    FIRST, before open_link() creates the redemption doc. Checking after
    would stamp opened_at on a link about to be refused -- which for a
    revoked link burns a redemption record for a session that never happened,
    and for a never-minted token leaves a record for a link that never
    existed.

    Mutation: move the _require_mint_record call below the open_link call in
    enforce_link_redemption -- red (a redemption record appears).
    """
    c, store = client

    resp = _mint(c)
    jti = resp.json()["jti"]
    token = resp.json()["url"].split("#t=", 1)[1]
    store.db.docs[("links", jti)]["status"] = "revoked"

    assert _open(c, token).status_code == 404
    assert store.records == {}, (
        "the refused open still wrote a redemption record -- the mint-record "
        "gate ran after open_link instead of before it"
    )


def test_an_unreachable_links_store_FAILS_CLOSED_at_open(client, monkeypatch):
    """Same polarity as the redemption store: unable to confirm a credit was
    reserved must not admit a paid session. get_link RAISES rather than
    returning None on an outage precisely so the two cases stay
    distinguishable in the log while both refuse.

    Mutation: catch LinksStoreUnavailable in _require_mint_record and return
    instead of raising (i.e. admit the link) -- red.
    """
    c, _store = client
    token = _mint(c).json()["url"].split("#t=", 1)[1]

    def _boom(jti, channel=None):
        raise links_store.LinksStoreUnavailable("simulated outage")

    monkeypatch.setattr(links_store, "get_link", _boom)

    assert _open(c, token).status_code == 404


def test_a_successful_open_mirrors_the_record_to_opened(client):
    """The best-effort console mirror. It is a DERIVED CACHE -- the
    authoritative "was this opened" answer is the redemption doc -- but the
    admin console's link table reads it, so a successful open must move
    minted -> opened.

    Mutation: delete the mark_opened call in open_client_link -- red.
    """
    c, store = client

    resp = _mint(c)
    jti = resp.json()["jti"]
    token = resp.json()["url"].split("#t=", 1)[1]
    assert store.db.docs[("links", jti)]["status"] == "minted"

    assert _open(c, token).status_code == 200

    assert store.db.docs[("links", jti)]["status"] == "opened"
    assert store.db.docs[("links", jti)]["opened_at"] > 0


def test_a_FAILED_mirror_write_does_not_refuse_the_client(client, monkeypatch):
    """The mirror is advisory and must stay that way. A Firestore hiccup on a
    cosmetic status field must never turn a successful client open into "this
    link is not valid" -- and (A5) must never cause a refund of a link
    someone is filling, which is why the refund transaction reads the
    redemption doc rather than this field.

    The failure is injected at the WRITE, not at links_store._collection:
    patching the shared collection helper would also break the mint-record
    GATE's read, and the 404 that produced would be the gate failing closed
    (correct) rather than the mirror leaking (the bug being pinned). Drive
    the real mark_opened and make only its update() raise.

    Mutation: drop mark_opened's try/except so the exception propagates --
    red.
    """
    c, store = client
    token = _mint(c).json()["url"].split("#t=", 1)[1]

    def _boom(*a, **kw):
        raise RuntimeError("firestore hiccup")

    jti = [k[1] for k in store.db.docs if k[0] == "links"][0]
    monkeypatch.setattr(
        type(store.db.collection("links").document(jti)), "update", _boom)

    assert _open(c, token).status_code == 200
    # ... and the mirror genuinely did not stick, so the test is not passing
    # because the write silently succeeded.
    assert store.db.docs[("links", jti)]["status"] == "minted"


def test_a_REOPEN_does_not_overwrite_a_later_status(client):
    """The mirror only ever moves minted -> opened. Re-stamping on every
    reconnect would walk a completed (or revoked) record backwards to opened
    -- and the console would then show a finished link as in progress, or a
    revoked one as live.

    Mutation: drop the status == STATUS_MINTED guard in mark_opened -- red.
    """
    c, store = client

    resp = _mint(c)
    jti = resp.json()["jti"]
    token = resp.json()["url"].split("#t=", 1)[1]
    assert _open(c, token).status_code == 200
    store.db.docs[("links", jti)]["status"] = "completed"

    assert _open(c, token).status_code == 200

    assert store.db.docs[("links", jti)]["status"] == "completed"


def test_the_open_gate_reads_THIS_CHANNELS_collection(client, monkeypatch):
    """The mint-record gate must look in links[_<channel>], not a fixed
    links. A demo backend reading the staging collection would refuse every
    real demo link (an outage) -- and a staging backend reading links would
    ADMIT a demo-minted link whose credit belongs to a paying firm.

    Asserted on the CHANNEL ARGUMENT the gate passes, because get_link's own
    default resolves to the same value: a mutation that dropped the explicit
    channel= would still pass a value-only assertion, and this is the pin
    that survives it.

    Mutation: pass a literal "demo" (or drop the argument and hard-code the
    default) in _require_mint_record's get_link call -- red.
    """
    seen = []
    real_get_link = links_store.get_link

    def _spy(jti, channel=None):
        seen.append(channel)
        return real_get_link(jti, channel=channel)

    c, _store = client
    monkeypatch.setenv("LINK_CHANNEL", "staging")
    token = _mint(c).json()["url"].split("#t=", 1)[1]
    monkeypatch.setattr(links_store, "get_link", _spy)

    _open(c, token)

    assert seen == ["staging"], (
        "the open gate did not read the running channel's mint-record "
        "collection: {}".format(seen)
    )
