"""Per-user identity for the schema editor (bd polyglot-pdf-hn0jq).

Drives the three epic criteria this child is on the hook for:

  1. Two DIFFERENT editor users are distinguishable by the server -- a mutating
     action records WHICH one acted.
  2. Revoking one user's access does not disturb any other user, with no
     shared-secret rotation.
  4. An editor account grants no voice-app access and a voice-app account grants
     no editor access.

The point of the change: the editor authenticated with two shared secrets, so
every editor was one principal to the server. "An editor did it" was the most an
audit could ever say, two subcontractors could not be told apart, and removing
one person meant rotating the token for everyone.
"""
import sys
import types

import pytest
from fastapi import HTTPException

# This module tests the VERIFIER itself, so it opts out of the shared
# conftest shim that answers for it (bd polyglot-pdf-hn0jq).
pytestmark = pytest.mark.real_editor_auth

import backend.services.editor_auth as ea
from backend.services.editor_auth import (
    EDITOR_ROLE_CLAIM,
    NO_EDITOR_ACCESS_PREFIX,
    EditorActor,
    require_author_actor,
    require_editor_actor,
    verify_editor_token,
)


def _fake_firebase(monkeypatch, claims=None, raises=None, already_inited=True):
    """Stand in for firebase_admin.auth with a fixed decoded token.

    RECORDS what it was asked, because two guards on this path are otherwise
    invisible to a test: check_revoked (without which revoking a user is a
    no-op for up to an hour) and the self-init (without which the module works
    only when the voice app happens to have initialised Firebase first). Both
    survived a mutation with the whole suite green until the double recorded
    them -- pass `already_inited=False` to exercise the init branch.
    """
    calls = {"check_revoked": None, "initialize_app": 0}

    class _Auth:
        @staticmethod
        def verify_id_token(_tok, check_revoked=False):
            calls["check_revoked"] = check_revoked
            if raises is not None:
                raise raises
            return claims

    mod = types.ModuleType("firebase_admin")
    mod.auth = _Auth
    mod._apps = {"[DEFAULT]": object()} if already_inited else {}

    def _init(*_a, **_k):
        calls["initialize_app"] += 1
        mod._apps["[DEFAULT]"] = object()

    mod.initialize_app = _init
    monkeypatch.setitem(sys.modules, "firebase_admin", mod)
    monkeypatch.setattr(ea, "_dev_bypass_allowed", lambda: False)
    return calls


def _run(coro):
    import asyncio

    return asyncio.run(coro)


# --- criterion 1: two editors are distinguishable ---------------------------


def test_two_editors_resolve_to_DIFFERENT_people(monkeypatch):
    """The whole point. Under shared tokens both callers were byte-identical to
    the server; there was no field that could have differed."""
    _fake_firebase(monkeypatch, {"uid": "uid-maria",
                                 "email": "maria@example.com",
                                 EDITOR_ROLE_CLAIM: "editor"})
    maria = verify_editor_token("t")

    _fake_firebase(monkeypatch, {"uid": "uid-sam",
                                 "email": "sam@example.com",
                                 EDITOR_ROLE_CLAIM: "editor"})
    sam = verify_editor_token("t")

    assert maria.uid != sam.uid, "two editors must not be the same principal"
    assert maria.email != sam.email
    assert maria.role == sam.role == "editor", "...while sharing a ROLE"


def test_an_actor_names_a_person_for_attribution(monkeypatch):
    """label() is what a log line or a lock display shows. It must never be
    empty -- a lock that displays nothing is worse than one showing an opaque
    id -- so it falls back to the uid when the account has no email."""
    with_email = EditorActor(uid="u1", email="maria@example.com", role="editor")
    assert with_email.label() == "maria@example.com"

    no_email = EditorActor(uid="u2", role="editor")
    assert no_email.label() == "u2", "must fall back rather than render blank"


# --- criterion 2: revoking one person does not touch anyone else ------------


def test_revoking_one_user_leaves_another_working(monkeypatch):
    """No shared secret to rotate: one account losing its claim says nothing
    about any other account."""
    revoked = {"uid": "uid-maria", "email": "maria@example.com"}  # claim removed
    _fake_firebase(monkeypatch, revoked)
    with pytest.raises(HTTPException) as exc:
        verify_editor_token("marias-token")
    assert exc.value.status_code == 403

    still_listed = {"uid": "uid-sam", "email": "sam@example.com",
                    EDITOR_ROLE_CLAIM: "editor"}
    _fake_firebase(monkeypatch, still_listed)
    assert verify_editor_token("sams-token").uid == "uid-sam"


