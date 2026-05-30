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


# --- bd polyglot-pdf-6xp: stale-comment loop fixes ---
# Repro shape from PR #21: a COMMENTED review whose sole inline comment went
# OUTDATED (position null) after the fix commit, plus Copilot's re-review
# approval delivered as an ISSUE COMMENT (no formal review). The pre-fix
# watcher re-emitted the outdated comment as COMMENTS forever.

def test_outdated_inline_comment_dropped_yields_clean(capsys, monkeypatch):
    # Fix B1: an inline comment with position == null is outdated; dropping it
    # leaves no findings, and a COMMENTED state (not CHANGES_REQUESTED) is CLEAN.
    review = {"id": 555, "state": "COMMENTED", "submitted_at": "2026-05-28T12:00:00Z",
              "body": "", "user": {"login": "Copilot"}}
    inline = [{
        "user": {"login": "Copilot"}, "pull_request_review_id": 555,
        "created_at": "2026-05-28T12:00:00Z", "path": "CLAUDE.md",
        "position": None, "line": None, "original_line": 107,
        "body": "stale round-1 objection",
    }]
    rc, result = _run_watch_result(
        capsys, monkeypatch, reviews=[review], inline=inline,
        timeline=[_reviewed_event()],
    )
    assert (rc, result) == (0, "CLEAN")


def test_live_inline_comment_nonnull_position_still_comments(capsys, monkeypatch):
    # Anti-false-negative: a genuine round-2 finding lands on the current diff
    # with a non-null position -> still COMMENTS, never dropped.
    review = {"id": 556, "state": "COMMENTED", "submitted_at": "2026-05-28T12:00:00Z",
              "body": "", "user": {"login": "Copilot"}}
    inline = [{
        "user": {"login": "Copilot"}, "pull_request_review_id": 556,
        "created_at": "2026-05-28T12:00:00Z", "path": "app/x.py",
        "position": 12, "line": 42, "body": "real new finding",
    }]
    rc, result = _run_watch_result(
        capsys, monkeypatch, reviews=[review], inline=inline,
        timeline=[_reviewed_event()],
    )
    assert (rc, result) == (0, "COMMENTS")


def test_changes_requested_with_only_outdated_comment_still_comments(capsys, monkeypatch):
    # State must win: a CHANGES_REQUESTED verdict stays COMMENTS even if its
    # only inline comment is outdated (position null). The outdated-drop must
    # not launder a change-request to CLEAN.
    review = {"id": 557, "state": "CHANGES_REQUESTED", "submitted_at": "2026-05-28T12:00:00Z",
              "body": "", "user": {"login": "Copilot"}}
    inline = [{
        "user": {"login": "Copilot"}, "pull_request_review_id": 557,
        "created_at": "2026-05-28T12:00:00Z", "path": "app/x.py",
        "position": None, "line": None, "body": "outdated but state is CR",
    }]
    rc, result = _run_watch_result(
        capsys, monkeypatch, reviews=[review], inline=inline,
        timeline=[_reviewed_event()],
    )
    assert (rc, result) == (0, "COMMENTS")


def test_issue_comment_approval_round_is_clean_not_timeout(capsys, monkeypatch):
    # Fix A: the round's verdict is a Copilot ISSUE COMMENT (no in-window
    # review). Pre-fix this would TIMEOUT (review None -> keep polling). With
    # the issue-comment path, an explicit approval phrase -> CLEAN.
    issue = [{
        "user": {"login": "Copilot"},
        "created_at": "2026-05-28T12:00:05Z",
        "body": "Re-reviewed current HEAD. No further changes are needed on this branch.",
    }]
    rc, result = _run_watch_result(
        capsys, monkeypatch, reviews=[], issue=issue, timeline=[_reviewed_event()],
    )
    assert (rc, result) == (0, "CLEAN")


