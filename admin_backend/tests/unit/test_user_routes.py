"""The staff-account routes, for BOTH actors (bd polyglot-pdf-dmjl5).

THE THREE EXIT CRITERIA live here:

  1. test_the_claims_written_are_exactly_the_two_writable_ones and its
     escalation siblings -- for BOTH actors, the claims a route writes are
     the account's existing claims with exactly {firm_id, firm_role}
     overlaid, and NO request can put app_admin, schema_editor_role or
     vff_dev on an account.
  2. test_a_manager_gets_their_own_firm_from_the_token / _is_refused_403_
     for_naming_a_firm / test_an_app_admin_must_name_a_firm -- the two-actor
     firm rule, over every route.
  3. test_every_mutation_writes_a_pending_row_then_closes_it -- the
     pending-then-committed audit form, driven through the real routes
     rather than asserted structurally (that half is
     test_admin_audit_coverage.py's job; this half proves the rows actually
     appear, in order, with the right states).

THE FAKE FIREBASE AUTH below is a tiny in-memory DIRECTORY, not a
call-recorder. A recorder could tell us set_custom_user_claims was called; it
could not answer "what claims does the account HOLD afterwards", which is the
only form of criterion 1 worth pinning -- an allowlist bug is exactly a
difference between what was called and what ended up stored.

ASCII only.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from admin_backend.main import app
from admin_backend.services import audit_log, user_admin
from admin_backend.services.admin_auth import (
    ACTOR_KIND_APP_ADMIN,
    ACTOR_KIND_FIRM_MANAGER,
    CompositeActor,
    require_app_admin_or_owning_manager,
)


# --------------------------------------------------------------------------
# A minimal Firestore stand-in (audit rows only -- these routes make no other
# Firestore write). Same shape as test_config_routes.py's, minus the
# transaction machinery these routes cannot use.
# --------------------------------------------------------------------------

class _Timeline(list):
    """ONE ordered log of every side effect, Firestore AND Firebase Auth.

    THE FIRESTORE WRITES ALONE CANNOT PIN THE ORDER criterion 3 is about.
    "Pending BEFORE the action" is a claim about where the Auth call sits
    relative to the audit rows, and a log containing only Firestore writes
    would show the pending row first no matter where the Auth call moved --
    a vacuous assertion, demonstrated by mutation. So both fakes append
    here, and the ordering test reads this list.
    """


class _DocRef:
    def __init__(self, store, collection, doc_id):
        self._store = store
        self.collection_id = collection
        self.id = doc_id

    @property
    def _path(self):
        return (self.collection_id, self.id)

    def set(self, data, merge=False):
        self._store.docs[self._path] = dict(data)
        self._store.timeline.append(("audit-set", data.get("state")))

    def update(self, data):
        existing = self._store.docs.setdefault(self._path, {})
        existing.update(data)
        self._store.timeline.append(("audit-update", data.get("state")))


class _Collection:
    def __init__(self, store, name):
        self._store = store
        self._name = name

    def document(self, doc_id=None):
        if doc_id is None:
            self._store.auto_id_counter += 1
            doc_id = "auto{}".format(self._store.auto_id_counter)
        return _DocRef(self._store, self._name, doc_id)


class _FakeDb:
    def __init__(self, timeline=None):
        self.docs = {}
        self.auto_id_counter = 0
        self.timeline = timeline if timeline is not None else _Timeline()

    def collection(self, name):
        return _Collection(self, name)

    def audit_rows(self):
        return [v for (coll, _), v in self.docs.items()
                if coll == audit_log.COLLECTION]


# --------------------------------------------------------------------------
# A minimal Firebase Auth directory.
# --------------------------------------------------------------------------

class _EmailAlreadyExistsError(Exception):
    pass


class _UserNotFoundError(Exception):
    pass


class _UserRecord:
    def __init__(self, uid, email, custom_claims=None, disabled=False,
                 display_name=None):
        self.uid = uid
        self.email = email
        self.custom_claims = custom_claims
        self.disabled = disabled
        self.display_name = display_name


class _Page:
    def __init__(self, users):
        self.users = users

    def get_next_page(self):
        return None


class _FakeAuth:
    """An in-memory Firebase Auth admin surface.

    Stores what was WRITTEN, so a test can read back the claims an account
    actually holds -- which is what an allowlist assertion needs.
    """

    EmailAlreadyExistsError = _EmailAlreadyExistsError
    UserNotFoundError = _UserNotFoundError

    def __init__(self, timeline=None):
        self.timeline = timeline if timeline is not None else _Timeline()
        self.users = {}
        self.next_uid = 0
        self.create_error = None
        self.claims_error = None
        self.update_error = None
        self.reset_link_error = None
        self.reset_links = []
        # Every password create_user was called with, so a test can prove
        # none of them reaches the response.
        self.passwords_used = []

    # --- the SDK surface user_admin.py calls ---------------------------
    def create_user(self, *, email, email_verified=False, password=None,
                    display_name=None, disabled=False):
        self.timeline.append(("auth-create", email))
        if self.create_error is not None:
            raise self.create_error
        if any(u.email == email for u in self.users.values()):
            raise _EmailAlreadyExistsError("EMAIL_EXISTS")
        self.next_uid += 1
        uid = "uid-{}".format(self.next_uid)
        self.passwords_used.append(password)
        rec = _UserRecord(uid, email, None, disabled, display_name)
        self.users[uid] = rec
        return rec

    def get_user(self, uid):
        if uid not in self.users:
            raise _UserNotFoundError("USER_NOT_FOUND")
        return self.users[uid]

    def set_custom_user_claims(self, uid, claims):
        self.timeline.append(("auth-claims", uid))
        if self.claims_error is not None:
            raise self.claims_error
        self.users[uid].custom_claims = dict(claims)

    def update_user(self, uid, *, disabled=None):
        self.timeline.append(("auth-update", uid))
        if self.update_error is not None:
            raise self.update_error
        if uid not in self.users:
            raise _UserNotFoundError("USER_NOT_FOUND")
        if disabled is not None:
            self.users[uid].disabled = disabled
        return self.users[uid]

    def generate_password_reset_link(self, email):
        if self.reset_link_error is not None:
            raise self.reset_link_error
        link = "https://example.test/reset?e={}".format(email)
        self.reset_links.append(link)
        return link

    def list_users(self):
        return _Page(list(self.users.values()))


@pytest.fixture
def timeline():
    """The ONE ordered side-effect log both fakes append to."""
    return _Timeline()


@pytest.fixture
def fake_auth(monkeypatch, timeline):
    auth = _FakeAuth(timeline)
    monkeypatch.setattr(user_admin, "_fb_auth", lambda: auth)
    return auth


@pytest.fixture
def fake_db(monkeypatch, timeline):
    db = _FakeDb(timeline)
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)
    return db


ADMIN_ACTOR = CompositeActor(uid="admin-1", email="ops@example.com",
                             kind=ACTOR_KIND_APP_ADMIN)
MANAGER_ACTOR = CompositeActor(uid="mgr-1", email="ada@acme.example",
                               kind=ACTOR_KIND_FIRM_MANAGER, firm_id="acme")


def _client(actor):
    app.dependency_overrides[require_app_admin_or_owning_manager] = \
        lambda: actor
    return TestClient(app)


@pytest.fixture
def admin_client():
    """Overriding the DEPENDENCY, not faking a token: the gate itself is
    pinned in test_admin_auth.py, and re-proving it here would couple these
    tests to token plumbing they are not about."""
    with _client(ADMIN_ACTOR) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def manager_client():
    with _client(MANAGER_ACTOR) as c:
        yield c
    app.dependency_overrides.clear()


# ==========================================================================
# EXIT CRITERION 1 -- the claims allowlist, for BOTH actors
# ==========================================================================

# Pre-existing claims that MUST survive a write, one per privileged claim the
# console must never be able to grant, plus an unrelated one. Parametrized so
# a mutation that drops the merge reddens each claim's own case rather than
# one lumped assertion (mutation-verify per parametrization).
_SURVIVING_CLAIMS = [
    ({"app_admin": True}, "app_admin"),
    ({"schema_editor_role": "editor"}, "schema_editor_role"),
    ({"vff_dev": True}, "vff_dev"),
    ({"some_future_claim": "x"}, "some_future_claim"),
]


@pytest.mark.parametrize("actor_name", ["admin", "manager"])
def test_the_claims_written_are_exactly_the_two_writable_ones(
        fake_auth, fake_db, actor_name):
    """EXIT CRITERION 1, both actors: a CREATE stamps exactly
    {firm_id, firm_role} and nothing else.

    Mutation: add any third key to merge_firm_claims' overlay -- red."""
    actor = ADMIN_ACTOR if actor_name == "admin" else MANAGER_ACTOR
    body = {"email": "new@acme.example", "firm_role": "employee"}
    if actor_name == "admin":
        body["firm_id"] = "acme"
    with _client(actor) as client:
        resp = client.post("/admin/users", json=body)
    app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    uid = resp.json()["uid"]
    assert fake_auth.users[uid].custom_claims == {
        "firm_id": "acme", "firm_role": "employee"}