def test_revoke_removes_only_the_editor_claim(monkeypatch):
    """The bootstrap script's revoke must not destroy unrelated claims.

    set_custom_user_claims REPLACES the whole object rather than merging, so a
    careless revoke would silently strip a person's firm access too -- the same
    hazard bootstrap_firm.py calls out and pins.
    """
    import scripts.bootstrap_editor_user as boot

    stamped = {}

    class _User:
        uid = "uid-maria"
        custom_claims = {"firm_id": "acme", "firm_role": "manager",
                         EDITOR_ROLE_CLAIM: "editor"}

    revoked_sessions = []

    class _Auth:
        UserNotFoundError = KeyError

        @staticmethod
        def get_user_by_email(_e):
            return _User()

        @staticmethod
        def set_custom_user_claims(uid, claims):
            stamped[uid] = claims

        @staticmethod
        def revoke_refresh_tokens(uid):
            revoked_sessions.append(uid)

    mod = types.ModuleType("firebase_admin")
    mod.auth = _Auth
    monkeypatch.setitem(sys.modules, "firebase_admin", mod)

    status, _ = boot.revoke_editor_role("maria@example.com")

    assert status == "revoked"
    # Dropping the claim alone leaves an already-signed-in user working for up
    # to an hour, because claims only reach a newly minted token. The shared
    # secret this replaces revoked INSTANTLY on rotation, so without this the
    # change regresses the property it exists to improve.
    assert revoked_sessions == ["uid-maria"], (
        "revoke did not kill the live session -- access persists until the "
        "token expires")
    left = stamped["uid-maria"]
    assert EDITOR_ROLE_CLAIM not in left, "editor access must be gone"
    assert left["firm_id"] == "acme", "unrelated claims must SURVIVE"
    assert left["firm_role"] == "manager"


def test_granting_preserves_existing_claims(monkeypatch):
    """The mirror hazard on the grant side."""
    import scripts.bootstrap_editor_user as boot

    stamped = {}

    class _User:
        uid = "uid-sam"
        custom_claims = {"firm_id": "acme"}

    class _Auth:
        UserNotFoundError = KeyError

        @staticmethod
        def get_user_by_email(_e):
            return _User()

        @staticmethod
        def set_custom_user_claims(uid, claims):
            stamped[uid] = claims

    mod = types.ModuleType("firebase_admin")
    mod.auth = _Auth
    monkeypatch.setitem(sys.modules, "firebase_admin", mod)

    status, _ = boot.stamp_editor_role("sam@example.com", "editor")

    assert status == "stamped"
    assert stamped["uid-sam"][EDITOR_ROLE_CLAIM] == "editor"
    assert stamped["uid-sam"]["firm_id"] == "acme", "firm claim must SURVIVE"


# --- criterion 4: no cross-grant between the editor and the voice app -------


def test_a_voice_app_account_gets_no_editor_access(monkeypatch):
    """The separation constraint, in one assertion.

    A fully valid voice-app account -- real uid, real email, real firm claims --
    is refused by the editor because it carries no EDITOR_ROLE_CLAIM. 403 not
    401: they authenticated fine, they are simply not listed here.
    """
    _fake_firebase(monkeypatch, {"uid": "uid-voice", "email": "v@example.com",
                                 "firm_id": "acme", "firm_role": "manager"})
    with pytest.raises(HTTPException) as exc:
        verify_editor_token("a-real-voice-app-token")
    assert exc.value.status_code == 403


def test_the_editor_claim_is_not_the_voice_apps_claim():
    """Named for THIS surface, so a firm_role can never grant editor access.

    If these two ever became the same string, granting someone firm access would
    silently hand them the schema editor.
    """
    assert EDITOR_ROLE_CLAIM == "schema_editor_role"
    assert EDITOR_ROLE_CLAIM not in ("firm_role", "firm_id", "role")


def test_editor_auth_does_not_import_the_voice_apps_auth():
    """The editor folder must stay liftable (maintainer constraint 2026-08-20:
    do not create new dependencies a separation epic would have to unravel)."""
    src = (ea.__file__)
    text = open(src, encoding="utf-8").read()
    assert "from backend.services.auth import" not in text
    assert "import backend.services.auth" not in text


# --- the gate itself --------------------------------------------------------


def test_a_missing_bearer_header_is_401(monkeypatch):
    monkeypatch.setattr(ea, "_dev_bypass_allowed", lambda: False)
    with pytest.raises(HTTPException) as exc:
        _run(require_editor_actor(authorization=None))
    assert exc.value.status_code == 401


def test_an_editor_is_refused_the_author_gate():
    with pytest.raises(HTTPException) as exc:
        _run(require_author_actor(EditorActor(uid="u", role="editor")))
    assert exc.value.status_code == 403


