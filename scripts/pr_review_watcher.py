"""Watch a GitHub PR for a bot code-review COMPLETION, then exit.

Supports two reviewers behind `--reviewer copilot|codex` (default: copilot).
The CLASSIFICATION logic (approval-phrase / change-ask / inline-findings-first
heuristics) is shared and reviewer-agnostic -- it is the product of many past
false-positive/false-negative fixes (each cited `bd <id>`), so it is preserved
verbatim across reviewers. Only the reviewer-SPECIFIC bits vary, and they are
isolated in a `ReviewerProfile` (see PROFILES below): the bot login marker, how
"the review finished" is detected, the error sentinel, and the clean signal.

Background
----------
The development cycle waits on the bot's review after every re-trigger
("@copilot please review" / "@codex review"). Historically the orchestrating
agent polled `gh api .../comments` every few minutes -- each poll a full,
expensive model turn that did nothing but run one shell command and check
whether a counter moved. This script moves that wait OUT of the model: run it
via the agent harness's `run_in_background`, and the agent is woken exactly
once, when the review reaches a terminal state, with the verdict already
classified. Zero polling turns.

Why "review completion", not "a new comment"
---------------------------------------------
The COMMON case is the bot finishing a review with NO inline comments (just a
completed review whose state, or a 👍 reaction, is the verdict). "No comment
yet" and "done, nothing to say" look identical if you only watch the
inline-comment stream, so a naive new-comment watcher would hang forever on a
clean review. This script instead watches for the review to COMPLETE and then
classifies the terminal state.

Detecting "the review finished" (reviewer-specific)
---------------------------------------------------
COPILOT exposes a lifecycle on the issue TIMELINE (`/issues/{n}/timeline`):
  copilot_work_started   -> in flight; keep waiting (no premature TIMEOUT)
  reviewed               -> a verdict submitted; classify it (below)
  copilot_work_finished  -> Copilot done, produced no review -> CLEAN
These are the authoritative "where is the review" signals -- the
reviews/comments endpoints only populate after a verdict submits, so they
can't tell "not started" from "in progress" from "finished with nothing."

CODEX emits NO such timeline events. Its completion is detected directly from
the review surfaces: a posted review / inline comments (= findings), or its
clean sentinel -- a 👍 reaction plus a "Codex Review: Didn't find any major
issues" issue comment. With no in-flight signal, the Codex profile relies on
the --since floor and the timeout to bound the wait.

Once the review has landed, the findings come from three surfaces (a verdict
can land on any; watching one misses the others):

  1. Inline review comments  -> GET /repos/{o}/{r}/pulls/{n}/comments
  2. Top-level reviews        -> GET /repos/{o}/{r}/pulls/{n}/reviews
  3. PR issue comments        -> GET /repos/{o}/{r}/issues/{n}/comments

A review event whose body is the reviewer's error sentinel (e.g. "Copilot
encountered an error...") is an ERROR, not a finding.

Two staleness traps these surfaces hide, both handled:

  - An inline comment whose `position` is null is OUTDATED -- its anchor fell
    out of the current diff after later commits. GitHub never deletes it, and
    it re-matches its (frozen) review by id on every poll, so a resolved
    round-1 comment would loop the closeout forever. Outdated inline comments
    are dropped (a genuine new finding has a non-null position).
  - A RE-review verdict (after the re-trigger) frequently lands as an ISSUE
    COMMENT, not a formal review -- it has no state and never appears in
    /reviews. Reading /reviews alone would re-select the frozen prior review
    (false COMMENTS) or, with a --since floor, find nothing (false TIMEOUT). So
    when no in-window review exists, we classify from the latest in-window bot
    issue comment: an explicit approval phrase ("no further changes...") ->
    CLEAN, otherwise COMMENTS.

Terminal states (printed as the final line: "RESULT: <STATE>")
--------------------------------------------------------------
  COMMENTS -- review complete, the bot left findings. The findings are
              printed so the agent sees them without another API call.
  CLEAN    -- review complete, no findings (the common case). Also covers a
              PR that was closed WITHOUT being merged while nothing was pending.
  MERGED   -- the PR was merged while watching (the merge event lands in the
              same timeline this script polls). Lets the caller skip a separate
              `gh pr view` to learn the outcome: treat it as "done + already
              merged" -> skip the maintainer-merge ping, go straight to bead
              close. Exit 0, like CLEAN.
  ERROR    -- the review failed or the bot hit a quota/availability error.
              Surfaced to the user; NO auto-retry (a quota error will not
              clear for hours, so backoff just burns wall-clock). The user
              decides whether to wait out the reset or proceed without a review.
  TIMEOUT  -- no completed review appeared within --timeout-min. Distinct
              from ERROR (exit code 2 vs 1) so a caller can retry-later on a
              timeout but investigate on a genuine failure.

Any unexpected crash is caught and reported as RESULT: ERROR with the
exception text, so the agent is woken with a real signal rather than the
script dying silently (which would look like "still waiting" forever).

Usage
-----
    python scripts/pr_review_watcher.py <pr-number> [--reviewer copilot|codex]
        [--repo OWNER/REPO] [--timeout-min N] [--poll-sec N] [--since ISO8601]

`--since` lets the caller scope detection to reviews/comments created after
a known timestamp (e.g. the moment of a "@codex review" re-trigger), so a
re-review loop does not re-detect the previous round's verdict.

Exit codes: 0 for COMMENTS/CLEAN/MERGED, 1 for ERROR, 2 for TIMEOUT. TIMEOUT and
ERROR are distinct so a shell caller can retry-later on a timeout but
investigate on a genuine error. The RESULT line is the contract; the exit
code mirrors it for shell callers.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone

# Make this script's dir importable so `import swarm_config` works under both
# direct execution and importlib-based test loading (see bd_safe.py note).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import swarm_config  # noqa: E402


def _setup_utf8_stdio() -> None:
    """Force stdout/stderr to UTF-8 so printing review text can't crash.

    Copilot review bodies routinely contain emoji (e.g. 💡) and other
    non-Latin-1 characters. On Windows the default console encoding is cp1252,
    so printing a review detail raises UnicodeEncodeError and crashes the
    watcher AFTER it has already classified the verdict -- the caller then sees
    a bogus RESULT: ERROR (see bead polyglot-pdf-39a). errors="replace" lets any
    undisplayable glyph degrade to a placeholder instead of killing the process.

    Called from main() (NOT at import time) so importing this module for its
    helpers -- e.g. the test suite -- does not mutate the process's shared
    sys.stdout encoding as a side effect.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                # Stream already detached/redirected in a way that rejects
                # reconfigure; the per-print fallback (_safe_print) still
                # protects us.
                pass

