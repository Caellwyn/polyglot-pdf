"""Tests for scripts/pick_review_model.py (bd polyglot-pdf-hrn.4, A/B arm B).

Pins the parts the plan's verification section calls out for #2's router:
  - shortstat parsing (insertions + deletions, either side optional, empty=0);
  - the size->model mapping at and around the threshold (boundary is inclusive
    of haiku);
  - the fail-toward-capable fallback when git can't measure the diff (prints
    sonnet, exits 1);
  - the --shortstat / --threshold overrides used for synthetic shortstats.

Run with the backend venv (the worktree has no venv of its own):
  PYTHONPATH=. backend/.venv/Scripts/python.exe -m pytest tests/test_pick_review_model.py
"""
import importlib.util
import pathlib
import sys

import pytest


# Load the script as a module without running its CLI main() -- same pattern as
# tests/test_harness_ledger.py / tests/test_doc_freshness.py.
SCRIPT_PATH = (
    pathlib.Path(__file__).resolve().parent.parent / "scripts" / "pick_review_model.py"
)
spec = importlib.util.spec_from_file_location("pick_review_model", SCRIPT_PATH)
picker = importlib.util.module_from_spec(spec)
sys.modules["pick_review_model"] = picker
spec.loader.exec_module(picker)


# --------------------------------------------------------------------------- #
# Shortstat parsing
# --------------------------------------------------------------------------- #
class TestChangedLines:
    def test_insertions_and_deletions_summed(self):
        line = " 23 files changed, 2277 insertions(+), 346 deletions(-)"
        assert picker.changed_lines(line) == 2277 + 346

    def test_insertions_only(self):
        assert picker.changed_lines(" 1 file changed, 5 insertions(+)") == 5

    def test_deletions_only(self):
        assert picker.changed_lines(" 1 file changed, 3 deletions(-)") == 3

    def test_empty_is_zero(self):
        # git emits an empty string for "no changes".
        assert picker.changed_lines("") == 0
        assert picker.changed_lines("   ") == 0

    def test_files_count_ignored(self):
        # The "N files changed" number must NOT be added to the line total.
        # 2 files, 1 insertion -> 1 changed line, not 3.
        assert picker.changed_lines(" 2 files changed, 1 insertion(+)") == 1


# --------------------------------------------------------------------------- #
# Size -> model mapping
# --------------------------------------------------------------------------- #
class TestPickModel:
    def test_small_diff_picks_haiku(self):
        assert picker.pick_model(10) == "haiku"

    def test_large_diff_picks_sonnet(self):
        assert picker.pick_model(500) == "sonnet"

    def test_threshold_boundary_is_inclusive_haiku(self):
        # <= threshold -> haiku; threshold+1 -> sonnet.
        assert picker.pick_model(picker.DEFAULT_THRESHOLD) == "haiku"
        assert picker.pick_model(picker.DEFAULT_THRESHOLD + 1) == "sonnet"

    def test_zero_lines_picks_haiku(self):
        assert picker.pick_model(0) == "haiku"

    def test_custom_threshold(self):
        assert picker.pick_model(100, threshold=120) == "haiku"
        assert picker.pick_model(100, threshold=80) == "sonnet"


# --------------------------------------------------------------------------- #
# CLI: --shortstat override (no git call)
# --------------------------------------------------------------------------- #
class TestMainShortstatOverride:
    def test_small_shortstat_prints_haiku(self, capsys):
        rc = picker.main(["--shortstat", " 1 file changed, 4 insertions(+)"])
        assert rc == 0
        assert capsys.readouterr().out.strip() == "haiku"

    def test_large_shortstat_prints_sonnet(self, capsys):
        rc = picker.main(["--shortstat", " 9 files changed, 900 insertions(+), 50 deletions(-)"])
        assert rc == 0
        assert capsys.readouterr().out.strip() == "sonnet"

    def test_empty_shortstat_prints_haiku(self, capsys):
        # No diff at all -> 0 changed lines -> haiku (degenerate but well-defined).
        rc = picker.main(["--shortstat", ""])
        assert rc == 0
        assert capsys.readouterr().out.strip() == "haiku"

    def test_threshold_flag_changes_boundary(self, capsys):
        # 100 changed lines: sonnet at the default 80, haiku at a raised 120.
        stat = " 1 file changed, 100 insertions(+)"
        assert picker.main(["--shortstat", stat]) == 0
        assert capsys.readouterr().out.strip() == "sonnet"  # default threshold 80
        rc = picker.main(["--shortstat", stat, "--threshold", "120"])
        assert rc == 0
        assert capsys.readouterr().out.strip() == "haiku"

    def test_verbose_reports_count_on_stderr(self, capsys):
        rc = picker.main(["--shortstat", " 1 file changed, 7 insertions(+)", "--verbose"])
        assert rc == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "haiku"
        assert "7 changed line" in captured.err


# --------------------------------------------------------------------------- #
# CLI: git failure -> fail toward the capable model
# --------------------------------------------------------------------------- #
class TestMainGitFallback:
    def test_git_failure_prints_sonnet_and_exits_1(self, capsys, monkeypatch):
        def boom(base):
            raise RuntimeError("git diff --shortstat origin/dev...HEAD failed (exit 128): bad ref")

        monkeypatch.setattr(picker, "get_shortstat", boom)
        rc = picker.main([])  # no --shortstat -> goes through get_shortstat
        assert rc == 1
        captured = capsys.readouterr()
        # Still prints a usable model -- the SAFE (capable) one, never haiku.
        assert captured.out.strip() == "sonnet"
        assert captured.out.strip() == picker.SAFE_FALLBACK_MODEL
        assert "falling back to sonnet" in captured.err
