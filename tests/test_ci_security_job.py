"""Pin the sprint-23 F1 security scaffolding as shipped text (bd
polyglot-pdf-ikdnd): the informational security job in ci.yml and the tools
it runs, dependabot's ecosystems, the key-material gitignore patterns, and
the runtime/test requirements split. Text pins, like
tests/test_setup_monitoring_script.py: a line that silently disappears
fails here instead of in a review round.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
CLOUDBUILD = REPO_ROOT / "cloudbuild.yaml"
DEPENDABOT = REPO_ROOT / ".github" / "dependabot.yml"
GITIGNORE = REPO_ROOT / ".gitignore"
REQ = REPO_ROOT / "backend" / "requirements.txt"
REQ_DEV = REPO_ROOT / "backend" / "requirements-dev.txt"

SECURITY_TOOLS = (
    "pip-audit -r backend/requirements.txt",
    "npm audit --omit=dev",
    "detect-secrets-hook --baseline .secrets.baseline",
    "bandit -r backend admin_backend -ll",
    "semgrep --config p/python --config p/typescript",
)
DEPENDABOT_ECOSYSTEMS = (
    ('"pip"', '"/backend"'),
    ('"npm"', '"/frontend"'),
    ('"npm"', '"/schema-editor"'),
    ('"npm"', '"/admin-console"'),
    ('"github-actions"', '"/"'),
)
KEY_PATTERNS = ("*.pem", "*.key", "*service-account*.json", "*credentials*.json")
TEST_ONLY_PINS = ("pytest==", "pytest-asyncio==", "pytest-cov==")
JOB_HEADER = "\n  security:\n"


def _ci():
    return CI.read_text(encoding="utf-8")


def _security_job():
    text = _ci()
    assert JOB_HEADER in text, "ci.yml has no security job"
    return text.split(JOB_HEADER, 1)[1]


def test_the_security_job_exists_and_is_informational():
    job = _security_job()
    assert "name: security scans (informational)" in job
    # EVERY scanner step continues on error: one noisy tool must not hide
    # the others, and the job never gates (ci.yml's non-blocking doctrine).
    # Scanner steps are the `run:` steps other than the one that installs
    # the scanners, so a step added without the flag fails here.
    run_steps = job.count(chr(10) + "        run:")
    assert run_steps >= len(SECURITY_TOOLS) + 1
    assert job.count("continue-on-error: true") == run_steps - 1


def test_every_security_tool_runs_in_the_job():
    job = _security_job()
    missing = [t for t in SECURITY_TOOLS if t not in job]
    assert not missing, "security job lost these scanner invocations: " + repr(missing)


def test_the_three_npm_audits_cover_the_three_apps():
    job = _security_job()
    for app in ("frontend", "schema-editor", "admin-console"):
        assert "working-directory: " + app in job, app


def _install_lines():
    """Every `pip install` of the backend requirements anywhere an operator or
    a runner would follow: CI, Cloud Build, the dev scripts in every shell
    dialect (.sh / .bat / .ps1) and the two READMEs. Derived by glob, so a
    new script is covered the day it is added."""
    files = [CI, CLOUDBUILD, REPO_ROOT / "README.md", REPO_ROOT / "scripts" / "README.md"]
    for pattern in ("*.sh", "*.bat", "*.ps1"):
        files.extend(sorted((REPO_ROOT / "scripts").glob(pattern)))
    for path in files:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if stripped.startswith(("#", "REM ", "::")):
                continue  # prose about the files, not an install
            if "pip install" in line and "requirements" in line:
                yield path.relative_to(REPO_ROOT).as_posix(), line.strip()


# The ONE deliberate exception (bd polyglot-pdf-lwka0): ci.yml's
# backend-runtime-install job installs backend/requirements.txt ALONE, on
# purpose, to prove the runtime file resolves in a clean environment the way
# the deploy image does -- it never runs pytest, so it is not one of the
# "pytest runner" lines this test polices. Named explicitly (not pattern-
# matched, not a blanket "ignore ci.yml") so a SECOND bare-runtime install
# line added anywhere still trips this test (CLAUDE.md scar #8: enumerate the
# set, don't loosen the check to swallow the whole class).
DELIBERATE_RUNTIME_ONLY_INSTALLS = (
    (".github/workflows/ci.yml", "run: pip install -r backend/requirements.txt"),
)


def test_every_pytest_runner_installs_the_dev_requirements():
    """pytest lives in requirements-dev.txt now; a runner or a dev script
    that installs only requirements.txt has no test runner. The .bat mirrors
    of the .sh scripts are part of this set (CLAUDE.md scar #8)."""
    lines = list(_install_lines())
    assert len(lines) >= 8, "the install-line scan is vacuous: " + repr(lines)
    bare = [
        (f, l) for f, l in lines
        if "requirements-dev" not in l and (f, l) not in DELIBERATE_RUNTIME_ONLY_INSTALLS
    ]
    assert not bare, "these still install the runtime file alone: " + repr(bare)
    for runner in (CI, CLOUDBUILD):
        assert "backend/requirements-dev.txt" in runner.read_text(encoding="utf-8")


def test_dependabot_covers_every_ecosystem():
    text = DEPENDABOT.read_text(encoding="utf-8")
    for eco, directory in DEPENDABOT_ECOSYSTEMS:
        assert "package-ecosystem: " + eco in text, eco
        assert "directory: " + directory in text, directory
    assert text.count('interval: "weekly"') == len(DEPENDABOT_ECOSYSTEMS)


def test_gitignore_refuses_key_material():
    lines = {l.strip() for l in GITIGNORE.read_text(encoding="utf-8").splitlines()}
    missing = [p for p in KEY_PATTERNS if p not in lines]
    assert not missing, ".gitignore lost the key-material patterns: " + repr(missing)


def test_the_image_requirements_carry_no_test_tooling():
    runtime = REQ.read_text(encoding="utf-8")
    leaked = [p for p in TEST_ONLY_PINS if p in runtime]
    assert not leaked, "test tooling is back in the runtime requirements: " + repr(leaked)
    dev = REQ_DEV.read_text(encoding="utf-8")
    assert "-r requirements.txt" in dev
    assert all(p in dev for p in TEST_ONLY_PINS)


def test_python_multipart_is_past_the_cve_fix():
    """CVE-2024-53981 is fixed in python-multipart 0.0.18; the pin must not
    regress below it."""
    m = re.search(r"^python-multipart==(\d+)\.(\d+)\.(\d+)$",
                  REQ.read_text(encoding="utf-8"), re.M)
    assert m, "python-multipart pin missing"
    assert tuple(int(x) for x in m.groups()) >= (0, 0, 18)
