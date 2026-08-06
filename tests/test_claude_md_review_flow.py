"""Consistency contract for the review-flow rules stated in CLAUDE.md.

CLAUDE.md is tier-1 and auto-loads into EVERY session, so a stale review rule
there does not fail loudly -- it silently teaches the retired flow to every
future agent. It restates the review flow in several places (scar tissue #2, the
auto-merge condition, the "Never merge" rule, the Closeout section), and nothing
kept those statements in agreement.

That gap is not hypothetical. Landing the three-way review gate (bd
polyglot-pdf-saxh) took THREE fresh-eyes rounds, each finding one more spot in
CLAUDE.md still describing the OLD rule, because each fix was made per-instance
and no test covered this file at all:

  round 1 -> the auto-merge condition (:199)
  round 2 -> the "Never merge" rule (:223), 20 lines below the round-1 fix
  round 3 -> the Closeout section (:475), which said docs get "NO outer review"
             -- the same claim in words the earlier greps did not match

These tests pin the PROPERTY ("no statement in this file says a docs-only change
gets no adversarial review") rather than any one sentence's wording, so the next
paraphrase is caught by CI instead of by a fourth review round.

Run with the backend venv (the worktree has no venv of its own):
  PYTHONPATH=. backend/.venv/Scripts/python.exe -m pytest tests/test_claude_md_review_flow.py
"""
import pathlib
import re

import pytest

CLAUDE_PATH = pathlib.Path(__file__).resolve().parent.parent / "CLAUDE.md"


@pytest.fixture(scope="module")
def text():
    assert CLAUDE_PATH.is_file(), "CLAUDE.md must exist at the repo root"
    return CLAUDE_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def lines(text):
    return text.splitlines()


def test_names_both_outer_reviewers(text):
    # The outer slot has TWO possible agents since bd saxh. Naming only one is
    # how the Closeout section drifted for three rounds.
    assert "cross-surface-reviewer" in text, \
        "CLAUDE.md must name the Opus outer reviewer agent"
    assert "docs-reviewer" in text, \
        "CLAUDE.md must name the Haiku docs reviewer agent (bd saxh)"


def test_no_statement_says_docs_get_no_adversarial_review(text):
    """The property, stated paraphrase-independently.

    Any SENTENCE that mentions docs-only changes AND denies them a review is a
    defect, however it is phrased -- "skip", "no outer review", "gets none",
    "zero".

    Operate on SENTENCES, not lines. The round-3 defect wrapped as:

        ... Docs-only / `.beads`-only /
        journal-only / trivial changes get NO outer review.

    so a line-based check sees "docs-only" and the denial on DIFFERENT lines,
    and a naive per-line 'trivial' exemption fires on the wrapped remainder --
    which is exactly how a first draft of this test passed against the real
    historical text. Collapse whitespace first, then split on sentence ends.

    The trivial arm is the ONLY legitimate no-review case. A sentence is exempt
    only when the denial applies SOLELY to trivial changes -- i.e. it says
    "trivial" and does NOT also sweep docs/journal into the same denial.
    """
    flat = re.sub(r"\s+", " ", text)
    denial = re.compile(
        r"(skips?|skipped|no|zero|none|without)\b[^.]{0,80}?"
        r"(outer review|adversarial review|review at all|review entirely)",
        re.IGNORECASE,
    )
    subject = re.compile(r"docs-only|docs/|journal-only|`\.beads`-only", re.IGNORECASE)
    offenders = []
    for sentence in re.split(r"(?<=\.)\s+", flat):
        lo = sentence.lower()
        if not subject.search(lo) or not denial.search(sentence):
            continue
        # Exempt ONLY when the denial is scoped to trivial alone -- a sentence
        # naming docs AND trivial together in one denial is the defect, not an
        # exemption (that is precisely the round-3 wording).
        only_trivial = "trivial" in lo and not re.search(
            r"(docs-only|journal-only|`\.beads`-only|docs/)[^.]{0,40}"
            r"(/|,|and|or)?\s*trivial[^.]{0,40}(get|receive)s?\s+(no|none|zero)",
            lo,
        ) and not re.search(r"docs-only[^.]{0,60}(get|receive)s?\s+no\b", lo)
        if only_trivial:
            continue
        # Exempt explicit history ("was retired", "before bd saxh ...").
        if re.search(r"\bretired\b|\bbefore bd\b|\bused to\b|\bformerly\b", lo):
            continue
        offenders.append(sentence.strip())
    assert not offenders, (
        "CLAUDE.md sentence(s) still deny docs-only changes an adversarial "
        "review; since bd saxh they get ONE Haiku docs-reviewer pass and only "
        "TRIVIAL changes get none:\n  " + "\n  ".join(offenders)
    )


def test_auto_merge_condition_is_scoped_to_the_opus_gate(text):
    # bd saxh deliberately did NOT widen auto-merge: a Haiku-cleared docs PR
    # still pings. If this narrows to a bare "an adversarial reviewer cleared
    # it", docs PRs silently become auto-merge-eligible -- a real autonomy
    # change that is the maintainer's call, not a doc edit's side effect.
    lo = text.lower()
    assert re.search(r"opus cross-surface (gate|review) specifically", lo), \
        ("the auto-merge condition must name the OPUS gate specifically, so a "
         "Haiku-cleared docs PR does not silently become auto-merge-eligible")


def test_no_retired_multi_opus_gate(text):
    # Regression guard for bd ofh6: the retired two-independent-clearing-passes
    # gate and the guaranteed-Opus inner round must not reappear.
    lo = text.lower()
    for phrase in ("two independent", "clause 5", "final clearing round"):
        assert phrase not in lo, \
            "CLAUDE.md must not reinstate the retired multi-Opus gate: " + phrase
