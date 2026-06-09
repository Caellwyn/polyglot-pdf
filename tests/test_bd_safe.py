"""Tests for scripts/bd_safe.py.

Imports the script as a module (repo precedent: test_pr_review_watcher.py,
test_doc_freshness.py) and exercises the wrapper logic with `_run`
monkeypatched so no `bd`/`gh`/`git` subprocess is ever spawned. The point of
the tests is the SAFETY behaviors: pull-then-push bracketing fires, the two
collision checks gate a claim, and the dep-add direction cannot be inverted.
"""

import importlib.util
import json
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


# --- change-surface overlap (R1 collision guard, bd polyglot-pdf-h2r.1) ---

@pytest.mark.parametrize(
    "a,b,expected",
    [
        ("scripts/foo.py", "scripts/foo.py", True),       # identical file
        ("scripts/foo.py", "scripts/bar.py", False),      # sibling files
        ("scripts/", "scripts/foo.py", True),             # dir prefix contains file
        ("scripts/foo.py", "scripts/", True),             # symmetric
        ("scripts/", "scripts-extra/foo.py", False),      # sibling DIR, not nested
        (".claude/skills/", ".claude/skills/closeout/SKILL.md", True),
        ("./scripts/foo.py", "scripts/foo.py", True),     # leading ./ normalized
        ("scripts\\foo.py", "scripts/foo.py", True),      # backslash normalized
        ("scripts/", "scripts", True),                    # dir prefix vs bare dir name
        ("scripts", "scripts/foo.py", False),             # bare 'scripts' is a FILE, no nesting
        ("", "scripts/foo.py", False),                    # empty never overlaps (per-surface)
        ("./", "scripts/foo.py", True),                   # "./" = repo root -> overlaps all (#1)
        ("/", "anything/at/all.py", True),                # root prefix overlaps all (#1)
        (".//", "docs/x.md", True),                       # multi "./" collapses to root (#1)
    ],
)
def test_one_surface_overlaps(a, b, expected):
    assert bs._one_surface_overlaps(a, b) is expected


def test_normalize_surface_root_forms():
    # A non-empty input that collapses to nothing is the repo root "/", NOT ""
    # (empty would falsely overlap nothing). A genuinely empty input stays "".
    assert bs._normalize_surface("./") == "/"
    assert bs._normalize_surface("/") == "/"
    assert bs._normalize_surface(".//") == "/"
    assert bs._normalize_surface("") == ""
    assert bs._normalize_surface("   ") == ""


def test_root_surface_does_not_silently_opt_out_of_guard():
    # The #1 false-negative: a bead declaring "./" must still collide.
    assert bs._surfaces_overlap(["./"], ["scripts/foo.py"]) is True
    assert bs._surfaces_overlap(["scripts/foo.py"], ["/"]) is True


def test_surfaces_overlap_unknown_policy():
    # Either side empty (UNKNOWN) -> conservative overlap.
    assert bs._surfaces_overlap([], ["scripts/x.py"]) is True
    assert bs._surfaces_overlap(["scripts/x.py"], []) is True
    assert bs._surfaces_overlap([], []) is True
    # Both declared + disjoint -> no overlap.
    assert bs._surfaces_overlap(["docs/a.md"], ["scripts/b.py"]) is False
    # Both declared + intersecting -> overlap.
    assert bs._surfaces_overlap(["scripts/"], ["docs/x", "scripts/y.py"]) is True


def _bead_show_json(surfaces):
    # Shape of `bd show <id> --json` (a list whose [0] is the bead).
    return json.dumps([{"id": "x", "metadata": {"surfaces": surfaces}}])


def test_bead_surfaces_parses_metadata(monkeypatch):
    rec = _RunRecorder([
        (lambda c: c[:3] == ["bd", "show", "proj-aaa1"],
         _proc(stdout=_bead_show_json(["scripts/", "docs/x.md"]))),
    ])
    monkeypatch.setattr(bs, "_run", rec)
    assert bs._bead_surfaces("proj-aaa1") == ["scripts/", "docs/x.md"]


