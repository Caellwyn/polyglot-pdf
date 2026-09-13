"""Tests for scripts/closeout_prep.py (bd polyglot-pdf-hrn.2).

Pins the parts the plan's verification calls out for #4:
  - the structured result shape (check/status/summary/detail);
  - status roll-up (FAIL outranks ATTENTION outranks OK) and the exit-code map;
  - precondition parsing (dirty tree / no-commits-ahead -> ATTENTION, bad base
    ref -> ATTENTION with the git message, clean+ahead -> OK) via a stubbed git;
  - the doc-freshness STALE-marker parse and the beads exit-code mapping;
  - the rendered TODO leads with the right RESULT line per overall status.

The check functions shell out (git / the sibling scripts / pytest), so those
are exercised by stubbing the subprocess boundary rather than spawning real
processes -- the same module-load + monkeypatch pattern as the other harness
tests. The live end-to-end run is the closeout's own Step 4.

Run with the backend venv (the worktree has no venv of its own):
  PYTHONPATH=. backend/.venv/Scripts/python.exe -m pytest tests/test_closeout_prep.py
"""
import importlib.util
import os
import pathlib
import subprocess
import sys

import pytest


SCRIPT_PATH = (
    pathlib.Path(__file__).resolve().parent.parent / "scripts" / "closeout_prep.py"
)
spec = importlib.util.spec_from_file_location("closeout_prep", SCRIPT_PATH)
prep = importlib.util.module_from_spec(spec)
sys.modules["closeout_prep"] = prep
spec.loader.exec_module(prep)


def _cp(returncode=0, stdout="", stderr=""):
    """Build a fake CompletedProcess for stubbing the subprocess boundary."""
    return subprocess.CompletedProcess(args=[], returncode=returncode,
                                       stdout=stdout, stderr=stderr)


@pytest.fixture()
def clean_git_env(monkeypatch):
    """Drop every inherited GIT_* var for the whole test, not just _git_in.

    _git_in isolates the commands IT runs, but the code under test
    (check_preconditions) shells out through its own helper and inherits the
    ambient environment -- so with GIT_DIR set it inspects the WRONG REPOSITORY
    while the scratch repo is built correctly. Any real-repo test must clear the
    variables process-wide, which is what this does.
    """
    for key in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(key, raising=False)


