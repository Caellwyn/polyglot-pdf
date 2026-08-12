"""
Tests for scripts/read_confirmations.py's exit-code contract (bd polyglot-pdf-k3v7).

The script documents three exit codes: 0 = events printed, 1 = the query
SUCCEEDED and the session has no events, 2 = RETRIEVAL FAILED (the sink
could not be queried -- NOT evidence the record is absent). Before this
bead, running WITHOUT --firestore (and CONFIRMATION_FIRESTORE_ENABLED
unset -- the normal laptop case) silently fell into exit code 1 having
never queried the durable trail at all, conflating "did not check" with
"checked, found nothing".

ASCII only.
"""
import importlib
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


@pytest.fixture
def read_confirmations_main(monkeypatch):
    """Import (or re-import) the script fresh each test so argv/env changes
    in one test never leak into another via module caching."""
    monkeypatch.delenv("CONFIRMATION_FIRESTORE_ENABLED", raising=False)
    if "scripts.read_confirmations" in sys.modules:
        module = importlib.reload(sys.modules["scripts.read_confirmations"])
    else:
        module = importlib.import_module("scripts.read_confirmations")
    return module.main


def test_omitting_firestore_flag_fails_retrieval_not_reports_no_events(
    read_confirmations_main, monkeypatch, capsys
):
    """The exact regression: no --firestore, CONFIRMATION_FIRESTORE_ENABLED
    unset -> the script must exit 2 (RETRIEVAL FAILED), never the bare
    exit-1 'no events found' that looks like a clean, checked result."""
    monkeypatch.setattr(sys, "argv", ["read_confirmations.py", "fss_never_checked"])

    exit_code = read_confirmations_main()

    captured = capsys.readouterr()
    assert exit_code == 2, (
        "expected RETRIEVAL FAILED (exit 2) when the durable sink was never "
        "consulted; got exit %d -- stdout=%r stderr=%r"
        % (exit_code, captured.out, captured.err)
    )
    assert "NOT evidence the record is absent" in captured.err
    assert "No confirmation events found" not in captured.err


def test_firestore_flag_with_a_working_sink_still_reports_no_events_as_exit_1(
    read_confirmations_main, monkeypatch, capsys
):
    """A GENUINELY empty durable trail (sink enabled, query succeeds, zero
    events) must still be exit 1 -- this bead narrows the false-clean case,
    it must not turn every empty result into a false failure."""
    monkeypatch.setattr(
        sys, "argv", ["read_confirmations.py", "fss_really_empty", "--firestore"]
    )

    class _EmptyDB:
        def collection(self, name):
            return self

        def where(self, *a, **kw):
            return self

        def stream(self):
            return iter(())

    monkeypatch.setattr("backend.services.auth.get_db", lambda: _EmptyDB())

    exit_code = read_confirmations_main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "No confirmation events found" in captured.err
