"""POST /api/deploys/webhook (bd polyglot-pdf-tb3kp, Epic 4 bead 4.3).

Pins the bead's exit criterion 2:

  1. test_a_real_pubsub_push_envelope_upserts_a_console_triggered_build --
     driven with a REAL Pub/Sub push envelope fixture (base64-encoded JSON,
     the shape Pub/Sub itself sends), updating a PRE-EXISTING deployments
     row by build_id.
  2. test_a_bash_triggered_build_with_no_existing_row_is_created_external --
     the same envelope shape, but for a build_id with no console-triggered
     row -- creates one with triggered_by "external".
  3. test_every_cloud_build_status_maps -- every Build.Status value this
     module's map declares.
  4. test_a_repeated_message_is_idempotent -- same messageId (or just the
     same build payload) applied twice produces the identical document.
  5. test_wrong_audience_and_wrong_caller_email_are_refused -- the OIDC
     gate: right audience wrong email is 403; a token that fails
     verification outright is 401.
  6. test_a_malformed_message_is_400_not_500.
  7. test_a_status_update_writes_one_audit_row -- the webhook's own
     mutation audits (admin_audit_log), in-transaction, since this route
     is a Firestore mutation like any other.

THE FAKE FIRESTORE supports a real, all-or-nothing TRANSACTION (the webhook's
own _upsert_deployment is @firestore.transactional, matching firm_routes.py
and config_routes.py's shape) -- same design as test_sweep_routes.py's own
_FakeDb/_Transaction, extended with Query.stream(transaction=...) since this
route's existing-row lookup runs INSIDE the transaction.

ASCII only.
"""
from __future__ import annotations

import base64
import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from admin_backend.main import app
from admin_backend.routes import deploy_webhook
from admin_backend.services import admin_auth, audit_log


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
        return _Snap(self._path, self._store.docs.get(self._path))


class _Query:
    def __init__(self, store, path, clauses=(), limit_n=None):
        self._store = store
        self._path = path
        self._clauses = clauses
        self._limit_n = limit_n

    def where(self, field, op, value):
        assert op == "=="
        return _Query(self._store, self._path,
                      self._clauses + ((field, value),), self._limit_n)

    def limit(self, n):
        return _Query(self._store, self._path, self._clauses, n)

    def stream(self, transaction=None):
        rows = [
            (path, data) for path, data in self._store.docs.items()
            if path[:-1] == self._path
            and all(data.get(f) == v for f, v in self._clauses)
        ]
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


class _Transaction:
    def __init__(self, store):
        self._store = store
        self._buffer = []

    def set(self, ref, data, merge=False):
        self._buffer.append((ref._path, dict(data), merge, "set"))

    def update(self, ref, data):
        self._buffer.append((ref._path, dict(data), False, "update"))

    def commit(self):
        for path, data, merge, kind in self._buffer:
            if kind == "update":
                existing = self._store.docs.get(path, {})
                existing.update(data)
                self._store.docs[path] = existing
            elif merge and path in self._store.docs:
                self._store.docs[path].update(data)
            else:
                self._store.docs[path] = dict(data)
        self._buffer = []


class _FakeDb:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})
        self.auto_id_counter = 0

    def collection(self, name):
        return _Collection(self, (name,))

    def transaction(self):
        return _Transaction(self)

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


WEBHOOK_URL = "https://polyglot-admin-xyz.a.run.app/api/deploys/webhook"
PUSH_SA_EMAIL = "pubsub-push-sa@example.iam.gserviceaccount.com"
OTHER_EMAIL = "someone-else@example.iam.gserviceaccount.com"


def _push_envelope(build: dict) -> dict:
    """A REAL Pub/Sub push envelope shape (message.data base64-encoded
    JSON), matching what Cloud Build's notification actually sends."""
    raw = json.dumps(build).encode("utf-8")
    return {
        "message": {
            "data": base64.b64encode(raw).decode("ascii"),
            "messageId": "msg-1",
            "attributes": {},
        },
        "subscription": "projects/p/subscriptions/cloud-builds-webhook",
    }


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)
    import firebase_admin
    monkeypatch.setattr(firebase_admin, "firestore", _FakeFirestoreModule(),
                        raising=False)
    return db


@pytest.fixture
def webhook_env(monkeypatch):
    monkeypatch.setenv("ADMIN_SERVICE_URL",
                       "https://polyglot-admin-xyz.a.run.app")
    monkeypatch.setenv("PUBSUB_PUSH_SA_EMAIL", PUSH_SA_EMAIL)


