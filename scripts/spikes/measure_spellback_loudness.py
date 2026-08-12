"""Measure the spell-back clip's loudness against the Live model's voice.

WHY THIS SHIPS (fresh-eyes round 1 on bd polyglot-pdf-9oejl): the gain constant
the per-persona gain table in backend/services/spellback_tts.py holds numbers
in a production audio path, and no unit test can tell whether its VALUE is
right -- only that it is passed through. So the evidence for it must be
reproducible rather than quoted from a scratchpad. Run this to re-derive it.

WHAT IT DOES
  1. Measures the Live model's speech loudness from real output dumps
     (backend/logs/audio_out/gemini_*/*.wav, captured under LIVE_DEV_AUDIO_DUMP).
  2. Synthesizes spell-back clips at the SHIPPED voice/locale for a set of
     gains and measures each.
  3. Reports the ratio to the model, plus peak headroom (a boosted encode that
     CLIPS sounds worse, not louder -- that is the failure mode to avoid).

METHOD NOTE -- why speech-gated RMS, not whole-file RMS: the two sources pad
silence very differently, and a whole-file RMS is dominated by that padding, so
it would compare padding as much as speech. This gates on 20ms frames above 15%
of each file's own peak, making it speech-vs-speech.

WHY volume_gain_db IS NOT LINEAR: the measured result does not follow the dB
arithmetic (a 5.02 dB deficit is NOT closed by +5 dB). Measure, do not derive.

Usage (from repo root, backend venv):
  backend/.venv/Scripts/python.exe scripts/spikes/measure_spellback_loudness.py

Cost: a few cents of Cloud TTS. Requires ADC + texttospeech enabled.
ASCII only (scar #6).
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..")))

from backend.config import Settings  # noqa: E402
from backend.services.spellback_tts import (  # noqa: E402
    build_spellback_text,
    resolve_spellback_voice,
)

# Names representative of the real workload (the W-7 harness fixtures).
SAMPLE_VALUES = ["JOSE", "JOHNSON", "NGUYEN", "MARIA"]
FRAME_SEC = 0.02
VOICED_FRACTION_OF_PEAK = 0.15


def speech_rms(samples, rate: float) -> float:
    """RMS over SPEECH frames only (see the method note in the docstring)."""
    x = np.asarray(samples, dtype=np.float64)
    if x.ndim > 1:
        x = x.mean(axis=1)
    if x.size == 0:
        return 0.0
    frame = max(1, int(rate * FRAME_SEC))
    n = (x.size // frame) * frame
    if n == 0:
        return float(np.sqrt(np.mean(x ** 2)))
    frames = x[:n].reshape(-1, frame)
    frame_rms = np.sqrt((frames ** 2).mean(axis=1))
    peak = frame_rms.max()
    if peak <= 0:
        return 0.0
    voiced = frame_rms[frame_rms > peak * VOICED_FRACTION_OF_PEAK]
    if voiced.size == 0:
        voiced = frame_rms
    return float(np.sqrt((voiced ** 2).mean()))


def measure_model(pattern: str):
    """Speech RMS of every Gemini output dump matching `pattern`."""
    vals = []
    for path in sorted(glob.glob(pattern)):
        try:
            data, rate = sf.read(path)
        except Exception:
            continue
        # Skip scraps too short to characterize a speaking voice.
        if len(data) / float(rate) < 0.5:
            continue
        vals.append(speech_rms(data, rate))
    return vals


def measure_clips(gain_db: float, out_dir: str):
    """Synthesize clips at `gain_db` and return (rms list, peak list)."""
    from google.cloud import texttospeech

    client = texttospeech.TextToSpeechClient()
    settings = Settings()
    rmss, peaks = [], []
    for value in SAMPLE_VALUES:
        voice_name, locale = resolve_spellback_voice(settings, "English")
        text = build_spellback_text(value, locale)
        voice_params = {"language_code": locale}
        if voice_name:
            voice_params["name"] = voice_name
        resp = client.synthesize_speech(
            input=texttospeech.SynthesisInput(text=text),
            voice=texttospeech.VoiceSelectionParams(**voice_params),
            audio_config=texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                volume_gain_db=gain_db,
            ),
        )
        path = os.path.join(out_dir, "loudness_%+.0fdB_%s.mp3" % (gain_db, value))
        with open(path, "wb") as f:
            f.write(resp.audio_content)
        data, rate = sf.read(path)
        d = np.asarray(data, dtype=np.float64)
        if d.ndim > 1:
            d = d.mean(axis=1)
        rmss.append(speech_rms(data, rate))
        peaks.append(float(np.abs(d).max()))
    return rmss, peaks


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dumps", default=os.path.join(
        "backend", "logs", "audio_out", "gemini_*", "*.wav"),
        help="glob for Live-model output dumps")
    # Spans every value in _MEASURED_GAIN_DB (Algieba +4, Iapetus +7) plus 0
    # as the un-boosted baseline, so the printed sweep BRACKETS whatever is
    # shipped. A sweep that skips the shipped value would send an operator
    # following the on-screen rule to a different number than the live one
    # (Opus cross-surface review: the old 0,5,6,7 default missed Algieba's +4
    # entirely, and both 6 and 7 CLIP on that voice).
    ap.add_argument("--gains", default="0,3,4,5,6,7",
                    help="comma-separated volume_gain_db values to try")
    ap.add_argument("--out-dir", default=os.path.join("backend", "logs"),
                    help="where to write the synthesized comparison clips")
    args = ap.parse_args()

    model_vals = measure_model(args.dumps)
    if not model_vals:
        print("NO MODEL DUMPS matched %r -- capture some first with "
              "LIVE_DEV_AUDIO_DUMP=true, or pass --dumps." % args.dumps)
        return 2
    model = float(np.median(model_vals))
    print("model  n=%d  median speech RMS = %.5f" % (len(model_vals), model))
    print()

    os.makedirs(args.out_dir, exist_ok=True)
    for raw in args.gains.split(","):
        gain = float(raw.strip())
        rmss, peaks = measure_clips(gain, args.out_dir)
        med = float(np.median(rmss))
        peak = max(peaks)
        print("gain=%+5.1f dB  clip median RMS=%.5f  = %3.0f%% of model  "
              "max peak=%.3f  %s"
              % (gain, med, 100.0 * med / model, peak,
                 "CLIPPING" if peak >= 0.999 else "headroom ok"))
    print()
    print("Pick the gain closest to 100%% of model WITHOUT clipping, and set")
    print("_MEASURED_GAIN_DB['<persona>'] in backend/services/spellback_tts.py")
    print("(the gain is looked up BY PERSONA -- there is no single constant).")
    print("Perceived loudness is not RMS -- confirm the pick BY EAR.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
