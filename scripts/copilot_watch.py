"""Watch a GitHub PR for GitHub Copilot review COMPLETION, then exit.

Background
----------
The development cycle waits on Copilot's auto-review after every PR open
(and after every "@copilot please review" re-trigger). Historically the
orchestrating agent polled `gh api .../comments` every few minutes -- each
poll a full, expensive model turn that did nothing but run one shell
command and check whether a counter moved. This script moves that wait OUT
of the model: run it via the agent harness's `run_in_background`, and the
agent is woken exactly once, when the review reaches a terminal state, with
the verdict already classified. Zero polling turns.

Why "review completion", not "a new comment"
---------------------------------------------
The COMMON case is Copilot finishing a review with NO inline comments (just
a completed review whose state is the verdict). "No comment yet" and "done,
nothing to say" look identical if you only watch the inline-comment stream,
so a naive new-comment watcher would hang forever on a clean review. This
script instead watches for the review to COMPLETE and then classifies the
terminal state.

Timeline-driven lifecycle
-------------------------
The authoritative "where is the review" signal is the issue TIMELINE
(`/issues/{n}/timeline`), NOT the reviews/comments endpoints -- those only
populate after a verdict submits, so they can't tell "not started" from "in
progress" from "finished with nothing," and they hide two terminal states
(Copilot error; finished-with-no-review). The watcher reads the timeline:

  copilot_work_started   -> in flight; keep waiting (no premature TIMEOUT)
  reviewed               -> a verdict submitted; classify it (below)
  copilot_work_finished  -> Copilot done, produced no review -> CLEAN

Once a `reviewed` event lands, the findings come from three surfaces (a
verdict can land on any; watching one misses the others):

  1. Inline review comments  -> GET /repos/{o}/{r}/pulls/{n}/comments
  2. Top-level reviews        -> GET /repos/{o}/{r}/pulls/{n}/reviews
  3. PR issue comments        -> GET /repos/{o}/{r}/issues/{n}/comments

A `reviewed` event whose body is "Copilot encountered an error..." is an
ERROR, not a finding.

Two staleness traps these surfaces hide, both handled:

  - An inline comment whose `position` is null is OUTDATED -- its anchor fell
    out of the current diff after later commits. GitHub never deletes it, and
    it re-matches its (frozen) review by id on every poll, so a resolved
    round-1 comment would loop the closeout forever. Outdated inline comments
    are dropped (a genuine new finding has a non-null position).
  - Copilot's RE-review verdict (after "@copilot please review") frequently
    lands as an ISSUE COMMENT, not a formal review -- it has no state and never
    appears in /reviews. Reading /reviews alone would re-select the frozen
    prior review (false COMMENTS) or, with a --since floor, find nothing (false
    TIMEOUT). So when no in-window review exists, we classify from the latest
    in-window Copilot issue comment: an explicit approval phrase ("no further
    changes...") -> CLEAN, otherwise COMMENTS.

Terminal states (printed as the final line: "RESULT: <STATE>")
--------------------------------------------------------------
  COMMENTS -- review complete, Copilot left findings. The findings are
              printed so the agent sees them without another API call.
  CLEAN    -- review complete, no findings (the common case). Also covers a
              PR that was closed WITHOUT being merged while nothing was pending.
  MERGED   -- the PR was merged while watching (the merge event lands in the
              same timeline this script polls). Lets the caller skip a separate
              `gh pr view` to learn the outcome: treat it as "done + already
              merged" -> skip the maintainer-merge ping, go straight to bead
              close. Exit 0, like CLEAN.
  ERROR    -- the review failed or Copilot hit a quota/availability error.
              Surfaced to the user; NO auto-retry (a quota error will not
              clear for hours, so backoff just burns wall-clock). The user
              decides whether to wait out the reset or proceed without
              Copilot.
  TIMEOUT  -- no completed review appeared within --timeout-min. Distinct
              from ERROR (exit code 2 vs 1) so a caller can retry-later on a
              timeout but investigate on a genuine failure.

Any unexpected crash is caught and reported as RESULT: ERROR with the
exception text, so the agent is woken with a real signal rather than the
script dying silently (which would look like "still waiting" forever).

Usage
-----
    python scripts/copilot_watch.py <pr-number> [--repo OWNER/REPO]
        [--timeout-min N] [--poll-sec N] [--since ISO8601]

`--since` lets the caller scope detection to reviews/comments created after
a known timestamp (e.g. the moment of a "@copilot please review"
re-trigger), so a re-review loop does not re-detect the previous round's
verdict.

Exit codes: 0 for COMMENTS/CLEAN/MERGED, 1 for ERROR, 2 for TIMEOUT. TIMEOUT and
ERROR are distinct so a shell caller can retry-later on a timeout but
investigate on a genuine error. The RESULT line is the contract; the exit
code mirrors it for shell callers.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
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

# Login substrings that identify the Copilot reviewer. Must match Copilot
# specifically and NOT the generic "github-actions[bot]" actor, which is
# shared by every Actions workflow (CI status, labelers, release bots) --
# matching it would misclassify an unrelated bot's review as a Copilot
# verdict and exit early with a bogus result. Copilot's review actor has
# consistently carried "copilot" in its login (e.g. "copilot-pull-request-
# reviewer[bot]"); match that case-insensitive substring only.
COPILOT_LOGIN_MARKERS = ("copilot",)

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
# the authoritative "where is the review" signals -- the reviews/comments
# endpoints only populate after a verdict submits, so they can't distinguish
# "not started" from "in progress" from "finished with nothing." Event names
# confirmed against live PRs 2026-05-29.
COPILOT_WORK_STARTED = "copilot_work_started"    # in flight -- keep waiting
COPILOT_WORK_FINISHED = "copilot_work_finished"  # terminal: done (may be CLEAN)
COPILOT_REVIEWED = "reviewed"                     # terminal: a verdict submitted

# When Copilot fails (e.g. quota), it posts a `reviewed` event whose BODY is
# this sentence -- NOT a real verdict. Detect it so it classifies as ERROR
# instead of being mistaken for a COMMENTS finding.
COPILOT_ERROR_BODY_PREFIX = "Copilot encountered an error"


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


def _is_copilot(login: str) -> bool:
    lo = (login or "").lower()
    return any(marker in lo for marker in COPILOT_LOGIN_MARKERS)


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


def _latest_copilot_review(repo: str, pr: int, since: datetime | None):
    """Return the most recent COMPLETED Copilot review at/after `since`, or None.

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
        if not _is_copilot(login):
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


