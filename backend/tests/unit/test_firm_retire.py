"""Firms retire their OWN private forms (bd polyglot-pdf-z6bk9).

MAINTAINER DECISION (2026-08-07): "A firm can retire its own proprietary
intake forms but not shared government ones." This is the firm tier's FIRST
write path -- everything before it was read + telemetry.

Three conditions authorize the write, and each is pinned separately because
each fails differently in production:
  1. firm_role == "manager" (the 02ye four-level model: employees send links
     and track status; they do not take forms out of service).
  2. owner_firm_id == the caller's firm. VISIBILITY IS NOT AUTHORIZATION --
     bd vccy lets a firm see and fill kits its allowlist names, including
     ones it does not own.
  3. visibility == "private". Never a shared/government form.

Every refusal is a 404, never a 403: a 403 confirms the kit exists to a firm
that cannot see it -- the existence leak the read gates exist to prevent
(exit criterion 2).

ASCII only.
"""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import backend.routes.form_kit_routes as fkr


_TOKENS = {
    "mgr-a": {"uid": "u1", "firm_id": "firm-a", "firm_role": "manager"},
    "emp-a": {"uid": "u2", "firm_id": "firm-a", "firm_role": "employee"},
    "mgr-b": {"uid": "u3", "firm_id": "firm-b", "firm_role": "manager"},
    "legacy": {"uid": "u4"},
}

# kit_id -> live metadata
_KITS = {
    "firm-a-intake": {
        "status": "complete", "visibility": "private", "owner_firm_id": "firm-a",
    },
    "firm-b-intake": {
        "status": "complete", "visibility": "private", "owner_firm_id": "firm-b",
    },
    # Shared/government: no owner, not private.
    "w7": {"status": "complete"},
    # ADVERSARIAL: a SHARED kit that nonetheless carries this firm as owner
    # (a mis-tagged onboard, or a government form a firm sponsored). The
    # ownership check passes here, so ONLY the visibility check can refuse
    # it -- without this row, deleting that check left all 12 tests green
    # and the government-form promise was unpinned (caught by mutation).
    "w7-mis-tagged": {"status": "complete", "owner_firm_id": "firm-a"},
    "firm-a-draft": {
        "status": "draft", "visibility": "private", "owner_firm_id": "firm-a",
    },
}


class _Store:
    allow_convention_fallback = False
    enforce_complete_on_public_reads = True

    def __init__(self):
        self.meta = {k: dict(v) for k, v in _KITS.items()}
        self.written = {}
        self.archived = []

    async def load_manifest(self, manifest_file="index.json"):
        return {"forms": [
            {"id": k, "label": k, "description": None,
             "schemaFile": "schema.json", "schemaPath": "/form-kits/" + k + "/schema.json",
             "pdfFile": "form.pdf", "pdfPath": "/form-kits/" + k + "/form.pdf",
             "visibility": "public", "ownerFirmId": None}
            for k in self.meta
        ]}

    async def load_metadata(self, kit_id):
        return self.meta.get(kit_id)

    async def load_schema(self, kit_id, schema_file="schema.json"):
        return {"form_metadata": {"edition_date": "01/2025"}, "fields": [{"id": "f"}]}

    async def load_archived_revision_or_none(self, kit_id, marker):
        return None

    async def put_archived_revision(self, kit_id, marker, schema, meta=None):
        self.archived.append((kit_id, marker))

    async def put_metadata(self, kit_id, meta):
        self.written[kit_id] = meta
        self.meta[kit_id] = meta


@pytest.fixture
def client(monkeypatch):
    store = _Store()

    def _verify(token):
        claims = _TOKENS.get(token)
        if claims is None:
            raise HTTPException(status_code=401, detail="bad token")
        return dict(claims)

    monkeypatch.setenv("VFF_DISABLE_AUTH", "false")
    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: store)
    monkeypatch.setattr("backend.services.auth.verify_token", _verify)
    app = FastAPI()
    app.include_router(fkr.router)
    return TestClient(app), store


def _retire(c, kit_id, token):
    return c.post("/api/form-kits/" + kit_id + "/retire",
                  headers={"Authorization": "Bearer " + token})


# --- exit criterion 1: a firm retires its own private form -------------------


def test_a_manager_retires_their_OWN_private_form(client):
    """The happy path: status flips to unpublished and the revision is
    ARCHIVED FIRST, so confirmation records naming it stay retrievable.
    Mutation: drop the _archive_published_revision call -- the archive
    assertion goes red."""
    c, store = client

    resp = _retire(c, "firm-a-intake", "mgr-a")

    assert resp.status_code == 200
    assert resp.json()["status"] == "unpublished"
    assert store.written["firm-a-intake"]["status"] == "unpublished"
    # Archived BEFORE the status flip -- the bytes only exist unaltered until
    # retirement (bd w3zw).
    assert [k for k, _m in store.archived] == ["firm-a-intake"]
    assert resp.json()["archived_marker"] is not None


