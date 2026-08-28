"""The session-id guard exists TWICE, and the copies must not drift (bd dft1).

Python: backend/utils/confirmation_logger.py `_is_safe_session_id` -- the
authority, because that id names a FILE server-side.

TypeScript: frontend/src/schema-forms/utils/resumeFromPdf.ts `isSafeSessionId`
-- a mirror, because the client reads a hand-editable PDF and must not adopt a
hostile id as its own session identity before ever contacting the server.

DUPLICATION IS DELIBERATE (a browser cannot import the Python), so the risk is
DRIFT: someone hardens one side and the other silently keeps accepting what it
now rejects. This test derives the TS rules from the shipped source and
asserts they still match the Python -- so tightening either alone fails here.

ASCII only.
"""

import re
from pathlib import Path

import pytest

from backend.utils.confirmation_logger import (
    _FORM_SESSION_ID_RE,
    _WINDOWS_RESERVED,
    _is_safe_session_id,
)

_TS = (
    Path(__file__).resolve().parents[3]
    / "frontend" / "src" / "schema-forms" / "utils" / "resumeFromPdf.ts"
)

pytestmark = pytest.mark.skipif(not _TS.exists(), reason="frontend source absent")


def _ts_source() -> str:
    return _TS.read_text(encoding="utf-8")


def test_the_CHARSET_and_length_bound_match():
    src = _ts_source()
    m = re.search(r"const SESSION_ID_RE = /\^(.+?)\$/;", src)
    assert m, "the TS mirror no longer declares SESSION_ID_RE"
    ts_pattern = m.group(1)
    py_pattern = _FORM_SESSION_ID_RE.pattern
    assert ts_pattern == py_pattern, (
        "the session-id charset drifted between the Python guard and its TS "
        f"mirror: python={py_pattern!r} ts={ts_pattern!r}"
    )


def test_the_WINDOWS_DEVICE_NAMES_match():
    src = _ts_source()
    block = re.search(
        r"const WINDOWS_DEVICE_NAMES = new Set\(\[(.*?)\]\);", src, re.S
    )
    assert block, "the TS mirror no longer declares WINDOWS_DEVICE_NAMES"
    ts_names = set(re.findall(r"'([A-Z0-9]+)'", block.group(1)))
    assert ts_names == set(_WINDOWS_RESERVED), (
        "the reserved-name sets drifted: "
        f"python-only={set(_WINDOWS_RESERVED) - ts_names}, "
        f"ts-only={ts_names - set(_WINDOWS_RESERVED)}"
    )


def test_the_TS_mirror_still_checks_every_RULE_the_python_does():
    """The rules that are code, not data.

    Each was reached by adversarially attacking the Python guard rather than
    by reasoning about it -- the device names and trailing dots both passed
    its first version -- so a mirror that quietly drops one is a real hole.
    """
    src = _ts_source()
    assert "includes('..')" in src, "TS mirror lost the '..' traversal check"
    assert "endsWith('.')" in src, (
        "TS mirror lost the trailing-dot check (Windows strips trailing dots, "
        "so 'x.' and 'x' collide)"
    )
    assert "SESSION_ID_RE.test" in src, "TS mirror lost the charset check"
    assert "WINDOWS_DEVICE_NAMES.has" in src, "TS mirror lost the device-name check"


@pytest.mark.parametrize(
    "hostile",
    [
        "../../../etc/passwd", "fss/../secret", "..",
        "CON", "PRN", "NUL", "COM1", "LPT9", "con", "Com1",
        "trailing.", "...", "", "a" * 129, "has space", "semi;colon",
    ],
)
def test_the_PYTHON_guard_refuses_what_the_mirror_must_also_refuse(hostile):
    """Pins the shared REFUSAL set from the authoritative side.

    The TS mirror is checked structurally above; this pins the behavior these
    inputs must produce, so a Python-side loosening is caught too.
    """
    assert _is_safe_session_id(hostile) is False


@pytest.mark.parametrize(
    "ok",
    ["fss_1756000000_abc", "fss-1", "a", "A.B_c-1", "a" * 128],
)
def test_the_PYTHON_guard_accepts_ordinary_session_ids(ok):
    """The other half: a guard that refuses everything would pass the tests
    above while breaking every resume."""
    assert _is_safe_session_id(ok) is True
