"""scripts/audit/inventory_stores.py CLI contract (bd polyglot-pdf-uaxt5,
sprint 23 workstream A).

EXIT CRITERION 1 lives here: the script never prints a stored VALUE (only
key names, value types, max string length, and counts), and it flags any
key outside a collection's pinned allowlist.

Pins:
- --project is required (argparse-level) and the DEAD_PROJECTS refusal
  aborts before any Firestore/GCS/BigQuery call;
- a resolved-project mismatch aborts with exit 2, mirroring
  scripts/grant_credits.py's identical guard;
- the summarizer NEVER carries a document's actual value anywhere in its
  output -- pinned by feeding it a document with a distinctive value and
  asserting that literal string is absent from the summary's repr;
- a key outside PINNED_ALLOWLISTS is reported in flagged_keys;
- a key inside the allowlist is never flagged (pin both directions, scar #9).

The CLI is driven as main([...]) matching grant_credits.py's own pattern, so
no module-reload/argv-monkeypatch fixture is needed.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.audit.inventory_stores as inv  # noqa: E402

PROJECT = "polyglot-demo-aa709"


class _FakeApp:
    def __init__(self, project_id):
        self.project_id = project_id


@pytest.fixture
def firebase_stub(monkeypatch):
    """Pretend firebase_admin is already initialized for PROJECT -- mirrors
    test_grant_credits_cli.py's identical fixture."""
    import firebase_admin
    monkeypatch.setattr(firebase_admin, "_apps", {"[DEFAULT]": object()},
                        raising=False)
    monkeypatch.setattr(firebase_admin, "get_app",
                        lambda: _FakeApp(PROJECT), raising=False)
    return firebase_admin


# --------------------------------------------------------------------------
# Refusal gates -- must fire BEFORE any store is touched.
# --------------------------------------------------------------------------

def test_dead_project_is_refused_before_any_call(monkeypatch):
    """Mutation: drop the DEAD_PROJECTS check from main() -- this goes red,
    since _init_firebase_admin would then be reached and raise/hang on a
    genuinely dead project instead of returning a clean exit 2."""
    called = {"init": False}
    monkeypatch.setattr(inv, "_init_firebase_admin",
                        lambda project: called.__setitem__("init", True))
    code = inv.main(["--project", "polyglot-forms-919f2"])
    assert code == 2
    assert called["init"] is False


def test_project_mismatch_aborts_with_exit_2(firebase_stub):
    """The resolved firebase_admin project ({}) differs from --project
    (a different demo-shaped name) -- must abort, never silently query the
    resolved project instead of the one the operator named.

    Mutation: drop the resolved != args.project check in
    _init_firebase_admin -- this goes red, continuing past the mismatch.
    """.format(PROJECT)
    code = inv.main(["--project", "some-other-project"])
    assert code == 2


def test_missing_project_flag_is_a_usage_error():
    with pytest.raises(SystemExit) as exc:
        inv.main([])
    assert exc.value.code == 2


# --------------------------------------------------------------------------
# The redaction property -- the load-bearing guarantee of this script.
# --------------------------------------------------------------------------

class _FakeDoc:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return dict(self._data)


_SENTINEL_VALUE = "TOP SECRET A-NUMBER A123456789 SHOULD NEVER BE PRINTED"


def test_summarize_docs_never_carries_the_value_anywhere():
    """Feed a document containing a distinctive, sentinel-shaped value and
    prove it is nowhere in the summary's repr -- not in a nested dict, not
    truncated, not partially present. This is the property the whole
    script depends on; the redaction happens at the summarizer, not at the
    print statements, so this test targets the ACTUAL choke point.

    Mutation: change `entry["max_str_len"] = max(cur, len(value))` to also
    stash `value` itself (e.g. a debug "sample" field) -- this goes red.
    """
    docs = [_FakeDoc({
        "field_id": "p1_line1_aliennumber",
        "value": _SENTINEL_VALUE,
        "count": 3,
    })]
    summary = inv._summarize_docs(docs, allowlist=frozenset({"field_id", "count"}))
    assert _SENTINEL_VALUE not in repr(summary)
    # The key IS reported (it is outside the allowlist -- flagged, not
    # hidden), but only the key name, type and length -- never the string.
    assert "value" in summary["keys"]
    assert summary["keys"]["value"]["types"] == ["str"]
    assert summary["keys"]["value"]["max_str_len"] == len(_SENTINEL_VALUE)
    assert "value" in summary["flagged_keys"]


