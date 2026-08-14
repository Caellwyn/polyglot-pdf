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
    assert len(undertaking[0]) > 80, (
        f"{language}: the review-undertaking paragraph is suspiciously short "
        f"({len(undertaking[0])} chars) -- verify the clause survived."
    )