def test_the_TWO_KINDS_of_403_are_distinguishable_by_the_client(monkeypatch):
    """Same status code, opposite client remedies -- so the wire must say which.

    "You hold no editor role at all" must send the person to the sign-in gate's
    refused screen: nothing they do in the editor can help, an operator has to
    grant access. "You are a valid editor, but this action is author-only" must
    surface as an ordinary refusal and LEAVE THEM WORKING -- evicting an editor
    for pressing Publish is a worse bug than the one the refused screen fixed
    (bd polyglot-pdf-yswp3, cross-surface review).

    The marker is a PREFIX, not the message text, because the client has to
    branch on it: every previous attempt in this repo to key on English prose
    has been defeated by a rewording, and here a wrong branch throws a working
    editor out of the app.
    """
    # 1. No claim at all -> marked, because it must evict.
    _fake_firebase(monkeypatch, {"uid": "uid-nobody", "email": "v@example.com"})
    with pytest.raises(HTTPException) as exc:
        verify_editor_token("voice-app-token")
    assert exc.value.status_code == 403
    assert str(exc.value.detail).startswith(NO_EDITOR_ACCESS_PREFIX), (
        "the no-editor-access 403 lost its machine-readable marker, so the "
        "editor cannot tell it from an author-only refusal and will either "
        "strand a voice-app user on a sign-in form that can never work, or "
        "evict a valid editor who pressed an author-only button."
    )

    # 2. A REAL editor refused an author action -> NOT marked.
    with pytest.raises(HTTPException) as exc:
        _run(require_author_actor(EditorActor(uid="u", role="editor")))
    assert exc.value.status_code == 403
    assert not str(exc.value.detail).startswith(NO_EDITOR_ACCESS_PREFIX), (
        "an author-only refusal is marked as no-editor-access, so a valid "
        "editor pressing an author button is thrown out of the editor."
    )


def test_an_author_passes_the_editor_gate(monkeypatch):
    """Author strictly includes editor -- the rule the shared tokens had."""
    _fake_firebase(monkeypatch, {"uid": "uid-josh", "email": "josh@example.com",
                                 EDITOR_ROLE_CLAIM: "author"})
    actor = verify_editor_token("t")
    assert actor.is_author
    assert _run(require_author_actor(actor)).uid == "uid-josh"


def test_a_verified_token_with_no_subject_is_refused(monkeypatch):
    """Every downstream use -- locking, attribution -- depends on uid being a
    real person, so an identity-less token is a failure rather than an actor
    with an invented id."""
    _fake_firebase(monkeypatch, {"email": "ghost@example.com",
                                 EDITOR_ROLE_CLAIM: "editor"})
    with pytest.raises(HTTPException) as exc:
        verify_editor_token("t")
    assert exc.value.status_code == 401


def test_an_unknown_role_value_is_refused(monkeypatch):
    """A claim carrying junk must not be trusted as a role."""
    _fake_firebase(monkeypatch, {"uid": "u", EDITOR_ROLE_CLAIM: "superuser"})
    with pytest.raises(HTTPException) as exc:
        verify_editor_token("t")
    assert exc.value.status_code == 403


def test_EVERY_403_the_backend_raises_is_classified(monkeypatch):
    """The prefix is a SET property, so assert it over the set -- not samples.

    Two tests above pin the two 403s that live in editor_auth.py. The ones an
    editor actually meets in normal use are elsewhere: the per-transition gates
    in editor_kit_routes (Publish, and reopening a live form). Nothing links
    those to the constant, so a future 403 added there -- or a well-meant
    "let's make this consistent" prefixing of one -- would silently start
    evicting editors, with the suite green. That is CLAUDE.md scar #8's shape
    exactly, which is why this enumerates rather than samples.

    Reads the SOURCE because these raises are inside request handlers with
    substantial setup; the property is about which literals carry the marker,
    and that is visible statically. Derived from the shipped file, never a
    hand-listed set.
    """
    import ast
    import pathlib

    # EVERY route module serving the editor surface, not just the biggest one:
    # a 403 added to the readiness routes would otherwise land unpinned, which
    # is the same one-file-at-a-time miss this guard exists to stop.
    routes_dir = pathlib.Path(ea.__file__).resolve().parent.parent / "routes"
    modules = [routes_dir / "editor_kit_routes.py",
               routes_dir / "editor_readiness_routes.py"]
    for m in modules:
        assert m.exists(), f"{m.name} moved -- this scan is now blind to it"

    prefixed, plain = [], []
    nodes_all = []
    for m in modules:
        nodes_all.extend(ast.walk(ast.parse(m.read_text(encoding="utf-8"))))
    for node in nodes_all:
        if not isinstance(node, ast.Raise) or node.exc is None:
            continue
        call = node.exc if isinstance(node.exc, ast.Call) else None
        if call is None or getattr(call.func, "id", None) != "HTTPException":
            continue
        kw = {k.arg: k.value for k in call.keywords}
        status = kw.get("status_code")
        if not (isinstance(status, ast.Constant) and status.value == 403):
            continue
        detail = kw.get("detail", ast.Constant(""))
        nodes = list(ast.walk(detail))
        text = "".join(n.value for n in nodes
                       if isinstance(n, ast.Constant) and isinstance(n.value, str))
        # Two ways to carry the marker, and the SECOND is the one that matters:
        # the only legitimate prefixed 403 (editor_auth.py) is written as
        # `NO_EDITOR_ACCESS_PREFIX + "..."`, so that is the idiom someone would
        # copy here "for consistency". A literal-only scan cannot see it --
        # measured: prefixing the Publish 403 via the constant passed this test
        # before the Name check below was added.
        by_literal = NO_EDITOR_ACCESS_PREFIX in text
        by_constant = any(isinstance(n, ast.Name)
                          and "NO_EDITOR_ACCESS" in n.id for n in nodes)
        (prefixed if (by_literal or by_constant) else plain).append(
            (node.lineno, text[:60]))

    assert plain, (
        "no unprefixed 403 found in the editor route modules -- either they "
        "moved or this scan broke. An empty set would make this test vacuous."
    )
    assert not prefixed, (
        "a 403 in the editor route modules carries "
        + NO_EDITOR_ACCESS_PREFIX + ", "
        "which EVICTS the caller to the sign-in gate's refused screen. Only "
        "editor_auth's 'this account holds no editor role' 403 may do that. "
        "These are refusals of a specific ACTION for a valid editor, so they "
        "must stay unprefixed or an editor pressing Publish is thrown out of "
        "the editor: " + repr(prefixed)
    )