def _git_in(path):
    """A git runner for a scratch repo, ISOLATED from the ambient gitconfig.

    Some checks can only be pinned against real git -- a stub returns a canned
    string and structurally cannot see a command-line flag like --no-renames or
    -z. But a real-git test inherits the developer's global config, and
    `commit.gpgsign=true` (common, and set on many CI images) makes every commit
    exit 128. GIT_CONFIG_GLOBAL/SYSTEM=/dev/null pins the environment so the
    test fails only for the reason it exists to catch.

    stderr is surfaced on failure: `check=True` with `capture_output=True`
    otherwise reports a bare exit-128 with git's actual complaint swallowed.
    """
    # STRIP EVERY INHERITED GIT_* VAR, not just the config files. Two classes
    # defeat a narrower fix, and the first is severe:
    #
    #   * GIT_DIR -- `git init` on the scratch dir becomes a no-op re-init of
    #     the AMBIENT repo, and every add/commit/checkout after it lands there.
    #     A test suite whose subject is "do not silently mutate someone else's
    #     git history" would have been doing exactly that.
    #   * GIT_CONFIG_COUNT / GIT_CONFIG_KEY_n / GIT_CONFIG_VALUE_n -- applied
    #     ON TOP of nulled config files, so commit.gpgsign=true still breaks
    #     every commit through that door.
    #
    # Allowlist rather than blocklist: anything GIT_-prefixed is dropped, then
    # only what the test needs is set back.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "t"
    env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "t@t"

    def run(*args):
        r = subprocess.run(["git", *args], cwd=str(path), env=env,
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise AssertionError("git {} failed ({}): {}".format(
                " ".join(args), r.returncode, r.stderr.strip()))
        return r

    return run


# --------------------------------------------------------------------------- #
# Status roll-up + exit-code map
# --------------------------------------------------------------------------- #
class TestOverallStatus:
    def test_all_ok(self):
        results = [prep._result("a", prep.STATUS_OK, "x"),
                   prep._result("b", prep.STATUS_OK, "y")]
        assert prep.overall_status(results) == prep.STATUS_OK

    def test_attention_when_any_attention(self):
        results = [prep._result("a", prep.STATUS_OK, "x"),
                   prep._result("b", prep.STATUS_ATTENTION, "y")]
        assert prep.overall_status(results) == prep.STATUS_ATTENTION

    def test_fail_outranks_attention(self):
        results = [prep._result("a", prep.STATUS_ATTENTION, "x"),
                   prep._result("b", prep.STATUS_FAIL, "y")]
        assert prep.overall_status(results) == prep.STATUS_FAIL

    def test_exit_code_map(self):
        assert prep._EXIT_FOR_STATUS[prep.STATUS_OK] == 0
        assert prep._EXIT_FOR_STATUS[prep.STATUS_ATTENTION] == 3
        assert prep._EXIT_FOR_STATUS[prep.STATUS_FAIL] == 1


# --------------------------------------------------------------------------- #
# Preconditions (Step 0) via stubbed _git
# --------------------------------------------------------------------------- #
class TestPreconditions:
    def test_clean_and_ahead_is_ok(self, monkeypatch):
        def fake_git(args, cwd=None):
            if args[0] == "merge-base":
                return _cp(0)  # branch claims to contain the base tip
            if args[:2] == ["status", "--short"]:
                return _cp(0, stdout="")  # clean
            if args[0] == "log":
                return _cp(0, stdout="abc123 some commit\n")  # one ahead
            return _cp(0)
        monkeypatch.setattr(prep, "_git", fake_git)
        r = prep.check_preconditions(pathlib.Path("/wt"), "origin/dev")
        assert r["status"] == prep.STATUS_OK
        assert "1 commit(s) ahead" in r["summary"]

    def test_wholesale_deletions_are_flagged(self, monkeypatch):
        """The stale-base squash trap (CLAUDE.md scar #3).

        `git reset --soft <branch>` from a branch cut off an OLDER base moves
        the pointer forward while keeping the old tree, so every commit that
        landed in between becomes a DELETION -- silently reverting other
        people's merged work. Nothing errors, the tree is CLEAN, and the suite
        stays green because the deleted work's tests go with it. Caught once by
        eye on bd polyglot-pdf-06u5o (a 4-file change reporting "11 files
        changed, 261 deletions"); this is the mechanical net.
        """
        def fake_git(args, cwd=None):
            if args[0] == "merge-base":
                return _cp(0)  # branch claims to contain the base tip
            if args[:2] == ["status", "--short"]:
                return _cp(0, stdout="")  # clean -- the trap leaves it clean
            if args[0] == "log":
                return _cp(0, stdout="abc123 squashed\n")
            if args[:3] == ["diff", "--diff-filter=M", "--name-only"]:
                return _cp(0, stdout="")
            if args[:3] == ["diff", "--diff-filter=D", "--name-only"]:
                # NUL-separated: the check passes -z so paths with spaces or
                # non-ASCII bytes are not quoted by git.
                return _cp(0, stdout="docs/journal/entries/other-work.md\x00"
                                     "frontend/src/someoneElse.test.ts\x00")
            return _cp(0)
        monkeypatch.setattr(prep, "_git", fake_git)
        r = prep.check_preconditions(pathlib.Path("/wt"), "origin/dev")
        assert r["status"] == prep.STATUS_ATTENTION
        assert "REVERTS 2 file(s)" in r["summary"]
        # The casualties must be NAMED -- a count alone does not tell the
        # orchestrator whose work is about to vanish.
        assert "frontend/src/someoneElse.test.ts" in r["detail"]

    def test_a_RENAMED_file_trap_is_caught_in_a_REAL_repo(self, tmp_path, clean_git_env):
        """--no-renames, pinned against real git rather than a stub.

        Git's rename detection collapses a rewound rename into an `R` entry,
        which neither the D nor the M filter selects -- so the trap reported
        STATUS_OK on a base that had renamed a file. The stubs cannot pin this:
        they return canned strings and never see the flag. This builds the trap
        for real.
        """
        g = _git_in(tmp_path)
        g("init", "-q", "-b", "main", ".")
        (tmp_path / "old.py").write_text("v1\n", encoding="utf-8")
        g("add", "-A")
        g("commit", "-q", "-m", "c1")
        g("checkout", "-qb", "feat")
        (tmp_path / "mine.txt").write_text("mine\n", encoding="utf-8")
        g("add", "-A")
        g("commit", "-q", "-m", "wip")
        g("checkout", "-q", "main")
        g("mv", "old.py", "new.py")          # the base RENAMES it
        g("commit", "-q", "-m", "their rename")
        g("checkout", "-q", "feat")
        g("reset", "--soft", "main")          # THE TRAP
        g("commit", "-q", "-m", "squashed")

        r = prep.check_preconditions(tmp_path, "main")

        assert r["status"] == prep.STATUS_ATTENTION, \
            "a rewound RENAME reported clean: {}".format(r["summary"])
        assert "REVERTS" in r["summary"]

    def test_a_NON_ASCII_path_trap_is_caught_in_a_REAL_repo(self, tmp_path, clean_git_env):
        """-z on BOTH diffs, pinned against real git.

        Without -z, git QUOTES a path containing non-ASCII bytes or spaces --
        emitting "caf\\303\\251.py" rather than the raw name. `rev-parse
        HEAD:"caf\\303\\251.py"` then fails, _rewound_paths returns [], and a
        genuine trap reports OK: a silent miss on exactly the paths hardest to
        eyeball. Measured: removing -z from the M-diff alone flips this repo's
        verdict from attention to ok while all stub tests stay green.

        The file is created with a bytes-level name so this source stays ASCII
        (CLAUDE.md scar #6).
        """
        g = _git_in(tmp_path)
        g("init", "-q", "-b", "main", ".")
        name = b"caf\xc3\xa9.py".decode("utf-8")
        (tmp_path / name).write_text("v1\n", encoding="utf-8")
        g("add", "-A")
        g("commit", "-q", "-m", "c1")
        g("checkout", "-qb", "feat")
        (tmp_path / "mine.txt").write_text("mine\n", encoding="utf-8")
        g("add", "-A")
        g("commit", "-q", "-m", "wip")
        g("checkout", "-q", "main")
        (tmp_path / name).write_text("v2-THEIR-FIX\n", encoding="utf-8")  # base EDITS it
        g("add", "-A")
        g("commit", "-q", "-m", "their fix")
        g("checkout", "-q", "feat")
        g("reset", "--soft", "main")          # THE TRAP
        g("commit", "-q", "-m", "squashed")

        r = prep.check_preconditions(tmp_path, "main")

        assert r["status"] == prep.STATUS_ATTENTION, \
            "a rewound non-ASCII path reported clean: {}".format(r["summary"])
        assert "REVERTS" in r["summary"]
        # The path must be REPORTED raw, not as git's quoted "caf\303\251.py"
        # form -- a name nobody can paste into a command.
        assert name in r["detail"], \
            "the casualty was named in git's quoted form: {}".format(r["detail"])

    def test_a_non_ascii_DELETION_is_named_raw_in_a_REAL_repo(self, tmp_path, clean_git_env):
        """-z on the D-diff specifically.

        The sibling test above exercises a MODIFIED non-ASCII path, so it pins
        -z only on the M-diff; the D-diff's own -z survived mutation until this
        existed. Here the base ADDS a non-ASCII file, so the trap surfaces it
        through the deletion path instead.
        """
        g = _git_in(tmp_path)
        g("init", "-q", "-b", "main", ".")
        (tmp_path / "seed.txt").write_text("v1\n", encoding="utf-8")
        g("add", "-A")
        g("commit", "-q", "-m", "c1")
        g("checkout", "-qb", "feat")
        (tmp_path / "mine.txt").write_text("mine\n", encoding="utf-8")
        g("add", "-A")
        g("commit", "-q", "-m", "wip")
        g("checkout", "-q", "main")
        name = b"r\xc3\xa9sum\xc3\xa9.py".decode("utf-8")
        (tmp_path / name).write_text("their new file\n", encoding="utf-8")
        g("add", "-A")
        g("commit", "-q", "-m", "their addition")
        g("checkout", "-q", "feat")
        g("reset", "--soft", "main")          # THE TRAP
        g("commit", "-q", "-m", "squashed")

        r = prep.check_preconditions(tmp_path, "main")

        assert r["status"] == prep.STATUS_ATTENTION, \
            "a deleted non-ASCII path reported clean: {}".format(r["summary"])
        assert name in r["detail"], \
            "the casualty was named in git's quoted form: {}".format(r["detail"])

    def test_a_SELF_revert_on_a_file_the_base_never_touched_is_not_flagged(
            self, tmp_path, clean_git_env):
        """`rev-list base`, not `rev-list HEAD`.

        A branch that experiments and then reverts its OWN change is doing
        routine work. The question the guard asks is "did this branch rewind to
        something the BASE once held", so the branch's own past versions must
        not be candidates -- walking HEAD's history makes them candidates and
        also shifts commits[0], defeating the base-tip skip.

        Real-repo rather than stubbed: a stub cannot observe WHICH ref rev-list
        was handed. I could not reproduce the divergence a reviewer reported, so
        this pins the property directly instead of arguing about the mechanism.
        """
        g = _git_in(tmp_path)
        g("init", "-q", "-b", "dev", ".")
        (tmp_path / "seed.txt").write_text("base\n", encoding="utf-8")
        g("add", "-A")
        g("commit", "-q", "-m", "c1")
        g("checkout", "-qb", "feat")
        cfg = tmp_path / "cfg.py"
        cfg.write_text("v2\n", encoding="utf-8")       # my work
        g("add", "-A")
        g("commit", "-q", "-m", "my v2")
        cfg.write_text("v3\n", encoding="utf-8")       # an experiment
        g("add", "-A")
        g("commit", "-q", "-m", "experiment")
        cfg.write_text("v2\n", encoding="utf-8")       # ...which I back out
        g("add", "-A")
        g("commit", "-q", "-m", "back to v2")

        r = prep.check_preconditions(tmp_path, "dev")

        assert r["status"] == prep.STATUS_OK, \
            "a routine self-revert was flagged as reverting the base: {}".format(
                r["summary"])

    def test_matching_the_BASE_TIP_is_not_a_revert(self, monkeypatch):
        """The `commits[1:]` skip -- the false-positive direction.

        A branch whose file ends up byte-identical to the BASE TIP'S OWN version
        holds current content; that is the normal case, not a revert. Without
        the skip, `commits[0]` (the base tip) is compared too and every such
        branch flags -- the cry-wolf regression that killed the earlier
        --diff-filter=DM attempt.

        Stubbed rather than real-repo because the trap direction cannot reach
        this: post-reset, HEAD differs from the base tip on every M-listed path
        by construction, so only a hand-built case exercises it.
        """
        def fake_git(args, cwd=None):
            if args[0] == "merge-base":
                return _cp(0)
            if args[:2] == ["status", "--short"]:
                return _cp(0, stdout="")
            if args[0] == "log":
                return _cp(0, stdout="abc123 c\n")
            if args[:3] == ["diff", "--diff-filter=D", "--name-only"]:
                return _cp(0, stdout="")
            if args[:3] == ["diff", "--diff-filter=M", "--name-only"]:
                return _cp(0, stdout="shared.py\0")
            if args[0] == "rev-parse" and args[1].startswith("HEAD:"):
                return _cp(0, stdout="blobTIP\n")   # same as the base tip's
            if args[0] == "rev-list":
                return _cp(0, stdout="tip111\nprev222\n")
            return _cp(0)

        def fake_batch(args, stdin_text, cwd=None):
            # The batch is fed ONLY commits[1:], so the base tip's own blob must
            # not appear here. If the skip is removed, the caller feeds tip111
            # as well and this stub's first line would match.
            assert "tip111:" not in stdin_text, \
                "the base tip was fed to the blob check -- commits[1:] skip lost"
            return _cp(0, stdout="blobOLDER\n")     # nothing older matches

        monkeypatch.setattr(prep, "_git", fake_git)
        monkeypatch.setattr(prep, "_git_stdin", fake_batch)
        r = prep.check_preconditions(pathlib.Path("/wt"), "origin/dev")

        assert r["status"] == prep.STATUS_OK
        assert "REVERTS" not in r["summary"]

    def test_the_ancestry_probe_asks_the_question_in_the_RIGHT_ORDER(self, monkeypatch):
        """`--is-ancestor <base> HEAD`, not the reverse.

        The operands are not symmetric: the question is "does HEAD contain the
        base tip", and asking it backwards inverts the gate so the guard is
        SKIPPED on exactly the trap it exists for. Measured against a real trap
        repo: the swap flips the verdict from "branch REVERTS 2 file(s)" to
        "clean tree". Every other stub in this file matches on
        `args[0] == "merge-base"` and returns rc=0 regardless of order, so
        nothing else can see the swap.
        """
        seen = {}

        def fake_git(args, cwd=None):
            if args[0] == "merge-base":
                seen["argv"] = list(args)
                # rc=0 ONLY for the correct order; the swap must not pass.
                if args == ["merge-base", "--is-ancestor", "origin/dev", "HEAD"]:
                    return _cp(0)
                return _cp(1)
            if args[:2] == ["status", "--short"]:
                return _cp(0, stdout="")
            if args[0] == "log":
                return _cp(0, stdout="abc123 squashed\n")
            if args[:3] == ["diff", "--diff-filter=D", "--name-only"]:
                return _cp(0, stdout="theirWork.py\0")
            if args[:3] == ["diff", "--diff-filter=M", "--name-only"]:
                return _cp(0, stdout="")
            return _cp(0)

        monkeypatch.setattr(prep, "_git", fake_git)
        r = prep.check_preconditions(pathlib.Path("/wt"), "origin/dev")

        assert seen["argv"] == ["merge-base", "--is-ancestor", "origin/dev", "HEAD"], \
            "ancestry probe asked the wrong question: {}".format(seen.get("argv"))
        # ...and the guard actually ran, rather than being gated out.
        assert r["status"] == prep.STATUS_ATTENTION
        assert "REVERTS 1 file(s)" in r["summary"]

    def test_a_REWOUND_edit_is_flagged(self, monkeypatch):
        """The commoner trap shape: the base EDITED a file, and the branch
        carries an older version of it.

        No deletion is involved, so a deletions-only check reports clean. The
        discriminator is BLOB IDENTITY -- a rewound file is byte-identical to an
        earlier commit's version, an edited one to none. Content survives the
        reset; commit topology does not.
        """
        def fake_git(args, cwd=None):
            if args[0] == "merge-base":
                return _cp(0)
            if args[:2] == ["status", "--short"]:
                return _cp(0, stdout="")
            if args[0] == "log":
                return _cp(0, stdout="abc123 squashed\n")
            if args[:3] == ["diff", "--diff-filter=D", "--name-only"]:
                return _cp(0, stdout="")           # NOTHING deleted
            if args[:3] == ["diff", "--diff-filter=M", "--name-only"]:
                return _cp(0, stdout="backend/theirFix.py\n")
            if args[0] == "rev-parse" and args[1] == "HEAD:backend/theirFix.py":
                return _cp(0, stdout="blobOLD\n")  # what the branch carries
            if args[0] == "rev-list":
                return _cp(0, stdout="tip111\nprev222\n")
            return _cp(0)

        def fake_batch(args, stdin_text, cwd=None):
            # cat-file --batch-check resolves the whole history in ONE call --
            # a separate subprocess boundary that must be stubbed too.
            return _cp(0, stdout="blobOLD\n")  # ...matches an OLDER commit

        monkeypatch.setattr(prep, "_git", fake_git)
        monkeypatch.setattr(prep, "_git_stdin", fake_batch)
        r = prep.check_preconditions(pathlib.Path("/wt"), "origin/dev")
        assert r["status"] == prep.STATUS_ATTENTION
        assert "REVERTS 1 file(s)" in r["summary"]
        assert "backend/theirFix.py" in r["detail"]

    def test_a_LEGITIMATE_edit_is_not_flagged(self, monkeypatch):
        """The cry-wolf test that killed an earlier --diff-filter=DM attempt.

        A branch editing a file the base also touched must stay silent: its
        content matches NO older version, because it is new work.
        """
        def fake_git(args, cwd=None):
            if args[0] == "merge-base":
                return _cp(0)
            if args[:2] == ["status", "--short"]:
                return _cp(0, stdout="")
            if args[0] == "log":
                return _cp(0, stdout="abc123 c\n")
            if args[:3] == ["diff", "--diff-filter=D", "--name-only"]:
                return _cp(0, stdout="")
            if args[:3] == ["diff", "--diff-filter=M", "--name-only"]:
                return _cp(0, stdout="backend/myEdit.py\n")
            if args[0] == "rev-parse" and args[1].startswith("HEAD:"):
                return _cp(0, stdout="blobNEW\n")  # my own new content
            if args[0] == "rev-list":
                return _cp(0, stdout="tip111\nprev222\n")
            return _cp(0)

        def fake_batch(args, stdin_text, cwd=None):
            return _cp(0, stdout="blobOTHER\n")  # matches nothing older

        monkeypatch.setattr(prep, "_git", fake_git)
        monkeypatch.setattr(prep, "_git_stdin", fake_batch)
        r = prep.check_preconditions(pathlib.Path("/wt"), "origin/dev")
        assert r["status"] == prep.STATUS_OK
        assert "REVERTS" not in r["summary"]

    def test_an_ordinary_BEHIND_base_branch_is_not_flagged(self, monkeypatch):
        """The ancestry gate.

        A branch that is simply behind the base does NOT claim to contain the
        base tip, and diffing it would report the base's own newer files as
        noise -- flagging every routine branch is how a guard gets ignored.
        Only `reset --soft <branch-name>` fakes the containment, which is what
        makes the containment the discriminating signal.
        """
        def fake_git(args, cwd=None):
            if args[0] == "merge-base":
                return _cp(1)  # does NOT contain the base tip
            if args[:2] == ["status", "--short"]:
                return _cp(0, stdout="")
            if args[0] == "log":
                return _cp(0, stdout="abc123 c\n")
            if args[:3] == ["diff", "--diff-filter=M", "--name-only"]:
                return _cp(0, stdout="")
            if args[:3] == ["diff", "--diff-filter=D", "--name-only"]:
                # Would report the base's newer files, but must never be asked.
                return _cp(0, stdout="someoneElse.py\n")
            return _cp(0)
        monkeypatch.setattr(prep, "_git", fake_git)
        r = prep.check_preconditions(pathlib.Path("/wt"), "origin/dev")
        assert r["status"] == prep.STATUS_OK
        assert "REVERTS" not in r["summary"]

    def test_a_broken_deletion_check_fails_CLOSED(self, monkeypatch):
        """An unreadable diff must not read as "no deletions".

        Reporting silence on a failed check is indistinguishable from a safe
        branch -- and silence is the exact failure this whole guard exists to
        eliminate. Reachable: three-dot diff exits 128 with "no merge base" on
        unrelated histories.
        """
        def fake_git(args, cwd=None):
            if args[0] == "merge-base":
                return _cp(0)  # branch claims to contain the base tip
            if args[:2] == ["status", "--short"]:
                return _cp(0, stdout="")
            if args[0] == "log":
                return _cp(0, stdout="abc123 c\n")
            if args[:3] == ["diff", "--diff-filter=M", "--name-only"]:
                return _cp(0, stdout="")
            if args[:3] == ["diff", "--diff-filter=D", "--name-only"]:
                return _cp(128, stderr="fatal: no merge base")
            return _cp(0)
        monkeypatch.setattr(prep, "_git", fake_git)
        r = prep.check_preconditions(pathlib.Path("/wt"), "origin/dev")
        assert r["status"] == prep.STATUS_ATTENTION
        assert "UNVERIFIED" in r["summary"]

    def test_no_deletions_does_not_false_positive(self, monkeypatch):
        """A purely additive branch must stay OK, or the check gets ignored."""
        def fake_git(args, cwd=None):
            if args[0] == "merge-base":
                return _cp(0)  # branch claims to contain the base tip
            if args[:2] == ["status", "--short"]:
                return _cp(0, stdout="")
            if args[0] == "log":
                return _cp(0, stdout="abc123 c\n")
            if args[:3] == ["diff", "--diff-filter=M", "--name-only"]:
                return _cp(0, stdout="")
            if args[:3] == ["diff", "--diff-filter=D", "--name-only"]:
                return _cp(0, stdout="")  # nothing deleted
            return _cp(0)
        monkeypatch.setattr(prep, "_git", fake_git)
        r = prep.check_preconditions(pathlib.Path("/wt"), "origin/dev")
        assert r["status"] == prep.STATUS_OK
        assert "REVERTS" not in r["summary"]

    def test_dirty_tree_is_attention(self, monkeypatch):
        def fake_git(args, cwd=None):
            if args[0] == "merge-base":
                return _cp(0)  # branch claims to contain the base tip
            if args[:2] == ["status", "--short"]:
                return _cp(0, stdout=" M foo.py\n?? bar.py\n")
            if args[0] == "log":
                return _cp(0, stdout="abc123 c\n")
            return _cp(0)
        monkeypatch.setattr(prep, "_git", fake_git)
        r = prep.check_preconditions(pathlib.Path("/wt"), "origin/dev")
        assert r["status"] == prep.STATUS_ATTENTION
        assert "DIRTY" in r["summary"]
        assert "foo.py" in r["detail"]

    def test_no_commits_ahead_is_attention(self, monkeypatch):
        def fake_git(args, cwd=None):
            if args[0] == "merge-base":
                return _cp(0)  # branch claims to contain the base tip
            if args[:2] == ["status", "--short"]:
                return _cp(0, stdout="")  # clean
            if args[0] == "log":
                return _cp(0, stdout="")  # none ahead
            return _cp(0)
        monkeypatch.setattr(prep, "_git", fake_git)
        r = prep.check_preconditions(pathlib.Path("/wt"), "origin/dev")
        assert r["status"] == prep.STATUS_ATTENTION
        assert "no commits ahead" in r["summary"]
        # Clean tree + no commits -> detail explains the empty commits section.
        assert "No commits ahead" in r["detail"]

    def test_dirty_and_no_commits_detail_mentions_both(self, monkeypatch):
        # When BOTH problems hold, the detail must mention the no-commits issue,
        # not just the uncommitted-file list (fresh-eyes PR #54).
        def fake_git(args, cwd=None):
            if args[0] == "merge-base":
                return _cp(0)  # branch claims to contain the base tip
            if args[:2] == ["status", "--short"]:
                return _cp(0, stdout=" M foo.py\n")  # dirty
            if args[0] == "log":
                return _cp(0, stdout="")  # none ahead
            return _cp(0)
        monkeypatch.setattr(prep, "_git", fake_git)
        r = prep.check_preconditions(pathlib.Path("/wt"), "origin/dev")
        assert r["status"] == prep.STATUS_ATTENTION
        assert "DIRTY" in r["summary"] and "no commits ahead" in r["summary"]
        assert "foo.py" in r["detail"]
        assert "No commits ahead" in r["detail"]  # second problem spelled out

    def test_bad_base_ref_is_attention_with_git_message(self, monkeypatch):
        def fake_git(args, cwd=None):
            if args[0] == "merge-base":
                return _cp(0)  # branch claims to contain the base tip
            if args[:2] == ["status", "--short"]:
                return _cp(0, stdout="")
            if args[0] == "log":
                return _cp(128, stderr="fatal: bad revision 'origin/nope...HEAD'")
            return _cp(0)
        monkeypatch.setattr(prep, "_git", fake_git)
        r = prep.check_preconditions(pathlib.Path("/wt"), "origin/nope")
        assert r["status"] == prep.STATUS_ATTENTION
        assert "bad ref" in r["summary"]
        assert "fatal" in r["detail"]

    def test_git_status_failure_is_fail(self, monkeypatch):
        def fake_git(args, cwd=None):
            if args[0] == "merge-base":
                return _cp(0)  # branch claims to contain the base tip
            if args[:2] == ["status", "--short"]:
                return _cp(1, stderr="not a git repo")
            return _cp(0)
        monkeypatch.setattr(prep, "_git", fake_git)
        r = prep.check_preconditions(pathlib.Path("/wt"), "origin/dev")
        assert r["status"] == prep.STATUS_FAIL


# --------------------------------------------------------------------------- #
# Beads (Step 1): housekeeping exit-code mapping
# --------------------------------------------------------------------------- #
class TestBeads:
    def test_exit_0_is_ok(self, monkeypatch, tmp_path):
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "closeout_housekeeping.py").write_text("#", encoding="utf-8")
        monkeypatch.setattr(prep, "_run_check_script",
                            lambda *a, **k: _cp(0, stdout="RESULT: CLEAN"))
        r = prep.check_beads(pathlib.Path("py"), tmp_path)
        assert r["status"] == prep.STATUS_OK

    def test_exit_3_is_attention(self, monkeypatch, tmp_path):
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "closeout_housekeeping.py").write_text("#", encoding="utf-8")
        monkeypatch.setattr(prep, "_run_check_script",
                            lambda *a, **k: _cp(3, stdout="RESULT: SLIP-FOUND"))
        r = prep.check_beads(pathlib.Path("py"), tmp_path)
        assert r["status"] == prep.STATUS_ATTENTION
        assert "SLIP" in r["summary"]

    def test_exit_1_is_fail(self, monkeypatch, tmp_path):
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "closeout_housekeeping.py").write_text("#", encoding="utf-8")
        monkeypatch.setattr(prep, "_run_check_script",
                            lambda *a, **k: _cp(1, stderr="bd missing"))
        r = prep.check_beads(pathlib.Path("py"), tmp_path)
        assert r["status"] == prep.STATUS_FAIL

    def test_missing_script_is_fail(self, tmp_path):
        r = prep.check_beads(pathlib.Path("py"), tmp_path)  # no scripts/ dir
        assert r["status"] == prep.STATUS_FAIL
        assert "not found" in r["summary"]


