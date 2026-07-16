"""Spoken-language-name -> BCP-47 code map for ASR language biasing.

bd polyglot-pdf-y25o: system instructions steer the LLM's OUTPUT language only;
`AudioTranscriptionConfig.language_codes` biases the ASR listener itself. Without
the bias, multilingual ASR can transcribe a mumbled session-language word as a
neighboring language (es -> pt was observed live: "distrito quintal"), and the
transcription then drags the native-audio model's language auto-detect with it.

Keys mirror frontend/src/shared/languages.ts SPOKEN_LANGUAGES (the app-start
modal's choices -- the names travel the wire verbatim, per the
choice-authoritative language design). Values are the BCP-47 codes Google's
speech stack uses for those languages. A language with no reliable ASR code
(Quechua) is deliberately absent: lookup returns None and the session simply
gets no bias -- today's behavior.

This is a HINT map for an endpoint feature that is SDK-present but was not
endpoint-verified before bd y25o (docs/genai_docs/live-api-best-practices.md);
the adapter applies it only behind TRANSCRIPTION_LANGUAGE_HINT_ENABLED.
"""
from typing import List, Optional

# One primary code per supported spoken language. Regional variants chosen for
# the app's user base (US immigration intake): es-US over es-ES, pt-BR over
# pt-PT. ASCII-only (scar #6).
SPOKEN_LANGUAGE_BCP47 = {
    "english": "en-US",
    "spanish": "es-US",
    "chinese": "cmn-CN",
    "tagalog": "fil-PH",
    "arabic": "ar-XA",
    "french": "fr-FR",
    "korean": "ko-KR",
    "german": "de-DE",
    "portuguese": "pt-BR",
    "hindi": "hi-IN",
    "italian": "it-IT",
    "urdu": "ur-PK",
    "persian": "fa-IR",
    "dutch": "nl-NL",
    "ukrainian": "uk-UA",
    "swedish": "sv-SE",
    "afrikaans": "af-ZA",
    # "quechua": no Google ASR support -- intentionally unmapped (no bias).
}


def bcp47_codes_for_spoken_language(name: Optional[str]) -> Optional[List[str]]:
    """Return the transcription language_codes hint for a spoken-language name.

    Case-insensitive on the plain-English name the frontend sends ("Spanish").
    Returns a single-code list (the AudioTranscriptionConfig.language_codes
    shape), or None when the name is unknown/unset -- callers treat None as
    "apply no bias".
    """
    if not name or not isinstance(name, str):
        return None
    code = SPOKEN_LANGUAGE_BCP47.get(name.strip().lower())
    return [code] if code else None
