"""THE SET PIN for "every collected suite actually runs in the gates".

A suite that no gate runs is worse than no suite at all: it reports green
because nothing executed it. This repo has shipped that failure twice.

  - bd polyglot-pdf-3ave journaled it for CI: "CI runs `pytest backend/tests
    tests`, so the PR would have merged CI-red".
  - bd polyglot-pdf-pnoik added `admin_backend/tests` to pytest.ini's
    `testpaths`, and BOTH gates -- .github/workflows/ci.yml and
    scripts/closeout_prep.py -- hardcoded their own suite paths, so all 12
    tests in the new suite (including the admin service-account role pin and
    the import-direction guard, i.e. the whole point of that bead) ran in
    NEITHER gate.

Both failures are the same shape: `testpaths` is the declaration of what the
suites ARE, and a gate that re-lists suite paths by hand silently drifts from
it. So this pins the SET rather than any one member (CLAUDE.md scar #8): the
gates must not name suite paths at all, which is what makes them inherit a new
root automatically.

Mutations that must turn this red:
  - re-add explicit suite paths to the CI pytest invocation
  - re-add an explicit suite path to closeout_prep.check_tests
  - add a root to pytest.ini testpaths that neither gate would then run
"""
import configparser
import io
import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PYTEST_INI = REPO_ROOT / "pytest.ini"
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
CLOSEOUT_PREP = REPO_ROOT / "scripts" / "closeout_prep.py"


def _testpaths():
    """The declared suite roots, read from pytest.ini itself.

    Derived, never hand-listed: a hand-copied expectation here would drift the
    same way the gates did, and this test would then bless the drift.
    """
    parser = configparser.ConfigParser()
    parser.read_string(io.open(PYTEST_INI, encoding="utf-8").read())
    raw = parser.get("pytest", "testpaths")
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _ci_pytest_commands():
    """Every `pytest ...` command line in the CI workflow."""
    text = io.open(CI_YML, encoding="utf-8").read()
    return [m.group(1).strip()
            for m in re.finditer(r"run:\s*(pytest[^\n]*)", text)]


def test_pytest_ini_declares_every_suite_that_exists():
    """testpaths is the declaration; a suite dir outside it never runs.

    Catches the ORIGINAL error one layer earlier than the gates: a new
    `<pkg>/tests` package that was never added to testpaths at all is invisible
    to a bare pytest, so the gate fixes below would not save it.
    """
    declared = {p.rstrip("/") for p in _testpaths()}
    found = set()
    for tests_dir in REPO_ROOT.glob("*/tests"):
        if not (tests_dir / "__init__.py").exists():
            continue
        found.add(tests_dir.relative_to(REPO_ROOT).as_posix())
    # The root-level `tests/` harness suite has no __init__.py, so it is not
    # picked up by the glob above; assert it explicitly since it is a real root.
    assert "tests" in declared, _testpaths()
    missing = sorted(found - declared)
    assert not missing, (
        "these test packages exist but are NOT in pytest.ini testpaths, so a "
        "bare pytest never collects them:\n  " + "\n  ".join(missing))


def test_every_declared_suite_root_exists():
    """A testpaths entry naming a directory that is gone makes pytest error."""
    missing = [p for p in _testpaths() if not (REPO_ROOT / p).is_dir()]
    assert not missing, (
        "pytest.ini testpaths names directories that do not exist:\n  "
        + "\n  ".join(missing))


def test_ci_runs_pytest_without_naming_suite_paths():
    """CI must inherit testpaths, not re-list the suites.

    This is the exact regression of bd polyglot-pdf-3ave and of the
    admin_backend miss: `pytest backend/tests tests` pins CI to the suites that
    existed the day the line was written.
    """
    commands = _ci_pytest_commands()
    assert commands, "no pytest invocation found in " + CI_YML.as_posix()

    roots = [p.rstrip("/") for p in _testpaths()]
    offenders = []
    for cmd in commands:
        for root in roots:
            # Match the root as a whole argument, so an unrelated flag value
            # containing the word is not mistaken for a suite path.
            if re.search(r"(?<![\w/-])" + re.escape(root) + r"/?(?=\s|$)", cmd):
                offenders.append("{!r} names suite path {!r}".format(cmd, root))

    assert not offenders, (
        "the CI pytest command hardcodes suite paths, so a new testpaths root "
        "would not run in CI:\n  " + "\n  ".join(offenders)
        + "\n\nUse a bare `pytest -q -m \"not external\"` and let pytest.ini "
          "testpaths decide which suites exist.")


def test_closeout_prep_runs_pytest_without_naming_suite_paths():
    """The pre-PR gate must inherit testpaths the same way CI does.

    closeout_prep.check_tests() is the gate an orchestrator actually runs
    before opening a PR; if it names suite paths, a new suite is unguarded in
    review even when CI is fixed.
    """
    text = io.open(CLOSEOUT_PREP, encoding="utf-8").read()
    body = text[text.index("def check_tests("):]
    body = body[:body.index("\ndef ")]

    # The subprocess argv is what actually decides which suites run.
    argv = re.search(r"\[str\(py\),\s*\"-m\",\s*\"pytest\"(.*?)\]", body,
                     re.DOTALL)
    assert argv, "could not find the pytest argv in check_tests():\n" + body
    args = argv.group(1)

    assert "tests_dir" not in args, (
        "check_tests() passes an explicit suite directory to pytest, so a new "
        "pytest.ini testpaths root is not gated pre-PR:\n" + args.strip())
    for root in (p.rstrip("/") for p in _testpaths()):
        assert '"{}"'.format(root) not in args, (
            "check_tests() hardcodes suite path {!r}".format(root))


def test_check_tests_runs_from_the_worktree_root():
    """A bare pytest only finds pytest.ini if cwd is the repo root.

    Without cwd=WT the bare invocation searches upward from the process's own
    cwd and can collect a DIFFERENT tree (or error), which would turn the fix
    above into a new silent failure.
    """
    text = io.open(CLOSEOUT_PREP, encoding="utf-8").read()
    body = text[text.index("def check_tests("):]
    body = body[:body.index("\ndef ")]
    assert "cwd=str(WT)" in body, (
        "check_tests() must run pytest with cwd at the worktree root so the "
        "worktree's own pytest.ini testpaths is the one that applies")
