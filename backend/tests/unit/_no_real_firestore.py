"""The no-real-Firestore guard, shared by backend/tests/conftest.py and
admin_backend/tests/conftest.py (bd polyglot-pdf-21m1y).

WHY THIS EXISTS. Every store in this family (backend/services/alerts.py,
usage_rollups.py, link_redemptions.py, links_store.py, credit_ledger.py)
lazily reaches Firestore through ONE seam: backend.services.auth.get_db(),
which calls firebase_admin.firestore.client(). That function (see
firebase_admin/firestore.py) resolves the default app -- INITIALIZING one
with ADC if backend/services/auth.py's bare, exception-swallowing
`firebase_admin.initialize_app()` (module import time) already didn't -- and
then constructs a REAL `google.cloud.firestore.Client(...)`. On a developer
machine with gcloud ADC and a quota project, that client is not a fake: it
is a live connection to whatever project the ambient credential resolves to.
2026-09-15: exactly this path wrote 149 alerts docs, a link_redemptions doc,
a firm usage rollup, and 19 orphaned links docs into the shared demo project
from unpatched local test runs -- see the bead body for the full inventory.

WHAT IS PATCHED, AND WHY BOTH. `firebase_admin.initialize_app` is patched so
a test that (deliberately or by omission) tries to stand up a fresh default
app during the test run is stopped at the point that would succeed against
ADC. `google.cloud.firestore.Client` -- the class `firebase_admin.firestore
.client()` actually instantiates (confirmed by reading firebase_admin's own
source: `_FirestoreService.get_client` calls `firestore.Client(credentials=
..., project=..., database=...)` where `firestore` there IS `google.cloud
.firestore`) -- is patched at the constructor so ANY path that reaches a real
client is caught, not just the one this repo's stores currently use. Patching
only get_db() would miss a test that imported google.cloud.firestore directly
or a future store that skipped the shared helper; patching both named targets
is what the bead asks for and is the belt-and-suspenders the incident earned.

WHAT THIS DOES NOT BREAK. Every existing store test patches ABOVE this seam
(backend.services.auth.get_db, or a module's own _get_db/_collection) with a
fake -- see backend/tests/unit/_fake_firestore.py and the per-module _FakeDb
classes in test_alerts_dedup.py / test_links_store.py / test_usage_rollups.py.
None of those tests ever calls firebase_admin.initialize_app or constructs a
google.cloud.firestore.Client, so the guard never fires for them: it can only
ever catch a test that skipped the fake and fell through to the real thing.
scripts/grant_credits.py's and scripts/bootstrap_firm.py's CLI tests stub
`firebase_admin._apps` non-empty specifically so `initialize_app` is never
called in the first place -- also untouched by this guard.

OPT OUT: @pytest.mark.external, the marker that already gates the two tests
requiring the real Gemini Live API (pytest.ini). A test that deliberately
needs the real ADC path (there are none today; this repo has no such test)
declares that marker and is exempted, exactly like Gemini access is.

ASCII only.
"""
from __future__ import annotations

import pytest

_GUARD_MESSAGE = (
    "tests must not reach a real Firestore -- patch the store (e.g. "
    "backend.services.auth.get_db, or the module's own _get_db/_collection) "
    "or mark the test external"
)


class RealFirestoreReachedInTest(RuntimeError):
    """Raised in place of a real firebase_admin/Firestore call from a test.

    A distinct subclass (rather than a bare RuntimeError) so a test that
    means to prove the guard fires can assert on the type, not a string
    that could coincidentally match some other failure.
    """


def install_no_real_firestore_guard(monkeypatch, request) -> None:
    """Patch the two named real-Firestore entry points to raise loudly.

    Call this from an autouse fixture in each testpath's own conftest.py
    (backend/tests/conftest.py, admin_backend/tests/conftest.py) -- NOT
    shared as a fixture itself, so each suite keeps owning its own guard the
    way the K_SERVICE isolation fixture already does (see this file's
    sibling docstrings): a fixture imported from one suite's tree into
    another's conftest would make the second suite's protection depend on
    the first suite continuing to exist at that import path.

    OPT OUT: @pytest.mark.external. Checked here, not registered as a
    second marker, so both conftest.py copies share one definition of what
    "the test may reach a real backend" means.
    """
    if request.node.get_closest_marker("external"):
        return

    def _raise_initialize_app(*_args, **_kwargs):
        raise RealFirestoreReachedInTest(
            "firebase_admin.initialize_app() called from a test -- "
            + _GUARD_MESSAGE
        )

    def _raise_firestore_client_init(*_args, **_kwargs):
        raise RealFirestoreReachedInTest(
            "google.cloud.firestore.Client() constructed from a test -- "
            + _GUARD_MESSAGE
        )

    import firebase_admin
    import google.cloud.firestore as gc_firestore

    monkeypatch.setattr(
        firebase_admin, "initialize_app", _raise_initialize_app
    )
    monkeypatch.setattr(
        gc_firestore.Client, "__init__", _raise_firestore_client_init
    )
