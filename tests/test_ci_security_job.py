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
    # Every scanner step continues on error: one noisy tool must not hide
    # the others, and the job never gates (ci.yml's non-blocking doctrine).
    assert job.count("continue-on-error: true") >= len(SECURITY_TOOLS)


def test_every_security_tool_runs_in_the_job():
    job = _security_job()
    missing = [t for t in SECURITY_TOOLS if t not in job]
    assert not missing, "security job lost these scanner invocations: " + repr(missing)


def test_the_three_npm_audits_cover_the_three_apps():
    job = _security_job()
    for app in ("frontend", "schema-editor", "admin-console"):
        assert "working-directory: " + app in job, app


def test_every_pytest_runner_installs_the_dev_requirements():
    """pytest lives in requirements-dev.txt now; a runner that installs only
    requirements.txt has no test runner and goes red on the first PR."""
    for path in (CI, CLOUDBUILD):
        text = path.read_text(encoding="utf-8")
        assert "backend/requirements-dev.txt" in text, str(path)


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
