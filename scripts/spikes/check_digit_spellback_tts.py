"""TTS-only live check for the digit read-back clip (bd polyglot-pdf-r3ham.26).

Exit criterion 3: synthesize a DIGIT clip in several session languages through
the PRODUCTION path (resolve_spellback_voice(..., for_digits=True) ->
build_spellback_text -> _synthesize_sync, MP3 + the real per-voice gain), then
have Cloud Speech-to-Text IN THAT LANGUAGE transcribe it. Two measurements,
because STT alone cannot answer the question (first run, 2026-11-21):

  SEPARATE TOKENS -- measured on the WAVEFORM, not on STT. Cloud STT applies
    inverse text normalization: a fast run of spoken digit words comes back
    as one numeral ("cinco, cero, tres" -> "503"), and it merges repeats
    ("5, 5, 5" -> "5 5"), so a transcript cannot distinguish separate digits
    from one multi-digit number. Instead the digit slot exactly as the clip
    renders it ("5, 0, 3, ...") is synthesized as LINEAR16 with the same voice
    and the voiced segments are counted (a segment ends after >=120 ms of
    silence). PASS = exactly one segment per digit.
  LANGUAGE -- measured by STT in the session language on the production MP3
    clip. PASS = no English digit word recognized and at least 80% of the
    digits recovered in order. An English voice heard by another language's
    recognizer comes back as transliterated English words (ur-IN STT on an
    English clip: "five zero" in Urdu script), not as that language's digits.

Also runs the NEGATIVE leg at zero cost: languages whose locale lists no TTS
voice (or that are unmapped) must raise SpellbackLanguageUnavailable before
any synthesis -- never an English digit clip.

NO Live-model (Gemini) spend. Cost: Cloud TTS Chirp 3 HD ~$30 / 1M chars
(~60 chars per clip) + Cloud STT v1 standard $0.024/min billed in 15 s
increments (one request per clip). The script prints its estimate and refuses
to spend without --yes.

Credentials: ADC. TTS and STT need a quota project for user ADC; set
GOOGLE_CLOUD_QUOTA_PROJECT (defaults to GOOGLE_CLOUD_PROJECT).

Usage (repo root, backend venv):
  PYTHONPATH=. backend/.venv/Scripts/python.exe \
      scripts/spikes/check_digit_spellback_tts.py --yes \
      [--languages Spanish Chinese Russian] [--value 5035550297]

The value is SYNTHETIC (no PII). Transcripts are printed ascii()-escaped so a
cp1252 console never crashes (scar #6); the UTF-8 report goes to --out.
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path

TTS_USD_PER_CHAR = 30.0 / 1_000_000   # Chirp 3 HD list price
STT_USD_PER_15S = 0.024 / 4            # v1 standard, 15 s increments
# Generous upper bound on one clip's length (frame + 10 digits ~ 6-9 s).
_CLIP_SECONDS_BOUND = 15

# Cloud STT v1 language codes differ from TTS for Mandarin only (among the
# languages this spike defaults to). A probe-local map, not product data.
_STT_CODE = {"cmn-CN": "cmn-Hans-CN"}

_ENGLISH_DIGIT_WORDS = {"zero", "oh", "one", "two", "three", "four", "five",
                        "six", "seven", "eight", "nine"}


def _ensure_quota_project() -> None:
    if not os.environ.get("GOOGLE_CLOUD_QUOTA_PROJECT"):
        proj = os.environ.get("GOOGLE_CLOUD_PROJECT")
        if proj:
            os.environ["GOOGLE_CLOUD_QUOTA_PROJECT"] = proj


def _stt(audio_mp3: bytes, locale: str) -> dict:
    from google.cloud import speech_v1p1beta1 as speech

    client = speech.SpeechClient()
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.MP3,
        sample_rate_hertz=24000,
        language_code=_STT_CODE.get(locale, locale),
        enable_automatic_punctuation=True,
        enable_word_time_offsets=True,
        model="default",
    )
    resp = client.recognize(config=config,
                            audio=speech.RecognitionAudio(content=audio_mp3))
    texts, words, confs = [], [], []
    for result in resp.results:
        if not result.alternatives:
            continue
        alt = result.alternatives[0]
        texts.append(alt.transcript)
        confs.append(alt.confidence)
        words.extend(w.word for w in alt.words)
    return {"text": " ".join(t.strip() for t in texts).strip(),
            "words": words,
            "confidence": round(min(confs), 3) if confs else 0.0}


def _lcs_len(a: str, b: str) -> int:
    prev = [0] * (len(b) + 1)
    for ch in a:
        cur = [0]
        for j, other in enumerate(b):
            cur.append(prev[j] + 1 if ch == other else max(prev[j + 1], cur[j]))
        prev = cur
    return prev[-1]


def _count_voiced_segments(pcm16: bytes, rate: int = 16000) -> list:
    """Durations (s) of voiced segments in 16-bit mono PCM; a segment closes
    after >=120 ms below 6% of the peak 10 ms RMS."""
    import array

    samples = array.array("h", pcm16)
    win = rate // 100
    rms = []
    for i in range(0, len(samples) - win, win):
        chunk = samples[i:i + win]
        rms.append((sum(x * x for x in chunk) / win) ** 0.5)
    if not rms:
        return []
    thr = max(rms) * 0.06
    segs, cur, gap = [], None, 0
    for i, v in enumerate(rms):
        if v > thr:
            cur = [i, i] if cur is None else [cur[0], i]
            gap = 0
        elif cur is not None:
            gap += 1
            if gap >= 12:
                segs.append(cur)
                cur, gap = None, 0
    if cur:
        segs.append(cur)
    return [round((b - a + 1) / 100.0, 2) for a, b in segs]


def _digit_slot_segments(value: str, voice: str, locale: str) -> list:
    """Synthesize the clip's digit slot alone (same voice, same rendering)
    as LINEAR16 and count its voiced segments."""
    from google.cloud import texttospeech as tts

    from backend.services import spellback_tts

    slot = ", ".join(value)  # build_spellback_text's own join for digits
    params = {"language_code": locale}
    if voice:
        params["name"] = voice
    resp = spellback_tts._get_client().synthesize_speech(
        input=tts.SynthesisInput(text=slot),
        voice=tts.VoiceSelectionParams(**params),
        audio_config=tts.AudioConfig(
            audio_encoding=tts.AudioEncoding.LINEAR16, sample_rate_hertz=16000),
    )
    return _count_voiced_segments(resp.audio_content[44:])


def _language_verdict(value: str, heard: dict) -> dict:
    digits_heard = "".join(re.findall(r"\d", heard["text"]))
    english = sorted({w.lower().strip(".,") for w in heard["words"]}
                     & _ENGLISH_DIGIT_WORDS)
    recovered = _lcs_len(value, digits_heard) / float(len(value))
    return {"digits_heard": digits_heard,
            "digits_recovered": round(recovered, 2),
            "english_digit_words": english,
            "language_pass": not english and recovered >= 0.8}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--languages", nargs="+",
                    default=["Spanish", "Chinese", "Russian"])
    ap.add_argument("--negative", nargs="*", default=["Urdu", "Persian", "Klingon"],
                    help="languages that must get NO digit clip")
    ap.add_argument("--value", default="5035550297")
    ap.add_argument("--out", default="")
    ap.add_argument("--name", default="",
                    help="ALSO run the NAME leg: synthesize this spelled name "
                         "through the letter path and STT it (recorded, not "
                         "scored -- letter names are judged by reading the "
                         "transcript)")
    ap.add_argument("--name-languages", nargs="+", default=None,
                    help="languages for the NAME leg (default: --languages)")
    ap.add_argument("--names-only", action="store_true",
                    help="run only the NAME leg (skip the digit legs)")
    ap.add_argument("--no-stt", action="store_true",
                    help="skip the STT language leg (waveform token check only)")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args(argv)

    _ensure_quota_project()
    from backend.config import Settings
    from backend.services import spellback_tts
    from backend.services.spellback_tts import (
        SpellbackLanguageUnavailable, build_spellback_text,
        resolve_spellback_voice)

    settings = Settings()
    plan = []
    for lang in args.languages:
        voice, locale = resolve_spellback_voice(settings, lang, for_digits=True)
        text = build_spellback_text(args.value, locale)
        plan.append((lang, voice, locale, text))

    slot_chars = len(", ".join(args.value))
    chars = sum(len(t) for *_x, t in plan) * (0 if args.no_stt else 1)
    chars += slot_chars * len(plan)
    stt = 0 if args.no_stt else len(plan) * math.ceil(_CLIP_SECONDS_BOUND / 15) * STT_USD_PER_15S
    est = chars * TTS_USD_PER_CHAR + stt
    print("plan: %d language(s), %d TTS chars, %s, estimated <= $%.4f (no Live model)"
          % (len(plan), chars, "no STT" if args.no_stt else "%d STT request(s)" % len(plan), est))
    if args.names_only:
        print("  (--names-only: the digit legs above are NOT run)")
    for lang, voice, locale, _t in plan:
        print("  %-10s -> %s (%s)" % (lang, voice or "(locale default)", locale))
    if args.name:
        n_langs = args.name_languages or args.languages
        n_chars = sum(len(build_spellback_text(
            args.name, resolve_spellback_voice(settings, lg)[1])) for lg in n_langs)
        print("name leg: %d clip(s), %d chars + %d STT request(s), estimated <= $%.4f"
              % (len(n_langs), n_chars, len(n_langs),
                 n_chars * TTS_USD_PER_CHAR + len(n_langs) * STT_USD_PER_15S))

    report = {"value": args.value, "estimate_usd": round(est, 4),
              "positive": [], "negative": []}

    # Negative leg first: free (raises before any synthesis).
    all_pass = True
    for lang in args.negative:
        try:
            got = resolve_spellback_voice(settings, lang, for_digits=True)
            print("NEGATIVE FAIL %s: resolved %r -- a digit clip would be made"
                  % (lang, got))
            report["negative"].append({"language": lang, "raised": False})
            all_pass = False
        except SpellbackLanguageUnavailable:
            print("negative ok   %s: no digit clip (SpellbackLanguageUnavailable)" % lang)
            report["negative"].append({"language": lang, "raised": True})

    if not args.yes:
        print("dry run: pass --yes to synthesize")
        return 0

    if args.name:
        report["names"] = []
        for lang in (args.name_languages or args.languages):
            n_voice, n_locale = resolve_spellback_voice(settings, lang)
            n_text = build_spellback_text(args.name, n_locale)
            n_audio = spellback_tts._synthesize_sync(n_text, n_voice, n_locale)
            n_heard = _stt(n_audio, n_locale)
            print("NAME %-10s %s voice=%s text=%s heard=%s conf=%.2f" % (
                lang, n_locale, n_voice or "(locale default)", ascii(n_text),
                ascii(n_heard["text"]), n_heard["confidence"]))
            report["names"].append({"language": lang, "locale": n_locale,
                                    "voice": n_voice, "clip_text": n_text,
                                    **n_heard})
    if args.names_only:
        plan = []

    for lang, voice, locale, text in plan:
        row = {"language": lang, "locale": locale, "voice": voice, "clip_text": text}
        segs = _digit_slot_segments(args.value, voice, locale)
        row["digit_segments"] = segs
        row["tokens_pass"] = len(segs) == len(args.value)
        ok = row["tokens_pass"]
        line = "%-10s %s segments=%d/%d %s" % (
            lang, locale, len(segs), len(args.value), segs)
        if not args.no_stt:
            audio = spellback_tts._synthesize_sync(text, voice, locale)
            heard = _stt(audio, locale)
            row.update(heard)
            row.update(_language_verdict(args.value, heard))
            ok = ok and row["language_pass"]
            line += " | stt conf=%.2f heard=%s recovered=%.2f english=%s" % (
                heard["confidence"], ascii(heard["text"]),
                row["digits_recovered"], row["english_digit_words"])
        all_pass = all_pass and ok
        print("%s %s" % ("PASS" if ok else "FAIL", line))
        report["positive"].append(row)

    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        print("report: %s" % args.out)
    print("OVERALL %s" % ("PASS" if all_pass else "FAIL"))
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