# --------------------------------------------------------------------------- #
# Docs (Step 2): STALE-marker parse
# --------------------------------------------------------------------------- #
class TestDocs:
    def _mk(self, tmp_path):
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "check_doc_freshness.py").write_text("#", encoding="utf-8")

    def test_clean_output_is_ok(self, monkeypatch, tmp_path):
        self._mk(tmp_path)
        monkeypatch.setattr(prep, "_run_check_script",
                            lambda *a, **k: _cp(0, stdout="docs/x.md: OK\nAll docs up to date."))
        r = prep.check_docs(pathlib.Path("py"), tmp_path)
        assert r["status"] == prep.STATUS_OK

    def test_stale_marker_is_attention(self, monkeypatch, tmp_path):
        self._mk(tmp_path)
        monkeypatch.setattr(prep, "_run_check_script",
                            lambda *a, **k: _cp(0, stdout="  STALE: docs/x.md  (older than ...)"))
        r = prep.check_docs(pathlib.Path("py"), tmp_path)
        assert r["status"] == prep.STATUS_ATTENTION
        assert "STALE" in r["summary"]

    def test_nonzero_exit_is_fail_not_false_clean(self, monkeypatch, tmp_path):
        # The freshness checker is documented to always exit 0; a non-zero exit
        # means it CRASHED, so empty stdout must NOT read as OK (fresh-eyes PR
        # #54). It must be FAIL, never a false-clean.
        self._mk(tmp_path)
        monkeypatch.setattr(prep, "_run_check_script",
                            lambda *a, **k: _cp(1, stdout="", stderr="Traceback ... ImportError"))
        r = prep.check_docs(pathlib.Path("py"), tmp_path)
        assert r["status"] == prep.STATUS_FAIL
        assert "crashed" in r["summary"]


