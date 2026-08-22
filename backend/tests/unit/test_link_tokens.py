"""Client magic-link tokens (bd polyglot-pdf-ugm6).

The client's ONLY entry path, so the failure modes here are the product's:
a forgeable token is unauthorized access to a firm's form, and a leaked
client identifier collapses the split-key arrangement the whole design
exists to provide.

ASCII only.
"""
import time

import pytest

from backend.services.link_tokens import (
    DEFAULT_COMPLETE_WINDOW_S,
    DEFAULT_OPEN_WINDOW_S,
    LinkTokenError,
    TOKEN_VERSION,
    completion_deadline,
    mint_link_token,
    verify_link_token,
)

_SECRET = "k" * 40


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("LINK_TOKEN_SECRET", _SECRET)


def _mint(**kw):
    kw.setdefault("firm_id", "firm-a")
    kw.setdefault("kit_id", "i-90")
    kw.setdefault("employee_id", "emp-1")
    return mint_link_token(**kw)


# --- the invariant this whole design exists for -----------------------------


def test_the_token_carries_NO_client_identifier(monkeypatch):
    """THE SPLIT-KEY INVARIANT (maintainer, 2026-08-19). We hold a
    pseudonymous record; the FIRM holds identity. Neither side alone can
    connect a record to a person, so re-identification requires the firm to
    act -- which puts the disclosure decision on the party with the
    attorney-client relationship.

    Adding a client identifier here is not a feature, it is a change to the
    product's legal posture. This test is the tripwire: it asserts the
    COMPLETE key set, so a new field cannot be added without a reviewer
    seeing this docstring.

    Mutation: add "client_email" to the payload -- red.
    """
    token, _jti = _mint()
    payload = verify_link_token(token)

    assert set(payload) == {
        "v", "firm_id", "kit_id", "employee_id", "jti", "iat", "exp", "cw",
    }, "the token's field set changed -- see the split-key invariant above"

    # employee_id names OUR CUSTOMER'S STAFF, not the form's subject. That is
    # the maintainer's telemetry requirement and does not touch the invariant.
    assert payload["employee_id"] == "emp-1"


def test_the_jti_is_unguessable_and_unique():
    """The jti is the FIRM'S JOIN KEY -- what they record against a client's
    case and what our session records carry. A predictable one would let an
    outsider correlate links to sessions, defeating the split.

    Mutation: derive the jti from a counter or a timestamp -- red.
    """
    jtis = {_mint()[1] for _ in range(50)}

    assert len(jtis) == 50, "jti must be unique per mint"
    for jti in jtis:
        assert len(jti) >= 20, "jti must carry real entropy"


# --- forgery -----------------------------------------------------------------


def test_a_tampered_payload_is_refused():
    """The signature covers the payload, so editing ANY field invalidates it.
    Pinned per-field: a token whose kit_id or firm_id can be swapped is
    unauthorized access to another form or another firm's form.

    Mutation: verify the signature over a subset of fields -- red.
    """
    import base64
    import json

    token, _ = _mint()
    payload_b64, sig = token.split(".")
    payload = json.loads(base64.urlsafe_b64decode(
        payload_b64 + "=" * (-len(payload_b64) % 4)))

    for field, evil in (("kit_id", "n-400"), ("firm_id", "firm-b"),
                        ("employee_id", "emp-99"), ("exp", 99999999999)):
        forged = dict(payload)
        forged[field] = evil
        forged_b64 = base64.urlsafe_b64encode(
            json.dumps(forged, sort_keys=True, separators=(",", ":")).encode()
        ).decode().rstrip("=")
        with pytest.raises(LinkTokenError):
            verify_link_token(forged_b64 + "." + sig)


def test_a_token_signed_with_a_DIFFERENT_secret_is_refused(monkeypatch):
    """Someone who does not hold our signing key cannot mint links.
    Mutation: compare signatures with == on a truncated digest -- still red,
    because this is about the KEY, not the comparison."""
    token, _ = _mint()

    monkeypatch.setenv("LINK_TOKEN_SECRET", "z" * 40)
    with pytest.raises(LinkTokenError):
        verify_link_token(token)


@pytest.mark.parametrize(
    "bad",
    ["", "nodot", "a.b.c", ".", "x.", ".y", "not base64.at all!!"],
    ids=["empty", "no-dot", "jwt-shaped", "bare-dot", "no-sig", "no-payload",
         "garbage"],
)
def test_malformed_tokens_are_refused_not_crashed(bad):
    """A client-supplied string reaches this function, so every shape must
    produce a clean refusal rather than an unhandled exception (which would
    be a 500 and a stack trace instead of a 404)."""
    with pytest.raises(LinkTokenError):
        verify_link_token(bad)


def test_a_missing_or_short_secret_refuses_rather_than_defaulting(monkeypatch):
    """FAIL CLOSED. A default key would be forgeable by anyone reading the
    source; a per-process random one would silently kill every outstanding
    link on each restart. Refusing is the honest failure.

    Mutation: fall back to a hardcoded default -- red.
    """
    token, _ = _mint()
    for value in ("", "tooshort"):
        monkeypatch.setenv("LINK_TOKEN_SECRET", value)
        with pytest.raises(LinkTokenError):
            verify_link_token(token)
        with pytest.raises(LinkTokenError):
            _mint()


