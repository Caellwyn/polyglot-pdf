"""Consistency contract for the review-flow rules stated in CLAUDE.md.

CLAUDE.md is tier-1 and auto-loads into EVERY session, so a stale review rule
there does not fail loudly -- it silently teaches the retired flow to every
future agent. It restates the review flow in several places (scar tissue #2, the
auto-merge condition, the "Never merge" rule, the Closeout section), and nothing
kept those statements in agreement.

That gap is not hypothetical. Landing the three-way review gate (bd
polyglot-pdf-saxh) took three fresh-eyes rounds to find THREE REAL REGRESSIONS --
each one more spot in CLAUDE.md still describing the OLD rule -- because each fix
was made per-instance and no test covered this file at all. On `origin/dev` they
are at:

  :89  -- scar tissue #2, "skip the outer review"
  :218 -- the "Never merge" rule, "skipped review under the docs-only gate"
  :470 -- the Closeout section, "changes get NO outer review"

(NB: "real regression" here means a defect that actually shipped in CLAUDE.md.
The sibling battery file numbers a DIFFERENT sequence -- later rounds in which a
reviewer defeated a draft of THIS TEST. The two numberings are unrelated; refer
to real regressions by their `origin/dev` line, and to test-defeat rounds by
their escape class.)

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
    a docs/journal/beads-only subject co-occurs with any review word, and asserts
    the set EXACTLY EQUALS a hand-reviewed allowlist. Adding such a sentence --
    in ANY phrasing, including ones nobody thought to grep for -- fails the test
    and forces a human to read it and either fix the doc or consciously allowlist
    it. That is the property worth pinning; "is this particular sentence OK?" is
    a judgment call, and this file's job is to make sure the judgment gets made.

    Two later rounds defeated weaker versions of even that design, and both
    escapes came from MATCHING rather than enumerating:

      - The enumerator originally required a denial VERB before the review noun,
        so "The adversarial Haiku review is never run for docs-only changes"
        (noun first) was never enumerated. Fixed by dropping the denial test
        entirely -- any review word now makes a sentence a candidate.
      - The allowlist originally matched by SUBSTRING, so a sentence could quote
        an allowed fragment verbatim while asserting the opposite ("Docs-only
        changes get ZERO adversarial review going forward; the older line
        '<allowed fragment>' has been superseded.") and pass. Fixed by exact
        whole-sentence equality: any edit to an allowlisted sentence, including
        appending a clause that reverses it, changes the string and re-trips.

    Consequence, by design: this test fails whenever a docs+review sentence is
    added or reworded, even correctly. That is the point -- the failure is a
    prompt to review the prose, and the message says so.

    Operate on SENTENCES, not lines: the round-3 defect wrapped mid-sentence, so
    a line-based check saw the subject and the denial on different lines.

    SCOPE, stated honestly. This catches a SENTENCE pairing a docs-only subject
    with review vocabulary, inside one paragraph. It does NOT catch a denial that
    uses no review vocabulary at all, nor one split across a paragraph break.
    Those are accepted and PINNED as known limits in
    `test_claude_md_review_flow_battery.py::UNENUMERABLE_BY_DESIGN`. The failure
    mode this exists for is DRIFT -- a maintainer updating one statement of the
    rule and missing another -- and all three real regressions (the ones listed
    in this module's docstring above, verifiable at `git show
    origin/dev:CLAUDE.md` lines 89, 218 and 470) were single in-paragraph
    sentences using ordinary review vocabulary. A prose heuristic cannot be made
    evasion-proof; every scope has an adjacent-scope escape. So it covers the
    realistic class well and NAMES the rest rather than chasing them.
    """
    # ENUMERATION half. Deliberately over-broad: any sentence mentioning the
    # docs-only change class AND containing a review word is a candidate. It does
    # NOT try to decide whether the sentence denies anything -- two drafts tried
    # and were defeated live, once by vocabulary ("bypass"), once by word order
    # ("The adversarial review is never run for docs-only changes" puts the
    # denial AFTER the noun, so a directional pattern missed it). Dropping the
    # denial test entirely removes that whole class of escape.
    subject = re.compile(
        r"docs[- ]only|journal[- ]only|`?\.?beads`?[- ]only|"
        r"docs,? (beads|journal)|prose[- ]only",
        re.IGNORECASE,
    )
    review_word = re.compile(r"review|adversarial|haiku|opus|gate", re.IGNORECASE)

    # SCOPE = the PARAGRAPH. There is deliberately no fixed sentence window.
    #
    # Splitting on ". " is unavoidably approximate -- an internal abbreviation
    # ("e.g.", "i.e.") splits one prose sentence in two -- so the subject and the
    # review word can land in different fragments. Two earlier mechanisms tried
    # to bound that gap and both were defeated: single-fragment matching (round 7
    # beat it with "e.g."), then a 2-fragment sliding window (round 8 beat THAT
    # with a three-sentence phrasing and a doubled "e.g. ... i.e." split).
    #
    # Any fixed N is the same patch-the-instance trap one increment later -- see
    # docs/standards/testing.md#change-the-mechanism. So there is no N: a
    # candidate is any subject-bearing sentence whose PARAGRAPH mentions review
    # at all. CLAUDE.md keeps one claim inside one paragraph, so the paragraph is
    # the real unit of meaning, and no sentence-splitting artifact can separate a
    # subject from its own paragraph.
    #
    # Report the SUBJECT-BEARING SENTENCE, never the whole paragraph: reporting
    # the paragraph would drag unrelated neighbouring sentences into the
    # allowlist, so editing a neighbour would churn it.
    candidates = []
    for para in re.split(r"\n\s*\n", text):
        para_flat = re.sub(r"\s+", " ", para).strip()
        if not para_flat or not review_word.search(para_flat):
            continue
        for frag in re.split(r"(?<=\.)\s+", para_flat):
            frag = frag.strip()
            if frag and subject.search(frag):
                candidates.append(frag)
    candidates = list(dict.fromkeys(candidates))

    # ALLOWLIST half: EXACT whole-sentence equality, never substring containment.
    # A substring allowlist was defeated live by a sentence that QUOTED an allowed
    # fragment verbatim while asserting the opposite ("Docs-only changes get ZERO
    # adversarial review going forward; the older line '<allowed fragment>' has
    # been superseded."). Exact equality makes that impossible: any edit to an
    # allowlisted sentence -- including appending a clause that reverses it --
    # changes the string and re-trips the test.
    #
    # Hand-reviewed 2026-08-05 (bd saxh). Each sentence below was read and
    # confirmed to state the CURRENT three-way rule. Whitespace is collapsed, so
    # copy the failure output verbatim when updating.
    ALLOWED = {
        "**Docs-only changes get ONE adversarial HAIKU review** instead "
        "(the `docs-reviewer` agent -- prose review, not a contract trace); "
        "only a genuinely TRIVIAL diff skips adversarial review entirely "
        "(fresh-eyes `NO-GAPS` is its record).",

        "**This condition means the OPUS cross-surface gate specifically** "
        "-- a docs-only PR cleared by the Haiku `docs-reviewer`, or a "
        "trivial PR with no adversarial review, does NOT satisfy it and "
        "pings (below).",

        "**Never** merge a PR whose review wasn't CLEAN, whose checks are "
        "red, or whose adversarial review was not the Opus cross-surface "
        "gate specifically (a Haiku-cleared docs-only PR, or a trivial PR "
        "with no adversarial review at all) -- those ping too.",

        "**Docs-only / `.beads`-only / journal-only changes get the cheap "
        "arm instead: ONE adversarial HAIKU review** (the `docs-reviewer` "
        "agent, same loop, prose review rather than a contract trace).",

        "- **BOTH review layers run PRE-PR, serial not parallel** (closeout "
        "Steps 5.5 + 5.6): the fresh-eyes assess loop first (scored against "
        "the bead's exit criteria, re-spawned until no gap at the routed "
        "haiku/sonnet model), THEN ONE outer adversarial pass looped until "
        "it clears -- the Opus `cross-surface-reviewer` for a source diff, "
        "or the Haiku `docs-reviewer` for a docs-only one (only a trivial "
        "diff gets neither), all on the local branch with fixes committed.",
    }
    unexpected = [s for s in candidates if s not in ALLOWED]
    assert not unexpected, (
        "CLAUDE.md sentence(s) about docs-only changes and review are new or "
        "reworded.\n\n"
        "THIS FAILURE IS EXPECTED whenever such a sentence is added or edited -- "
        "it is not necessarily a bug. The test cannot judge prose, so it asks a "
        "human to. Since bd saxh, docs-only changes get ONE Haiku "
        "`docs-reviewer` pass and ONLY genuinely trivial changes get none.\n\n"
        "READ each sentence below. If it states that rule correctly, paste it "
        "VERBATIM into this test's ALLOWED set (whitespace is collapsed, so copy "
        "from this output, not from the file). If it does not, fix CLAUDE.md.\n\n"
        "  " + "\n\n  ".join(unexpected)
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
