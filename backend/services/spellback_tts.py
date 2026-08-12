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
import os
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

# Loudness leveling against the Live model's voice (bd polyglot-pdf-9oejl).
# The two audio paths are different systems -- the model's PCM plays through
# the Web Audio context, the clip is an MP3 in an HTMLAudioElement -- and
# nothing normalized one against the other, so the clip landed ~5 dB quieter
# and sounded odd mid-conversation. The client-side lever cannot fix it
# (HTMLAudioElement.volume only ATTENUATES, and it is already at 1.0), so the
# leveling happens in the ENCODE.
#
# THE RIGHT GAIN IS PER-VOICE -- measured, never derived. Reproduce with:
#   SPELLBACK_TTS_VOICE={locale}-Chirp3-HD-{persona} \
#     backend/.venv/Scripts/python.exe scripts/spikes/measure_spellback_loudness.py
# against a model median speech-gated RMS of 0.1487 (63 real Gemini dumps):
#
#   Iapetus (2026-08-10):  +0 dB -> 57%   +6 dB -> 89%   +7 dB -> 99% peak 0.696
#   Algieba (2026-08-11):  +0 dB -> 72%   +4 dB -> 92% peak 0.975
#                          ...but +6 dB CLIPS (peak 1.025) and +7 dB hits 111%
#
# Two traps this table exists to stop:
#   1. volume_gain_db is NOT a clean linear boost -- a 5 dB deficit is not
#      closed by +5 dB.
#   2. VOICES DIFFER IN BASE LOUDNESS. Algieba starts 15 points louder than
#      Iapetus, so Iapetus's +7.0 would drive it past full scale and CLIP --
#      audibly worse than the quiet clip this leveling was added to fix.
# Chirp3 is also GENERATIVE, so the same text varies a few percent run to run;
# never trust a single earlier reading. Re-run the script whenever the voice
# changes, and confirm BY EAR (perceived loudness is not RMS).
#
# The gain is DERIVED FROM THE PERSONA, not configured beside it. An earlier
# revision made it a separate env knob; fresh-eyes round 1 pointed out that the
# override path this created is exactly how the pair drifts -- an operator who
# swaps LIVE_VOICE_NAME on Cloud Run without also setting the gain ships a
# mismatch that no test, log, or startup check can see (the unit test only pins
# the compile-time defaults). Looking the gain up BY VOICE makes that
# impossible by construction rather than by discipline.
#
# An unmeasured persona falls back to the CONSERVATIVE end of the table, never
# to the loudest measured value: too quiet is the defect we started with, but
# too loud CLIPS, which is worse and irreversible in the encode.
_MEASURED_GAIN_DB = {
    "Algieba": 4.0,
    "Iapetus": 7.0,
}
_UNMEASURED_PERSONA_GAIN_DB = min(_MEASURED_GAIN_DB.values())


def spellback_gain_db(voice_name: str) -> float:
    """The measured volume_gain_db for the persona in `voice_name`.

    `voice_name` is a full Cloud TTS voice ("en-US-Chirp3-HD-Algieba") or ""
    (the locale's default voice, whose loudness is unmeasured). An explicit
    SPELLBACK_VOLUME_GAIN_DB still wins -- it is the escape hatch for tuning a
    new voice by ear before its measurement lands in the table.
    """
    override = (os.getenv("SPELLBACK_VOLUME_GAIN_DB", "") or "").strip()
    if override:
        try:
            return float(override)
        except ValueError:
            # Log the LENGTH, never a field named `value` -- the no-PII sweep
            # (test_no_pii_logging) bans that shape in backend logs outright,
            # and an operator-set env var is not worth carving an exception
            # into a privacy guard for. The env var name in the event is
            # enough to find the typo.
            _log.warning("spellback_gain_override_not_a_number",
                         chars=len(override))
    persona = voice_name.rsplit("-", 1)[-1] if voice_name else ""
    if persona in _MEASURED_GAIN_DB:
        return _MEASURED_GAIN_DB[persona]
    _log.info("spellback_gain_unmeasured_persona",
              persona=persona or "(locale default)",
              using_db=_UNMEASURED_PERSONA_GAIN_DB)
    return _UNMEASURED_PERSONA_GAIN_DB

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
    the model's persona). Every rung keeps the SESSION locale -- an unknown
    language already resolved to en-US upstream, so there is no separate
    English rung to fall to:
      1. {session-locale}-Chirp3-HD-{persona}  -- ideal: their language, our voice
      2. any Chirp3 voice in the SESSION locale -- their language, other voice
      3. the locale's default voice ("")       -- their language, always valid
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

    # Rung 3: no Chirp3 voice in this locale at all -- fall back to the
    # locale's DEFAULT voice. Unconditional (fresh-eyes round 2): an empty
    # voice name is ALWAYS valid, whereas the old English-persona rung, when
    # the locale already WAS en-US, rebuilt the exact name rung 1 had just
    # proven nonexistent -- 502ing every clip instead of degrading. Keeping
    # the locale also keeps the user's language on the non-English path.
    _log.info("spellback_voice_locale_default", wanted=candidate, locale=locale)
    return "", locale


def _synthesize_sync(text: str, voice_name: str, locale: str) -> bytes:
    from google.cloud import texttospeech

    voice_params = {"language_code": locale}
    if voice_name:
        voice_params["name"] = voice_name
    response = _get_client().synthesize_speech(
        input=texttospeech.SynthesisInput(text=text),
        voice=texttospeech.VoiceSelectionParams(**voice_params),
        audio_config=texttospeech.AudioConfig(
            # Derived from the voice ACTUALLY resolved (which may be a
            # fallback persona, not LIVE_VOICE_NAME's) -- the gain follows the
            # voice that will speak, never a stale pairing.
            volume_gain_db=spellback_gain_db(voice_name),
            audio_encoding=texttospeech.AudioEncoding.MP3
        ),
    )
    return response.audio_content


async def synthesize_spellback(value: str, settings, language_name=None) -> bytes:
    """Synthesize the verification-clip MP3 for `value` in the session language.

    Runs ALL blocking work in a worker thread so the event loop (and with it
    every concurrent WS session's control channel) never blocks. That includes
    voice RESOLUTION, not just synthesis: the ladder's first call per process
    fetches list_voices, a network RPC -- resolving it on the loop would stall
    every session for its duration, the exact defect class bd 4hnyq fixes on
    the handshake path (Opus cross-surface review). Raises ValueError on an
    empty/oversized value; propagates TTS client errors to the caller (the
    route maps them to a 502 without logging the value).
    """
    if not value or not value.strip():
        raise ValueError("empty value")
    if len(value) > MAX_SPELLBACK_CHARS:
        raise ValueError("value too long")

    def _resolve_and_synthesize():
        voice_name, locale = resolve_spellback_voice(settings, language_name)
        text = build_spellback_text(value, locale)
        return _synthesize_sync(text, voice_name, locale), locale

    audio, locale = await asyncio.to_thread(_resolve_and_synthesize)
    _log.info(
        "spellback_tts_synthesized",
        value_chars=len(value),
        audio_bytes=len(audio),
        locale=locale,
    )
    return audio
