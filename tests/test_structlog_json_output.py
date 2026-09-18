"""Every deployed log line is JSON, from a FRESH import of each real app.

WHY A SUBPROCESS. The bug this pins (bd polyglot-pdf-65jeu) is an IMPORT-ORDER
bug: `structlog.get_logger().bind(...)` at module level froze structlog's
DEFAULT ConsoleRenderer onto that logger, because both apps imported their
route and service modules before calling configure_logging(). In-process
pytest cannot see it -- by the time a test runs, conftest and earlier imports
have already configured structlog, and structlog's configuration is global
process state that no fixture can honestly rewind to "what a cold container
sees". Only a fresh interpreter that imports backend.main (or
admin_backend.main) the way uvicorn does reproduces the deployed ordering.

WHAT WENT WRONG LIVE (staging, 2026-09-18, build 3c4990170). ledger_export,
form_session_ended, usage_rollup_written and sweep_expired_links_complete all
reached Cloud Logging as textPayload in ConsoleRenderer format. The telemetry
sink filters on jsonPayload.event_type, so none of those rows ever reached
BigQuery: the income view (source: ledger_export) could not be built at all.
The same freeze bypassed pii_safe_exception_processor, so those loggers
rendered exception MESSAGES -- which in this app can embed a field value --
straight into Cloud Logging, breaking the guarantee in
docs/standards/hipaa-pii-policy.md.

WHAT THIS ASSERTS, per app: every line the app emits on stdout/stderr during
import AND from a real module logger parses as JSON; the ledger_export line
carries its event_type (the key the sink filters on); and a sentinel exception
message never appears anywhere in the output.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest


def _repo_root() -> pathlib.Path:
    p = pathlib.Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "backend" / "routes").is_dir():
            return parent
    return p.parent.parent


REPO_ROOT = _repo_root()

# A string no other part of the repo contains, standing in for a field value
# embedded in an exception message.
SENTINEL = "ZZQQ_FIELD_VALUE_SENTINEL_65JEU"

# (app module, logger module to exercise, attribute, event name)
APPS = [
    pytest.param(
        "backend.main",
        "backend.services.credit_ledger",
        "ledger_export",
        id="backend-credit_ledger",
    ),
    pytest.param(
        "admin_backend.main",
        "admin_backend.routes.sweep_routes",
        "sweep_expired_links_complete",
        id="admin-sweep_routes",
    ),
]

_DRIVER = '''
import importlib, sys
import {app}  # noqa: F401  -- the deployed import path, in order
mod = importlib.import_module("{logger_mod}")
log = mod._log
log.info("{event}", event_type="{event}", amount=-1)
try:
    raise ValueError("{sentinel}")
except ValueError:
    log.exception("deliberate_handled_failure")
'''


@pytest.mark.parametrize("app,logger_mod,event", APPS)
def test_app_emits_only_json_and_never_an_exception_message(app, logger_mod, event):
    """A cold import of the real app emits JSON, with no exception message."""
    driver = _DRIVER.format(
        app=app, logger_mod=logger_mod, event=event, sentinel=SENTINEL
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    # Force the CHILD to write UTF-8; the parent decodes UTF-8 below. Without
    # this the child crashes on a non-cp1252 glyph on Windows.
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [sys.executable, "-c", driver],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        # BYTES, decoded by hand below. text=True would decode through the
        # parent's locale (cp1252 on Windows), and the failure mode this test
        # pins emits ANSI colour bytes from structlog's ConsoleRenderer --
        # which raise UnicodeDecodeError in subprocess's reader THREAD, losing
        # the output entirely and turning a real leak into "emitted nothing".
        timeout=180,
    )
    def _text(raw) -> str:
        # errors="replace" so an undecodable byte degrades to U+FFFD instead
        # of throwing: this test must still be able to READ the output when
        # the logging configuration is broken, which is exactly when the bytes
        # are least well-behaved.
        return (raw or b"").decode("utf-8", errors="replace")

    combined = _text(proc.stdout) + _text(proc.stderr)

    # CHECKED FIRST, before the exit-code gate. With the processor chain
    # missing, structlog's unconfigured .exception() re-raises and the
    # interpreter prints the traceback -- message included -- on its way
    # out. That is a PII leak AND a non-zero exit, so asserting the exit
    # code first would report a bare 'driver crashed' and bury the very
    # leak this test exists to catch.
    assert SENTINEL not in combined, (
        "the exception MESSAGE reached the log for {} -- "
        "pii_safe_exception_processor was bypassed, which is the PII half "
        "of bd polyglot-pdf-65jeu. Output:\n{}".format(app, combined)
    )

    assert proc.returncode == 0, (
        "driver failed for {}:\nSTDOUT:\n{}\nSTDERR:\n{}".format(
            app, _text(proc.stdout), _text(proc.stderr)
        )
    )

    lines = [ln for ln in combined.splitlines() if ln.strip()]
    assert lines, "the app emitted nothing at all -- the driver proves nothing"

    # 1. EVERY line is JSON. A ConsoleRenderer line ("2026-09-15 21:38:03
    #    [info     ] ledger_export  amount=-1 ...") fails json.loads, which is
    #    exactly the live symptom.
    records = []
    for line in lines:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pytest.fail(
                "Non-JSON log line from {} -- a logger bound before "
                "configure_logging() kept structlog's ConsoleRenderer, so "
                "this line reaches Cloud Logging as textPayload and never "
                "matches the sink's jsonPayload.event_type filter:\n"
                "  {!r}\nFull output:\n{}".format(app, line, combined)
            )

    # 2. The event the sink filters on is present, with its event_type key.
    matching = [r for r in records if r.get("event") == event]
    assert matching, (
        "no {!r} record in the output of {}; got events {}".format(
            event, app, sorted({r.get("event") for r in records})
        )
    )
    assert any(r.get("event_type") == event for r in matching), (
        "the {!r} line carries no event_type key -- the telemetry sink "
        "filters on jsonPayload.event_type, so it would never be "
        "exported".format(event)
    )

    # 3. The exception rendered as TYPE + FRAMES (the message itself was
    #    already checked above, ahead of the exit-code gate).
    failures = [r for r in records if r.get("event") == "deliberate_handled_failure"]
    assert failures, "the handled exception produced no record at all"
    assert any(r.get("error_type") == "ValueError" for r in failures), (
        "the exception record carries no error_type; got {}".format(failures)
    )
    assert any("stack_trace" in r for r in failures), (
        "the exception record carries no stack_trace frames, so Cloud Error "
        "Reporting cannot group it; got {}".format(failures)
    )
