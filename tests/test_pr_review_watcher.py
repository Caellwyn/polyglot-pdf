"""Tests for scripts/pr_review_watcher.py.

Imports the script as a module (repo precedent: test_doc_freshness.py,
test_reset_dev_db_script.py) and exercises the pure classification logic
without hitting the network. The round-scoping tests monkeypatch
`_run_gh_api` so no `gh` call is made.

The reviewer-specific behavior lives in `ReviewerProfile`s (cw.COPILOT_PROFILE
/ cw.CODEX_PROFILE); classification helpers take a profile. Tests that don't
care which reviewer default to the Copilot profile via `PROFILE`.
"""

import datetime
import importlib.util
import pathlib
import sys

import pytest


SCRIPT_PATH = (
    pathlib.Path(__file__).resolve().parent.parent / "scripts" / "pr_review_watcher.py"
)
spec = importlib.util.spec_from_file_location("pr_review_watcher", SCRIPT_PATH)
cw = importlib.util.module_from_spec(spec)
sys.modules["pr_review_watcher"] = cw
spec.loader.exec_module(cw)

UTC = datetime.timezone.utc

# Default profile for tests that are reviewer-agnostic (the classification
# heuristics are shared). Reviewer-specific tests reference cw.CODEX_PROFILE.
PROFILE = cw.COPILOT_PROFILE


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
def test_is_reviewer_copilot(login, expected):
    assert cw._is_reviewer(login, PROFILE) is expected


# --- exit-code contract (finding #5: TIMEOUT distinct from ERROR) ---

def test_exit_code_map():
    assert cw._EXIT_CODES == {
        "COMMENTS": 0,
        "CLEAN": 0,
        "MERGED": 0,
        "TIMEOUT": 2,
        "ERROR": 1,
    }


