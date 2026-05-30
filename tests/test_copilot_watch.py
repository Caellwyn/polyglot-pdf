"""Tests for scripts/copilot_watch.py.

Imports the script as a module (repo precedent: test_doc_freshness.py,
test_reset_dev_db_script.py) and exercises the pure classification logic
without hitting the network. The round-scoping tests monkeypatch
`_run_gh_api` so no `gh` call is made.
"""

import datetime
import importlib.util
import pathlib
import sys

import pytest


SCRIPT_PATH = (
    pathlib.Path(__file__).resolve().parent.parent / "scripts" / "copilot_watch.py"
)
spec = importlib.util.spec_from_file_location("copilot_watch", SCRIPT_PATH)
cw = importlib.util.module_from_spec(spec)
sys.modules["copilot_watch"] = cw
spec.loader.exec_module(cw)

UTC = datetime.timezone.utc


# --- author detection (finding #1: must NOT match generic actions bot) ---

@pytest.mark.parametrize(
    "login,expected",
    [
        ("copilot-pull-request-reviewer[bot]", True),
        ("Copilot", True),
        ("github-actions[bot]", False),
        ("dependabot[bot]", False),
        ("some-human", False),
        ("", False),
    ],
)
def test_is_copilot(login, expected):
    assert cw._is_copilot(login) is expected


# --- exit-code contract (finding #5: TIMEOUT distinct from ERROR) ---

def test_exit_code_map():
    assert cw._EXIT_CODES == {"COMMENTS": 0, "CLEAN": 0, "TIMEOUT": 2, "ERROR": 1}


@pytest.mark.parametrize(
    "state,code", [("COMMENTS", 0), ("CLEAN", 0), ("TIMEOUT", 2), ("ERROR", 1)]
)
def test_emit_returns_matching_exit_code(state, code, capsys):
    assert cw._emit(state, "detail") == code
    out = capsys.readouterr().out
    assert "RESULT: {}".format(state) in out


class _Cp1252Stdout:
    """A stdout stand-in that behaves like a Windows cp1252 console: its
    write() raises UnicodeEncodeError on any non-cp1252 char (e.g. an emoji),
    exactly as the real crash did. Captures what survives so tests can assert
    the fallback actually emitted the contract line."""

    encoding = "cp1252"

    def __init__(self):
        self.captured = ""

    def write(self, s):
        s.encode("cp1252")  # raises UnicodeEncodeError on un-encodable chars
        self.captured += s
        return len(s)

    def flush(self):
        pass


def test_emit_does_not_crash_on_emoji_detail(monkeypatch):
    # Regression (bead polyglot-pdf-39a): with a real cp1252-style stdout, a
    # Copilot review body containing an emoji must NOT raise UnicodeEncodeError,
    # and the RESULT contract line must still be emitted (degraded, not lost).
    fake = _Cp1252Stdout()
    monkeypatch.setattr(sys, "stdout", fake)
    detail = "Copilot says: \U0001f4a1 consider X"
    assert cw._emit("COMMENTS", detail) == 0  # must not raise
    # The fallback re-encodes via cp1252/replace, so the emoji becomes '?'
    # but the contract line is intact.
    assert "RESULT: COMMENTS" in fake.captured


def test_safe_print_emits_via_fallback_when_print_cannot_encode(monkeypatch):
    # When the primary print() can't encode (cp1252 stdout + emoji), the
    # fallback must still WRITE a degraded line -- not silently swallow it.
    fake = _Cp1252Stdout()
    monkeypatch.setattr(sys, "stdout", fake)
    cw._safe_print("has emoji \U0001f4a1 and text")  # must not raise
    assert "has emoji" in fake.captured
    assert "and text" in fake.captured


# --- timestamp floor (findings #2/#8: prior-round items excluded) ---

def test_after_floor():
    floor = datetime.datetime(2026, 5, 28, tzinfo=UTC)
    assert cw._after("2026-05-29T00:00:00Z", floor) is True   # after floor
    assert cw._after("2026-05-01T00:00:00Z", floor) is False  # before floor
    assert cw._after("", floor) is True                       # unparseable -> include
    assert cw._after("2026-05-29T00:00:00Z", None) is True    # no floor


# --- inline-comment scoping by review_id (Copilot finding on PR #383) ---

def _patch_api(monkeypatch, reviews=None, inline=None, issue=None,
               timeline=None, pr_state="open"):
    """Route _run_gh_api by endpoint suffix to canned payloads."""
    def fake(path):
        if path.endswith("/timeline"):
            return timeline or []
        if path.endswith("/reviews"):
            return reviews or []
        if "/pulls/" in path and path.endswith("/comments"):
            return inline or []
        if "/issues/" in path and path.endswith("/comments"):
            return issue or []
        # bare PR object (state lookup)
        return {"state": pr_state}
    monkeypatch.setattr(cw, "_run_gh_api", fake)


def _reviewed_event(when="2026-05-28T12:00:01Z"):
    return {"event": "reviewed", "actor": {"login": "Copilot"}, "submitted_at": when}


def _run_watch_result(capsys, monkeypatch, **api):
    """Run watch() and return (exit_code, RESULT-state-string)."""
    _patch_api(monkeypatch, **api)
    rc = cw.watch("o/r", 1, timeout_min=1, poll_sec=0, since=None)
    out = capsys.readouterr().out
    result = None
    for line in out.splitlines():
        if line.startswith("RESULT: "):
            result = line.split("RESULT: ", 1)[1].strip()
    return rc, result


