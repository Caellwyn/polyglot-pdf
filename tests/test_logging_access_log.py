"""uvicorn.access must never log at INFO (bd polyglot-pdf-6rj0j, sprint 23 B0).

The one guard the container-level `--no-access-log` flag does not cover is a
uvicorn started WITHOUT that flag (a local launcher, a future deploy script
that rebuilds the CMD). configure_logging() therefore caps the
`uvicorn.access` logger at WARNING like every other noisy library logger,
so an access line -- which carries the full request target, including the
`?token=` credential on /ws/fill -- is dropped at INFO wherever the app
runs. The Dockerfile flag is pinned separately in
tests/test_dockerfile_app_module.py; each layer fails on its own.

Mutation: restore `logging.getLogger("uvicorn.access").setLevel(logging.INFO)`
at the end of configure_logging() -> both assertions go red.
"""
import logging

import pytest

from backend.utils.logging import configure_logging


@pytest.fixture
def restored_uvicorn_access():
    """Snapshot uvicorn.access and put it back, so this test leaves no
    process-wide logger state behind for a later test to trip over."""
    access = logging.getLogger("uvicorn.access")
    saved = (access.level, list(access.handlers), access.propagate)
    yield access
    access.setLevel(saved[0])
    access.handlers = saved[1]
    access.propagate = saved[2]


def test_configure_logging_caps_uvicorn_access_at_warning(restored_uvicorn_access):
    configure_logging()
    access = logging.getLogger("uvicorn.access")
    assert access.level >= logging.WARNING, (
        "uvicorn.access is at level {} after configure_logging(); an INFO "
        "access line carries the /ws/fill?token= credential into Cloud "
        "Logging".format(logging.getLevelName(access.level)))
    assert not access.isEnabledFor(logging.INFO), (
        "uvicorn.access still accepts INFO records after configure_logging()")


# --- the OTHER line that carries the request target ----------------------------------
# uvicorn's WebSocket protocol logs '<client> - "WebSocket <path?query>" [accepted]'
# at INFO on the `uvicorn.error` logger (uvicorn/protocols/websockets/*_impl.py),
# NOT on uvicorn.access -- so --no-access-log does not cover it, and until the
# deprecated ?token= form is retired (sprint 23 C2, bd polyglot-pdf-0j8e5) that
# line carries a live credential. The `uvicorn.error` entry in noisy_loggers is
# the only guard. Found by F2's outer review (bd polyglot-pdf-cwiip).
# Mutation: drop "uvicorn.error" from noisy_loggers -> red.


@pytest.fixture
def restored_uvicorn_error():
    err = logging.getLogger("uvicorn.error")
    saved = err.level
    yield
    err.setLevel(saved)


def test_configure_logging_caps_uvicorn_error_at_warning_too(restored_uvicorn_error):
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    configure_logging()
    err = logging.getLogger("uvicorn.error")
    assert err.level >= logging.WARNING, (
        "uvicorn.error is at level {} after configure_logging(); its INFO "
        "'WebSocket <path?query> [accepted]' line carries the request target".format(err.level))
    assert not err.isEnabledFor(logging.INFO), (
        "uvicorn.error still accepts INFO records after configure_logging()")