def test_summarize_docs_flags_a_key_outside_the_allowlist():
    docs = [_FakeDoc({"field_id": "f1", "unexpected_key": "x"})]
    summary = inv._summarize_docs(docs, allowlist=frozenset({"field_id"}))
    assert summary["flagged_keys"] == ["unexpected_key"]


def test_summarize_docs_does_not_flag_an_allowlisted_key():
    """Pin the other direction (scar #9): an allowlisted key must never be
    reported as flagged, or every real deployment would show false
    positives on every key."""
    docs = [_FakeDoc({"field_id": "f1", "count": 1})]
    summary = inv._summarize_docs(
        docs, allowlist=frozenset({"field_id", "count"}))
    assert summary["flagged_keys"] == []


def test_summarize_docs_with_no_allowlist_reports_but_never_flags():
    """allowlist=None (an unmanaged store, e.g. authorized_emails or kits)
    reports every key but flags none -- a deliberate "I have nothing to
    compare against" mode, distinct from an EMPTY frozenset allowlist
    (every key flagged, e.g. authorized_emails' own PINNED_ALLOWLISTS
    entry) which means "this store is pinned to write NOTHING"."""
    docs = [_FakeDoc({"anything": "goes"})]
    summary = inv._summarize_docs(docs, allowlist=None)
    assert "anything" in summary["keys"]
    assert summary["flagged_keys"] == []


def test_an_empty_pinned_allowlist_flags_every_key():
    """The authorized_emails case: PINNED_ALLOWLISTS maps it to an EMPTY
    frozenset (no code-side writer in this repo to copy a shape from), so
    every key it carries must be reported as outside the allowlist -- never
    silently treated as "nothing to check"."""
    docs = [_FakeDoc({"email": "someone@example.com"})]
    summary = inv._summarize_docs(docs, allowlist=frozenset())
    assert summary["flagged_keys"] == ["email"]


# --------------------------------------------------------------------------
# gcloud/bq invocation -- resolved through shutil.which (Windows trap).
# --------------------------------------------------------------------------

def test_run_resolves_the_executable_through_shutil_which(monkeypatch):
    """Mutation: call subprocess.run(argv, ...) directly with the bare
    argv[0] -- this goes red on the assertion that _resolve_exe was
    consulted, and would raise WinError 2 for real on a bare "gcloud" on
    Windows CI."""
    seen = {}

    def fake_which(name):
        seen["asked"] = name
        return "/resolved/path/to/" + name

    monkeypatch.setattr(inv.shutil, "which", fake_which)

    class _FakeCompleted:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(argv, **kwargs):
        seen["argv0"] = argv[0]
        return _FakeCompleted()

    monkeypatch.setattr(inv.subprocess, "run", fake_run)

    inv._run(["gcloud", "storage", "ls"])
    assert seen["asked"] == "gcloud"
    assert seen["argv0"] == "/resolved/path/to/gcloud"


def test_run_survives_a_missing_executable(monkeypatch):
    """An OSError from a genuinely missing binary must be reported as a
    failed run (code 127), never raise out of the script -- a report with
    one unreachable store beats a traceback."""
    monkeypatch.setattr(inv.shutil, "which", lambda name: None)

    def fake_run(argv, **kwargs):
        raise OSError("not found")

    monkeypatch.setattr(inv.subprocess, "run", fake_run)

    code, out, err = inv._run(["definitely-not-a-real-binary"])
    assert code == 127
    assert "not found" in err


# --------------------------------------------------------------------------
# Every PINNED_ALLOWLISTS entry must be a frozenset or the None sentinel --
# a plain set or list would allow a silent mutation of the pin at runtime.
# --------------------------------------------------------------------------

def test_every_pinned_allowlist_is_a_frozenset_or_none():
    for name, allowlist in inv.PINNED_ALLOWLISTS.items():
        assert allowlist is None or isinstance(allowlist, frozenset), (
            "{}'s allowlist is {!r} -- must be a frozenset (immutable pin) "
            "or None (deliberate report-only mode)".format(name, type(allowlist))
        )