# Review states that represent a CURRENT verdict. APPROVED /
# CHANGES_REQUESTED / COMMENTED are "the review finished with a verdict";
# PENDING is still in progress. DISMISSED is deliberately EXCLUDED: a
# dismissed review is not a current verdict (it was cleared, usually during
# a re-review), so treating it as terminal would make the watcher exit early
# on a stale review while the real new verdict is still pending.
TERMINAL_REVIEW_STATES = {"APPROVED", "CHANGES_REQUESTED", "COMMENTED"}

# Non-APPROVED terminal states are a verdict EVEN WITH AN EMPTY BODY -- the
# state itself is the signal, so they must classify as COMMENTS, never CLEAN.
NON_CLEAN_STATES = {"CHANGES_REQUESTED"}

# Copilot's lifecycle on the issue TIMELINE (/issues/{n}/timeline). These are
# the authoritative "where is the review" signals for Copilot -- the
# reviews/comments endpoints only populate after a verdict submits, so they
# can't distinguish "not started" from "in progress" from "finished with
# nothing." Event names confirmed against live PRs 2026-05-29. CODEX does NOT
# emit these (its profile detects completion from the review surfaces instead).
COPILOT_WORK_STARTED = "copilot_work_started"    # in flight -- keep waiting
COPILOT_WORK_FINISHED = "copilot_work_finished"  # terminal: done (may be CLEAN)
TIMELINE_REVIEWED = "reviewed"                    # terminal: a verdict submitted


@dataclass(frozen=True)
class ReviewerProfile:
    """The reviewer-SPECIFIC knobs the shared classifier reads.

    Everything that differs between GitHub Copilot and OpenAI Codex lives here;
    the classification heuristics below take a profile and are otherwise
    identical for both. Adding a third reviewer is a new profile, not new
    branching in the classifier.

    Fields:
      key                -- the --reviewer value ("copilot" / "codex").
      label              -- human name for messages ("Copilot" / "Codex").
      login_markers      -- case-insensitive substrings that identify the bot's
                            login. Must match the bot specifically and NOT the
                            generic "github-actions[bot]" actor (shared by every
                            Actions workflow -- matching it would misclassify an
                            unrelated bot's review as this reviewer's verdict).
      error_body_prefix  -- a review/comment body starting with this is the
                            bot's failure sentinel (quota/availability), NOT a
                            finding -> ERROR.
      uses_timeline      -- True if the bot emits copilot_work_* timeline
                            events (Copilot). False (Codex) means completion is
                            inferred from the review surfaces + --since floor.
      clean_sentinels    -- extra issue-comment phrases that mean "done, no
                            findings" for THIS reviewer (e.g. Codex's "didn't
                            find any major issues"). Merged into the shared
                            approval check; the shared LGTM/no-further-changes
                            phrases apply to every reviewer.
      clean_reaction     -- a GitHub reaction (rollup key, e.g. "+1" for 👍) the
                            bot adds to its OWN comment to signal approval. When
                            set, a bot comment carrying this reaction with a
                            positive count classifies CLEAN -- the canonical,
                            language-independent approval signal. None for a
                            reviewer that signals approval only in prose
                            (Copilot). The rollup ships inline on the comment
                            payload (comment["reactions"]["+1"]), so this costs
                            no extra API call.
    """

    key: str
    label: str
    login_markers: tuple[str, ...]
    error_body_prefix: str
    uses_timeline: bool
    clean_sentinels: tuple[str, ...] = ()
    clean_reaction: str | None = None


# Copilot: review actor login carries "copilot" (e.g.
# "copilot-pull-request-reviewer[bot]"); emits copilot_work_* timeline events;
# fails with "Copilot encountered an error...".
COPILOT_PROFILE = ReviewerProfile(
    key="copilot",
    label="Copilot",
    login_markers=("copilot",),
    error_body_prefix="Copilot encountered an error",
    uses_timeline=True,
)

# Codex (OpenAI ChatGPT GitHub app): review actor login is
# "chatgpt-codex-connector[bot]" (confirmed from a live PR 2026-06-01). Emits
# NO timeline lifecycle events -- completion is detected from the review
# surfaces. The CANONICAL clean signal is a 👍 ("+1") reaction Codex adds to its
# own approval comment (documented behavior) -- `clean_reaction="+1"` makes that
# the primary CLEAN path, independent of the comment's prose/language. The text
# sentinels below ("Codex Review: Didn't find any major issues") are a
# belt-and-suspenders fallback for a clean comment that arrives before/without
# the reaction. The bot does NOT carry "copilot" in its login, so the markers
# stay disjoint and a Codex run never matches a Copilot comment.
CODEX_PROFILE = ReviewerProfile(
    key="codex",
    label="Codex",
    login_markers=("codex",),
    error_body_prefix="Codex encountered an error",
    uses_timeline=False,
    clean_reaction="+1",  # 👍 -- the documented canonical approval signal
    clean_sentinels=(
        "didn't find any major issues",   # straight apostrophe U+0027
        "didn’t find any major issues",   # NOT a duplicate -- curly apostrophe U+2019;
                                          # GitHub's markdown renderer emits this form.
                                          # Both variants are pinned by a test; keep both.
        "no major issues",                # apostrophe-free fallback
    ),
)

