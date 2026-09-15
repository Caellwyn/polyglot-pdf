"""scripts/purge_test_artifacts.py CLI contract (bd polyglot-pdf-21m1y, exit
criterion 2).

EXIT CRITERION 2: --dry-run lists EXACTLY the enumerated shapes and nothing
else, and --apply deletes only those. Pins:

- alerts docs matched by firm_id in {firm-a, acme} OR doc id
  link_exhausted_jti-a; an unrelated alert (different firm_id, different id)
  is never listed;
- link_redemptions and links docs (bare + every channel-suffixed variant)
  whose firm_id is missing or firm-a; a doc with a DIFFERENT real firm_id is
  never listed;
- firms/firm-a plus every one of its subcollections' documents, enumerated
  dynamically rather than off a hardcoded subcollection list;
- --dry-run performs the same read-only matching pass as --apply (so the two
  paths cannot drift) and calls .delete() on nothing;
- --apply deletes exactly the matched set and nothing else;
- a mismatched or dead --project aborts with exit 2 before any read;
- a delete failure is reported and does not abort the rest of the sweep.

The CLI is driven as main([...]) -- purge_test_artifacts.main takes argv,
matching bootstrap_firm.py/grant_credits.py, so no module-reload/argv-
monkeypatch fixture is needed.

A hand-rolled fake Firestore (not the shared _fake_firestore.py transaction
fake in backend/tests/unit/, which models transactional buffer-and-retry
semantics this script never uses) -- this script only streams collections,
reads one doc, enumerates subcollections, and deletes refs.

Each test's docstring names the mutation that must turn it red.

ASCII only.
"""
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.purge_test_artifacts as purge  # noqa: E402

PROJECT = "polyglot-demo-aa709"


class _FakeApp:
    def __init__(self, project_id):
        self.project_id = project_id


@pytest.fixture
def firebase_stub(monkeypatch):
    """Pretend firebase_admin is already initialized for PROJECT.

    Same shape as test_grant_credits_cli.py's fixture of the same name:
    patching _apps non-empty keeps main() from calling the real
    initialize_app; get_app returns an object whose project_id the script
    asserts against --project.
    """
    import firebase_admin
    monkeypatch.setattr(firebase_admin, "_apps", {"[DEFAULT]": object()},
                        raising=False)
    monkeypatch.setattr(firebase_admin, "get_app",
                        lambda: _FakeApp(PROJECT), raising=False)
    return firebase_admin


# --------------------------------------------------------- the fake store


class _FakeSnap:
    def __init__(self, doc_id, data, ref):
        self.id = doc_id
        self._data = data
        self.reference = ref
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _FakeDocRef:
    def __init__(self, store, path):
        self._store = store
        self._path = path
        self.id = path[-1]
        self.path = "/".join(path)

    def get(self):
        data = self._store.docs.get(self._path)
        return _FakeSnap(self._path[-1], data, self)

    def collection(self, name):
        return _FakeCollection(self._store, self._path + (name,))

    def collections(self):
        """Every subcollection actually populated under this doc,
        discovered from the store's own doc paths -- mirrors Firestore's
        real collections() call, which lists what EXISTS rather than a
        caller-declared schema."""
        seen = []
        prefix = self._path
        for path in self._store.docs:
            if len(path) > len(prefix) + 1 and path[:len(prefix)] == prefix:
                subcoll_name = path[len(prefix)]
                if subcoll_name not in seen:
                    seen.append(subcoll_name)
        return [_FakeCollection(self._store, prefix + (name,))
                for name in seen]

    def delete(self):
        self._store.deleted.append(self._path)
        self._store.docs.pop(self._path, None)


class _FakeCollection:
    def __init__(self, store, path):
        self._store = store
        self._path = path
        self.id = path[-1]

    def document(self, doc_id):
        return _FakeDocRef(self._store, self._path + (doc_id,))

    def stream(self):
        prefix = self._path
        for path, data in list(self._store.docs.items()):
            if len(path) == len(prefix) + 1 and path[:len(prefix)] == prefix:
                yield _FakeSnap(
                    path[-1], data, _FakeDocRef(self._store, path)
                )


class _FakeDb:
    def __init__(self, docs):
        # {(collection, doc_id, [subcollection, doc_id, ...]): {...}}
        self.docs = dict(docs)
        self.deleted = []

    def collection(self, name):
        return _FakeCollection(self, (name,))


