"""On a deployed instance (K_SERVICE is set by Cloud Run) no env knob may
raise the log volume into payload territory (bd polyglot-pdf-wfgjz, sprint
23 B1a). Three guards, each pinned on its own layer:

  1. configure_logging never runs below INFO with K_SERVICE set, whatever
     LOG_LEVEL says, and the noisy library loggers stay capped at WARNING.
  2. Settings forces the two local-dev dump knobs (LIVE_DEV_TRANSCRIPTS,
     LIVE_DEV_AUDIO_DUMP) off with K_SERVICE set.
  3. No backend source reads the library verbosity env names at all, so
     there is nothing for a deploy to set.
"""
import logging
import pathlib
import re

import pytest


def _repo_root() -> pathlib.Path:
    p = pathlib.Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "backend" / "utils").is_dir():
            return parent
    raise AssertionError("repo root not found")


REPO_ROOT = _repo_root()


@pytest.fixture
def restored_logging():
    root = logging.getLogger()
    saved = (list(root.handlers), root.level)
    saved_noisy = {n: logging.getLogger(n).level for n in ("httpx", "uvicorn.access", "websockets")}
    yield
    root.handlers, root.level = saved[0], saved[1]
    for n, lvl in saved_noisy.items():
        logging.getLogger(n).setLevel(lvl)
    import structlog
    structlog.reset_defaults()


def test_deployed_instance_never_logs_below_info(monkeypatch, restored_logging):
    """Mutation-verified by deleting the K_SERVICE clamp in configure_logging."""
    from backend.utils.logging import configure_logging

    monkeypatch.setenv("K_SERVICE", "polyglot-backend")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    configure_logging()
    assert logging.getLogger().level == logging.INFO
    for name in ("httpx", "uvicorn.access", "websockets"):
        assert logging.getLogger(name).level == logging.WARNING, name


def test_local_dev_keeps_log_level_free(monkeypatch, restored_logging):
    from backend.utils.logging import configure_logging

    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    configure_logging()
    assert logging.getLogger().level == logging.DEBUG


def test_deployed_instance_forces_the_dump_knobs_off(monkeypatch):
    """Mutation-verified by deleting the K_SERVICE block in Settings._resolve_model."""
    from backend.config import Settings

    monkeypatch.setenv("K_SERVICE", "polyglot-backend")
    monkeypatch.setenv("VERTEXAI", "true")
    # The field defaults are read from the env at import time, so the knobs
    # are passed explicitly: this is the value a deploy would carry.
    s = Settings(LIVE_DEV_TRANSCRIPTS=True, LIVE_DEV_AUDIO_DUMP=True)
    assert s.LIVE_DEV_TRANSCRIPTS is False
    assert s.LIVE_DEV_AUDIO_DUMP is False


def test_local_dev_can_turn_the_dump_knobs_on(monkeypatch):
    from backend.config import Settings

    monkeypatch.delenv("K_SERVICE", raising=False)
    s = Settings(LIVE_DEV_TRANSCRIPTS=True, LIVE_DEV_AUDIO_DUMP=True)
    assert s.LIVE_DEV_TRANSCRIPTS is True
    assert s.LIVE_DEV_AUDIO_DUMP is True


# Verbosity / debug env names that would echo payloads (or forward transcripts)
# if the backend honoured them. Backend source may read one ONLY inside a
# statement gated on K_SERVICE being absent.
_VERBOSITY_KNOBS = ("HTTPX_LOG_LEVEL", "SEND_TRANSCRIPT", "GOOGLE_GENAI_DEBUG",
                    "GOOGLE_GENAI_LOG", "GOOGLE_SDK_PYTHON_LOGGING_SCOPE")


def _backend_sources():
    for base in ("backend", "admin_backend"):
        for p in (REPO_ROOT / base).rglob("*.py"):
            parts = p.relative_to(REPO_ROOT).parts
            if "tests" in parts or ".venv" in parts or "scripts" in parts:
                continue
            yield p


def test_no_backend_source_reads_a_library_verbosity_knob():
    names = "|".join(re.escape(k) for k in _VERBOSITY_KNOBS)
    # An env READ of the knob (getenv / environ[...] / environ.get), not a
    # mention in a comment or docstring.
    pattern = re.compile(r"(?:getenv|environ(?:\.get)?)\s*[\(\[]\s*[\"'](?:" + names + r")[\"']")
    offenders = []
    scanned = 0
    for p in _backend_sources():
        scanned += 1
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, line in enumerate(lines, 1):
            if not pattern.search(line):
                continue
            # A read is allowed only when the same statement is gated on
            # K_SERVICE (the harness knob in websocket_routes is local-only).
            stmt = " ".join(lines[max(0, i - 3):i + 2])
            if "K_SERVICE" not in stmt:
                offenders.append("%s:%d" % (p.relative_to(REPO_ROOT).as_posix(), i))
    assert scanned > 50, "source scan is vacuous"
    assert not offenders, "backend source honours a verbosity knob: " + repr(offenders)