def _authed(monkeypatch, *, email=PUSH_SA_EMAIL, email_verified=True):
    def _verify(token, audience):
        assert audience == WEBHOOK_URL
        return {"email": email, "email_verified": email_verified}
    monkeypatch.setattr(admin_auth, "_verify_google_id_token", _verify)


def test_a_real_pubsub_push_envelope_upserts_a_console_triggered_build(
        fake_db, webhook_env, monkeypatch):
    _authed(monkeypatch)
    fake_db.docs[("deployments", "console-row")] = {
        "target": "editor", "target_family": "editor", "channel": "demo",
        "sha": "a" * 40, "triggered_by": "op-1", "build_id": "build-99",
        "status": "queued", "log_url": None, "ts": 100,
    }
    build = {
        "id": "build-99", "status": "WORKING",
        "logUrl": "https://console.cloud.google.com/build-99",
        "substitutions": {"_TARGET": "editor", "_CHANNEL": "demo"},
    }
    with TestClient(app) as client:
        resp = client.post("/api/deploys/webhook", json=_push_envelope(build),
                           headers={"Authorization": "Bearer tok"})
    assert resp.status_code == 204, resp.text

    row = fake_db.docs[("deployments", "console-row")]
    assert row["status"] == "working"
    assert row["log_url"] == "https://console.cloud.google.com/build-99"
    # No SECOND row was created for a build_id that already had one.
    assert len([p for p in fake_db.docs if p[0] == "deployments"]) == 1


def test_a_bash_triggered_build_with_no_existing_row_is_created_external(
        fake_db, webhook_env, monkeypatch):
    _authed(monkeypatch)
    build = {
        "id": "build-bash-1", "status": "SUCCESS",
        "logUrl": "https://console.cloud.google.com/build-bash-1",
        # REAL Cloud Build shape: createTime/finishTime are RFC3339
        # strings (protobuf Timestamp's JSON mapping), never bare numbers
        # -- see deploy_webhook.py's _to_epoch() docstring.
        "createTime": "2026-09-15T10:00:00.500Z",
        "finishTime": "2026-09-15T10:10:00.600Z",
        "substitutions": {
            "_TARGET": "backend-staging", "_CHANNEL": "staging",
            "_SHA": "c" * 40,
        },
    }
    with TestClient(app) as client:
        resp = client.post("/api/deploys/webhook", json=_push_envelope(build),
                           headers={"Authorization": "Bearer tok"})
    assert resp.status_code == 204, resp.text

    rows = [v for k, v in fake_db.docs.items() if k[0] == "deployments"]
    assert len(rows) == 1
    row = rows[0]
    assert row["build_id"] == "build-bash-1"
    assert row["triggered_by"] == "external"
    assert row["target"] == "backend-staging"
    assert row["target_family"] == "backend"
    assert row["channel"] == "staging"
    assert row["sha"] == "c" * 40
    assert row["status"] == "success"
    # ts/finished_at must be the SAME float-epoch type deploy_routes.py's
    # own time.time() writes use -- an RFC3339 string stored verbatim
    # would sort wrong against a float "ts" in the same collection.
    assert isinstance(row["ts"], float)
    assert isinstance(row["finished_at"], float)
    assert row["ts"] == datetime(
        2026, 9, 15, 10, 0, 0, 500000, tzinfo=timezone.utc).timestamp()
    assert row["finished_at"] == datetime(
        2026, 9, 15, 10, 10, 0, 600000, tzinfo=timezone.utc).timestamp()


@pytest.mark.parametrize("raw_status,expected", [
    ("QUEUED", "queued"),
    ("WORKING", "working"),
    ("SUCCESS", "success"),
    ("FAILURE", "failure"),
    ("INTERNAL_ERROR", "failure"),
    ("TIMEOUT", "failure"),
    ("EXPIRED", "failure"),
    ("CANCELLED", "cancelled"),
])
def test_every_cloud_build_status_maps(
        fake_db, webhook_env, monkeypatch, raw_status, expected):
    _authed(monkeypatch)
    build = {
        "id": "build-status-{}".format(raw_status), "status": raw_status,
        "substitutions": {"_TARGET": "editor", "_CHANNEL": "demo"},
    }
    with TestClient(app) as client:
        resp = client.post("/api/deploys/webhook", json=_push_envelope(build),
                           headers={"Authorization": "Bearer tok"})
    assert resp.status_code == 204
    rows = [v for k, v in fake_db.docs.items() if k[0] == "deployments"]
    assert rows[0]["status"] == expected


