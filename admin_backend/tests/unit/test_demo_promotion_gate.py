"""bd polyglot-pdf-jub5f -- Epic 4 bead 4.4 of
docs/sprint_22_admin-console_plan.md, exit criteria 1 and 2.

Assembles, IN ONE FILE, the three directions the bead's exit criteria name:

  1. THROUGH THE REAL ROUTE (POST /admin/deploys): a demo-family target with
     no staging success is refused 409, naming the missing staging record;
     the SAME target with a matching staging success proceeds to 200.
     test_deploy_routes.py already pins these two cases as part of bead
     4.3's own exit criterion 3 (the route existed before this bead) --
     this file restates them as bead 4.4's own record, per exit criterion
     1's literal text ("proves the route refuses ... and allows through the
     real POST /admin/deploys"). The assertions are the SAME behavior,
     pinned again here as this bead's own criterion, not a second,
     competing spec of different behavior.
  2. THE PURE PREDICATE'S CASE TABLE: wrong family, wrong sha, status
     failure, and the no-recency rollback case (an older sha's success is
     NOT invalidated by a later staging deploy of a different sha).
     test_promotion_gate.py (bd 4.2) already carries the exhaustive
     per-field table over admin_backend.services.promotion_gate.
     staging_verified; this file's table is the four cases the bead body
     names verbatim, kept here so bead 4.4's own exit criterion is provable
     from this one file without cross-referencing 4.2's.
  3. THE CLI'S EXIT CODES (scripts/promotion_gate.py), with a STUBBED
     Firestore query -- no real network/gcloud call: exit 0 when a matching
     staging success exists, exit 1 when it does not, and exit 1 (fail
     CLOSED) when the query itself raises.

MUTATION-VERIFIED (CLAUDE.md scar #9, "test the tests"): every test group
below was hand-verified to go red under the mutation the bead names --
dropping promotion_gate.py's status check, and adding a recency rule that
lets a newer staging deploy's SHA satisfy an older one's demo build. See
each test's docstring for the exact mutation and the observed failure.

ASCII only.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from admin_backend.main import app
from admin_backend.routes import deploy_routes
from admin_backend.services import audit_log, cloud_build
from admin_backend.services.admin_auth import AdminActor, require_app_admin
from admin_backend.services.promotion_gate import staging_verified
import scripts.promotion_gate as promotion_gate_cli

VALID_SHA_A = "a" * 40
VALID_SHA_B = "b" * 40


# --------------------------------------------------------------------------
# 1. THROUGH THE REAL ROUTE -- a minimal fake Firestore, same shape as
# test_deploy_routes.py's own _FakeDb (kept as a local copy rather than a
# shared import: that file's own docstring already anticipates a third
# caller as the trigger to promote this to a conftest fixture, but doing so
# is a refactor beyond this bead's declared surfaces -- noted for a future
# bead, not undertaken here).
# --------------------------------------------------------------------------
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
    def __init__(self, store, path, clauses=()):
        self._store = store
        self._path = path
        self._clauses = tuple(clauses)

    def where(self, field, op, value):
        return _Query(self._store, self._path, self._clauses + ((field, op, value),))

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
        snaps = []
        for path, data in self._store.docs.items():
            if path[:-1] == self._path and self._matches(data):
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

    def stream(self):
        return _Query(self._store, self._path).stream()


class _FakeDb:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})
        self.auto_id_counter = 0

    def collection(self, name):
        return _Collection(self, (name,))


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


def test_route_refuses_409_naming_the_missing_staging_record(
        fake_db, admin_client, monkeypatch):
    """Exit criterion 1's first clause: a demo-family target (backend-demo)
    with NO staging success record for its sha is refused before Cloud
    Build is ever touched, and the 409 detail NAMES the missing record
    (the family and sha it looked for), not a generic refusal.

    Mutation-verified: short-circuiting deploy_routes._do_trigger_deploy's
    "if target in GATED_TARGETS" check to `if False:` (skipping the gate
    entirely) turns this red -- the call proceeds to 200 with a fabricated
    build id instead of 409.
    """
    monkeypatch.setattr(deploy_routes, "_project_id", lambda: "proj-1")
    called = []
    monkeypatch.setattr(
        cloud_build, "run_target",
        lambda *a, **k: called.append(1) or {"build_id": "x", "log_url": "y"})

    resp = admin_client.post(
        "/admin/deploys", json={"target": "backend-demo", "sha": VALID_SHA_A})

    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert "backend" in detail, "409 detail does not name the target family"
    assert VALID_SHA_A in detail, "409 detail does not name the sha"
    assert not called, "Cloud Build must not be reached when the gate refuses"


def test_route_allows_through_with_a_matching_staging_success(
        fake_db, admin_client, monkeypatch):
    """Exit criterion 1's second clause: the SAME target/sha proceeds to a
    real (mocked) Cloud Build call once a matching staging success record
    exists.

    Mutation-verified: changing the fixture's staging row status to
    "failure" turns this red (409 instead of 200) -- confirming the test
    actually depends on staging_verified() finding a real success match,
    not merely on a row existing.
    """
    fake_db.docs[("deployments", "staging-row")] = {
        "target": "backend-staging", "target_family": "backend",
        "channel": "staging", "sha": VALID_SHA_A, "status": "success",
    }
    monkeypatch.setattr(deploy_routes, "_project_id", lambda: "proj-1")
    monkeypatch.setattr(
        cloud_build, "run_target",
        lambda target, sha, project_id: {
            "build_id": "build-789", "log_url": "https://example.com/log"})

    resp = admin_client.post(
        "/admin/deploys", json={"target": "backend-demo", "sha": VALID_SHA_A})

    assert resp.status_code == 200, resp.text
    assert resp.json()["build_id"] == "build-789"


# --------------------------------------------------------------------------
# 2. THE PURE PREDICATE'S CASE TABLE -- the four cases the bead body names
# verbatim, plus the positive case each is a negation of.
# --------------------------------------------------------------------------
def _record(**overrides):
    base = {
        "channel": "staging",
        "target_family": "backend",
        "sha": VALID_SHA_A,
        "status": "success",
    }
    base.update(overrides)
    return base


def test_predicate_positive_case():
    assert staging_verified("backend", VALID_SHA_A, [_record()]) is True


def test_predicate_wrong_family_does_not_verify():
    """A staging success for FRONTEND must not clear a BACKEND demo build.

    Mutation-verified: deleting the `record.get("target_family") ==
    target_family` clause from staging_verified() turns this red (returns
    True).
    """
    assert staging_verified(
        "backend", VALID_SHA_A, [_record(target_family="frontend")]
    ) is False


def test_predicate_wrong_sha_does_not_verify():
    """A staging success for a DIFFERENT commit must not clear this one.

    Mutation-verified: deleting the `record.get("sha") == sha` clause turns
    this red.
    """
    assert staging_verified(
        "backend", VALID_SHA_A, [_record(sha=VALID_SHA_B)]
    ) is False


def test_predicate_status_failure_does_not_verify():
    """A FAILED staging build for the exact sha does not count.

    Mutation-verified: dropping the `record.get("status") ==
    STATUS_SUCCESS` clause from staging_verified() (the mutation the bead
    body names explicitly) turns this red -- a failed staging record then
    satisfies the predicate, which is exactly the bypass this test exists
    to close.
    """
    assert staging_verified(
        "backend", VALID_SHA_A, [_record(status="failure")]
    ) is False


def test_predicate_no_recency_rule_older_verified_sha_still_verifies():
    """THE ROLLBACK CASE (bead body: 'no recency rule'). Staging has since
    moved on to a NEWER sha; the OLDER sha's own staging success record
    still stands and still verifies -- promoting that older, already-proven
    sha to the demo (a rollback) must remain allowed.

    Mutation-verified: adding a recency rule -- e.g. requiring the matched
    record to be the MOST RECENT staging record for the family (picking
    only the record with the highest ts, or outright rejecting a match
    when a later-sha staging record for the same family also exists) --
    turns this red: it flips the old-sha case to False, which is precisely
    the regression the plan's 'no recency rule' decision forbids.
    """
    records = [
        _record(sha="c" * 40),  # the older, already-verified sha
        _record(sha="d" * 40),  # staging has since moved on to a newer one
    ]
    assert staging_verified("backend", "c" * 40, records) is True


# --------------------------------------------------------------------------
# 3. THE CLI'S EXIT CODES (scripts/promotion_gate.py), stubbed Firestore.
#
# require_staging_verified() is imported straight off the admin_backend
# module's sibling CLI script rather than shelled out to (a real subprocess
# invocation of scripts/promotion_gate.py under a stubbed Firestore is
# exercised at a lower level by tests/test_cloudbuild_yaml.py's runtime
# simulation, which stubs the `python` binary itself; this test instead
# proves the CLI's OWN function returns the right exit code for each
# Firestore outcome without needing a real query).
# --------------------------------------------------------------------------
def test_cli_exits_zero_when_staging_verified(monkeypatch):
    monkeypatch.setattr(
        promotion_gate_cli, "_staging_deployments_for",
        lambda family, sha, project: [_record(sha=sha, target_family=family)],
    )
    assert promotion_gate_cli.require_staging_verified(
        "backend", VALID_SHA_A, None) == 0


def test_cli_exits_one_when_staging_not_verified(monkeypatch):
    """Mutation-verified: inverting require_staging_verified()'s `if
    staging_verified(...)` branch (returning 0 on the else arm too) turns
    this red.
    """
    monkeypatch.setattr(
        promotion_gate_cli, "_staging_deployments_for",
        lambda family, sha, project: [],
    )
    assert promotion_gate_cli.require_staging_verified(
        "backend", VALID_SHA_A, None) == 1


def test_cli_exits_one_fail_closed_when_the_query_itself_raises(monkeypatch):
    """An inconclusive Firestore read must REFUSE, not wave the deploy
    through -- module docstring's 'fails CLOSED' discipline.

    Mutation-verified: replacing the `except Exception: ... return 1` guard
    with a bare re-raise turns this red (the test would then need to catch
    an exception instead of getting a clean exit code -- the CLI, run for
    real inside a Cloud Build step, would crash the step with a traceback
    rather than a readable refusal, which the surrounding `set -euo
    pipefail` still fails the build on, but without the operator-readable
    message this module exists to print).
    """
    def _boom(family, sha, project):
        raise RuntimeError("firestore unavailable")

    monkeypatch.setattr(promotion_gate_cli, "_staging_deployments_for", _boom)
    assert promotion_gate_cli.require_staging_verified(
        "backend", VALID_SHA_A, None) == 1
