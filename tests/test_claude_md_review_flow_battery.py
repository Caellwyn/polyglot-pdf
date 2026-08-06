"""Adversarial battery against test_every_docs_only_mention_is_allowlisted.

Every entry here defeated an earlier draft of that test. Kept as one battery so a
mechanism change is re-verified against ALL prior escapes at once, per
docs/standards/testing.md#change-the-mechanism.

  round 4 -- "bypass ... entirely"                     (verb vocabulary)
  round 5 -- ONE->NO in the load-bearing sentence      (literal-infix noun)
  round 6 -- noun-first word order                     (directional pattern)
  round 6 -- quoting an allowed fragment while reversing it (substring allowlist)
  round 7 -- "e.g." mid-sentence split                 (sentence-splitter)
"""
import importlib.util
import pathlib

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "_pin", _HERE / "test_claude_md_review_flow.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

BASE = (_HERE.parent / "CLAUDE.md").read_text(encoding="utf-8")
ALLOWED_FRAG = "**Docs-only changes get ONE adversarial HAIKU review** instead"
# Insert mid-document, not at EOF: a round-7 finding showed EOF appends can be
# caught coincidentally (the unterminated tail merges into one fragment), which
# would give a false sense that the enumeration is robust.
ANCHOR = "## Critical rules"


def flagged(txt):
    """True when the pin rejects `txt` (i.e. it caught something)."""
    try:
        mod.test_every_docs_only_mention_is_allowlisted(txt)
        return False
    except AssertionError:
        return True


def inject_mid(sentence):
    assert ANCHOR in BASE, "anchor missing from CLAUDE.md"
    return BASE.replace(ANCHOR, sentence + "\n\n" + ANCHOR, 1)




# Every phrasing below defeated an earlier draft of the pin. They are kept as
# ONE parametrized battery so that changing the mechanism re-verifies against
# ALL prior escapes at once, rather than only against the newest one.
REGRESSIONS = [
    # round 4 -- verb vocabulary
    "Docs-only, beads-only, and journal-only diffs bypass adversarial review entirely.",
    "Journal-only edits proceed without an adversarial review, unlike trivial one-liners.",
    "Docs-only / `.beads`-only / journal-only / trivial changes get NO outer review.",
    "Docs only changes skip the outer review.",
    "Docs-only PRs are excluded from adversarial review.",
    "Journal-only changes never receive an adversarial review.",
    "Docs-only diffs are exempt from adversarial review.",
    "Prose-only PRs forgo the adversarial review.",
    "Docs-only work waives the adversarial review requirement.",
    "Docs-only PRs are excused from the adversarial Haiku review.",
    # round 5 -- model-name infix between adjective and noun
    "Docs-only changes get no adversarial Sonnet pass.",
    # round 6 -- noun-first word order (denial AFTER the reviewed noun)
    "The adversarial Haiku review is never run for docs-only changes, contrary to earlier plans.",
    "The Haiku docs-reviewer pass is not required for docs-only changes anymore.",
    "For docs-only changes the adversarial review step is entirely optional.",
    # round 6 -- quote an allowlisted fragment verbatim while reversing it
    "Docs-only changes get ZERO adversarial review going forward; the older draft line "
    "'" + ALLOWED_FRAG + "' has been superseded.",
    # round 7 -- an abbreviation period splits subject from review word
    "Lightweight changes to docs-only surfaces (e.g. journal edits) never receive an "
    "adversarial pass.",
    "Docs-only diffs (i.e. prose, beads, journal) skip the adversarial review.",
    # round 8 -- the subject and the review word land MORE than one fragment
    # apart, defeating any fixed-size sentence window. This is why the scope is
    # the PARAGRAPH rather than an N-sentence slide.
    "Docs-only changes are handled specially. They go through a lightweight path. "
    "No adversarial pass applies to them, by the way, at all, ever.",
]

