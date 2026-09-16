"""POST/GET /admin/deploys (bd polyglot-pdf-tb3kp, Epic 4 bead 4.3; GET
/admin/deploys/targets and GET /admin/deploys/promotable added by bd
polyglot-pdf-ryx86, E4.7, for the console's Deploys page).

Pins the bead's exit criterion 1:

  1. test_trigger_writes_a_queued_row_and_a_pending_then_committed_audit_pair
     -- a mocked run_build_trigger, both writes checked.
  2. test_a_cloud_build_failure_marks_audit_failed_and_leaves_no_queued_row
     -- mutation-verified: reverting the failure-handling branch (returning
     the success path instead) is what proves this test can fail.
  3. test_route_auth_and_audit_coverage_include_all_four_routes -- a
     read-only sanity check that the route/gate and audit-coverage set
     tests (test_admin_route_auth.py, test_admin_audit_coverage.py) already
     enumerate all four deploy routes; those two files own the real
     assertions, this file only guards against a rename silently dropping
     one from THIS file's own knowledge of the route set.
  4. test_demo_family_target_refuses_early_without_staging_success /
     test_demo_family_target_with_staging_success_proceeds -- the early,
     friendly 409 (exit criterion 3's route half).
  5. test_unknown_target_is_422 / test_malformed_sha_is_422.
  6. test_list_deploys_filters_by_channel_and_target /
     test_get_one_deploy_by_id / test_get_unknown_deploy_is_404.

bd polyglot-pdf-ryx86 (E4.7) adds:

  7. test_list_deploy_targets_returns_the_closed_set_with_gated_flags --
     GET /admin/deploys/targets restates deploy/targets.py's TARGETS/
     GATED_TARGETS/CHANNEL_BY_TARGET, derived off those same constants (not
     a hand-typed expected list) so a future target addition cannot drift
     the two apart silently.
  8. test_promotable_true_after_staging_success /
     test_promotable_false_without_staging_success -- GET /admin/deploys/
     promotable for a GATED_TARGETS entry computes the SAME predicate the
     POST route's own early 409 uses.
  9. test_promotable_is_always_true_for_a_non_gated_target -- the preview
     must not invent a stricter rule than POST's own early check applies.
  10. test_promotable_requires_target_and_sha / test_promotable_target_and_
      sha_are_validated -- same 422 shapes as POST's own body validation.
  11. test_targets_and_promotable_routes_are_reachable_ahead_of_the_deploy_id_
      route -- mutation-verified registration-order guard: a literal
      "targets"/"promotable" request must reach the new handlers, not fall
      through to GET /admin/deploys/{deploy_id} as an attempted id lookup.

THE FAKE FIRESTORE extends test_sweep_routes.py's own _FakeDb/_Collection/
_Query shape with order_by()/limit() (this route's list endpoint is the
first admin-service query to need them) -- kept as a LOCAL, richer copy
rather than importing that module's classes, since a shared test-fixture
module would need its own promotion to a conftest and no third caller
exists yet to justify it.

ASCII only.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from admin_backend.main import app
from admin_backend.routes import deploy_routes
from admin_backend.services import audit_log, cloud_build
from admin_backend.services.admin_auth import AdminActor, require_app_admin

VALID_SHA_A = "a" * 40
VALID_SHA_B = "b" * 40


class _Snap:
    def __init__(self, path, data):
        self._path = path
        self._data = dict(data) if data is not None else None
        self.reference = None

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

    def get(self):
        snap = _Snap(self._path, self._store.docs.get(self._path))
        snap.reference = self
        return snap

    def set(self, data):
        self._store.docs[self._path] = dict(data)

    def update(self, data):
        existing = self._store.docs.get(self._path, {})
        existing.update(data)
        self._store.docs[self._path] = existing


class _Query:
    def __init__(self, store, path, clauses=(), order=None, limit_n=None):
        self._store = store
        self._path = path
        self._clauses = tuple(clauses)
        self._order = order
        self._limit_n = limit_n

    def where(self, field, op, value):
        return _Query(self._store, self._path,
                      self._clauses + ((field, op, value),),
                      self._order, self._limit_n)

    def order_by(self, field, direction="ASCENDING"):
        return _Query(self._store, self._path, self._clauses,
                      (field, direction), self._limit_n)

    def limit(self, n):
        return _Query(self._store, self._path, self._clauses, self._order, n)

    def _matches(self, data):
        for field, op, value in self._clauses:
            actual = data.get(field)
            if op == "==":
                if actual != value:
                    return False
            else:
                raise NotImplementedError(op)
        return True

    def stream(self):
        rows = [
            (path, data) for path, data in self._store.docs.items()
            if path[:-1] == self._path and self._matches(data)
        ]
        if self._order is not None:
            field, direction = self._order
            rows.sort(key=lambda pd: pd[1].get(field),
                      reverse=(direction == "DESCENDING"))
        if self._limit_n is not None:
            rows = rows[: self._limit_n]
        snaps = []
        for path, data in rows:
            snap = _Snap(path, data)
            snap.reference = _DocRef(self._store, path)
            snaps.append(snap)
        return iter(snaps)


class _Collection:
    def __init__(self, store, path):
        self._store = store
        self._path = path

    def document(self, doc_id=None):
        if doc_id is None:
            self._store.auto_id_counter += 1
            doc_id = "auto{}".format(self._store.auto_id_counter)
        return _DocRef(self._store, self._path + (doc_id,))

    def where(self, field, op, value):
        return _Query(self._store, self._path).where(field, op, value)

    def order_by(self, field, direction="ASCENDING"):
        return _Query(self._store, self._path).order_by(field, direction)

    def stream(self):
        return _Query(self._store, self._path).stream()


class _FakeDb:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})
        self.auto_id_counter = 0

    def collection(self, name):
        return _Collection(self, (name,))

    def audit_rows(self):
        return [v for path, v in self.docs.items()
                if path[0] == audit_log.COLLECTION]

    def deployment_rows(self):
        return [v for path, v in self.docs.items()
                if path[0] == deploy_routes.COLLECTION]


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)
    return db


@pytest.fixture
def admin_client():
    actor = AdminActor(uid="op-1", email="op@x.com")
    app.dependency_overrides[require_app_admin] = lambda: actor
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_trigger_writes_a_queued_row_and_a_pending_then_committed_audit_pair(
        fake_db, admin_client, monkeypatch):
    monkeypatch.setattr(
        cloud_build, "run_target",
        lambda target, sha, project_id: {
            "build_id": "build-123", "log_url": "https://example.com/log"})
    monkeypatch.setattr(deploy_routes, "_project_id", lambda: "proj-1")

    resp = admin_client.post(
        "/admin/deploys", json={"target": "editor", "sha": VALID_SHA_A})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["target"] == "editor"
    assert body["build_id"] == "build-123"
    assert body["status"] == deploy_routes.STATUS_QUEUED

    rows = fake_db.deployment_rows()
    assert len(rows) == 1
    assert rows[0]["build_id"] == "build-123"
    assert rows[0]["status"] == deploy_routes.STATUS_QUEUED
    assert rows[0]["sha"] == VALID_SHA_A
    assert rows[0]["triggered_by"] == "op-1"

    audit_rows = fake_db.audit_rows()
    assert len(audit_rows) == 1
    assert audit_rows[0]["state"] == audit_log.STATE_COMMITTED
    assert audit_rows[0]["action"] == deploy_routes.ACTION_DEPLOY_TRIGGER
    assert audit_rows[0]["after"]["build_id"] == "build-123"


def test_a_cloud_build_failure_marks_audit_failed_and_leaves_no_queued_row(
        fake_db, admin_client, monkeypatch):
    def _boom(target, sha, project_id):
        raise cloud_build.CloudBuildUnavailable("trigger not found")

    monkeypatch.setattr(cloud_build, "run_target", _boom)
    monkeypatch.setattr(deploy_routes, "_project_id", lambda: "proj-1")

    resp = admin_client.post(
        "/admin/deploys", json={"target": "editor", "sha": VALID_SHA_A})

    assert resp.status_code == 503, resp.text

    rows = fake_db.deployment_rows()
    assert len(rows) == 1
    # NO row claims a build id, and its status is corrected away from
    # "queued" -- exit criterion 1's own wording.
    assert rows[0]["build_id"] is None
    assert rows[0]["status"] == deploy_routes.STATUS_FAILURE

    audit_rows = fake_db.audit_rows()
    assert len(audit_rows) == 1
    assert audit_rows[0]["state"] == audit_log.STATE_FAILED


def test_unknown_target_is_422(admin_client):
    resp = admin_client.post(
        "/admin/deploys", json={"target": "nonexistent", "sha": VALID_SHA_A})
    assert resp.status_code == 422


@pytest.mark.parametrize("bad_sha", [
    "short", "A" * 40, "g" * 40, "a" * 39, "a" * 41, "",
])
def test_malformed_sha_is_422(admin_client, bad_sha):
    resp = admin_client.post(
        "/admin/deploys", json={"target": "editor", "sha": bad_sha})
    assert resp.status_code == 422


def test_demo_family_target_refuses_early_without_staging_success(
        fake_db, admin_client, monkeypatch):
    monkeypatch.setattr(deploy_routes, "_project_id", lambda: "proj-1")
    called = []
    monkeypatch.setattr(
        cloud_build, "run_target",
        lambda *a, **k: called.append(1) or {"build_id": "x", "log_url": "y"})

    resp = admin_client.post(
        "/admin/deploys", json={"target": "backend-demo", "sha": VALID_SHA_A})

    assert resp.status_code == 409, resp.text
    assert not called, "Cloud Build must not be called when the gate refuses"
    assert not fake_db.deployment_rows(), (
        "no deployment row should be written for an early-refused trigger")


def test_demo_family_target_with_staging_success_proceeds(
        fake_db, admin_client, monkeypatch):
    fake_db.docs[("deployments", "staging-row")] = {
        "target": "backend-staging", "target_family": "backend",
        "channel": "staging", "sha": VALID_SHA_A, "status": "success",
    }
    monkeypatch.setattr(deploy_routes, "_project_id", lambda: "proj-1")
    monkeypatch.setattr(
        cloud_build, "run_target",
        lambda target, sha, project_id: {
            "build_id": "build-456", "log_url": "https://example.com/log"})

    resp = admin_client.post(
        "/admin/deploys", json={"target": "backend-demo", "sha": VALID_SHA_A})

    assert resp.status_code == 200, resp.text
    assert resp.json()["build_id"] == "build-456"


def test_admin_service_is_not_refused_by_the_early_gate(
        fake_db, admin_client, monkeypatch):
    """An admin-service deploy must reach Cloud Build with an EMPTY
    deployments collection.

    Its staging-equivalent proof is written by its own build's
    admin-service-record-deployment step, which by construction runs before
    that build's admin-service-staging-gate -- so a pre-build route check
    could never find a row for a new sha and would 409 every admin-service
    deploy forever. The in-build gate is the enforcement; this route's check
    only covers targets whose proof predates the build.
    """
    monkeypatch.setattr(deploy_routes, "_project_id", lambda: "proj-1")
    monkeypatch.setattr(
        cloud_build, "run_target",
        lambda target, sha, project_id: {
            "build_id": "build-admin", "log_url": "https://example.com/log"})

    resp = admin_client.post(
        "/admin/deploys", json={"target": "admin-service", "sha": VALID_SHA_A})

    assert resp.status_code == 200, resp.text
    assert resp.json()["build_id"] == "build-admin"


def test_list_deploys_filters_by_channel_and_target(fake_db, admin_client):
    fake_db.docs[("deployments", "d1")] = {
        "target": "backend-staging", "target_family": "backend",
        "channel": "staging", "sha": VALID_SHA_A, "status": "success",
        "ts": 100,
    }
    fake_db.docs[("deployments", "d2")] = {
        "target": "backend-demo", "target_family": "backend",
        "channel": "demo", "sha": VALID_SHA_B, "status": "success", "ts": 200,
    }
    fake_db.docs[("deployments", "d3")] = {
        "target": "frontend-demo", "target_family": "frontend",
        "channel": "demo", "sha": VALID_SHA_A, "status": "queued", "ts": 300,
    }

    resp = admin_client.get("/admin/deploys")
    assert resp.status_code == 200, resp.text
    rows = resp.json()["rows"]
    assert [r["id"] for r in rows] == ["d3", "d2", "d1"], (
        "rows must come back newest-first by ts")

    resp = admin_client.get("/admin/deploys", params={"channel": "demo"})
    assert {r["id"] for r in resp.json()["rows"]} == {"d2", "d3"}

    resp = admin_client.get(
        "/admin/deploys", params={"target": "backend-demo"})
    assert {r["id"] for r in resp.json()["rows"]} == {"d2"}


def test_get_one_deploy_by_id(fake_db, admin_client):
    fake_db.docs[("deployments", "d1")] = {
        "target": "editor", "target_family": "editor", "channel": "demo",
        "sha": VALID_SHA_A, "status": "success", "ts": 100,
    }
    resp = admin_client.get("/admin/deploys/d1")
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == "d1"
    assert resp.json()["target"] == "editor"


def test_get_unknown_deploy_is_404(fake_db, admin_client):
    resp = admin_client.get("/admin/deploys/nope")
    assert resp.status_code == 404


def test_route_auth_and_audit_coverage_include_all_four_routes():
    """A read-only sanity check -- the real assertions live in
    test_admin_route_auth.py and test_admin_audit_coverage.py, which derive
    the live route set off app.routes. This test only guards THIS file's
    own knowledge of the route set against drifting from what main.py
    actually registers.
    """
    paths = {(tuple(sorted(r.methods)), r.path)
             for r in app.routes if hasattr(r, "methods")}
    expected = {
        (("POST",), "/admin/deploys"),
        (("GET",), "/admin/deploys"),
        (("GET",), "/admin/deploys/targets"),
        (("GET",), "/admin/deploys/promotable"),
        (("GET",), "/admin/deploys/{deploy_id}"),
    }
    assert expected <= paths, (
        "one or more of the five /admin/deploys routes is missing from "
        "the live app -- did a route get renamed or dropped?")


def test_list_deploy_targets_returns_the_closed_set_with_gated_flags(admin_client):
    """bd polyglot-pdf-ryx86 (E4.7): GET /admin/deploys/targets restates
    deploy/targets.py's own TARGETS/CHANNEL_BY_TARGET/GATED_TARGETS,
    DERIVED off those same constants -- a hand-typed expected list here
    would happily agree with a stale route and never catch a real drift.
    Mutation: drop the "gated" key computation (always False) -- red.
    """
    from deploy.targets import CHANNEL_BY_TARGET, GATED_TARGETS, TARGETS, target_family

    resp = admin_client.get("/admin/deploys/targets")
    assert resp.status_code == 200, resp.text
    rows = resp.json()["targets"]
    assert [r["target"] for r in rows] == list(TARGETS)
    for row in rows:
        t = row["target"]
        assert row["target_family"] == target_family(t)
        assert row["channel"] == CHANNEL_BY_TARGET[t]
        assert row["gated"] == (t in GATED_TARGETS)
    # At least one gated and one non-gated row actually exist in the fixture
    # -- otherwise the per-row equality checks above could all pass on an
    # accidentally-constant "gated" value.
    assert any(r["gated"] for r in rows)
    assert any(not r["gated"] for r in rows)


def test_promotable_false_without_staging_success(fake_db, admin_client):
    """bd polyglot-pdf-ryx86 (E4.7): a GATED_TARGETS entry with no matching
    staging success is NOT promotable. Mutation: hard-code `promotable =
    True` -- red."""
    resp = admin_client.get(
        "/admin/deploys/promotable",
        params={"target": "backend-demo", "sha": VALID_SHA_A},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {
        "target": "backend-demo", "sha": VALID_SHA_A,
        "target_family": "backend", "gated": True, "promotable": False,
    }


def test_promotable_true_after_staging_success(fake_db, admin_client):
    """bd polyglot-pdf-ryx86 (E4.7): the SAME predicate POST's own early
    409 uses -- a matching staging success flips this to True. Mutation:
    swap `staging_verified` for a constant -- red (this and the test above
    together pin both branches)."""
    fake_db.docs[("deployments", "staging-row")] = {
        "target": "backend-staging", "target_family": "backend",
        "channel": "staging", "sha": VALID_SHA_A, "status": "success",
    }
    resp = admin_client.get(
        "/admin/deploys/promotable",
        params={"target": "backend-demo", "sha": VALID_SHA_A},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["promotable"] is True


def test_promotable_is_always_true_for_a_non_gated_target(admin_client):
    """bd polyglot-pdf-ryx86 (E4.7): a target outside GATED_TARGETS (POST's
    own early check applies no gate to it either) must never be reported
    as blocked, even with an EMPTY deployments collection. Mutation: run
    the staging_verified check unconditionally -- red."""
    resp = admin_client.get(
        "/admin/deploys/promotable",
        params={"target": "editor", "sha": VALID_SHA_A},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["gated"] is False
    assert body["promotable"] is True


def test_promotable_requires_target_and_sha(admin_client):
    resp = admin_client.get("/admin/deploys/promotable")
    assert resp.status_code == 422
    resp = admin_client.get(
        "/admin/deploys/promotable", params={"target": "editor"})
    assert resp.status_code == 422
    resp = admin_client.get(
        "/admin/deploys/promotable", params={"sha": VALID_SHA_A})
    assert resp.status_code == 422


def test_promotable_target_and_sha_are_validated(admin_client):
    resp = admin_client.get(
        "/admin/deploys/promotable",
        params={"target": "nonexistent", "sha": VALID_SHA_A})
    assert resp.status_code == 422

    resp = admin_client.get(
        "/admin/deploys/promotable",
        params={"target": "editor", "sha": "short"})
    assert resp.status_code == 422


def test_targets_and_promotable_routes_are_reachable_ahead_of_the_deploy_id_route(
        fake_db, admin_client):
    """bd polyglot-pdf-ryx86 (E4.7): a literal "targets"/"promotable"
    request must reach the new handlers, never fall through to GET
    /admin/deploys/{deploy_id} as an attempted id lookup (module
    docstring's registration-order note). Mutation: register the two new
    routes AFTER get_deploy on the router -- red (both would 404 as "No
    such deployment" instead of returning their real shape)."""
    resp = admin_client.get("/admin/deploys/targets")
    assert resp.status_code == 200, resp.text
    assert "targets" in resp.json()

    resp = admin_client.get(
        "/admin/deploys/promotable",
        params={"target": "editor", "sha": VALID_SHA_A})
    assert resp.status_code == 200, resp.text
    assert "promotable" in resp.json()

    # A REAL unknown deploy id still 404s -- the guard above did not simply
    # disable the {deploy_id} route.
    resp = admin_client.get("/admin/deploys/some-other-id")
    assert resp.status_code == 404
