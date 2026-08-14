"""Pin the canonical intro-script store to the supported-language set.

Sprint 20 (epic polyglot-pdf-s1iex, bd s1iex.2). The store
backend/services/intro_script.json is the ONE source both surfaces consume:
the modal renders its paragraphs and the TTS input is those paragraphs
joined (the hard invariant: modal text IS the spoken text). These tests are
DERIVED from SPOKEN_LANGUAGE_BCP47, never a hand-list (repo rule: the
language set is growing toward ~90; a hand-list rots silently). Adding a
language to the app without a counsel-grade script now fails here BY DESIGN
-- that gate is a recorded maintainer decision in the sprint-20 plan.

The byte cap: Cloud TTS synthesizeSpeech rejects input over 5000 UTF-8
bytes. The route interpolates [FORM NUMBER] and [AGREE LABEL] before
synthesis, so the stored text must clear the cap WITH interpolation
headroom; 200 bytes covers the longest label (~30 UTF-8 bytes) twice plus a
form number, several times over. Failure past the cap is a permanent 502
for that language only, invisible in English testing -- the reason this is
pinned per-language, not spot-checked.

ASCII only in this file (scar #6); expected values are ASCII placeholders
and the brand string, never re-typed non-ASCII glyphs (bd uov.6 lesson).
"""
import json
from pathlib import Path

import pytest

from backend.utils.language_codes import SPOKEN_LANGUAGE_BCP47

_STORE_PATH = (Path(__file__).resolve().parents[2]
               / "services" / "intro_script.json")

SYNTH_INPUT_BYTE_CAP = 5000
INTERPOLATION_MARGIN = 200

FORM_PLACEHOLDER = "[FORM NUMBER]"
AGREE_PLACEHOLDER = "[AGREE LABEL]"
BRAND = "PolyGlot Forms"

# The English master has 8 paragraphs; every translation mirrors that
# structure so the modal renders the same shape in every language.
MASTER_PARAGRAPH_COUNT = 8


