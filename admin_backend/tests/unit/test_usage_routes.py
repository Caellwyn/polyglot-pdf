"""GET /admin/firms/{firm_id}/usage, GET /admin/kits/{kit_id}/usage (bd
polyglot-pdf-mpebj, E3.11a).

Pins: the required month/channel validation, the doc-id resolution
matching usage_rollups.py's own convention (demo bare, other channels
suffixed), the explicit key allowlist, "missing rollup doc is an empty
reading, not a 404", and the firm route's manager-scoping (404 for another
firm, mirroring link_routes.py's own rule).

THE FAKE FIRESTORE is a minimal stand-in: no transactions needed (these are
plain reads), just .collection().document().get() and a nested
.collection("usage").document(month).get().

AUTH IS OVERRIDDEN VIA app.dependency_overrides, not a real Firebase token
-- mirrors test_kit_routes.py's / test_admin_link_routes.py's own pattern:
the gates themselves are pinned by test_admin_auth.py / test_composite_
gate.py / test_admin_route_auth.py; this file's job is the ROUTE behavior
once an actor of a given kind is resolved.

ASCII only.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from admin_backend.main import app
from admin_backend.routes import usage_routes
from admin_backend.services.admin_auth import (
    ACTOR_KIND_APP_ADMIN,
    ACTOR_KIND_FIRM_MANAGER,
    AdminActor,
    CompositeActor,
    require_app_admin,
    require_app_admin_or_owning_manager,
)


# --------------------------------------------------------------------------
# A minimal fake Firestore: {(collection, doc_id, ...): data}.
# --------------------------------------------------------------------------

class _Snap:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _DocRef:
    def __init__(self, store, path):
        self._store = store
        self._path = path

    def collection(self, name):
        return _Collection(self._store, self._path + (name,))

    def get(self):
        if self._store.read_error is not None:
            raise self._store.read_error
        return _Snap(self._store.docs.get(self._path))


class _Collection:
    def __init__(self, store, path):
        self._store = store
        self._path = path

    def document(self, doc_id):
        return _DocRef(self._store, self._path + (doc_id,))


class _FakeDb:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})
        self.read_error = None

    def collection(self, name):
        return _Collection(self, (name,))


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDb({("firms", "acme"): {"name": "Acme"}})
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)
    return db


ADMIN_ACTOR = CompositeActor(uid="admin-1", email="ops@example.com",
                             kind=ACTOR_KIND_APP_ADMIN)
MANAGER_ACTOR = CompositeActor(uid="mgr-1", email="ada@acme.example",
                               kind=ACTOR_KIND_FIRM_MANAGER, firm_id="acme")


def _client(composite_actor):
    """A TestClient acting as `composite_actor` on the firm-usage route
    (require_app_admin_or_owning_manager) and as a plain app admin on the
    kit-usage route (require_app_admin) -- mirrors test_admin_link_routes.py
    's own multi-gate override fixture."""
    app.dependency_overrides[require_app_admin_or_owning_manager] = \
        lambda: composite_actor
    app.dependency_overrides[require_app_admin] = \
        lambda: AdminActor(uid=composite_actor.uid,
                           email=composite_actor.email)
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


def _set_firm_usage(fake_db, firm_id, doc_id, data):
    fake_db.docs[("firms", firm_id, "usage", doc_id)] = data


def _set_kit_usage(fake_db, kit_id, doc_id, data):
    fake_db.docs[("kits", kit_id, "usage", doc_id)] = data


# --------------------------------------------------------------------------
# Doc-id resolution -- mirrors usage_rollups._month_key exactly.
# --------------------------------------------------------------------------

def test_rollup_doc_id_demo_is_bare_other_channels_are_suffixed():
    """Mutation: suffix every channel including demo -- red (a bare "demo"
    write from usage_rollups.py would never be found by this route)."""
    assert usage_routes._rollup_doc_id("2026-09", "demo") == "2026-09"
    assert usage_routes._rollup_doc_id(
        "2026-09", "staging") == "2026-09_staging"


# --------------------------------------------------------------------------
# Firm usage route.
# --------------------------------------------------------------------------

def test_firm_usage_returns_the_allowlisted_rollup_fields(
        admin_client, fake_db):
    _set_firm_usage(fake_db, "acme", "2026-09", {
        "connections_ended": 5, "sessions_completed": 4,
        "cost_usd_total": 1.25, "links_opened": 2, "links_completed": 1,
        "links_minted": 3,
        "by_kit": {"i-90": {"sessions": 4, "cost_usd": 1.25}},
        "by_employee": {"emp-1": {"sessions": 4, "cost_usd": 1.25,
                                   "links_minted": 3}},
        "by_language": {"zh-CN": {"sessions": 1, "cost_usd": 0.1}},
        "kind": "live", "channel": "demo",
        "extra_internal_field": "should never leak",
    })
    resp = admin_client.get(
        "/admin/firms/acme/usage?month=2026-09&channel=demo")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["firm_id"] == "acme"
    usage = body["usage"]
    assert usage["connections_ended"] == 5
    assert usage["sessions_completed"] == 4
    assert usage["cost_usd_total"] == 1.25
    assert usage["links_minted"] == 3
    assert usage["by_kit"] == {"i-90": {"sessions": 4, "cost_usd": 1.25}}
    assert usage["by_employee"] == {
        "emp-1": {"sessions": 4, "cost_usd": 1.25, "links_minted": 3}}
    assert usage["by_language"] == {"zh-CN": {"sessions": 1, "cost_usd": 0.1}}
    assert "extra_internal_field" not in usage


