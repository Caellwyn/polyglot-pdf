"""scripts/seed_kit_commercials.py CLI contract (Epic 2 bead A6).

EXIT CRITERION 1 (seed_kit_commercials half): dry-run, idempotent re-run,
the missing required flag (--default-credit-cost), and per-kit
burn_cap_usd resolution from metadata vs the default.

Pins the operator-facing safety properties:
- --default-credit-cost is REQUIRED (no default -- no pricing signal exists
  to derive one);
- every kit under --kits-root gets a kits/{kit_id} doc with credit_cost ==
  --default-credit-cost;
- burn_cap_usd comes from the kit's own metadata.json
  link_cost_ceiling_usd when present and a valid positive number, else
  --default-burn-cap-usd;
- a re-run with the SAME flags writes the SAME doc again (idempotent in
  effect, not skipped -- this is a seed script, re-runnable as pricing
  defaults change before the console exists);
- --dry-run writes nothing;
- a mismatched resolved project ABORTS with exit 2 before anything is
  written, and the dead project is refused outright;
- a kit with a missing/unparseable metadata.json is skipped, not fatal.

The CLI is driven as main([...]) -- matching every sibling operator script
in this repo, so no module-reload/argv-monkeypatch fixture is needed.

Each test's docstring names the mutation that must turn it red.

ASCII only.
"""
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.seed_kit_commercials as seed_kit_commercials  # noqa: E402

PROJECT = "polyglot-demo-aa709"


class _FakeApp:
    def __init__(self, project_id):
        self.project_id = project_id


@pytest.fixture
def firebase_stub(monkeypatch):
    """Pretend firebase_admin is already initialized for PROJECT."""
    import firebase_admin

    monkeypatch.setattr(
        firebase_admin, "_apps", {"[DEFAULT]": object()}, raising=False
    )
    monkeypatch.setattr(
        firebase_admin, "get_app", lambda: _FakeApp(PROJECT), raising=False
    )
    return firebase_admin


class _FakeDocRef:
    def __init__(self, store, kit_id):
        self._store = store
        self._kit_id = kit_id

    def set(self, payload):
        # The real script always passes a full replacement dict (never
        # merge=True) -- a seed doc has no partial-update path.
        self._store[self._kit_id] = dict(payload)


class _FakeCollection:
    def __init__(self, store):
        self._store = store

    def document(self, kit_id):
        return _FakeDocRef(self._store, kit_id)


class _FakeDb:
    def __init__(self):
        self.kits = {}  # kit_id -> written payload

    def collection(self, name):
        assert name == "kits"
        return _FakeCollection(self.kits)


@pytest.fixture
def wired_db(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)
    return db


def _make_kit(root: Path, kit_id: str, metadata: dict | None):
    kit_dir = root / kit_id
    kit_dir.mkdir(parents=True, exist_ok=True)
    if metadata is not None:
        (kit_dir / "metadata.json").write_text(
            json.dumps(metadata), encoding="utf-8"
        )
    return kit_dir


def _argv(*extra, project=PROJECT, default_credit_cost="5", kits_root=None):
    argv = ["--project", project]
    if default_credit_cost is not None:
        argv += ["--default-credit-cost", default_credit_cost]
    if kits_root is not None:
        argv += ["--kits-root", str(kits_root)]
    return argv + list(extra)


# --------------------------------------------------- missing required flag


def test_default_credit_cost_is_required(tmp_path, capsys):
    """--default-credit-cost has no default; argparse must refuse with exit
    2 and no firebase_admin touch. Mutation: give it a default value --
    this would stop raising SystemExit and go red."""
    _make_kit(tmp_path, "w7", {"label": "W-7"})
    with pytest.raises(SystemExit) as exc:
        seed_kit_commercials.main(_argv(default_credit_cost=None, kits_root=tmp_path))
    assert exc.value.code == 2


def test_default_credit_cost_must_be_positive(tmp_path, capsys):
    """A zero or negative --default-credit-cost must be refused with exit 2
    before any Firestore touch. Mutation: drop the `<= 0` check -- would
    proceed to firebase_admin init with a nonsensical price."""
    _make_kit(tmp_path, "w7", {"label": "W-7"})
    rc = seed_kit_commercials.main(
        _argv("--default-credit-cost", "0", default_credit_cost=None, kits_root=tmp_path)
    )
    assert rc == 2
    assert "positive" in capsys.readouterr().err


# --------------------------------------------------------- dead/wrong project


def test_dead_project_is_refused(tmp_path, capsys):
    """The former prod project must be refused before any Firestore touch.
    Mutation: remove the DEAD_PROJECTS check."""
    _make_kit(tmp_path, "w7", {"label": "W-7"})
    rc = seed_kit_commercials.main(
        _argv(project="polyglot-forms-919f2", kits_root=tmp_path)
    )
    assert rc == 2
    assert "DEAD" in capsys.readouterr().err


