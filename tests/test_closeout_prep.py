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
            if args[:2] == ["status", "--short"]:
                return _cp(0, stdout="")  # clean
            if args[0] == "log":
                return _cp(0, stdout="abc123 some commit\n")  # one ahead
            return _cp(0)
        monkeypatch.setattr(prep, "_git", fake_git)
        r = prep.check_preconditions(pathlib.Path("/wt"), "origin/dev")
        assert r["status"] == prep.STATUS_OK
        assert "1 commit(s) ahead" in r["summary"]

    def test_dirty_tree_is_attention(self, monkeypatch):
        def fake_git(args, cwd=None):
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
