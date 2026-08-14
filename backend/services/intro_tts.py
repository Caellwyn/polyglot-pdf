"""
Scripted intro+disclaimer clip synthesis (sprint 20, bd polyglot-pdf-s1iex.3).

Synthesizes Sol's fixed intro+disclaimer script -- the canonical per-language
paragraphs[] in intro_script.json, the SAME text the disclaimer modal renders
(the sprint-20 hard invariant: modal text IS the TTS input) -- through the
spell-back TTS stack ({locale}-Chirp3-HD-{persona} voice resolution with its
three-rung fallback), for POST /api/tts/intro to return as audio/mpeg.

KEYED-ROUTE CONTRACT: callers send a bounded form-number KEY, never text.
The spoken form name comes from KNOWN_FORMS below and the agree-button label
from intro_agree_labels.json (mirrored from the frontend's
BUTTON_TRANSLATIONS, pinned by a static test) -- so no caller-supplied string
ever enters synthesis, and this authenticated endpoint cannot be used as a
general-purpose TTS synthesizer (there is no rate limiting in backend/main.py).

GAIN IS 0 dB, not the spell-back per-voice gain: +4 dB was measured on ~4s
spell-back clips and CLIPS ~90s content (raw-waveform peak 1.000, measured
2026-08-13 -- scripts/spikes/intro_duration_findings.md). The intro clip also
plays standalone, before any Live session, so the mid-conversation loudness
match that motivated the spell-back gain does not apply.

CACHE: in-process, keyed (resolved language, form number, script hash) --
18 languages x a handful of forms. A repeat request never re-synthesizes;
the ETag is derived from the cached audio bytes so it is stable for the
process lifetime. script_version() is the per-language script hash the
disclaimer-acceptance record logs (bd s1iex.7) so the audit log can answer
"which exact text did the user agree to?".

Nothing here logs PII: language names and form numbers are keys, not user
content. ASCII only in this file (scar #6); the script text lives in UTF-8
data files.
"""

import asyncio
import hashlib
import json
import threading
from pathlib import Path

import structlog

from backend.services.spellback_tts import (
    _synthesize_sync,
    resolve_spellback_voice,
)

_log = structlog.get_logger()

_STORE_PATH = Path(__file__).resolve().parent / "intro_script.json"
_LABELS_PATH = Path(__file__).resolve().parent / "intro_agree_labels.json"

# The intro clip's encode gain -- see the module docstring. Never swap in
# spellback_gain_db() here: that gain clips at this clip length.
INTRO_GAIN_DB = 0.0

# Cloud TTS synthesizeSpeech rejects input over 5000 UTF-8 bytes. The store
# is pinned under (cap - margin) by test_intro_script.py, so tripping this
# guard means the store and its tests were bypassed -- fail loudly.
SYNTH_INPUT_BYTE_CAP = 5000

# The known-form table: wire key -> spoken/displayed form name. The form name
# is deliberately IDENTICAL in every language ("Form I-90" -- what users call
# it, untranslatable-by-construction; maintainer decision in the sprint-20
# plan). Kit ids do NOT map cleanly to these ("f1040" -> "Form 1040",
# "w9-heldout" -> "Form W-9"), so this is an explicit table, not a derivation;
# adding a form kit that runs voice sessions means adding a row here.
KNOWN_FORMS = {
    "I-90": "Form I-90",
    "W-7": "Form W-7",
    "W-9": "Form W-9",
    "1040": "Form 1040",
}

FORM_PLACEHOLDER = "[FORM NUMBER]"
AGREE_PLACEHOLDER = "[AGREE LABEL]"
_FALLBACK_LANGUAGE = "English"


def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data.pop("_comment", None)
    return data


_LANGUAGES = _load_json(_STORE_PATH)["languages"]
_AGREE_LABELS = _load_json(_LABELS_PATH)