def test_bead_surfaces_missing_metadata_returns_empty(monkeypatch):
    # Empty metadata + no open PR (the _RunRecorder default makes `gh pr list`
    # return empty) -> [] (UNKNOWN). derive_from_prs=False keeps it a pure read of
    # the declaration with NO gh call, which is what this test pins.
    rec = _RunRecorder([
        (lambda c: c[:3] == ["bd", "show", "proj-aaa1"],
         _proc(stdout=json.dumps([{"id": "x", "metadata": {}}]))),
    ])
    monkeypatch.setattr(bs, "_run", rec)
    assert bs._bead_surfaces("proj-aaa1", derive_from_prs=False) == []
    assert not rec.ran("gh", "pr", "list")


def test_bead_surfaces_filters_non_string_junk(monkeypatch):
    # A malformed surfaces list (null/number/nested) must not crash the overlap
    # math later -- non-strings are dropped, strings kept (#2).
    rec = _RunRecorder([
        (lambda c: c[:3] == ["bd", "show", "proj-aaa1"],
         _proc(stdout=json.dumps(
             [{"id": "x", "metadata": {"surfaces": ["scripts/", None, 7, ["nested"], "docs/x.md"]}}]))),
    ])
    monkeypatch.setattr(bs, "_run", rec)
    assert bs._bead_surfaces("proj-aaa1") == ["scripts/", "docs/x.md"]
    # And the kept surfaces still drive overlap without raising.
    assert bs._surfaces_overlap(
        bs._bead_surfaces("proj-aaa1"), ["scripts/foo.py"]
    ) is True


# --- PR-derived surfaces for undeclared claims (bd polyglot-pdf-8y7) ---

def test_bead_surfaces_declared_wins_without_pr_lookup(monkeypatch):
    # Declared surfaces are authoritative: no gh call is made when they exist.
    rec = _RunRecorder([
        (lambda c: c[:3] == ["bd", "show", "proj-aaa1"],
         _proc(stdout=_bead_show_json(["scripts/x.py"]))),
    ])
    monkeypatch.setattr(bs, "_run", rec)
    assert bs._bead_surfaces("proj-aaa1") == ["scripts/x.py"]
    assert not rec.ran("gh", "pr", "list")  # never reached PR derivation


def test_bead_surfaces_no_derive_flag_skips_gh(monkeypatch):
    # derive_from_prs=False reads only the declaration and never calls gh, even
    # when the bead declared nothing (the next_bead candidate path).
    rec = _RunRecorder([
        (lambda c: c[:3] == ["bd", "show", "proj-aaa1"],
         _proc(stdout=json.dumps([{"id": "x", "metadata": {}}]))),
    ])
    monkeypatch.setattr(bs, "_run", rec)
    assert bs._bead_surfaces("proj-aaa1", derive_from_prs=False) == []
    assert not rec.ran("gh", "pr", "list")


def test_bead_surfaces_derives_from_open_pr_when_undeclared(monkeypatch):
    # No declared surfaces + an open PR whose title carries the id -> the bead's
    # surfaces are that PR's changed files (the board-lock fix).
    def fake(cmd, *, check=True):
        if cmd[:3] == ["bd", "show", "proj-aaa1"]:
            return _proc(stdout=json.dumps([{"id": "x", "metadata": {}}]))
        if cmd[:3] == ["gh", "pr", "list"]:
            return _proc(stdout='[{"number": 7, "title": "feat (bd proj-aaa1)"}]')
        if cmd[:3] == ["gh", "pr", "view"] and "7" in cmd:
            return _proc(stdout=json.dumps(
                {"files": [{"path": "frontend/src/x.ts"},
                           {"path": "docs/y.md"}]}))
        return _proc()
    monkeypatch.setattr(bs, "_run", fake)
    assert bs._bead_surfaces("proj-aaa1") == ["frontend/src/x.ts", "docs/y.md"]


def test_bead_surfaces_undeclared_no_pr_is_unknown(monkeypatch):
    # No declaration AND no open PR -> [] (genuinely UNKNOWN; the conservative
    # collide-with-everything policy still applies downstream).
    def fake(cmd, *, check=True):
        if cmd[:3] == ["bd", "show", "proj-aaa1"]:
            return _proc(stdout=json.dumps([{"id": "x", "metadata": {}}]))
        if cmd[:3] == ["gh", "pr", "list"]:
            return _proc(stdout="[]")
        return _proc()
    monkeypatch.setattr(bs, "_run", fake)
    assert bs._bead_surfaces("proj-aaa1") == []