def test_a_repeated_message_is_idempotent(fake_db, webhook_env, monkeypatch):
    _authed(monkeypatch)
    build = {
        "id": "build-repeat-1", "status": "SUCCESS",
        "logUrl": "https://x/build-repeat-1",
        "substitutions": {"_TARGET": "editor", "_CHANNEL": "demo"},
    }
    envelope = _push_envelope(build)
    with TestClient(app) as client:
        r1 = client.post("/api/deploys/webhook", json=envelope,
                         headers={"Authorization": "Bearer tok"})
        r2 = client.post("/api/deploys/webhook", json=envelope,
                         headers={"Authorization": "Bearer tok"})
    assert r1.status_code == 204
    assert r2.status_code == 204
    rows = [v for k, v in fake_db.docs.items() if k[0] == "deployments"]
    assert len(rows) == 1, "a repeated message must not create a second row"
    assert rows[0]["status"] == "success"


def test_out_of_order_working_after_success_does_not_regress_status(
        fake_db, webhook_env, monkeypatch):
    """Pub/Sub's push subscription carries no ordering key (fresh-eyes
    review of bd polyglot-pdf-tb3kp) -- a SUCCESS message can be followed by
    a stale WORKING message for the same build_id. The row must stay
    "success" with its finished_at intact; only log_url may still move."""
    _authed(monkeypatch)
    success_build = {
        "id": "build-reorder-1", "status": "SUCCESS",
        "logUrl": "https://x/build-reorder-1",
        "finishTime": "2026-09-15T11:00:00Z",
        "substitutions": {"_TARGET": "editor", "_CHANNEL": "demo"},
    }
    stale_working_build = {
        "id": "build-reorder-1", "status": "WORKING",
        "logUrl": "https://x/build-reorder-1",
        "substitutions": {"_TARGET": "editor", "_CHANNEL": "demo"},
    }
    with TestClient(app) as client:
        r1 = client.post(
            "/api/deploys/webhook", json=_push_envelope(success_build),
            headers={"Authorization": "Bearer tok"})
        r2 = client.post(
            "/api/deploys/webhook", json=_push_envelope(stale_working_build),
            headers={"Authorization": "Bearer tok"})
    assert r1.status_code == 204
    assert r2.status_code == 204

    rows = [v for k, v in fake_db.docs.items() if k[0] == "deployments"]
    assert len(rows) == 1, "the stale message must update, not duplicate"
    row = rows[0]
    assert row["status"] == "success", (
        "a stale WORKING message regressed a terminal SUCCESS status")
    assert row["finished_at"] == datetime(
        2026, 9, 15, 11, 0, 0, tzinfo=timezone.utc).timestamp(), (
        "a stale WORKING message cleared finished_at on a terminal row")


def test_a_second_terminal_status_still_applies_over_the_first(
        fake_db, webhook_env, monkeypatch):
    """The regression guard is one-directional: it drops a NON-terminal
    message arriving after a terminal one, but a second terminal message
    (e.g. Cloud Build's own FAILURE after a redelivered SUCCESS is not a
    real transition, but this pins that the guard does not ALSO block
    terminal-to-terminal writes, which is not the guarded case)."""
    _authed(monkeypatch)
    working_build = {
        "id": "build-reorder-2", "status": "WORKING",
        "substitutions": {"_TARGET": "editor", "_CHANNEL": "demo"},
    }
    success_build = {
        "id": "build-reorder-2", "status": "SUCCESS",
        "logUrl": "https://x/build-reorder-2",
        "finishTime": "2026-09-15T11:20:00Z",
        "substitutions": {"_TARGET": "editor", "_CHANNEL": "demo"},
    }
    with TestClient(app) as client:
        r1 = client.post(
            "/api/deploys/webhook", json=_push_envelope(working_build),
            headers={"Authorization": "Bearer tok"})
        r2 = client.post(
            "/api/deploys/webhook", json=_push_envelope(success_build),
            headers={"Authorization": "Bearer tok"})
    assert r1.status_code == 204
    assert r2.status_code == 204

    rows = [v for k, v in fake_db.docs.items() if k[0] == "deployments"]
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "success"
    assert row["finished_at"] == datetime(
        2026, 9, 15, 11, 20, 0, tzinfo=timezone.utc).timestamp()


def test_wrong_caller_email_is_403_no_token_is_401(
        fake_db, webhook_env, monkeypatch):
    build = {"id": "b1", "status": "SUCCESS", "substitutions": {}}
    envelope = _push_envelope(build)

    _authed(monkeypatch, email=OTHER_EMAIL)
    with TestClient(app) as client:
        resp = client.post("/api/deploys/webhook", json=envelope,
                           headers={"Authorization": "Bearer tok"})
    assert resp.status_code == 403

    with TestClient(app) as client:
        resp = client.post("/api/deploys/webhook", json=envelope)
    assert resp.status_code == 401