def resolve_intro_language(language_name) -> str:
    """The store's display-cased language name for a wire language name.

    Case-insensitive; unknown/empty falls back to English -- the same
    fallback the shipped disclaimer modal applies to its own translations
    (an older or odd client gets a working English clip, never an error).
    """
    if language_name:
        wanted = str(language_name).strip().casefold()
        for name in _LANGUAGES:
            if name.casefold() == wanted:
                return name
    return _FALLBACK_LANGUAGE


def script_version(language: str) -> str:
    """Hash of the language's canonical script text -- the acceptance-record
    script_version (bd s1iex.7): which exact text the user heard/read.

    Covers everything LANGUAGE-scoped that reaches the spoken/rendered text:
    the canonical paragraphs AND the language's agree label -- a label edit
    changes what the user hears, so it must change the version (fresh-eyes
    round 1: hashing only the template let intro_agree_labels.json drift
    silently under an unchanged version). The form number is deliberately
    OUTSIDE the hash: it is a per-request parameter the acceptance flow
    records separately alongside the version.
    """
    label = _AGREE_LABELS.get(language) or _AGREE_LABELS[_FALLBACK_LANGUAGE]
    joined = " ".join(_LANGUAGES[language]["paragraphs"])
    return hashlib.sha256(
        ("%s\n%s" % (joined, label)).encode("utf-8")).hexdigest()[:16]


def build_intro_text(language: str, form_number: str) -> str:
    """The exact synthesis input: canonical paragraphs joined, placeholders
    interpolated from the two server-side tables. Raises ValueError on an
    unknown form key (the route maps it to a 400)."""
    if form_number not in KNOWN_FORMS:
        raise ValueError("unknown form")
    text = " ".join(_LANGUAGES[language]["paragraphs"])
    text = text.replace(FORM_PLACEHOLDER, KNOWN_FORMS[form_number])
    label = _AGREE_LABELS.get(language) or _AGREE_LABELS[_FALLBACK_LANGUAGE]
    text = text.replace(AGREE_PLACEHOLDER, label)
    n = len(text.encode("utf-8"))
    if n > SYNTH_INPUT_BYTE_CAP:
        raise RuntimeError("intro text over synthesis byte cap")
    return text


# (language, form_number, script_version) -> (audio bytes, etag). Process
# lifetime; 18 languages x len(KNOWN_FORMS) entries at most, no eviction
# needed. First writer wins so the ETag stays stable across concurrent
# first requests.
_cache: dict = {}
_cache_lock = threading.Lock()


async def synthesize_intro(language_name, form_number: str,
                           settings) -> tuple[bytes, str]:
    """Synthesize (or serve from cache) the intro clip.

    Returns (mp3_bytes, etag). Raises ValueError on an unknown form key;
    propagates TTS client errors to the caller (the route maps them to a
    502 without logging text). All blocking work -- voice resolution
    (list_voices is a network RPC on first use) AND synthesis -- runs in a
    worker thread, same loop discipline as synthesize_spellback.
    """
    if form_number not in KNOWN_FORMS:
        raise ValueError("unknown form")
    language = resolve_intro_language(language_name)
    key = (language, form_number, script_version(language))
    with _cache_lock:
        hit = _cache.get(key)
    if hit is not None:
        return hit

    def _resolve_and_synthesize() -> bytes:
        voice_name, locale = resolve_spellback_voice(settings, language)
        text = build_intro_text(language, form_number)
        return _synthesize_sync(text, voice_name, locale,
                                gain_db=INTRO_GAIN_DB)

    audio = await asyncio.to_thread(_resolve_and_synthesize)
    etag = '"intro-%s"' % hashlib.sha256(audio).hexdigest()[:24]
    with _cache_lock:
        hit = _cache.get(key)
        if hit is None:
            hit = (audio, etag)
            _cache[key] = hit
    _log.info(
        "intro_tts_synthesized",
        language=language,
        form_number=form_number,
        # The CACHED winner's size, not this thread's draw -- under a
        # concurrent first-request race the loser's bytes are discarded.
        audio_bytes=len(hit[0]),
    )
    return hit
