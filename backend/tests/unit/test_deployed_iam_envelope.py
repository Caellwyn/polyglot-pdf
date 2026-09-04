"""What the DEPLOYED service may ask Firebase for.

WHY THIS FILE EXISTS. Three bugs in one day reached the live app through a
green suite, green CI, nine review rounds and a cross-surface pass. The last
one -- check_revoked on the auth handshake -- broke EVERY connection with
INSUFFICIENT_PERMISSION, and no test could have caught it: every test stubs
the Firebase SDK, so the stub cheerfully answers a call the real service
account is forbidden to make.

THE STRUCTURAL GAP: a mock proves the code CALLS something. It cannot prove
the caller is ALLOWED to. Those are different questions, and only the second
was failing.

WHAT THIS CHECKS INSTEAD: the deployed service runs as polyglot-backend-sa,
whose roles are deliberately narrow (aiplatform.user, datastore.user,
logging.logWriter, secretmanager.secretAccessor, storage.objectViewer). None
grants firebaseauth.users.get, so any Firebase Auth call beyond verifying a
token's SIGNATURE fails in production, always, on the first request.

SCOPE. Everything under backend/ that ships -- routes, services, adapters,
utils, models, ports, and the module root -- derived by EXCLUSION, so a new
package is covered the day it appears. (The first version scanned routes and
services only; routes import adapters and utils transitively, so a privileged
call there was invisible to the guard written to catch exactly that.) The
scripts/ bootstrap tools are NOT in scope: they run under an operator's own
gcloud credentials, where these calls are correct and necessary.

Static on purpose -- no token, no deploy, no network -- so it runs in CI on
every change.
"""
import ast
import pathlib

# DERIVED from the installed SDK, not hand-listed. My first version named
# eight calls and missed twenty -- including generate_sign_in_with_email_link,
# the magic-link flow the maintainer says future users will arrive through.
# That is the same hand-list failure this repo has now hit four times.
#
# The rule is INVERTED: everything in firebase_admin.auth touches the Identity
# Toolkit API and needs an IAM permission, EXCEPT verifying a token, which is
# pure signature math against public keys. So allow-list the safe ones and
# treat the rest as privileged -- a new SDK function is covered the day it
# ships instead of the day someone remembers to add it.
_SIGNATURE_ONLY = {
    "verify_id_token",   # public-key signature check; no API call, no IAM
}


def _privileged_calls():
    """Every firebase_admin.auth callable that needs an IAM permission."""
    import firebase_admin.auth as fb_auth

    return {
        name for name in dir(fb_auth)
        if not name.startswith("_")
        and name[0].islower()
        and callable(getattr(fb_auth, name, None))
        and name not in _SIGNATURE_ONLY
    }


# EVERYTHING Cloud Run executes, not just where the bug happened to be. The
# first version scanned routes/ + services/ only -- but routes import adapters
# and utils transitively, so a privileged call added there would have been
# invisible to the very guard written to prevent it. No live instance today;
# the SCOPE hole was real.
#
# Derived by EXCLUSION (everything under backend/, minus what does not run in
# the service) rather than by listing what to include, so a NEW top-level
# package is covered the day it appears instead of silently skipped.
_NOT_DEPLOYED = {"tests", ".venv", "__pycache__", "docs", "logs", "scripts"}


def _deployed_sources():
    """Every .py file the Cloud Run service can execute."""
    root = pathlib.Path(__file__).resolve().parents[2]
    for f in sorted(root.rglob("*.py")):
        rel = f.relative_to(root)
        if any(part in _NOT_DEPLOYED for part in rel.parts):
            continue
        yield f, root