PROFILES = {p.key: p for p in (COPILOT_PROFILE, CODEX_PROFILE)}


def _run_gh_api(path: str) -> object:
    """Call `gh api --paginate <path>` and return parsed JSON.

    `--paginate` follows GitHub's Link headers so a PR with more than one
    page of comments/reviews (>30 by default) is returned in full rather
    than silently truncated. For list endpoints, gh concatenates the pages
    into a single JSON array.

    Raises RuntimeError on non-zero exit or unparseable output so the caller
    can classify it as ERROR rather than crashing.
    """
    # encoding="utf-8" is REQUIRED: GitHub's API returns UTF-8, but
    # text=True alone decodes with the platform default (cp1252 on Windows),
    # which crashes the subprocess reader thread on any non-cp1252 byte --
    # e.g. a curly quote in a Copilot review body. errors="replace" keeps a
    # stray undecodable byte from being fatal.
    # TimeoutExpired (a hung gh call) and OSError (gh missing / not on PATH)
    # are converted to RuntimeError so the caller's transient-retry path
    # handles them, rather than escaping as an "Unexpected crash".
    try:
        proc = subprocess.run(
            ["gh", "api", "--paginate", path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("gh api {} timed out after 60s".format(path))
    except OSError as exc:
        raise RuntimeError("gh api {} could not run: {}".format(path, exc))
    if proc.returncode != 0:
        raise RuntimeError(
            "gh api {} failed (exit {}): {}".format(
                path, proc.returncode, proc.stderr.strip() or "no stderr"
            )
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("gh api {} returned non-JSON: {}".format(path, exc))


def _is_reviewer(login: str, profile: ReviewerProfile) -> bool:
    """True if `login` is the configured reviewer bot (per the profile markers)."""
    lo = (login or "").lower()
    return any(marker in lo for marker in profile.login_markers)


def _parse_iso(ts: str) -> datetime:
    """Parse a GitHub ISO8601 timestamp (e.g. 2026-05-28T12:00:00Z)."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _after(ts: str, since: datetime | None) -> bool:
    """True if the timestamp is at/after `since` (or if no `since` filter)."""
    if since is None:
        return True
    try:
        return _parse_iso(ts) >= since
    except (ValueError, AttributeError):
        # Unparseable timestamp -- include it rather than silently drop a
        # possibly-real verdict.
        return True


def _pr_closed_state(repo: str, pr: int) -> str | None:
    """Return the PR's terminal disposition, or None if still open.

    - "merged"  -> the PR was merged (`merged_at` set, or `merged` true)
    - "closed"  -> closed WITHOUT merging
    - None      -> still open
    Merge detection reads `merged` / `merged_at` directly from the PR payload
    (`repos/{owner}/{repo}/pulls/{number}`), avoiding a separate `gh pr view`.
    """
    data = _run_gh_api("repos/{}/pulls/{}".format(repo, pr))
    if not isinstance(data, dict) or data.get("state") != "closed":
        return None
    if data.get("merged") or data.get("merged_at"):
        return "merged"
    return "closed"


def _latest_reviewer_review(repo: str, pr: int, since: datetime | None, profile: ReviewerProfile):
    """Return the most recent COMPLETED review by this reviewer at/after `since`, or None.

    Surface 2 (top-level reviews). A completed review IS the verdict even
    when it carries no inline comments -- this is how CLEAN is detected. We
    return only the LATEST one so that findings can be scoped to this round
    (see _collect_findings); a stale prior-round review must not set the
    floor for the current round's findings.
    """
    latest = None
    latest_ts = None
    for rv in _run_gh_api("repos/{}/pulls/{}/reviews".format(repo, pr)) or []:
        login = (rv.get("user") or {}).get("login", "")
        state = rv.get("state", "")
        submitted = rv.get("submitted_at") or rv.get("created_at") or ""
        if not _is_reviewer(login, profile):
            continue
        if state not in TERMINAL_REVIEW_STATES:
            continue  # PENDING -- still reviewing
        if not _after(submitted, since):
            continue
        try:
            ts = _parse_iso(submitted)
        except (ValueError, AttributeError):
            ts = None
        # Prefer the review with the latest parseable timestamp; an
        # unparseable timestamp loses to any parseable one but still beats
        # nothing.
        if latest is None or (ts is not None and (latest_ts is None or ts > latest_ts)):
            latest, latest_ts = rv, ts
    return latest


def _timeline_state(repo: str, pr: int, since: datetime | None, profile: ReviewerProfile):
    """Read the reviewer's lifecycle from the issue timeline.

    Returns one of:
      "reviewed"  -- a `reviewed` event landed (verdict; classify via reviews
                     endpoint -- could be COMMENTS / CLEAN / ERROR-body).
      "finished"  -- `copilot_work_finished` with no later `reviewed`: the bot
                     is done and produced no review -> treat as CLEAN.
      "working"   -- `copilot_work_started` seen, no terminal event yet: keep
                     waiting (do NOT TIMEOUT prematurely; a verdict is coming).
      None        -- no reviewer activity at/after `since`: not started yet.

    For a reviewer that emits NO timeline lifecycle events (Codex,
    `profile.uses_timeline == False`), there is no in-flight signal to read, so
    this always returns "reviewed" -- meaning "go look at the review surfaces
    directly." The surface classifiers (`_classify_reviewed` ->
    `_classify_issue_comment_round`) return None when nothing has landed yet,
    which the poll loop treats as "keep waiting," so we still don't TIMEOUT
    prematurely; the --since floor and timeout bound the wait instead.

    Only events at/after `since` count, so a re-review round is not confused
    with the previous round's terminal events.
    """
    if not profile.uses_timeline:
        return "reviewed"
    started = finished = reviewed = False
    for ev in _run_gh_api("repos/{}/issues/{}/timeline".format(repo, pr)) or []:
        name = ev.get("event", "")
        actor = (ev.get("actor") or ev.get("user") or {}).get("login", "")
        when = ev.get("created_at") or ev.get("submitted_at") or ""
        # review_requested carries the requester as actor (a human), so don't
        # gate the copilot_* / reviewed events on actor being the bot for the
        # request event; but the work/review events themselves are the bot's.
        if name == TIMELINE_REVIEWED and _is_reviewer(actor, profile) and _after(when, since):
            reviewed = True
        elif name == COPILOT_WORK_FINISHED and _after(when, since):
            finished = True
        elif name == COPILOT_WORK_STARTED and _after(when, since):
            started = True
    if reviewed:
        return "reviewed"
    if finished:
        return "finished"
    if started:
        return "working"
    return None


def _collect_findings(repo: str, pr: int, floor: datetime | None, review: dict, profile: ReviewerProfile):
    """Collect the reviewer's findings tied to the current review round.

    Inline comments are matched EXACTLY to this round by
    `pull_request_review_id == review['id']` -- not by timestamp. Copilot
    posts its inline comments slightly BEFORE it submits the review, so
    flooring inline comments at the review's `submitted_at` would drop
    same-round findings and misclassify as CLEAN. The review_id link is the
    authoritative round boundary for inline comments.

    Issue comments have no review_id, so they fall back to the `floor`
    timestamp (the round boundary derived from the review / caller --since),
    which keeps prior-round issue comments from leaking in. The review's own
    summary body is counted ONLY when it contains an explicit change-ask -- a
    COMMENTED review always carries a neutral "## Pull request overview" summary,
    so counting every non-empty body would make a clean review read as COMMENTS.
    """
    findings = []
    review_id = review.get("id")

    # The review's summary BODY is not itself an actionable finding -- a
    # COMMENTED review always carries an "## Pull request overview" summary even
    # when Copilot has nothing to change, so counting the body would make every
    # clean review read as COMMENTS. Count the body only if it explicitly asks
    # for a change (mirrors the issue-comment rule); otherwise it's context. The
    # caller still flips to COMMENTS on a CHANGES_REQUESTED state or any inline
    # finding below, so a genuine verdict is never lost.
    body = (review.get("body") or "").strip()
    if body and _has_change_ask(body) and not _is_approval_comment(body, profile):
        findings.append("[review:{}] {}".format(review.get("state", "?"), body))

    # Surface 1: inline review comments, matched to THIS review by id.
    for c in _run_gh_api("repos/{}/pulls/{}/comments".format(repo, pr)) or []:
        login = (c.get("user") or {}).get("login", "")
        if _is_reviewer(login, profile) and c.get("pull_request_review_id") == review_id:
            # GitHub sets `position` to null once a comment's anchor falls out
            # of the CURRENT diff -- the canonical "outdated" signal. An
            # outdated comment is a prior round's finding that later commits
            # moved past; re-reporting it loops the closeout forever (a
            # COMMENTED review's stale comment re-matches by id every poll).
            # Require `position` PRESENT-and-null (real GitHub always includes
            # the key); a payload missing the key is NOT treated as outdated,
            # so we never drop a finding on a partial response. A genuine new
            # finding lands on the current diff with a non-null position, so
            # this never hides live feedback. State still wins upstream: a
            # CHANGES_REQUESTED verdict stays COMMENTS even if its comments drop.
            if "position" in c and c["position"] is None:
                continue
            loc = c.get("path", "?")
            line = c.get("line") or c.get("original_line") or "?"
            findings.append(
                "[inline {}:{}] {}".format(loc, line, (c.get("body") or "").strip())
            )

    # Surface 3: PR issue comments, scoped to this round by timestamp (no
    # review_id linkage exists for issue comments). A comment counts as a finding
    # ONLY if it explicitly asks for a change -- an approval ("LGTM") or a neutral
    # summary/acknowledgement is NOT a finding. This keeps the findings-based
    # invariant: novel approval/summary prose can't flip a clean round to COMMENTS,
    # while a prose-only "please fix X" is still caught by the change-ask gate.
    for c in _run_gh_api("repos/{}/issues/{}/comments".format(repo, pr)) or []:
        login = (c.get("user") or {}).get("login", "")
        created = c.get("created_at", "")
        body = (c.get("body") or "").strip()
        if (
            _is_reviewer(login, profile)
            and _after(created, floor)
            and not _is_approval_comment(body, profile)
            and _has_change_ask(body)
        ):
            findings.append("[issue-comment] {}".format(body))

    return findings


# Exit codes by terminal state. COMMENTS/CLEAN are "the review happened"
# (success); TIMEOUT and ERROR are distinct so a shell caller can branch
# (retry-later on TIMEOUT vs investigate on ERROR) without parsing text.
_EXIT_CODES = {"COMMENTS": 0, "CLEAN": 0, "MERGED": 0, "TIMEOUT": 2, "ERROR": 1}

# Consecutive transient-error tolerance before giving up. A 1-second network
# blip or token refresh should not be terminal; a real quota exhaustion will
# fail every poll and trip this after a few rounds without long backoff.
MAX_CONSECUTIVE_API_ERRORS = 3


def _safe_print(text: str) -> None:
    """print() that never dies on an un-encodable character.

    main()'s _setup_utf8_stdio() normally makes stdout UTF-8, but if that failed
    (detached/redirected stream) a stray emoji would still crash the print. Fall
    back to encoding through the stream's own codec with errors="replace" so the
    RESULT contract line always gets emitted. A truly unwritable stdout (e.g. a
    binary stream) is unrecoverable -- swallow that too rather than re-raising,
    since the whole point is to never die on output.
    """
    try:
        print(text)
    except UnicodeEncodeError:
        try:
            enc = getattr(sys.stdout, "encoding", None) or "utf-8"
            sys.stdout.write(text.encode(enc, "replace").decode(enc) + "\n")
        except Exception:  # noqa: BLE001 -- last resort: output must never crash us
            pass


def _emit(state: str, detail: str = "") -> int:
    """Print the contract result block and return the matching exit code."""
    if detail:
        _safe_print(detail)
    _safe_print("RESULT: {}".format(state))
    return _EXIT_CODES.get(state, 1)


# A Copilot re-review delivered as an issue comment approves with a phrase like
# "no further changes were needed". We classify CLEAN only when the comment is
# UNAMBIGUOUSLY an approval -- an approval phrase AND no change-asking signal in
# the same comment ("but please...", "however, fix...", a remaining numbered
# ask). A mixed comment ("no changes needed in section 3, but fix section 4")
# must stay COMMENTS. Erring toward COMMENTS preserves the core invariant: never
# read ambiguity as CLEAN.
# Phrasings Copilot uses to approve a re-review delivered as an issue comment.
# Each is an UNAMBIGUOUS "nothing to do" statement -- kept deliberately specific.
# Broad/bare forms ("no blocking issues", "no remaining issues", "nothing to
# address") were rejected: they can prefix a soft suggestion ("no blocking
# issues, I'd recommend...") and risk a FALSE CLEAN (which could merge past a
# real finding -- the dangerous direction). The "no outstanding findings" /
# "nothing further to address" forms were observed on PR #43 (bd polyglot-pdf-fau);
# #42's "I don't see any new blocking issues" is intentionally NOT matched.
_APPROVAL_PATTERNS = (
    "no further changes",
    "no changes are needed",
    "no changes needed",
    "no additional changes",
    "no further action",
    "no outstanding findings",
    "no outstanding issues",
    "nothing further to address",
    "nothing further to change",
)
# If any of these appear, the comment is asking for something -> NOT a clean
# approval, even if it also contains an approval phrase.
_CHANGE_ASK_SIGNALS = (
    " but ",
    "however",
    "please ",
    "should ",
    "needs to",
    "fix ",
    "missing",
    "incorrect",
    "consider ",
    # soft-recommendation markers: Copilot pairs an "approval" phrase with a
    # non-blocking suggestion ("no blocking issues, though I'd recommend...").
    # Treat those as a change-ask so they stay COMMENTS, not CLEAN. (bd fau)
    "recommend",
    "suggest",
    "though ",
    "worth ",
    # exception connectors: an approval phrase that carves out a real finding
    # ("no outstanding findings BEYOND the race condition"; "no further changes
    # needed OTHER THAN the TODO in auth.py"). (bd ztk)
    "beyond ",
    "other than",
    "except ",
    "aside from",
    "apart from",
)


# The canonical approval body the repo instructs Copilot to post when it has no
# findings (.github/copilot-instructions.md): the single word LGTM, alone. Matched
# EXACTLY (stripped, case-insensitive, tolerating the markdown/quote wrappers
# Copilot sometimes adds: **LGTM**, `LGTM`, "> LGTM") so it is a deterministic
# CLEAN that no _CHANGE_ASK_SIGNALS heuristic can veto. Pinning ONE fixed word is
# what ends the approval-phrase whack-a-mole: its classification can't drift.
def _is_exact_lgtm(body: str) -> bool:
    # Strip the markdown/quote wrappers and trailing sentence punctuation Copilot
    # sometimes adds (**LGTM**, `LGTM`, "> LGTM", "LGTM!", "LGTM.") so the one-word
    # signal still matches. The strip set is decoration only -- it can't turn a
    # non-LGTM body into "lgtm".
    stripped = (body or "").strip().strip("`*_>#\"' \t\r\n.!").strip()
    return stripped.lower() == "lgtm"


def _has_change_ask(body: str) -> bool:
    """True if the comment asks for any change (so it must stay COMMENTS)."""
    return any(sig in (body or "").lower() for sig in _CHANGE_ASK_SIGNALS)


# Max length / structure for a body to be approval-SHAPED. A genuine "nothing to
# do" note is short and flat; a comment that merely OPENS with an approval phrase
# but then appends a finding via an exception clause or a second paragraph
# ("No outstanding findings beyond the race condition in X"; "No further changes
# needed.\n\nOne minor observation: ...") is long/multi-block and must NOT ride the
# phrase allowlist to CLEAN (bd polyglot-pdf-ztk). The denylist can't enumerate
# every connector, so we gate on shape instead of chasing words.
_APPROVAL_SHAPE_MAX_CHARS = 200


# A markdown list-item marker at line start: a bullet (-, *, +) or an ordered
# marker (digits then '.' or ')') FOLLOWED BY whitespace. The trailing-space
# requirement is what distinguishes a list marker ("1. fix the helper") from a
# decimal in prose ("response time is 3.5s") -- the latter is not a list and must
# not trip the shape guard.
_LIST_MARKER_RE = re.compile(r"^(?:[-*+]|\d+[.)])\s")


def _is_approval_shaped(body: str) -> bool:
    """True if the body is short + single-paragraph + has no list/numbered items."""
    b = (body or "").strip()
    if len(b) > _APPROVAL_SHAPE_MAX_CHARS:
        return False
    if "\n\n" in b:  # more than one paragraph
        return False
    for line in b.splitlines():
        if _LIST_MARKER_RE.match(line.lstrip()):
            return False  # bullet or numbered list -> structured findings
    return True


def _is_approval_comment(body: str, profile: ReviewerProfile) -> bool:
    # Fast path: the exact canonical signal is always an approval, no heuristics.
    if _is_exact_lgtm(body):
        return True
    lo = (body or "").lower()
    # The reviewer's own clean sentinels (e.g. Codex's "didn't find any major
    # issues") are added to the shared approval phrasings. They still go through
    # the same shape + change-ask gates below, so a sentinel that appears inside a
    # long multi-finding comment does NOT ride to CLEAN -- the protections that
    # ended the Copilot whack-a-mole apply unchanged.
    approval_phrases = _APPROVAL_PATTERNS + profile.clean_sentinels
    if not any(p in lo for p in approval_phrases):
        return False
    # An approval phrase is present, but it only counts if the comment is also
    # approval-SHAPED (short/flat) AND does not ALSO ask for a change. A long or
    # multi-paragraph comment that merely starts with an approval phrase stays
    # COMMENTS -- the findings-based path below is the real backstop. (bd ztk)
    if not _is_approval_shaped(body):
        return False
    return not _has_change_ask(body)


def _has_clean_reaction(comment: dict, profile: ReviewerProfile) -> bool:
    """True if `comment` carries the profile's canonical approval reaction (👍).

    Reads the `reactions` rollup that GitHub ships INLINE on the comment payload
    (no extra API call): `comment["reactions"]["+1"]` is the count of 👍. A
    positive count means the bot signed off via its documented approval signal.
    Returns False when the profile defines no clean_reaction (Copilot), when the
    rollup is absent, or when the count is zero -- so it can only ever ADD a
    CLEAN signal, never suppress a finding.

    Note: the rollup is a count, not an actor list, so this does not prove the
    BOT (vs a human) added the 👍. The caller only consults it on a comment it
    has already attributed to the bot, and a human thumbs-up on the bot's own
    approval comment would agree with it anyway, so the count is sufficient.
    """
    if not profile.clean_reaction:
        return False
    rollup = comment.get("reactions")
    if not isinstance(rollup, dict):
        return False
    try:
        return int(rollup.get(profile.clean_reaction, 0)) > 0
    except (TypeError, ValueError):
        return False


def _latest_by_created(comments: list) -> dict | None:
    """Return the comment with the max `created_at` (ISO8601 sorts lexically).

    Don't rely on API list ordering -- pick the semantically latest explicitly.
    """
    if not comments:
        return None
    return max(comments, key=lambda c: c.get("created_at", ""))


def _new_inline_findings(repo: str, pr: int, since: datetime | None, profile: ReviewerProfile) -> list:
    """Actionable reviewer inline comments for THIS round (the deterministic core).

    An actionable finding is an inline review comment that (a) is the bot's,
    (b) lands on the CURRENT diff (non-null `position` -- a null position is an
    outdated prior-round anchor, never a live ask), and (c) was created at/after
    `since` (the round floor). This is the fact the whole classifier rests on:
    a real "please change X" from the bot is an inline comment on the diff. Its
    presence/absence does NOT depend on what words the bot puts in its summary,
    so it can't be defeated by novel approval phrasing.
    """
    findings = []
    for c in _run_gh_api("repos/{}/pulls/{}/comments".format(repo, pr)) or []:
        login = (c.get("user") or {}).get("login", "")
        if not _is_reviewer(login, profile):
            continue
        if "position" in c and c["position"] is None:
            continue  # outdated anchor -- not a live finding
        if not _after(c.get("created_at", ""), since):
            continue  # prior round
        loc = c.get("path", "?")
        line = c.get("line") or c.get("original_line") or "?"
        findings.append("[inline {}:{}] {}".format(loc, line, (c.get("body") or "").strip()))
    return findings


def _strip_quotes(body: str) -> str:
    """Drop markdown blockquote lines (`> ...`) from a comment body.

    Copilot's re-review issue comment ECHOES the trigger as a quote -- e.g. it
    opens with `> @copilot please review`. That quoted "please" tripped
    _has_change_ask and turned a clean acknowledgment into a false COMMENTS
    (bd polyglot-pdf-x8o). The quote is the trigger we sent, never Copilot's
    verdict, so strip all `>`-prefixed lines before any prose analysis. Leading
    whitespace before `>` is tolerated (nested/indented quotes).
    """
    return "\n".join(
        line for line in (body or "").splitlines() if not line.lstrip().startswith(">")
    )


def _classify_issue_comment_round(repo: str, pr: int, since: datetime | None, profile: ReviewerProfile):
    """Classify a round whose verdict arrives as a bot ISSUE COMMENT (no review).

    INLINE-FINDINGS-FIRST. The verdict leads on a STRUCTURAL fact the bot can't
    reword away -- whether it left a NEW actionable inline comment on the current
    diff this round -- because the approval-allowlist and change-ask-denylist prose
    heuristics are both unbounded-NL whack-a-mole. Prose is only a tie-breaker when
    there's no new inline finding, and it is analyzed on the QUOTE-STRIPPED body so
    the echoed `> @copilot please review` trigger can't masquerade as a change-ask
    (bd polyglot-pdf-x8o). Order:

      1. ERROR body -> ERROR (the bot failed; not a verdict).
      2. a NEW actionable inline finding this round -> COMMENTS. The primary signal:
         a real "please change X" from the bot is an inline comment on the diff,
         regardless of the summary prose's wording.
      3. the profile's canonical approval REACTION (Codex's 👍 / "+1") on the bot
         comment -> CLEAN. This is the documented, language-independent approval
         signal, so it ranks above prose -- but BELOW inline findings (a 👍 plus a
         real inline ask is still COMMENTS).
      4. exact `LGTM` / known approval phrase / reviewer clean sentinel -> CLEAN
         (fast path). For Codex this is the prose fallback when the reaction is
         absent ("Didn't find any major issues").
      5. change-ask prose (on the quote-stripped body) -> COMMENTS. Ungated: a
         genuine prose-only "please fix Y" is a real ask even on a PR that also has
         prior-round inline comments, so this must NOT be suppressed (an earlier
         gate here caused a false-CLEAN -- fresh-eyes on PR #49).
      6. otherwise -> CLEAN (no new inline finding, no change-ask -> approval by
         absence, whatever words the bot chose).

    Returns an exit code, or None if no bot issue comment at/after `since`
    exists yet (caller keeps polling -- the surface may just be lagging).
    Residual risk accepted: a substantive ask phrased with none of the change-ask
    signal words AND delivered with no inline anchor would read CLEAN; in practice
    the bot's actionable findings are inline, and human merge + fresh-eyes backstop.
    """
    bot_comments = [
        c
        for c in (_run_gh_api("repos/{}/issues/{}/comments".format(repo, pr)) or [])
        if _is_reviewer((c.get("user") or {}).get("login", ""), profile)
        and _after(c.get("created_at", ""), since)
    ]
    latest = _latest_by_created(bot_comments)
    if latest is None:
        return None
    body = (latest.get("body") or "").strip()
    # Analyze prose on the quote-stripped body so an echoed trigger ("> @codex
    # review") can't trip change-ask/approval heuristics. The full body is
    # still shown in the emitted detail for the human reader.
    prose = _strip_quotes(body)

    # 1. Bot-failed sentinel.
    if body.startswith(profile.error_body_prefix):
        return _emit("ERROR", "{} could not review this PR: {}".format(profile.label, body))

    # 2. PRIMARY signal: a NEW actionable inline finding this round -> COMMENTS.
    # This leads, so an acknowledgment that merely mentions a change-ask word
    # ("the issues raised were addressed") can no longer flip a clean round.
    inline = _new_inline_findings(repo, pr, since, profile)
    if inline:
        return _emit(
            "COMMENTS",
            "{} left {} inline finding(s) this round:\n\n{}".format(
                profile.label, len(inline), "\n\n".join(inline)
            ),
        )

    # 3. Canonical approval REACTION (Codex's 👍). The documented, language-
    # independent sign-off. Ranks above prose but below inline findings (checked
    # above), so a 👍 can never override a real inline ask.
    if _has_clean_reaction(latest, profile):
        return _emit(
            "CLEAN",
            "{} approved via {} reaction (no inline findings):\n\n{}".format(
                profile.label, profile.clean_reaction, body or "(empty comment)"
            ),
        )

    # 4. No reaction. An explicit prose approval (exact LGTM / known phrase /
    # reviewer clean sentinel) is the fallback CLEAN.
    if _is_approval_comment(prose, profile):
        return _emit(
            "CLEAN",
            "{} approved via issue comment (no inline findings):\n\n{}".format(
                profile.label, body
            ),
        )

    # 5. Change-ask prose (quote-stripped) -> COMMENTS. Ungated by design: a real
    # prose-only "please fix Y" must be caught even when the PR has prior-round
    # inline comments (gating this on inline-history caused a false-CLEAN).
    if _has_change_ask(prose):
        return _emit(
            "COMMENTS",
            "{}'s comment prose asks for a change:\n\n{}".format(profile.label, body),
        )

    # 6. No new inline finding, no approval reaction, not an explicit approval, no
    # prose-only ask -> the round is clean (approval by absence of any finding).
    return _emit(
        "CLEAN",
        "{} commented with no new inline finding this round -> treating as "
        "approval (verdict is by inline findings, not prose):\n\n{}".format(
            profile.label, body
        ),
    )


def _classify_reviewed(repo: str, pr: int, since: datetime | None, profile: ReviewerProfile):
    """A verdict is expected; fetch the review and emit it (or None to keep polling).

    Handles three sub-cases:
      - ERROR-body (the profile's error sentinel) -> ERROR, not a finding.
      - findings present OR a non-clean state (CHANGES_REQUESTED) -> COMMENTS.
      - otherwise -> CLEAN.
    If the findings fetch fails after we know a verdict exists, we still emit
    the verdict from the review body / state rather than discarding it.
    """
    review = _latest_reviewer_review(repo, pr, since, profile)
    if review is None:
        # No in-window formal REVIEW. Either (1) the bot delivered this round's
        # verdict as an ISSUE COMMENT (re-reviews often do -- no state, no
        # review_id, absent from /reviews; Codex's clean verdict is always an
        # issue comment + 👍), or (2) the reviews endpoint just hasn't caught up
        # yet. Try the issue-comment surface; if nothing there either, signal the
        # caller to keep polling.
        rc = _classify_issue_comment_round(repo, pr, since, profile)
        if rc is not None:
            return rc
        return None

    body = (review.get("body") or "").strip()
    state = review.get("state", "")

    if body.startswith(profile.error_body_prefix):
        return _emit("ERROR", "{} could not review this PR: {}".format(profile.label, body))

    floor = since
    submitted = review.get("submitted_at") or review.get("created_at") or ""
    try:
        review_ts = _parse_iso(submitted)
        if floor is None or review_ts > floor:
            floor = review_ts
    except (ValueError, AttributeError):
        pass

    try:
        findings = _collect_findings(repo, pr, floor, review, profile)
    except RuntimeError as exc:
        # Verdict already known -- do not throw it away on a secondary fetch
        # failure. Mirror the findings-based body rule: a COMMENTED review's
        # overview summary is NOT a finding, so a non-empty body alone is not
        # COMMENTS -- only a CHANGES_REQUESTED state or a change-ask body is.
        # (Using a plain `or body` here would flip every clean review to COMMENTS
        # whenever the inline fetch hiccups, since the overview body is always
        # present -- the exact false-COMMENTS this redesign removes.)
        body_is_finding = (
            bool(body) and _has_change_ask(body) and not _is_approval_comment(body, profile)
        )
        if state in NON_CLEAN_STATES or body_is_finding:
            return _emit(
                "COMMENTS",
                "{} review complete (state={}, could not fetch inline "
                "comments: {}). Body:\n\n{}".format(profile.label, state, exc, body or "(none)"),
            )
        return _emit(
            "CLEAN",
            "{} review complete, no actionable review-body finding "
            "(could not fetch inline comments: {}).".format(profile.label, exc),
        )

    # A CHANGES_REQUESTED state is a verdict even with no findings text.
    if findings or state in NON_CLEAN_STATES:
        detail = "{} left {} finding(s):\n\n{}".format(
            profile.label, len(findings), "\n\n".join(findings)
        ) if findings else "{} review state={} with no inline findings.".format(profile.label, state)
        return _emit("COMMENTS", detail)
    return _emit("CLEAN", "{} review complete with no findings.".format(profile.label))


def watch(repo: str, pr: int, timeout_min: int, poll_sec: int, since: datetime | None,
          profile: ReviewerProfile) -> int:
    """Poll until the reviewer reaches a terminal state, then classify.

    For a TIMELINE reviewer (Copilot): `copilot_work_started` means "keep
    waiting" (a verdict is coming, so we never TIMEOUT while it is provably
    mid-review); `reviewed` means classify the verdict; `copilot_work_finished`
    with no review means it finished and produced nothing (CLEAN).

    For a NON-timeline reviewer (Codex): `_timeline_state` returns "reviewed"
    every poll, so we probe the review surfaces directly each time;
    `_classify_reviewed` returns None until a verdict (review, or issue comment
    + clean sentinel) lands, which falls through to the wait below. There is no
    "working" signal, so the deadline alone bounds the wait.
    """
    deadline = time.monotonic() + timeout_min * 60
    consecutive_errors = 0
    while True:
        try:
            # A merge is the most decisive terminal state -- once the PR is
            # merged the review verdict is moot, and the merge event lands in
            # the same timeline. Check it FIRST so the caller learns "merged"
            # without a separate `gh pr view`, regardless of the bot's status.
            # (One fetch per poll; reused for the closed-without-merge case below.)
            closed_state = _pr_closed_state(repo, pr)
            if closed_state == "merged":
                return _emit("MERGED", "PR was merged; no review pending.")

            state = _timeline_state(repo, pr, since, profile)
            if state == "reviewed":
                rc = _classify_reviewed(repo, pr, since, profile)
                if rc is not None:
                    return rc
                # Verdict not landed/consistent yet -- fall through to wait.
            elif state == "finished":
                # Finished with no in-window formal review -- but the bot may
                # have delivered its verdict as an ISSUE COMMENT (the common
                # shape for a re-review). Classify that before concluding
                # "nothing to say."
                rc = _classify_issue_comment_round(repo, pr, since, profile)
                if rc is not None:
                    return rc
                return _emit(
                    "CLEAN", "{} finished work and produced no review.".format(profile.label)
                )
            # state == "working" or None -> keep polling (below). closed_state
            # (fetched above) carries the closed-without-merge case. Suppress it
            # ONLY while the bot is provably mid-review ("working"), so a review
            # that is in flight can still land even as the PR closes. We must NOT
            # suppress on "reviewed", because a NON-timeline reviewer (Codex)
            # ALWAYS reports "reviewed" (it has no in-flight signal) -- gating on
            # `state is not None` there made the closed-without-merge terminal
            # below structurally unreachable for Codex, so an abandoned Codex PR
            # would TIMEOUT instead of CLEAN (fresh-eyes PR #52). A genuine Codex
            # verdict is already returned above via _classify_reviewed; reaching
            # here means no verdict yet, so honoring closed_state is correct.
            if state == "working":
                closed_state = None
        except RuntimeError as exc:
            # Transient (network blip, token refresh, 5xx, gh hang/missing).
            # Retry within the poll loop; give up only after several in a row.
            consecutive_errors += 1
            if consecutive_errors >= MAX_CONSECUTIVE_API_ERRORS:
                return _emit(
                    "ERROR",
                    "{} watch failed {} times in a row; giving up. "
                    "Last error: {}".format(profile.label, consecutive_errors, exc),
                )
            time.sleep(poll_sec)
            continue
        consecutive_errors = 0

        # Only treat a closed-without-merge PR as terminal when the bot never
        # started -- if it is "working", let the review land even as the PR
        # closes. (Merged is already handled at the top of the loop.)
        if closed_state == "closed":
            return _emit("CLEAN", "PR is closed (not merged); no review pending.")

        if time.monotonic() >= deadline:
            # The TIMEOUT note describes how far the review got. For a TIMELINE
            # reviewer (Copilot) we can distinguish "started but slow" from
            # "never started" via the in-flight signal. A NON-timeline reviewer
            # (Codex) has no such signal -- `state` is always "reviewed" there,
            # which does NOT mean a verdict landed (none did, or we'd have
            # returned above), so reporting "never started" would be misleading.
            # Say "did not complete" for that case instead (fresh-eyes PR #52).
            if not profile.uses_timeline:
                note = "did not complete in the window"
            elif state == "working":
                note = "started but not finished"
            else:
                note = "never started"
            return _emit(
                "TIMEOUT",
                "Timed out after {} min; {} review {}.".format(timeout_min, profile.label, note),
            )
        time.sleep(poll_sec)


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(description="Watch a PR for a bot code-review completion.")
    parser.add_argument("pr", type=int, help="PR number")
    parser.add_argument(
        "--reviewer",
        choices=sorted(PROFILES),
        default="copilot",
        help="Which review bot to watch (default: copilot). Switch to 'codex' "
        "at the Copilot->Codex cutover (bd polyglot-pdf-hrn.9).",
    )
    parser.add_argument(
        "--repo", default=swarm_config.repo(), help="OWNER/REPO"
    )
    parser.add_argument("--timeout-min", type=int, default=20)
    parser.add_argument("--poll-sec", type=int, default=20)
    parser.add_argument(
        "--since",
        default=None,
        help="ISO8601; only count reviews/comments at or after this time "
        "(use the moment of a re-trigger to avoid re-detecting the prior round)",
    )
    args = parser.parse_args(argv)

    profile = PROFILES[args.reviewer]

    since = None
    if args.since:
        try:
            since = _parse_iso(args.since)
            if since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)
        except ValueError as exc:
            return _emit("ERROR", "Bad --since value: {}".format(exc))

    try:
        return watch(args.repo, args.pr, args.timeout_min, args.poll_sec, since, profile)
    except KeyboardInterrupt:
        return _emit("ERROR", "Interrupted.")
    except Exception as exc:  # noqa: BLE001 -- last-resort: never die silently
        return _emit("ERROR", "Unexpected crash: {!r}".format(exc))


if __name__ == "__main__":
    sys.exit(main())