@pytest.mark.parametrize("existing,claim_name", _SURVIVING_CLAIMS,
                         ids=[c for _, c in _SURVIVING_CLAIMS])
@pytest.mark.parametrize("actor_name", ["admin", "manager"])
def test_a_role_change_preserves_every_other_claim(
        fake_auth, fake_db, existing, claim_name, actor_name):
    """MERGE, NEVER REPLACE. set_custom_user_claims REPLACES the whole claims
    object, so a role change that did not merge would silently strip a
    manager's vff_dev claim and lock them out of the voice app.

    Mutation: return only the overlay from merge_firm_claims (drop the
    `**base` spread) -- every parametrization red."""
    actor = ADMIN_ACTOR if actor_name == "admin" else MANAGER_ACTOR
    claims = {"firm_id": "acme", "firm_role": "employee", **existing}
    fake_auth.users["u9"] = _UserRecord("u9", "bo@acme.example", claims)

    body = {"firm_role": "manager"}
    if actor_name == "admin":
        body["firm_id"] = "acme"
    with _client(actor) as client:
        resp = client.patch("/admin/users/u9/role", json=body)
    app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    after = fake_auth.users["u9"].custom_claims
    assert after[claim_name] == existing[claim_name], (
        "{} was destroyed by a role change".format(claim_name))
    assert after["firm_role"] == "manager"


