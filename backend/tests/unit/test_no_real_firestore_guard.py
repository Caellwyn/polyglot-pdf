"""Pins the no-real-Firestore guard itself (bd polyglot-pdf-21m1y, exit
criterion 1's "a test proves it with a deliberately unpatched call").

2026-09-15: unpatched backend tests reached the real shared Firestore
project through a developer's gcloud ADC -- see the bead body for the
149-plus-document inventory. backend/tests/conftest.py's autouse
_no_real_firestore fixture (and admin_backend/tests/conftest.py's copy of
it) now patches firebase_admin.initialize_app, google.cloud.firestore.Client,
and firebase_admin.firestore.client (the round-2 addition that closes the
warm-cache gap the first two targets miss) to raise
RealFirestoreReachedInTest instead of touching anything real. This file
proves that guard actually fires, on ALL THREE named targets, rather than
trusting the conftest wiring by inspection.

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
    of raising, and this goes red. Verified 2026-09-15.

    The `db is None` check runs AFTER pytest.raises, not inside it
    (bd polyglot-pdf-uyoi4): an AssertionError raised INSIDE that block is
    itself an Exception, so the old `with pytest.raises(Exception): db =
    get_db(); assert db is None` swallowed its own assertion failure and
    passed regardless of what get_db() returned -- a fully defeated guard
    that returns a real, truthy client made this test pass, not fail."""
    from backend.services.auth import get_db

    # No app exists yet in this test's process state, so a fully-defeated
    # guard resolves via get_app() -> ValueError (no default app) rather
    # than actually returning a client; a working guard raises its own
    # named sentinel first. Either is an acceptable "did not succeed"
    # outcome -- a return value never is, which is why the check below runs
    # unconditionally rather than inside the pytest.raises block.
    db = None
    try:
        db = get_db()
    except (RealFirestoreReachedInTest, ValueError):
        pass
    assert db is None, f"get_db() must never return successfully here; got {db!r}"


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


def test_get_db_is_still_caught_when_the_client_is_already_cached():
    """THE ROUND-2 GAP (bd polyglot-pdf-21m1y): a WARM firebase_admin client
    cache must be caught exactly like a cold one.

    firebase_admin's _FirestoreService caches clients on the App object
    (self._clients[database_id]) for the lifetime of the process. On a
    cache HIT, _FirestoreService.get_client returns the cached client
    WITHOUT ever calling google.cloud.firestore.Client(...) again -- so a
    guard that only patches that constructor never fires for a second (or
    later) call to firebase_admin.firestore.client() once anything, in this
    process, has warmed the cache. This is exactly backend/services/auth
    .py's own import-time initialize_app() + first get_db() call: the real
    incident condition.

    This test manufactures a warm cache directly (a real App plus a stub
    _FirestoreService with a pre-populated _clients dict standing in for
    "some earlier, unguarded call already built one") and proves get_db()
    still raises under the guard -- i.e. that the guard's protection does
    not depend on the constructor patch alone.

    Mutation: remove the `fa_firestore.client` patch from
    install_no_real_firestore_guard (keep the other two) -- this goes red:
    get_db() returns the cached fake "real" client object instead of
    raising, because _FirestoreService.get_client's cache-hit branch never
    reaches google.cloud.firestore.Client(). Verified 2026-09-15."""
    import firebase_admin as fb
    import firebase_admin.firestore as fa_firestore
    from firebase_admin import credentials

    class _StubCredential(credentials.Base):
        def get_credential(self):
            return None

    class _FakeCachedClient:
        """Stands in for a real google.cloud.firestore.Client that some
        earlier, unguarded call in this process already constructed and
        firebase_admin cached. If get_db() ever returns this object, the
        guard has been defeated by a warm cache -- the exact 2026-09-15
        failure mode."""

    class _WarmFirestoreService:
        def __init__(self, app):
            self._app = app
            self._clients = {"(default)": _FakeCachedClient()}

        def get_client(self, database_id):
            database_id = database_id or "(default)"
            return self._clients[database_id]

    app = fb.App(
        "[DEFAULT]", _StubCredential(), {"projectId": "polyglot-demo-aa709"}
    )
    fb._apps["[DEFAULT]"] = app
    # Pre-seed the App's service cache with a warm _FirestoreService, the
    # way a real process would have after any earlier get_db() call --
    # app._services stores instances keyed by the attribute name firestore
    # uses internally (fa_firestore._FIRESTORE_ATTRIBUTE).
    app._services[fa_firestore._FIRESTORE_ATTRIBUTE] = _WarmFirestoreService(app)
    try:
        from backend.services.auth import get_db

        with pytest.raises(RealFirestoreReachedInTest):
            db = get_db()
            assert not isinstance(db, _FakeCachedClient)
    finally:
        fb._apps.pop("[DEFAULT]", None)
