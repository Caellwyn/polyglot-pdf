"""Link listing + revoke on the admin service (bd polyglot-pdf-jmiys, Epic 2
Track B bead B4; the listing route's employee actor added by bd
polyglot-pdf-scaig).

EXIT CRITERIA THIS FILE PINS:

  1. test_link_listing_response_is_allowlisted -- the response contains
     EXACTLY the allowlisted keys even when the stored doc carries extras
     (mutation-verified: adding a stray key to either stored doc must not
     make it into the response).
  2. test_a_manager_listing_another_firms_links_is_404_not_403,
     test_an_app_admin_may_list_any_firm,
     test_a_missing_channel_is_422 / test_an_unknown_channel_is_422.
  3. test_revoke_writes_status_and_one_audit_row_atomically (the atomicity
     half, over a fake Firestore with real transaction semantics -- the
     SAME shape test_firm_routes.py and test_sweep_routes.py already use).
     The OPEN-refusal half of this criterion (a subsequent A3 open of the
     revoked jti is refused with the uniform 404) is pinned separately in
     backend/tests/integration/test_revoked_link_open.py, over the REAL
     HTTP open route, as the bead requires.

BD POLYGLOT-PDF-SCAIG ADDS (plan lines 567-569, "Tests to pin" #9):
  test_employee_link_listing_response_is_allowlisted and
  test_employee_history_scoped_to_token below -- an employee never sees
  another employee's links, and employee_id is taken from the TOKEN, never
  the query, even when the query tries to name someone else.
  test_an_employee_cannot_revoke and
  test_an_employee_listing_another_firms_links_is_404_not_403 pin the two
  edges of the new gate: the write route is untouched (an employee gets the
  SAME refusal an unauthenticated caller of that dependency would), and the
  existence-hiding 404 rule extends to the third actor kind exactly as it
  already covers a manager.

THE FAKE FIRESTORE below is the SAME shape test_sweep_routes.py's own
_FakeDb/_Transaction/_Query use (tuple-path documents, a real
all-or-nothing transaction, a `.where()`-filtered `.stream()`) -- this
route's Firestore surface is exactly links[_<channel>] +
link_redemptions[_<channel>] + admin_audit_log, the same three collections
that file's sweep route touches, so the two suites share one fake shape
rather than inventing a second.

ASCII only.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import backend.services.link_redemptions as link_redemptions
import backend.services.links_store as links_store
from admin_backend.main import app
from admin_backend.routes import link_routes
from admin_backend.services import audit_log
from admin_backend.services.admin_auth import (
    ACTOR_KIND_APP_ADMIN,
    ACTOR_KIND_FIRM_EMPLOYEE,
    ACTOR_KIND_FIRM_MANAGER,
    CompositeActor,
    require_app_admin_or_owning_manager,
    require_app_admin_or_owning_manager_or_employee,
)


# --------------------------------------------------------------------------
# The fake Firestore: identical shape to test_sweep_routes.py's _FakeDb.
# --------------------------------------------------------------------------

class _Snap:
    def __init__(self, path, data):
        self._path = path
        self._data = dict(data) if data is not None else None

    @property
    def id(self):
        return self._path[-1]

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _DocRef:
    def __init__(self, store, path):
        self._store = store
        self._path = path
        self.id = path[-1]

    def collection(self, name):
        return _Collection(self._store, self._path + (name,))

    def get(self, transaction=None):
        return _Snap(self._path, self._store.docs.get(self._path))


class _Query:
    def __init__(self, store, path, clauses=()):
        self._store = store
        self._path = path
        self._clauses = tuple(clauses)

    def where(self, *args, **kwargs):
        if "filter" in kwargs:
            ff = kwargs["filter"]
            field, op, value = ff.field_path, ff.op_string, ff.value
        else:
            field, op, value = args
        return _Query(self._store, self._path,
                      self._clauses + ((field, op, value),))

    def _matches(self, data):
        for field, op, value in self._clauses:
            if data.get(field) != value:
                return False
        return True

    def stream(self):
        rows = [
            (path, data) for path, data in self._store.docs.items()
            if path[:-1] == self._path and self._matches(data)
        ]
        return iter([_Snap(path, data) for path, data in rows])


class _Collection:
    def __init__(self, store, path):
        self._store = store
        self._path = path

    def document(self, doc_id=None):
        if doc_id is None:
            self._store.auto_id_counter += 1
            doc_id = "auto{}".format(self._store.auto_id_counter)
        return _DocRef(self._store, self._path + (doc_id,))

    def where(self, *args, **kwargs):
        return _Query(self._store, self._path).where(*args, **kwargs)

    def stream(self):
        return _Query(self._store, self._path).stream()


class _Transaction:
    def __init__(self, store):
        self._store = store
        self._buffer = []

    def set(self, ref, data, merge=False):
        if self._store.audit_write_error is not None and \
                ref._path[0] == audit_log.COLLECTION:
            raise self._store.audit_write_error
        self._buffer.append((ref._path, dict(data), merge))

    def commit(self):
        for path, data, merge in self._buffer:
            self._store.apply_set(path, data, merge)
        self._buffer = []


class _FakeDb:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})
        self.auto_id_counter = 0
        self.audit_write_error = None

    def collection(self, name):
        return _Collection(self, (name,))

    def transaction(self):
        return _Transaction(self)

    def apply_set(self, path, data, merge):
        if merge and path in self.docs:
            self.docs[path].update(data)
        else:
            self.docs[path] = dict(data)

    # test helpers -----------------------------------------------------
    def link(self, jti, channel="demo"):
        name = links_store._collection_name(channel)
        return self.docs.get((name, jti))

    def audit_rows(self):
        return [v for path, v in self.docs.items()
                if path[0] == audit_log.COLLECTION]


class _FakeTransactionalDecorator:
    def __call__(self, fn):
        def wrapper(transaction):
            fn(transaction)
            transaction.commit()
        return wrapper


class _FakeFirestoreModule:
    transactional = _FakeTransactionalDecorator()


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDb()
    import firebase_admin
    monkeypatch.setattr(firebase_admin, "firestore", _FakeFirestoreModule(),
                        raising=False)
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)
    return db


def _mint(fake_db, jti="jti-1", firm_id="acme", channel="demo",
          status=links_store.STATUS_MINTED, employee_id="emp-1",
          kit_id="w7", credit_cost=2, cap_usd=5.0, minted_at=1,
          open_deadline=500, **over):
    name = links_store._collection_name(channel)
    record = {
        "jti": jti, "firm_id": firm_id, "kit_id": kit_id,
        "employee_id": employee_id, "credit_cost": credit_cost,
        "cap_usd": cap_usd, "minted_at": minted_at,
        "open_deadline": open_deadline, "status": status,
        "revoked_by": None, "revoked_at": None, "expire_at": None,
    }
    record.update(over)
    fake_db.docs[(name, jti)] = record
    return record


def _redeem(fake_db, jti="jti-1", channel="demo", **over):
    name = link_redemptions._collection_name(channel)
    record = {"jti": jti, "firm_id": "acme", "kit_id": "w7",
              "opened_at": 10, "completed_at": None, "spend_usd": 0.5,
              "turns": 3}
    record.update(over)
    fake_db.docs[(name, jti)] = record
    return record


ADMIN_ACTOR = CompositeActor(uid="admin-1", email="ops@example.com",
                             kind=ACTOR_KIND_APP_ADMIN)
MANAGER_ACTOR = CompositeActor(uid="mgr-1", email="ada@acme.example",
                               kind=ACTOR_KIND_FIRM_MANAGER, firm_id="acme")
OTHER_MANAGER_ACTOR = CompositeActor(
    uid="mgr-2", email="bo@other.example",
    kind=ACTOR_KIND_FIRM_MANAGER, firm_id="other-firm")
# Employee actors (bd polyglot-pdf-scaig) -- employee_id is their own uid,
# exactly as require_app_admin_or_owning_manager_or_employee constructs one
# from a verified token.
EMPLOYEE_ACTOR = CompositeActor(
    uid="emp-1", email="al@acme.example",
    kind=ACTOR_KIND_FIRM_EMPLOYEE, firm_id="acme", employee_id="emp-1")
OTHER_EMPLOYEE_ACTOR = CompositeActor(
    uid="emp-b", email="bea@acme.example",
    kind=ACTOR_KIND_FIRM_EMPLOYEE, firm_id="acme", employee_id="emp-b")
OTHER_FIRM_EMPLOYEE_ACTOR = CompositeActor(
    uid="emp-2", email="cy@other.example",
    kind=ACTOR_KIND_FIRM_EMPLOYEE, firm_id="other-firm", employee_id="emp-2")


def _client(actor):
    # BOTH dependencies are overridden to the SAME actor: list_firm_links
    # carries require_app_admin_or_owning_manager_or_employee while
    # revoke_link still carries the narrower require_app_admin_or_owning_
    # manager (bd polyglot-pdf-scaig kept the write route's gate
    # untouched) -- a client built from one actor must drive both routes
    # identically for the admin/manager cases this file already exercises,
    # and an employee actor overriding the narrower dependency is exactly
    # what the "an employee cannot revoke" test below needs to be able to
    # even reach the route at all (the real dependency chain would 403 an
    # employee token before revoke_link's body ever runs; overriding lets
    # the test instead prove the ROUTE'S OWN actor-kind check, see that
    # test's docstring).
    app.dependency_overrides[require_app_admin_or_owning_manager] = \
        lambda: actor
    app.dependency_overrides[
        require_app_admin_or_owning_manager_or_employee] = lambda: actor
    return TestClient(app)


@pytest.fixture
def admin_client():
    with _client(ADMIN_ACTOR) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def manager_client():
    with _client(MANAGER_ACTOR) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def other_manager_client():
    with _client(OTHER_MANAGER_ACTOR) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def employee_client():
    with _client(EMPLOYEE_ACTOR) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def other_employee_client():
    """A second employee of the SAME firm ('acme') as EMPLOYEE_ACTOR --
    used to prove one employee never sees another's links."""
    with _client(OTHER_EMPLOYEE_ACTOR) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def other_firm_employee_client():
    """An employee of a DIFFERENT firm ('other-firm') -- used to prove the
    404-not-403 existence-hiding rule extends to the employee actor kind."""
    with _client(OTHER_FIRM_EMPLOYEE_ACTOR) as c:
        yield c
    app.dependency_overrides.clear()


