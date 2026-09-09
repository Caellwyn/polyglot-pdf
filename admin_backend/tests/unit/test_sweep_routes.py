"""POST /admin/links/sweep-expired (bd polyglot-pdf-8vgfh).

Pins the bead's three exit criteria:

  1. test_expired_link_is_refunded_once_and_a_rerun_refunds_nothing --
     idempotency through A5's refund_expired_link, exercised via the real
     route rather than calling the ledger helper directly.
  2. test_right_audience_wrong_email_is_403_no_token_is_401 -- the two-
     factor OIDC gate: a token with the right audience but a different
     caller email is refused 403 (never 401 -- it verified fine, it is
     simply not the caller this route accepts), and no token at all is 401.
  3. (scripts/setup-admin-service.sh's own text -- see
     tests/test_setup_admin_service_scheduler.py, not this file.)

THE FAKE FIRESTORE mirrors backend/tests/unit/test_credit_refunds.py's
_FakeDb (tuple-path documents, a real all-or-nothing transaction, and a
`.where()`-filtered `.stream()` over a bare collection) -- this route's
Firestore surface is exactly that module's plus one more top-level
collection, admin_audit_log, so the two suites share the shape rather than
inventing a second one.

ASCII only.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import backend.services.credit_ledger as credit_ledger
import backend.services.link_redemptions as link_redemptions
import backend.services.links_store as links_store
from admin_backend.main import app
from admin_backend.routes import sweep_routes
from admin_backend.services import admin_auth, audit_log


# --------------------------------------------------------------------------
# The fake Firestore: identical shape to test_credit_refunds.py's _FakeDb.
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
        if transaction is not None:
            transaction.reads.append(self._path)
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
            actual = data.get(field)
            if op == "==":
                if actual != value:
                    return False
            elif op == "<":
                if actual is None or not (actual < value):
                    return False
            else:
                raise NotImplementedError(op)
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
        self.reads = []
        self.writes = []

    def set(self, ref, data, merge=False):
        if self._store.audit_write_error is not None and \
                ref._path[0] == audit_log.COLLECTION:
            raise self._store.audit_write_error
        self.writes.append(ref._path)
        self._buffer.append((ref._path, dict(data), merge))

    def commit(self):
        for path, data, merge in self._buffer:
            self._store.apply_set(path, data, merge)
        self._buffer = []

    def reset(self):
        self._buffer = []
        self.reads = []
        self.writes = []


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

    # test helpers --------------------------------------------------
    def firm(self, firm_id):
        return self.docs.get(("firms", firm_id))

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
    db = _FakeDb({("firms", "acme"): {
        "name": "Acme", "status": "active", "kind": "live",
        "balance_credits": 10,
    }})
    import firebase_admin
    monkeypatch.setattr(firebase_admin, "firestore", _FakeFirestoreModule(),
                        raising=False)
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)
    return db


def _mint(fake_db, jti="jti-1", firm_id="acme", channel="demo",
          status=links_store.STATUS_MINTED, open_deadline=500,
          credit_cost=2, kit_id="w7", **over):
    name = links_store._collection_name(channel)
    record = {
        "jti": jti, "firm_id": firm_id, "kit_id": kit_id,
        "employee_id": "emp-1", "credit_cost": credit_cost, "cap_usd": 5.0,
        "minted_at": 1, "open_deadline": open_deadline, "status": status,
        "revoked_by": None, "revoked_at": None, "expire_at": None,
    }
    record.update(over)
    fake_db.docs[(name, jti)] = record
    return record


def _redeem(fake_db, jti="jti-1", channel="demo", **over):
    name = link_redemptions._collection_name(channel)
    record = {"jti": jti, "firm_id": "acme", "kit_id": "w7",
              "opened_at": 1, "completed_at": None}
    record.update(over)
    fake_db.docs[(name, jti)] = record
    return record


# --------------------------------------------------------------------------
# A real OIDC-shaped caller, without touching google.auth's actual network
# call -- test_google_oidc_gate.py owns proving verify_oauth2_token itself
# is invoked correctly; these tests are about the ROUTE's behaviour once a
# claims dict comes back, so they monkeypatch the one seam admin_auth.py
# exposes for it (_verify_google_id_token).
# --------------------------------------------------------------------------

SCHEDULER_EMAIL = "scheduler-sa@test-project.iam.gserviceaccount.com"
# ADMIN_SERVICE_URL is the admin service's BARE Cloud Run URL (the SERVICE
# ROOT, matching every real caller of this env var -- deploy-admin.sh's own
# `gcloud run services describe ... status.url` output and scripts/setup-
# admin-service.sh's `--uri="$ADMIN_SERVICE_URL/admin/links/sweep-expired"`
# NOTE line). sweep_routes._audience() appends the route's own path to it
# (bd polyglot-pdf-8vgfh cross-surface review finding 2 -- setting this env
# var to the FULL path here, as an earlier version of this fixture did,
# silently masked exactly the audience-mismatch bug that finding caught:
# the shipped setup script's --oidc-token-audience is root+path, so a test
# that put the full path directly into ADMIN_SERVICE_URL was testing the
# wrong contract). AUDIENCE is the value _audience() actually produces once
# _sweep_oidc_gate resolves it -- what a real Cloud Scheduler token's `aud`
# claim must equal.
ADMIN_SERVICE_URL = "https://polyglot-admin-test.a.run.app"
AUDIENCE = ADMIN_SERVICE_URL + "/admin/links/sweep-expired"


@pytest.fixture
def scheduler_env(monkeypatch):
    """Configures the route's audience + allowlist env vars, and stubs the
    OIDC verification seam to return a claims dict for whatever bearer token
    the test sends -- 'valid-scheduler-token' resolves to the real
    scheduler identity, anything else raises ValueError (an invalid token),
    matching _verify_google_id_token's own contract."""
    monkeypatch.setenv("ADMIN_SERVICE_URL", ADMIN_SERVICE_URL)
    monkeypatch.setenv("SWEEP_SCHEDULER_SA_EMAIL", SCHEDULER_EMAIL)

    def _fake_verify(token, audience):
        if token == "valid-scheduler-token":
            return {"email": SCHEDULER_EMAIL, "email_verified": True,
                    "aud": audience}
        if token == "valid-other-caller-token":
            return {"email": "someone-else@other-project.iam.gserviceaccount.com",
                    "email_verified": True, "aud": audience}
        raise ValueError("invalid token: {}".format(token))

    monkeypatch.setattr(admin_auth, "_verify_google_id_token", _fake_verify)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _auth(token):
    return {"Authorization": "Bearer {}".format(token)} if token else {}