def test_issue_comment_nonapproval_round_is_comments(capsys, monkeypatch):
    # Fix A risk-mitigation: an issue comment that is NOT an explicit approval
    # stays COMMENTS (never read ambiguity as CLEAN).
    issue = [{
        "user": {"login": "Copilot"},
        "created_at": "2026-05-28T12:00:05Z",
        "body": "One more thing: please also update the changelog.",
    }]
    rc, result = _run_watch_result(
        capsys, monkeypatch, reviews=[], issue=issue, timeline=[_reviewed_event()],
    )
    assert (rc, result) == (0, "COMMENTS")


def test_is_approval_comment():
    assert cw._is_approval_comment("No further changes were needed.")
    assert cw._is_approval_comment("the contract is consistent; no changes needed")
    assert not cw._is_approval_comment("please fix the typo")
    assert not cw._is_approval_comment("")


def test_since_scopes_out_prior_round_review(monkeypatch):
    # Fix C contract: with --since after a round-1 review, that review is
    # excluded from _latest_copilot_review (so a re-watch won't re-detect it).
    round1 = {"id": 1, "state": "COMMENTED", "submitted_at": "2026-05-28T12:00:00Z",
              "body": "round 1", "user": {"login": "Copilot"}}
    _patch_api(monkeypatch, reviews=[round1])
    since = cw._parse_iso("2026-05-28T12:30:00Z")  # after round 1
    assert cw._latest_copilot_review("o/r", 1, since) is None


def test_finished_with_issue_comment_approval_is_clean(capsys, monkeypatch):
    # Fix A via the "finished" branch: after a re-trigger, the timeline shows
    # copilot_work_finished (no new `reviewed`), and the verdict is an approval
    # ISSUE COMMENT. Must classify CLEAN, not "finished -> produced no review".
    timeline = [{"event": "copilot_work_finished", "created_at": "2026-05-28T12:05:00Z"}]
    issue = [{"user": {"login": "Copilot"}, "created_at": "2026-05-28T12:05:01Z",
              "body": "No further changes are needed on this branch."}]
    rc, result = _run_watch_result(
        capsys, monkeypatch, timeline=timeline, issue=issue,
    )
    assert (rc, result) == (0, "CLEAN")


def test_pr21_real_shape_with_since_is_clean(capsys, monkeypatch):
    """End-to-end repro of bd polyglot-pdf-6xp on PR #21's actual API shape.

    Round 1 left a COMMENTED review whose inline comment is position-non-null
    (1). After the fix + re-trigger, Copilot's "no further changes" verdict
    landed as ISSUE COMMENTS and the timeline shows copilot_work_finished (NO
    new `reviewed` event). With --since at the re-trigger, the watcher must
    reach CLEAN via the finished+issue-comment path -- not loop on the stale
    round-1 review (COMMENTS) nor TIMEOUT.
    """
    review = {"id": 4395801885, "state": "COMMENTED",
              "submitted_at": "2026-05-30T19:00:31Z", "body": "",
              "user": {"login": "copilot-pull-request-reviewer[bot]"}}
    inline = [{"user": {"login": "copilot-pull-request-reviewer[bot]"},
               "pull_request_review_id": 4395801885,
               "created_at": "2026-05-30T19:00:30Z", "path": "CLAUDE.md",
               "position": 1, "line": None, "body": "round-1 objection"}]
    issue = [{"user": {"login": "Copilot"}, "created_at": "2026-05-30T19:10:32Z",
              "body": "Re-reviewed current HEAD. No further changes are needed "
                      "on this branch."}]
    timeline = [
        {"event": "reviewed", "actor": {"login": "Copilot"},
         "submitted_at": "2026-05-30T19:00:31Z"},
        {"event": "copilot_work_finished", "actor": {"login": "Caellwyn"},
         "created_at": "2026-05-30T19:10:56Z"},
    ]
    _patch_api(monkeypatch, reviews=[review], inline=inline, issue=issue,
               timeline=timeline)
    since = cw._parse_iso("2026-05-30T19:06:16Z")  # the re-trigger moment
    rc = cw.watch("o/r", 21, timeout_min=0, poll_sec=0, since=since)
    out = capsys.readouterr().out
    assert rc == 0 and "RESULT: CLEAN" in out