def test_the_dev_bypass_is_refused_on_a_deployed_instance(monkeypatch):
    """K_SERVICE is Cloud Run's marker. Fail-closed by construction: the bypass
    is refused when deployed however the env is set."""
    monkeypatch.setenv("VFF_DISABLE_AUTH", "true")
    monkeypatch.setenv("K_SERVICE", "editor-backend")
    assert ea._dev_bypass_allowed() is False

    monkeypatch.delenv("K_SERVICE", raising=False)
    assert ea._dev_bypass_allowed() is True


# --- criterion 1, the part that was MISSING: an action RECORDS who -----------
#
# Round 1 scored this criterion FAIL: the verifier could tell two people apart,
# but no route recorded which one acted -- every log line still said role=editor,
# byte-identical to what the shared-token code produced. Resolving identity and
# USING it are different things, and only the second is what the criterion asks
# for.


def test_a_mutating_action_records_WHICH_person_acted(tmp_path, monkeypatch):
    """The criterion, end to end through a real route.

    Two editors save the same kit; the two records must name different people.
    Under shared tokens this was impossible -- there was no field that could
    have differed.
    """
    import json

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import backend.routes.editor_kit_routes as ekr
    from backend.services.form_kits import LocalFormKitStore

    captured = []

    class _CapturingLog:
        """The module binds its logger at IMPORT time, so reconfiguring
        structlog inside the test never reaches it -- patch the bound logger."""

        def info(self, event, **kw):
            captured.append({"event": event, **kw})

        def warning(self, event, **kw):
            captured.append({"event": event, **kw})

        def error(self, event, **kw):
            captured.append({"event": event, **kw})

        def bind(self, **_kw):
            return self

    kit = tmp_path / "w7"
    kit.mkdir()
    (kit / "schema.json").write_text('{"fields": []}', encoding="utf-8")
    (kit / "metadata.json").write_text(
        json.dumps({"status": "draft", "label": "w7"}), encoding="utf-8")
    (kit / "form.pdf").write_bytes(b"%PDF-1.7")

    app = FastAPI()
    app.include_router(ekr.router)
    store = LocalFormKitStore(tmp_path)
    monkeypatch.setattr(ekr, "get_form_kit_store", lambda: store)

    async def _no_drift(_s, _k, _sc, _sf):
        return 0, None

    monkeypatch.setattr(ekr, "_sweep_drifted_translations", _no_drift)
    monkeypatch.setattr(ekr, "_log", _CapturingLog())

    people = {
        "maria-token": EditorActor(uid="uid-maria", email="maria@example.com",
                                   role="editor"),
        "sam-token": EditorActor(uid="uid-sam", email="sam@example.com",
                                 role="editor"),
    }
    monkeypatch.setattr(
        ea, "verify_editor_token",
        lambda t: people.get(t) or (_ for _ in ()).throw(
            HTTPException(status_code=401, detail="no")),
    )

    c = TestClient(app)
    for token in ("maria-token", "sam-token"):
        r = c.put("/api/editor/kits/w7/schema", json={"fields": []},
                  headers={"X-Editor-Token": token})
        assert r.status_code == 200, r.text

    saves = [e for e in captured if e.get("event") == "editor_schema_saved"]
    assert len(saves) == 2, f"expected two save records, got {len(saves)}"

    actors = [e.get("actor") for e in saves]
    assert all(actors), "a save recorded NO actor -- the criterion is unmet"
    assert actors[0] != actors[1], (
        "two different editors produced the SAME record: {}".format(actors))
    assert "maria@example.com" in actors and "sam@example.com" in actors