def _timeline_state(repo: str, pr: int, since: datetime | None):
    """Read Copilot's lifecycle from the issue timeline.

    Returns one of:
      "reviewed"  -- a `reviewed` event landed (verdict; classify via reviews
                     endpoint -- could be COMMENTS / CLEAN / ERROR-body).
      "finished"  -- `copilot_work_finished` with no later `reviewed`: Copilot
                     is done and produced no review -> treat as CLEAN.
      "working"   -- `copilot_work_started` seen, no terminal event yet: keep
                     waiting (do NOT TIMEOUT prematurely; a verdict is coming).
      None        -- no Copilot activity at/after `since`: not started yet.

    Only events at/after `since` count, so a re-review round is not confused
    with the previous round's terminal events.
    """
    started = finished = reviewed = False
    for ev in _run_gh_api("repos/{}/issues/{}/timeline".format(repo, pr)) or []:
        name = ev.get("event", "")
        actor = (ev.get("actor") or ev.get("user") or {}).get("login", "")
        when = ev.get("created_at") or ev.get("submitted_at") or ""
        # review_requested carries the requester as actor (a human), so don't
        # gate the copilot_* / reviewed events on actor being Copilot for the
        # request event; but the work/review events themselves are Copilot's.
        if name == COPILOT_REVIEWED and _is_copilot(actor) and _after(when, since):
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


