"""The voice socket accepts a CLIENT LINK token (bd polyglot-pdf-ugm6).

Without this, the client tier is unreachable: /ws/fill required a Firebase ID
token, and a firm's client has no account and must never have one. The link
token -- which WE signed -- carries firm_id, kit_id, employee_id and jti, so
a client session satisfies the telemetry requirement (firm + form +
originating employee) with no account anywhere.

ASCII only.
"""
import pytest

from backend.routes.websocket_routes import _verify_ws_credential
from backend.services.link_tokens import LinkTokenError, mint_link_token

_SECRET = "w" * 40


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("LINK_TOKEN_SECRET", _SECRET)


def test_a_client_link_token_resolves_to_firm_form_and_employee(monkeypatch):
    """THE TELEMETRY REQUIREMENT, end to end: 'every session logged by the
    backend should include the firm id, the form id, and the id of the
    originating employee' (maintainer, 2026-08-14). For a CLIENT session all
    three come from the link, because there is no account to read them from.

    Mutation: drop employee_id from the returned claims -- red.
    """
    token, jti = mint_link_token("firm-a", "i-90", "u-emp-7")

    claims = _verify_ws_credential(token)

    assert claims["firm_id"] == "firm-a"
    assert claims["link_kit_id"] == "i-90"
    assert claims["employee_id"] == "u-emp-7"
    assert claims["jti"] == jti
    assert claims["is_client_link"] is True
    # A client has NO account, and nothing here may imply one.
    assert claims["uid"] is None


def test_a_STAFF_firebase_token_still_takes_the_firebase_path(monkeypatch):
    """The staff path must be untouched. Dispatch is on SHAPE (a JWT has two
    dots), so a staff token can never be parsed as a link.

    Mutation: route everything to verify_link_token -- red.
    """
    called = {}

    def _fake_verify(tok):
        called["token"] = tok
        return {"uid": "u-staff", "firm_id": "firm-a", "firm_role": "manager"}

    monkeypatch.setattr("backend.routes.websocket_routes.verify_token",
                        _fake_verify)

    claims = _verify_ws_credential("header.payload.signature")

    assert called["token"] == "header.payload.signature"
    assert claims["uid"] == "u-staff"
    assert "is_client_link" not in claims


def test_a_FORGED_link_token_is_refused(monkeypatch):
    """A one-dot string is dispatched to the link verifier, which checks the
    signature. It must NOT fall through to Firebase (where it would fail
    anyway) or be admitted.

    Mutation: return the payload without verifying -- red.
    """
    token, _ = mint_link_token("firm-a", "i-90", "u-emp-7")
    forged = token[:-4] + "AAAA"

    with pytest.raises(LinkTokenError):
        _verify_ws_credential(forged)


def test_an_EXPIRED_link_is_refused_at_the_socket(monkeypatch):
    """The open endpoint checks the window, but the socket must check too:
    an attacker with a stale token could otherwise skip /open entirely and
    connect straight to the paid session.

    Mutation: skip verify_link_token's expiry check -- red.
    """
    import time

    long_ago = int(time.time()) - 10_000
    token, _ = mint_link_token("firm-a", "i-90", "u-emp-7",
                               open_window_s=60, now=long_ago)

    with pytest.raises(LinkTokenError):
        _verify_ws_credential(token)


def test_a_staff_token_shape_is_never_parsed_as_a_link(monkeypatch):
    """The credential boundary, from the other side. Even if a Firebase JWT
    somehow carried link-looking content, its THREE segments send it to the
    Firebase verifier -- the two systems cannot merge by accident."""
    seen = {}

    def _fake_verify(tok):
        seen["called"] = True
        return {"uid": "u-staff"}

    monkeypatch.setattr("backend.routes.websocket_routes.verify_token",
                        _fake_verify)

    _verify_ws_credential("a.b.c")

    assert seen.get("called") is True


@pytest.mark.parametrize("bad", ["", "nodots", "a.b.c.d", None, 12345])
def test_malformed_credentials_do_not_crash_the_dispatcher(bad, monkeypatch):
    """Whatever arrives on the query string reaches this function. A
    non-string or odd shape must raise cleanly (the caller closes 1008), not
    blow up with a TypeError before the socket is closed properly."""
    monkeypatch.setattr("backend.routes.websocket_routes.verify_token",
                        lambda tok: (_ for _ in ()).throw(ValueError("bad")))

    with pytest.raises(Exception):
        _verify_ws_credential(bad)