# --------------------------------------------------------------------------
# _audience() vs. scripts/setup-admin-service.sh's declared scheduler job
# (bd polyglot-pdf-8vgfh cross-surface review finding 2). The scheduler job
# is declared with --oidc-token-audience="$ADMIN_SERVICE_URL/admin/links/
# sweep-expired" (service root + path); ADMIN_SERVICE_URL on the admin
# service itself is set to the bare service root. _audience() must bridge
# that gap by appending the route's own path -- if it instead returned
# ADMIN_SERVICE_URL bare, every real scheduler-minted token's `aud` claim
# (root+path) would never match, and require_google_oidc would 401 the one
# caller it exists to admit.
# --------------------------------------------------------------------------

def test_audience_appends_the_route_path_to_the_bare_service_root(
        monkeypatch):
    """Mutation: change _audience() to `return os.getenv("ADMIN_SERVICE_URL",
    "")` (the bare root, no path appended) -- this goes red."""
    monkeypatch.setenv("ADMIN_SERVICE_URL", ADMIN_SERVICE_URL)
    assert sweep_routes._audience() == AUDIENCE


def test_audience_is_empty_when_admin_service_url_is_unset(monkeypatch):
    """An unconfigured deployment must resolve to an empty audience (which
    require_google_oidc fail-closes on, see test_route_refuses_with_503_
    when_unconfigured below) -- never a bare "/admin/links/sweep-expired"
    path, which is not a URL any real caller could present as `aud`."""
    monkeypatch.delenv("ADMIN_SERVICE_URL", raising=False)
    assert sweep_routes._audience() == ""