def _firebase_auth_aliases(tree):
    """Local names this file binds to the firebase_admin.auth MODULE itself
    (not a specific function -- see `_direct_privileged_imports` for that).

    Covers every import shape seen or plausible in this repo that puts a
    name on the auth module:
    - `from firebase_admin import auth [as X]` (backend/services/auth.py,
      and aliased in backend/services/editor_auth.py, imported
      function-local, not at module scope -- so this walks the WHOLE tree,
      not just its top level).
    - A bare `import firebase_admin.auth [as X]` -- unaliased, this is only
      reachable as the DOTTED path `firebase_admin.auth`, since Python gives
      no bare local name for an unaliased dotted import. That dotted string
      is registered as a possible alias, and `_call_receiver_name` resolves
      a matching dotted Attribute chain to the same string so it can match.
    - `import firebase_admin [as X]` -- this binds a name to the PACKAGE,
      not directly to `.auth`, so on its own it registers nothing here (see
      the note below on `firebase_admin` alone). But combined with a
      two-level access `<name>.auth.get_user(...)`, `_call_receiver_name`
      resolves the receiver to the dotted string `"<name>.auth"` --
      registering a package alias's `.auth` suffix (`pkg_alias + ".auth"`)
      here is what lets that match, covering both `import firebase_admin`
      (bare -> `firebase_admin.auth`) and `import firebase_admin as fb`
      (-> `fb.auth`).
    Never binds a PLAIN package alias (e.g. bare `firebase_admin` or `fb`)
    to this set by itself -- `firebase_admin.initialize_app()` etc. are not
    Identity Toolkit calls, so only the `.auth`-suffixed form is privileged.

    NOT COVERED, deliberately: a wildcard `from firebase_admin.auth import
    *`. Python gives no enumerable set of names a `*` import binds without
    executing the module (the AST node just says `alias.name == "*"`), so
    no static walk can resolve which bare names it introduces. This is a
    different kind of gap from the ones this function fixes -- not a
    missing case in an otherwise-closed enumeration, but a shape that is
    fundamentally opaque to static analysis, in the same family as the
    `getattr(auth, "get_user")(uid)` and cross-module re-export gaps ruled
    out of scope during review. No wildcard import of firebase_admin.auth
    exists anywhere in backend/ today (verified).

    ALSO NOT COVERED, deliberately, same family: re-aliasing an already-
    bound name via plain assignment, e.g. `fb2 = fb` then
    `fb2.auth.get_user(uid)`, or `gu = get_user` then `gu(uid)`. This
    function (and `_direct_privileged_imports`) only walks import
    STATEMENTS, not general assignment targets -- tracking a `Name = Name`
    chain soundly needs real data-flow / constant-propagation analysis
    (What does `fb2` alias transitively? Is it reassigned later? Is the
    original name shadowed first?), not a bare single-pass AST walk. Found
    during review round 4 as a real (if currently unused) gap in the same
    "old bare-name matcher caught it, new receiver-bound matcher does not"
    class as the wildcard-import case above -- ruled out of scope for the
    identical reason: closing it soundly is a different, larger kind of
    analysis than this file does anywhere else, not one more import shape
    to enumerate. No such re-aliasing of firebase_admin/auth exists
    anywhere in backend/ today (verified).

    KNOWN LIMITATION, deliberately accepted: this is FILE-WIDE, not
    scope-local. An alias imported inside one function is treated as bound
    for the whole file, so an unrelated variable of the SAME NAME in a
    different function (e.g. a parameter also called `fb_auth`) would be
    false-flagged if it happened to call a same-named privileged method.
    No such collision exists anywhere in backend/ today (verified). True
    scope-tracking would need a real symbol table, not a bare AST walk;
    given the guard's failure mode (false positive) is the safer direction
    to err in already, this residual gap is accepted rather than built out
    -- revisit only if a real collision ever appears.
    """
    aliases = set()
    package_aliases = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "firebase_admin":
            for alias in node.names:
                if alias.name == "auth":
                    aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "firebase_admin.auth":
                    aliases.add(alias.asname or alias.name)
                elif alias.name == "firebase_admin":
                    package_aliases.add(alias.asname or alias.name)
    for pkg_alias in package_aliases:
        aliases.add(pkg_alias + ".auth")
    return aliases