def test_mismatched_resolved_project_aborts(firebase_stub, monkeypatch, tmp_path, capsys):
    """A resolved project different from --project must abort with exit 2
    and write nothing. Mutation: drop the resolved-vs-requested equality
    check."""
    _make_kit(tmp_path, "w7", {"label": "W-7"})
    import firebase_admin

    monkeypatch.setattr(
        firebase_admin, "get_app", lambda: _FakeApp("some-other-project")
    )
    called = {"db": False}

    def _get_db():
        called["db"] = True
        return _FakeDb()

    monkeypatch.setattr("backend.services.auth.get_db", _get_db)

    rc = seed_kit_commercials.main(_argv(kits_root=tmp_path))
    assert rc == 2
    assert not called["db"], "must abort before touching Firestore"


# ------------------------------------------------------------- no kits found


def test_no_kits_found_aborts_with_exit_2(tmp_path, capsys):
    """An empty --kits-root (or one with no metadata.json anywhere) must
    abort with exit 2 before touching firebase_admin at all. Mutation:
    remove the `if not kit_dirs: return 2` guard -- would proceed to
    initialize firebase_admin for nothing to seed."""
    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    rc = seed_kit_commercials.main(_argv(kits_root=empty_root))
    assert rc == 2
    assert "no kits found" in capsys.readouterr().err.lower()


# ------------------------------------------------------------- basic seeding


def test_every_kit_gets_the_default_credit_cost(
        firebase_stub, wired_db, tmp_path):
    """Every kit under --kits-root gets credit_cost == --default-credit-cost.
    Mutation: hardcode credit_cost=1 instead of args.default_credit_cost --
    reddens this test for any cost != 1."""
    _make_kit(tmp_path, "w7", {"label": "W-7"})
    _make_kit(tmp_path, "f1040", {"label": "1040"})

    rc = seed_kit_commercials.main(
        _argv("--default-credit-cost", "7", default_credit_cost=None, kits_root=tmp_path)
    )

    assert rc == 0
    assert wired_db.kits["w7"]["credit_cost"] == 7
    assert wired_db.kits["f1040"]["credit_cost"] == 7


def test_kit_with_no_metadata_json_is_skipped_not_fatal(
        firebase_stub, wired_db, tmp_path, capsys):
    """A kit dir with a metadata.json that fails to parse must be skipped
    (warned on stderr) while the sweep continues for other kits. Mutation:
    let the JSONDecodeError propagate uncaught -- would abort main()
    entirely instead of skipping just this kit."""
    _make_kit(tmp_path, "w7", {"label": "W-7"})
    broken = _make_kit(tmp_path, "broken-kit", None)
    (broken / "metadata.json").write_text("{not valid json", encoding="utf-8")

    rc = seed_kit_commercials.main(_argv(kits_root=tmp_path))

    assert rc == 0
    assert "w7" in wired_db.kits
    assert "broken-kit" not in wired_db.kits
    assert "broken-kit" in capsys.readouterr().err


# ------------------------------------------------- burn_cap_usd resolution


def test_burn_cap_usd_from_metadata_key_when_present_and_valid(
        firebase_stub, wired_db, tmp_path):
    """A kit's own link_cost_ceiling_usd (e.g. w7's $3) must be used as
    burn_cap_usd, not the default. Mutation: always use
    args.default_burn_cap_usd, ignoring metadata -- would write 10.0
    instead of 3, reddening this test."""
    _make_kit(tmp_path, "w7", {"label": "W-7", "link_cost_ceiling_usd": 3})

    rc = seed_kit_commercials.main(
        _argv("--default-burn-cap-usd", "10", kits_root=tmp_path)
    )

    assert rc == 0
    assert wired_db.kits["w7"]["burn_cap_usd"] == 3.0


def test_burn_cap_usd_falls_back_to_default_when_metadata_key_absent(
        firebase_stub, wired_db, tmp_path):
    """A kit with no link_cost_ceiling_usd key must fall back to
    --default-burn-cap-usd. Mutation: crash or default to 0 on a missing
    key instead of falling back -- reddens this test."""
    _make_kit(tmp_path, "f1040", {"label": "1040"})

    rc = seed_kit_commercials.main(
        _argv("--default-burn-cap-usd", "12.5", kits_root=tmp_path)
    )

    assert rc == 0
    assert wired_db.kits["f1040"]["burn_cap_usd"] == 12.5


@pytest.mark.parametrize("bad_value", [None, "free", -4, 0, True, []])
def test_burn_cap_usd_falls_back_on_every_malformed_metadata_value(
        firebase_stub, wired_db, tmp_path, bad_value):
    """A malformed link_cost_ceiling_usd (wrong type, non-positive, bool,
    a list) must fall back to the default, never crash and never remove
    the ceiling (the plan's 'a bad edit must never remove a form's
    ceiling' rule). Mutation: drop any one of the isinstance/positive/NaN
    guards in _positive_number -- this parametrization catches whichever
    one is missing."""
    _make_kit(
        tmp_path, "quirky-kit",
        {"label": "Quirky", "link_cost_ceiling_usd": bad_value},
    )

    rc = seed_kit_commercials.main(
        _argv("--default-burn-cap-usd", "9", kits_root=tmp_path)
    )

    assert rc == 0
    assert wired_db.kits["quirky-kit"]["burn_cap_usd"] == 9.0


