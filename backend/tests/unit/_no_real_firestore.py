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

WHAT IS PATCHED, AND WHY THREE TARGETS (gap fix, 2026-09-15). Originally
this patched only two targets: `firebase_admin.initialize_app` (so a test
that tries to stand up a fresh default app during the run is stopped before
ADC succeeds) and `google.cloud.firestore.Client` (the class
`firebase_admin.firestore.client()` instantiates on a CACHE MISS -- see
`_FirestoreService.get_client` below). THAT WAS NOT ENOUGH: firebase_admin
caches clients on the App object (`_FirestoreService._clients`, keyed by
database_id) for the lifetime of the process, across every test. backend/
services/auth.py:15-19 runs a bare `initialize_app()` at IMPORT time --
before any fixture, so before this guard is ever installed -- and on a
machine with working ADC that creates a real default app. The FIRST call to
get_db() anywhere in the process then constructs and caches a real client;
EVERY LATER call, guarded test or not, is a cache hit that returns that same
real client WITHOUT ever calling `firestore.Client(...)` again -- so the
constructor patch never fires for it. Reproduced in isolation (bd
polyglot-pdf-21m1y round 2): a single unguarded `get_db()` call anywhere in
the process silently poisons every later guarded test's protection, with no
@external marker involved.

The fix is a THIRD patch: `firebase_admin.firestore.client` itself -- the
one function every consumer in this repo actually calls (get_db() calls
exactly this, nothing else; confirmed nothing else calls
`google.cloud.firestore.Client` directly in backend/ or admin_backend/) --
is patched to always raise, unconditionally, before either the App-service
cache lookup or the `_clients` dict lookup inside it ever runs. Patching the
function is what makes a cache hit and a cache miss equally caught: there is
no code path to a real client that does not go through this name first. The
initialize_app and Client-constructor patches stay as belt-and-suspenders
for a test that imports `google.cloud.firestore` directly or a future store
that skips `firebase_admin.firestore.client` and open-codes a Client -- but
the `firebase_admin.firestore.client` patch is the one that actually closes
the incident's hole, because it does not depend on cache state at all.

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
    """Patch the three named real-Firestore entry points to raise loudly.

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

    def _raise_firebase_admin_firestore_client(*_args, **_kwargs):
        raise RealFirestoreReachedInTest(
            "firebase_admin.firestore.client() called from a test -- "
            + _GUARD_MESSAGE
        )

    import firebase_admin
    import firebase_admin.firestore as fa_firestore
    import google.cloud.firestore as gc_firestore

    monkeypatch.setattr(
        firebase_admin, "initialize_app", _raise_initialize_app
    )
    monkeypatch.setattr(
        gc_firestore.Client, "__init__", _raise_firestore_client_init
    )
    # THE FIX FOR THE WARM-CACHE GAP (bd polyglot-pdf-21m1y, round 2). The
    # Client-constructor patch above only fires on a CACHE MISS inside
    # firebase_admin's _FirestoreService -- once any code in this process
    # (e.g. backend/services/auth.py's import-time initialize_app + first
    # get_db() call) has populated that cache with a real client, every
    # later call to firebase_admin.firestore.client() -- guarded test or
    # not -- returns the same real, live client without ever reaching the
    # Client constructor again. Patching the client() FUNCTION ITSELF closes
    # that: it is the one seam every consumer in this repo actually calls
    # (get_db() -> firestore.client(), nothing else), and it sits ahead of
    # both the App-service cache lookup and the _clients dict lookup inside
    # it, so a cache hit is caught exactly as reliably as a cache miss.
    monkeypatch.setattr(
        fa_firestore, "client", _raise_firebase_admin_firestore_client
    )
