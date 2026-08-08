"""
Deterministic spell-back audio synthesis (bd polyglot-pdf-22h1f / 44ywm).

Renders a stored field value as a NATURAL-LANGUAGE verification clip via Cloud
Text-to-Speech, OUTSIDE the Live model's speech path: "You said J, O, S, E.
Is that correct?" -- in the SESSION language, with the regional voice. The
native-audio Live model's speech head has a measured sticky-first-spelling
defect (bd polyglot-pdf-0rpu), so the model never speaks a spelling; the clip
is a deterministic function of the STORED value only (bd polyglot-pdf-h7wx).

Design (bd 44ywm, maintainer-directed 2026-08-07/08, superseding the original
SSML approach):
- PLAIN TEXT input, never SSML. Chirp 3 HD voices are LLM-based: they generate
  prosody from natural text, and SSML say-as/break markup renders mechanically
  (robotic, unevenly spaced -- the maintainer's notebook A/B proved it).
  Letters ride as a comma-separated sequence inside the frame sentence;
  measured: JOHNSON letters-only SSML 10.2s vs plain text WITH the question
  4.9s, synthesis 2.3s -> 0.9s.
- The clip carries the WHOLE verification question, so the model's post-tool
  job is to WAIT, not to ask.
- SESSION LANGUAGE (maintainer ruling): frame + voice follow the session's
  spoken language ({locale}-Chirp3-HD-{persona}); letter names come out the
  way that language's speakers say them (a Spanish speaker hears 'jota';
  languages with no native Latin-letter names -- e.g. Chinese -- naturally get
  English-style letter names from their regional voice). Locales with no
  Chirp3 voice fall back to en-US -- availability is derived from the API's
  list_voices at runtime, NEVER a hand-pinned language list (repo rule).
- Frames + per-language punctuation words are DATA (spellback_frames.json,
  UTF-8; code files stay ASCII-only).
- PII: the value is never logged here (lengths only), matching the server-side
  no-field-values policy (docs/standards/hipaa-pii-policy.md).
"""

import asyncio
import json
import threading
from pathlib import Path

import structlog

from backend.utils.language_codes import bcp47_codes_for_spoken_language

_log = structlog.get_logger()

# Hard cap on the value length accepted for synthesis. Names on the supported
# forms run well under this; a longer value is almost certainly a mis-targeted
# field (an address, a narrative). MIRRORED as SPELLBACK_MAX_CHARS in
# frontend/src/shared/spellbackPlayer.ts (client fail-fast pre-check); the two
# are pinned to each other by a static test.
MAX_SPELLBACK_CHARS = 60

_FRAMES_PATH = Path(__file__).resolve().parent / "spellback_frames.json"
_FALLBACK_LOCALE = "en-US"


