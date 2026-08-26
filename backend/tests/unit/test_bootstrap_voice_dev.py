"""The voice-dev enrolment tool -- the ONLY way out of a voice lockout.

bd polyglot-pdf-hn0jq made firm_id-or-dev REQUIRED to reach the voice app. An
earlier round of this same bead shipped that gate with its enrolment path as a
function nothing could call: a lockout whose only documented remedy was
unreachable. The tool exists now; these pin that it keeps working.

Round 4 and round 5 both asked why this file did not exist. It does now.
"""

import sys
import types

import pytest

sys.path.insert(0, __import__("os").path.dirname(
    __import__("os").path.dirname(__import__("os").path.dirname(
        __import__("os").path.dirname(__import__("os").path.abspath(__file__))))))

import scripts.bootstrap_voice_dev as boot  # noqa: E402
from backend.services.auth import VOICE_DEV_CLAIM  # noqa: E402

pytestmark = pytest.mark.real_editor_auth


class _User:
    def __init__(self, uid="uid-josh", claims=None):
        self.uid = uid
        self.custom_claims = claims


def _fake_fb(monkeypatch, user=None, stamped=None, revoked=None, users=None):
    """Stand in for firebase_admin, recording what the tool asked it to do."""
    stamped = {} if stamped is None else stamped
    revoked = [] if revoked is None else revoked

    class _Auth:
        UserNotFoundError = KeyError

        @staticmethod
        def get_user_by_email(_e):
            if user is None:
                raise _Auth.UserNotFoundError(_e)
            return user

        @staticmethod
        def set_custom_user_claims(uid, claims):
            stamped[uid] = claims

        @staticmethod
        def revoke_refresh_tokens(uid):
            revoked.append(uid)

        @staticmethod
        def list_users():
            class _Page:
                def __init__(self, us):
                    self.users = us

                def get_next_page(self):
                    return None

            return _Page(users or [])

    mod = types.ModuleType("firebase_admin")
    mod.auth = _Auth
    mod._apps = {"[DEFAULT]": object()}
    mod.initialize_app = lambda *a, **k: None
    monkeypatch.setitem(sys.modules, "firebase_admin", mod)
    return stamped, revoked


def test_granting_dev_access_PRESERVES_every_other_claim(monkeypatch):
    """set_custom_user_claims REPLACES rather than merges.

    A maintainer account plausibly carries a firm_id (they are also a firm
    user) or an editor role. Stamping the dev claim without spreading the
    existing ones would silently strip them -- the same hazard the firm and
    editor tools both carry a warning about.
    """
    existing = {"firm_id": "acme", "schema_editor_role": "author"}
    stamped, _ = _fake_fb(monkeypatch, _User(claims=existing))

    status, uid = boot.stamp_dev_claim("josh@example.com")

    assert status == "stamped"
    assert stamped[uid] == {**existing, VOICE_DEV_CLAIM: True}, (
        "granting dev access destroyed an unrelated claim")


def test_revoking_dev_access_LEAVES_every_other_claim(monkeypatch):
    """The mirror: revocation must remove the key, not blank the object."""
    existing = {"firm_id": "acme", "schema_editor_role": "author",
                VOICE_DEV_CLAIM: True}
    stamped, revoked = _fake_fb(monkeypatch, _User(claims=dict(existing)))

    status, uid = boot.revoke_dev_claim("josh@example.com")

    assert status == "revoked"
    assert stamped[uid] == {"firm_id": "acme", "schema_editor_role": "author"}
    assert VOICE_DEV_CLAIM not in stamped[uid]
    assert revoked == [uid], (
        "revoking dev access left the live session running -- it survives "
        "until the token expires, up to an hour")


def test_revoking_someone_who_is_not_a_dev_changes_nothing(monkeypatch):
    stamped, revoked = _fake_fb(monkeypatch, _User(claims={"firm_id": "acme"}))

    status, _ = boot.revoke_dev_claim("someone@example.com")

    assert status == "not_a_dev"
    assert stamped == {}, "a no-op revoke rewrote the claims"
    assert revoked == []


def test_an_unknown_email_is_reported_not_crashed(monkeypatch):
    """The operator mistypes an address; they need to be told, not traced."""
    _fake_fb(monkeypatch, user=None)

    assert boot.stamp_dev_claim("nobody@example.com")[0] == "unknown_email"
    assert boot.revoke_dev_claim("nobody@example.com")[0] == "unknown_email"