def _seed():
    """A store carrying one of every shape the bead's inventory describes,
    PLUS a look-alike of each that must survive every run untouched."""
    return {
        # alerts: two matched by firm_id, one matched by doc id alone, one
        # UNRELATED alert that must never be touched.
        ("alerts", "link_exhausted_jti-x"): {
            "firm_id": "firm-a", "kind": "link_exhausted",
        },
        ("alerts", "acme_credit_low_2026-09-10"): {
            "firm_id": "acme", "kind": "credit_low",
        },
        ("alerts", "link_exhausted_jti-a"): {
            # No firm_id at all -- matched purely by doc id, per the bead
            # body's "one link_exhausted_jti-a" line.
            "kind": "link_exhausted",
        },
        ("alerts", "unrelated-real-alert"): {
            "firm_id": "real-firm", "kind": "credit_low",
        },
        # link_redemptions: bare + staging-suffixed, firm-a and no-firm_id,
        # plus an unrelated real firm's redemption that must survive.
        ("link_redemptions", "jti-1"): {"firm_id": "firm-a"},
        ("link_redemptions", "jti-2"): {},  # no firm_id key at all
        ("link_redemptions", "jti-3"): {"firm_id": "real-firm"},
        ("link_redemptions_staging", "jti-4"): {"firm_id": "firm-a"},
        # links: same shape, bare + staging.
        ("links", "jti-5"): {"firm_id": None},  # explicit None
        ("links", "jti-6"): {"firm_id": "real-firm"},
        ("links_staging", "jti-7"): {},
        # firms/firm-a plus two subcollections' docs.
        ("firms", "firm-a"): {"name": "Test Firm A", "kind": "mock"},
        ("firms", "firm-a", "ledger", "auto1"): {
            "type": "mint_debit", "amount": -1,
        },
        ("firms", "firm-a", "usage", "2026-09"): {"sessions_completed": 3},
        # An UNRELATED real firm that must survive completely, subcollection
        # included.
        ("firms", "real-firm"): {"name": "Real Firm", "kind": "live"},
        ("firms", "real-firm", "ledger", "auto1"): {
            "type": "purchase", "amount": 500,
        },
    }


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDb(_seed())
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)
    return db


# --------------------------------------------------------------- dry run