def _load_frames() -> dict:
    with open(_FRAMES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    data.pop("_comment", None)
    return data


_FRAMES = _load_frames()


def resolve_spellback_locale(language_name) -> str:
    """The clip's BCP-47 locale for a spoken-language NAME ('Spanish').

    Uses the same name->code map as the ASR bias (language_codes.py). Unknown,
    empty, or unmapped names fall back to en-US.
    """
    codes = bcp47_codes_for_spoken_language(language_name)
    return codes[0] if codes else _FALLBACK_LOCALE


def build_spellback_text(value: str, locale: str) -> str:
    """The plain-text clip sentence for `value` in `locale`.

    Every character is voiced: letters/digits as themselves (the regional
    voice reads them as that language's speakers do), known punctuation as the
    locale's word for it, anything else as the en-US fallback word or -- last
    resort -- the character itself. Nothing is silently dropped: a dropped
    character would make the clip verify a DIFFERENT string than the stored
    value, the exact defect class this tool exists to eliminate.
    """
    entry = _FRAMES.get(locale) or _FRAMES[_FALLBACK_LOCALE]
    fallback_punct = _FRAMES[_FALLBACK_LOCALE]["punctuation"]
    punct = entry.get("punctuation") or {}
    parts = []
    for ch in value:
        if ch.isalnum():
            parts.append(ch.upper() if ch.isalpha() else ch)
        else:
            parts.append(punct.get(ch) or fallback_punct.get(ch) or ch)
    letters = ", ".join(parts)
    return entry["frame"].replace("{letters}", letters)


# The Cloud TTS client is created lazily and cached: construction builds a gRPC
# channel (slow), and the route calls synthesize per verification turn.
_client = None
_client_lock = threading.Lock()

# Voice-availability cache (populated from list_voices on first use; process
# lifetime). None = not yet fetched; empty set = fetch failed (fail open: use
# the derived name and let a bad one surface as a synth error -> the tool's
# error variant).
_available_voices = None
_voices_lock = threading.Lock()


def _get_client():
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                # Imported here, not at module top: google-cloud-texttospeech
                # is only needed when the spell-back flag is on, and unit
                # tests patch this factory without the package installed.
                from google.cloud import texttospeech

                _client = texttospeech.TextToSpeechClient()
    return _client


def _known_voices() -> set:
    """Cached list_voices names. Derived at runtime, never hand-pinned per
    language (repo rule: languages grow 17 -> ~90). An empty set means the
    fetch failed -- callers then fail OPEN and use the derived name.
    """
    global _available_voices
    if _available_voices is None:
        with _voices_lock:
            if _available_voices is None:
                try:
                    resp = _get_client().list_voices()
                    _available_voices = {v.name for v in resp.voices}
                except Exception as exc:
                    _log.warning("spellback_list_voices_failed",
                                 error_type=type(exc).__name__)
                    _available_voices = set()
    return _available_voices


def _voice_exists(name: str) -> bool:
    known = _known_voices()
    if not known:
        return True  # fail open: a listing blip must not force the fallback
    return name in known


def _any_chirp3_voice_for(locale: str):
    """Any Chirp 3 HD voice in `locale`, or None.

    The fallback ladder's middle rung (live probe 2026-08-08): several
    supported languages carry Chirp3 voices but NOT every persona (ru-RU has
    8 of 30, no Iapetus). Keeping the user's LANGUAGE matters far more than
    keeping the model's persona, so a persona miss drops to a different
    persona in the SAME language before it ever drops to English.
    """
    known = _known_voices()
    if not known:
        return None
    prefix = "%s-Chirp3-HD-" % locale
    candidates = sorted(n for n in known if n.startswith(prefix))
    return candidates[0] if candidates else None


def resolve_spellback_voice(settings, language_name=None):
    """The (voice_name, locale) pair for the clip.

    An explicit SPELLBACK_TTS_VOICE wins outright (full voice name; its locale
    prefix is used as the language_code). Otherwise the voice follows the
    SESSION language ({locale}-Chirp3-HD-{persona}) with the persona matched
    to the Live model's LIVE_VOICE_NAME -- the Chirp 3 HD family carries the
    Live API's prebuilt voice names, so the clip sounds like the same speaker.
    Fallback ladder, LANGUAGE-FIRST (the user's language matters more than
    the model's persona):
      1. {session-locale}-Chirp3-HD-{persona}  -- ideal: their language, our voice
      2. any Chirp3 voice in the SESSION locale -- their language, other voice
      3. the locale's default voice ("")       -- still their language
      4. en-US-Chirp3-HD-{persona}             -- only when the locale is unknown
    Inputs are .strip()ed, matching the Live adapter's own LIVE_VOICE_NAME
    handling (bd polyglot-pdf-vx0q4).
    """
    explicit = (getattr(settings, "SPELLBACK_TTS_VOICE", "") or "").strip()
    if explicit:
        # 'en-US-Chirp3-HD-Algieba' -> locale 'en-US'.
        bits = explicit.split("-")
        locale = "-".join(bits[:2]) if len(bits) >= 2 else _FALLBACK_LOCALE
        return explicit, locale

    locale = resolve_spellback_locale(language_name)
    persona = (getattr(settings, "LIVE_VOICE_NAME", "") or "").strip()
    if not persona:
        return "", locale
    candidate = "%s-Chirp3-HD-%s" % (locale, persona)
    if _voice_exists(candidate):
        return candidate, locale

    # Rung 2: keep the LANGUAGE, take another Chirp3 persona (ru-RU carries 8
    # of the 30 personas, no Iapetus -- dropping to English there would speak
    # the wrong language just to keep our voice).
    same_language = _any_chirp3_voice_for(locale)
    if same_language:
        _log.info("spellback_voice_persona_fallback",
                  wanted=candidate, using=same_language)
        return same_language, locale

    # Rung 3: no Chirp3 at all in this locale -- the locale's DEFAULT voice
    # still speaks the user's language, which beats an English clip.
    if locale != _FALLBACK_LOCALE:
        _log.info("spellback_voice_locale_default", wanted=candidate,
                  locale=locale)
        return "", locale

    fallback = "%s-Chirp3-HD-%s" % (_FALLBACK_LOCALE, persona)
    _log.info("spellback_voice_fallback", wanted=candidate, using=fallback)
    return fallback, _FALLBACK_LOCALE


def _synthesize_sync(text: str, voice_name: str, locale: str) -> bytes:
    from google.cloud import texttospeech

    voice_params = {"language_code": locale}
    if voice_name:
        voice_params["name"] = voice_name
    response = _get_client().synthesize_speech(
        input=texttospeech.SynthesisInput(text=text),
        voice=texttospeech.VoiceSelectionParams(**voice_params),
        audio_config=texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        ),
    )
    return response.audio_content


async def synthesize_spellback(value: str, settings, language_name=None) -> bytes:
    """Synthesize the verification-clip MP3 for `value` in the session language.

    Runs the blocking Cloud TTS call in a worker thread so the event loop (and
    with it the WS control channel) never blocks. Raises ValueError on an
    empty/oversized value; propagates TTS client errors to the caller (the
    route maps them to a 502 without logging the value).
    """
    if not value or not value.strip():
        raise ValueError("empty value")
    if len(value) > MAX_SPELLBACK_CHARS:
        raise ValueError("value too long")
    voice_name, locale = resolve_spellback_voice(settings, language_name)
    text = build_spellback_text(value, locale)
    audio = await asyncio.to_thread(_synthesize_sync, text, voice_name, locale)
    _log.info(
        "spellback_tts_synthesized",
        value_chars=len(value),
        audio_bytes=len(audio),
        locale=locale,
    )
    return audio