# --- the time windows --------------------------------------------------------


def test_a_link_expires_after_its_OPEN_window():
    """~48h to open from issuance (maintainer default). Mutation: compare
    with > instead of >= at the boundary, or drop the check -- red."""
    now = 1_000_000
    token, _ = _mint(now=now)

    assert verify_link_token(token, now=now + DEFAULT_OPEN_WINDOW_S - 1)
    with pytest.raises(LinkTokenError):
        verify_link_token(token, now=now + DEFAULT_OPEN_WINDOW_S)


def test_the_COMPLETION_clock_starts_at_OPEN_not_at_mint():
    """A client who opens their link 47 hours in still gets the full
    completion window -- otherwise the two windows silently compound and a
    link that is technically still valid is unusable.

    Mutation: return iat + cw instead of opened_at + cw -- red.
    """
    minted_at = 1_000_000
    token, _ = _mint(now=minted_at)
    payload = verify_link_token(token, now=minted_at + 1)

    opened_at = minted_at + DEFAULT_OPEN_WINDOW_S - 3600  # opened late
    assert completion_deadline(payload, opened_at) == (
        opened_at + DEFAULT_COMPLETE_WINDOW_S
    )


def test_the_windows_are_overridable_per_mint():
    """A firm with a slower intake process must not be forced to re-issue."""
    now = 500_000
    token, _ = _mint(now=now, open_window_s=60, complete_window_s=120)
    payload = verify_link_token(token, now=now + 30)

    assert payload["exp"] == now + 60
    assert payload["cw"] == 120


# --- format / version --------------------------------------------------------


def test_an_unknown_token_version_is_refused():
    """An old link must fail closed rather than be reinterpreted under new
    rules. Mutation: ignore the version field -- red."""
    import base64
    import json

    token, _ = _mint()
    payload_b64, _sig = token.split(".")
    payload = json.loads(base64.urlsafe_b64decode(
        payload_b64 + "=" * (-len(payload_b64) % 4)))
    payload["v"] = TOKEN_VERSION + 1

    # Re-sign it, so this tests the VERSION check and not the signature.
    from backend.services.link_tokens import _b64u, _sign
    reissued = _b64u(json.dumps(payload, sort_keys=True,
                                separators=(",", ":")).encode())
    with pytest.raises(LinkTokenError):
        verify_link_token(reissued + "." + _sign(reissued))


def test_a_link_token_is_STRUCTURALLY_DISTINCT_from_a_firebase_jwt():
    """THE CREDENTIAL BOUNDARY (checked against epic polyglot-pdf-ijntk).

    Three credential systems exist -- firm staff (Firebase ID tokens), the
    schema editor (its own per-user identity), and client links (this one).
    They must never merge. A Firebase JWT has THREE dot-separated segments;
    a link token has TWO. That difference is what stops either verifier
    silently accepting the other's token if a future change routes a token
    to the wrong place.

    Mutation: give the link token a third segment -- red.
    """
    token, _ = _mint()

    assert token.count(".") == 1, (
        "a link token must not be JWT-shaped -- see the credential boundary "
        "in link_tokens.py"
    )
    # And the reverse: a JWT-shaped string is refused here.
    with pytest.raises(LinkTokenError):
        verify_link_token("header.payload.signature")


def test_required_fields_must_be_present_and_correctly_typed():
    """A JSON `true` must not pass where a timestamp is expected (bool is an
    int subclass in Python -- the classic version of this bug)."""
    import base64
    import json

    from backend.services.link_tokens import _b64u, _sign

    base, _ = _mint()
    payload_b64, _ = base.split(".")
    good = json.loads(base64.urlsafe_b64decode(
        payload_b64 + "=" * (-len(payload_b64) % 4)))

    for field, bad_value in (("firm_id", ""), ("kit_id", 5), ("jti", None),
                             ("exp", True), ("iat", "soon"), ("cw", False)):
        payload = dict(good)
        payload[field] = bad_value
        blob = _b64u(json.dumps(payload, sort_keys=True,
                                separators=(",", ":")).encode())
        with pytest.raises(LinkTokenError):
            verify_link_token(blob + "." + _sign(blob))

    for field in ("firm_id", "kit_id", "employee_id", "jti", "iat", "exp", "cw"):
        payload = {k: v for k, v in good.items() if k != field}
        blob = _b64u(json.dumps(payload, sort_keys=True,
                                separators=(",", ":")).encode())
        with pytest.raises(LinkTokenError):
            verify_link_token(blob + "." + _sign(blob))


def test_mint_requires_all_three_identifiers():
    """A blank firm or kit would mint a token that names nothing."""
    for kw in ({"firm_id": ""}, {"kit_id": ""}, {"employee_id": ""},
               {"firm_id": None}):
        with pytest.raises(LinkTokenError):
            _mint(**kw)


def test_a_freshly_minted_token_verifies_against_real_time():
    """No frozen clock: the default windows must be sane against time.time(),
    not just against injected timestamps."""
    token, jti = _mint()
    payload = verify_link_token(token)

    assert payload["jti"] == jti
    assert payload["iat"] <= int(time.time()) + 1