@pytest.mark.parametrize("forbidden", sorted(user_admin.FORBIDDEN_CLAIMS))
@pytest.mark.parametrize("actor_name", ["admin", "manager"])
def test_no_request_can_grant_a_privileged_claim(
        fake_auth, fake_db, forbidden, actor_name):
    """EXIT CRITERION 1's escalation half, BY NAME, both actors.

    Sends the forbidden claim through every field a request has -- the
    top-level body, the role field, and the firm_id field -- and asserts the
    account never ends up holding it. This is the attack the allowlist
    exists to stop: a console (or a compromised one) minting its own admins.

    Mutation: have create_user pass the request body through to
    set_custom_user_claims -- red for every claim."""
    actor = ADMIN_ACTOR if actor_name == "admin" else MANAGER_ACTOR
    body = {
        "email": "evil@acme.example",
        "firm_role": "employee",
        forbidden: True,
        "custom_claims": {forbidden: True},
        "claims": {forbidden: True},
    }
    if actor_name == "admin":
        body["firm_id"] = "acme"
    with _client(actor) as client:
        resp = client.post("/admin/users", json=body)
    app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    stored = fake_auth.users[resp.json()["uid"]].custom_claims
    assert forbidden not in stored
    assert set(stored) == set(user_admin.WRITABLE_CLAIMS)


def test_the_forbidden_set_and_the_writable_set_are_disjoint():
    """The two constants are the whole allowlist story; if they ever
    overlapped, the escalation test above would pass while the escalation
    succeeded."""
    assert not (user_admin.WRITABLE_CLAIMS & user_admin.FORBIDDEN_CLAIMS)
    assert user_admin.WRITABLE_CLAIMS == {"firm_id", "firm_role"}
    assert user_admin.FORBIDDEN_CLAIMS == {
        "app_admin", "schema_editor_role", "vff_dev"}


