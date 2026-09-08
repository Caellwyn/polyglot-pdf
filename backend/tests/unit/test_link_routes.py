"""Client magic-link routes: mint + open (bd polyglot-pdf-ugm6).

`/open` is the only UNAUTHENTICATED endpoint that starts a paid session, so
its refusal behavior is the security surface: every rejection must be
indistinguishable, or the endpoint becomes an oracle for probing which links
and firms exist.

ASCII only.
"""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import backend.routes.link_routes as lr
from backend.services.link_redemptions import (
    LinkAlreadyUsed,
    RedemptionUnavailable,
)

_SECRET = "s" * 40

_TOKENS = {
    "emp-a": {"uid": "u-emp-a", "firm_id": "firm-a", "firm_role": "employee"},
    "mgr-a": {"uid": "u-mgr-a", "firm_id": "firm-a", "firm_role": "manager"},
    "emp-b": {"uid": "u-emp-b", "firm_id": "firm-b", "firm_role": "employee"},
    "nofirm": {"uid": "u-solo"},
    "nouid": {"firm_id": "firm-a", "firm_role": "employee"},
}

_ALLOWED = {"firm-a": ["firm-a-intake"], "firm-b": ["firm-b-intake"]}


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


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LINK_TOKEN_SECRET", _SECRET)
    monkeypatch.setenv("LINK_BASE_URL", "https://forms.example.com")
    monkeypatch.setenv("VFF_DISABLE_AUTH", "false")
    # LINK_MINTING_ENABLED moved off os.getenv to runtime_config (bd
    # polyglot-pdf-bg313): patch the resolver these tests actually exercise
    # rather than an env var the route no longer reads.
    monkeypatch.setattr(lr, "_rc_minting_enabled", lambda: True)

    def _verify(token):
        claims = _TOKENS.get(token)
        if claims is None:
            raise HTTPException(status_code=401, detail="bad token")
        return dict(claims)

    monkeypatch.setattr("backend.services.auth.verify_token", _verify)
    monkeypatch.setattr(lr, "get_allowed_kits",
                        lambda firm_id: list(_ALLOWED.get(firm_id, [])))
    store = _Redemptions()
    # /open now goes through enforce_link_redemption, which calls open_link
    # inside link_redemptions -- patch it THERE so these tests exercise the
    # REAL gate (completion-window check included) rather than standing in
    # for the whole thing.
    monkeypatch.setattr("backend.services.link_redemptions.open_link",
                        store.open_link)

    app = FastAPI()
    app.include_router(lr.router)
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