def test_bead_surfaces_pr_view_failure_falls_back_to_unknown(monkeypatch):
    # The PR exists but `gh pr view` fails -> we cannot derive, so [] (UNKNOWN),
    # never a crash. The conservative policy then blocks, which is the safe side.
    def fake(cmd, *, check=True):
        if cmd[:3] == ["bd", "show", "proj-aaa1"]:
            return _proc(stdout=json.dumps([{"id": "x", "metadata": {}}]))
        if cmd[:3] == ["gh", "pr", "list"]:
            return _proc(stdout='[{"number": 7, "title": "feat (bd proj-aaa1)"}]')
        if cmd[:3] == ["gh", "pr", "view"] and "7" in cmd:
            return _proc(returncode=1, stderr="boom")
        return _proc()
    monkeypatch.setattr(bs, "_run", fake)
    assert bs._bead_surfaces("proj-aaa1") == []


def test_bead_surfaces_pr_derivation_dedups_across_prs(monkeypatch):
    # Two open PRs carry the id; the union of their files is returned once each,
    # in first-seen order.
    def fake(cmd, *, check=True):
        if cmd[:3] == ["bd", "show", "proj-aaa1"]:
            return _proc(stdout=json.dumps([{"id": "x", "metadata": {}}]))
        if cmd[:3] == ["gh", "pr", "list"]:
            return _proc(stdout=json.dumps([
                {"number": 7, "title": "a (bd proj-aaa1)"},
                {"number": 8, "title": "b (bd proj-aaa1)"},
            ]))
        if cmd[:3] == ["gh", "pr", "view"] and "7" in cmd:
            return _proc(stdout=json.dumps({"files": [{"path": "a.py"},
                                                      {"path": "shared.py"}]}))
        if cmd[:3] == ["gh", "pr", "view"] and "8" in cmd:
            return _proc(stdout=json.dumps({"files": [{"path": "shared.py"},
                                                      {"path": "b.py"}]}))
        return _proc()
    monkeypatch.setattr(bs, "_run", fake)
    assert bs._bead_surfaces("proj-aaa1") == ["a.py", "shared.py", "b.py"]


def test_pr_derived_surfaces_unblock_disjoint_candidate(monkeypatch):
    # End-to-end of the fix: an active claim with NO declared surfaces but an open
    # PR touching only frontend files must NOT block a candidate that declares
    # only backend surfaces. Pre-fix this returned True (UNKNOWN-collides-all).
    def fake(cmd, *, check=True):
        if cmd[:3] == ["bd", "show", "proj-claim"]:
            return _proc(stdout=json.dumps([{"id": "claim", "metadata": {}}]))
        if cmd[:3] == ["gh", "pr", "list"]:
            return _proc(stdout='[{"number": 9, "title": "x (bd proj-claim)"}]')
        if cmd[:3] == ["gh", "pr", "view"] and "9" in cmd:
            return _proc(stdout=json.dumps({"files": [{"path": "frontend/a.ts"}]}))
        return _proc()
    monkeypatch.setattr(bs, "_run", fake)
    claim_surfaces = bs._bead_surfaces("proj-claim")          # derived from PR
    assert claim_surfaces == ["frontend/a.ts"]
    candidate = ["backend/config.py", "pytest.ini"]
    assert bs._surfaces_overlap(candidate, claim_surfaces) is False


# --- conservative on uncertainty: every failure collapses to UNKNOWN ([]) so the
# overlap policy still blocks, never a partial footprint (bd 8y7, Codex review) ---