def test_merge_firm_claims_writes_only_allowlisted_keys_from_this_call():
    """The helper's own property, stated as the invariant rather than as an
    example: every key whose value CHANGED is in WRITABLE_CLAIMS."""
    existing = {"app_admin": True, "vff_dev": True, "firm_id": "old",
                "firm_role": "employee", "unrelated": 3}
    after = user_admin.merge_firm_claims(
        existing, firm_id="new", firm_role="manager")
    changed = {k for k in set(existing) | set(after)
               if existing.get(k) != after.get(k)}
    assert changed <= user_admin.WRITABLE_CLAIMS
    assert set(existing) <= set(after), "no pre-existing claim was dropped"


def test_the_generated_password_never_reaches_the_response(
        fake_auth, fake_db, admin_client):
    """A password in a console response is a credential in a browser tab, a
    log, and a screenshot. The reset link is the only credential path."""
    resp = admin_client.post("/admin/users", json={
        "email": "new@acme.example", "firm_role": "employee",
        "firm_id": "acme"})
    assert resp.status_code == 200
    assert fake_auth.passwords_used, "create_user was called with no password"
    body = resp.text
    for password in fake_auth.passwords_used:
        assert password not in body
    assert "password" not in resp.json()


def test_create_returns_a_reset_link_and_no_email_is_sent(
        fake_auth, fake_db, admin_client):
    """NO OUTBOUND EMAIL in this epic (planner decision): the console
    displays the link and the operator delivers it."""
    resp = admin_client.post("/admin/users", json={
        "email": "new@acme.example", "firm_role": "employee",
        "firm_id": "acme"})
    assert resp.status_code == 200
    assert resp.json()["reset_link"] == fake_auth.reset_links[0]


def test_a_failed_reset_link_still_leaves_the_account_created(
        fake_auth, fake_db, admin_client):
    """Best-effort by design: the account and its claims are already
    correct, and reporting a failure would invite a retry that refuses on
    the duplicate email."""
    fake_auth.reset_link_error = RuntimeError("quota")
    resp = admin_client.post("/admin/users", json={
        "email": "new@acme.example", "firm_role": "employee",
        "firm_id": "acme"})
    assert resp.status_code == 200
    assert resp.json()["reset_link"] is None
    assert fake_auth.users[resp.json()["uid"]].custom_claims["firm_id"] == \
        "acme"


# ==========================================================================
# EXIT CRITERION 2 -- the two-actor firm rule, over EVERY route
# ==========================================================================

# Every route, with a request that is valid apart from the firm question.
# Enumerated so the firm rule is pinned on the WHOLE set rather than on the
# create route with the rest assumed (CLAUDE.md scar #8).
_ROUTES = [
    ("POST", "/admin/users",
     {"email": "x@acme.example", "firm_role": "employee"}, "create"),
    ("PATCH", "/admin/users/u9/disable", {"disabled": True}, "disable"),
    ("PATCH", "/admin/users/u9/role", {"firm_role": "manager"}, "role"),
    ("GET", "/admin/users", None, "list"),
]


def _send(client, method, path, body, firm_id=None):
    """One request, with firm_id placed where THAT route carries it -- the
    body for the writes, the query string for the read."""
    if method == "GET":
        params = {"firm_id": firm_id} if firm_id is not None else None
        return client.get(path, params=params)
    payload = dict(body or {})
    if firm_id is not None:
        payload["firm_id"] = firm_id
    return client.request(method, path, json=payload)


@pytest.mark.parametrize("method,path,body,name", _ROUTES,
                         ids=[r[3] for r in _ROUTES])
def test_a_manager_gets_their_own_firm_from_the_token(
        fake_auth, fake_db, method, path, body, name):
    """EXIT CRITERION 2, first half: a manager names no firm and the route
    acts on the firm in their TOKEN.

    Mutation: read the firm from the body first and fall back to the token
    -- these still pass (no firm is sent), which is why the refusal test
    below is the other half of this criterion and not optional."""
    fake_auth.users["u9"] = _UserRecord(
        "u9", "bo@acme.example", {"firm_id": "acme", "firm_role": "employee"})
    with _client(MANAGER_ACTOR) as client:
        resp = _send(client, method, path, body)
    app.dependency_overrides.clear()
    assert resp.status_code == 200, resp.text
    assert resp.json()["firm_id"] == "acme"