def test_dry_run_lists_exactly_the_enumerated_shapes_and_nothing_else(
        firebase_stub, fake_db, capsys):
    """EXIT CRITERION 2, the dry-run half. Every matched doc appears in the
    listing and every unrelated look-alike does not.

    Mutation: change _alert_matches to always return True -- the unrelated
    alert doc id appears in the output and this goes red. Verified
    2026-09-15."""
    rc = purge.main(["--project", PROJECT, "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out

    # Matched.
    assert "alerts/link_exhausted_jti-x" in out
    assert "alerts/acme_credit_low_2026-09-10" in out
    assert "alerts/link_exhausted_jti-a" in out
    assert "link_redemptions/jti-1" in out
    assert "link_redemptions/jti-2" in out
    assert "link_redemptions_staging/jti-4" in out
    assert "links/jti-5" in out
    assert "links_staging/jti-7" in out
    assert "firms/firm-a/ledger/auto1" in out
    assert "firms/firm-a/usage/2026-09" in out
    assert "firms/firm-a" in out

    # Never matched.
    assert "unrelated-real-alert" not in out
    assert "link_redemptions/jti-3" not in out
    assert "links/jti-6" not in out
    assert "real-firm" not in out

    assert fake_db.deleted == []


def test_dry_run_deletes_nothing(firebase_stub, fake_db):
    """The default posture is read-only. Mutation: call ref.delete() inside
    the dry-run branch -- fake_db.deleted becomes non-empty and this goes
    red. Verified 2026-09-15."""
    purge.main(["--project", PROJECT, "--dry-run"])
    assert fake_db.deleted == []


def test_no_flag_at_all_also_defaults_to_a_dry_run(firebase_stub, fake_db):
    """Neither --dry-run nor --apply given: the SAFE default is read-only,
    matching the module docstring's "the default posture is read-only".

    Mutation: make apply_deletes default to True -- a real delete happens
    with neither flag passed and this goes red. Verified 2026-09-15."""
    rc = purge.main(["--project", PROJECT])
    assert rc == 0
    assert fake_db.deleted == []


def test_dry_run_and_apply_together_is_refused(firebase_stub, fake_db, capsys):
    """Mutually exclusive: an operator cannot ask for both in one run.

    Mutation: delete the `if args.apply and args.dry_run` refusal -- exit 0
    happens (through whichever branch argparse order picks) and this goes
    red. Verified 2026-09-15."""
    rc = purge.main(["--project", PROJECT, "--dry-run", "--apply"])
    assert rc == 2
    assert fake_db.deleted == []
    assert "mutually exclusive" in capsys.readouterr().err


# ----------------------------------------------------------------- apply


def test_apply_deletes_exactly_the_matched_set(firebase_stub, fake_db):
    """EXIT CRITERION 2, the apply half. Every matched path is deleted;
    every unrelated path survives.

    Mutation: iterate over db.docs directly instead of the matched result
    (deleting everything) -- the unrelated-real-alert assertion goes red.
    Verified 2026-09-15."""
    rc = purge.main(["--project", PROJECT, "--apply"])
    assert rc == 0

    remaining = set(fake_db.docs.keys())
    assert ("alerts", "link_exhausted_jti-x") not in remaining
    assert ("alerts", "acme_credit_low_2026-09-10") not in remaining
    assert ("alerts", "link_exhausted_jti-a") not in remaining
    assert ("link_redemptions", "jti-1") not in remaining
    assert ("link_redemptions", "jti-2") not in remaining
    assert ("link_redemptions_staging", "jti-4") not in remaining
    assert ("links", "jti-5") not in remaining
    assert ("links_staging", "jti-7") not in remaining
    assert ("firms", "firm-a") not in remaining
    assert ("firms", "firm-a", "ledger", "auto1") not in remaining
    assert ("firms", "firm-a", "usage", "2026-09") not in remaining

    # Survivors, untouched.
    assert ("alerts", "unrelated-real-alert") in remaining
    assert ("link_redemptions", "jti-3") in remaining
    assert ("links", "jti-6") in remaining
    assert ("firms", "real-firm") in remaining
    assert ("firms", "real-firm", "ledger", "auto1") in remaining


def test_apply_with_no_matches_deletes_nothing_and_exits_0(
        firebase_stub, monkeypatch):
    """An empty/clean project must not be treated as an error.

    Mutation: raise on an empty match set instead of printing "0
    document(s)" -- this goes red. Verified 2026-09-15."""
    db = _FakeDb({})
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)
    rc = purge.main(["--project", PROJECT, "--apply"])
    assert rc == 0
    assert db.deleted == []


def test_a_failed_delete_is_reported_and_does_not_abort_the_sweep(
        firebase_stub, fake_db, monkeypatch, capsys):
    """One bad delete (a permission hiccup, a doc already gone under a
    race) must not stop the rest of the sweep from completing.

    Mutation: let the exception propagate out of main() instead of being
    caught per-ref -- the surviving deletes never happen and this goes red.
    Verified 2026-09-15."""
    original_matches = purge.find_matches

    def _boom_on_first(db):
        matches = original_matches(db)
        # Make the FIRST alert ref's delete() raise, everything else normal.
        first_id, first_ref = matches["alerts"][0]

        def _raise():
            raise RuntimeError("permission denied")

        first_ref.delete = _raise
        return matches

    monkeypatch.setattr(purge, "find_matches", _boom_on_first)
    rc = purge.main(["--project", PROJECT, "--apply"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "FAILED to delete" in err
    assert "permission denied" in err
    # The other matched docs (not the one that raised) were still deleted.
    remaining = set(fake_db.docs.keys())
    assert ("firms", "firm-a") not in remaining


# ------------------------------------------------------- project guards


def test_the_DEAD_project_is_refused_before_anything_is_read(
        fake_db, capsys):
    """Mutation: empty DEAD_PROJECTS -- the run proceeds past the guard and
    this goes red. Verified 2026-09-15."""
    rc = purge.main(["--project", "polyglot-forms-919f2"])
    assert rc == 2
    assert fake_db.deleted == []
    assert "DEAD" in capsys.readouterr().err


def test_a_MISMATCHED_resolved_project_aborts_with_exit_2(
        monkeypatch, fake_db, capsys):
    """Mutation: delete the `if resolved != args.project` block -- the read
    pass proceeds against the wrong project and this goes red. Verified
    2026-09-15."""
    import firebase_admin
    monkeypatch.setattr(firebase_admin, "_apps", {"[DEFAULT]": object()},
                        raising=False)
    monkeypatch.setattr(firebase_admin, "get_app",
                        lambda: _FakeApp("some-other-project"), raising=False)
    rc = purge.main(["--project", PROJECT, "--dry-run"])
    assert rc == 2
    assert fake_db.deleted == []
    assert "refusing" in capsys.readouterr().err


def test_project_is_a_REQUIRED_flag(firebase_stub):
    """Mutation: give --project a default -- SystemExit is not raised and
    this goes red. Verified 2026-09-15."""
    with pytest.raises(SystemExit):
        purge.main([])


# ------------------------------------------------- channel enumeration


def test_channel_suffixed_collections_match_KNOWN_CHANNELS():
    """The bare name (demo) plus every OTHER known channel's suffixed name
    -- mirrors link_redemptions._collection_name/links_store._collection_name.

    Mutation: hardcode a single collection name instead of deriving from
    KNOWN_CHANNELS -- this goes red once a channel is added or removed
    from the tuple without updating a hand-written list. Verified
    2026-09-15."""
    names = purge._channel_collection_names("links")
    assert names[0] == "links"
    for channel in purge.KNOWN_CHANNELS:
        if channel == "demo":
            continue
        assert "links_{}".format(channel) in names
    assert len(names) == len(purge.KNOWN_CHANNELS)


# ---------------------------------------- constants pinned against drift


def test_collection_constants_match_service_constants():
    """purge.py hand-duplicates these as literals rather than importing them
    (see the module comment above ALERTS_COLLECTION -- importing
    backend.services.auth transitively via backend.services.* triggers that
    module's import-time initialize_app() before main() has pinned a
    project). Import the four LEAF service modules directly instead: none
    of alerts.py/link_redemptions.py/links_store.py/firms.py imports
    backend.services.auth at module scope (confirmed: only backend.services.
    auth itself calls firebase_admin.initialize_app() at import time), so
    this import is safe and does not reach real Firestore -- it only reads
    each module's own COLLECTION name constant.

    Mutation: change any one of the four purge.py constants (e.g.
    ALERTS_COLLECTION = "alertz") -- this goes red. Verified 2026-09-15."""
    from backend.services import alerts, firms, link_redemptions, links_store

    assert purge.ALERTS_COLLECTION == alerts.COLLECTION
    assert purge.LINK_REDEMPTIONS_COLLECTION == link_redemptions.COLLECTION
    assert purge.LINKS_COLLECTION == links_store.COLLECTION
    assert purge.FIRMS_COLLECTION == firms._FIRMS_COLLECTION


def test_known_channels_matches_every_admin_route_copy():
    """admin_backend/routes/{config,firm,link}_routes.py each carry their own
    literal KNOWN_CHANNELS = ("demo", "staging") tuple (a pre-existing
    repo-wide duplication this diff does not introduce -- see
    docs/standards/testing.md). purge.py's copy must match all three, or a
    channel added in one place and not here silently stops being purged.

    Read the route files' SOURCE TEXT rather than importing them: importing
    admin_backend.routes.config_routes pulls in admin_backend.services.
    admin_auth, which imports backend.services.auth and would trip its
    import-time initialize_app() before main() pins a project -- the same
    hazard purge.py's own module comment documents for its literals.

    Mutation: change purge.KNOWN_CHANNELS to a different tuple -- this goes
    red. Verified 2026-09-15."""
    import re
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    route_files = [
        repo_root / "admin_backend" / "routes" / "config_routes.py",
        repo_root / "admin_backend" / "routes" / "firm_routes.py",
        repo_root / "admin_backend" / "routes" / "link_routes.py",
    ]
    pattern = re.compile(r'^KNOWN_CHANNELS\s*=\s*(\(.*\))\s*$', re.MULTILINE)
    for route_file in route_files:
        text = route_file.read_text(encoding="utf-8")
        match = pattern.search(text)
        assert match, "no KNOWN_CHANNELS literal found in {}".format(
            route_file)
        route_channels = eval(match.group(1))  # noqa: S307 -- literal tuple
        assert route_channels == purge.KNOWN_CHANNELS, (
            "{} KNOWN_CHANNELS {} != purge.py's {}".format(
                route_file.name, route_channels, purge.KNOWN_CHANNELS))