def test_bead_surfaces_bd_show_failure_is_unknown_not_pr_derived(monkeypatch):
    # bd show FAILS for a bead that genuinely has declared surfaces. We must NOT
    # silently replace the unreadable authoritative declaration with a narrower PR
    # diff -- a bd failure stays UNKNOWN ([]). If this fell through to derivation,
    # the gh calls below would (wrongly) win.
    def fake(cmd, *, check=True):
        if cmd[:3] == ["bd", "show", "proj-aaa1"]:
            return _proc(returncode=1, stderr="dolt down")
        if cmd[:3] == ["gh", "pr", "list"]:
            return _proc(stdout='[{"number": 5, "title": "x (bd proj-aaa1)"}]')
        if cmd[:3] == ["gh", "pr", "view"]:
            return _proc(stdout=json.dumps({"files": [{"path": "a.py"}]}))
        return _proc()
    monkeypatch.setattr(bs, "_run", fake)
    assert bs._bead_surfaces("proj-aaa1") == []
    # And UNKNOWN [] still blocks under the conservative policy.
    assert bs._surfaces_overlap(["whatever.py"], []) is True


def test_pr_changed_files_truncation_is_unknown(monkeypatch):
    # A file list at the gh 100-file cap may be truncated -> None (UNKNOWN), never
    # a partial list that could hide an overlap.
    big = {"files": [{"path": "f{}.py".format(i)} for i in range(bs._PR_FILE_CAP)]}
    rec = _RunRecorder([
        (lambda c: c[:3] == ["gh", "pr", "view"],
         _proc(stdout=json.dumps(big))),
    ])
    monkeypatch.setattr(bs, "_run", rec)
    assert bs._pr_changed_files(9, bs.DEFAULT_REPO) is None


def test_pr_changed_files_includes_renamed_old_path(monkeypatch):
    # A rename touches BOTH the new and old path -> both are write targets.
    rec = _RunRecorder([
        (lambda c: c[:3] == ["gh", "pr", "view"],
         _proc(stdout=json.dumps({"files": [
             {"path": "new/name.py", "previousPath": "old/name.py"}]}))),
    ])
    monkeypatch.setattr(bs, "_run", rec)
    assert bs._pr_changed_files(9, bs.DEFAULT_REPO) == ["new/name.py", "old/name.py"]


def test_derive_surfaces_partial_failure_is_unknown(monkeypatch):
    # Two PRs carry the id; the second PR's file lookup FAILS. The union would be
    # incomplete -> the whole derivation returns None (UNKNOWN), not a partial set.
    def fake(cmd, *, check=True):
        if cmd[:3] == ["bd", "show", "proj-aaa1"]:
            return _proc(stdout=json.dumps([{"id": "x", "metadata": {}}]))
        if cmd[:3] == ["gh", "pr", "list"]:
            return _proc(stdout=json.dumps([
                {"number": 7, "title": "a (bd proj-aaa1)"},
                {"number": 8, "title": "b (bd proj-aaa1)"},
            ]))
        if cmd[:3] == ["gh", "pr", "view"] and "7" in cmd:
            return _proc(stdout=json.dumps({"files": [{"path": "a.py"}]}))
        if cmd[:3] == ["gh", "pr", "view"] and "8" in cmd:
            return _proc(returncode=1, stderr="boom")
        return _proc()
    monkeypatch.setattr(bs, "_run", fake)
    assert bs._derive_surfaces_from_prs("proj-aaa1", bs.DEFAULT_REPO) is None
    # And _bead_surfaces coerces that None -> [] (UNKNOWN) for the overlap math.
    assert bs._bead_surfaces("proj-aaa1") == []


def test_derive_surfaces_pr_list_failure_is_unknown(monkeypatch):
    # The PR-list lookup itself fails -> None (UNKNOWN), distinct from a confident
    # "no open PR" ([]).
    def fake(cmd, *, check=True):
        if cmd[:3] == ["gh", "pr", "list"]:
            return _proc(returncode=1, stderr="rate limited")
        return _proc()
    monkeypatch.setattr(bs, "_run", fake)
    assert bs._pr_numbers_for_bead("proj-aaa1", bs.DEFAULT_REPO) is None
    assert bs._derive_surfaces_from_prs("proj-aaa1", bs.DEFAULT_REPO) is None


