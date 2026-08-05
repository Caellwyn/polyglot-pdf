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
    # Spelled-name sequence for the text/audio desync attribution (bd
    # polyglot-pdf-0rpu, plan Stage 0d): the exact three names from the failing
    # 2026-08-05 session. Letters are dot-separated so gTTS voices them as
    # individual letter names ("jay. oh. aitch. en."), matching how a user
    # spells aloud. The follow-up "no" lets a scenario exercise the re-spell
    # loop the failing session hit.
    ("spell_john.wav", "J. O. H. N."),
    ("spell_joshua.wav", "J. O. S. H. U. A."),
    ("spell_johnson.wav", "J. O. H. N. S. O. N."),
    ("confirm_no.wav", "no that's wrong"),
    # Section-2 numeric value for the multi-section scenario (bd polyglot-pdf-8k8):
    # a 5-digit ZIP that fits p1_line6f_zipcode (max_length 5). Expected filled
    # value "12345".
    ("digits_12345.wav", "one two three four five"),
    # Secretary cross-field query for the ask_secretary E2E (bd polyglot-pdf-p68s
    # / jnjj.45d): a plain-language question about a PAST answer in a DIFFERENT
    # field. The principal cannot answer from its own (thin) context, so it must
    # call ask_secretary, which holds the WHOLE form catalog (full_schema) + the
    # current values. Phrasing matches the tool description's example shape.
    ("secretary_query_alien.wav",
     "what alien registration number did I give earlier?"),
    # Long-standard-list read-out request (bd polyglot-pdf-bxra): on an
    # ask-directly field (e.g. the I-90 50-state selects) this must trigger
    # the COMPLETE option recital.
    ("read_all_options.wav",
     "Can you please read me the whole list of options?"),
    # wsao.2 measurement-gate utterances (sprint-16 step 2): the w7
    # reason-for-applying A/B. A deep requirements question answerable ONLY
    # from the booklet's reason section (Exceptions 1-2: no tax return needed
    # under an exception; boxes a/f also require box h), the box-a answer, and
    # Spanish variants for the language-lock contamination arm. Spanish text is
    # unicode-escaped to keep this source ASCII (CLAUDE.md scar #6). Entries
    # may carry an optional third element: the gTTS language code.
    ("treaty_question.wav",
     "Do I need to attach a tax return if I'm applying under a treaty "
     "exception?"),
    ("reason_a_answer.wav",
     "Yes, box A applies to me. I'm claiming a tax treaty benefit."),
    # Spanish glyphs are chr()-composed so this source stays pure ASCII
    # (CLAUDE.md scar #6): 0xBF=inverted-?, 0xF3=o-acute, 0xED=i-acute.
    ("treaty_question_es.wav",
     chr(0xBF) + "Necesito adjuntar una declaraci" + chr(0xF3) + "n de "
     "impuestos si presento la solicitud bajo una excepci" + chr(0xF3) + "n "
     "del tratado?", "es"),
    ("reason_a_answer_es.wav",
     "S" + chr(0xED) + ", la casilla A. Reclamo un beneficio del tratado "
     "fiscal.", "es"),
    ("confirm_yes_es.wav", "s" + chr(0xED) + ", es correcto", "es"),
]

TARGET_SR = 16000  # Gemini Live input rate (audio/pcm;rate=16000).

# Repo-root-relative output dir (vite serves frontend/public at the web root).
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
OUT_DIR = os.path.join(_REPO_ROOT, "frontend", "public", "test-fixtures")


def synth_to_wav(text: str, out_path: str, lang: str = "en") -> None:
    """Synthesize `text`, resample to 16 kHz mono PCM16, write `out_path`."""
    # gTTS emits MP3; write to a temp file then load+resample with librosa.
    tmp_fd, tmp_mp3 = tempfile.mkstemp(suffix=".mp3")
    os.close(tmp_fd)
    try:
        gTTS(text=text, lang=lang).save(tmp_mp3)
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
    force = "--force" in sys.argv
    os.makedirs(OUT_DIR, exist_ok=True)
    print("output dir:", OUT_DIR)
    for entry in UTTERANCES:
        name, text = entry[0], entry[1]
        lang = entry[2] if len(entry) > 2 else "en"
        out_path = os.path.join(OUT_DIR, name)
        # Committed fixtures are stable artifacts -- regenerating them churns
        # bytes for no reason. Skip existing files unless --force.
        if os.path.exists(out_path) and not force:
            print("skip (exists):", name)
            continue
        synth_to_wav(text, out_path, lang=lang)
    print("done. commit the .wav files under frontend/public/test-fixtures/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