def _direct_privileged_imports(tree, privileged):
    """Local names bound DIRECTLY to a privileged firebase_admin.auth
    function, e.g. `from firebase_admin.auth import get_user` -> calling
    the bare name `get_user(uid)` needs no receiver at all, so the
    receiver-bound check in `_privileged_calls_in_tree` can never see it.
    Returns {local_name: real_sdk_name} so a rename via `as` is still
    correctly attributed to the real, privileged function it is."""
    direct = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "firebase_admin.auth":
            for alias in node.names:
                if alias.name in privileged:
                    direct[alias.asname or alias.name] = alias.name
    return direct


def _call_receiver_name(fn):
    """The Name this `fn.attr(...)` call resolves off, as a dotted string.

    `fb_auth.get_user(uid)` -> `fn` is `Attribute(value=Name('fb_auth'))` ->
    returns `'fb_auth'`. `firebase_admin.auth.get_user(uid)` -> `fn.value`
    is itself `Attribute(value=Name('firebase_admin'), attr='auth')` ->
    returns the dotted `'firebase_admin.auth'`. This same dotted-string
    resolution also covers `fb.auth.get_user(uid)` after `import
    firebase_admin as fb` (-> `'fb.auth'`) -- `_firebase_auth_aliases`
    registers the matching `pkg_alias + ".auth"` string for any name bound
    to the `firebase_admin` package itself, so any two-level `<alias>.auth`
    receiver this function resolves has a matching entry to compare
    against. Anything else (a chained `x().get_user(uid)`, a subscript, a
    receiver-less call) returns None and is never flagged -- under-covering
    an exotic access pattern is the safe direction for a guard whose
    failure mode (a false positive) trains people to delete it.
    """
    if not isinstance(fn, ast.Attribute):
        return None
    receiver = fn.value
    if isinstance(receiver, ast.Name):
        return receiver.id
    if isinstance(receiver, ast.Attribute) and isinstance(receiver.value, ast.Name):
        return "{}.{}".format(receiver.value.id, receiver.attr)
    return None


def _privileged_calls_in_tree(tree, privileged):
    """Every ast.Call node (+ the matched name) in `tree` that is a
    privileged firebase_admin.auth call, bound to a real auth alias --
    either an `X.method(...)` call where X resolves to the auth module, or
    a bare `method(...)` call where `method` was imported directly from
    firebase_admin.auth.

    The ONE matching rule this whole file relies on -- both the production
    guard below and the precision test's synthetic-source harness call this
    same function, so the rule cannot drift between two hand-duplicated
    copies (CLAUDE.md scar #7: two restatements of one rule silently
    diverge; one shared implementation cannot).

    Deliberately does NOT early-return when a file has no auth_aliases at
    all: doing so would let a false-positive fixture with NO
    firebase_admin.auth import pass regardless of whether the receiver
    check (this bead's actual fix) is even present, since the early-exit
    alone would mask a reverted receiver check. Letting the loop run
    unconditionally means the `in auth_aliases` clause is what's actually
    exercised by the precision test below.
    """
    auth_aliases = _firebase_auth_aliases(tree)
    direct_imports = _direct_privileged_imports(tree, privileged)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Attribute):
            name = fn.attr
            if name in privileged and _call_receiver_name(fn) in auth_aliases:
                yield node, name
        elif isinstance(fn, ast.Name) and fn.id in direct_imports:
            yield node, direct_imports[fn.id]