def test_firm_usage_links_minted_alone_is_a_real_reading_not_no_data(
        admin_client, fake_db):
    """bd polyglot-pdf-he3lt: a firm-month with ONLY a mint (no session, no
    open, no completion) still comes back with links_minted set and every
    other counter null -- the console's own "no data" predicate must treat
    this as real activity, not a missing doc. Mutation: drop links_minted
    from _FIRM_USAGE_KEYS -- red (the field silently vanishes from the
    response even though it was written)."""
    _set_firm_usage(fake_db, "acme", "2026-09", {"links_minted": 1})
    resp = admin_client.get(
        "/admin/firms/acme/usage?month=2026-09&channel=demo")
    assert resp.status_code == 200, resp.text
    usage = resp.json()["usage"]
    assert usage["links_minted"] == 1
    assert usage["connections_ended"] is None
    assert usage["links_opened"] is None


def test_firm_usage_missing_rollup_doc_is_an_empty_reading_not_404(
        admin_client, fake_db):
    """No usage doc for this month -- a quiet month, not an error.
    Mutation: 404 on a missing usage doc instead of returning an empty
    reading -- red."""
    resp = admin_client.get(
        "/admin/firms/acme/usage?month=2026-09&channel=demo")
    assert resp.status_code == 200, resp.text
    usage = resp.json()["usage"]
    assert usage["connections_ended"] is None
    assert usage["by_kit"] is None


def test_firm_usage_unknown_firm_is_404(admin_client, fake_db):
    resp = admin_client.get(
        "/admin/firms/ghost/usage?month=2026-09&channel=demo")
    assert resp.status_code == 404


@pytest.mark.parametrize("query", [
    "channel=demo",  # missing month
    "month=2026-09",  # missing channel
    "month=2026-9&channel=demo",  # unpadded month
    "month=2026-13&channel=demo",  # out-of-range month
    "month=2026-09&channel=prod",  # unknown channel
], ids=["no-month", "no-channel", "unpadded-month", "bad-month-13",
        "unknown-channel"])
def test_firm_usage_refuses_missing_or_malformed_params(
        admin_client, fake_db, query):
    resp = admin_client.get("/admin/firms/acme/usage?{}".format(query))
    assert resp.status_code == 422, resp.text


def test_firm_usage_reads_the_channel_suffixed_doc_for_staging(
        admin_client, fake_db):
    """Mutation: hard-code the demo doc-id shape for every channel -- this
    would read the WRONG (bare) doc and return an empty reading instead of
    the staging data seeded below -- red."""
    _set_firm_usage(fake_db, "acme", "2026-09_staging", {
        "connections_ended": 9,
    })
    resp = admin_client.get(
        "/admin/firms/acme/usage?month=2026-09&channel=staging")
    assert resp.status_code == 200, resp.text
    assert resp.json()["usage"]["connections_ended"] == 9


# --------------------------------------------------------------------------
# Manager scoping -- mirrors link_routes.py's own 404-not-403 rule.
# --------------------------------------------------------------------------

def test_a_manager_reads_their_own_firms_usage(manager_client, fake_db):
    resp = manager_client.get(
        "/admin/firms/acme/usage?month=2026-09&channel=demo")
    assert resp.status_code == 200, resp.text


def test_a_manager_cannot_read_another_firms_usage_and_gets_404_not_403(
        manager_client, fake_db):
    """Mutation: swap the 404 in _require_owning_firm for a 403 -- red (the
    whole point is that the status code must not reveal whether the OTHER
    firm exists)."""
    fake_db.docs[("firms", "other")] = {"name": "Other"}
    resp = manager_client.get(
        "/admin/firms/other/usage?month=2026-09&channel=demo")
    assert resp.status_code == 404, resp.text


# --------------------------------------------------------------------------
# Kit usage route.
# --------------------------------------------------------------------------

def test_kit_usage_returns_the_allowlisted_rollup_fields(
        admin_client, fake_db):
    _set_kit_usage(fake_db, "i-90", "2026-09", {
        "connections_ended": 3, "sessions_completed": 2,
        "cost_usd_total": 0.5, "links_minted": 2,
        "by_firm": {"acme": {"sessions": 2}},
        "kind": "live", "channel": "demo",
        "internal_only": "no",
    })
    resp = admin_client.get(
        "/admin/kits/i-90/usage?month=2026-09&channel=demo")
    assert resp.status_code == 200, resp.text
    usage = resp.json()["usage"]
    assert usage["connections_ended"] == 3
    assert usage["links_minted"] == 2
    assert usage["by_firm"] == {"acme": {"sessions": 2}}
    assert "internal_only" not in usage


def test_kit_usage_with_no_profile_doc_still_returns_a_reading(
        admin_client, fake_db):
    """A kit_id with no kits/{kit_id} profile doc at all still resolves --
    see get_kit_usage's own docstring for why this route does not 404 on
    that (unlike the firm route)."""
    resp = admin_client.get(
        "/admin/kits/no-such-kit/usage?month=2026-09&channel=demo")
    assert resp.status_code == 200, resp.text
    assert resp.json()["usage"]["connections_ended"] is None


def test_kit_usage_requires_month_and_channel(admin_client, fake_db):
    resp = admin_client.get("/admin/kits/i-90/usage?channel=demo")
    assert resp.status_code == 422
    resp = admin_client.get("/admin/kits/i-90/usage?month=2026-09")
    assert resp.status_code == 422
