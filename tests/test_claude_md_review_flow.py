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


def test_every_docs_only_mention_is_allowlisted(text):
    """Enumerate the sentences that pair a docs-only subject with a denial verb.

    HOW THIS WORKS, and why it is shaped this way. Three fresh-eyes rounds each
    found one more CLAUDE.md sentence describing the retired two-way gate, so
    this file exists to stop the fourth. But two drafts of a "detect the bad
    sentence" regex were defeated in opposite directions -- one missed
    "bypass adversarial review entirely" (vocabulary narrower than English),
    the next flagged the legitimate baseline (exemption logic that swallowed
    the rule). Regexes do not parse English, and a pin that is wrong in either
    direction is worse than none: a false negative is silent, a false positive
    gets the test deleted.

    So this does NOT try to judge sentences. It ENUMERATES every sentence where
    a docs/journal/beads-only subject co-occurs with a denial verb, and asserts
    the set equals a hand-reviewed allowlist. Adding such a sentence -- in ANY
    phrasing, including ones nobody thought to grep for -- fails the test and
    forces a human to read it and either fix the doc or consciously allowlist
    it. That is the property worth pinning; "is this particular sentence OK?" is
    a judgment call, and this file's job is to make sure the judgment gets made.

    Operate on SENTENCES, not lines: the round-3 defect wrapped mid-sentence, so
    a line-based check saw the subject and the denial on different lines.
    """
    flat = re.sub(r"\s+", " ", text)
    # Denial verbs, deliberately broad. An earlier draft listed only
    # skip/no/zero/none/without and a fresh-eyes round defeated it live with
    # "bypass adversarial review entirely" -- a pin whose vocabulary is narrower
    # than English is not a pin. Prefer a false positive (loud, fixable) over a
    # false negative (silent, and the whole reason this file exists).
    denial = re.compile(
        r"\b(skips?|skipped|skipping|bypass(es|ed)?|forgo(es)?|waive[sd]?|"
        r"exempt(ed)?|excluded|omit(s|ted)?|no|not|zero|none|never|without)\b"
        r"[^.]{0,80}?"
        r"(outer review|adversarial review|review at all|review entirely|"
        r"adversarial (model )?(review|pass|look)|reviewed adversarially)",
        re.IGNORECASE,
    )
    # The subject must be the CHANGE CLASS, not an incidental path mention.
    # `docs/` alone matched citation paths ("see docs/doctrine/..."), which is a
    # false-positive source, so require the change-class phrasing.
    subject = re.compile(
        r"docs[- ]only|journal[- ]only|`?\.?beads`?[- ]only|"
        r"docs,? (beads|journal)|prose[- ]only",
        re.IGNORECASE,
    )
    offenders = []
    for sentence in re.split(r"(?<=\.)\s+", flat):
        lo = sentence.lower()
        if not subject.search(lo) or not denial.search(sentence):
            continue
        offenders.append(sentence.strip())

    # Hand-reviewed 2026-08-05 (bd saxh). Each entry was read and confirmed to
    # state the CURRENT three-way rule. Match on a distinctive fragment so
    # ordinary rewording does not churn the list, while a NEW sentence -- or a
    # rewrite that changes what one of these claims -- still trips it.
    ALLOWED = (
        # Scar tissue #2: states the Haiku arm, then scopes the denial to trivial.
        "**Docs-only changes get ONE adversarial HAIKU review** instead",
        # The Closeout section's summary of the same three-way fork.
        "the Haiku `docs-reviewer` for a docs-only one (only a trivial diff gets neither)",
        # The auto-merge condition: names what does NOT satisfy the Opus gate.
        "or a trivial PR with no",
        # The "Never merge" rule, same scoping.
        "a trivial PR with no\n   adversarial review at all",
    )
    unexpected = [s for s in offenders if not any(frag in s for frag in ALLOWED)]
    assert not unexpected, (
        "New or reworded CLAUDE.md sentence(s) pair a docs-only subject with a "
        "denial of review. Since bd saxh, docs-only changes get ONE Haiku "
        "`docs-reviewer` pass and ONLY genuinely trivial changes get none. "
        "Read each sentence below: fix the doc, or -- if it is correct -- add a "
        "fragment of it to this test's ALLOWED tuple.\n  " + "\n  ".join(unexpected)
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
