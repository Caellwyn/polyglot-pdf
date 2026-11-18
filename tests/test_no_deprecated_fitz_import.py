"""No tracked Python file imports PyMuPDF under its deprecated `fitz` name.

PyMuPDF >= 1.26 prints "The `fitz` API is deprecated ... Use `import pymupdf`
instead." at IMPORT time, and future releases remove the name. That line is
not JSON, so on the deployed backend it reaches Cloud Logging as textPayload
at every startup -- and tests/test_structlog_json_output.py, which requires
every app output line to be JSON, fails on it (bd polyglot-pdf-k5dnc). Every
importer uses `import pymupdf as fitz` instead, which keeps the `fitz.` call
sites unchanged.

The set is DISCOVERED from `git ls-files` (what CI sees), not hand-listed, so a
new file that reintroduces the old import fails here.
"""

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# `import fitz`, `import fitz as x`, `from fitz import ...`, and the
# importorskip("fitz") form the tests use.
_DEPRECATED = re.compile(
    r"^\s*(import\s+fitz\b|from\s+fitz\b)|importorskip\(\s*[\"']fitz[\"']",
    re.M,
)


def _tracked_python_files():
    out = subprocess.run(
        ["git", "ls-files", "*.py"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.split()
    assert out, "git ls-files returned no Python files -- the scan proves nothing"
    return out


def test_no_tracked_file_imports_the_deprecated_fitz_name():
    offenders = []
    for rel in _tracked_python_files():
        # This file names the deprecated forms in its own pattern and samples.
        if rel == "tests/test_no_deprecated_fitz_import.py":
            continue
        text = (REPO / rel).read_text(encoding="utf-8", errors="replace")
        for m in _DEPRECATED.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            offenders.append(f"{rel}:{line}")
    assert not offenders, (
        "import PyMuPDF as `import pymupdf as fitz`, not via the deprecated "
        "`fitz` name (its import-time warning is a non-JSON log line): "
        + ", ".join(offenders)
    )


def test_the_pattern_catches_every_deprecated_form():
    """Guard the guard: each shape the rewrite removed must still match."""
    for bad in (
        "import fitz",
        "    import fitz  # noqa",
        "import fitz as _fitz",
        "from fitz import Document",
        'fitz = pytest.importorskip("fitz")',
        "pytest.importorskip('fitz', reason='x')",
    ):
        assert _DEPRECATED.search(bad), bad
    for ok in (
        "import pymupdf as fitz",
        'fitz = pytest.importorskip("pymupdf")',
        'def f(doc: "fitz.Document"): ...',
    ):
        assert not _DEPRECATED.search(ok), ok
