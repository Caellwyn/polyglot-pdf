"""Light structural contract for AGENTS.md (the file OpenAI Codex reads).

AGENTS.md is prose, not code, so these are presence-checks -- they pin the
review-section invariants that, if silently deleted, would quietly make Codex's
reviews non-aggressive again (bd polyglot-pdf-nvd) or break the closeout
watcher's approval-signal contract. They are intentionally minimal: the real
validation is dogfooding (Codex reviewing the PR that changes this file). We
assert that the rules EXIST and name their key terms, not their exact wording.

Run with the backend venv (the worktree has no venv of its own):
  PYTHONPATH=. backend/.venv/Scripts/python.exe -m pytest tests/test_agents_md.py
"""
import pathlib

import pytest

AGENTS_PATH = pathlib.Path(__file__).resolve().parent.parent / "AGENTS.md"

# Codex truncates the merged instruction chain at project_doc_max_bytes (32 KiB
# default). If AGENTS.md alone approaches that, the review rules near the end risk
# being cut. Keep a margin so nested/global files can also load.
PROJECT_DOC_MAX_BYTES = 32 * 1024


@pytest.fixture(scope="module")
def text():
    assert AGENTS_PATH.exists(), "{} is missing".format(AGENTS_PATH)
    return AGENTS_PATH.read_text(encoding="utf-8")


def test_under_codex_byte_cap(text):
    # Stay well under the 32 KiB cap so the review section (late in the file) is
    # never truncated out of Codex's instruction chain.
    size = len(text.encode("utf-8"))
    assert size < PROJECT_DOC_MAX_BYTES, (
        "AGENTS.md is {} bytes, at/over the {}-byte Codex cap; split or trim "
        "so the review rules aren't truncated".format(size, PROJECT_DOC_MAX_BYTES)
    )


def test_has_review_section(text):
    assert "## If you are reviewing a PR" in text


def test_review_uses_thumbs_up_approval_signal(text):
    # The closeout watcher classifies CLEAN from the thumbs-up (+1) reaction; the
    # AGENTS.md etiquette MUST keep telling Codex to approve that way, or clean
    # reviews stop being detected (bd hrn.9).
    assert "+1" in text or "\U0001F44D" in text  # "+1" rollup key or the emoji
    assert "approv" in text.lower()


def test_aggressive_severity_section_present(text):
    # bd nvd: the redefinition of P0/P1 that makes Codex aggressive must be
    # present and name both tiers + the "aggressive" intent.
    assert "Issue severity" in text
    assert "P0" in text and "P1" in text
    assert "aggressive" in text.lower()


def test_severity_enumerates_repo_invariants(text):
    # The P1 list must keep enumerating the repo's hard invariants by name -- these
    # are the highest-value, repo-specific findings Codex would otherwise miss
    # (bd nvd). Check a representative subset by keyword.
    lo = text.lower()
    for term in ("stateless", "pii", "confirm_field", "ascii", "section",
                 "vad", "update_form_fields"):
        assert term in lo, "severity list lost the '{}' invariant".format(term)


def test_codex_commit_caveat_present(text):
    # AGENTS.md is read by Codex WHEN IT REVIEWS. It must carry the commit caveat
    # so Codex distinguishes "review me" from a direct "@codex please commit ..."
    # instruction and does not mis-route a commit request as a review (bd hrn.9).
    # (The "@codex review" trigger itself is the AUTHOR's tool -- it lives in the
    # closeout SKILL + glue, not in AGENTS.md -- so it is NOT asserted here; that
    # was a vacuous OR that passed on the wrong disjunct. Fresh-eyes PR #118 #2.)
    assert "@codex please commit" in text
