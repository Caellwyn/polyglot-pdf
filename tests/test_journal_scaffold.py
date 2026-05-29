"""Tests for scripts/journal_scaffold.py.

Module-import + monkeypatched `_run_bd_show` so no real bd call is made.
Verifies frontmatter assembly (required + optional fields), the 5 mandated
body sections, slug/filename derivation, the tags placeholder (never a
guessed tag), and the no-overwrite guard.
"""

import importlib.util
import pathlib
import sys

import pytest


SCRIPT_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "scripts" / "journal_scaffold.py"
)
spec = importlib.util.spec_from_file_location("journal_scaffold", SCRIPT_PATH)
js = importlib.util.module_from_spec(spec)
sys.modules["journal_scaffold"] = js
spec.loader.exec_module(js)


BEAD = {
    "id": "yourturn-group-nbj1",
    "title": "Swarm step 2: bd_safe.py + closeout + journal_scaffold",
}


# --- slug + suffix derivation ---

def test_slugify_basic():
    assert js._slugify("Swarm step 2: bd_safe.py") == "swarm-step-2-bd-safe-py"


def test_slugify_caps_length_on_word_boundary():
    slug = js._slugify("a " * 60)
    assert len(slug) <= 50 and not slug.endswith("-")


def test_id_suffix():
    assert js._id_suffix("yourturn-group-nbj1") == "nbj1"


# --- frontmatter assembly ---

def test_skeleton_has_required_frontmatter_and_sections():
    out = js.build_skeleton(BEAD, date="2026-05-28", sprint=None, pr=None)
    assert "date: 2026-05-28" in out
    assert "bead: yourturn-group-nbj1" in out
    assert 'title: "Swarm step 2: bd_safe.py + closeout + journal_scaffold"' in out
    # tags is a placeholder, NOT a guessed value.
    assert "tags: []" in out
    assert "docs/journal/TAGS.md" in out
    for section in ("## Trigger", "## What shipped", "## Lessons",
                    "## Doc freshness", "## Files touched"):
        assert section in out


def test_optional_sprint_and_pr_included_when_given():
    out = js.build_skeleton(BEAD, date="2026-05-28", sprint=75, pr="B.3")
    assert "sprint: 75" in out
    assert 'pr: "B.3"' in out


def test_optional_fields_omitted_when_absent():
    out = js.build_skeleton(BEAD, date="2026-05-28", sprint=None, pr=None)
    assert "sprint:" not in out
    assert "pr:" not in out


def test_title_with_quotes_does_not_break_frontmatter():
    bead = {"id": "x-1", "title": 'Fix "weird" thing'}
    out = js.build_skeleton(bead, date="2026-05-28", sprint=None, pr=None)
    assert "title:" in out and '"weird"' not in out  # double quotes downgraded


# --- file writing + guards ---

def test_writes_to_computed_path(tmp_path, monkeypatch):
    monkeypatch.setattr(js, "_run_bd_show", lambda _id: BEAD)
    monkeypatch.setattr(js, "ENTRIES_DIR", tmp_path)
    rc = js.main(["yourturn-group-nbj1", "--date", "2026-05-28"])
    assert rc == js.EXIT_OK
    written = list(tmp_path.glob("2026-05-28-bd-nbj1-*.md"))
    assert len(written) == 1
    assert "## Trigger" in written[0].read_text(encoding="utf-8")


def test_refuses_to_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(js, "_run_bd_show", lambda _id: BEAD)
    target = tmp_path / "existing.md"
    target.write_text("do not clobber", encoding="utf-8")
    rc = js.main(["yourturn-group-nbj1", "--out", str(target)])
    assert rc == js.EXIT_FAIL
    assert target.read_text(encoding="utf-8") == "do not clobber"


def test_print_mode_writes_no_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(js, "_run_bd_show", lambda _id: BEAD)
    monkeypatch.setattr(js, "ENTRIES_DIR", tmp_path)
    rc = js.main(["yourturn-group-nbj1", "--date", "2026-05-28", "--print"])
    assert rc == js.EXIT_OK
    assert list(tmp_path.glob("*.md")) == []
    assert "## Trigger" in capsys.readouterr().out


def test_bad_date_rejected(monkeypatch):
    monkeypatch.setattr(js, "_run_bd_show", lambda _id: BEAD)
    assert js.main(["yourturn-group-nbj1", "--date", "not-a-date"]) == js.EXIT_FAIL


def test_run_bd_show_no_exact_match_raises(monkeypatch):
    # bd show --json may return related context beads; if none has the exact
    # requested id, we must RAISE rather than silently use the first bead
    # (which would write a mismatched `bead:` field into the entry).
    import subprocess

    def fake_run(*a, **k):
        return subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout='[{"id": "yourturn-group-OTHER", "title": "Wrong bead"}]',
            stderr="",
        )
    monkeypatch.setattr(js.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError):
        js._run_bd_show("yourturn-group-nbj1")