@pytest.mark.parametrize("named_firm", ["other-firm", "acme"],
                         ids=["another-firm", "their-OWN-firm"])
@pytest.mark.parametrize("method,path,body,name", _ROUTES,
                         ids=[r[3] for r in _ROUTES])
def test_a_manager_naming_any_firm_is_refused_403(
        fake_auth, fake_db, method, path, body, name, named_firm):
    """EXIT CRITERION 2, the refusal -- and note the SECOND parametrization:
    naming their OWN firm is refused too.

    "The same value" is not the test; "did you try to choose" is. Accepting
    a matching value would make the refusal depend on what the caller
    happened to send, and the next console version that sent it on every
    request would silently stop being refused -- at which point a bug that
    sent the wrong firm would be a cross-firm write.

    Mutation: in resolve_target_firm, refuse only when body_firm_id !=
    actor.firm_id -- the their-OWN-firm half goes red."""
    fake_auth.users["u9"] = _UserRecord(
        "u9", "bo@acme.example", {"firm_id": "acme", "firm_role": "employee"})
    with _client(MANAGER_ACTOR) as client:
        resp = _send(client, method, path, body, firm_id=named_firm)
    app.dependency_overrides.clear()
    assert resp.status_code == 403, resp.text


@pytest.mark.parametrize("method,path,body,name", _ROUTES,
                         ids=[r[3] for r in _ROUTES])
def test_an_app_admin_must_name_a_firm(
        fake_auth, fake_db, method, path, body, name):
    """EXIT CRITERION 2, second half: 422 when an admin omits the firm.
    There is no firm to fall back to, and defaulting to any particular one
    would be a guess with a write behind it.

    Mutation: return "" or a default firm instead of raising 422 -- red."""
    with _client(ADMIN_ACTOR) as client:
        resp = _send(client, method, path, body)
    app.dependency_overrides.clear()
    assert resp.status_code == 422, resp.text


@pytest.mark.parametrize("method,path,body,name", _ROUTES,
                         ids=[r[3] for r in _ROUTES])
def test_an_app_admin_acts_on_the_firm_they_named(
        fake_auth, fake_db, method, path, body, name):
    fake_auth.users["u9"] = _UserRecord(
        "u9", "bo@other.example",
        {"firm_id": "other-firm", "firm_role": "employee"})
    with _client(ADMIN_ACTOR) as client:
        resp = _send(client, method, path, body, firm_id="other-firm")
    app.dependency_overrides.clear()
    assert resp.status_code == 200, resp.text
    assert resp.json()["firm_id"] == "other-firm"


@pytest.mark.parametrize("uid_route", ["disable", "role"])
def test_a_manager_cannot_touch_an_account_in_another_firm(
        fake_auth, fake_db, uid_route):
    """A uid is a bearer of nothing. Without the scoping check a manager
    could disable any account in the project by pasting its uid.

    404 and not 403, deliberately: a 403 would confirm that a guessed uid
    names a real account.

    Mutation: delete the firm_id comparison in _require_account_in_firm --
    both parametrizations go red."""
    fake_auth.users["u-other"] = _UserRecord(
        "u-other", "x@other.example",
        {"firm_id": "other-firm", "firm_role": "employee"})
    path = "/admin/users/u-other/{}".format(uid_route)
    body = {"disabled": True} if uid_route == "disable" else \
        {"firm_role": "manager"}
    with _client(MANAGER_ACTOR) as client:
        resp = client.patch(path, json=body)
    app.dependency_overrides.clear()
    assert resp.status_code == 404, resp.text
    assert fake_auth.users["u-other"].custom_claims["firm_role"] == "employee"
    assert fake_auth.users["u-other"].disabled is False