def test_wrong_audience_is_401(fake_db, webhook_env, monkeypatch):
    def _verify(token, audience):
        raise ValueError("audience mismatch")
    monkeypatch.setattr(admin_auth, "_verify_google_id_token", _verify)
    build = {"id": "b1", "status": "SUCCESS", "substitutions": {}}
    with TestClient(app) as client:
        resp = client.post("/api/deploys/webhook",
                           json=_push_envelope(build),
                           headers={"Authorization": "Bearer tok"})
    assert resp.status_code == 401


def test_a_malformed_message_is_400_not_500(fake_db, webhook_env,
                                             monkeypatch):
    _authed(monkeypatch)
    with TestClient(app) as client:
        resp = client.post(
            "/api/deploys/webhook", json={"not": "a real envelope"},
            headers={"Authorization": "Bearer tok"})
    assert resp.status_code == 400


def test_unconfigured_env_vars_refuse_with_503(fake_db, monkeypatch):
    # webhook_env fixture deliberately NOT used -- ADMIN_SERVICE_URL and
    # PUBSUB_PUSH_SA_EMAIL are both unset, so require_google_oidc's own
    # fail-CLOSED behavior (admin_auth.py's "an empty audience or empty
    # allowlist must never be read as allow it") must refuse with 503.
    monkeypatch.delenv("ADMIN_SERVICE_URL", raising=False)
    monkeypatch.delenv("PUBSUB_PUSH_SA_EMAIL", raising=False)
    build = {"id": "b1", "status": "SUCCESS", "substitutions": {}}
    with TestClient(app) as client:
        resp = client.post(
            "/api/deploys/webhook", json=_push_envelope(build),
            headers={"Authorization": "Bearer tok"})
    assert resp.status_code == 503


def test_a_status_update_writes_one_audit_row(fake_db, webhook_env,
                                              monkeypatch):
    _authed(monkeypatch)
    fake_db.docs[("deployments", "console-row")] = {
        "target": "editor", "target_family": "editor", "channel": "demo",
        "sha": "a" * 40, "triggered_by": "op-1", "build_id": "build-audit-1",
        "status": "queued", "log_url": None, "ts": 100,
    }
    build = {
        "id": "build-audit-1", "status": "SUCCESS",
        "substitutions": {"_TARGET": "editor", "_CHANNEL": "demo"},
    }
    with TestClient(app) as client:
        resp = client.post("/api/deploys/webhook", json=_push_envelope(build),
                           headers={"Authorization": "Bearer tok"})
    assert resp.status_code == 204, resp.text

    audit_rows = fake_db.audit_rows()
    assert len(audit_rows) == 1
    assert audit_rows[0]["state"] == audit_log.STATE_COMMITTED
    assert audit_rows[0]["actor_uid"] == deploy_webhook.WEBHOOK_ACTOR
    assert audit_rows[0]["action"] == deploy_webhook.ACTION_DEPLOY_STATUS_UPDATE
    assert audit_rows[0]["after"]["status"] == "success"


def test_a_forced_audit_failure_leaves_the_deployment_row_unchanged(
        fake_db, webhook_env, monkeypatch):
    """The atomicity half: a Firestore-write mutation whose audit write
    fails must leave the mutation itself uncommitted -- same discipline as
    test_credit_routes.py / test_config_routes.py's own forced-audit-failure
    pins."""
    _authed(monkeypatch)
    fake_db.docs[("deployments", "console-row")] = {
        "target": "editor", "target_family": "editor", "channel": "demo",
        "sha": "a" * 40, "triggered_by": "op-1", "build_id": "build-fail-1",
        "status": "queued", "log_url": None, "ts": 100,
    }

    def _boom(*a, **k):
        raise RuntimeError("audit write failed")
    monkeypatch.setattr(audit_log, "record_in_transaction", _boom)

    build = {
        "id": "build-fail-1", "status": "SUCCESS",
        "substitutions": {"_TARGET": "editor", "_CHANNEL": "demo"},
    }
    # raise_server_exceptions=False: the point being pinned is NOT the
    # status code an unhandled exception happens to surface as, it is that
    # the deployment row below never changed -- so the exception is allowed
    # to propagate to a 500 response rather than exploding the test itself.
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post("/api/deploys/webhook", json=_push_envelope(build),
                           headers={"Authorization": "Bearer tok"})
    assert resp.status_code == 500

    row = fake_db.docs[("deployments", "console-row")]
    assert row["status"] == "queued", (
        "a forced audit failure must leave the deployment row's status "
        "UNCHANGED -- the transaction must not have partially committed")