# --------------------------------------------------------------------------- #
# Tests (Step 4): pytest exit-code mapping + summary parse
# --------------------------------------------------------------------------- #
class TestTests:
    def test_pass_is_ok(self, monkeypatch, tmp_path):
        (tmp_path / "backend" / "tests").mkdir(parents=True)
        monkeypatch.setattr(prep.subprocess, "run",
                            lambda *a, **k: _cp(0, stdout="...\n168 passed, 2 skipped in 35s"))
        r = prep.check_tests(pathlib.Path("py"), tmp_path)
        assert r["status"] == prep.STATUS_OK
        assert "168 passed" in r["summary"]

    def test_failure_is_attention(self, monkeypatch, tmp_path):
        (tmp_path / "backend" / "tests").mkdir(parents=True)
        monkeypatch.setattr(prep.subprocess, "run",
                            lambda *a, **k: _cp(1, stdout="...\n1 failed, 167 passed"))
        r = prep.check_tests(pathlib.Path("py"), tmp_path)
        assert r["status"] == prep.STATUS_ATTENTION
        assert "FAILED" in r["summary"]

    def test_missing_tests_dir_is_fail(self, tmp_path):
        r = prep.check_tests(pathlib.Path("py"), tmp_path)
        assert r["status"] == prep.STATUS_FAIL

    def test_summary_line_extracts_passed(self):
        assert "168 passed" in prep._summary_line("blah\n168 passed, 2 skipped in 3s\n")
        assert prep._summary_line("no summary here") == ""

    def test_timeout_is_its_own_status_not_a_launch_failure(self, monkeypatch, tmp_path):
        """A suite that merely ran LONG must never render as "could not run".

        bd polyglot-pdf-u98r1: the run was widened to every testpaths root
        (590s -> 706s) while the ceiling stayed at 600s, so check_tests died on
        its own timeout on EVERY closeout. Because TimeoutExpired subclasses
        SubprocessError, the generic `except SubprocessError` arm swallowed it
        and reported "could not run pytest" -- which overall_status renders as
        "RESULT: PREP-ERROR -- a check could not run (not a closeout verdict)".
        The orchestrator reads past a tooling error, so the pre-PR suite gate
        verified NOTHING while still looking like it had run.

        So the timeout arm must be ordered FIRST and say what actually
        happened. This pins the distinction the bug erased: a timeout is
        ATTENTION (a missing verdict someone must chase), not the FAIL that
        means the launch itself broke.
        """
        (tmp_path / "backend" / "tests").mkdir(parents=True)

        def _timeout(*a, **k):
            raise subprocess.TimeoutExpired(cmd=["pytest"], timeout=prep._TESTS_TIMEOUT_S)

        monkeypatch.setattr(prep.subprocess, "run", _timeout)
        r = prep.check_tests(pathlib.Path("py"), tmp_path)

        assert r["status"] == prep.STATUS_ATTENTION, (
            "a timed-out suite must not be the FAIL that means 'could not run'"
        )
        # Distinguishable from the launch-failure arm by its text, so the
        # orchestrator can tell 'ran long, no verdict' from 'never started'.
        assert "could not run pytest" not in r["summary"]
        assert str(prep._TESTS_TIMEOUT_S) in r["summary"]

    def test_launch_failure_is_still_fail(self, monkeypatch, tmp_path):
        """The negative half: a REAL launch failure must keep reporting FAIL.

        Without this, the arm above could be "satisfied" by mapping every
        subprocess error to ATTENTION, which would hide a broken interpreter.
        """
        (tmp_path / "backend" / "tests").mkdir(parents=True)

        def _boom(*a, **k):
            raise OSError("No such file or directory: 'py'")

        monkeypatch.setattr(prep.subprocess, "run", _boom)
        r = prep.check_tests(pathlib.Path("py"), tmp_path)
        assert r["status"] == prep.STATUS_FAIL
        assert "could not run pytest" in r["summary"]

    def test_ceiling_clears_the_measured_full_suite_runtime(self):
        """The ceiling must carry real headroom over the MEASURED runtime.

        The original bug was not that a timeout existed -- it was that the
        ceiling sat 106s BELOW the run it had to cover. 600s was itself only
        10s above the older, narrower scope, i.e. sized with no headroom and
        therefore one suite-growth away from re-breaking.

        Asserting a MULTIPLE of the measured runtime (not a bare `> measured`)
        is what keeps this honest: a ceiling that merely squeaks past today's
        wall time reopens the same hole on a slower box or after a few hundred
        new tests.
        """
        measured_full_suite_s = 706  # bd polyglot-pdf-u98r1, reference machine
        assert prep._TESTS_TIMEOUT_S >= 2 * measured_full_suite_s, (
            "_TESTS_TIMEOUT_S={}s leaves too little headroom over the measured "
            "{}s full-suite run; size it with room for a slower machine and "
            "future test growth".format(prep._TESTS_TIMEOUT_S, measured_full_suite_s)
        )


