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