def _languages() -> dict:
    with open(_STORE_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data["languages"]


def _spoken_language_names() -> set:
    return {name.casefold() for name in SPOKEN_LANGUAGE_BCP47}


def test_language_set_matches_spoken_languages():
    """Set EQUALITY with the app's language list -- both directions.

    A missing language is a user-facing gap (no intro clip); an extra one is
    dead legal copy nobody reviews. Case-insensitive: the store keys carry
    the display casing ('English'), the BCP-47 map keys are lowercase.
    """
    store_names = {name.casefold() for name in _languages()}
    assert store_names == _spoken_language_names()


@pytest.mark.parametrize("language", sorted(_languages()))
def test_script_under_synthesis_byte_cap(language):
    joined = " ".join(_languages()[language]["paragraphs"])
    n = len(joined.encode("utf-8"))
    assert n <= SYNTH_INPUT_BYTE_CAP - INTERPOLATION_MARGIN, (
        "%s script is %d UTF-8 bytes; cap %d minus %d interpolation margin"
        % (language, n, SYNTH_INPUT_BYTE_CAP, INTERPOLATION_MARGIN))


@pytest.mark.parametrize("language", sorted(_languages()))
def test_placeholders_intact(language):
    """The route interpolates by placeholder -- a translation that lost or
    translated a placeholder ships a clip with a literal bracket-token (or
    no form name at all) in that language only."""
    joined = " ".join(_languages()[language]["paragraphs"])
    assert joined.count(FORM_PLACEHOLDER) == 1, language
    assert joined.count(AGREE_PLACEHOLDER) == 2, language


@pytest.mark.parametrize("language", sorted(_languages()))
def test_brand_never_translated(language):
    """Three brand mentions per script (two liability clauses + the release
    clause). A dropped mention is a dropped legal element in that language."""
    joined = " ".join(_languages()[language]["paragraphs"])
    assert joined.count(BRAND) == 3, language


@pytest.mark.parametrize("language", sorted(_languages()))
def test_paragraph_structure(language):
    paragraphs = _languages()[language]["paragraphs"]
    assert len(paragraphs) == MASTER_PARAGRAPH_COUNT, language
    assert all(isinstance(p, str) and p.strip() for p in paragraphs), language


@pytest.mark.parametrize("language", sorted(_languages()))
def test_paragraphs_is_the_only_content_key(language):
    """Pin the shape: ONE canonical text per language. A reintroduced
    fullText (the pre-sprint-20 modal-vs-spoken drift bug) fails here."""
    assert set(_languages()[language].keys()) == {"paragraphs"}, language


# The undertaking paragraph is TWO clauses: (a) the applicant agrees to REVIEW
# the document (themselves and with a certified professional), and (b) they
# absolve the brand of liability. Only (a) is the legal-posture element that
# docs/standards/confirmation-and-audit.md's "Undertaken" register rests on --
# (b) is a separate liability release that test_brand_never_translated covers.
#
# CALIBRATED FLOOR, not a guess: the shortest real undertaking paragraph is
# Chinese at 89 chars (CJK packs more meaning per character); the next shortest
# is Korean at 142. A drop of clause (a) removes roughly 40-55% of the
# paragraph in every language measured. 80 is set just under the true minimum
# so a genuine translation never trips it, while a release-only rewrite -- which
# in the Latin-script languages lands at 120-235 chars -- is caught by the
# ENGLISH anchor below rather than by length alone.
_MIN_UNDERTAKING_CHARS = 80
# Floor under the measured 0.93 minimum (French), with headroom for
# legitimate re-wording. Re-measure if a language is added.
_MIN_UNDERTAKING_RATIO = 0.80

# ABSOLUTE per-language baseline, in characters, measured from the shipped
# file. The ratio guard above has an in-document denominator (paragraph 5),
# and paragraph 5 is ITSELF a review statement -- so an editorial pass that
# shortens the review language would plausibly touch paragraphs 5 and 6
# TOGETHER, and the ratio recovers while the undertaking is gone. Demonstrated:
# a Korean release-only paragraph at 81 chars with paragraph 5 trimmed to 95
# gives ratio 0.85 and sails past the ratio guard (bd polyglot-pdf-brd1q).
#
# An absolute floor cannot be defeated that way -- there is nothing in the
# document to move. 0.75x the shipped length leaves generous room for genuine
# re-wording while a dropped clause (40-55% of the paragraph) lands far below.
# REGENERATE these when a language is added or the script is legitimately
# rewritten; do not hand-edit a single entry to make a failure go away.
_SHIPPED_UNDERTAKING_CHARS = {
    "Afrikaans": 282,
    "Arabic": 177,
    "Chinese": 89,
    "Dutch": 296,
    "English": 238,
    "French": 253,
    "German": 327,
    "Hindi": 247,
    "Italian": 271,
    "Korean": 142,
    "Persian": 223,
    "Portuguese": 257,
    "Russian": 252,
    "Spanish": 250,
    "Swedish": 275,
    "Tagalog": 309,
    "Ukrainian": 256,
    "Urdu": 269,
}
_UNDERTAKING_SHRINK_TOLERANCE = 0.75

# The English source text is NOT translated, so it can be asserted verbatim.
# This is the guard that actually pins clause (a): an adversarial mutation that
# keeps both markers, keeps the release, and stays long (the realistic shape of
# a translation-sweep loss) passes a structural check but fails this one.
_EN_REVIEW_CLAUSE = "you agree to review the completed document"
_EN_PROFESSIONAL = "certified professional"


def test_english_undertaking_states_the_REVIEW_clause_verbatim():
    """The English undertaking must literally state the review agreement.

    English is the source language and is not translated, so the exact clause
    is assertable. This is the anchor the per-language structural test cannot
    provide: it pins that the paragraph promises REVIEW, not merely that a
    paragraph carrying the agree-placeholder and the brand exists.

    Caught a real weakness in the first version of this file's undertaking
    test: rewriting a paragraph to keep the agree-placeholder, the brand, and
    a plausible length while DROPPING "agrees to review ... with a certified
    professional" left that test green. This one goes red.
    """
    paragraphs = _languages()["English"]["paragraphs"]
    undertaking = [
        p for p in paragraphs if AGREE_PLACEHOLDER in p and BRAND in p
    ]
    assert len(undertaking) == 1, "English: expected one undertaking paragraph"
    text = undertaking[0]
    assert _EN_REVIEW_CLAUSE in text, (
        "The English undertaking no longer states that the applicant agrees to "
        "REVIEW the completed document. That clause is the 'Undertaken' "
        "register in docs/standards/confirmation-and-audit.md -- the liability "
        "release alone does not carry it."
    )
    assert _EN_PROFESSIONAL in text, (
        "The English undertaking no longer names a CERTIFIED PROFESSIONAL. "
        "Self-review alone is a materially weaker undertaking and changes the "
        "legal posture the deferral language depends on."
    )


@pytest.mark.parametrize("language", sorted(_languages()))
def test_review_undertaking_paragraph_survives_translation(language):
    """The REVIEW UNDERTAKING must survive into every language.

    The legal posture (docs/standards/confirmation-and-audit.md, "The
    deployment invariant") rests on three DIFFERENT registers, and this one is
    the strongest user-facing element: the applicant AGREES to obtain review
    ("you agree to review the completed document yourself and with a certified
    professional before filing"), where the written DisclaimerModal only
    ADVISES it. It is the clause the [AGREE LABEL] click records consent to.

    A translation that dropped or softened this paragraph would ship a language
    in which the applicant never undertook review at all -- invisible, because
    every other test here (placeholder counts, brand counts, paragraph count)
    would still pass. Pinned structurally rather than by wording, since the
    text is genuinely translated: the undertaking lives in the paragraph that
    carries BOTH agree-placeholders' first occurrence and the brand release,
    so assert that paragraph exists and is substantive in every language.
    """
    paragraphs = _languages()[language]["paragraphs"]
    # The undertaking paragraph is the one carrying an AGREE placeholder AND
    # the brand (the "you agree to review ... and absolve <BRAND>" clause).
    undertaking = [
        p for p in paragraphs
        if AGREE_PLACEHOLDER in p and BRAND in p
    ]
    assert len(undertaking) == 1, (
        f"{language}: expected exactly ONE paragraph carrying both the agree "
        f"placeholder and the brand (the review undertaking + liability "
        f"release); found {len(undertaking)}. A translation that split or "
        f"dropped that clause changes the legal posture for this language "
        f"only -- see docs/standards/confirmation-and-audit.md."
    )
    # Substantive, not a stub: the English clause is ~230 chars; a translation
    # that collapsed to just the placeholder would pass a bare truthiness check.
    # SCRIPT-INDEPENDENT two-clause guard. An absolute floor is weak: it must
    # clear Chinese (89 chars) so it cannot catch a Latin-script paragraph that
    # lost a clause and still runs 120-235 chars. Measuring the undertaking
    # against THIS LANGUAGE'S OWN paragraph 5 removes the script variable --
    # both shrink together in a dense script. Measured across all 18 languages
    # the ratio sits in 0.93-1.31 (min French 0.93, max Chinese 1.31); dropping
    # either clause takes roughly 40-55% out of the numerator and lands far
    # below the floor.
    #
    # A per-language LEXICAL check was tried and rejected: matching shared
    # "certified professional" vocabulary against paragraph 5 works in 16 of 18
    # languages but returns zero tokens for Chinese and Korean, which do not
    # space-delimit words. A guard that is green for 16 and structurally blind
    # for 2 is worse than an honest one -- it would read as full coverage.
    para5 = paragraphs[5]
    ratio = len(undertaking[0]) / len(para5)
    assert ratio >= _MIN_UNDERTAKING_RATIO, (
        f"{language}: the undertaking paragraph is {ratio:.2f}x this language's "
        f"paragraph 5, below the {_MIN_UNDERTAKING_RATIO} floor (observed range "
        f"across all 18 languages: 0.93-1.31). That is the signature of a "
        f"DROPPED CLAUSE -- most likely the review undertaking, leaving only the "
        f"liability release. See docs/standards/confirmation-and-audit.md."
    )
    baseline = _SHIPPED_UNDERTAKING_CHARS.get(language)
    assert baseline is not None, (
        f"{language}: no shipped-length baseline. A language was added -- "
        f"regenerate _SHIPPED_UNDERTAKING_CHARS from intro_script.json."
    )
    assert len(undertaking[0]) >= baseline * _UNDERTAKING_SHRINK_TOLERANCE, (
        f"{language}: the undertaking paragraph is {len(undertaking[0])} chars "
        f"against a shipped baseline of {baseline}. Below "
        f"{_UNDERTAKING_SHRINK_TOLERANCE:.0%} of the shipped length is the "
        f"signature of a DROPPED CLAUSE. Unlike the ratio guard above, this "
        f"cannot be masked by editing a neighbouring paragraph in the same "
        f"pass (bd polyglot-pdf-brd1q)."
    )
    assert len(undertaking[0]) >= _MIN_UNDERTAKING_CHARS, (
        f"{language}: the review-undertaking paragraph is suspiciously short "
        f"({len(undertaking[0])} chars) -- verify the clause survived."
    )