# --------------------------------------------------------------------------- #
# Rendering: the TODO leads with the right RESULT line
# --------------------------------------------------------------------------- #
class TestRender:
    def test_ready_when_all_ok(self):
        results = [prep._result("preconditions", prep.STATUS_OK, "clean"),
                   prep._result("beads", prep.STATUS_OK, "no slips")]
        out = prep.render_todo(results, prep.STATUS_OK)
        assert "RESULT: READY" in out
        assert "[OK]" in out

    def test_attention_lists_only_attention_items(self):
        results = [prep._result("preconditions", prep.STATUS_OK, "clean"),
                   prep._result("docs", prep.STATUS_ATTENTION, "stale doc", detail="STALE: x.md")]
        out = prep.render_todo(results, prep.STATUS_ATTENTION)
        assert "RESULT: ATTENTION" in out
        assert "docs: stale doc" in out
        assert "STALE: x.md" in out  # detail block shown
        assert "preconditions: clean" not in out  # ok items not in the triage list

    def test_prep_error_when_fail(self):
        results = [prep._result("beads", prep.STATUS_FAIL, "bd missing", detail="trace")]
        out = prep.render_todo(results, prep.STATUS_FAIL)
        assert "RESULT: PREP-ERROR" in out
        assert "beads: bd missing" in out

    def test_prep_error_still_surfaces_attention_detail(self):
        # A FAIL outranks a co-occurring ATTENTION in the verdict, but the
        # ATTENTION item's detail must STILL be shown so a mixed run doesn't cost
        # a second round-trip to discover the dirty tree (fresh-eyes PR #54).
        results = [
            prep._result("preconditions", prep.STATUS_ATTENTION, "dirty", detail="M foo.py"),
            prep._result("docs", prep.STATUS_FAIL, "freshness crashed", detail="Traceback"),
        ]
        out = prep.render_todo(results, prep.STATUS_FAIL)
        assert "RESULT: PREP-ERROR" in out
        assert "docs: freshness crashed" in out          # the headline FAIL
        assert "Also needs triage" in out                # the attention section
        assert "preconditions: dirty" in out
        assert "M foo.py" in out                          # the attention DETAIL is present


