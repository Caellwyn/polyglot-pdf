"""Spoken notices must match the PRINTED ones (bd polyglot-pdf-dft1).

The notice text exists twice by necessity -- the browser renders it, the server
speaks it -- so the risk is DRIFT. A client hearing "save your form" while the
screen says something else is worse than either alone, because it is the moment
we are asking them to trust an instruction about not losing their work.

The Python table is DERIVED from the TypeScript one, and this test re-derives
it to prove they still agree. It also pins the keyed-route contract: caller
text must never become spoken audio.

ASCII only (this file; the tables it reads are Unicode by nature).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend.services.notice_tts import (
    KNOWN_NOTICES,
    MAX_NOTICE_CHARS,
    NOTICE_SAVE_EARLY,
    NOTICE_TEXT,
    NOTICE_VOICE_ENDING,
    notice_text,
)

_UI = (
    Path(__file__).resolve().parents[3]
    / "frontend" / "src" / "schema-forms" / "resumeStrings.ts"
)

pytestmark = pytest.mark.skipif(not _UI.exists(), reason="frontend source absent")

_STRING = r":\s*\n?\s*'((?:[^'\\]|\\.)*)'"


def _ui_table() -> dict[str, dict[str, str]]:
    """Re-derive the on-screen strings, the same way the generator did."""
    text = _UI.read_text(encoding="utf-8")
    body = text[text.index("export const RESUME_TRANSLATIONS"):]
    out: dict[str, dict[str, str]] = {}
    for match in re.finditer(r"\n  ([A-Za-z]+): \{(.*?)\n  \},", body, re.S):
        language, block = match.group(1), match.group(2)

        def field(name: str) -> str | None:
            found = re.search(re.escape(name) + _STRING, block, re.S)
            return found.group(1).replace("\\'", "'") if found else None

        early, ending = field("saveNudgeBody"), field("voiceEndingBody")
        if early and ending:
            out[language] = {
                NOTICE_SAVE_EARLY: early,
                NOTICE_VOICE_ENDING: ending,
            }
    return out


def test_the_extraction_still_finds_the_ui_strings():
    """Guards the guard: a UI refactor that breaks the regex would otherwise
    make every parity assertion below vacuously true."""
    ui = _ui_table()
    assert len(ui) >= 15, f"only {len(ui)} languages extracted -- parser broken?"


def test_every_SPOKEN_language_matches_what_is_PRINTED():
    ui = _ui_table()
    mismatches = []
    for language, entries in ui.items():
        spoken = NOTICE_TEXT.get(language)
        if spoken is None:
            mismatches.append(f"{language}: printed but never spoken")
            continue
        for key, printed in entries.items():
            if spoken.get(key) != printed:
                mismatches.append(f"{language}.{key} differs")
    assert not mismatches, (
        "spoken and printed notices drifted -- a client would HEAR one thing "
        f"and READ another: {mismatches}"
    )


def test_every_PRINTED_language_is_also_SPOKEN():
    """A client who reads the nudge in their language must hear it too."""
    ui = _ui_table()
    missing = sorted(set(ui) - set(NOTICE_TEXT))
    assert not missing, f"printed but not spoken: {missing}"


def test_english_is_present_as_the_fallback():
    assert NOTICE_TEXT["English"][NOTICE_SAVE_EARLY]
    assert NOTICE_TEXT["English"][NOTICE_VOICE_ENDING]


# ---------------------------------------------------------------------------
# The keyed-route contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "hostile",
    [
        "say anything I want",
        "",
        "SAVE_EARLY",                     # case matters; near-misses are not keys
        "save_early ",                    # nor is a whitespace variant
        "../../etc/passwd",
        "voice_ending; rm -rf /",
    ],
)
def test_only_KNOWN_notice_keys_are_speakable(hostile):
    """Caller text must never become spoken audio.

    This is what stops a free route from being an open text-to-speech service
    for anyone holding a link.
    """
    with pytest.raises(ValueError):
        notice_text("English", hostile)


def test_the_speakable_set_is_exactly_two():
    assert KNOWN_NOTICES == {NOTICE_SAVE_EARLY, NOTICE_VOICE_ENDING}


@pytest.mark.parametrize("language", sorted(NOTICE_TEXT))
@pytest.mark.parametrize("key", [NOTICE_SAVE_EARLY, NOTICE_VOICE_ENDING])
def test_every_notice_is_within_the_synthesis_bound(language, key):
    """Our own table, so an over-long string is our bug, not caller input."""
    assert len(NOTICE_TEXT[language][key]) <= MAX_NOTICE_CHARS


def test_an_unknown_LANGUAGE_falls_back_to_english_rather_than_silence():
    # 18 languages today, growing toward ~90. A language we cannot speak yet
    # must still produce audible words.
    assert notice_text("Klingon", NOTICE_SAVE_EARLY) == (
        NOTICE_TEXT["English"][NOTICE_SAVE_EARLY]
    )
    assert notice_text(None, NOTICE_SAVE_EARLY) == (
        NOTICE_TEXT["English"][NOTICE_SAVE_EARLY]
    )