def test_surface_collision_does_not_derive_for_claiming_bead(monkeypatch):
    # The bead being CLAIMED is read with derive_from_prs=False (it has no PR yet),
    # so _surface_collision makes no `gh pr view` for it -- only `_pr_collision`'s
    # own `gh pr list` runs. With no active claims, no surface collision.
    def fake(cmd, *, check=True):
        if cmd[:3] == ["bd", "show", "proj-claim"]:
            return _proc(stdout=json.dumps([{"id": "x", "metadata": {}}]))
        if cmd[:2] == ["bd", "list"]:
            return _proc(stdout="[]")  # no active claims
        return _proc()
    rec_calls = []
    orig = fake
    def recording(cmd, *, check=True):
        rec_calls.append(list(cmd))
        return orig(cmd, check=check)
    monkeypatch.setattr(bs, "_run", recording)
    assert bs._surface_collision("proj-claim") is None
    assert not any(c[:3] == ["gh", "pr", "view"] for c in rec_calls)


def test_active_claim_ids_filters_to_live_work(monkeypatch):
    # in_progress beads: foo has an open PR (live -> active); bar has neither PR
    # nor branch (stale -> NOT active); the exclude_id is never counted.
    def fake(cmd, *, check=True):
        if cmd[:2] == ["bd", "list"]:
            return _proc(stdout=json.dumps([
                {"id": "proj-foo", "status": "in_progress"},
                {"id": "proj-bar", "status": "in_progress"},
                {"id": "proj-self", "status": "in_progress"},
            ]))
        if cmd[:4] == ["git", "rev-parse", "--abbrev-ref", "HEAD"]:
            return _proc(stdout="dev")
        if cmd[:3] == ["gh", "pr", "list"]:
            if "proj-foo" in " ".join(cmd):
                return _proc(stdout='[{"number":1,"title":"x (bd proj-foo)"}]')
            return _proc(stdout="[]")
        if cmd[:3] == ["git", "branch", "-a"]:
            return _proc(stdout="* dev")  # no foreign branches
        return _proc()
    monkeypatch.setattr(bs, "_run", fake)
    active = bs._active_claim_ids(exclude_id="proj-self")
    assert active == ["proj-foo"]          # foo live, bar stale dropped
    assert "proj-bar" not in active
    assert "proj-self" not in active        # excluded


def test_active_claim_ids_isolates_per_bead_failure(monkeypatch):
    # A transient gh failure for ONE in-progress bead must not abort the whole
    # enumeration; that bead is conservatively counted as active (#5).
    def fake(cmd, *, check=True):
        if cmd[:2] == ["bd", "list"]:
            return _proc(stdout=json.dumps([
                {"id": "proj-boom", "status": "in_progress"},
                {"id": "proj-ok", "status": "in_progress"},
            ]))
        if cmd[:4] == ["git", "rev-parse", "--abbrev-ref", "HEAD"]:
            return _proc(stdout="dev")
        if cmd[:3] == ["gh", "pr", "list"]:
            if "proj-boom" in " ".join(cmd):
                # _pr_collision raises RuntimeError on a non-zero gh exit.
                return _proc(returncode=1, stderr="gh transient")
            if "proj-ok" in " ".join(cmd):
                return _proc(stdout='[{"number":2,"title":"y (bd proj-ok)"}]')
            return _proc(stdout="[]")
        if cmd[:3] == ["git", "branch", "-a"]:
            return _proc(stdout="* dev")
        return _proc()
    monkeypatch.setattr(bs, "_run", fake)
    active = bs._active_claim_ids(exclude_id="")
    # boom counted (conservative on failure), ok counted (live PR).
    assert set(active) == {"proj-boom", "proj-ok"}