def test_audience_matches_the_setup_scripts_declared_oidc_token_audience():
    """Cross-checks _audience()'s composed shape against the ACTUAL text of
    scripts/setup-admin-service.sh's --oidc-token-audience flag, so a future
    edit to either side that reintroduces the root-vs-root+path mismatch
    (finding 2) is caught here rather than only in production. Mutation:
    change --oidc-token-audience in the script to just "$ADMIN_SERVICE_URL"
    (drop the path) -- this goes red."""
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parents[3]
    script = (repo_root / "scripts" / "setup-admin-service.sh").read_text(
        encoding="utf-8")
    # The script's echo statements carry backslash-escaped quotes and a
    # backslash-escaped "$" (they are printed inside a double-quoted `echo
    # -e "..."` shell string) -- unescape both before comparing against the
    # semantic flag value a copy-paste of the printed command would
    # actually run, same approach as tests/test_setup_admin_service_
    # scheduler.py's _job_create_block helper.
    unescaped = script.replace('\\"', '"').replace('\\$', '$')
    assert (
        '--oidc-token-audience="$ADMIN_SERVICE_URL'
        + sweep_routes._SWEEP_ROUTE_PATH + '"'
    ) in unescaped, (
        "scripts/setup-admin-service.sh's declared --oidc-token-audience "
        "must be $ADMIN_SERVICE_URL followed by sweep_routes._SWEEP_ROUTE_"
        "PATH ({!r}) -- exactly what _audience() computes from the bare "
        "ADMIN_SERVICE_URL env var set on the admin service. If either "
        "side changes without the other, the scheduler's real token "
        "audience stops matching what the route checks against.".format(
            sweep_routes._SWEEP_ROUTE_PATH))


# --------------------------------------------------------------------------
# Exit criterion 1: idempotent refund through the real route.
# --------------------------------------------------------------------------

def test_expired_link_is_refunded_once_and_a_rerun_refunds_nothing(
        client, fake_db, scheduler_env):
    """A minted link past its deadline is refunded once by the sweep; a
    re-run refunds nothing. Mutation: drop the `if link.get("status") !=
    STATUS_MINTED: raise` guard in credit_ledger.refund_expired_link (the
    function this route calls) -- the second sweep call would credit the
    firm again. Verified by reverting that guard and observing the second
    call's total_refunded go from 0 to 1."""
    _mint(fake_db, jti="jti-1", credit_cost=2, open_deadline=500)

    resp1 = client.post(
        "/admin/links/sweep-expired?channel=demo",
        headers=_auth("valid-scheduler-token"))
    assert resp1.status_code == 200, resp1.text
    body1 = resp1.json()
    assert body1["total_refunded"] == 1
    assert body1["total_skipped"] == 0
    assert fake_db.firm("acme")["balance_credits"] == 12
    assert fake_db.link("jti-1")["status"] == links_store.STATUS_REFUNDED

    resp2 = client.post(
        "/admin/links/sweep-expired?channel=demo",
        headers=_auth("valid-scheduler-token"))
    assert resp2.status_code == 200, resp2.text
    body2 = resp2.json()
    assert body2["total_refunded"] == 0
    assert fake_db.firm("acme")["balance_credits"] == 12, (
        "a re-run must not credit the firm a second time")


def test_a_race_landing_on_the_same_jti_twice_refunds_exactly_once(
        client, fake_db, scheduler_env):
    """THE GUARD THE QUERY-LEVEL RE-RUN TEST ABOVE CANNOT REACH. Once a link
    is refunded its status flips to `refunded`, so the sweep's OWN query
    (status == minted) never presents it to a second SWEEP PASS again --
    which means the previous test proves the query's own filtering works,
    but says nothing about whether credit_ledger.refund_expired_link's
    INTERNAL idempotency guard (the transaction re-reading links/{jti} and
    refusing anything but `minted`) still works once this route's
    extra_writes wiring is added on top of it. That is exactly the race two
    overlapping sweep invocations (or a sweep racing bead A5's lazy
    reconcile path) would hit: both read the query result while the record
    still says `minted`, and only ONE of their transactions may win.

    Modelled here by calling the exact per-link path sweep_routes._sweep_
    channel uses -- credit_ledger.refund_expired_link with the SAME extra_
    writes-shaped audit closure -- directly, twice in a row against the
    SAME jti (the second call's transaction re-reads the FIRST call's
    already-committed status=refunded, exactly as it would if a second
    process's query had returned the same jti moments earlier).

    Mutation: revert the `if link.get("status") != STATUS_MINTED: raise`
    guard in credit_ledger.refund_expired_link -- verified 2026-09-09 by
    reverting it and observing the balance go to 14 (double-credited)
    instead of staying at 12 after the second call."""
    _mint(fake_db, jti="jti-6", credit_cost=2, open_deadline=500)

    def _audit_write(tx, firm_snapshot):
        audit_log.record_in_transaction(
            tx, fake_db, actor_uid=sweep_routes.SWEEP_ACTOR,
            actor_email=None, action=sweep_routes.ACTION_EXPIRY_REFUND,
            target="links/jti-6", before={}, after={}, channel="demo",
            request_id=audit_log.new_request_id(),
        )

    first = credit_ledger.refund_expired_link(
        fake_db, "jti-6", actor=sweep_routes.SWEEP_ACTOR, channel="demo",
        now=1000.0, extra_writes=_audit_write)
    assert first["amount"] == 2
    assert fake_db.firm("acme")["balance_credits"] == 12

    with pytest.raises(credit_ledger.LinkNotRefundable) as exc:
        credit_ledger.refund_expired_link(
            fake_db, "jti-6", actor=sweep_routes.SWEEP_ACTOR, channel="demo",
            now=1000.0, extra_writes=_audit_write)
    assert exc.value.reason == "not_pending"
    assert fake_db.firm("acme")["balance_credits"] == 12, (
        "a second transaction racing on the same jti must credit the firm "
        "exactly once"
    )
    assert len(fake_db.audit_rows()) == 1, (
        "the refused second attempt must not write a second audit row "
        "either -- it never reaches the extra_writes call at all"
    )


