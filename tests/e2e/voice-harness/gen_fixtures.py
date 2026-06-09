"""One-time generator for the voice-harness audio fixtures (bd polyglot-pdf-g8w).

Synthesizes the two canned utterances the E2E voice harness replays into the app,
resamples them to the wire format the backend forwards to Gemini (16 kHz, mono,
signed 16-bit little-endian PCM), and writes them as .wav under
frontend/public/test-fixtures/ so vite serves them at /test-fixtures/<name>.wav.

This is run ONCE by a human/agent and its output is committed; the harness itself
never calls TTS at test time (deterministic, offline, no per-run dependency).

Usage (from repo root, with the backend venv that has gtts + librosa + soundfile):
    backend/.venv/Scripts/python.exe tests/e2e/voice-harness/gen_fixtures.py

Network: gTTS hits Google's translate TTS endpoint at generation time only.
If you are offline, generate elsewhere and copy the .wav files in -- the format
contract (16 kHz / mono / PCM_16) is enforced + printed below.

Prereq note: librosa imports the legacy `pkg_resources`, which setuptools >= 81
no longer ships. If you hit `ModuleNotFoundError: No module named 'pkg_resources'`,
run `python -m pip install "setuptools<81"` in the venv first.
"""
from __future__ import annotations

import os
import sys
import tempfile

import librosa
import numpy as np
import soundfile as sf
from gtts import gTTS

# (output filename, spoken text). The digits phrase is what a user typically says
# for a numeric field; "1234567" is the expected filled value. The confirm phrase
# is the affirmative reply to Gemini's verification question.
UTTERANCES = [
    ("digits_1234567.wav", "one two three four five six seven"),
    ("confirm_yes.wav", "yes that's correct"),
]

TARGET_SR = 16000  # Gemini Live input rate (audio/pcm;rate=16000).

# Repo-root-relative output dir (vite serves frontend/public at the web root).
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
OUT_DIR = os.path.join(_REPO_ROOT, "frontend", "public", "test-fixtures")


def synth_to_wav(text: str, out_path: str) -> None:
    """Synthesize `text`, resample to 16 kHz mono PCM16, write `out_path`."""
    # gTTS emits MP3; write to a temp file then load+resample with librosa.
    tmp_fd, tmp_mp3 = tempfile.mkstemp(suffix=".mp3")
    os.close(tmp_fd)
    try:
        gTTS(text=text, lang="en").save(tmp_mp3)
        # mono=True downmixes; sr=TARGET_SR resamples. Returns float32 in [-1, 1].
        audio, sr = librosa.load(tmp_mp3, sr=TARGET_SR, mono=True)
    finally:
        try:
            os.remove(tmp_mp3)
        except OSError:
            pass

    # float32 [-1,1] -> int16 PCM. Clip first so a stray >1.0 sample can't wrap.
    pcm16 = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
    sf.write(out_path, pcm16, TARGET_SR, subtype="PCM_16")

    info = sf.info(out_path)
    print(
        "wrote {name}: {sr} Hz, {ch} ch, {sub}, {dur:.2f}s".format(
            name=os.path.basename(out_path),
            sr=info.samplerate,
            ch=info.channels,
            sub=info.subtype,
            dur=info.duration,
        )
    )
    # Hard-fail the run if the format contract drifted -- the harness depends on it.
    assert info.samplerate == TARGET_SR, "sample rate must be 16000"
    assert info.channels == 1, "must be mono"
    assert info.subtype == "PCM_16", "must be 16-bit PCM"


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    print("output dir:", OUT_DIR)
    for name, text in UTTERANCES:
        synth_to_wav(text, os.path.join(OUT_DIR, name))
    print("done. commit the .wav files under frontend/public/test-fixtures/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
