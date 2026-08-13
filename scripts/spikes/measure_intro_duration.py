"""Measure the REAL synthesized duration of intro+disclaimer script candidates.

Sprint 20 stage-1 gate (bd polyglot-pdf-s1iex.1): the English master must land
at 60-90 SECONDS MEASURED from real synthesized audio -- never estimated from
word count (maintainer directive: word-count extrapolation is what produced a
wrong "2.5 minutes" estimate for a notice that actually runs ~60s).

Default synthesis runs the SHIPPED path:
backend.services.spellback_tts._synthesize_sync -- the exact voice resolution
({locale}-Chirp3-HD-{persona} with the three-rung fallback),
volume_gain_db=spellback_gain_db(voice), MP3 encode that the spell-back clip
ships with and that the intro route (bd polyglot-pdf-s1iex.3) will reuse.
Deploy-fidelity per the experimentation skill: nothing is stubbed.

--encoding adds LABELED EXPERIMENTAL ARMS (deliberate deviations from the
shipped encode, for the 2026-08-13 "why does the HD voice sound robotic"
investigation -- the shipped Cloud TTS v1 MP3 default is 32 kbps mono, which
starves a 24 kHz HD voice):
  mp3      -- the shipped path verbatim (v1 default MP3 = 32 kbps)
  mp3_64   -- v1beta1 MP3_64_KBPS (NOTE: measured 2026-08-13, Chirp3-HD
              voices REJECT this encoding -- kept only to document the 400)
  ogg      -- v1 OGG_OPUS: the best-quality COMPRESSED option Chirp3 accepts
  linear16 -- v1 LINEAR16 (uncompressed WAV @ native rate): the no-codec
              reference; if THIS still sounds robotic the voice itself is the
              limit, not the encode
Gain note: the shipped +4.0 dB Algieba gain CLIPS on long-form content
(measured peak 1.000 on an ~91s clip; the short spell-back clips peaked
0.975). For clean codec A/B, set SPELLBACK_VOLUME_GAIN_DB=0 in the env --
spellback_gain_db() honors it as an override.

Usage (from repo root; the backend venv lives in the MAIN checkout):
  backend/.venv/Scripts/python.exe scripts/spikes/measure_intro_duration.py \
      scripts/spikes/data/intro_en_v4.txt [more candidates...] \
      [--encoding mp3|mp3_64|linear16] [--language English]

Prints per candidate: MEASURED duration (the gate number), UTF-8 byte length
of the input text (the 5000-byte synthesizeSpeech input cap -- bead .2's
budget), char/word counts (context only, never the claim), resolved
voice/gain, peak amplitude (clipping check), and the audio file's actual
bitrate. Writes audio next to the input file. Prints ASCII ONLY (scar #6):
candidate text is UTF-8 data and is never echoed to stdout.

Cost: ~1.4KB of Chirp3-HD characters per candidate per arm (~USD 30 per 1M
chars); no LLM calls. Requires ADC + Cloud Text-to-Speech enabled.
ASCII only in this file (scar #6).
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..")))

from backend.config import Settings  # noqa: E402
from backend.services.spellback_tts import (  # noqa: E402
    _synthesize_sync,
    resolve_spellback_voice,
    spellback_gain_db,
)

TARGET_LOW_S = 60.0
# 95, not the plan's original 90: the maintainer widened the window 2026-08-13
# when freezing the (longer) edited master -- see the "Post-filing maintainer
# decisions" section of docs/sprint_20_sol-intro-tts_plan.md.
TARGET_HIGH_S = 95.0
SYNTH_INPUT_BYTE_CAP = 5000  # Cloud TTS synthesizeSpeech input limit (UTF-8).


def _synthesize_arm(text: str, voice_name: str, locale: str,
                    encoding: str) -> tuple[bytes, str]:
    """One LABELED experimental encode arm. Returns (audio, file extension).

    Mirrors _synthesize_sync's request exactly except audio_encoding; the
    mp3_64 arm needs the v1beta1 API surface (MP3_64_KBPS is not in v1).
    """
    if encoding == "mp3_64":
        from google.cloud import texttospeech_v1beta1 as tts
        enc = tts.AudioEncoding.MP3_64_KBPS
        ext = ".64.mp3"
    elif encoding == "ogg":
        from google.cloud import texttospeech as tts
        enc = tts.AudioEncoding.OGG_OPUS
        ext = ".ogg"
    else:  # linear16
        from google.cloud import texttospeech as tts
        enc = tts.AudioEncoding.LINEAR16
        ext = ".wav"
    client = tts.TextToSpeechClient()
    voice_params = {"language_code": locale}
    if voice_name:
        voice_params["name"] = voice_name
    resp = client.synthesize_speech(
        input=tts.SynthesisInput(text=text),
        voice=tts.VoiceSelectionParams(**voice_params),
        audio_config=tts.AudioConfig(
            volume_gain_db=spellback_gain_db(voice_name),
            audio_encoding=enc,
        ),
    )
    return resp.audio_content, ext


def measure(path: str, language: str, encoding: str) -> int:
    with open(path, encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        print("%s: EMPTY -- skipped" % path)
        return 2

    voice_name, locale = resolve_spellback_voice(Settings(), language)
    if encoding == "mp3":
        audio = _synthesize_sync(text, voice_name, locale)  # the SHIPPED path
        ext = ".mp3"
    else:
        audio, ext = _synthesize_arm(text, voice_name, locale, encoding)

    out_path = os.path.splitext(path)[0] + ext
    with open(out_path, "wb") as f:
        f.write(audio)

    data, rate = sf.read(out_path)
    d = np.asarray(data, dtype=np.float64)
    if d.ndim > 1:
        d = d.mean(axis=1)
    duration_s = len(d) / float(rate)
    n_bytes = len(text.encode("utf-8"))
    verdict = ("IN WINDOW" if TARGET_LOW_S <= duration_s <= TARGET_HIGH_S
               else ("TOO SHORT" if duration_s < TARGET_LOW_S else "TOO LONG"))
    print("%s [%s]:" % (os.path.basename(path), encoding))
    print("  voice=%s locale=%s gain=%+.1fdB rate=%dHz"
          % (voice_name or "(locale default)", locale,
             spellback_gain_db(voice_name), rate))
    print("  MEASURED duration = %.1f s  [target %.0f-%.0f s]  -> %s"
          % (duration_s, TARGET_LOW_S, TARGET_HIGH_S, verdict))
    print("  input: %d UTF-8 bytes (cap %d), %d chars, %d words"
          % (n_bytes, SYNTH_INPUT_BYTE_CAP, len(text), len(text.split())))
    print("  audio: %s (%d bytes, %.1f kbps, peak %.3f%s)"
          % (out_path, len(audio), len(audio) * 8 / duration_s / 1000,
             float(np.abs(d).max()),
             " CLIPPING" if float(np.abs(d).max()) >= 0.999 else ""))
    return 0 if verdict == "IN WINDOW" else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("candidates", nargs="+",
                    help="UTF-8 text files with candidate script copy")
    ap.add_argument("--language", default="English",
                    help="session language NAME (drives voice locale), "
                         "e.g. English, Spanish, Hindi")
    ap.add_argument("--encoding", default="mp3",
                    choices=["mp3", "mp3_64", "ogg", "linear16"],
                    help="mp3 = the shipped encode; others are labeled "
                         "experimental arms (see module docstring)")
    args = ap.parse_args()

    worst = 0
    for path in args.candidates:
        rc = measure(path, args.language, args.encoding)
        worst = max(worst, rc)
        print()
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