# KNOWN LIMITS, deliberately not "fixed" -- see the scope note below.
#
# This pin catches a SENTENCE that pairs a docs-only subject with review
# vocabulary, within one paragraph. Two shapes fall outside that and are accepted:
#
#   1. NO REVIEW VOCABULARY at all ("...never get a look from anyone"). Widening
#      `review_word` toward every synonym for "look at" restarts the
#      patch-the-instance trap AND makes the pin so broad that every docs
#      paragraph is a candidate -- which is how such tests get deleted.
#   2. SPLIT ACROSS PARAGRAPHS -- topic sentence in one paragraph, the denial in
#      the next ("...handled by a separate path.\n\nThat path involves no
#      adversarial review step."). Widening to N paragraphs is the same tuned
#      constant that already failed at N sentences (rounds 7, 8).
#
# WHY ACCEPTING THEM IS THE RIGHT CALL, and not just fatigue: the failure mode
# this pin exists for is DRIFT -- a maintainer updating one statement of the rule
# and missing another. All THREE real regressions it was built from (visible at
# `git show origin/dev:CLAUDE.md` lines 89, 218 and 470) were single
# sentences inside one paragraph, using ordinary review vocabulary, because
# someone editing this rule is by definition describing the review flow. Both
# shapes above were constructed by an adversarial reviewer *trying* to evade the
# check; neither has ever occurred naturally. A prose heuristic cannot be made
# evasion-proof -- each scope has an adjacent-scope escape -- so the honest design
# is to cover the realistic class well and PIN the rest as known.
#
# Each limit is a test below: if one ever closes, that test fails and tells the
# reader what to check. A known limit with a test is a reviewed decision; the same
# limit in a comment is a hole the next round rediscovers.
UNENUMERABLE_BY_DESIGN = [
    # no review vocabulary at all
    "Docs-only edits (e.g. journal notes, i.e. prose) never get a look from anyone.",
    # subject and denial split across a paragraph break
    "Docs-only and journal-only changes are handled by a separate path.\n\n"
    "That path involves no adversarial review step of any kind.",
]

REVERSALS = [
    ("ONE->NO", "get ONE adversarial HAIKU review", "get NO adversarial HAIKU review"),
    ("ONE->ZERO", "get ONE adversarial HAIKU review", "get ZERO adversarial HAIKU review"),
]

LEGITIMATE = [
    ("citation-path", "See docs/doctrine/review-flow.md for the full rules."),
]


@pytest.mark.parametrize("label,old,new", REVERSALS, ids=[r[0] for r in REVERSALS])
def test_in_place_reversal_is_caught(label, old, new):
    """Reversing the real load-bearing sentence must fail the pin."""
    mutated = BASE.replace(old, new, 1)
    assert mutated != BASE, "mutation did not apply -- a green result would be meaningless"
    assert flagged(mutated), \
        "reversing '{}' -> '{}' slipped past the pin".format(old, new)


@pytest.mark.parametrize("sentence", REGRESSIONS)
def test_regression_phrasing_is_caught(sentence):
    """Each phrasing that defeated an earlier draft must now be caught."""
    mutated = inject_mid(sentence)
    assert mutated != BASE, "injection did not apply"
    assert flagged(mutated), "this phrasing escaped the pin: " + sentence


def test_baseline_passes():
    """The real, unmodified CLAUDE.md must pass -- else the pin cries wolf."""
    assert not flagged(BASE), (
        "the pin fails on the CURRENT CLAUDE.md; regenerate its ALLOWED set "
        "from the real text rather than hand-editing it"
    )


@pytest.mark.parametrize("label,sentence", LEGITIMATE, ids=[c[0] for c in LEGITIMATE])
def test_legitimate_sentence_does_not_trip(label, sentence):
    assert not flagged(inject_mid(sentence)), \
        "false positive on a legitimate sentence: " + sentence


@pytest.mark.parametrize("sentence", UNENUMERABLE_BY_DESIGN)
def test_known_limit_still_holds(sentence):
    """Pin the ACCEPTED limit so it stays a decision, not a silent hole.

    A denial phrased with no review vocabulary cannot be enumerated. If this
    test starts FAILING, the limit was closed -- good news, but check HOW: if
    `review_word` was widened toward "look/see/examine/touch", confirm the pin
    did not become noise (every docs paragraph a candidate), which is how these
    pins get deleted. Then move this case into REGRESSIONS.
    """
    assert not flagged(inject_mid(sentence)), (
        "the known limit no longer holds -- see this test's docstring before "
        "celebrating: " + sentence
    )