def test_inline_matched_by_review_id_not_timestamp(monkeypatch):
    # Inline comment was CREATED before the review was SUBMITTED (Copilot's
    # real behavior). A timestamp floor at submitted_at would drop it; the
    # review_id match must still include it.
    review = {
        "id": 555,
        "state": "COMMENTED",
        "submitted_at": "2026-05-28T12:00:05Z",
        "body": "",
        "user": {"login": "Copilot"},
    }
    inline = [
        {
            "user": {"login": "Copilot"},
            "pull_request_review_id": 555,
            "created_at": "2026-05-28T12:00:00Z",  # 5s BEFORE submit
            "path": "app/x.py",
            "line": 10,
            "body": "same-round finding",
        }
    ]
    _patch_api(monkeypatch, inline=inline)
    floor = cw._parse_iso(review["submitted_at"])
    findings = cw._collect_findings("o/r", 1, floor, review)
    assert any("same-round finding" in f for f in findings)


def test_inline_from_other_review_id_excluded(monkeypatch):
    review = {"id": 555, "state": "COMMENTED", "submitted_at": "2026-05-28T12:00:00Z",
              "body": "", "user": {"login": "Copilot"}}
    inline = [
        {
            "user": {"login": "Copilot"},
            "pull_request_review_id": 111,  # a DIFFERENT (prior) round
            "created_at": "2026-05-28T12:00:01Z",
            "path": "app/x.py", "line": 1, "body": "stale finding",
        }
    ]
    _patch_api(monkeypatch, inline=inline)
    findings = cw._collect_findings("o/r", 1, None, review)
    assert not any("stale finding" in f for f in findings)


# watch() tests assert on the RESULT line, not just rc -- CLEAN and COMMENTS
# both exit 0, so rc alone can't distinguish them (Copilot finding tests:147).

def test_clean_when_review_has_no_findings(capsys, monkeypatch):
    review = {"id": 9, "state": "APPROVED", "submitted_at": "2026-05-28T12:00:00Z",
              "body": "", "user": {"login": "Copilot"}}
    rc, result = _run_watch_result(
        capsys, monkeypatch, reviews=[review], timeline=[_reviewed_event()]
    )
    assert (rc, result) == (0, "CLEAN")


def test_comments_when_review_body_present(capsys, monkeypatch):
    review = {"id": 9, "state": "CHANGES_REQUESTED", "submitted_at": "2026-05-28T12:00:00Z",
              "body": "please fix X", "user": {"login": "Copilot"}}
    rc, result = _run_watch_result(
        capsys, monkeypatch, reviews=[review], timeline=[_reviewed_event()]
    )
    assert (rc, result) == (0, "COMMENTS")


def test_changes_requested_empty_body_is_comments_not_clean(capsys, monkeypatch):
    # A non-APPROVED terminal state is a verdict even with no body/findings.
    review = {"id": 9, "state": "CHANGES_REQUESTED", "submitted_at": "2026-05-28T12:00:00Z",
              "body": "", "user": {"login": "Copilot"}}
    rc, result = _run_watch_result(
        capsys, monkeypatch, reviews=[review], timeline=[_reviewed_event()]
    )
    assert (rc, result) == (0, "COMMENTS")


def test_error_body_classifies_as_error(capsys, monkeypatch):
    review = {"id": 9, "state": "COMMENTED", "submitted_at": "2026-05-28T12:00:00Z",
              "body": "Copilot encountered an error and was unable to review this PR.",
              "user": {"login": "Copilot"}}
    rc, result = _run_watch_result(
        capsys, monkeypatch, reviews=[review], timeline=[_reviewed_event()]
    )
    assert (rc, result) == (1, "ERROR")


def test_finished_work_no_review_is_clean(capsys, monkeypatch):
    # copilot_work_finished with no `reviewed` event -> CLEAN (done, nothing).
    timeline = [{"event": "copilot_work_finished", "created_at": "2026-05-28T12:00:00Z"}]
    rc, result = _run_watch_result(capsys, monkeypatch, timeline=timeline)
    assert (rc, result) == (0, "CLEAN")


def test_working_then_deadline_is_timeout(capsys, monkeypatch):
    # copilot_work_started but no terminal event -> keep waiting, then TIMEOUT.
    timeline = [{"event": "copilot_work_started", "created_at": "2026-05-28T12:00:00Z"}]
    _patch_api(monkeypatch, timeline=timeline)
    rc = cw.watch("o/r", 1, timeout_min=0, poll_sec=0, since=None)
    out = capsys.readouterr().out
    assert rc == 2 and "RESULT: TIMEOUT" in out and "started but not finished" in out


def test_timeline_state_detection(monkeypatch):
    _patch_api(monkeypatch, timeline=[_reviewed_event()])
    assert cw._timeline_state("o/r", 1, None) == "reviewed"
    _patch_api(monkeypatch, timeline=[{"event": "copilot_work_finished",
                                       "created_at": "2026-05-28T12:00:00Z"}])
    assert cw._timeline_state("o/r", 1, None) == "finished"
    _patch_api(monkeypatch, timeline=[{"event": "copilot_work_started",
                                       "created_at": "2026-05-28T12:00:00Z"}])
    assert cw._timeline_state("o/r", 1, None) == "working"
    _patch_api(monkeypatch, timeline=[])
    assert cw._timeline_state("o/r", 1, None) is None


def test_latest_review_wins(monkeypatch):
    older = {"id": 1, "state": "COMMENTED", "submitted_at": "2026-05-28T10:00:00Z",
             "body": "old", "user": {"login": "Copilot"}}
    newer = {"id": 2, "state": "APPROVED", "submitted_at": "2026-05-28T12:00:00Z",
             "body": "new", "user": {"login": "Copilot"}}
    _patch_api(monkeypatch, reviews=[older, newer])
    latest = cw._latest_copilot_review("o/r", 1, None)
    assert latest["id"] == 2