def test_the_deployed_service_makes_no_privileged_firebase_auth_call():
    """A privileged call here fails on the FIRST request in production."""
    privileged = _privileged_calls()
    offenders = []
    for f, root in _deployed_sources():
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node, name in _privileged_calls_in_tree(tree, privileged):
            offenders.append("{}:{} calls {}()".format(
                f.relative_to(root).as_posix(), node.lineno, name))

    assert not offenders, (
        "The deployed service makes Firebase Auth calls its service account "
        "cannot perform. Each fails with INSUFFICIENT_PERMISSION on the first "
        "request in production, and no mocked test will see it:"
        + chr(10) + "  " + (chr(10) + "  ").join(offenders)
        + chr(10) + chr(10)
        + "Either grant polyglot-backend-sa the IAM role (a deliberate "
          "widening the maintainer approves) or do not make the call.")


def test_verify_id_token_is_not_called_with_check_revoked():
    """The specific flag that took the app down, pinned by name.

    check_revoked turns a signature check into a USER-RECORD FETCH. It reads
    as a small hardening flag, which is why it survived review twice: the AST
    test above catches privileged METHOD calls, and this catches the KEYWORD
    that quietly becomes one.
    """
    offenders = []
    for f, root in _deployed_sources():
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if kw.arg == "check_revoked" and not (
                        isinstance(kw.value, ast.Constant)
                        and kw.value.value is False):
                    offenders.append("{}:{}".format(
                        f.relative_to(root).as_posix(), node.lineno))

    assert not offenders, (
        "check_revoked is set on a token verification in the deployed "
        "service. It needs firebaseauth.users.get, which polyglot-backend-sa "
        "does not have, so EVERY request will 403:"
        + chr(10) + "  " + (chr(10) + "  ").join(offenders))


def _offenders_in_source(source: str, privileged) -> list:
    """Run the SAME scan `_privileged_calls_in_tree` provides against a
    synthetic source string, standalone -- lets the precision test below
    exercise the exact matching rule the production guard uses, without
    writing a real deployed file."""
    tree = ast.parse(source)
    return [name for _, name in _privileged_calls_in_tree(tree, privileged)]