# --------------------------------------------------------------------------- #
# CLI wiring (main): json + skip-tests + exit code, with checks stubbed
# --------------------------------------------------------------------------- #
class TestMain:
    def _stub_roots(self, monkeypatch, tmp_path):
        py = tmp_path / "py"
        py.write_text("#", encoding="utf-8")
        monkeypatch.setattr(prep, "resolve_roots", lambda: (tmp_path, tmp_path))
        monkeypatch.setattr(prep, "venv_python", lambda R: py)

    def test_main_json_and_exit_ok(self, monkeypatch, tmp_path, capsys):
        self._stub_roots(monkeypatch, tmp_path)
        monkeypatch.setattr(prep, "check_preconditions",
                            lambda WT, base: prep._result("preconditions", prep.STATUS_OK, "clean"))
        monkeypatch.setattr(prep, "check_beads",
                            lambda py, WT: prep._result("beads", prep.STATUS_OK, "ok"))
        monkeypatch.setattr(prep, "check_docs",
                            lambda py, WT: prep._result("docs", prep.STATUS_OK, "ok"))
        rc = prep.main(["--skip-tests", "--json"])
        assert rc == 0
        import json
        payload = json.loads(capsys.readouterr().out)
        assert payload["status"] == "ok"
        assert {c["check"] for c in payload["checks"]} == {"preconditions", "beads", "docs"}

    def test_main_skip_tests_omits_test_check(self, monkeypatch, tmp_path, capsys):
        self._stub_roots(monkeypatch, tmp_path)
        # Map each check function to the check name it reports, explicitly (not
        # by string-splitting the function name -- that was fragile against a
        # multi-segment name like check_foo_bar; fresh-eyes PR #54).
        check_names = {
            "check_preconditions": "preconditions",
            "check_beads": "beads",
            "check_docs": "docs",
        }
        for fn_name, check in check_names.items():
            monkeypatch.setattr(prep, fn_name,
                                (lambda c: (lambda *a, **k: prep._result(c, prep.STATUS_OK, "ok")))(check))
        called = {"tests": False}
        def boom(*a, **k):
            called["tests"] = True
            return prep._result("tests", prep.STATUS_OK, "ok")
        monkeypatch.setattr(prep, "check_tests", boom)
        prep.main(["--skip-tests", "--json"])
        assert called["tests"] is False

    def test_main_exit_3_on_attention(self, monkeypatch, tmp_path, capsys):
        self._stub_roots(monkeypatch, tmp_path)
        monkeypatch.setattr(prep, "check_preconditions",
                            lambda WT, base: prep._result("preconditions", prep.STATUS_ATTENTION, "dirty"))
        monkeypatch.setattr(prep, "check_beads",
                            lambda py, WT: prep._result("beads", prep.STATUS_OK, "ok"))
        monkeypatch.setattr(prep, "check_docs",
                            lambda py, WT: prep._result("docs", prep.STATUS_OK, "ok"))
        rc = prep.main(["--skip-tests"])
        assert rc == 3

    def test_main_venv_missing_is_fail(self, monkeypatch, tmp_path):
        monkeypatch.setattr(prep, "resolve_roots", lambda: (tmp_path, tmp_path))
        monkeypatch.setattr(prep, "venv_python", lambda R: tmp_path / "no-such-python")
        rc = prep.main(["--skip-tests"])
        assert rc == 1