@pytest.mark.parametrize("uid_route", ["disable", "role"])
def test_an_unknown_uid_is_INDISTINGUISHABLE_from_another_firms_account(
        fake_auth, fake_db, uid_route):
    """The other direction of the same leak: both refusals must be the same
    404 with the same body, or the difference IS the existence oracle."""
    fake_auth.users["u-other"] = _UserRecord(
        "u-other", "x@other.example",
        {"firm_id": "other-firm", "firm_role": "employee"})
    body = {"disabled": True} if uid_route == "disable" else \
        {"firm_role": "manager"}
    with _client(MANAGER_ACTOR) as client:
        wrong_firm = client.patch(
            "/admin/users/u-other/{}".format(uid_route), json=body)
        nonexistent = client.patch(
            "/admin/users/u-does-not-exist/{}".format(uid_route), json=body)
    app.dependency_overrides.clear()
    assert wrong_firm.status_code == nonexistent.status_code == 404
    assert wrong_firm.json() == nonexistent.json()


def test_the_list_shows_only_the_resolved_firms_staff(
        fake_auth, fake_db, manager_client):
    """The client-side claims filter, and the response allowlist."""
    fake_auth.users["u1"] = _UserRecord(
        "u1", "a@acme.example", {"firm_id": "acme", "firm_role": "manager"})
    fake_auth.users["u2"] = _UserRecord(
        "u2", "b@other.example",
        {"firm_id": "other-firm", "firm_role": "manager"})
    fake_auth.users["u3"] = _UserRecord("u3", "editor@x.example",
                                        {"schema_editor_role": "editor"})
    resp = manager_client.get("/admin/users")
    assert resp.status_code == 200
    assert [u["uid"] for u in resp.json()["users"]] == ["u1"]


def test_the_list_response_is_an_explicit_key_allowlist(
        fake_auth, fake_db, manager_client):
    """A future internal claim must not reach the console the day it
    appears. The shape is a decision, so it is asserted.

    Mutation: spread the claims dict into the row -- red."""
    fake_auth.users["u1"] = _UserRecord(
        "u1", "a@acme.example",
        {"firm_id": "acme", "firm_role": "manager",
         "secret_internal_flag": "leaked", "app_admin": True})
    resp = manager_client.get("/admin/users")
    row = resp.json()["users"][0]
    assert set(row) == {"uid", "email", "display_name", "disabled",
                        "firm_id", "firm_role", "schema_editor_role",
                        "vff_dev"}
    assert "secret_internal_flag" not in row
    assert "app_admin" not in row


@pytest.mark.parametrize("bad_role", ["admin", "owner", "MANAGER", "",
                                      "manager ", "app_admin"])
def test_an_unknown_firm_role_is_refused_422(
        fake_auth, fake_db, admin_client, bad_role):
    """The role is a closed vocabulary. An unrecognized value stamped into a
    claim would authorize nothing and de-authorize everything, silently.

    Mutation: drop the membership check in _validated_role -- red for every
    value."""
    resp = admin_client.post("/admin/users", json={
        "email": "x@acme.example", "firm_role": bad_role,
        "firm_id": "acme"})
    assert resp.status_code == 422
    assert not fake_auth.users


@pytest.mark.parametrize("bad_firm", ["Acme", "acme/../other", "acme\n",
                                      "a" * 200, "-acme", ""])
def test_an_invalid_firm_slug_is_refused_422(
        fake_auth, fake_db, admin_client, bad_firm):
    """Only an APP ADMIN can reach this: a manager's firm_id came from a
    verified token and was never caller text. `acme\\n` is the trailing-
    newline case a $-anchored .match would let through (bd
    polyglot-pdf-sbfk)."""
    resp = admin_client.post("/admin/users", json={
        "email": "x@acme.example", "firm_role": "employee",
        "firm_id": bad_firm})
    assert resp.status_code == 422
    assert not fake_auth.users


def test_a_duplicate_email_is_409_and_creates_nothing(
        fake_auth, fake_db, admin_client):
    fake_auth.users["u1"] = _UserRecord("u1", "taken@acme.example", None)
    resp = admin_client.post("/admin/users", json={
        "email": "taken@acme.example", "firm_role": "employee",
        "firm_id": "acme"})
    assert resp.status_code == 409
    assert len(fake_auth.users) == 1


# ==========================================================================
# EXIT CRITERION 3 -- the pending-then-committed audit form, driven live
# ==========================================================================

_MUTATIONS = [
    ("POST", "/admin/users",
     {"email": "n@acme.example", "firm_role": "employee", "firm_id": "acme"},
     "user.create"),
    ("PATCH", "/admin/users/u9/disable", {"disabled": True, "firm_id": "acme"},
     "user.disable"),
    ("PATCH", "/admin/users/u9/role",
     {"firm_role": "manager", "firm_id": "acme"}, "user.role"),
]


