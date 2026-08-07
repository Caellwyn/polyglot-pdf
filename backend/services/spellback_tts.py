"""
Deterministic spell-back audio synthesis (bd polyglot-pdf-22h1f).

Renders a stored field value as letter-by-letter audio via Cloud Text-to-Speech,
OUTSIDE the Live model's speech path. Background: the native-audio Live model's
speech head has a measured sticky-first-spelling defect -- on spelled name
read-backs it can emit a STALE name's letters while its own text track and tool
calls are correct (bd polyglot-pdf-0rpu, 9.7% of scoreable spelled read-backs on
the control arm). The fix is to never let the model speak a spelling: the client
plays this deterministic clip instead, sourced ONLY from the stored value (bd
polyglot-pdf-h7wx: a read-back must never come from the model's memory).

Design decisions (bd polyglot-pdf-22h1f, maintainer-approved sketch):
- The clip is LETTERS ONLY (no framing prose). The model provides the framing
  ("I will play the spelling back" / "is that correct?") in the session
  language with its own voice -- prose was never observed corrupted, only
  spelled letter sequences. This also avoids needing the framing phrase
  translated into 17+ session languages.
- The voice is ALWAYS en-US, matching the SI invariant that Latin letters are
  read by their ENGLISH letter names in every session language (the letters are
  exactly what is written on the English form). A session-language voice would
  read letter NAMES in that language -- or, for non-Latin-alphabet languages,
  unpredictably transliterate.
- PII: the value is never logged here (lengths only), matching the server-side
  no-field-values policy (docs/standards/hipaa-pii-policy.md).
"""

import asyncio
import threading
from xml.sax.saxutils import escape

import structlog

_log = structlog.get_logger()

# Hard cap on the value length accepted for synthesis. Names on the supported
# forms run well under this; a longer value is almost certainly a mis-targeted
# field (an address, a narrative) whose spelled clip would run past the
# coordinator's round-trip budget.
MAX_SPELLBACK_CHARS = 60

# Pause between spelled characters. Mirrors the SI's per-character read-back
# rule (distinct, deliberate pause so the user can follow one character at a
# time) -- docs/components/voice-ai.md "Spoken delivery".
_CHAR_BREAK = '<break time="400ms"/>'

# Characters that must be spoken as words, not fed to say-as (which skips or
# mangles punctuation). Keys are the literal characters; values are what the
# en-US voice says.
_SPOKEN_PUNCTUATION = {
    " ": "space",
    "-": "hyphen",
    "'": "apostrophe",
    ".": "period",
    ",": "comma",
    "/": "slash",
    "&": "ampersand",
}


def build_spellback_ssml(value: str) -> str:
    """Build the SSML for a letter-by-letter rendering of `value`.

    Every character is spoken individually: letters/digits via
    <say-as interpret-as="characters">, known punctuation as its English word,
    anything else as the word "symbol" (never silently dropped -- a dropped
    character would make the clip verify a DIFFERENT string than the stored
    value, the exact defect class this tool exists to eliminate).
    """
    parts = []
    for ch in value:
        if ch.isalnum():
            parts.append(
                '<say-as interpret-as="characters">%s</say-as>' % escape(ch)
            )
        elif ch in _SPOKEN_PUNCTUATION:
            parts.append(escape(_SPOKEN_PUNCTUATION[ch]))
        else:
            parts.append("symbol")
    body = _CHAR_BREAK.join(parts)
    # rate="85%": the spelled read-back goes distinctly slower than prose, per
    # the SI's per-character pacing rule.
    return '<speak><prosody rate="85%%">%s</prosody></speak>' % body


# The Cloud TTS client is created lazily and cached: construction builds a gRPC
# channel (slow), and the route calls synthesize per verification turn.
_client = None
_client_lock = threading.Lock()


def _get_client():
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                # Imported here, not at module top: google-cloud-texttospeech is
                # only needed when the spell-back flag is on, and unit tests
                # patch this factory without the package installed.
                from google.cloud import texttospeech

                _client = texttospeech.TextToSpeechClient()
    return _client


def _synthesize_sync(value: str, voice_name: str) -> bytes:
    from google.cloud import texttospeech

    ssml = build_spellback_ssml(value)
    voice_params = {"language_code": "en-US"}
    if voice_name:
        voice_params["name"] = voice_name
    response = _get_client().synthesize_speech(
        input=texttospeech.SynthesisInput(ssml=ssml),
        voice=texttospeech.VoiceSelectionParams(**voice_params),
        audio_config=texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        ),
    )
    return response.audio_content


async def synthesize_spellback(value: str, voice_name: str = "") -> bytes:
    """Synthesize the letter-by-letter MP3 for `value`.

    Runs the blocking Cloud TTS call in a worker thread so the event loop (and
    with it the WS control channel) never blocks. Raises ValueError on an
    empty/oversized value; propagates TTS client errors to the caller (the
    route maps them to a 502 without logging the value).
    """
    if not value or not value.strip():
        raise ValueError("empty value")
    if len(value) > MAX_SPELLBACK_CHARS:
        raise ValueError("value too long")
    audio = await asyncio.to_thread(_synthesize_sync, value, voice_name)
    _log.info(
        "spellback_tts_synthesized",
        value_chars=len(value),
        audio_bytes=len(audio),
    )
    return audio