# --------------------------------------------------------------------------- #
# cp1252 stdout regression (bd polyglot-pdf-hrn.16)
# --------------------------------------------------------------------------- #
class TestCp1252Stdout:
    """render_todo embeds bd orphans/stale output, which carries non-cp1252
    glyphs (U+2713 checkmark, U+23F0 alarm-clock). On a cp1252 Windows console
    print() raised UnicodeEncodeError and the script exited PREP-ERROR instead
    of printing its verdict. The module-level stream reconfigure (matching
    journal_scaffold.py / closeout_finish.py) fixes it."""

    def test_reconfigure_idiom_present_at_module_top(self):
        src = SCRIPT_PATH.read_text(encoding="utf-8")
        # The exact sibling idiom: reconfigure stdout/stderr to utf-8/replace.
        assert 'reconfigure(encoding="utf-8", errors="replace")' in src

    def test_glyph_print_survives_cp1252_stream_after_reconfigure(self):
        # Reproduce the failure mode directly: a cp1252 text stream that the
        # reconfigure idiom converts to utf-8/replace must then print the audit
        # glyphs without raising (it crashed before the fix).
        import io
        stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
        # U+2713 and U+23F0 are the glyphs bd emits in orphans/stale output.
        stream.write("orphan ✓ stale ⏰")
        stream.flush()  # must not raise UnicodeEncodeError

    def test_render_todo_with_glyphs_is_encodable_utf8(self):
        # A TODO whose detail carries the bd glyphs must round-trip through utf-8
        # (what the reconfigured stream uses) without loss.
        results = [
            prep._result("beads", prep.STATUS_ATTENTION,
                         "orphans/stale", detail="✓ done  ⏰ stale"),
        ]
        out = prep.render_todo(results, prep.STATUS_ATTENTION)
        assert "✓" in out and "⏰" in out
        out.encode("utf-8")  # the reconfigured stream's codec -- must not raise