@pytest.mark.parametrize("method,path,body,action", _MUTATIONS,
                         ids=[m[3] for m in _MUTATIONS])
def test_every_mutation_writes_a_pending_row_then_closes_it(
        fake_auth, fake_db, timeline, admin_client, method, path, body,
        action):
    """EXIT CRITERION 3, driven through the real route.

    Asserts the ORDER, not just the end state: the pending SET lands before
    the Auth call, and the committed UPDATE after. An end-state-only
    assertion would pass a route that wrote both rows after the fact, which
    is exactly the retry ambiguity the form exists to close.

    Mutation: move record_pending after the to_thread call -- red (the
    order flips); delete mark_committed -- red (state stays pending)."""
    fake_auth.users["u9"] = _UserRecord(
        "u9", "bo@acme.example", {"firm_id": "acme", "firm_role": "employee"})
    resp = admin_client.request(method, path, json=body)
    assert resp.status_code == 200, resp.text

    rows = fake_db.audit_rows()
    assert len(rows) == 1, "exactly one audit row per mutation"
    row = rows[0]
    assert row["action"] == action
    assert row["state"] == audit_log.STATE_COMMITTED
    assert row["actor_uid"] == ADMIN_ACTOR.uid
    assert row["request_id"] == resp.json()["request_id"]

    # The ORDER, across BOTH systems. The pending row must precede every
    # Firebase Auth mutation, and the close-out must follow them all.
    kinds = [k for k, _ in timeline]
    assert kinds[0] == "audit-set", (
        "the pending row must be written BEFORE the Auth call; timeline "
        "was {}".format(kinds))
    assert timeline[0][1] == audit_log.STATE_PENDING
    assert kinds[-1] == "audit-update", (
        "the row must be closed out AFTER the Auth call; timeline was "
        "{}".format(kinds))
    assert any(k.startswith("auth-") for k in kinds), (
        "no Auth call happened at all -- the ordering claim would be "
        "vacuous")


@pytest.mark.parametrize("method,path,body,action", _MUTATIONS,
                         ids=[m[3] for m in _MUTATIONS])
def test_a_failed_auth_call_leaves_the_row_marked_failed(
        fake_auth, fake_db, admin_client, method, path, body, action):
    """The other terminal state. A failure that left the row at pending
    would be indistinguishable from a crash mid-action, and an operator
    would have to check Firebase by hand before every retry.

    Mutation: delete mark_failed from the except branch -- red."""
    fake_auth.users["u9"] = _UserRecord(
        "u9", "bo@acme.example", {"firm_id": "acme", "firm_role": "employee"})
    # Every route's own Auth call fails: create for the create route, the
    # claims stamp for the role route, update_user for disable. One flag
    # would leave whichever route it did not cover asserting nothing.
    fake_auth.create_error = RuntimeError("boom")
    fake_auth.claims_error = RuntimeError("boom")
    fake_auth.update_error = RuntimeError("boom")

    resp = admin_client.request(method, path, json=body)
    assert resp.status_code == 502, resp.text
    rows = fake_db.audit_rows()
    assert len(rows) == 1
    assert rows[0]["state"] == audit_log.STATE_FAILED
    assert rows[0]["error"]


def test_a_read_writes_no_audit_row(fake_auth, fake_db, manager_client):
    """The log records MUTATIONS. A row per list would bury them."""
    fake_auth.users["u1"] = _UserRecord(
        "u1", "a@acme.example", {"firm_id": "acme", "firm_role": "manager"})
    assert manager_client.get("/admin/users").status_code == 200
    assert fake_db.audit_rows() == []


def test_the_audit_row_carries_no_reset_link_or_password(
        fake_auth, fake_db, admin_client):
    """An audit row is read in a console table and exported to BigQuery. A
    credential-bearing URL must not be in either."""
    resp = admin_client.post("/admin/users", json={
        "email": "n@acme.example", "firm_role": "employee",
        "firm_id": "acme"})
    assert resp.status_code == 200
    blob = repr(fake_db.audit_rows())
    assert "reset?e=" not in blob
    for password in fake_auth.passwords_used:
        assert password not in blob