# ==========================================================================
# GET /admin/firms/{firm_id}/links
# ==========================================================================


def test_a_missing_channel_is_422(admin_client, fake_db):
    resp = admin_client.get("/admin/firms/acme/links")
    assert resp.status_code == 422


def test_an_unknown_channel_is_422(admin_client, fake_db):
    resp = admin_client.get(
        "/admin/firms/acme/links", params={"channel": "prod"})
    assert resp.status_code == 422


def test_an_app_admin_may_list_any_firm(admin_client, fake_db):
    _mint(fake_db, jti="jti-1", firm_id="acme")
    _mint(fake_db, jti="jti-2", firm_id="other-firm")
    resp = admin_client.get(
        "/admin/firms/other-firm/links", params={"channel": "demo"})
    assert resp.status_code == 200
    body = resp.json()
    assert [row["jti"] for row in body["links"]] == ["jti-2"]


def test_a_manager_lists_their_own_firms_links(manager_client, fake_db):
    _mint(fake_db, jti="jti-1", firm_id="acme")
    resp = manager_client.get(
        "/admin/firms/acme/links", params={"channel": "demo"})
    assert resp.status_code == 200
    assert [row["jti"] for row in resp.json()["links"]] == ["jti-1"]


def test_a_manager_listing_another_firms_links_is_404_not_403(
        manager_client, fake_db):
    """Exit criterion 2. A manager naming a firm that is not their own gets
    the SAME 404 an unknown firm_id would get -- never 403, which would
    confirm the named firm exists."""
    _mint(fake_db, jti="jti-1", firm_id="other-firm")
    resp = manager_client.get(
        "/admin/firms/other-firm/links", params={"channel": "demo"})
    assert resp.status_code == 404


