"""Measure the REAL synthesized duration of intro+disclaimer script candidates.

Sprint 20 stage-1 gate (bd polyglot-pdf-s1iex.1): the English master must land
at 60-90 SECONDS MEASURED from real synthesized audio -- never estimated from
word count (maintainer directive: word-count extrapolation is what produced a
wrong "2.5 minutes" estimate for a notice that actually runs ~60s).

Synthesis runs the SHIPPED path: backend.services.spellback_tts._synthesize_sync
-- the exact voice resolution ({locale}-Chirp3-HD-{persona} with the three-rung
fallback), volume_gain_db=spellback_gain_db(voice), MP3 encode that the
spell-back clip ships with and that the intro route (bd polyglot-pdf-s1iex.3)
will reuse. Deploy-fidelity per the experimentation skill: nothing is stubbed.

Usage (from repo root; the backend venv lives in the MAIN checkout):
  backend/.venv/Scripts/python.exe scripts/spikes/measure_intro_duration.py \
      scripts/spikes/data/intro_en_v1.txt [more candidate files...]
  Options: --language English  (session language name; drives voice locale)

Prints per candidate: MEASURED MP3 duration (the gate number), UTF-8 byte
length of the input text (the 5000-byte synthesizeSpeech input cap -- bead
.2's per-language budget), char/word counts (context only, never the claim),
and the resolved voice + gain. Writes the MP3 next to the input file as
<name>.mp3. Prints ASCII ONLY (scar #6): candidate text is UTF-8 data and is
never echoed to stdout.

Cost: ~1.3KB of Chirp3-HD characters per candidate (~USD 30 per 1M chars ->
roughly 4 cents per 10 iterations); no LLM calls. Requires ADC + Cloud
Text-to-Speech enabled -- the same setup measure_spellback_loudness.py
already ran successfully on this machine (2026-08-10/11).
ASCII only in this file (scar #6).
"""
from __future__ import annotations

import argparse
import os
import sys

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
TARGET_HIGH_S = 90.0
SYNTH_INPUT_BYTE_CAP = 5000  # Cloud TTS synthesizeSpeech input limit (UTF-8).


def measure(path: str, language: str) -> int:
    with open(path, encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        print("%s: EMPTY -- skipped" % path)
        return 2

    voice_name, locale = resolve_spellback_voice(Settings(), language)
    audio = _synthesize_sync(text, voice_name, locale)

    mp3_path = os.path.splitext(path)[0] + ".mp3"
    with open(mp3_path, "wb") as f:
        f.write(audio)

    data, rate = sf.read(mp3_path)
    duration_s = len(data) / float(rate)
    n_bytes = len(text.encode("utf-8"))
    verdict = ("IN WINDOW" if TARGET_LOW_S <= duration_s <= TARGET_HIGH_S
               else ("TOO SHORT" if duration_s < TARGET_LOW_S else "TOO LONG"))
    print("%s:" % os.path.basename(path))
    print("  voice=%s locale=%s gain=%+.1fdB"
          % (voice_name or "(locale default)", locale,
             spellback_gain_db(voice_name)))
    print("  MEASURED duration = %.1f s  [target %.0f-%.0f s]  -> %s"
          % (duration_s, TARGET_LOW_S, TARGET_HIGH_S, verdict))
    print("  input: %d UTF-8 bytes (cap %d), %d chars, %d words"
          % (n_bytes, SYNTH_INPUT_BYTE_CAP, len(text), len(text.split())))
    print("  mp3: %s (%d bytes)" % (mp3_path, len(audio)))
    return 0 if verdict == "IN WINDOW" else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("candidates", nargs="+",
                    help="UTF-8 text files with candidate script copy")
    ap.add_argument("--language", default="English",
                    help="session language NAME (drives voice locale), "
                         "e.g. English, Spanish, Hindi")
    args = ap.parse_args()

    worst = 0
    for path in args.candidates:
        rc = measure(path, args.language)
        worst = max(worst, rc)
        print()
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