def test_default_burn_cap_usd_matches_link_budget_default(tmp_path):
    """seed_kit_commercials' compiled-in default must match
    backend.services.link_budget.DEFAULT_LINK_COST_CEILING_USD, so an
    un-overridden kit's seeded ceiling matches what the runtime would have
    resolved anyway. Mutation: change one constant without the other --
    this test is the tripwire."""
    from backend.services import link_budget

    assert (
        seed_kit_commercials.DEFAULT_BURN_CAP_USD
        == link_budget.DEFAULT_LINK_COST_CEILING_USD
    )


def test_kit_cost_ceiling_key_matches_link_budget_constant():
    """The metadata key literal must match link_budget.KIT_COST_CEILING_KEY
    (kept as a literal here for the same import-ordering reason every
    sibling script documents). Mutation: typo one of the two strings --
    this test is the tripwire."""
    from backend.services import link_budget

    assert (
        seed_kit_commercials.KIT_COST_CEILING_KEY
        == link_budget.KIT_COST_CEILING_KEY
    )


# --------------------------------------------------------------- display


def test_display_label_comes_from_metadata_label(firebase_stub, wired_db, tmp_path):
    """display.label must be the kit's metadata.json label when present.
    Mutation: always use kit_id for the label -- reddens this test."""
    _make_kit(tmp_path, "w7", {"label": "W-7 (ITIN Application)"})

    rc = seed_kit_commercials.main(_argv(kits_root=tmp_path))

    assert rc == 0
    assert wired_db.kits["w7"]["display"] == {"label": "W-7 (ITIN Application)"}


def test_display_label_falls_back_to_kit_id_when_label_missing(
        firebase_stub, wired_db, tmp_path):
    """A kit with no (or a blank) label must fall back to its kit_id.
    Mutation: crash on a missing label instead of falling back -- reddens
    this test."""
    _make_kit(tmp_path, "unlabeled-kit", {"status": "draft"})

    rc = seed_kit_commercials.main(_argv(kits_root=tmp_path))

    assert rc == 0
    assert wired_db.kits["unlabeled-kit"]["display"] == {"label": "unlabeled-kit"}


# -------------------------------------------------------------------- dry-run


def test_dry_run_writes_nothing(firebase_stub, wired_db, tmp_path, capsys):
    """--dry-run must print the doc that would be written but call no
    Firestore .set(). Mutation: remove the `if args.dry_run: continue`
    guard -- would perform the real write despite --dry-run."""
    _make_kit(tmp_path, "w7", {"label": "W-7"})

    rc = seed_kit_commercials.main(_argv("--dry-run", kits_root=tmp_path))

    assert rc == 0
    assert wired_db.kits == {}
    assert "DRY RUN" in capsys.readouterr().out


# -------------------------------------------------------- idempotent re-run


def test_rerun_with_same_flags_writes_the_same_doc_again(
        firebase_stub, wired_db, tmp_path):
    """Two consecutive runs with identical flags must produce the SAME
    credit_cost/burn_cap_usd/display -- re-running is safe and has the same
    effect, even though the doc is re-written (this is a seed script, not a
    write-once migration). Mutation: make the second run compute a
    different burn_cap_usd or credit_cost from identical inputs -- reddens
    this test."""
    _make_kit(tmp_path, "w7", {"label": "W-7", "link_cost_ceiling_usd": 3})

    rc1 = seed_kit_commercials.main(
        _argv("--default-credit-cost", "5", default_credit_cost=None, kits_root=tmp_path)
    )
    first = dict(wired_db.kits["w7"])

    rc2 = seed_kit_commercials.main(
        _argv("--default-credit-cost", "5", default_credit_cost=None, kits_root=tmp_path)
    )
    second = dict(wired_db.kits["w7"])

    assert rc1 == 0 and rc2 == 0
    assert first["credit_cost"] == second["credit_cost"] == 5
    assert first["burn_cap_usd"] == second["burn_cap_usd"] == 3.0
    assert first["display"] == second["display"]


# ---------------------------------------------------------- resilience: one bad kit


def test_one_failing_kit_does_not_abort_the_sweep(
        firebase_stub, wired_db, tmp_path, monkeypatch, capsys):
    """A write failure on one kit must be recorded and reported (exit 1),
    but must not stop the sweep from processing the remaining kits.
    Mutation: remove the try/except around the per-kit write -- an
    exception would propagate and abort main() entirely."""
    _make_kit(tmp_path, "bad-kit", {"label": "Bad"})
    _make_kit(tmp_path, "good-kit", {"label": "Good"})

    real_document = _FakeCollection.document

    def _boom_document(self, kit_id):
        ref = real_document(self, kit_id)
        if kit_id == "bad-kit":
            def _raise(payload):
                raise RuntimeError("simulated write failure")
            ref.set = _raise
        return ref

    monkeypatch.setattr(_FakeCollection, "document", _boom_document)

    rc = seed_kit_commercials.main(_argv(kits_root=tmp_path))

    assert rc == 1
    assert "bad-kit" in capsys.readouterr().err
    assert "good-kit" in wired_db.kits