def test_an_unknown_firm_is_also_404_for_an_app_admin(admin_client, fake_db):
    """The 404 is not an existence-of-firm-manager-access signal -- an app
    admin gets the same 404-shaped empty-list-is-not-what-happens-here
    behavior is NOT claimed; this just proves an app admin's request for a
    firm with zero links is a normal 200 with an empty list, not a 404 --
    the admin service has no firm registry check in THIS route (firm_routes
    owns firm existence); listing is link-store-only."""
    resp = admin_client.get(
        "/admin/firms/nonexistent-firm/links", params={"channel": "demo"})
    assert resp.status_code == 200
    assert resp.json()["links"] == []


def test_status_and_employee_id_filter(admin_client, fake_db):
    _mint(fake_db, jti="jti-1", firm_id="acme", status=links_store.STATUS_MINTED,
          employee_id="emp-a")
    _mint(fake_db, jti="jti-2", firm_id="acme",
          status=links_store.STATUS_REVOKED, employee_id="emp-a")
    _mint(fake_db, jti="jti-3", firm_id="acme", status=links_store.STATUS_MINTED,
          employee_id="emp-b")
    resp = admin_client.get("/admin/firms/acme/links", params={
        "channel": "demo", "status": links_store.STATUS_MINTED,
        "employee_id": "emp-a",
    })
    assert resp.status_code == 200
    assert [row["jti"] for row in resp.json()["links"]] == ["jti-1"]


