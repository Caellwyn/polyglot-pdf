"""A revoked link is refused at open, with the uniform 404 (bd
polyglot-pdf-jmiys, Epic 2 Track B bead B4's exit criterion 3, second half --
the atomicity half is pinned in admin_backend/tests/unit/
test_admin_link_routes.py::test_revoke_writes_status_and_one_audit_row_
atomically).

WHY THIS FILE EXISTS SEPARATELY FROM test_admin_link_routes.py. The bead is
explicit that this is "an integration test over the real open route" -- the
admin-service revoke route and the PUBLIC backend's open route are two
different FastAPI apps (admin_backend.main.app vs backend.main.app), so no
single TestClient can walk both. This file drives the REAL
backend.main.app's POST /api/links/open the same way
backend/tests/unit/test_link_routes.py and backend/tests/integration/
test_client_link_journey.py already do (mint a real token via
backend.services.link_tokens.mint_link_token, patch link_redemptions.
open_link with an in-memory fake, patch get_allowed_kits), and layers in
the ONE new fact this bead adds: a links[_<channel>]/{jti} mint record with
status=links_store.STATUS_REVOKED must make that jti's open attempt refuse,
with the SAME 404 body every other open refusal already uses (bd
polyglot-pdf-ugm6's "every failure returns the same 404" invariant).

STATUS AS OF THIS BEAD (2026-09-09), READ THIS BEFORE ASSUMING A FAILURE
HERE IS A BUG IN THIS FILE. Epic 2 Track A bead A3 (bd polyglot-pdf-jecrl,
plan: "Mint transaction" route half + "Open requires a mint record") is the
bead that wires backend/routes/link_routes.py's open_client_link to READ
links_store.get_link(jti, channel=...) and refuse when the record is
missing/revoked/refunded. bd polyglot-pdf-jecrl shows CLOSED in beads, but
its PR (#749, branch feat/jecrl-mint-reserve-open-gate) had NOT merged to
origin/dev as of this bead's own worktree creation -- confirmed by diffing
this bead's origin/dev checkout against that branch, which shows the whole
mint-reserve-then-sign + open-requires-a-mint-record change still absent
from backend/routes/link_routes.py here. B4's own surfaces list
(admin_backend/routes/link_routes.py, admin_backend/tests/unit/
test_admin_link_routes.py, backend/tests/integration/
test_revoked_link_open.py) does not include backend/routes/link_routes.py --
wiring that open-side check is A3's job, not B4's, and duplicating a partial
version of it here would fork the one gate the plan describes as living in
ONE place. So: THIS TEST PINS THE CONTRACT THE BEAD REQUIRES, written to
pass once A3's open-gate change reaches this branch (whether by a future
merge of dev into this branch, or by A3 landing on dev before this PR does)
-- it is not expected to be green against a `backend/routes/link_routes.py`
that predates A3. If it is red, check first whether A3 has landed in the
base this branch is compared against, and pull it in, before assuming the
revoke route (admin_backend/routes/link_routes.py, verified separately and
green in test_admin_link_routes.py) is the bug.

ASCII only.
"""
import time

import pytest
from fastapi.testclient import TestClient

import backend.routes.link_routes as lr
from backend.main import app
from backend.services.link_redemptions import LinkAlreadyUsed
from backend.services.link_tokens import mint_link_token
from backend.services import links_store

_SECRET = "r" * 40
_FIRM = "firm-a"
_KIT = "firm-a-intake"
_EMPLOYEE = "u-emp-7"


class _RedemptionStore:
    """The SAME minimal in-memory redemption fake test_client_link_journey.py
    and test_link_routes.py already use -- open_link/complete_link only,
    since this file's new behavior is entirely about the SEPARATE
    links_store mint record, not the redemption record's own logic."""

    def __init__(self):
        self.records = {}

    def open_link(self, jti, firm_id, kit_id, now=None):
        rec = self.records.get(jti)
        if rec is not None:
            if rec.get("completed_at"):
                raise LinkAlreadyUsed("already completed")
            return rec
        rec = {"jti": jti, "firm_id": firm_id, "kit_id": kit_id,
               "opened_at": int(now if now is not None else time.time()),
               "completed_at": None}
        self.records[jti] = rec
        return rec


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LINK_TOKEN_SECRET", _SECRET)
    monkeypatch.setenv("VFF_DISABLE_AUTH", "false")
    store = _RedemptionStore()
    monkeypatch.setattr("backend.services.link_redemptions.open_link",
                        store.open_link)
    # Patch the ROUTE MODULE'S own bound name -- backend/routes/link_routes.py
    # does `from backend.services.firms import get_allowed_kits`, so patching
    # backend.services.firms (or kit_gates, which imports it separately for
    # ITS OWN callers) leaves the route's own reference untouched.
    monkeypatch.setattr(lr, "get_allowed_kits", lambda firm_id: [_KIT])
    return TestClient(app), store


def _mint_token(jti):
    token, minted_jti = mint_link_token(
        firm_id=_FIRM, kit_id=_KIT, employee_id=_EMPLOYEE, jti=jti)
    assert minted_jti == jti
    return token


def _seed_mint_record(monkeypatch, jti, status, channel="demo"):
    """Stand in for links_store's real Firestore-backed get_link(): a real
    record dict keyed by jti, so this test proves the OPEN ROUTE reads
    links_store.get_link and reacts to STATUS_REVOKED specifically --
    rather than the store's own Firestore plumbing, which
    backend/tests/unit/test_links_store.py already covers.
    """
    records = {jti: {
        "jti": jti, "firm_id": _FIRM, "kit_id": _KIT,
        "employee_id": _EMPLOYEE, "credit_cost": 1, "cap_usd": 5.0,
        "minted_at": int(time.time()), "open_deadline": int(time.time()) + 3600,
        "status": status, "revoked_by": "admin-1" if
        status == links_store.STATUS_REVOKED else None,
        "revoked_at": int(time.time()) if
        status == links_store.STATUS_REVOKED else None,
    }}

    def _fake_get_link(requested_jti, channel=None):
        return records.get(requested_jti)

    monkeypatch.setattr(links_store, "get_link", _fake_get_link)
    return records


def test_a_revoked_link_is_refused_at_open_with_the_uniform_404(
        client, monkeypatch):
    """THE bead's exit criterion: a subsequent A3 open of a revoked jti is
    refused with the uniform 404 -- the SAME body every other open refusal
    in this route uses (bd polyglot-pdf-ugm6's indistinguishable-refusals
    invariant), not a distinct "revoked" message that would let an outside
    observer distinguish a revoked link from a merely-expired or
    never-existed one.
    """
    c, _store = client
    jti = "revoked-jti-1"
    token = _mint_token(jti)
    _seed_mint_record(monkeypatch, jti, links_store.STATUS_REVOKED)

    resp = c.post("/api/links/open", json={"token": token})

    assert resp.status_code == 404
    assert resp.json()["detail"] == "This link is not valid."


def test_a_minted_but_unrevoked_link_still_opens(client, monkeypatch):
    """The control case: a jti whose mint record is present and
    STATUS_MINTED opens normally -- proves the revoke check is not simply
    refusing every jti with a mint record, only revoked ones."""
    c, _store = client
    jti = "minted-jti-1"
    token = _mint_token(jti)
    _seed_mint_record(monkeypatch, jti, links_store.STATUS_MINTED)

    resp = c.post("/api/links/open", json={"token": token})

    assert resp.status_code == 200
    assert resp.json()["jti"] == jti