def test_a_console_triggered_build_going_terminal_writes_a_float_finished_at(
        fake_db, webhook_env, monkeypatch):
    """The UPDATE path (an existing console-triggered row, not the CREATE
    path test_a_bash_triggered_build_with_no_existing_row_is_created_external
    already covers) must also normalize Cloud Build's real RFC3339
    finishTime to the same float-epoch type deploy_routes.py's own
    time.time() writes use for "ts" -- round-3 fresh-eyes finding, bd
    polyglot-pdf-tb3kp / polyglot-pdf-xqejk. Mutation-verified: reverting
    _to_epoch()'s call at the finished_at write site back to
    `build.get("finishTime") or time.time()` makes this assertion fail
    with a str, not a float."""
    _authed(monkeypatch)
    fake_db.docs[("deployments", "console-row-2")] = {
        "target": "editor", "target_family": "editor", "channel": "demo",
        "sha": "a" * 40, "triggered_by": "op-1", "build_id": "build-100",
        "status": "queued", "log_url": None, "ts": 100.0,
        "finished_at": None,
    }
    build = {
        "id": "build-100", "status": "SUCCESS",
        "logUrl": "https://x/build-100",
        "finishTime": "2026-09-15T12:00:00.250Z",
        "substitutions": {"_TARGET": "editor", "_CHANNEL": "demo"},
    }
    with TestClient(app) as client:
        resp = client.post("/api/deploys/webhook", json=_push_envelope(build),
                           headers={"Authorization": "Bearer tok"})
    assert resp.status_code == 204, resp.text

    row = fake_db.docs[("deployments", "console-row-2")]
    assert isinstance(row["finished_at"], float), (
        "finished_at must be a float epoch like deploy_routes.py's ts, "
        "not the raw RFC3339 string Cloud Build sends")
    assert row["finished_at"] == datetime(
        2026, 9, 15, 12, 0, 0, 250000, tzinfo=timezone.utc).timestamp()


class TestToEpoch:
    """Direct unit coverage of deploy_webhook._to_epoch -- the helper the
    two tests above exercise end-to-end. These pin the parsing edge cases
    Cloud Build's real payload can hit that an end-to-end test would be
    slow and awkward to enumerate through the HTTP route."""

    def test_bare_number_passes_through_as_float(self):
        assert deploy_webhook._to_epoch(600) == 600.0
        assert deploy_webhook._to_epoch(600.5) == 600.5

    def test_rfc3339_with_z_suffix(self):
        got = deploy_webhook._to_epoch("2026-09-15T12:34:56Z")
        want = datetime(
            2026, 9, 15, 12, 34, 56, tzinfo=timezone.utc).timestamp()
        assert got == want

    def test_rfc3339_with_millisecond_fraction(self):
        got = deploy_webhook._to_epoch("2026-09-15T12:34:56.789Z")
        want = datetime(
            2026, 9, 15, 12, 34, 56, 789000, tzinfo=timezone.utc).timestamp()
        assert got == want

    def test_rfc3339_with_nanosecond_fraction(self):
        # Cloud Build's real protobuf Timestamp JSON mapping can carry up
        # to 9 fractional digits (nanoseconds); Python's datetime only
        # resolves to microseconds (6 digits), so this must truncate
        # rather than raise.
        got = deploy_webhook._to_epoch("2026-09-15T12:34:56.123456789Z")
        want = datetime(
            2026, 9, 15, 12, 34, 56, 123456, tzinfo=timezone.utc).timestamp()
        assert got == want

    def test_rfc3339_with_explicit_negative_offset(self):
        got = deploy_webhook._to_epoch("2026-09-15T12:34:56-05:00")
        want = datetime(
            2026, 9, 15, 17, 34, 56, tzinfo=timezone.utc).timestamp()
        assert got == want

    def test_none_falls_back_to_wall_clock(self, monkeypatch):
        monkeypatch.setattr(deploy_webhook.time, "time", lambda: 12345.0)
        assert deploy_webhook._to_epoch(None) == 12345.0

    def test_unparsable_string_falls_back_to_wall_clock(self, monkeypatch):
        monkeypatch.setattr(deploy_webhook.time, "time", lambda: 54321.0)
        assert deploy_webhook._to_epoch("not-a-timestamp") == 54321.0