def test_claim_aborts_on_surface_overlap(monkeypatch, capsys):
    # No PR/branch collision on the bead itself, but an ACTIVE foreign claim
    # writes an overlapping surface -> hard block (the R1 guard).
    def fake(cmd, *, check=True):
        if cmd[:2] == ["bd", "dolt"]:
            return _proc()
        if cmd[:3] == ["gh", "pr", "list"]:
            # the bead being claimed has no PR; the active claim 'other' does.
            if "proj-other" in " ".join(cmd):
                return _proc(stdout='[{"number":9,"title":"x (bd proj-other)"}]')
            return _proc(stdout="[]")
        if cmd[:3] == ["git", "branch", "-a"]:
            return _proc(stdout="* dev")
        if cmd[:4] == ["git", "rev-parse", "--abbrev-ref", "HEAD"]:
            return _proc(stdout="dev")
        if cmd[:2] == ["bd", "list"]:
            return _proc(stdout=json.dumps([{"id": "proj-other", "status": "in_progress"}]))
        if cmd[:3] == ["bd", "show", "proj-mine"]:
            return _proc(stdout=_bead_show_json(["scripts/"]))
        if cmd[:3] == ["bd", "show", "proj-other"]:
            return _proc(stdout=_bead_show_json(["scripts/foo.py"]))
        return _proc()
    monkeypatch.setattr(bs, "_run", fake)
    args = types.SimpleNamespace(
        id="proj-mine", repo=bs.DEFAULT_REPO, no_surface_check=False
    )
    rc = bs.cmd_claim(args)
    assert rc == bs.EXIT_ABORT_COLLISION
    out = capsys.readouterr().out
    assert "write-surface overlap" in out
    assert "proj-other" in out


def test_claim_no_surface_check_flag_skips_guard(monkeypatch):
    # --no-surface-check drops ONLY the surface guard; the claim proceeds even
    # with an overlapping active claim present.
    def fake(cmd, *, check=True):
        if cmd[:3] == ["gh", "pr", "list"]:
            return _proc(stdout="[]")
        if cmd[:3] == ["git", "branch", "-a"]:
            return _proc(stdout="* dev")
        if cmd[:4] == ["git", "rev-parse", "--abbrev-ref", "HEAD"]:
            return _proc(stdout="dev")
        # bd list should NOT even be consulted when the guard is skipped, but be
        # safe if it is.
        if cmd[:2] == ["bd", "list"]:
            return _proc(stdout=json.dumps([{"id": "proj-other", "status": "in_progress"}]))
        if cmd[:3] == ["bd", "show", "proj-other"]:
            return _proc(stdout=_bead_show_json(["scripts/foo.py"]))
        if cmd[:3] == ["bd", "show", "proj-mine"]:
            return _proc(stdout=_bead_show_json(["scripts/"]))
        return _proc()
    rec_calls = []
    orig = fake
    def tracking(cmd, *, check=True):
        rec_calls.append(list(cmd))
        return orig(cmd, check=check)
    monkeypatch.setattr(bs, "_run", tracking)
    args = types.SimpleNamespace(
        id="proj-mine", repo=bs.DEFAULT_REPO, no_surface_check=True
    )
    rc = bs.cmd_claim(args)
    assert rc == bs.EXIT_OK
    assert any("--claim" in c for c in rec_calls)
    # guard skipped: no bd list (active-claim enumeration) was run.
    assert not any(c[:2] == ["bd", "list"] for c in rec_calls)


def test_claim_proceeds_when_surfaces_disjoint(monkeypatch):
    # An active claim exists but its surfaces are disjoint -> claim proceeds.
    def fake(cmd, *, check=True):
        if cmd[:3] == ["gh", "pr", "list"]:
            if "proj-other" in " ".join(cmd):
                return _proc(stdout='[{"number":9,"title":"x (bd proj-other)"}]')
            return _proc(stdout="[]")
        if cmd[:3] == ["git", "branch", "-a"]:
            return _proc(stdout="* dev")
        if cmd[:4] == ["git", "rev-parse", "--abbrev-ref", "HEAD"]:
            return _proc(stdout="dev")
        if cmd[:2] == ["bd", "list"]:
            return _proc(stdout=json.dumps([{"id": "proj-other", "status": "in_progress"}]))
        if cmd[:3] == ["bd", "show", "proj-other"]:
            return _proc(stdout=_bead_show_json(["docs/a.md"]))
        if cmd[:3] == ["bd", "show", "proj-mine"]:
            return _proc(stdout=_bead_show_json(["scripts/b.py"]))
        return _proc()
    monkeypatch.setattr(bs, "_run", fake)
    args = types.SimpleNamespace(
        id="proj-mine", repo=bs.DEFAULT_REPO, no_surface_check=False
    )
    assert bs.cmd_claim(args) == bs.EXIT_OK
