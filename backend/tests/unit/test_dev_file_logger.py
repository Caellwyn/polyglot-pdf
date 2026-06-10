"""
PII-never-logged guard for DevFileLogger.log_error (bd polyglot-pdf-p84m).

The unconditional terminal write in log_error reaches stdout/stderr -> Cloud Run
-> Cloud Logging in PRODUCTION. A caller may pass str(exception) as error_message,
and an exception string can embed the field value the failing code was handling.
So the always-on terminal line must carry only the error_TYPE (a class/category
name), NEVER error_message. The full message + context still go to the
_write_to_file entry, which is gated on self.enabled (dev-only).

RED-FIRST: against the pre-p84m sink, the terminal line was
"[error] ERROR [{type}]: {message}" -- so a PII substring in error_message DID
appear on the always-on terminal write. These assert it no longer does.
"""
import sys

from backend.utils.dev_file_logger import DevFileLogger


# A sentinel that stands in for a field value an exception string might embed,
# e.g. ValueError("could not parse SSN 123-45-6789").
_PII_SENTINEL = "PII_SENTINEL_123_45_6789"


def _capture_log_error(capsys, *, enabled: bool):
    """Run log_error with the dev flag forced to `enabled` and return the captured
    (stdout, stderr)."""
    logger = DevFileLogger()
    # Force the gate regardless of whether backend/.env.DEV exists in this env, so
    # the test is deterministic. enabled=False simulates production.
    logger.enabled = enabled
    logger.log_error(
        error_type="tool_callback_error",
        error_message=f"could not handle value {_PII_SENTINEL}",
        context={"tool_name": "update_form_fields", "arguments": {"ssn": _PII_SENTINEL}},
    )
    return capsys.readouterr()


def test_log_error_terminal_omits_pii_in_production(capsys):
    """With dev logging OFF (production), the unconditional terminal write must NOT
    contain the exception message / PII -- only the error type."""
    captured = _capture_log_error(capsys, enabled=False)
    combined = captured.out + captured.err

    # The error TYPE is allowed (it is a category name, never PII).
    assert "tool_callback_error" in combined
    # The PII substring (from error_message AND context) must NOT appear.
    assert _PII_SENTINEL not in combined


def test_log_error_terminal_omits_pii_even_in_dev(capsys):
    """Even with dev logging ON, the TERMINAL line itself carries only the type.

    (Dev mode additionally writes the full message+context to the gated FILE sink,
    which is local-only and out of scope here -- we assert the terminal contract.)
    """
    captured = _capture_log_error(capsys, enabled=True)
    # stderr is where ERROR-severity terminal writes go.
    assert "tool_callback_error" in (captured.out + captured.err)
    # The terminal write does not interpolate error_message, so the sentinel must
    # not be on the terminal line. (The file sink is not stdout/stderr.)
    terminal_error_lines = [
        ln for ln in (captured.out + captured.err).splitlines()
        if "[error] ERROR" in ln
    ]
    assert terminal_error_lines, "expected an ERROR terminal line"
    for ln in terminal_error_lines:
        assert _PII_SENTINEL not in ln
