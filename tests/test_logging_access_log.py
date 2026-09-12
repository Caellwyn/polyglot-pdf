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

from backend.utils.logging import configure_logging


def test_configure_logging_caps_uvicorn_access_at_warning():
    configure_logging()
    access = logging.getLogger("uvicorn.access")
    assert access.level >= logging.WARNING, (
        "uvicorn.access is at level {} after configure_logging(); an INFO "
        "access line carries the /ws/fill?token= credential into Cloud "
        "Logging".format(logging.getLevelName(access.level)))
    assert not access.isEnabledFor(logging.INFO), (
        "uvicorn.access still accepts INFO records after configure_logging()")
