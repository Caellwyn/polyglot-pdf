"""Tests for scripts/bd_safe.py.

Imports the script as a module (repo precedent: test_pr_review_watcher.py,
test_doc_freshness.py) and exercises the wrapper logic with `_run`
monkeypatched so no `bd`/`gh`/`git` subprocess is ever spawned. The point of
the tests is the SAFETY behaviors: pull-then-push bracketing fires, the two
collision checks gate a claim, and the dep-add direction cannot be inverted.
"""

import importlib.util
import pathlib
import subprocess
import sys
import types

import pytest


SCRIPT_PATH = (
    pathlib.Path(__file__).resolve().parent.parent / "scripts" / "bd_safe.py"
)
spec = importlib.util.spec_from_file_location("bd_safe", SCRIPT_PATH)
bs = importlib.util.module_from_spec(spec)
sys.modules["bd_safe"] = bs
spec.loader.exec_module(bs)


def _proc(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


class _RunRecorder:
    """Routes bd_safe._run calls to canned results and records the commands."""

    def __init__(self, responses):
        # responses: list of (predicate, CompletedProcess). First match wins.
        self.responses = responses
        self.calls = []

    def __call__(self, cmd, *, check=True):
        self.calls.append(list(cmd))
        for pred, result in self.responses:
            if pred(cmd):
                if check and result.returncode != 0:
                    raise RuntimeError("command failed: {}".format(" ".join(cmd)))
                return result
        return _proc()  # default: success, empty output

    def ran(self, *tokens):
        """True if some recorded call contains ALL the given tokens in order-agnostic membership."""
        return any(all(t in call for t in tokens) for call in self.calls)


# --- id-suffix derivation (collision branch-grep token) ---

@pytest.mark.parametrize(
    "bead_id,expected",
    [
        ("yourturn-group-nbj1", "nbj1"),
        ("yourturn-group-24j.2", "24j2"),   # punctuation dropped to match branch name
        ("yourturn-group-3go1", "3go1"),
    ],
)
def test_id_suffix(bead_id, expected):
    assert bs._id_suffix(bead_id) == expected


# --- claim: collision checks gate the claim ---

def test_claim_aborts_on_pr_collision(monkeypatch, capsys):
    # An OPEN PR whose TITLE carries the bead id is a real live claim -> abort.
    recorder = _RunRecorder([
        (lambda c: c[:3] == ["gh", "pr", "list"],
         _proc(stdout='[{"number": 42, "title": "feat: thing (bd yourturn-group-nbj1)"}]')),
    ])
    monkeypatch.setattr(bs, "_run", recorder)
    args = types.SimpleNamespace(id="yourturn-group-nbj1", repo=bs.DEFAULT_REPO)
    rc = bs.cmd_claim(args)
    assert rc == bs.EXIT_ABORT_COLLISION
    assert "ABORT" in capsys.readouterr().out
    # Must NOT have claimed.
    assert not recorder.ran("update", "--claim")
    # The collision query must be scoped to OPEN PRs (not --state all), so a
    # merged PR can't block the bead forever (bd polyglot-pdf-9pe).
    assert recorder.ran("gh", "pr", "list", "--state", "open")
    assert not recorder.ran("--state", "all")


def test_claim_ignores_pr_that_only_mentions_bead_in_body(monkeypatch):
    # The false positive that motivated 9pe: a (merged or open) PR that only
    # MENTIONS the bead in its body -- e.g. as a deferred finding -- must NOT
    # block the claim. We search open PRs, but the authoritative filter is the
    # TITLE; a body-only mention won't appear in --json title, so even if the
    # server-side --search surfaces the PR, the title filter drops it.
    recorder = _RunRecorder([
        # gh's --search matched on body text, but the title has no bead id.
        (lambda c: c[:3] == ["gh", "pr", "list"],
         _proc(stdout='[{"number": 46, "title": "docs: unrelated title, no bead id here"}]')),
        (lambda c: c[:4] == ["git", "rev-parse", "--abbrev-ref", "HEAD"],
         _proc(stdout="dev")),
        (lambda c: c[:3] == ["git", "branch", "-a"], _proc(stdout="* dev")),
    ])
    monkeypatch.setattr(bs, "_run", recorder)
    args = types.SimpleNamespace(id="yourturn-group-nbj1", repo=bs.DEFAULT_REPO)
    rc = bs.cmd_claim(args)
    assert rc == bs.EXIT_OK
    assert recorder.ran("update", "--claim")  # the claim proceeded


def test_pr_collision_returns_none_on_empty_json(monkeypatch):
    # gh pr list --json emits "[]" (not empty string) when nothing matches.
    recorder = _RunRecorder([
        (lambda c: c[:3] == ["gh", "pr", "list"], _proc(stdout="[]")),
    ])
    monkeypatch.setattr(bs, "_run", recorder)
    assert bs._pr_collision("yourturn-group-nbj1", bs.DEFAULT_REPO) is None


def test_pr_collision_does_not_match_longer_id_prefix(monkeypatch):
    # A shorter id must not collide with a PR for a LONGER id that has it as a
    # prefix: claiming `...-ab1` must not be blocked by a PR titled `(bd ...-ab12)`
    # (fresh-eyes finding on PR #47). The title boundary check enforces this.
    recorder = _RunRecorder([
        (lambda c: c[:3] == ["gh", "pr", "list"],
         _proc(stdout='[{"number": 7, "title": "feat: x (bd yourturn-group-ab12)"}]')),
    ])
    monkeypatch.setattr(bs, "_run", recorder)
    assert bs._pr_collision("yourturn-group-ab1", bs.DEFAULT_REPO) is None
    # ...but the exact id still collides.
    assert bs._pr_collision("yourturn-group-ab12", bs.DEFAULT_REPO) is not None


def test_pr_collision_search_term_is_quoted(monkeypatch):
    # The --search term must be quoted so GitHub treats the hyphenated id as one
    # phrase instead of OR-ing its hyphen-split tokens (fresh-eyes finding #47).
    recorder = _RunRecorder([
        (lambda c: c[:3] == ["gh", "pr", "list"], _proc(stdout="[]")),
    ])
    monkeypatch.setattr(bs, "_run", recorder)
    bs._pr_collision("yourturn-group-nbj1", bs.DEFAULT_REPO)
    assert recorder.ran("--search", '"yourturn-group-nbj1"')


def test_claim_aborts_on_branch_collision(monkeypatch, capsys):
    # A FOREIGN worker's branch carries the suffix while I'm on a DIFFERENT
    # branch -- the exclusion must NOT suppress it, so the claim still aborts.
    recorder = _RunRecorder([
        (lambda c: c[:3] == ["gh", "pr", "list"], _proc(stdout="[]")),  # no PR
        (lambda c: c[:4] == ["git", "rev-parse", "--abbrev-ref", "HEAD"],
         _proc(stdout="dev")),  # I'm on dev, not the colliding branch
        (lambda c: c[:3] == ["git", "branch", "-a"],
         _proc(stdout="  remotes/origin/feature/nbj1-swarm-scripts")),
    ])
    monkeypatch.setattr(bs, "_run", recorder)
    args = types.SimpleNamespace(id="yourturn-group-nbj1", repo=bs.DEFAULT_REPO)
    rc = bs.cmd_claim(args)
    assert rc == bs.EXIT_ABORT_COLLISION
    assert not recorder.ran("update", "--claim")


def test_claim_brackets_with_pull_and_push(monkeypatch):
    recorder = _RunRecorder([
        (lambda c: c[:3] == ["gh", "pr", "list"], _proc(stdout="[]")),       # no PR
        (lambda c: c[:3] == ["git", "branch", "-a"], _proc(stdout="* dev")),  # no match
    ])
    monkeypatch.setattr(bs, "_run", recorder)
    args = types.SimpleNamespace(id="yourturn-group-nbj1", repo=bs.DEFAULT_REPO)
    rc = bs.cmd_claim(args)
    assert rc == bs.EXIT_OK
    assert recorder.ran("dolt", "pull")
    assert recorder.ran("update", "--claim")
    assert recorder.ran("dolt", "push")
    # pull must precede claim, claim must precede push.
    flat = ["|".join(c) for c in recorder.calls]
    pull_i = next(i for i, c in enumerate(flat) if "pull" in c)
    claim_i = next(i for i, c in enumerate(flat) if "--claim" in c)
    push_i = next(i for i, c in enumerate(flat) if "push" in c)
    assert pull_i < claim_i < push_i


# --- close: pull/push bracketing ---

def test_close_brackets_and_passes_reason(monkeypatch):
    recorder = _RunRecorder([])
    monkeypatch.setattr(bs, "_run", recorder)
    args = types.SimpleNamespace(id="yourturn-group-nbj1", reason="done in PR #X")
    rc = bs.cmd_close(args)
    assert rc == bs.EXIT_OK
    assert recorder.ran("dolt", "pull")
    assert recorder.ran("close", "--reason", "done in PR #X")
    assert recorder.ran("dolt", "push")


# --- dep-add: direction cannot be inverted ---

def test_dep_add_epic_child_blocks_the_epic(monkeypatch):
    # scar rule 13: epic is BLOCKED BY child -> `bd dep add <epic> <child>`.
    recorder = _RunRecorder([])
    monkeypatch.setattr(bs, "_run", recorder)
    args = types.SimpleNamespace(
        epic="yourturn-group-32qp", child="yourturn-group-nbj1",
        blocked=None, prereq=None,
    )
    rc = bs.cmd_dep_add(args)
    assert rc == bs.EXIT_OK
    # First arg to `bd dep add` is the epic (blocked); second is the child.
    dep_call = next(c for c in recorder.calls if "dep" in c and "add" in c)
    assert dep_call == ["bd", "dep", "add", "yourturn-group-32qp", "yourturn-group-nbj1"]


def test_dep_add_blocked_prereq_general_form(monkeypatch):
    recorder = _RunRecorder([])
    monkeypatch.setattr(bs, "_run", recorder)
    args = types.SimpleNamespace(
        epic=None, child=None,
        blocked="yourturn-group-dw03", prereq="yourturn-group-nbj1",
    )
    rc = bs.cmd_dep_add(args)
    assert rc == bs.EXIT_OK
    dep_call = next(c for c in recorder.calls if "dep" in c and "add" in c)
    assert dep_call == ["bd", "dep", "add", "yourturn-group-dw03", "yourturn-group-nbj1"]


def test_dep_add_rejects_mixed_or_incomplete_flags(monkeypatch, capsys):
    monkeypatch.setattr(bs, "_run", _RunRecorder([]))
    # epic without child
    args = types.SimpleNamespace(epic="x", child=None, blocked=None, prereq=None)
    assert bs.cmd_dep_add(args) == bs.EXIT_FAIL
    # child without epic (the symmetric case)
    args_c = types.SimpleNamespace(epic=None, child="x", blocked=None, prereq=None)
    assert bs.cmd_dep_add(args_c) == bs.EXIT_FAIL
    # blocked without prereq
    args_b = types.SimpleNamespace(epic=None, child=None, blocked="x", prereq=None)
    assert bs.cmd_dep_add(args_b) == bs.EXIT_FAIL
    # neither pair
    args2 = types.SimpleNamespace(epic=None, child=None, blocked=None, prereq=None)
    assert bs.cmd_dep_add(args2) == bs.EXIT_FAIL


def test_dep_add_rejects_both_pairs_given(monkeypatch):
    # Supplying all four flags is ambiguous -- must reject, not silently
    # prefer epic/child and drop blocked/prereq.
    rec = _RunRecorder([])
    monkeypatch.setattr(bs, "_run", rec)
    args = types.SimpleNamespace(epic="e", child="c", blocked="b", prereq="p")
    assert bs.cmd_dep_add(args) == bs.EXIT_FAIL
    assert not rec.ran("dep", "add")  # nothing was written


# --- branch collision is token-boundaried, not a bare substring ---

def test_branch_collision_no_false_positive_on_substring(monkeypatch):
    # Short suffix "c1" must NOT match "calendar-ical-c1x" or "abc1def".
    rec = _RunRecorder([
        (lambda c: c[:3] == ["git", "branch", "-a"],
         _proc(stdout="  remotes/origin/feature/calendar-ical-fix\n  abc1def-branch")),
    ])
    monkeypatch.setattr(bs, "_run", rec)
    assert bs._branch_collision("yourturn-group-c1") is None


def test_branch_collision_matches_real_branch(monkeypatch):
    rec = _RunRecorder([
        (lambda c: c[:3] == ["git", "branch", "-a"],
         _proc(stdout="* feature/nbj1-swarm-scripts\n  dev")),
    ])
    monkeypatch.setattr(bs, "_run", rec)
    hit = bs._branch_collision("yourturn-group-nbj1")
    assert hit is not None and "nbj1-swarm-scripts" in hit


# --- self-collision: the worktree's OWN current branch must not abort ---

def test_branch_collision_excludes_own_current_branch(monkeypatch):
    # The bead's feature branch is already checked out in this worktree
    # (* marker) plus its remote tracking ref. Neither is a foreign worker.
    rec = _RunRecorder([
        (lambda c: c[:3] == ["git", "branch", "-a"],
         _proc(stdout="* feature/dw03-closeout-skill\n"
                      "  remotes/origin/feature/dw03-closeout-skill\n"
                      "  dev")),
    ])
    monkeypatch.setattr(bs, "_run", rec)
    hit = bs._branch_collision(
        "yourturn-group-dw03", current_branch="feature/dw03-closeout-skill"
    )
    assert hit is None


def test_branch_collision_still_flags_foreign_branch_with_same_suffix(monkeypatch):
    # A DIFFERENT branch carrying the same suffix (another worker's) must
    # still trip even when my current branch also carries it.
    rec = _RunRecorder([
        (lambda c: c[:3] == ["git", "branch", "-a"],
         _proc(stdout="* feature/dw03-closeout-skill\n"
                      "  remotes/origin/fix/dw03-other-worker\n")),
    ])
    monkeypatch.setattr(bs, "_run", rec)
    hit = bs._branch_collision(
        "yourturn-group-dw03", current_branch="feature/dw03-closeout-skill"
    )
    assert hit is not None and "other-worker" in hit


@pytest.mark.parametrize(
    "line,current,expected",
    [
        ("* feature/dw03-x", "feature/dw03-x", True),            # current in this worktree
        ("  remotes/origin/feature/dw03-x", "feature/dw03-x", True),  # its tracking ref
        ("  fix/dw03-other", "feature/dw03-x", False),          # different local branch
        # A "+" line is a branch current in ANOTHER worktree. By git's
        # semantics it can never name THIS worktree's current branch, so the
        # realistic "+" case is a DIFFERENT branch -> not excluded (a foreign
        # worktree's branch is a real collision and must still trip).
        ("+ feature/dw03-elsewhere", "feature/dw03-x", False),
        ("* feature/dw03-x", None, False),                      # detached / no current
    ],
)
def test_is_own_current_branch(line, current, expected):
    assert bs._is_own_current_branch(line, current) is expected


def test_claim_succeeds_when_only_own_branch_present(monkeypatch):
    # The end-to-end fix: claim run from inside the bead's own worktree
    # branch must NOT self-abort -- it should claim.
    rec = _RunRecorder([
        (lambda c: c[:3] == ["gh", "pr", "list"], _proc(stdout="[]")),  # no PR
        (lambda c: c[:4] == ["git", "rev-parse", "--abbrev-ref", "HEAD"],
         _proc(stdout="feature/dw03-closeout-skill")),
        (lambda c: c[:3] == ["git", "branch", "-a"],
         _proc(stdout="* feature/dw03-closeout-skill\n  dev")),
    ])
    monkeypatch.setattr(bs, "_run", rec)
    args = types.SimpleNamespace(id="yourturn-group-dw03", repo=bs.DEFAULT_REPO)
    rc = bs.cmd_claim(args)
    assert rc == bs.EXIT_OK
    assert rec.ran("update", "--claim")


# --- collision check surfaces a tooling failure rather than passing silently ---

def test_pr_collision_check_failure_raises(monkeypatch):
    recorder = _RunRecorder([
        (lambda c: c[:3] == ["gh", "pr", "list"], _proc(returncode=1, stderr="auth")),
    ])
    monkeypatch.setattr(bs, "_run", recorder)
    with pytest.raises(RuntimeError):
        bs._pr_collision("yourturn-group-nbj1", bs.DEFAULT_REPO)