def test_link_listing_response_is_allowlisted(admin_client, fake_db):
    """Exit criterion 1. The response contains EXACTLY the allowlisted keys
    even when the stored docs carry extras -- a PROPERTY, mutation-verified
    below by removing the allowlist filter in a way the parametrized
    variant proves goes red."""
    _mint(fake_db, jti="jti-1", firm_id="acme",
          some_internal_field="should never leak",
          another_secret=42)
    _redeem(fake_db, jti="jti-1", extra_internal="also should never leak")
    resp = admin_client.get(
        "/admin/firms/acme/links", params={"channel": "demo"})
    assert resp.status_code == 200
    row = resp.json()["links"][0]
    assert set(row.keys()) == set(link_routes._ALLOWLISTED_KEYS)
    assert row == {
        "jti": "jti-1", "kit_id": "w7", "employee_id": "emp-1",
        "status": links_store.STATUS_MINTED, "minted_at": 1,
        "open_deadline": 500, "opened_at": 10, "completed_at": None,
        "spend_usd": 0.5, "turns": 3, "cap_usd": 5.0, "credit_cost": 2,
    }


def test_a_link_never_opened_has_null_redemption_fields(admin_client, fake_db):
    """No link_redemptions doc exists yet (never opened) -- the join must
    not 500 or invent a redemption record."""
    _mint(fake_db, jti="jti-1", firm_id="acme")
    resp = admin_client.get(
        "/admin/firms/acme/links", params={"channel": "demo"})
    row = resp.json()["links"][0]
    assert row["opened_at"] is None
    assert row["completed_at"] is None
    assert row["spend_usd"] is None
    assert row["turns"] is None


def test_listing_writes_no_audit_row(admin_client, fake_db):
    _mint(fake_db, jti="jti-1", firm_id="acme")
    admin_client.get("/admin/firms/acme/links", params={"channel": "demo"})
    assert fake_db.audit_rows() == []


# ==========================================================================
# GET /admin/firms/{firm_id}/links -- the EMPLOYEE actor (bd
# polyglot-pdf-scaig, plan "Tests to pin" #9)
# ==========================================================================


def test_an_employee_can_list_their_own_firms_links(employee_client, fake_db):
    """The gate that was a flat 403 before this bead now lets an employee
    reach the route at all -- the base case bd polyglot-pdf-scaig exists to
    fix."""
    _mint(fake_db, jti="jti-1", firm_id="acme", employee_id="emp-1")
    resp = employee_client.get(
        "/admin/firms/acme/links", params={"channel": "demo"})
    assert resp.status_code == 200
    assert [row["jti"] for row in resp.json()["links"]] == ["jti-1"]


def test_employee_history_scoped_to_token_not_query(
        employee_client, fake_db):
    """Exit criterion / plan test #9, the query half: an employee's OWN
    links are returned even when the query asks for someone else's, and a
    query naming another employee_id does not leak that other employee's
    links either -- the token wins, not the query, in EITHER direction.

    Mutation: read employee_id from the query when present instead of
    always forcing actor.employee_id -- this goes red (jti-2, minted for
    "emp-b", would appear in the response)."""
    _mint(fake_db, jti="jti-1", firm_id="acme", employee_id="emp-1")
    _mint(fake_db, jti="jti-2", firm_id="acme", employee_id="emp-b")
    resp = employee_client.get("/admin/firms/acme/links", params={
        "channel": "demo", "employee_id": "emp-b",
    })
    assert resp.status_code == 200
    assert [row["jti"] for row in resp.json()["links"]] == ["jti-1"]