def test_listing_shows_only_accounts_carrying_the_dev_claim(monkeypatch):
    us = [
        _User("uid-josh", {VOICE_DEV_CLAIM: True}),
        _User("uid-firm", {"firm_id": "acme"}),
        _User("uid-editor", {"schema_editor_role": "editor"}),
    ]
    for u, email in zip(us, ["josh@x.com", "firm@x.com", "editor@x.com"]):
        u.email = email
    _fake_fb(monkeypatch, users=us)

    rows = boot.list_dev_users()

    assert rows == ["josh@x.com"], (
        "the listing showed accounts that do not carry the dev claim: "
        "{}".format(rows))


def test_the_dev_claim_is_the_one_the_VOICE_GATE_actually_reads(monkeypatch):
    """Producer and consumer must name the same key.

    The tool and the gate are in different files; if they drift, enrolment
    silently stops working and the only remedy for a lockout is the thing
    that is broken.
    """
    import backend.services.auth as va

    existing = {}
    stamped, _ = _fake_fb(monkeypatch, _User(claims=existing))
    _, uid = boot.stamp_dev_claim("josh@example.com")

    granted = stamped[uid]

    monkeypatch.setenv("VFF_DISABLE_AUTH", "false")

    class _Auth:
        @staticmethod
        def verify_id_token(_tok, **_kw):
            return {"uid": uid, "email": "josh@example.com", **granted}

    monkeypatch.setattr(va, "auth", _Auth)

    assert va.verify_token("josh-token")["uid"] == uid, (
        "an account the enrolment tool just stamped was refused by the gate")


def test_the_handshake_does_NOT_ask_firebase_to_check_revocation():
    """Pinned as an ABSENCE, which is the opposite of what this test used to say.

    check_revoked forces a Firebase USER-RECORD FETCH, needing
    firebaseauth.users.get. polyglot-backend-sa does not have it -- its roles
    are aiplatform.user, datastore.user, logging.logWriter,
    secretmanager.secretAccessor, storage.objectViewer -- so passing the flag
    made EVERY deployed handshake fail with INSUFFICIENT_PERMISSION. The app
    could not connect at all; the maintainer hit it on the live demo.

    WHY NO TEST CAUGHT IT, and why this one is a source assertion rather than a
    behavioural one: VFF_DISABLE_AUTH returns before the call locally, and
    every test stubs the Firebase SDK. The failure exists ONLY against real
    Firebase with the real service account, so no amount of mocking reaches it.
    Pinning the call SHAPE is the only thing that fails in CI rather than in
    production.

    THE ACCEPTED COST: revoking an account takes effect when its token expires
    (up to an hour), not immediately. Chosen over granting the deployed backend
    permission to read any user record (maintainer, 2026-08-26). The revoke
    tools still call revoke_refresh_tokens, so a revoked user cannot MINT a new
    token -- they keep the one they hold until it expires.
    """
    import pathlib as _p

    root = _p.Path(__file__).resolve().parents[3]
    for rel in ("backend/routes/websocket_routes.py",
                "backend/services/editor_auth.py"):
        src = (root / rel).read_text(encoding="utf-8")
        assert "check_revoked=True" not in src, (
            "{} passes check_revoked=True again. That needs "
            "firebaseauth.users.get, which the deployed service account does "
            "not have -- every handshake will fail with INSUFFICIENT_PERMISSION "
            "and the app will not connect. Grant the IAM role first, or leave "
            "it off.".format(rel))


def test_the_per_request_hot_path_does_NOT_pay_for_revocation(monkeypatch):
    """The performance half of the same decision, pinned so it is not undone.

    require_auth guards TTS spellback, which fires mid-conversation. Turning
    check_revoked on by default here would add a Firebase round trip to every
    utterance.
    """
    import backend.services.auth as va
    import inspect

    sig = inspect.signature(va.verify_token)
    assert sig.parameters["check_revoked"].default is False, (
        "verify_token now checks revocation by DEFAULT, which puts a Firebase "
        "round trip on the per-utterance hot path")

    # The sibling parameter, pinned the same way and for a sharper reason: a
    # one-character flip to False un-gates /api/fill-pdf, /ws/fill, both TTS
    # routes, the archive reads and the firm retire write ALL AT ONCE. Two
    # behavioural tests happen to cover it; this pins it directly, because the
    # blast radius of getting it wrong is every gated route in the app.
    assert sig.parameters["require_enrolment"].default is True, (
        "verify_token no longer requires enrolment by DEFAULT -- every route "
        "using require_auth is now open to any signed-in account")