def test_retiring_preserves_ownership_and_visibility(client):
    """Retirement is a STATUS change, not a delete and not an unshare: the
    kit stays private and stays owned, so the firm can still see its own
    history (bd qfyxr) and republish through the normal gate. Mutation:
    write a bare status-only dict instead of merging -- red."""
    c, store = client

    _retire(c, "firm-a-intake", "mgr-a")

    written = store.written["firm-a-intake"]
    assert written["owner_firm_id"] == "firm-a"
    assert written["visibility"] == "private"


# --- exit criterion 2: everything else is refused, as a 404 ------------------


@pytest.mark.parametrize(
    "kit_id, token, why",
    [
        ("firm-b-intake", "mgr-a", "another firm's private kit"),
        ("w7", "mgr-a", "a shared/government kit the firm can SEE and fill"),
        ("w7-mis-tagged", "mgr-a",
         "a SHARED kit tagged with this firm as owner -- only visibility refuses it"),
        ("firm-a-intake", "emp-a", "an EMPLOYEE of the owning firm"),
        ("firm-a-intake", "legacy", "an authed user with no firm claim"),
        ("firm-a-intake", "mgr-b", "a manager of a DIFFERENT firm"),
        ("no-such-kit", "mgr-a", "a kit that does not exist at all"),
    ],
    ids=["other-firms-kit", "government-kit", "government-kit-owned",
         "employee-role", "no-firm-claim", "other-firm-manager", "nonexistent"],
)
def test_every_unauthorized_retire_is_refused_as_404(client, kit_id, token, why):
    """The whole refusal matrix, and the refusal SHAPE.

    404 for all of them -- including a kit that plainly exists -- so the
    response cannot be used to probe which private kits other firms own.
    Mutations: drop the role check -> employee-role red; drop the ownership
    check -> other-firms-kit + other-firm-manager red; drop the visibility
    check -> government-kit red; return 403 -> all red.
    """
    c, store = client

    resp = _retire(c, kit_id, token)

    assert resp.status_code == 404, why
    assert store.written == {}, "an unauthorized call must write NOTHING"
    assert store.archived == []


def test_a_nonexistent_kit_and_another_firms_kit_are_INDISTINGUISHABLE(client):
    """Exit criterion 2's second half, stated as its own assertion: the two
    responses must not differ in status OR body, or the difference itself
    reveals that the other firm's kit exists. Mutation: give either refusal
    a distinct detail string -- red."""
    c, _store = client

    ghost = _retire(c, "no-such-kit", "mgr-a")
    other = _retire(c, "firm-b-intake", "mgr-a")

    assert ghost.status_code == other.status_code == 404
    assert ghost.json()["detail"].replace("no-such-kit", "X") == \
        other.json()["detail"].replace("firm-b-intake", "X")


def test_only_a_PUBLISHED_form_can_be_retired(client):
    """A draft is not live, so there is nothing to retire -- 409 (not 404):
    the caller IS authorized here, so the state is safe to tell them."""
    c, store = client

    resp = _retire(c, "firm-a-draft", "mgr-a")

    assert resp.status_code == 409
    assert store.written == {}


def test_retirement_is_NOT_a_delete(client):
    """Hard delete stays guarded and staff-only (bd 6x1j). This route must
    never remove anything -- it only writes metadata."""
    c, store = client

    _retire(c, "firm-a-intake", "mgr-a")

    assert "firm-a-intake" in store.meta, "the kit must still exist"
    assert store.meta["firm-a-intake"]["status"] == "unpublished"


# --- exit criterion 3: audited, with no client PII ---------------------------


def test_the_retirement_is_logged_with_the_acting_firm_and_no_client_pii(
    client, monkeypatch
):
    """Requirement 4: log who (firm_id) did what to which kit, keyed like the
    telemetry bead. The firm is our CUSTOMER, never a client -- and there is
    deliberately no client identifier to log. Mutation: drop firm_id from the
    log call -- red."""
    c, _store = client
    captured = {}

    def _fake_info(event, **kw):
        if event == "firm_retired_own_kit":
            captured.update(kw)

    monkeypatch.setattr(fkr._log, "info", _fake_info)

    _retire(c, "firm-a-intake", "mgr-a")

    assert captured.get("firm_id") == "firm-a"
    assert captured.get("kit_id") == "firm-a-intake"
    for banned in ("uid", "email", "user_id", "client_id", "value", "field_values"):
        assert banned not in captured, banned + " must never ride an audit line"