def test_an_employee_never_sees_another_employees_links(
        other_employee_client, fake_db):
    """The plan's own wording: "an employee never sees another employee's
    links". other_employee_client is a SECOND employee of the SAME firm
    ('acme') as the link below, with no query params at all -- the omission
    itself must not widen the result to the whole firm."""
    _mint(fake_db, jti="jti-1", firm_id="acme", employee_id="emp-1")
    resp = other_employee_client.get(
        "/admin/firms/acme/links", params={"channel": "demo"})
    assert resp.status_code == 200
    assert resp.json()["links"] == []


def test_an_employee_listing_another_firms_links_is_404_not_403(
        other_firm_employee_client, fake_db):
    """The existence-hiding 404 rule (_require_owning_firm) extends to the
    employee actor kind exactly as it already covers a manager -- an
    employee naming a firm that is not their own must not learn whether
    that firm exists."""
    _mint(fake_db, jti="jti-1", firm_id="acme", employee_id="emp-1")
    resp = other_firm_employee_client.get(
        "/admin/firms/acme/links", params={"channel": "demo"})
    assert resp.status_code == 404


def test_employee_link_listing_response_is_allowlisted(
        employee_client, fake_db):
    """Exit criterion / plan test #9's allowlist half: the SAME response
    shape an admin or manager gets (_public_link_view has no actor-kind
    branch), pinned again through the employee actor so a future change
    cannot special-case a wider response for this kind alone."""
    _mint(fake_db, jti="jti-1", firm_id="acme", employee_id="emp-1",
          some_internal_field="should never leak")
    _redeem(fake_db, jti="jti-1", extra_internal="also should never leak")
    resp = employee_client.get(
        "/admin/firms/acme/links", params={"channel": "demo"})
    assert resp.status_code == 200
    row = resp.json()["links"][0]
    assert set(row.keys()) == set(link_routes._ALLOWLISTED_KEYS)


def test_an_employee_status_filter_still_applies_with_employee_id_forced(
        employee_client, fake_db):
    """status stays a real, respected filter for an employee -- only
    employee_id is overridden, not every query param."""
    _mint(fake_db, jti="jti-1", firm_id="acme", employee_id="emp-1",
          status=links_store.STATUS_MINTED)
    _mint(fake_db, jti="jti-2", firm_id="acme", employee_id="emp-1",
          status=links_store.STATUS_REVOKED)
    resp = employee_client.get("/admin/firms/acme/links", params={
        "channel": "demo", "status": links_store.STATUS_MINTED,
    })
    assert resp.status_code == 200
    assert [row["jti"] for row in resp.json()["links"]] == ["jti-1"]


# ==========================================================================
# POST /admin/links/{jti}/revoke
# ==========================================================================


def test_revoke_requires_a_channel(admin_client, fake_db):
    _mint(fake_db, jti="jti-1", firm_id="acme")
    resp = admin_client.post("/admin/links/jti-1/revoke")
    assert resp.status_code == 422