def test_privileged_call_guard_is_bound_to_the_firebase_auth_receiver():
    """bd polyglot-pdf-a5nfk: matching on the bare method name alone (no
    receiver check) false-positives on any unrelated object exposing a
    same-named method -- store.get_user(), a cache's list_users(), etc.
    Bind the check to an alias of firebase_admin.auth instead."""
    privileged = _privileged_calls()

    # An unrelated object exposing same-named methods must NOT be flagged --
    # this is the exact false-positive the bead reported, reproduced with no
    # firebase_admin.auth import in scope at all.
    assert _offenders_in_source(
        "store.get_user(uid)\n"
        "d.update_user(x)\n"
        "self._cache.list_users()\n",
        privileged,
    ) == []

    # The load-bearing case: a REAL firebase_admin.auth import IS present
    # (so auth_aliases is non-empty -- this is the shape backend/services/
    # auth.py actually has), alongside an UNRELATED same-named call on a
    # different receiver in the SAME source. Only the receiver check (not
    # merely "does this file import firebase_admin.auth at all") can tell
    # these apart -- a version of the guard that dropped the receiver check
    # but kept the auth_aliases early-exit would wrongly flag `store` here.
    assert _offenders_in_source(
        "from firebase_admin import auth\n"
        "auth.verify_id_token(token)\n"
        "store.get_user(uid)\n",
        privileged,
    ) == []

    # The real Firebase Auth call, reached via either import shape this repo
    # actually uses, MUST still be flagged.
    assert _offenders_in_source(
        "from firebase_admin import auth\n"
        "auth.get_user(uid)\n",
        privileged,
    ) == ["get_user"]
    assert _offenders_in_source(
        "from firebase_admin import auth as fb_auth\n"
        "fb_auth.get_user(uid)\n",
        privileged,
    ) == ["get_user"]

    # Two MORE call shapes the receiver-check refactor could plausibly have
    # narrowed away (and, in an earlier draft of this fix, silently did):
    # a bare, unaliased `import firebase_admin.auth` (the receiver is a
    # DOTTED Attribute chain, not a bare Name) and a name imported DIRECTLY
    # from firebase_admin.auth (the call has no receiver at all). Both are
    # real, if currently unused, import styles -- a guard whose whole
    # premise is "derived, not hand-listed, so nothing is missed" must not
    # narrow its own coverage silently when fixing an unrelated precision bug.
    assert _offenders_in_source(
        "import firebase_admin.auth\n"
        "firebase_admin.auth.get_user(uid)\n",
        privileged,
    ) == ["get_user"]
    assert _offenders_in_source(
        "from firebase_admin.auth import get_user\n"
        "get_user(uid)\n",
        privileged,
    ) == ["get_user"]
    # ...and the alias form of a direct import must attribute the REAL name.
    assert _offenders_in_source(
        "from firebase_admin.auth import get_user as fetch_user\n"
        "fetch_user(uid)\n",
        privileged,
    ) == ["get_user"]
    # A bare-name call to an unrelated function with NO firebase_admin.auth
    # import anywhere in scope must stay unflagged -- confirms the direct-
    # import coverage above didn't reintroduce the original bare-name bug.
    assert _offenders_in_source("get_user(uid)\n", privileged) == []

    # Two MORE shapes found in a second review round: a name bound to the
    # firebase_admin PACKAGE itself (aliased or bare), accessed two levels
    # deep as `<name>.auth.get_user(...)`. The receiver here is a nested
    # Attribute chain rooted at a package alias, not at `firebase_admin.auth`
    # directly -- a different registration path than the dotted-import case
    # above, and one the same earlier draft of this fix also missed.
    assert _offenders_in_source(
        "import firebase_admin as fb\n"
        "fb.auth.get_user(uid)\n",
        privileged,
    ) == ["get_user"]
    assert _offenders_in_source(
        "import firebase_admin\n"
        "firebase_admin.auth.get_user(uid)\n",
        privileged,
    ) == ["get_user"]
    # A bare `import firebase_admin` alone (no `.auth` access) must never
    # itself be treated as a privileged alias -- initialize_app() and other
    # package-level calls are not Identity Toolkit calls.
    assert _offenders_in_source(
        "import firebase_admin\n"
        "firebase_admin.initialize_app()\n",
        privileged,
    ) == []
    # The above alone does not prove the package alias is scoped to `.auth`
    # specifically -- `initialize_app` was never in `privileged`, so a
    # broken implementation that (wrongly) registered the BARE package
    # alias itself (not just its `.auth` suffix) would pass it too. This
    # assertion uses a PRIVILEGED-named method called directly on the
    # bare package alias, with no `.auth` in the chain at all, which that
    # exact bug WOULD wrongly flag -- found by review round 4.
    assert _offenders_in_source(
        "import firebase_admin as fb\n"
        "fb.get_user(uid)\n",
        privileged,
    ) == []


# --------------------------------------------------------------------------- #
# The scan root's own boundary (bd polyglot-pdf-pnoik)
#
# Everything above walks backend/ and derives scope by EXCLUSION, which covers a
# new package UNDER backend/ the day it appears. It does NOT cover a SIBLING
# top-level package: admin_backend/ holds all the privileged code and runs under
# the WIDE admin-backend-sa, and it is outside this file's root entirely.
#
# So the exclusion-derived scope silently rests on a second, unstated premise --
# that nothing under backend/ reaches privileged code by IMPORTING the sibling.
# A single `from admin_backend.services.user_admin import create_user` inside
# backend/ would put the privileged call site in a file this guard never opens,
# and the public service would make an Identity Toolkit call under the narrow
# polyglot-backend-sa: exactly the 2026-08-26 outage this file exists to prevent.
# Pin the premise rather than trusting it.
# --------------------------------------------------------------------------- #
_ADMIN_PACKAGE = "admin_backend"