def test_a_locked_out_user_is_TOLD_they_are_not_enrolled(monkeypatch):
    """A lockout you cannot diagnose is worse than the lockout.

    This diff introduced the enrolment requirement, so a maintainer with no
    firm_id is now refused. If /ws/fill reports that as "Authentication
    failed", it is indistinguishable from a bad token -- they will go hunting
    for a credentials problem that does not exist, and nothing points them at
    bootstrap_voice_dev.py, which is the remedy.
    """
    import asyncio

    import backend.routes.websocket_routes as ws
    from fastapi import HTTPException

    closed = {}

    class _WS:
        async def close(self, code=None, reason=None):
            closed["code"] = code
            closed["reason"] = reason

        async def accept(self):
            raise AssertionError("must not accept an unenrolled connection")

    def _refuse(_tok, check_revoked=False):
        raise HTTPException(status_code=403,
                            detail="This account is not enrolled for the "
                                   "voice application")

    monkeypatch.setattr(ws, "verify_token", _refuse)

    asyncio.run(ws.fill_form_from_schema(_WS(), service=None, token="tok"))

    assert closed.get("code") == 1008
    assert "not enrolled" in (closed.get("reason") or "").lower(), (
        "a locked-out user was told {!r} -- indistinguishable from a bad "
        "token".format(closed.get("reason")))


# --- the invariant: an app you can reach is an app you can USE --------------
#
# bd polyglot-pdf-hn0jq gated six form-kit routes on voice enrolment, which
# meant a signed-in user with no firm got 403 on /api/form-kits: an app with
# no form to pick and no way out, since the only remedy the UI can offer is
# "sign in again" and signing in was never the problem. Found by the
# maintainer on the live app, not by nine rounds of review.
#
# Maintainer, 2026-08-25: "anyone using the app must have access to at least
# one form kit."


def test_a_signed_in_user_with_NO_claims_can_still_browse_forms(monkeypatch):
    """Selecting a form is not the privileged act; filling one is."""
    import backend.services.auth as va

    monkeypatch.setenv("VFF_DISABLE_AUTH", "false")

    class _Auth:
        @staticmethod
        def verify_id_token(_tok, **_kw):
            # A real, verified account -- no firm, no dev claim. The shape a
            # magic-link user arrives with.
            return {"uid": "uid-newcomer", "email": "someone@example.com"}

    monkeypatch.setattr(va, "auth", _Auth)

    claims = va.verify_token("a-token", require_enrolment=False)

    assert claims["uid"] == "uid-newcomer", (
        "a signed-in user was refused the form catalogue -- the app is "
        "unusable for them, with nothing to select")


def test_that_same_user_is_STILL_refused_when_acting_on_a_form(monkeypatch):
    """The other half. Browsing opens; filling stays gated.

    If this ever passes, the enrolment gate has been removed rather than
    narrowed, and the two-allowlist decision is undone.
    """
    import backend.services.auth as va
    from fastapi import HTTPException

    monkeypatch.setenv("VFF_DISABLE_AUTH", "false")

    class _Auth:
        @staticmethod
        def verify_id_token(_tok, **_kw):
            return {"uid": "uid-newcomer", "email": "someone@example.com"}

    monkeypatch.setattr(va, "auth", _Auth)

    with pytest.raises(HTTPException) as exc:
        va.verify_token("a-token")  # default: enrolment REQUIRED
    assert exc.value.status_code == 403


def test_the_catalogue_routes_do_not_require_enrolment():
    """Pin WHICH routes browse vs act, derived from the source.

    A future route added to the catalogue with require_auth reintroduces the
    lockout silently -- the app simply shows no forms, which reads as a data
    problem rather than an auth one.
    """
    import ast
    import pathlib as _p

    src = (_p.Path(__file__).resolve().parents[3]
           / "backend" / "routes" / "form_kit_routes.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    # SELECTING a form: these must never demand enrolment.
    browse = {"list_form_kits", "get_form_kit_schema"}
    seen = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        deps = [n.id for n in ast.walk(node)
                if isinstance(n, ast.Name) and n.id.startswith("require_")]
        if node.name in browse:
            seen[node.name] = deps

    assert set(seen) == browse, "a catalogue route was renamed or removed: {}".format(
        sorted(seen))
    for name, deps in seen.items():
        assert "require_signin" in deps, (
            "{} no longer uses require_signin -- a signed-in user with no firm "
            "cannot select a form, and the app is unusable for them".format(name))
        assert "require_auth" not in deps, (
            "{} demands enrolment again".format(name))