def test_revoke_writes_status_and_one_audit_row_atomically(
        admin_client, fake_db):
    """Exit criterion 3, atomicity half."""
    _mint(fake_db, jti="jti-1", firm_id="acme")
    resp = admin_client.post(
        "/admin/links/jti-1/revoke", params={"channel": "demo"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == links_store.STATUS_REVOKED
    assert body["before_status"] == links_store.STATUS_MINTED

    stored = fake_db.link("jti-1")
    assert stored["status"] == links_store.STATUS_REVOKED
    assert stored["revoked_by"] == ADMIN_ACTOR.uid
    assert isinstance(stored["revoked_at"], int)

    rows = fake_db.audit_rows()
    assert len(rows) == 1
    assert rows[0]["action"] == link_routes.ACTION_LINK_REVOKE
    assert rows[0]["actor_uid"] == ADMIN_ACTOR.uid
    assert rows[0]["target"] == "links/jti-1"
    assert rows[0]["channel"] == "demo"


def test_a_forced_audit_failure_leaves_the_link_unrevoked(
        admin_client, fake_db):
    """The atomicity property, proven by forcing the audit write to fail: a
    real transaction rolls the status change back too, since the fake's
    _Transaction only applies its buffer on commit() and _FakeTransactional
    Decorator only calls commit() when the wrapped function returns without
    raising."""
    before = _mint(fake_db, jti="jti-1", firm_id="acme")
    fake_db.audit_write_error = RuntimeError("simulated audit outage")
    resp = admin_client.post(
        "/admin/links/jti-1/revoke", params={"channel": "demo"})
    assert resp.status_code == 500
    assert fake_db.link("jti-1") == before


def test_a_manager_revokes_their_own_firms_link(manager_client, fake_db):
    _mint(fake_db, jti="jti-1", firm_id="acme")
    resp = manager_client.post(
        "/admin/links/jti-1/revoke", params={"channel": "demo"})
    assert resp.status_code == 200
    assert fake_db.link("jti-1")["revoked_by"] == MANAGER_ACTOR.uid


def test_a_manager_revoking_another_firms_link_is_404_not_403(
        other_manager_client, fake_db):
    """Exit criterion 2's revoke half -- same 404-not-403 rule as listing."""
    _mint(fake_db, jti="jti-1", firm_id="acme")
    resp = other_manager_client.post(
        "/admin/links/jti-1/revoke", params={"channel": "demo"})
    assert resp.status_code == 404
    assert fake_db.link("jti-1")["status"] == links_store.STATUS_MINTED


def test_revoking_an_unknown_jti_is_404(admin_client, fake_db):
    resp = admin_client.post(
        "/admin/links/no-such-jti/revoke", params={"channel": "demo"})
    assert resp.status_code == 404


@pytest.mark.parametrize("status", [
    links_store.STATUS_OPENED, links_store.STATUS_COMPLETED,
    links_store.STATUS_REFUNDED, links_store.STATUS_REVOKED,
    links_store.STATUS_BUDGET_EXHAUSTED,
])
def test_revoking_a_non_minted_link_is_409(admin_client, fake_db, status):
    """Only a STATUS_MINTED link may be revoked -- every OTHER status in
    the vocabulary is refused, enumerated rather than hand-picked (scar #8:
    enumerate the set, not one instance)."""
    _mint(fake_db, jti="jti-1", firm_id="acme", status=status)
    resp = admin_client.post(
        "/admin/links/jti-1/revoke", params={"channel": "demo"})
    assert resp.status_code == 409
    assert fake_db.link("jti-1")["status"] == status


def test_revoke_does_not_touch_the_other_channels_collection(
        admin_client, fake_db):
    _mint(fake_db, jti="jti-1", firm_id="acme", channel="demo")
    _mint(fake_db, jti="jti-1", firm_id="acme", channel="staging")
    admin_client.post("/admin/links/jti-1/revoke", params={"channel": "demo"})
    assert fake_db.link("jti-1", channel="demo")["status"] == \
        links_store.STATUS_REVOKED
    assert fake_db.link("jti-1", channel="staging")["status"] == \
        links_store.STATUS_MINTED


def test_revoke_route_carries_the_narrower_gate_not_the_employee_one(
        fake_db):
    """bd polyglot-pdf-scaig's OWN scope line: the write route stays on
    require_app_admin_or_owning_manager, UNCHANGED, so an employee token can
    never reach revoke_link's body at all -- the real dependency, not an
    override, is what refuses it. Proven by reading the route's wiring
    directly (mirrors test_admin_route_auth.py's approach) rather than by
    driving an HTTP call with an overridden dependency, since overriding
    require_app_admin_or_owning_manager with an employee actor (as the
    other revoke tests in this file could do) would prove only that the
    ROUTE BODY has no special-case for that kind -- not that the real gate
    refuses one before the body runs, which is the actual guarantee this
    bead makes.

    Mutation: swap revoke_link's dependency to require_app_admin_or_owning_
    manager_or_employee -- this goes red, and so does
    test_admin_route_auth.py::test_only_the_link_listing_route_carries_the_
    fifth_gate."""
    route = next(
        r for r in app.routes if r.path == "/admin/links/{jti}/revoke")
    dependant = route.dependant
    assert any(sub.call is require_app_admin_or_owning_manager
              for sub in dependant.dependencies)
    assert not any(
        sub.call is require_app_admin_or_owning_manager_or_employee
        for sub in dependant.dependencies)