def test_an_opened_link_past_its_deadline_is_never_refunded(
        client, fake_db, scheduler_env):
    """The redemption doc's mere existence refuses the refund, exactly like
    A5's own guarantee -- proven through the sweep route rather than only
    at the helper level, since this route is the sweep's whole reason to
    exist. Mutation: have the sweep call refund_expired_link with a
    channel that does not match the redemption doc's -- this test would
    then wrongly show a refund and go red for the right reason."""
    _mint(fake_db, jti="jti-2", credit_cost=2, open_deadline=500)
    _redeem(fake_db, jti="jti-2")

    resp = client.post(
        "/admin/links/sweep-expired?channel=demo",
        headers=_auth("valid-scheduler-token"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_refunded"] == 0
    assert body["total_skipped"] == 1
    assert fake_db.firm("acme")["balance_credits"] == 10
    assert fake_db.link("jti-2")["status"] == links_store.STATUS_MINTED


def test_sweep_with_no_channel_sweeps_every_known_channel(
        client, fake_db, scheduler_env):
    """Omitting ?channel= sweeps every channel in KNOWN_CHANNELS -- the
    hourly Scheduler job's own call shape. Mutation: hard-code the loop to
    only ever query "demo" -- the staging jti would never be found and this
    goes red."""
    _mint(fake_db, jti="jti-demo", channel="demo", open_deadline=500)
    _mint(fake_db, jti="jti-staging", channel="staging", open_deadline=500)

    resp = client.post(
        "/admin/links/sweep-expired", headers=_auth("valid-scheduler-token"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_refunded"] == 2
    channels_swept = {r["channel"] for r in body["results"]}
    assert channels_swept == set(sweep_routes.KNOWN_CHANNELS)


def test_unknown_channel_query_param_is_404(client, fake_db, scheduler_env):
    resp = client.post(
        "/admin/links/sweep-expired?channel=prod",
        headers=_auth("valid-scheduler-token"))
    assert resp.status_code == 404


# --------------------------------------------------------------------------
# Exit criterion 2: right audience wrong email is 403; no token is 401.
# --------------------------------------------------------------------------

def test_right_audience_wrong_email_is_403_no_token_is_401(
        client, fake_db, scheduler_env):
    """A token with the right audience but a different caller email is
    refused 403 (verified fine, just not the accepted caller); a request
    with no token at all is 401 (never verified anything). Mutation: swap
    the `is not True`/allowlist check's `raise HTTPException(403, ...)` for
    a 401 -- this test's first assertion goes red; swap the missing-token
    branch's 401 for 403 -- the second assertion goes red. Both directions
    verified 2026-09-09."""
    _mint(fake_db, jti="jti-3", open_deadline=500)

    wrong_caller = client.post(
        "/admin/links/sweep-expired?channel=demo",
        headers=_auth("valid-other-caller-token"))
    assert wrong_caller.status_code == 403, wrong_caller.text
    assert "NO_ADMIN_ACCESS:" in wrong_caller.json()["detail"]

    no_token = client.post("/admin/links/sweep-expired?channel=demo")
    assert no_token.status_code == 401, no_token.text

    # Neither refused call may have refunded anything.
    assert fake_db.firm("acme")["balance_credits"] == 10
    assert fake_db.link("jti-3")["status"] == links_store.STATUS_MINTED


def test_an_invalid_signature_token_is_401_not_403(
        client, fake_db, scheduler_env):
    """A token that fails verification OUTRIGHT (bad signature, expired,
    wrong audience) is 401, distinctly from the 403 a verified-but-
    disallowed caller gets. Mutation: catch ValueError and raise 403
    instead of 401 in require_google_oidc -- this goes red."""
    resp = client.post(
        "/admin/links/sweep-expired?channel=demo",
        headers=_auth("garbage-token"))
    assert resp.status_code == 401, resp.text


def test_route_refuses_with_503_when_unconfigured(client, fake_db):
    """No ADMIN_SERVICE_URL / SWEEP_SCHEDULER_SA_EMAIL set at all (the
    scheduler_env fixture is deliberately NOT used here) -- an unconfigured
    deployment must refuse every caller, never silently accept one against
    an empty audience or empty allowlist. Mutation: change the `not
    resolved_audience or not resolved_allowed_emails` guard in
    require_google_oidc to `and` -- an unconfigured deployment (both empty)
    would then fall through to token verification instead of 503ing."""
    resp = client.post(
        "/admin/links/sweep-expired?channel=demo",
        headers=_auth("anything"))
    assert resp.status_code == 503, resp.text


# --------------------------------------------------------------------------
# Audit coverage: the route's own extra_writes-joined audit row (Epic 2
# criterion 5).
# --------------------------------------------------------------------------

def test_a_committed_refund_writes_exactly_one_audit_row(
        client, fake_db, scheduler_env):
    """Every refund the sweep performs is audited (bead description).
    Mutation: drop the extra_writes=_audit_write argument from the
    refund_expired_link call in sweep_routes.py -- this goes red (zero
    rows)."""
    _mint(fake_db, jti="jti-4", open_deadline=500)

    resp = client.post(
        "/admin/links/sweep-expired?channel=demo",
        headers=_auth("valid-scheduler-token"))
    assert resp.status_code == 200, resp.text

    rows = fake_db.audit_rows()
    assert len(rows) == 1, "expected exactly one audit row, got {}".format(rows)
    row = rows[0]
    assert row["actor_uid"] == sweep_routes.SWEEP_ACTOR
    assert row["action"] == sweep_routes.ACTION_EXPIRY_REFUND
    assert row["channel"] == "demo"
    assert row["state"] == audit_log.STATE_COMMITTED
    assert audit_log.ROW_FIELDS <= set(row)


def test_a_forced_audit_failure_leaves_the_refund_uncommitted(
        client, fake_db, scheduler_env):
    """THE ATOMICITY PIN for the extra_writes-delegated shape of
    MUTATION_KIND_FIRESTORE (see test_admin_audit_coverage.py's module
    docstring): the audit row this route writes shares ONE transaction with
    A5's refund -- credit_ledger.refund_expired_link's own transaction,
    joined via extra_writes -- so a forced audit failure must leave the
    WHOLE refund uncommitted: no balance change, no ledger entry, and the
    links record still `minted` (not `refunded`). This is the
    extra_writes-delegated form's equivalent of test_config_routes.py's own
    forced-audit-failure pin.

    Mutation: move the extra_writes(tx, firm_snapshot) call in credit_
    ledger.refund_expired_link's _mark_refunded_and_extra OUTSIDE the
    transaction body (e.g. call it after _txn(db.transaction()) returns) --
    the refund would then commit even though this fixture's forced audit
    failure fires, and the balance/status assertions below would go red.
    Verified 2026-09-09 by moving that call after the transaction commits."""
    _mint(fake_db, jti="jti-5", credit_cost=2, open_deadline=500)
    fake_db.audit_write_error = RuntimeError("audit sink unavailable")

    resp = client.post(
        "/admin/links/sweep-expired?channel=demo",
        headers=_auth("valid-scheduler-token"))
    # The forced failure is swallowed by the sweep's per-link error handling
    # (a bad link must not abort the whole hourly pass) -- so the ROUTE
    # still returns 200, but with the link SKIPPED, not refunded.
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_refunded"] == 0
    assert body["total_skipped"] == 1

    assert fake_db.firm("acme")["balance_credits"] == 10, (
        "the balance must be unchanged when the joined audit write fails")
    assert fake_db.link("jti-5")["status"] == links_store.STATUS_MINTED, (
        "the links record must still read minted, not refunded, when the "
        "joined audit write fails -- otherwise the very next sweep pass "
        "would treat this link as already handled and never retry it")
    assert fake_db.audit_rows() == []