def test_two_editors_cannot_be_told_apart_by_role_alone(tmp_path, monkeypatch):
    """Guards the shape of the fix, not just its presence.

    Recording only the ROLE would satisfy a careless reading of "records which
    one acted" -- both editors log role=editor. The record has to carry
    something that DIFFERS between two people of the same role.
    """
    maria = EditorActor(uid="uid-maria", email="maria@example.com", role="editor")
    sam = EditorActor(uid="uid-sam", email="sam@example.com", role="editor")

    assert maria.role == sam.role, "same role -- so role cannot be the signal"
    assert maria.label() != sam.label(), "label() is what distinguishes them"


def test_EVERY_role_log_site_also_records_the_actor():
    """Enumerated, not hand-listed (repo scar: "Enumerate the block, don't hand
    list it" / "Every pattern in a list needs its OWN pinning test").

    Round 1 pinned attribution on ONE route. Round 2 then showed four more could
    have theirs stripped with 295 tests green -- and that a whole second file,
    editor_readiness_routes.py, had never been attributed at all. A single
    example test cannot see either miss.

    This derives the list from the SOURCE, so a new mutating route that logs a
    role without an actor fails here the day it is written, rather than the day
    someone audits the logs.
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[3]
    offenders = []
    for rel in ("backend/routes/editor_kit_routes.py",
                "backend/routes/editor_readiness_routes.py"):
        src = (root / rel).read_text(encoding="utf-8")
        # The comma-space is \s* because a long log call legitimately WRAPS
        # between role= and actor=; matching within one line would report a
        # false offender for pure formatting.
        for m in re.finditer(r"role=role\.role(?!,\s*actor=role\.label\(\))", src):
            line_no = src[:m.start()].count("\n") + 1
            line = src.split("\n")[line_no - 1]
            # The session RESPONSE MODEL is a wire shape, not an audit record --
            # it has no actor field and must not grow one here.
            if "EditorSessionResponse" in line:
                continue
            offenders.append(f"{rel}:{line_no}: {line.strip()[:70]}")

    assert not offenders, (
        "these record a role but not WHO acted -- criterion 1 is per-route:\n  "
        + "\n  ".join(offenders))


# --- criterion 3, the OTHER direction --------------------------------------
#
# Round 2 scored this FAIL: only voice-account-into-editor was tested, and the
# reverse did not hold in code at all -- backend/services/auth.py accepted any
# valid token, so an editor-only account reached /api/fill-pdf and /ws/fill.
#
# I escalated it as a contradiction (the criterion wants both directions; the
# constraint says do not touch voice auth). The maintainer resolved it toward
# the stronger reading: "voice app accounts should be tied to firms, or a devs.
# editor accounts are separate... Those should be 2 separate auth lists."


def test_an_editor_only_account_is_refused_by_the_VOICE_app(monkeypatch):
    """The second direction, which is the one that did not hold.

    An editor subcontractor polishes forms; they have no business filling one
    on a firm's behalf. Requiring the voice surface to check its OWN claim is
    what makes the two lists genuinely separate.
    """
    import backend.services.auth as va

    monkeypatch.setenv("VFF_DISABLE_AUTH", "false")

    class _Auth:
        @staticmethod
        def verify_id_token(_tok, **_kw):
            # A real editor account: valid, verified, and carrying the EDITOR
            # claim -- but nothing tying it to a firm or marking it a dev.
            return {"uid": "uid-maria", "email": "maria@example.com",
                    EDITOR_ROLE_CLAIM: "editor"}

    monkeypatch.setattr(va, "auth", _Auth)

    with pytest.raises(HTTPException) as exc:
        va.verify_token("an-editors-token")
    assert exc.value.status_code == 403, "an editor reached the voice app"


def test_a_firm_user_still_reaches_the_voice_app(monkeypatch):
    """The gate must not lock out the people it exists to serve."""
    import backend.services.auth as va

    monkeypatch.setenv("VFF_DISABLE_AUTH", "false")

    class _Auth:
        @staticmethod
        def verify_id_token(_tok, **_kw):
            return {"uid": "uid-firm", "email": "user@acme.com",
                    "firm_id": "acme", "firm_role": "employee"}

    monkeypatch.setattr(va, "auth", _Auth)
    assert va.verify_token("a-firm-users-token")["firm_id"] == "acme"


def test_a_dev_account_still_reaches_the_voice_app(monkeypatch):
    """The maintainer's own account, with no firm, must keep working."""
    import backend.services.auth as va

    monkeypatch.setenv("VFF_DISABLE_AUTH", "false")

    class _Auth:
        @staticmethod
        def verify_id_token(_tok, **_kw):
            return {"uid": "uid-dev", "email": "josh@example.com",
                    va.VOICE_DEV_CLAIM: True}

    monkeypatch.setattr(va, "auth", _Auth)
    assert va.verify_token("a-devs-token")["uid"] == "uid-dev"


