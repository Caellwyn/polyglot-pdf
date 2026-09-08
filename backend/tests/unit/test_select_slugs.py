"""mint_select_slugs / strip_trailing_code (bd polyglot-pdf-g2fpr, PR 2).

The generic minter (mint_unique_slugs) does not know two things a SELECT
needs: a label's trailing "(CODE)" must not leak into the slug, and a code
that is ALREADY a valid slug ('5') IS the value. Both live here so the
extractor (PR 2) and the migration (PR 3a) share one definition instead of
restating it -- the trap this repo keeps paying for.

ASCII only.
"""

import pytest

from backend.models.conditional_vocabulary import (
    is_valid_option_slug,
    mint_select_slugs,
    strip_trailing_code,
)


@pytest.mark.parametrize("label,expected", [
    ("Alabama (AL)", "Alabama"),
    ("Armed Forces Americas (AA)", "Armed Forces Americas"),
    ("District of Columbia (DC)", "District of Columbia"),
    ("Alabama (AL)  ", "Alabama"),            # trailing whitespace
    ("Alabama", "Alabama"),                   # nothing to strip
    ("Alabama (al)", "Alabama (al)"),         # lowercase is not a code
    ("Alabama (ALAB)", "Alabama"),            # up to 4 chars
    ("Alabama (ALABA)", "Alabama (ALABA)"),   # 5 is a word, not a code
    ("(AL) Alabama", "(AL) Alabama"),         # only TRAILING
    ("", ""),
])
def test_strip_trailing_code(label, expected):
    assert strip_trailing_code(label) == expected


def test_state_labels_mint_the_bare_name():
    slugs = mint_select_slugs(["Alabama (AL)", "Armed Forces Americas (AA)"],
                              ["AL", "AA"])
    assert slugs == ["alabama", "armed_forces_americas"]
    assert all(is_valid_option_slug(s) for s in slugs)


def test_a_code_that_is_already_a_slug_IS_the_value():
    """height_feet: '5' with label '5'. Minting from the label would invent a
    word for a number; the code is kept as the value."""
    assert mint_select_slugs(["5", "11"], ["5", "11"]) == ["5", "11"]
    # ...even when the LABEL was reworded: the kept code wins.
    assert mint_select_slugs(["five feet", "11"], ["5", "11"]) == ["5", "11"]


def test_kept_codes_are_reserved_before_minting():
    """A minted sibling cannot collide with a code kept as a value."""
    assert mint_select_slugs(["five", "Five"], ["five", "X"]) == ["five", "five_2"]


def test_duplicate_labels_get_positional_suffixes():
    assert mint_select_slugs(["Other", "Other", "Other 2"], ["A", "B", "C"]) == [
        "other", "other_2", "other_2_2"]


def test_a_missing_or_non_string_code_is_never_kept():
    assert mint_select_slugs(["Alabama (AL)", "Alaska"], [None, 7]) == ["alabama", "alaska"]


def test_length_mismatch_is_a_bug_not_a_silent_truncation():
    with pytest.raises(AssertionError):
        mint_select_slugs(["a", "b"], ["A"])


def test_reserved_slugs_are_held_before_minting():
    """The migration tool passes a field's ALREADY-v2 values as reserved."""
    assert mint_select_slugs(["Other"], ["X"], reserved=["other"]) == ["other_2"]


def test_a_kept_code_that_collides_with_a_reserved_slug_is_minted_instead():
    """Fresh-eyes (g2fpr.3): the keep fast-path handed a legacy '5' the same
    value as an already-v2 '5' in the same field. It is minted from its label."""
    assert mint_select_slugs(["Five"], ["5"], reserved=["5"]) == ["five"]
    # ...and the mint still avoids the reserved set.
    assert mint_select_slugs(["5"], ["5"], reserved=["5"]) == ["5_2"]


def test_reserved_defaults_to_nothing():
    assert mint_select_slugs(["5"], ["5"]) == ["5"]


def test_only_the_FIRST_occurrence_of_a_kept_code_is_kept():
    """Fresh-eyes round 2: two legacy options coded '5' both passed the keep
    fast-path and shared a value. Uniqueness is across the WHOLE set."""
    assert mint_select_slugs(["5", "Five North"], ["5", "5"]) == ["5", "five_north"]
    assert mint_select_slugs(["5", "5"], ["5", "5"]) == ["5", "5_2"]