def _reaches_admin_backend(module: str) -> bool:
    """One matching rule, shared by the guard and its precision test below.

    The dot is load-bearing: a hypothetical `admin_backend_shared` is a
    DIFFERENT package and must not be flagged.
    """
    return module == _ADMIN_PACKAGE or module.startswith(_ADMIN_PACKAGE + ".")


def _imported_modules(tree):
    """Every absolute module path this AST imports, in both statement shapes."""
    seen = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                seen.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            # level > 0 is a RELATIVE import: it resolves inside backend/ and
            # can never name the sibling package.
            if node.level:
                continue
            if node.module:
                seen.add(node.module)
                for alias in node.names:
                    if alias.name != "*":
                        seen.add("{}.{}".format(node.module, alias.name))
    return seen


def test_the_public_backend_never_imports_the_admin_package():
    """backend/ must not reach admin_backend/, in any import shape.

    This is the direction that DEFEATS the guard above: privileged code
    imported into the public service is privileged code running under the
    narrow service account, in a file no scan in this file ever reads.

    Shared logic flows the other way only -- admin_backend/ imports
    backend.services.* and backend.config (pinned from that side by
    admin_backend/tests/unit/test_admin_sa_iam_envelope.py).
    """
    offenders = []
    for f, root in _deployed_sources():
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for module in sorted(_imported_modules(tree)):
            if _reaches_admin_backend(module):
                offenders.append("{} imports {}".format(
                    f.relative_to(root).as_posix(), module))

    assert not offenders, (
        "backend/ imports the PRIVILEGED admin package:" + chr(10) + "  "
        + (chr(10) + "  ").join(sorted(offenders)) + chr(10) + chr(10)
        + "admin_backend/ runs under the WIDE admin-backend-sa and holds the "
          "privileged Firebase Auth calls. Importing it into the public "
          "service puts those calls under the NARROW polyglot-backend-sa, "
          "where they fail with INSUFFICIENT_PERMISSION on the first request "
          "-- and in a file this file's scan never opens. Move the shared part "
          "into backend/services/ and import THAT from both.")


def test_the_admin_import_guard_matches_both_import_statement_shapes():
    """The matching rule itself, against synthetic sources.

    Without this, a guard narrowed to one statement shape passes the test
    above purely because no backend file uses the other shape yet -- and the
    day one does, the guard is silently absent.
    """
    def hits(src):
        return {m for m in _imported_modules(ast.parse(src))
                if _reaches_admin_backend(m)}

    # Every shape that DOES reach the privileged package must be caught.
    assert hits("import admin_backend\n")
    assert hits("import admin_backend.services.user_admin\n")
    assert hits("from admin_backend import services\n")
    assert hits("from admin_backend.services.user_admin import create_user\n")

    # A package whose name merely STARTS with the same letters is a different
    # package -- a prefix test written without the dot would wrongly flag it.
    assert hits("import admin_backend_shared\n") == set()
    assert hits("from admin_backend_shared import x\n") == set()

    # The SANCTIONED direction and backend's own imports stay clean.
    assert hits("from backend.services import firms\n") == set()
    assert hits("from backend.config import get_settings\n") == set()

    # A RELATIVE import inside backend/ resolves within that package.
    assert hits("from . import services\n") == set()
    assert hits("from .services import auth\n") == set()


def test_the_admin_guard_actually_scans_the_public_backend():
    """The guard above is vacuous if _deployed_sources() yields nothing.

    A scan that finds no files passes every "no offenders" assertion. Pin that
    it reaches the public app module and skips the test tree, so a broken
    parents[] index or an over-eager exclusion fails HERE rather than turning
    the import guard into a no-op nobody notices.
    """
    scanned = {f.relative_to(root).as_posix() for f, root in _deployed_sources()}
    assert "main.py" in scanned, sorted(scanned)[:20]
    assert not any(part == "tests" for s in scanned for part in s.split("/")), (
        "the walk is picking up backend/tests/, which does not ship")