def test_the_two_allowlists_share_no_claim():
    """Two separate lists, mechanically.

    If the editor's claim ever satisfied the voice gate (or vice versa),
    enrolling someone in one surface would silently enrol them in the other --
    which is the whole thing the maintainer asked not to happen.
    """
    import backend.services.auth as va

    assert EDITOR_ROLE_CLAIM not in ("firm_id", "firm_role", va.VOICE_DEV_CLAIM)
    assert va.VOICE_DEV_CLAIM != EDITOR_ROLE_CLAIM


# --- guards that survived a mutation until these existed --------------------
#
# Round 3 mutation-tested the round-2 fixes and found three of them unpinned:
# the code was right, but nothing would notice if it stopped being right. A
# claimed fix nothing pins is indistinguishable from no fix at all.


def test_the_verifier_does_NOT_ask_firebase_to_check_revocation(monkeypatch):
    """INVERTED 2026-08-26, and the reversal is the point.

    This used to assert check_revoked is True, on the reasoning that
    revoke_refresh_tokens is inert without it. That reasoning was sound and
    the code was still unshippable: check_revoked forces a Firebase
    USER-RECORD FETCH needing firebaseauth.users.get, and the editor API runs
    on polyglot-backend, whose service account does not have it. Deployed,
    EVERY editor sign-in failed with INSUFFICIENT_PERMISSION -- the same
    failure that took the voice app down.

    Neither this test nor any other could see it: the fake SDK below answers
    happily, and the dev bypass skips the call locally. A test that stubs the
    dependency cannot discover that the real dependency is forbidden.

    THE COST, kept explicit rather than quietly dropped: revoking an editor
    takes effect when their token expires (up to an hour), NOT immediately --
    weaker than the shared secret this epic replaced. revoke_editor_role still
    calls revoke_refresh_tokens, so a revoked user cannot MINT a new token.
    The maintainer chose this over widening the deployed backend's IAM.
    """
    calls = _fake_firebase(monkeypatch, {"uid": "uid-maria",
                                         "email": "maria@example.com",
                                         EDITOR_ROLE_CLAIM: "editor"})
    ea.verify_editor_token("a-token")

    assert calls["check_revoked"] is False, (
        "the editor verifier asks Firebase to check revocation again -- that "
        "needs firebaseauth.users.get, which the deployed service account "
        "does not have, so every sign-in will fail with INSUFFICIENT_PERMISSION")


def test_the_editor_initialises_firebase_ITSELF_when_nothing_else_has(monkeypatch):
    """The liftability claim, made real.

    editor_auth deliberately imports nothing from the voice app -- but it also
    never initialised firebase_admin, so it worked only because the voice app's
    module happened to load first. Standing it up alone made every sign-in a
    401 that blamed the user's credential.

    test_editor_auth_does_not_import_the_voice_apps_auth checks the import is
    absent; this checks the module actually WORKS without it, which is the
    property that matters.
    """
    calls = _fake_firebase(monkeypatch, {"uid": "uid-maria",
                                         "email": "maria@example.com",
                                         EDITOR_ROLE_CLAIM: "editor"},
                           already_inited=False)

    actor = ea.verify_editor_token("a-token")

    assert calls["initialize_app"] == 1, (
        "editor_auth did not initialise Firebase -- lifted out of this repo it "
        "would 401 every sign-in")
    assert actor.uid == "uid-maria"


def test_an_already_initialised_app_is_not_re_initialised(monkeypatch):
    """The other direction: initialising twice raises in the real SDK."""
    calls = _fake_firebase(monkeypatch, {"uid": "uid-maria",
                                         "email": "maria@example.com",
                                         EDITOR_ROLE_CLAIM: "editor"},
                           already_inited=True)
    ea.verify_editor_token("a-token")
    assert calls["initialize_app"] == 0


MUTATING_VERBS = ("post", "put", "delete", "patch")


def _store_writes(root):
    """Every write the store exposes, read off the store's own AST."""
    import ast

    src = (root / "backend" / "services" / "form_kits.py").read_text(
        encoding="utf-8")
    return {n.name for n in ast.walk(ast.parse(src))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name.split("_")[0] in ("put", "delete", "write", "save", "set")}