# ==========================================================================
# The gate, on the routes themselves
# ==========================================================================

@pytest.mark.parametrize("method,path,body,name", _ROUTES,
                         ids=[r[3] for r in _ROUTES])
def test_every_user_route_carries_the_composite_gate_specifically(
        method, path, body, name):
    """test_admin_route_auth.py proves each route carries ONE of the four
    gates; this pins WHICH one for these four. Mutation: swap in
    require_app_admin -- red (and the manager tests above go 403)."""
    template = path.replace("/u9", "/{uid}")
    route = next(r for r in app.routes
                 if getattr(r, "path", None) == template
                 and method in (getattr(r, "methods", None) or set()))
    names = {sub.call.__name__ for sub in route.dependant.dependencies
             if getattr(sub.call, "__name__", None)}
    assert "require_app_admin_or_owning_manager" in names


# ==========================================================================
# The staff-pool walk itself (list_firm_users)
# ==========================================================================

class _MultiPage:
    """A pager that hands back a chain of pages, like the real SDK.

    list_users() returns ONE page and the walk follows get_next_page(). A
    single-page fake would leave the loop's continuation untested, which is
    the half that decides whether a firm's second page of staff is visible
    at all.
    """

    def __init__(self, pages):
        self._pages = list(pages)

    @property
    def users(self):
        return self._pages[0]

    def get_next_page(self):
        rest = self._pages[1:]
        return _MultiPage(rest) if rest else None


def _rec(uid, firm_id):
    return _UserRecord(uid, "{}@x.example".format(uid), {"firm_id": firm_id})


def test_the_walk_follows_every_page(fake_auth, monkeypatch):
    """Mutation: return after the first page (drop the get_next_page loop)
    -- red, and a firm whose staff spill onto page two silently lose half
    their list."""
    pages = [[_rec("u1", "acme"), _rec("u2", "other")],
             [_rec("u3", "acme")],
             [_rec("u4", "acme"), _rec("u5", "other")]]
    monkeypatch.setattr(fake_auth, "list_users",
                        lambda: _MultiPage(pages), raising=False)
    result = user_admin.list_firm_users("acme")
    assert [u["uid"] for u in result["users"]] == ["u1", "u3", "u4"]
    assert result["truncated"] is False


def test_the_walk_is_BOUNDED_and_says_when_it_stopped_early(
        fake_auth, monkeypatch):
    """max_results bounds accounts EXAMINED, not accounts returned, so a
    pathological pool cannot hang a console request. It must report the
    truncation: a silently short list is a firm that looks like it has
    fewer staff than it has.

    Mutation: return the rows without the truncated flag, or never set it
    -- red."""
    pages = [[_rec("u{}".format(i), "acme") for i in range(4)],
             [_rec("u9", "acme")]]
    monkeypatch.setattr(fake_auth, "list_users",
                        lambda: _MultiPage(pages), raising=False)

    bounded = user_admin.list_firm_users("acme", max_results=3)
    assert bounded["truncated"] is True
    assert len(bounded["users"]) == 3

    whole = user_admin.list_firm_users("acme")
    assert whole["truncated"] is False
    assert len(whole["users"]) == 5


def test_a_directory_failure_raises_rather_than_returning_an_empty_firm(
        fake_auth, monkeypatch):
    """FAIL LOUD here, unlike the firms store's fail-CLOSED reads. An empty
    list would read to an operator as "this firm has no staff", which is a
    different and actionable fact; the route turns this into a 502."""
    def _boom():
        raise RuntimeError("directory down")

    monkeypatch.setattr(fake_auth, "list_users", _boom, raising=False)
    with pytest.raises(user_admin.UserAdminError):
        user_admin.list_firm_users("acme")


def test_a_directory_failure_surfaces_as_502_not_an_empty_list(
        fake_auth, fake_db, manager_client, monkeypatch):
    def _boom():
        raise RuntimeError("directory down")

    monkeypatch.setattr(fake_auth, "list_users", _boom, raising=False)
    resp = manager_client.get("/admin/users")
    assert resp.status_code == 502