@pytest.mark.parametrize(
    "state,code",
    [("COMMENTS", 0), ("CLEAN", 0), ("MERGED", 0), ("TIMEOUT", 2), ("ERROR", 1)],
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
    rc = cw.watch("o/r", 1, timeout_min=1, poll_sec=0, since=None, profile=PROFILE)
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
    findings = cw._collect_findings("o/r", 1, floor, review, PROFILE)
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
    findings = cw._collect_findings("o/r", 1, None, review, PROFILE)
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
    rc = cw.watch("o/r", 1, timeout_min=0, poll_sec=0, since=None, profile=PROFILE)
    out = capsys.readouterr().out
    assert rc == 2 and "RESULT: TIMEOUT" in out and "started but not finished" in out


def test_timeline_state_detection(monkeypatch):
    _patch_api(monkeypatch, timeline=[_reviewed_event()])
    assert cw._timeline_state("o/r", 1, None, PROFILE) == "reviewed"
    _patch_api(monkeypatch, timeline=[{"event": "copilot_work_finished",
                                       "created_at": "2026-05-28T12:00:00Z"}])
    assert cw._timeline_state("o/r", 1, None, PROFILE) == "finished"
    _patch_api(monkeypatch, timeline=[{"event": "copilot_work_started",
                                       "created_at": "2026-05-28T12:00:00Z"}])
    assert cw._timeline_state("o/r", 1, None, PROFILE) == "working"
    _patch_api(monkeypatch, timeline=[])
    assert cw._timeline_state("o/r", 1, None, PROFILE) is None


def test_latest_review_wins(monkeypatch):
    older = {"id": 1, "state": "COMMENTED", "submitted_at": "2026-05-28T10:00:00Z",
             "body": "old", "user": {"login": "Copilot"}}
    newer = {"id": 2, "state": "APPROVED", "submitted_at": "2026-05-28T12:00:00Z",
             "body": "new", "user": {"login": "Copilot"}}
    _patch_api(monkeypatch, reviews=[older, newer])
    latest = cw._latest_reviewer_review("o/r", 1, None, PROFILE)
    assert latest["id"] == 2


# --- bd polyglot-pdf-6xp: stale-comment loop fixes ---
# Repro from PR #21: a COMMENTED review whose inline comment went OUTDATED
# (position null) after the fix commit, plus Copilot's re-review approval
# delivered as an ISSUE COMMENT (no formal review). The pre-fix watcher
# re-emitted the stale comment as COMMENTS forever.

def test_outdated_inline_comment_dropped_yields_clean(capsys, monkeypatch):
    # position present-and-null -> outdated -> dropped; COMMENTED state with no
    # remaining findings -> CLEAN.
    review = {"id": 555, "state": "COMMENTED", "submitted_at": "2026-05-28T12:00:00Z",
              "body": "", "user": {"login": "Copilot"}}
    inline = [{"user": {"login": "Copilot"}, "pull_request_review_id": 555,
               "created_at": "2026-05-28T12:00:00Z", "path": "CLAUDE.md",
               "position": None, "line": None, "original_line": 107,
               "body": "stale round-1 objection"}]
    rc, result = _run_watch_result(
        capsys, monkeypatch, reviews=[review], inline=inline,
        timeline=[_reviewed_event()])
    assert (rc, result) == (0, "CLEAN")


def test_missing_position_key_not_treated_as_outdated(capsys, monkeypatch):
    # A payload missing `position` entirely must NOT be dropped (robust to
    # partial responses) -- it's still a finding -> COMMENTS.
    review = {"id": 555, "state": "COMMENTED", "submitted_at": "2026-05-28T12:00:00Z",
              "body": "", "user": {"login": "Copilot"}}
    inline = [{"user": {"login": "Copilot"}, "pull_request_review_id": 555,
               "created_at": "2026-05-28T12:00:00Z", "path": "app/x.py",
               "line": 10, "body": "finding, no position key"}]
    rc, result = _run_watch_result(
        capsys, monkeypatch, reviews=[review], inline=inline,
        timeline=[_reviewed_event()])
    assert (rc, result) == (0, "COMMENTS")


def test_live_inline_comment_nonnull_position_still_comments(capsys, monkeypatch):
    # Anti-false-negative: a genuine round-2 finding has a non-null position.
    review = {"id": 556, "state": "COMMENTED", "submitted_at": "2026-05-28T12:00:00Z",
              "body": "", "user": {"login": "Copilot"}}
    inline = [{"user": {"login": "Copilot"}, "pull_request_review_id": 556,
               "created_at": "2026-05-28T12:00:00Z", "path": "app/x.py",
               "position": 12, "line": 42, "body": "real new finding"}]
    rc, result = _run_watch_result(
        capsys, monkeypatch, reviews=[review], inline=inline,
        timeline=[_reviewed_event()])
    assert (rc, result) == (0, "COMMENTS")


def test_changes_requested_with_only_outdated_comment_still_comments(capsys, monkeypatch):
    # State wins: CHANGES_REQUESTED stays COMMENTS even if its only comment is
    # outdated -- the outdated-drop must not launder a change-request to CLEAN.
    review = {"id": 557, "state": "CHANGES_REQUESTED", "submitted_at": "2026-05-28T12:00:00Z",
              "body": "", "user": {"login": "Copilot"}}
    inline = [{"user": {"login": "Copilot"}, "pull_request_review_id": 557,
               "created_at": "2026-05-28T12:00:00Z", "path": "app/x.py",
               "position": None, "line": None, "body": "outdated but state is CR"}]
    rc, result = _run_watch_result(
        capsys, monkeypatch, reviews=[review], inline=inline,
        timeline=[_reviewed_event()])
    assert (rc, result) == (0, "COMMENTS")


def test_issue_comment_approval_round_is_clean_not_timeout(capsys, monkeypatch):
    # Fix A: verdict is a Copilot ISSUE COMMENT (no in-window review). An
    # explicit approval phrase -> CLEAN (pre-fix this TIMEOUT'd).
    issue = [{"user": {"login": "Copilot"}, "created_at": "2026-05-28T12:00:05Z",
              "body": "Re-reviewed current HEAD. No further changes are needed on this branch."}]
    rc, result = _run_watch_result(
        capsys, monkeypatch, reviews=[], issue=issue, timeline=[_reviewed_event()])
    assert (rc, result) == (0, "CLEAN")


def test_issue_comment_nonapproval_round_is_comments(capsys, monkeypatch):
    # An issue comment that is not an explicit approval stays COMMENTS.
    issue = [{"user": {"login": "Copilot"}, "created_at": "2026-05-28T12:00:05Z",
              "body": "One more thing: please also update the changelog."}]
    rc, result = _run_watch_result(
        capsys, monkeypatch, reviews=[], issue=issue, timeline=[_reviewed_event()])
    assert (rc, result) == (0, "COMMENTS")


# --- bd polyglot-pdf-x8o: inline-findings-first (acknowledgment prose != COMMENTS) ---

def test_quoted_trigger_please_does_not_trip_changeask(capsys, monkeypatch):
    # THE bd-x8o root cause (PR #48 r2 verbatim shape): Copilot echoes the trigger
    # as a blockquote `> @copilot please review`, and that quoted "please" tripped
    # _has_change_ask -> false COMMENTS. With quote-stripping + no new inline
    # finding, the acknowledgment is CLEAN.
    body = (
        "> @copilot please review\n\n"
        "The two issues the reviewer raised were already addressed in the second "
        "commit. All guard tests pass; zero remaining print() PII sinks."
    )
    issue = [{"user": {"login": "Copilot"}, "created_at": "2026-05-28T12:00:05Z", "body": body}]
    rc, result = _run_watch_result(
        capsys, monkeypatch, reviews=[], issue=issue, inline=[],
        timeline=[_reviewed_event()])
    assert (rc, result) == (0, "CLEAN")


def test_strip_quotes_removes_blockquote_lines():
    assert cw._strip_quotes("> @copilot please review\n\nNo change-ask here.") == (
        "\nNo change-ask here."
    )
    assert cw._strip_quotes("  > indented quote\nkept") == "kept"
    assert cw._strip_quotes("no quotes at all") == "no quotes at all"


# The exact body Codex posts for a clean re-review (live, PR #133 round 3): a
# one-line verdict followed by the boilerplate "<details> About Codex in GitHub"
# footer the GitHub app auto-appends. The footer is multi-paragraph + >200 chars
# AND contains "suggest" ("If Codex has suggestions..."), so before the
# footer-strip it (a) failed _is_approval_shaped -> the "no major issues" sentinel
# never reached CLEAN, and (b) tripped _has_change_ask -> false COMMENTS. (bd pjd1)
_CODEX_CLEAN_BODY_WITH_FOOTER = (
    "Codex Review: Didn't find any major issues. Hooray!\n\n"
    "<details> <summary>About Codex in GitHub</summary>\n"
    "<br/>\n\n"
    "[Your team has set up Codex to review pull requests in this repo](https://example).\n"
    "Reviews are triggered when you\n"
    "- Open a pull request for review\n"
    "- Comment \"@codex review\".\n\n"
    "If Codex has suggestions, it will comment; otherwise it will react with a thumbs up.\n\n"
    "Codex can also answer questions or update the PR. Try commenting \"@codex address that feedback\".\n"
    "</details>"
)


def test_strip_details_footer_removes_boilerplate():
    # The footer block is dropped; the verdict line survives.
    stripped = cw._strip_details_footer(_CODEX_CLEAN_BODY_WITH_FOOTER)
    assert "Didn't find any major issues" in stripped
    assert "<details>" not in stripped
    assert "suggestions" not in stripped  # the "suggest" change-ask trigger is gone
    assert "</details>" not in stripped
    # A body with no footer is returned unchanged (modulo trailing whitespace).
    assert cw._strip_details_footer("plain body, no footer").strip() == "plain body, no footer"
    # Multiple footers / a footer mid-body are both removed.
    multi = "verdict\n<details>a</details>\nmore\n<details>b</details>"
    out = cw._strip_details_footer(multi)
    assert "<details>" not in out and "verdict" in out and "more" in out


def test_codex_clean_with_details_footer_classifies_clean():
    # The headline regression (bd pjd1): the real PR #133 round-3 clean comment,
    # footer and all, must be recognized as an approval -- NOT misread as a
    # change-ask because the footer mentions "suggestions".
    assert cw._is_approval_comment(_CODEX_CLEAN_BODY_WITH_FOOTER, cw.CODEX_PROFILE)
    # And it must NOT trip the change-ask gate once the footer is stripped.
    assert not cw._has_change_ask(cw._strip_details_footer(_CODEX_CLEAN_BODY_WITH_FOOTER))


def test_details_footer_strip_does_not_hide_a_real_change_ask():
    # FALSE-CLEAN guard: a genuine change-ask in the VISIBLE prose (outside any
    # footer) is still caught -- the strip only removes <details> blocks.
    body = (
        "Codex Review: One issue. Please fix the null check at line 42 before merge.\n\n"
        "<details> <summary>About Codex</summary>\nboilerplate\n</details>"
    )
    assert cw._has_change_ask(cw._strip_details_footer(body))
    assert not cw._is_approval_comment(body, cw.CODEX_PROFILE)


def test_leading_lgtm_is_approval_even_with_summary_and_footer():
    # AGENTS.md instructs Codex to LEAD a clean summary with `LGTM` (bd pjd1). A
    # leading LGTM followed by a human-readable summary + the footer must be an
    # approval -- the whole-body _is_exact_lgtm would reject this (summary present),
    # so _has_leading_lgtm is what makes the instructed token work.
    body = (
        "LGTM\n\nRe-reviewed the round-2 fixes; all addressed.\n\n"
        "<details> <summary>About Codex</summary>\nIf Codex has suggestions...\n</details>"
    )
    assert cw._has_leading_lgtm(body)
    assert cw._is_approval_comment(body, cw.CODEX_PROFILE)
    # Markdown-wrapped lead line still counts (**LGTM**, `LGTM`, "LGTM.").
    assert cw._has_leading_lgtm("**LGTM**\n\nnice work")
    assert cw._has_leading_lgtm("`LGTM`")
    # Not a lead-LGTM: the token is not first, or it's a different word.
    assert not cw._has_leading_lgtm("Looks good. LGTM follows below.\n\nLGTM")
    assert not cw._has_leading_lgtm("almost LGTM")


def test_leading_lgtm_with_change_ask_is_not_clean():
    # FALSE-CLEAN guard: `LGTM` leading a comment that ALSO asks for a change must
    # NOT be an approval -- the leading-LGTM path is gated on no change-ask.
    body = "LGTM\n\nbut please fix the off-by-one at line 42 before merge."
    assert cw._has_leading_lgtm(body)          # the lead line IS lgtm
    assert not cw._is_approval_comment(body, cw.CODEX_PROFILE)  # ...but the ask vetoes it


def test_new_inline_finding_beats_acknowledgment_prose(capsys, monkeypatch):
    # If a NEW actionable inline finding exists this round, it's COMMENTS even when
    # the issue-comment prose reads like an approval -- inline leads.
    issue = [{"user": {"login": "Copilot"}, "created_at": "2026-05-28T12:00:05Z",
              "body": "Looks good overall, no further changes needed."}]
    inline = [{"user": {"login": "Copilot"}, "created_at": "2026-05-28T12:00:04Z",
               "path": "app/x.py", "position": 4, "line": 12,
               "body": "this off-by-one is a real bug"}]
    rc, result = _run_watch_result(
        capsys, monkeypatch, reviews=[], issue=issue, inline=inline,
        timeline=[_reviewed_event()])
    assert (rc, result) == (0, "COMMENTS")


def test_genuine_prose_ask_with_stale_inline_is_comments(capsys, monkeypatch):
    # FALSE-CLEAN guard (fresh-eyes must-fix on PR #49): a GENUINE round-2 prose
    # ask ("please also fix the off-by-one") with NO new inline finding, on a PR
    # that already has a PRIOR-round inline comment, must be COMMENTS -- the
    # change-ask path is ungated, so prior inline history does NOT suppress it.
    since = cw._parse_iso("2026-05-28T12:00:00Z")
    issue = [{"user": {"login": "Copilot"}, "created_at": "2026-05-28T12:05:00Z",
              "body": "> @copilot please review\n\nPlease also fix the off-by-one "
                      "at line 42 before merge."}]
    inline = [{"user": {"login": "Copilot"}, "created_at": "2026-05-28T11:00:00Z",
               "path": "app/x.py", "position": 2, "line": 5, "body": "prior-round ask"}]
    _patch_api(monkeypatch, reviews=[], issue=issue, inline=inline,
               timeline=[_reviewed_event("2026-05-28T12:04:00Z")])
    rc = cw.watch("o/r", 1, timeout_min=1, poll_sec=0, since=since, profile=PROFILE)
    out = capsys.readouterr().out
    assert rc == 0 and "RESULT: COMMENTS" in out


def test_prose_only_changeask_no_inline_anywhere_is_comments(capsys, monkeypatch):
    # The legitimate fallback: Copilot left NO inline comments at all on the PR and
    # its prose genuinely asks for a change -> COMMENTS (a prose-only ask is caught).
    issue = [{"user": {"login": "Copilot"}, "created_at": "2026-05-28T12:00:05Z",
              "body": "One more thing: please also update the changelog before merge."}]
    rc, result = _run_watch_result(
        capsys, monkeypatch, reviews=[], issue=issue, inline=[],
        timeline=[_reviewed_event()])
    assert (rc, result) == (0, "COMMENTS")


def test_finished_with_issue_comment_approval_is_clean(capsys, monkeypatch):
    # Fix A via the "finished" branch: timeline=finished (no new reviewed) and
    # an approval issue comment -> CLEAN, not "produced no review".
    timeline = [{"event": "copilot_work_finished", "created_at": "2026-05-28T12:05:00Z"}]
    issue = [{"user": {"login": "Copilot"}, "created_at": "2026-05-28T12:05:01Z",
              "body": "No further changes are needed on this branch."}]
    rc, result = _run_watch_result(capsys, monkeypatch, timeline=timeline, issue=issue)
    assert (rc, result) == (0, "CLEAN")


def test_is_approval_comment_strict():
    # Clean approvals.
    assert cw._is_approval_comment("No further changes were needed.", PROFILE)
    assert cw._is_approval_comment("the contract is consistent; no changes needed", PROFILE)
    # MIXED comment (approval phrase + a change ask) must NOT be CLEAN
    # (fresh-eyes finding #1 / #7).
    assert not cw._is_approval_comment(
        "No changes needed in section 3, but please fix the null check in section 4.", PROFILE)
    assert not cw._is_approval_comment(
        "No further changes to the imports; however the main function has a bug.", PROFILE)
    # Clear non-approvals.
    assert not cw._is_approval_comment("please fix the typo", PROFILE)
    assert not cw._is_approval_comment("", PROFILE)


def test_latest_by_created_ignores_list_order():
    # Don't rely on API ordering -- pick max created_at explicitly (finding #3).
    older = {"created_at": "2026-05-28T10:00:00Z", "body": "older"}
    newer = {"created_at": "2026-05-28T12:00:00Z", "body": "newer"}
    assert cw._latest_by_created([newer, older])["body"] == "newer"  # reversed input
    assert cw._latest_by_created([]) is None


def test_approval_issue_comment_not_counted_as_finding_with_review(capsys, monkeypatch):
    # Fresh-eyes finding #4: a clean review PLUS a same-round approval issue
    # comment must stay CLEAN -- the approval must not enter findings.
    review = {"id": 9, "state": "COMMENTED", "submitted_at": "2026-05-28T12:00:00Z",
              "body": "", "user": {"login": "Copilot"}}
    issue = [{"user": {"login": "Copilot"}, "created_at": "2026-05-28T12:00:05Z",
              "body": "No further changes are needed."}]
    rc, result = _run_watch_result(
        capsys, monkeypatch, reviews=[review], issue=issue, timeline=[_reviewed_event()])
    assert (rc, result) == (0, "CLEAN")


# --- findings-based classification + exact-LGTM pin (bd polyglot-pdf-7ti) ---
# Motivation: Copilot kept inventing novel approval wordings the phrase list
# couldn't match (e.g. PR #45 round 2: "the two prior reviewer findings are
# already addressed in bff9399"), causing false COMMENTS / TIMEOUT. The watcher
# now treats approval as the ABSENCE of an actionable finding, and matches an
# exact `LGTM` body deterministically.

@pytest.mark.parametrize(
    "body,expected",
    [
        ("LGTM", True),
        ("lgtm", True),
        ("**LGTM**", True),       # markdown emphasis
        ("`LGTM`", True),         # inline code
        ("> LGTM", True),         # blockquote (Copilot quotes the trigger)
        ("LGTM.", True),          # trailing punctuation
        ("LGTM, nice work", False),   # extra prose -> not the exact signal
        ("looks good to me", False),  # not the literal token
        ("", False),
    ],
)
def test_is_exact_lgtm(body, expected):
    assert cw._is_exact_lgtm(body) is expected


def test_exact_lgtm_issue_comment_is_clean(capsys, monkeypatch):
    # The canonical signal: a bare LGTM issue comment -> CLEAN deterministically.
    issue = [{"user": {"login": "Copilot"}, "created_at": "2026-05-28T12:00:05Z",
              "body": "LGTM"}]
    rc, result = _run_watch_result(
        capsys, monkeypatch, reviews=[], issue=issue, timeline=[_reviewed_event()])
    assert (rc, result) == (0, "CLEAN")


def test_novel_approval_wording_with_no_findings_is_clean(capsys, monkeypatch):
    # THE regression that motivated this change (PR #45 round 2). A wording that
    # matches NO approval phrase and NO change-ask, with no inline finding this
    # round, must classify CLEAN -- not COMMENTS, not TIMEOUT.
    issue = [{"user": {"login": "Copilot"}, "created_at": "2026-05-28T12:00:05Z",
              "body": "I checked the branch state and the two prior reviewer "
                      "findings are already addressed in bff9399."}]
    rc, result = _run_watch_result(
        capsys, monkeypatch, reviews=[], issue=issue, inline=[],
        timeline=[_reviewed_event()])
    assert (rc, result) == (0, "CLEAN")


def test_novel_wording_but_new_inline_finding_is_comments(capsys, monkeypatch):
    # The findings-based backstop must not launder a REAL finding to CLEAN: if a
    # new actionable inline comment exists this round, it's COMMENTS regardless of
    # how breezy the summary prose is.
    issue = [{"user": {"login": "Copilot"}, "created_at": "2026-05-28T12:00:05Z",
              "body": "Took another look at the changes."}]  # no approval, no ask
    inline = [{"user": {"login": "Copilot"}, "created_at": "2026-05-28T12:00:04Z",
               "path": "app/x.py", "position": 7, "line": 20,
               "body": "this branch is dead code"}]
    rc, result = _run_watch_result(
        capsys, monkeypatch, reviews=[], issue=issue, inline=inline,
        timeline=[_reviewed_event()])
    assert (rc, result) == (0, "COMMENTS")


def test_prose_only_change_ask_with_no_inline_is_comments(capsys, monkeypatch):
    # A substantive ask delivered as prose ("please ...") with no inline anchor
    # must still be caught by the change-ask gate -> COMMENTS.
    issue = [{"user": {"login": "Copilot"}, "created_at": "2026-05-28T12:00:05Z",
              "body": "Overall fine, but please rename the helper for clarity."}]
    rc, result = _run_watch_result(
        capsys, monkeypatch, reviews=[], issue=issue, inline=[],
        timeline=[_reviewed_event()])
    assert (rc, result) == (0, "COMMENTS")


def test_commented_review_overview_body_only_is_clean(capsys, monkeypatch):
    # A COMMENTED review whose body is just the "## Pull request overview"
    # summary (no change-ask, no inline findings) is an approval, not COMMENTS.
    review = {"id": 9, "state": "COMMENTED", "submitted_at": "2026-05-28T12:00:00Z",
              "body": "## Pull request overview\n\nDocs-only change updating several docs.",
              "user": {"login": "Copilot"}}
    rc, result = _run_watch_result(
        capsys, monkeypatch, reviews=[review], inline=[], timeline=[_reviewed_event()])
    assert (rc, result) == (0, "CLEAN")


# --- bd polyglot-pdf-ztk: exception-clause / multi-paragraph false-CLEANs ---

@pytest.mark.parametrize(
    "body",
    [
        # exception clause carving out a real finding after an approval phrase
        "No outstanding findings beyond the race condition in X.",
        "No further changes needed other than addressing the TODO in auth.py.",
        "No outstanding issues except the hardcoded timeout.",
        # multi-paragraph: approval phrase, then a finding in a second paragraph
        "No outstanding findings.\n\nOne minor observation: the timeout is hardcoded.",
        # numbered/bulleted structure -> not approval-shaped
        "No further changes needed.\n- but rename the helper",
    ],
)
def test_exception_or_multiblock_phrasing_not_approval(body):
    # These all OPEN with a kept approval phrase but carry a real finding; the
    # shape guard + exception-connector signals must keep them out of CLEAN.
    assert not cw._is_approval_comment(body, PROFILE)


def test_exception_clause_issue_comment_is_comments(capsys, monkeypatch):
    issue = [{"user": {"login": "Copilot"}, "created_at": "2026-05-28T12:00:05Z",
              "body": "No outstanding findings beyond the race condition in X."}]
    rc, result = _run_watch_result(
        capsys, monkeypatch, reviews=[], issue=issue, inline=[],
        timeline=[_reviewed_event()])
    assert (rc, result) == (0, "COMMENTS")


def test_long_comment_starting_with_approval_phrase_not_approval():
    # A long body that merely opens with an approval phrase is not approval-shaped.
    body = "No further changes are needed " + ("x " * 120)  # > 200 chars
    assert not cw._is_approval_comment(body, PROFILE)


# --- round-3 review hardening (fresh-eyes + Copilot on PR #45) ---

def test_exact_lgtm_tolerates_bang():
    # LGTM! should hit the deterministic fast path (Copilot adds enthusiasm).
    assert cw._is_exact_lgtm("LGTM!") is True
    assert cw._is_exact_lgtm("**LGTM!**") is True


@pytest.mark.parametrize(
    "body,shaped",
    [
        ("No further changes needed.", True),
        # decimal in prose is NOT a list marker (requires trailing space)
        ("No further changes needed. Response time is 3.5s, acceptable.", True),
        # markdown ordered lists (both . and ) styles) ARE structured -> not shaped
        ("No further changes needed.\n1. rename the helper", False),
        ("No further changes needed.\n1) rename the helper", False),
        ("No further changes needed.\n- rename the helper", False),
        ("No further changes needed.\n12) the twelfth thing", False),
    ],
)
def test_is_approval_shaped_list_detection(body, shaped):
    assert cw._is_approval_shaped(body) is shaped


def test_paren_list_finding_is_not_approval():
    # FE #1: a finding using "1)" list syntax with no change-ask verb must not
    # ride the allowlist to CLEAN.
    assert not cw._is_approval_comment(
        "No further changes needed.\n1) the helper name is unclear", PROFILE)


def test_commented_review_overview_body_with_inline_finding_is_comments(capsys, monkeypatch):
    # FE #3 (must-fix companion): the SAME neutral-overview-body scenario, but
    # WITH a real inline finding this round, must stay COMMENTS -- proves the
    # body-not-counted change didn't also suppress inline findings.
    review = {"id": 9, "state": "COMMENTED", "submitted_at": "2026-05-28T12:00:00Z",
              "body": "## Pull request overview\n\nDocs-only change updating several docs.",
              "user": {"login": "Copilot"}}
    inline = [{"user": {"login": "Copilot"}, "pull_request_review_id": 9,
               "created_at": "2026-05-28T12:00:00Z", "path": "app/x.py",
               "position": 5, "line": 30, "body": "real new finding"}]
    rc, result = _run_watch_result(
        capsys, monkeypatch, reviews=[review], inline=inline,
        timeline=[_reviewed_event()])
    assert (rc, result) == (0, "COMMENTS")


def test_collect_findings_prose_only_finding_is_not_counted(monkeypatch):
    # FE #4: documents the ACCEPTED RISK. A review body stating a finding without
    # any change-ask signal word and no inline comment is NOT counted -> the round
    # reads CLEAN. This is deliberate (the human merge is the backstop); if a
    # future change tightens this, update this test consciously.
    review = {"id": 9, "state": "COMMENTED", "submitted_at": "2026-05-28T12:00:00Z",
              "body": "The null pointer on line 45 is still present.",
              "user": {"login": "Copilot"}}
    monkeypatch.setattr(cw, "_run_gh_api", lambda path: [])  # no inline / issue comments
    result = cw._collect_findings("o/r", 1, None, review, PROFILE)
    assert result == []  # accepted-risk: prose-only finding not detected


def test_runtime_error_fallback_clean_when_body_is_neutral_overview(capsys, monkeypatch):
    # Copilot #2 (the real bug): if the inline-comment fetch fails on a COMMENTED
    # review whose body is just the neutral overview, the fallback must NOT
    # classify COMMENTS just because the body is non-empty.
    review = {"id": 9, "state": "COMMENTED", "submitted_at": "2026-05-28T12:00:00Z",
              "body": "## Pull request overview\n\nLooks like a docs-only change.",
              "user": {"login": "Copilot"}}

    calls = {"n": 0}

    def fake(path):
        if path.endswith("/timeline"):
            return [_reviewed_event()]
        if path.endswith("/reviews"):
            return [review]
        if "/pulls/" in path and path.endswith("/comments"):
            raise RuntimeError("simulated inline fetch failure")
        if "/issues/" in path and path.endswith("/comments"):
            return []
        return {"state": "open"}

    monkeypatch.setattr(cw, "_run_gh_api", fake)
    rc = cw.watch("o/r", 1, timeout_min=1, poll_sec=0, since=None, profile=PROFILE)
    out = capsys.readouterr().out
    assert rc == 0 and "RESULT: CLEAN" in out


def test_runtime_error_fallback_comments_when_state_changes_requested(capsys, monkeypatch):
    # The complement: a CHANGES_REQUESTED state with a failed inline fetch must
    # STILL be COMMENTS (state wins, fallback must not launder it to CLEAN).
    review = {"id": 9, "state": "CHANGES_REQUESTED", "submitted_at": "2026-05-28T12:00:00Z",
              "body": "", "user": {"login": "Copilot"}}

    def fake(path):
        if path.endswith("/timeline"):
            return [_reviewed_event()]
        if path.endswith("/reviews"):
            return [review]
        if "/pulls/" in path and path.endswith("/comments"):
            raise RuntimeError("simulated inline fetch failure")
        if "/issues/" in path and path.endswith("/comments"):
            return []
        return {"state": "open"}

    monkeypatch.setattr(cw, "_run_gh_api", fake)
    rc = cw.watch("o/r", 1, timeout_min=1, poll_sec=0, since=None, profile=PROFILE)
    out = capsys.readouterr().out
    assert rc == 0 and "RESULT: COMMENTS" in out


def test_since_scopes_out_prior_round_review(monkeypatch):
    # Fix C: with --since after a round-1 review, that review is excluded.
    round1 = {"id": 1, "state": "COMMENTED", "submitted_at": "2026-05-28T12:00:00Z",
              "body": "round 1", "user": {"login": "Copilot"}}
    _patch_api(monkeypatch, reviews=[round1])
    since = cw._parse_iso("2026-05-28T12:30:00Z")
    assert cw._latest_reviewer_review("o/r", 1, since, PROFILE) is None


def test_pr21_real_shape_with_since_is_clean(capsys, monkeypatch):
    """End-to-end repro of bd polyglot-pdf-6xp on PR #21's real API shape.

    Round-1 COMMENTED review; its inline comment is position-NON-null (1) so the
    outdated-drop does not apply. After the fix + re-trigger, Copilot's "no
    further changes" verdict landed as ISSUE COMMENTS and the timeline shows
    copilot_work_finished (NO new `reviewed`). With --since at the re-trigger,
    the watcher must reach CLEAN via finished+issue-comment -- not loop on the
    stale review (COMMENTS) nor TIMEOUT.
    """
    review = {"id": 4395801885, "state": "COMMENTED",
              "submitted_at": "2026-05-30T19:00:31Z", "body": "",
              "user": {"login": "copilot-pull-request-reviewer[bot]"}}
    inline = [{"user": {"login": "copilot-pull-request-reviewer[bot]"},
               "pull_request_review_id": 4395801885,
               "created_at": "2026-05-30T19:00:30Z", "path": "CLAUDE.md",
               "position": 1, "line": None, "body": "round-1 objection"}]
    issue = [{"user": {"login": "Copilot"}, "created_at": "2026-05-30T19:10:32Z",
              "body": "Re-reviewed current HEAD. No further changes are needed on this branch."}]
    timeline = [
        {"event": "reviewed", "actor": {"login": "Copilot"},
         "submitted_at": "2026-05-30T19:00:31Z"},
        {"event": "copilot_work_finished", "actor": {"login": "Caellwyn"},
         "created_at": "2026-05-30T19:10:56Z"},
    ]
    _patch_api(monkeypatch, reviews=[review], inline=inline, issue=issue,
               timeline=timeline)
    since = cw._parse_iso("2026-05-30T19:06:16Z")
    rc = cw.watch("o/r", 21, timeout_min=0, poll_sec=0, since=since, profile=PROFILE)
    out = capsys.readouterr().out
    assert rc == 0 and "RESULT: CLEAN" in out


# ===========================================================================
# Codex profile (bd polyglot-pdf-hrn.10): the reviewer-agnostic classifier
# driven by CODEX_PROFILE. Codex differs from Copilot in four ways exercised
# here: (1) bot login "chatgpt-codex-connector[bot]", (2) NO copilot_work_*
# timeline events (uses_timeline=False), (3) its clean verdict is an issue
# comment "Codex Review: Didn't find any major issues. 👍", (4) error sentinel.
# ===========================================================================

CODEX = cw.CODEX_PROFILE
_CODEX_LOGIN = "chatgpt-codex-connector[bot]"


@pytest.mark.parametrize(
    "login,expected",
    [
        ("chatgpt-codex-connector[bot]", True),
        ("Codex", True),
        ("copilot-pull-request-reviewer[bot]", False),  # disjoint from Copilot
        ("github-actions[bot]", False),
        ("", False),
    ],
)
def test_is_reviewer_codex(login, expected):
    assert cw._is_reviewer(login, CODEX) is expected


def test_codex_profile_does_not_use_timeline():
    # Codex emits no copilot_work_* events, so _timeline_state must report
    # "reviewed" every poll (= go look at the review surfaces) WITHOUT reading
    # the timeline at all -- even when the timeline is empty.
    assert CODEX.uses_timeline is False
    # No monkeypatch of _run_gh_api: if it tried to read the timeline this would
    # raise. It must not.
    assert cw._timeline_state("o/r", 1, None, CODEX) == "reviewed"


def test_codex_clean_sentinel_is_clean(capsys, monkeypatch):
    # Codex's clean verdict: no review, an issue comment with the "didn't find
    # any major issues" sentinel. No timeline events at all.
    issue = [{
        "user": {"login": _CODEX_LOGIN},
        "created_at": "2026-06-01T12:00:00Z",
        "body": "Codex Review: Didn't find any major issues. \U0001f44d",
    }]
    _patch_api(monkeypatch, issue=issue)
    rc = cw.watch("o/r", 1, timeout_min=1, poll_sec=0, since=None, profile=CODEX)
    out = capsys.readouterr().out
    assert rc == 0 and "RESULT: CLEAN" in out


def test_codex_clean_with_footer_and_no_reaction_is_clean_end_to_end(capsys, monkeypatch):
    # The PR #133 round-3 regression END TO END (bd polyglot-pdf-pjd1): Codex's
    # clean comment carries the auto-appended <details> footer AND has NO thumbs-up
    # reaction (reactions absent). Pre-fix the footer defeated the shape gate and
    # tripped change-ask, so watch() emitted COMMENTS and the bead had to be closed
    # by hand. It must now classify CLEAN through the real watch() path.
    issue = [{
        "user": {"login": _CODEX_LOGIN},
        "created_at": "2026-06-09T23:21:48Z",
        "body": _CODEX_CLEAN_BODY_WITH_FOOTER,  # no "reactions" key -> no thumbs-up
    }]
    _patch_api(monkeypatch, issue=issue)
    rc = cw.watch("o/r", 1, timeout_min=1, poll_sec=0, since=None, profile=CODEX)
    out = capsys.readouterr().out
    assert rc == 0 and "RESULT: CLEAN" in out


def test_codex_clean_sentinel_via_is_approval_comment():
    # The sentinel rides the shared approval path only for the Codex profile;
    # the Copilot profile must NOT treat it as an approval (it's not a Copilot
    # phrasing), proving the profile actually gates the sentinel.
    sentinel = "Codex Review: Didn't find any major issues."
    assert cw._is_approval_comment(sentinel, CODEX) is True
    assert cw._is_approval_comment(sentinel, PROFILE) is False


def test_has_clean_reaction_detects_thumbs_up():
    # The 👍 rollup ("+1" > 0) is the canonical Codex approval. Copilot has no
    # clean_reaction, so the SAME payload must read False for it.
    has = {"reactions": {"+1": 1, "-1": 0}}
    none_ = {"reactions": {"+1": 0}}
    assert cw._has_clean_reaction(has, CODEX) is True
    assert cw._has_clean_reaction(none_, CODEX) is False
    assert cw._has_clean_reaction({}, CODEX) is False           # no rollup -> False
    assert cw._has_clean_reaction(has, PROFILE) is False         # Copilot: no reaction signal


def test_codex_thumbs_up_reaction_is_clean(capsys, monkeypatch):
    # The documented canonical signal: Codex 👍 reaction on its own comment ->
    # CLEAN, even with a body the prose heuristics wouldn't match on their own.
    issue = [{
        "user": {"login": _CODEX_LOGIN},
        "created_at": "2026-06-01T12:00:00Z",
        "body": "Reviewed the latest changes.",  # no approval phrase
        "reactions": {"+1": 1},
    }]
    _patch_api(monkeypatch, issue=issue)
    rc = cw.watch("o/r", 1, timeout_min=1, poll_sec=0, since=None, profile=CODEX)
    out = capsys.readouterr().out
    assert rc == 0 and "RESULT: CLEAN" in out
    assert "reaction" in out  # classified via the reaction path, not prose


def test_codex_thumbs_up_on_empty_comment_is_clean(capsys, monkeypatch):
    # Codex can 👍 with an empty/minimal body. The reaction alone is the verdict.
    issue = [{
        "user": {"login": _CODEX_LOGIN},
        "created_at": "2026-06-01T12:00:00Z",
        "body": "",
        "reactions": {"+1": 2},
    }]
    _patch_api(monkeypatch, issue=issue)
    rc = cw.watch("o/r", 1, timeout_min=1, poll_sec=0, since=None, profile=CODEX)
    out = capsys.readouterr().out
    assert rc == 0 and "RESULT: CLEAN" in out


def test_codex_inline_finding_beats_thumbs_up(capsys, monkeypatch):
    # ORDERING GUARANTEE: a 👍 reaction must NOT override a real inline finding.
    # A comment with a 👍 AND a same-round inline ask is COMMENTS, not CLEAN --
    # the inline-findings check ranks above the reaction check.
    issue = [{
        "user": {"login": _CODEX_LOGIN},
        "created_at": "2026-06-01T12:00:00Z",
        "body": "Mostly good.",
        "reactions": {"+1": 1},
    }]
    inline = [{
        "user": {"login": _CODEX_LOGIN},
        "pull_request_review_id": 99,
        "created_at": "2026-06-01T12:00:01Z",
        "path": "backend/config.py", "line": 5, "position": 1,
        "body": "This default will break when MODEL_NATIVE is unset.",
    }]
    _patch_api(monkeypatch, issue=issue, inline=inline)
    rc = cw.watch("o/r", 1, timeout_min=1, poll_sec=0, since=None, profile=CODEX)
    out = capsys.readouterr().out
    assert rc == 0 and "RESULT: COMMENTS" in out
    assert "MODEL_NATIVE" in out


def test_codex_inline_finding_is_comments(capsys, monkeypatch):
    # Codex left a real review with an inline finding -> COMMENTS.
    review = {"id": 77, "state": "COMMENTED", "submitted_at": "2026-06-01T12:00:01Z",
              "body": "", "user": {"login": _CODEX_LOGIN}}
    inline = [{
        "user": {"login": _CODEX_LOGIN},
        "pull_request_review_id": 77,
        "created_at": "2026-06-01T12:00:00Z",
        "path": "scripts/pr_review_watcher.py", "line": 42, "position": 1,
        "body": "Add MERGED to the closeout watcher states.",
    }]
    _patch_api(monkeypatch, reviews=[review], inline=inline)
    rc = cw.watch("o/r", 1, timeout_min=1, poll_sec=0, since=None, profile=CODEX)
    out = capsys.readouterr().out
    assert rc == 0 and "RESULT: COMMENTS" in out
    assert "Add MERGED" in out


def test_codex_error_sentinel_is_error(capsys, monkeypatch):
    issue = [{
        "user": {"login": _CODEX_LOGIN},
        "created_at": "2026-06-01T12:00:00Z",
        "body": "Codex encountered an error and could not complete the review.",
    }]
    _patch_api(monkeypatch, issue=issue)
    rc = cw.watch("o/r", 1, timeout_min=1, poll_sec=0, since=None, profile=CODEX)
    out = capsys.readouterr().out
    assert rc == 1 and "RESULT: ERROR" in out


def test_codex_change_ask_prose_is_comments(capsys, monkeypatch):
    # A Codex issue-comment that asks for a change (no inline) -> COMMENTS, via
    # the same change-ask gate the Copilot path uses.
    issue = [{
        "user": {"login": _CODEX_LOGIN},
        "created_at": "2026-06-01T12:00:00Z",
        "body": "Please fix the null-default handling in config.py before merge.",
    }]
    _patch_api(monkeypatch, issue=issue)
    rc = cw.watch("o/r", 1, timeout_min=1, poll_sec=0, since=None, profile=CODEX)
    out = capsys.readouterr().out
    assert rc == 0 and "RESULT: COMMENTS" in out


def test_codex_ignores_copilot_comment(capsys, monkeypatch):
    # A Copilot comment on the PR must NOT be read as Codex's verdict (disjoint
    # logins). With only a Copilot comment present, the Codex watch finds no
    # Codex verdict and TIMEOUTs rather than falsely classifying.
    issue = [{
        "user": {"login": "copilot-pull-request-reviewer[bot]"},
        "created_at": "2026-06-01T12:00:00Z",
        "body": "LGTM",
    }]
    _patch_api(monkeypatch, issue=issue)
    rc = cw.watch("o/r", 1, timeout_min=0, poll_sec=0, since=None, profile=CODEX)
    out = capsys.readouterr().out
    assert rc == 2 and "RESULT: TIMEOUT" in out


def test_codex_closed_without_merge_is_clean(capsys, monkeypatch):
    # Fresh-eyes PR #52, finding 2: a non-timeline reviewer (Codex) ALWAYS
    # reports state="reviewed", which previously nullified closed_state every
    # poll and made the closed-without-merge terminal unreachable -- an abandoned
    # Codex PR TIMEOUTed (exit 2) instead of going CLEAN (exit 0). With no Codex
    # verdict and the PR closed-not-merged, the watch must now reach CLEAN.
    _patch_api(monkeypatch, pr_state="closed")  # closed, no `merged` -> "closed"
    rc = cw.watch("o/r", 1, timeout_min=1, poll_sec=0, since=None, profile=CODEX)
    out = capsys.readouterr().out
    assert rc == 0 and "RESULT: CLEAN" in out
    assert "closed" in out.lower()


def test_codex_timeout_note_is_not_never_started(capsys, monkeypatch):
    # Fresh-eyes PR #52, finding 1: for a non-timeline reviewer there is no
    # in-flight signal, so the TIMEOUT note must NOT claim "never started"
    # (Codex may well be mid-review). It should say it didn't complete instead.
    _patch_api(monkeypatch)  # open PR, no verdict, no timeline
    rc = cw.watch("o/r", 1, timeout_min=0, poll_sec=0, since=None, profile=CODEX)
    out = capsys.readouterr().out
    assert rc == 2 and "RESULT: TIMEOUT" in out
    assert "never started" not in out
    assert "did not complete" in out


def test_default_reviewer_is_codex(monkeypatch):
    # The Copilot->Codex cutover (bd hrn.9) flips the --reviewer DEFAULT to codex,
    # so a watch launched without --reviewer drives the Codex profile. Stub watch()
    # to capture the profile main() selected from the default.
    seen = {}

    def fake_watch(repo, pr, timeout_min, poll_sec, since, profile):
        seen["profile"] = profile
        return cw._emit("CLEAN", "stub")
    monkeypatch.setattr(cw, "watch", fake_watch)
    cw.main(["1"])  # no --reviewer -> default
    assert seen["profile"].key == "codex"


def test_reviewer_copilot_still_selectable(monkeypatch):
    # The legacy copilot profile is still reachable via an explicit --reviewer
    # (kept for the generic watcher; the cutover only changed the default).
    seen = {}

    def fake_watch(repo, pr, timeout_min, poll_sec, since, profile):
        seen["profile"] = profile
        return cw._emit("CLEAN", "stub")
    monkeypatch.setattr(cw, "watch", fake_watch)
    cw.main(["1", "--reviewer", "copilot"])
    assert seen["profile"].key == "copilot"


def test_copilot_closed_without_merge_still_clean(capsys, monkeypatch):
    # Guard: the finding-2 fix must NOT regress Copilot. A closed-not-merged PR
    # with no Copilot timeline activity (state is None) still reaches CLEAN.
    _patch_api(monkeypatch, pr_state="closed")
    rc = cw.watch("o/r", 1, timeout_min=1, poll_sec=0, since=None, profile=PROFILE)
    out = capsys.readouterr().out
    assert rc == 0 and "RESULT: CLEAN" in out
    assert "closed" in out.lower()


# --- --close-on-clean: deterministic CLEAN-trigger bead close (bd hrn.14) ---
# The close fires ONLY on the CLEAN terminal state, never on COMMENTS / ERROR /
# TIMEOUT / MERGED, and never without the flag. A failed close downgrades the
# exit to EXIT_CLOSE_FAILED so the orchestrator triages instead of pinging
# "ready to merge". These tests stub watch() (to drive the terminal state via
# _emit, which sets cw._LAST_STATE) and _close_beads_on_clean (to spy on whether
# the close fired) -- no network, no bd/git.

def _run_main_with_state(monkeypatch, state, close_args, *, close_rc=0,
                         review_verdict=True):
    """Drive main() with a stubbed watch() that emits `state`, recording whether
    the bead-close ran. Returns (exit_code, close_called, beads_passed).

    `review_verdict` controls whether a CLEAN is marked a genuine passed-review
    verdict (the close gate) vs. a "no review pending" CLEAN (abandoned PR)."""
    # Reset the module-level state so a prior test can't leak a stale CLEAN into
    # this run's close gate (test-order independence -- fresh-eyes PR #60 #4).
    monkeypatch.setattr(cw, "_LAST_STATE", None)
    monkeypatch.setattr(cw, "_LAST_CLEAN_WAS_REVIEW", False)

    def fake_watch(repo, pr, timeout_min, poll_sec, since, profile):
        return cw._emit(state, "{} (stubbed)".format(state),
                        review_verdict=review_verdict)
    monkeypatch.setattr(cw, "watch", fake_watch)

    calls = {}

    def fake_close(beads):
        calls["beads"] = list(beads)
        return close_rc
    monkeypatch.setattr(cw, "_close_beads_on_clean", fake_close)

    argv = ["1", *close_args]
    rc = cw.main(argv)
    return rc, ("beads" in calls), calls.get("beads")


@pytest.mark.parametrize("state", ["COMMENTS", "ERROR", "TIMEOUT", "MERGED"])
def test_close_on_clean_does_not_fire_on_non_clean_state(monkeypatch, state):
    rc, called, _ = _run_main_with_state(
        monkeypatch, state, ["--close-on-clean", "polyglot-pdf-x1"])
    assert called is False, "{} must NOT trigger the bead close".format(state)
    # The exit code stays the review's own state code (close never ran).
    assert rc == cw._EXIT_CODES[state]


def test_close_on_clean_fires_on_clean(monkeypatch):
    rc, called, beads = _run_main_with_state(
        monkeypatch, "CLEAN",
        ["--close-on-clean", "polyglot-pdf-x1", "--close-on-clean", "polyglot-pdf-x2"])
    assert called is True
    assert beads == ["polyglot-pdf-x1", "polyglot-pdf-x2"]
    assert rc == 0  # CLEAN + successful close


def test_clean_without_flag_does_not_close(monkeypatch):
    rc, called, _ = _run_main_with_state(monkeypatch, "CLEAN", [])
    assert called is False  # no --close-on-clean -> unchanged behavior
    assert rc == 0


def test_close_failure_downgrades_exit_for_triage(monkeypatch):
    # CLEAN review, but the close itself fails -> EXIT_CLOSE_FAILED so the
    # orchestrator is woken to triage, never handed a false "ready to merge".
    rc, called, _ = _run_main_with_state(
        monkeypatch, "CLEAN", ["--close-on-clean", "polyglot-pdf-x1"],
        close_rc=cw.EXIT_CLOSE_FAILED)
    assert called is True
    assert rc == cw.EXIT_CLOSE_FAILED


def test_clean_that_is_not_a_review_verdict_does_not_close(monkeypatch):
    # A CLEAN that is NOT a passed-review verdict (e.g. an abandoned PR closed
    # without merge -> "no review pending") must NOT close the bead -- that would
    # mark un-shipped work done (fresh-eyes PR #60, Finding 1).
    rc, called, _ = _run_main_with_state(
        monkeypatch, "CLEAN", ["--close-on-clean", "polyglot-pdf-x1"],
        review_verdict=False)
    assert called is False
    assert rc == 0


def test_closed_without_merge_does_not_close_bead_real_path(monkeypatch, capsys):
    # End-to-end via the REAL watch(): a closed-without-merge PR emits CLEAN
    # ("no review pending"), but with --close-on-clean the bead must stay open.
    # This is the actual Finding-1 path (the stubbed test above pins the gate;
    # this pins that the real watch() marks this CLEAN as non-verdict).
    _patch_api(monkeypatch, pr_state="closed")
    monkeypatch.setattr(cw, "_LAST_STATE", None)
    monkeypatch.setattr(cw, "_LAST_CLEAN_WAS_REVIEW", False)
    spy = {}
    monkeypatch.setattr(cw, "_close_beads_on_clean",
                        lambda beads: spy.setdefault("called", beads) or 0)
    rc = cw.main(["1", "--repo", "o/r", "--timeout-min", "1", "--poll-sec", "0",
                  "--close-on-clean", "polyglot-pdf-x1"])
    out = capsys.readouterr().out
    assert "RESULT: CLEAN" in out          # the review verdict is still CLEAN
    assert "called" not in spy             # but the bead close did NOT fire
    assert rc == 0


def test_genuine_review_clean_sets_verdict_flag(monkeypatch, capsys):
    # The genuine "review complete with no findings" CLEAN must mark the verdict
    # flag so the close CAN fire (the positive half of Finding 1's fix).
    review = {"user": {"login": "Copilot"}, "state": "COMMENTED", "body": "",
              "submitted_at": "2026-05-28T12:00:02Z", "id": 1}
    monkeypatch.setattr(cw, "_LAST_CLEAN_WAS_REVIEW", False)
    _run_watch_result(
        capsys, monkeypatch, reviews=[review], timeline=[_reviewed_event()])
    assert cw._LAST_STATE == "CLEAN"
    assert cw._LAST_CLEAN_WAS_REVIEW is True


def test_codex_thumbs_up_issue_comment_clean_sets_verdict_flag(capsys, monkeypatch):
    # Codex's clean re-review arrives as an ISSUE COMMENT + a +1 reaction, NOT a
    # formal review -- so the issue-comment CLEAN path MUST set the verdict flag,
    # or --close-on-clean silently never fires on the common Codex path and a
    # review-worthy PR stalls after a clean re-review (Codex review, PR #118).
    issue = [{
        "user": {"login": _CODEX_LOGIN},
        "created_at": "2026-06-01T12:00:00Z",
        "body": "Didn't find any major issues.",
        "reactions": {"+1": 1},
    }]
    monkeypatch.setattr(cw, "_LAST_CLEAN_WAS_REVIEW", False)
    _patch_api(monkeypatch, issue=issue)
    rc = cw.watch("o/r", 1, timeout_min=1, poll_sec=0, since=None, profile=CODEX)
    out = capsys.readouterr().out
    assert rc == 0 and "RESULT: CLEAN" in out
    assert cw._LAST_CLEAN_WAS_REVIEW is True  # the close gate is now satisfied


def test_codex_clean_sentinel_issue_comment_sets_verdict_flag(capsys, monkeypatch):
    # The EXPLICIT prose-approval path (a clean sentinel / LGTM, no reaction) is a
    # genuine sign-off, so it sets the flag -- a clean re-review with the text
    # sentinel only still closes the bead.
    issue = [{
        "user": {"login": _CODEX_LOGIN},
        "created_at": "2026-06-01T12:00:00Z",
        "body": "no major issues",  # a clean sentinel, no reaction
    }]
    monkeypatch.setattr(cw, "_LAST_CLEAN_WAS_REVIEW", False)
    _patch_api(monkeypatch, issue=issue)
    rc = cw.watch("o/r", 1, timeout_min=1, poll_sec=0, since=None, profile=CODEX)
    out = capsys.readouterr().out
    assert rc == 0 and "RESULT: CLEAN" in out
    assert cw._LAST_CLEAN_WAS_REVIEW is True


def test_codex_neutral_comment_clean_does_NOT_set_verdict_flag(capsys, monkeypatch):
    # The "approval by ABSENCE" path (a neutral comment with no change-ask AND no
    # approval reaction/sentinel) reports CLEAN but must NOT set the verdict flag,
    # so --close-on-clean does NOT close the bead on a mere progress/ack note --
    # only an explicit approval may close (Codex review, PR #118, round 3). Without
    # this gate a neutral "looking into it" comment could mark work done.
    issue = [{
        "user": {"login": _CODEX_LOGIN},
        "created_at": "2026-06-01T12:00:00Z",
        "body": "Acknowledged, taking a look at this now.",  # neutral, no sign-off
    }]
    monkeypatch.setattr(cw, "_LAST_CLEAN_WAS_REVIEW", False)
    _patch_api(monkeypatch, issue=issue)
    rc = cw.watch("o/r", 1, timeout_min=1, poll_sec=0, since=None, profile=CODEX)
    out = capsys.readouterr().out
    assert rc == 0 and "RESULT: CLEAN" in out          # the loop still ends CLEAN
    assert cw._LAST_CLEAN_WAS_REVIEW is False          # but the close gate stays shut


def test_close_beads_on_clean_invokes_close_only(monkeypatch):
    # The close shells out to closeout_finish.py --close-only with one --bead per
    # id (the verified bd_safe close path); assert the command shape, no real run.
    seen = {}

    class _Proc:
        returncode = 0
        stdout = "CLOSED-ONLY"
        stderr = ""

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return _Proc()
    monkeypatch.setattr(cw.subprocess, "run", fake_run)

    rc = cw._close_beads_on_clean(["polyglot-pdf-a", "polyglot-pdf-b"])
    assert rc == 0
    cmd = seen["cmd"]
    assert cmd[1].endswith("closeout_finish.py")
    assert "--close-only" in cmd
    assert cmd.count("--bead") == 2
    assert "polyglot-pdf-a" in cmd and "polyglot-pdf-b" in cmd
    # Must NOT carry any PR-opening / telemetry flags -- close-only is the whole
    # contract (bead state syncs via bd dolt push, not the PR).
    for forbidden in ("--review-worthy", "--branch", "--pr-title", "--arm"):
        assert forbidden not in cmd