def _imported_writers(root, modules, writes):
    """Names imported from backend.* whose definitions reach a store write.

    FOLLOWS THE IMPORT to whatever module it names, rather than scanning a
    directory I chose. The first version looked only in backend/services/ --
    but these modules also import from backend.routes.*, backend.adapters.*
    and backend.utils.*, so a writer added in any of those would have been
    invisible. That is the same mistake twice: the seam was not the string
    matching, it was assuming where to look.

    Resolves the ALIAS too (`from x import y as z` records y's definition
    under the name z that the route body actually calls).
    """
    import ast

    wanted = {}
    for f in modules:
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and (n.module or "").startswith(
                    "backend."):
                for alias in n.names:
                    # local name -> (module, original name)
                    wanted[alias.asname or alias.name] = (n.module, alias.name)

    found = set()
    for local_name, (module, orig_name) in wanted.items():
        path = root.joinpath(*module.split(".")).with_suffix(".py")
        if not path.exists():
            pkg = root.joinpath(*module.split(".")) / "__init__.py"
            if not pkg.exists():
                continue
            path = pkg
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and n.name == orig_name
                    and _writes_somewhere(n, writes, frozenset())):
                found.add(local_name)
    return found


def _writes_somewhere(node, writes, helper_writers):
    """Does this function reach a store write, directly or via a helper?"""
    import ast

    for c in ast.walk(node):
        if not isinstance(c, ast.Call):
            continue
        f = c.func
        if isinstance(f, ast.Attribute) and f.attr in writes:
            return True
        if isinstance(f, ast.Name) and f.id in helper_writers:
            return True
        if isinstance(f, ast.Attribute) and f.attr in helper_writers:
            return True
    return False


def _attributes_an_actor(node, attributing_helpers=frozenset()):
    """Does this function record an actor -- directly, or via a helper?

    MUST follow helpers exactly as _writes_somewhere does. When only writes
    followed helpers, a route that delegates its whole body to a helper (POST
    /regenerate-guidance -> _regenerate_guidance_locked, which logs
    editor_guidance_regenerated WITH an actor) was flagged as unattributed --
    a false positive, which is the failure that trains an author to add a
    noise log rather than fix anything.
    """
    import ast

    for c in ast.walk(node):
        if not isinstance(c, ast.Call):
            continue
        for kw in c.keywords:
            if kw.arg == "actor":
                return True
        f = c.func
        if isinstance(f, ast.Name) and f.id in attributing_helpers:
            return True
        if isinstance(f, ast.Attribute) and f.attr in attributing_helpers:
            return True
    return False


def _route_verb(node):
    """The HTTP verb of a @router.<verb>(...) decorated function, or None."""
    import ast

    for d in node.decorator_list:
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute):
            if isinstance(d.func.value, ast.Name) and d.func.value.id == "router":
                return d.func.attr
    return None


def _route_path(node):
    import ast

    for d in node.decorator_list:
        if isinstance(d, ast.Call) and d.args:
            a = d.args[0]
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                return a.value
    return "?"


def _takes_an_actor(node):
    """Only a route that RECEIVES an actor can record one.

    Tested by ANNOTATION, not by parameter name. A two-name allowlist
    ("role"/"actor") meant a route declaring `who: Annotated[EditorActor,
    Depends(require_editor_role)]` was skipped entirely -- write or no write.
    The honest question is whether an EditorActor is injected, and the name a
    future author picks is not the guard's business.
    """
    import ast

    for arg in list(node.args.args) + list(node.args.kwonlyargs):
        ann = arg.annotation
        if ann is None:
            continue
        for n in ast.walk(ann):
            if isinstance(n, ast.Name) and n.id == "EditorActor":
                return True
            if isinstance(n, ast.Constant) and n.value == "EditorActor":
                return True
            if isinstance(n, ast.Name) and n.id in (
                    "require_editor_role", "require_author_role",
                    "require_editor_actor", "require_author_actor"):
                return True
    return False