def _collect_findings(repo: str, pr: int, floor: datetime | None, review: dict):
    """Collect Copilot findings tied to the current review round.

    Inline comments are matched EXACTLY to this round by
    `pull_request_review_id == review['id']` -- not by timestamp. Copilot
    posts its inline comments slightly BEFORE it submits the review, so
    flooring inline comments at the review's `submitted_at` would drop
    same-round findings and misclassify as CLEAN. The review_id link is the
    authoritative round boundary for inline comments.

    Issue comments have no review_id, so they fall back to the `floor`
    timestamp (the round boundary derived from the review / caller --since),
    which keeps prior-round issue comments from leaking in. The review's own
    body is always included -- it belongs to this round by construction.
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
    if body and _has_change_ask(body) and not _is_approval_comment(body):
        findings.append("[review:{}] {}".format(review.get("state", "?"), body))

    # Surface 1: inline review comments, matched to THIS review by id.
    for c in _run_gh_api("repos/{}/pulls/{}/comments".format(repo, pr)) or []:
        login = (c.get("user") or {}).get("login", "")
        if _is_copilot(login) and c.get("pull_request_review_id") == review_id:
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
            _is_copilot(login)
            and _after(created, floor)
            and not _is_approval_comment(body)
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
    stripped = (body or "").strip().strip("`*_>#\"' \t\r\n.").strip()
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


def _is_approval_shaped(body: str) -> bool:
    """True if the body is short + single-paragraph + has no list/numbered items."""
    b = (body or "").strip()
    if len(b) > _APPROVAL_SHAPE_MAX_CHARS:
        return False
    if "\n\n" in b:  # more than one paragraph
        return False
    for line in b.splitlines():
        ls = line.lstrip()
        if ls.startswith(("- ", "* ", "+ ")) or (ls[:2].isdigit() and "." in ls[:4]):
            return False  # bullet or numbered list -> structured findings
        if ls[:2] in ("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9."):
            return False
    return True


def _is_approval_comment(body: str) -> bool:
    # Fast path: the exact canonical signal is always an approval, no heuristics.
    if _is_exact_lgtm(body):
        return True
    lo = (body or "").lower()
    if not any(p in lo for p in _APPROVAL_PATTERNS):
        return False
    # An approval phrase is present, but it only counts if the comment is also
    # approval-SHAPED (short/flat) AND does not ALSO ask for a change. A long or
    # multi-paragraph comment that merely starts with an approval phrase stays
    # COMMENTS -- the findings-based path below is the real backstop. (bd ztk)
    if not _is_approval_shaped(body):
        return False
    return not _has_change_ask(body)


def _latest_by_created(comments: list) -> dict | None:
    """Return the comment with the max `created_at` (ISO8601 sorts lexically).

    Don't rely on API list ordering -- pick the semantically latest explicitly.
    """
    if not comments:
        return None
    return max(comments, key=lambda c: c.get("created_at", ""))


def _new_inline_findings(repo: str, pr: int, since: datetime | None) -> list:
    """Actionable Copilot inline comments for THIS round (the deterministic core).

    An actionable finding is an inline review comment that (a) is Copilot's,
    (b) lands on the CURRENT diff (non-null `position` -- a null position is an
    outdated prior-round anchor, never a live ask), and (c) was created at/after
    `since` (the round floor). This is the fact the whole classifier rests on:
    a real "please change X" from Copilot is an inline comment on the diff. Its
    presence/absence does NOT depend on what words Copilot puts in its summary,
    so it can't be defeated by novel approval phrasing.
    """
    findings = []
    for c in _run_gh_api("repos/{}/pulls/{}/comments".format(repo, pr)) or []:
        login = (c.get("user") or {}).get("login", "")
        if not _is_copilot(login):
            continue
        if "position" in c and c["position"] is None:
            continue  # outdated anchor -- not a live finding
        if not _after(c.get("created_at", ""), since):
            continue  # prior round
        loc = c.get("path", "?")
        line = c.get("line") or c.get("original_line") or "?"
        findings.append("[inline {}:{}] {}".format(loc, line, (c.get("body") or "").strip()))
    return findings


def _classify_issue_comment_round(repo: str, pr: int, since: datetime | None):
    """Classify a round whose verdict arrives as a Copilot ISSUE COMMENT (no review).

    FINDINGS-BASED (default-clean-unless-flagged). Approval is the ABSENCE of an
    actionable finding, not the presence of a recognized approval phrase -- so
    Copilot inventing a new "looks fine" wording can no longer cause a false
    COMMENTS or a TIMEOUT. The order of checks, strongest signal first:

      1. ERROR body            -> ERROR (Copilot failed; not a verdict).
      2. exact `LGTM` / known approval phrase, no change-ask -> CLEAN (fast path).
      3. comment asks for a change (_CHANGE_ASK_SIGNALS) -> COMMENTS (a prose-only
         ask: "please fix X" with no inline anchor still gets caught).
      4. a NEW actionable inline finding exists this round -> COMMENTS (the prose
         is just a summary; the inline comment governs).
      5. otherwise -> CLEAN (Copilot commented, asked for nothing, left no inline
         finding -- that IS an approval, whatever words it chose).

    Returns an exit code, or None if no Copilot issue comment at/after `since`
    exists yet (caller keeps polling -- the surface may just be lagging).
    Residual risk accepted: a substantive ask delivered ONLY as summary prose with
    none of the change-ask signal words AND no inline comment would read CLEAN; in
    practice Copilot's actionable findings are inline, and the human merge is the
    final gate.
    """
    copilot_comments = [
        c
        for c in (_run_gh_api("repos/{}/issues/{}/comments".format(repo, pr)) or [])
        if _is_copilot((c.get("user") or {}).get("login", ""))
        and _after(c.get("created_at", ""), since)
    ]
    latest = _latest_by_created(copilot_comments)
    if latest is None:
        return None
    body = (latest.get("body") or "").strip()

    # 1. Copilot-failed sentinel.
    if body.startswith(COPILOT_ERROR_BODY_PREFIX):
        return _emit("ERROR", "Copilot could not review this PR: {}".format(body))

    # 2. Explicit approval (exact LGTM or a known phrase with no change-ask).
    if _is_approval_comment(body):
        return _emit(
            "CLEAN",
            "Copilot approved via issue comment (no findings):\n\n{}".format(body),
        )

    # 3. Prose that asks for a change stays COMMENTS even with no inline anchor.
    if _has_change_ask(body):
        return _emit(
            "COMMENTS",
            "Copilot's comment asks for a change:\n\n{}".format(body),
        )

    # 4. No change-ask prose -- defer to the deterministic inline-finding check.
    inline = _new_inline_findings(repo, pr, since)
    if inline:
        return _emit(
            "COMMENTS",
            "Copilot left {} inline finding(s) this round:\n\n{}".format(
                len(inline), "\n\n".join(inline)
            ),
        )

    # 5. Commented, asked for nothing, no inline finding -> approval by absence.
    return _emit(
        "CLEAN",
        "Copilot commented with no actionable finding (no change-ask, no inline "
        "comment this round) -> treating as approval:\n\n{}".format(body),
    )


def _classify_reviewed(repo: str, pr: int, since: datetime | None) -> int:
    """A `reviewed` event landed; fetch the review and emit the verdict.

    Handles three sub-cases:
      - ERROR-body ("Copilot encountered an error...") -> ERROR, not a finding.
      - findings present OR a non-clean state (CHANGES_REQUESTED) -> COMMENTS.
      - otherwise -> CLEAN.
    If the findings fetch fails after we know a verdict exists, we still emit
    the verdict from the review body / state rather than discarding it.
    """
    review = _latest_copilot_review(repo, pr, since)
    if review is None:
        # No in-window formal REVIEW. Either (1) Copilot delivered this round's
        # verdict as an ISSUE COMMENT (re-reviews often do -- no state, no
        # review_id, absent from /reviews), or (2) the reviews endpoint just
        # hasn't caught up yet. Try the issue-comment surface; if nothing there
        # either, signal the caller to keep polling.
        rc = _classify_issue_comment_round(repo, pr, since)
        if rc is not None:
            return rc
        return None

    body = (review.get("body") or "").strip()
    state = review.get("state", "")

    if body.startswith(COPILOT_ERROR_BODY_PREFIX):
        return _emit("ERROR", "Copilot could not review this PR: {}".format(body))

    floor = since
    submitted = review.get("submitted_at") or review.get("created_at") or ""
    try:
        review_ts = _parse_iso(submitted)
        if floor is None or review_ts > floor:
            floor = review_ts
    except (ValueError, AttributeError):
        pass

    try:
        findings = _collect_findings(repo, pr, floor, review)
    except RuntimeError as exc:
        # Verdict already known -- do not throw it away on a secondary fetch
        # failure. A non-clean state or a non-empty body is still COMMENTS.
        if state in NON_CLEAN_STATES or body:
            return _emit(
                "COMMENTS",
                "Copilot review complete (state={}, could not fetch inline "
                "comments: {}). Body:\n\n{}".format(state, exc, body or "(none)"),
            )
        return _emit(
            "CLEAN",
            "Copilot review complete, no review-body findings "
            "(could not fetch inline comments: {}).".format(exc),
        )

    # A CHANGES_REQUESTED state is a verdict even with no findings text.
    if findings or state in NON_CLEAN_STATES:
        detail = "Copilot left {} finding(s):\n\n{}".format(
            len(findings), "\n\n".join(findings)
        ) if findings else "Copilot review state={} with no inline findings.".format(state)
        return _emit("COMMENTS", detail)
    return _emit("CLEAN", "Copilot review complete with no findings.")


def watch(repo: str, pr: int, timeout_min: int, poll_sec: int, since: datetime | None) -> int:
    """Poll the timeline until Copilot reaches a terminal state, then classify.

    Timeline-driven: `copilot_work_started` means "keep waiting" (a verdict is
    coming, so we never TIMEOUT while Copilot is provably mid-review);
    `reviewed` means classify the verdict; `copilot_work_finished` with no
    review means Copilot finished and produced nothing (CLEAN).
    """
    deadline = time.monotonic() + timeout_min * 60
    consecutive_errors = 0
    while True:
        try:
            # A merge is the most decisive terminal state -- once the PR is
            # merged the review verdict is moot, and the merge event lands in
            # the same timeline. Check it FIRST so the caller learns "merged"
            # without a separate `gh pr view`, regardless of Copilot's status.
            # (One fetch per poll; reused for the closed-without-merge case below.)
            closed_state = _pr_closed_state(repo, pr)
            if closed_state == "merged":
                return _emit("MERGED", "PR was merged; no Copilot review pending.")

            state = _timeline_state(repo, pr, since)
            if state == "reviewed":
                rc = _classify_reviewed(repo, pr, since)
                if rc is not None:
                    return rc
                # reviews endpoint not yet consistent -- fall through to wait.
            elif state == "finished":
                # Finished with no in-window formal review -- but Copilot may
                # have delivered its verdict as an ISSUE COMMENT (the common
                # shape for a re-review). Classify that before concluding
                # "nothing to say."
                rc = _classify_issue_comment_round(repo, pr, since)
                if rc is not None:
                    return rc
                return _emit(
                    "CLEAN", "Copilot finished work and produced no review."
                )
            # state == "working" or None -> keep polling (below). closed_state
            # (fetched above) carries the closed-without-merge case; only act on
            # it when Copilot never produced a verdict (state is None).
            if state is not None:
                closed_state = None
        except RuntimeError as exc:
            # Transient (network blip, token refresh, 5xx, gh hang/missing).
            # Retry within the poll loop; give up only after several in a row.
            consecutive_errors += 1
            if consecutive_errors >= MAX_CONSECUTIVE_API_ERRORS:
                return _emit(
                    "ERROR",
                    "Copilot watch failed {} times in a row; giving up. "
                    "Last error: {}".format(consecutive_errors, exc),
                )
            time.sleep(poll_sec)
            continue
        consecutive_errors = 0

        # Only treat a closed-without-merge PR as terminal when Copilot never
        # started -- if it is "working", let the review land even as the PR
        # closes. (Merged is already handled at the top of the loop.)
        if closed_state == "closed":
            return _emit("CLEAN", "PR is closed (not merged); no Copilot review pending.")

        if time.monotonic() >= deadline:
            # "working" past the deadline is still a TIMEOUT, but the message
            # distinguishes "never started" from "started but slow".
            note = "started but not finished" if state == "working" else "never started"
            return _emit(
                "TIMEOUT",
                "Timed out after {} min; Copilot review {}.".format(timeout_min, note),
            )
        time.sleep(poll_sec)


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(description="Watch a PR for Copilot review completion.")
    parser.add_argument("pr", type=int, help="PR number")
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

    since = None
    if args.since:
        try:
            since = _parse_iso(args.since)
            if since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)
        except ValueError as exc:
            return _emit("ERROR", "Bad --since value: {}".format(exc))

    try:
        return watch(args.repo, args.pr, args.timeout_min, args.poll_sec, since)
    except KeyboardInterrupt:
        return _emit("ERROR", "Interrupted.")
    except Exception as exc:  # noqa: BLE001 -- last-resort: never die silently
        return _emit("ERROR", "Unexpected crash: {!r}".format(exc))


if __name__ == "__main__":
    sys.exit(main())
