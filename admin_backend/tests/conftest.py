"""Shared pytest setup for the admin service's suite (bd polyglot-pdf-pnoik).

This is one of pytest.ini's three testpaths (backend/tests and tests/ are
the others). tests/conftest.py carries the K_SERVICE-strip guard (see "WHY
THIS FILE EXISTS" below) but NOT the _no_real_firestore guard further down
in this file -- tests/ has no Firestore-store-exercising tests today, only
shell-script text-parsing tests, so it was not wired in when this guard was
added (bd polyglot-pdf-21m1y; see docs/standards/testing.md's "No real
Firestore" section, which correctly names only backend/tests/conftest.py
and this file). A future test under tests/ that exercises a real store
(alerts.py, links_store.py, etc.) unpatched would reach real Firestore with
no guard catching it -- wire tests/conftest.py the same way this file's
_no_real_firestore fixture does, below, if that ever changes.

WHY THIS FILE EXISTS. admin_backend/main.py builds its CORS middleware at
MODULE scope, which calls backend.config.get_settings(); backend/config.py
fails closed when K_SERVICE is set (a deployed-service identity) alongside
VFF_DISABLE_AUTH=true. So an ambient K_SERVICE in the operator's shell aborts
this suite at COLLECTION with a pydantic ValidationError -- reproduced:

    K_SERVICE=x VFF_DISABLE_AUTH=true pytest admin_backend/tests/unit -q --co
    -> "Interrupted: 1 error during collection"

A per-test fixture runs far too late for that: collection imports the test
module, which imports admin_backend.main, before any fixture exists. Only a
module-level pop at conftest IMPORT time is early enough, which is exactly why
backend/tests/conftest.py and tests/conftest.py both do the same thing.

Without this file the suite was protected only INCIDENTALLY: a bare `pytest`
happens to import backend/tests/conftest.py first, and that sibling's pop
cleans the environment for everyone. That made this suite's collection depend
on another suite being collected alongside it -- so the narrow per-suite
invocation that docs/standards/testing.md itself prescribes broke, and the
protection would vanish the moment the suites were ever run separately.
Each testpath root owns its own guard so none of them relies on a sibling.
"""
import os

import pytest

from backend.tests.unit._no_real_firestore import (
    install_no_real_firestore_guard,
)

os.environ.pop("K_SERVICE", None)


@pytest.fixture(autouse=True)
def _isolate_k_service(monkeypatch):
    """Defense-in-depth for TEST-TIME Settings() construction.

    The module-level pop above closes the COLLECTION-time hole. This closes
    the rarer case where something re-sets K_SERVICE mid-session outside a
    test's own monkeypatch. A test that deliberately exercises the deployed
    path still works: its own monkeypatch.setenv layers over (and wins
    against) this delenv.
    """
    monkeypatch.delenv("K_SERVICE", raising=False)


@pytest.fixture(autouse=True)
def _no_real_firestore(monkeypatch, request):
    """Fail loudly on any unpatched real-Firestore reach (bd polyglot-pdf-21m1y).

    Shares its implementation with backend/tests/conftest.py's fixture of the
    same name -- see backend/tests/unit/_no_real_firestore.py for what is
    patched and why. Imported rather than reimplemented because admin_backend
    already imports backend.services.* for shared logic (this repo's own
    architecture doc: admin_backend is a sibling package built ON backend, not
    a duplicate of it) -- a second copy of this guard would be exactly the
    kind of set CLAUDE.md scar #8 warns against fixing once and then finding
    again piecemeal.

    OPT OUT: @pytest.mark.external, same marker used across the whole repo.
    """
    install_no_real_firestore_guard(monkeypatch, request)

# Sprint 23 PF-5 (bd o2fub): the backend's per-address limiter is OFF for the
# suite (TestClient is one address). Set here too, not only in
# backend/tests/conftest.py, so this suite never depends on a sibling
# having been collected first (the incidental-ordering hazard this file's
# own docstring describes).
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