def test_EVERY_mutating_editor_route_CONTAINS_an_attributed_log():
    """Criterion 1, enforced by PARSING rather than by matching text.

    This guard has been wrong four times, every time for the same reason: it
    read source as STRINGS. Chunk-splitting borrowed a following GET's log
    line; a hand-listed write set missed three store methods and invented two;
    comments and then docstrings promoted read-only helpers to writers; an
    unanchored pattern matched a nested closure and swallowed the enclosing
    route. Each fix was a better regex, and each left a new seam.

    The parser has no seams. ast sees the real call graph: which functions are
    routes, which reach a store write (directly or through a helper), and which
    pass actor= to a log call.

    WHAT IT STILL DOES NOT CHECK: that the write PATH reaches the log --
    containment is not reachability, and a route attributing only its refusal
    branch would satisfy this. The behavioural tests above pin that for the
    routes they drive.
    """
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[3]
    modules = sorted(
        f for f in (root / "backend" / "routes").glob("editor_*.py")
        if "require_editor" in f.read_text(encoding="utf-8"))
    assert modules, "no editor route modules found -- the derivation is broken"

    writes = _store_writes(root)
    assert writes, "no store write methods found -- the derivation is broken"

    # SEED with cross-module writers. The route modules IMPORT helpers that
    # write (_archive_published_revision lives in services/kit_gates.py and
    # calls put_archived_revision), and parsing only editor_*.py cannot see
    # them -- the module-boundary hole this guard's predecessor was written to
    # close, reopened one import further out. Derived from the services the
    # route modules actually import, never hand-listed.
    imported_writers = _imported_writers(root, modules, writes)

    trees = {f: ast.parse(f.read_text(encoding="utf-8")) for f in modules}

    # Helpers that reach a write, iterated to a fixed point so a route ->
    # _outer -> _inner -> put_metadata chain is not missed at any depth.
    helper_writers = set(imported_writers)
    while True:
        grown = set()
        for tree in trees.values():
            for node in ast.walk(tree):
                if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and node.name.startswith("_")
                        and node.name not in helper_writers
                        and _writes_somewhere(node, writes, helper_writers)):
                    grown.add(node.name)
        if not grown:
            break
        helper_writers |= grown

    # The mirror of helper_writers: helpers that RECORD an actor. Both sets are
    # needed, and for the same reason -- a route can delegate either half of
    # the job to a helper.
    attributing_helpers = set()
    while True:
        grown = set()
        for tree in trees.values():
            for node in ast.walk(tree):
                if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and node.name.startswith("_")
                        and node.name not in attributing_helpers
                        and _attributes_an_actor(node, attributing_helpers)):
                    grown.add(node.name)
        if not grown:
            break
        attributing_helpers |= grown

    unattributed = []
    for f, tree in trees.items():
        rel = f.relative_to(root).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            verb = _route_verb(node)
            if verb is None or verb.lower() not in MUTATING_VERBS:
                continue
            if not _takes_an_actor(node):
                continue
            if not _writes_somewhere(node, writes, helper_writers):
                continue
            if _attributes_an_actor(node, attributing_helpers):
                continue
            unattributed.append(
                rel + ": " + verb.upper() + " " + _route_path(node))

    assert not unattributed, (
        "these mutating routes write but record no actor, so 'who did this' "
        "is unanswerable for them:" + chr(10) + "  "
        + (chr(10) + "  ").join(sorted(unattributed)))


def test_a_malformed_token_is_401_never_a_500(monkeypatch):
    """Replaces test_non_ascii_access_code_is_401_not_500.

    LIVES HERE, not in test_editor_kit_routes.py, because that module has no
    real_editor_auth marker: the autouse conftest shim would have already
    replaced verify_editor_token, so the test would assert against the fake
    and could not fail. Measured -- it stayed green with the 401 handler
    deleted.

    That test existed because hmac.compare_digest raises TypeError on non-ASCII
    str, so a pasted smart quote turned an auth miss into a 500 (Codex P1, PR
    #279). The shared-token compare is gone, but the PROPERTY it protected is
    not: a bad credential must be a clean 401, never a crash. Firebase raises
    its own zoo of exceptions for a malformed token, so the same class of bug is
    one un-caught exception away.
    """
    import sys, types
    import backend.services.editor_auth as ea

    monkeypatch.setattr(ea, "_dev_bypass_allowed", lambda: False)

    class _Exploding:
        @staticmethod
        def verify_id_token(_tok, check_revoked=False):
            raise ValueError("malformed token: not a JWT")

    fake = types.ModuleType("firebase_admin")
    fake.auth = _Exploding
    # _apps: the verifier initialises the default app when none exists, so a
    # bare module double now trips that branch instead of reaching the auth
    # stub. (Only visible once this test moved out of the shimmed module and
    # started running against the real code it names.)
    fake._apps = {"[DEFAULT]": object()}
    fake.initialize_app = lambda *a, **k: None
    monkeypatch.setitem(sys.modules, "firebase_admin", fake)

    with pytest.raises(HTTPException) as exc:
        ea.verify_editor_token("sm\u2019art-quote-garbage")
    assert exc.value.status_code == 401, "a malformed token must 401, not 500"


def test_the_local_bypass_works_with_NO_header_at_all(monkeypatch):
    """The bypass must not be header-dependent.

    It sat behind the header check, so a header-less local request got 401
    "Sign-in required" even with the bypass on -- while the voice app checks
    its bypass first. The local editor only worked because its launcher bakes
    a token, so a curl or a probe against a bypassed backend failed
    confusingly. Now the two surfaces agree.
    """
    monkeypatch.setattr(ea, "_dev_bypass_allowed", lambda: True)

    actor = _run(ea.require_editor_actor(authorization=None, x_editor_token=None))

    assert actor.role == ea.ROLE_AUTHOR
    assert actor.label(), "the bypass actor must still name somebody"


def test_the_bypass_is_STILL_refused_on_a_deployed_instance(monkeypatch):
    """The hoist must not have widened where the bypass applies."""
    monkeypatch.setenv("VFF_DISABLE_AUTH", "true")
    monkeypatch.setenv("K_SERVICE", "editor-backend")

    assert ea._dev_bypass_allowed() is False, (
        "the dev bypass is live on a deployed instance")
