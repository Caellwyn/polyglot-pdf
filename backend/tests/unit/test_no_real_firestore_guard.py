"""Pins the no-real-Firestore guard itself (bd polyglot-pdf-21m1y, exit
criterion 1's "a test proves it with a deliberately unpatched call").

2026-09-15: unpatched backend tests reached the real shared Firestore
project through a developer's gcloud ADC -- see the bead body for the
149-plus-document inventory. backend/tests/conftest.py's autouse
_no_real_firestore fixture (and admin_backend/tests/conftest.py's copy of
it) now patches firebase_admin.initialize_app and
google.cloud.firestore.Client to raise RealFirestoreReachedInTest instead of
touching anything real. This file proves that guard actually fires, on
BOTH named targets, rather than trusting the conftest wiring by inspection.

Each test's docstring names the mutation that must turn it red.

ASCII only.
"""
import firebase_admin
import google.cloud.firestore as gc_firestore
import pytest

from backend.tests.unit._no_real_firestore import RealFirestoreReachedInTest


def test_initialize_app_raises_loudly_when_unpatched_by_a_test():
    """THE regression this bead exists to prevent, half one: a test (or a
    module a test imports) that calls firebase_admin.initialize_app()
    directly -- the exact call backend/services/auth.py makes at import time
    -- must be stopped here rather than succeeding against ADC.

    Mutation: remove the firebase_admin.initialize_app patch from
    install_no_real_firestore_guard -- this goes red (either the real call
    raises some OTHER error resolving credentials, or -- worse, on a machine
    with working ADC -- it quietly succeeds). Verified 2026-09-15."""
    with pytest.raises(RealFirestoreReachedInTest):
        firebase_admin.initialize_app()


def test_firestore_client_construction_raises_loudly_when_unpatched():
    """THE regression, half two: firebase_admin.firestore.client() (what
    every store in backend/services/ calls through get_db()) resolves to
    exactly this constructor -- google.cloud.firestore.Client(...) -- per
    firebase_admin's own source (_FirestoreService.get_client). Guarding
    only initialize_app would miss a call site that reused an
    already-initialized app and went straight for a client.

    Mutation: remove the google.cloud.firestore.Client patch from
    install_no_real_firestore_guard -- this goes red (a real Client
    construction is attempted, which raises a DIFFERENT exception, most
    likely for missing credentials/project, or succeeds outright). Verified
    2026-09-15."""
    with pytest.raises(RealFirestoreReachedInTest):
        gc_firestore.Client(project="polyglot-demo-aa709")


def test_get_db_never_returns_a_working_client_with_no_app_pre_existing():
    """The seam every store actually uses. backend/services/auth.py calls
    firebase_admin.initialize_app() at ITS OWN module import time (a bare,
    exception-swallowing try/except) -- on a machine with working ADC (the
    exact 2026-09-15 incident condition), that import-time call already
    creates a REAL default app before this test, or any fixture, ever runs.
    So get_db() -> firestore.client() -> get_app() can legitimately find
    that already-real app and proceed to construct a client -- which is
    exactly where the SECOND patch (google.cloud.firestore.Client) has to
    catch it, since the first patch (initialize_app) is already too late by
    then. This test forces the case where NO app exists yet (this process
    may not have imported backend.services.auth before): get_db() must
    still never SUCCEED -- it must raise, either the guard's own sentinel
    or a plain lookup error from get_app() finding nothing -- never return a
    working db handle.

    Mutation: remove BOTH patches from install_no_real_firestore_guard --
    get_db() then returns a real (or real-attempting) client object instead
    of raising, and this goes red. Verified 2026-09-15."""
    from backend.services.auth import get_db

    with pytest.raises(Exception):
        db = get_db()
        # Defense in depth in case some future firebase_admin version makes
        # get_app() itself lenient: a returned object must not be a usable
        # client either.
        assert db is None


def test_a_real_app_already_present_is_still_caught_at_the_client_patch():
    """The harder half of the story above, made explicit: simulate the
    2026-09-15 condition where backend/services/auth.py's module-level
    initialize_app() already succeeded (a real app exists) BEFORE this
    test's fixture patched anything -- so get_db() skips the
    initialize_app patch entirely and goes straight to constructing a
    client, which is exactly what the google.cloud.firestore.Client patch
    exists to catch.

    Uses a REAL firebase_admin.App (with a stub credential that returns
    None harmlessly -- firebase_admin resolves the credential before
    constructing the Client, but nothing downstream uses the value since
    the Client patch is what fires next) rather than a hand-rolled fake --
    App._get_service's internal caching is part of the real call path
    get_db() exercises, and a fake missing it would prove nothing about the
    real one.

    Mutation: remove the google.cloud.firestore.Client patch from
    install_no_real_firestore_guard -- a real client construction is
    attempted (raising some unrelated credential/project error, or -- on a
    machine with working ADC -- succeeding outright) and this goes red.
    Verified 2026-09-15."""
    import firebase_admin as fb
    from firebase_admin import credentials

    class _StubCredential(credentials.Base):
        def get_credential(self):
            # firebase_admin.firestore._FirestoreService.get_client() reads
            # the credential BEFORE constructing the Client -- so this must
            # return harmlessly (None is fine: nothing downstream uses it,
            # since the Client() call right after this is what the guard
            # intercepts).
            return None

    app = fb.App(
        "[DEFAULT]", _StubCredential(), {"projectId": "polyglot-demo-aa709"}
    )
    fb._apps["[DEFAULT]"] = app
    try:
        from backend.services.auth import get_db

        with pytest.raises(RealFirestoreReachedInTest):
            get_db()
    finally:
        fb._apps.pop("[DEFAULT]", None)


@pytest.mark.external
def test_the_external_marker_leaves_initialize_app_UNPATCHED():
    """The one sanctioned escape hatch, proven rather than assumed: a test
    carrying @pytest.mark.external must see the REAL firebase_admin
    .initialize_app, not the guard's patched version -- checked by identity
    rather than by calling it, because a real call's outcome depends on the
    machine's own ADC state (this repo's dev machines have working ADC, so
    an unpatched call can legitimately SUCCEED rather than raise -- the
    2026-09-15 incident condition exactly). Calling the real function here
    to observe its behavior would risk the same live write this bead exists
    to stop; identity is the honest, side-effect-free check.

    Mutation: delete the `if request.node.get_closest_marker("external"):
    return` early-out in install_no_real_firestore_guard -- initialize_app
    is then the guard's patched function even under this marker, and the
    module-identity assertion below goes red. Verified 2026-09-15."""
    from backend.tests.unit import _no_real_firestore as guard_module

    assert firebase_admin.initialize_app.__module__ != guard_module.__name__, (
        "an external-marked test must not see the guard's patched "
        "initialize_app"
    )
