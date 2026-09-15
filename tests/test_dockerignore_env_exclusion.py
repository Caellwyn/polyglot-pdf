"""The .dockerignore `backend/.env.*` line is the REAL production control for
the dev-only gates (bd polyglot-pdf-6088m, sprint 23 C4; PF-10).

backend/utils/dev_file_logger.py's DEV_LOGGING_ENABLED flips on the mere
EXISTENCE of backend/.env.DEV -- there is no env var, and no other check.
That marker-file gate is only safe in production because backend/.env.* is
excluded from the Cloud Run build context by .dockerignore, so the file can
never exist inside a built container. If that dockerignore line were ever
narrowed, removed, or typo'd, the file-existence check itself could not tell
the difference -- production would happily read a marker that should not be
there. This test pins that the exclusion is present at all, so a drive-by
edit to .dockerignore fails CI instead of silently reopening every dev-only
route that gates on DEV_LOGGING_ENABLED (/dev/console-log, /ws/echo, /ws/audio).

Mutation must turn this red:
  - deleting the `backend/.env.*` line from .dockerignore
  - narrowing it to `backend/.env.DEV` only (still catches the one case that
    matters today, but the test asserts the WIDER pattern is what ships,
    since a wildcard is what makes the guarantee independent of the marker's
    exact filename)
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCKERIGNORE = REPO_ROOT / ".dockerignore"


def _lines() -> list[str]:
    return [
        line.strip()
        for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_dockerignore_exists():
    assert DOCKERIGNORE.exists(), ".dockerignore is missing from the repo root"


def test_backend_env_wildcard_is_excluded():
    """The line that actually protects backend/.env.DEV from reaching a build.

    A bare `.env.*` at the repo root does NOT cover backend/.env.DEV under
    Docker's ignore-file semantics without a `**` prefix, so the explicit
    `backend/.env.*` line is load-bearing on its own, not merely a restatement
    of the root-level pattern above it.
    """
    lines = _lines()
    assert "backend/.env.*" in lines, (
        "backend/.env.* is missing from .dockerignore -- this is the line that "
        "keeps backend/.env.DEV (and any other backend/.env* file) out of the "
        "production container; without it, the dev-logging marker-file gate "
        "has no real backstop"
    )


def test_backend_env_bare_file_is_also_excluded():
    """backend/.env (no suffix) is a distinct pattern from backend/.env.* and
    must be excluded too -- a dev's plain backend/.env (API keys, local
    overrides) is a different leak than the .env.DEV marker but belongs in the
    same never-ships-to-prod bucket."""
    lines = _lines()
    assert "backend/.env" in lines, (
        "backend/.env is missing from .dockerignore"
    )
