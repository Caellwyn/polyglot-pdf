"""The PHI knobs must be unreachable in a deployed service.

bd polyglot-pdf-0rpu, maintainer directive 2026-08-05:
  - transcripts: "turn on transcripts for local dev ONLY. It's important for
    privacy that they are turned off for deploy."

Transcript capture and the output-audio dump are DOUBLE-GATED on
DEV_LOGGING_ENABLED -- the gitignored backend/.env.DEV marker file, which
cannot exist on Cloud Run -- AND their own opt-in setting. The load-bearing
assertion in this file is the PROD one: with the env var set, a service
without the marker must still capture NOTHING.

Both are PHI (docs/standards/hipaa-pii-policy.md). A regression here is a
privacy incident, not a bug, so the prod-negative cases are asserted first and
for each knob independently.

TEMPERATURE IS NO LONGER ONE OF THESE (maintainer 2026-08-10). It was
dev-marker-gated under the same 2026-08-05 directive ("not much point in
having a slider for deployment"), but that was reversed: 0.4 was judged by ear
to make the model's speech clearer, and every spell-back validation run (bd
22h1f / 44ywm) used it, so the demo deploys at 0.4 rather than shipping an
untested 1.0. It is now honored wherever it is set. Temperature is NOT PHI --
it carries no user data -- so promoting it does not touch the privacy
guarantee this file exists to protect, and the tests below still assert that
guarantee for the two knobs that DO carry PHI.
"""
import logging

import pytest
from unittest.mock import patch

import backend.adapters.live_ai_gemini as live_mod
from backend.config import Settings


@pytest.fixture(autouse=True)
def _quiet():
    """The adapter logs warnings for the intentionally-bad values below."""
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


def _build(*, dev_marker: bool, temperature: str = "", transcripts: bool = False):
    """Build the REAL Live connect config with the dev marker forced on/off."""
    with patch("google.genai.Client"), patch.object(
        live_mod, "DEV_LOGGING_ENABLED", dev_marker
    ):
        adapter = live_mod.LiveAIGemini(model="gemini-live-2.5-flash-native-audio")
        adapter._enable_transcripts = False  # the client-visible transcript stays off
        settings = Settings()
        settings.LIVE_TEMPERATURE = temperature
        settings.LIVE_DEV_TRANSCRIPTS = transcripts
        return adapter, adapter._build_live_config(settings)


# --- the privacy/production guarantees (most important) ----------------------

def test_production_ignores_the_PHI_knobs_even_when_the_env_var_is_set():
    """THE load-bearing test. No .env.DEV marker -> no transcript capture,
    whatever the env says. (Temperature is deliberately NOT asserted here --
    it is not PHI and is now deployable; see test_temperature_applies_in_
    production_too below.)"""
    adapter, config = _build(dev_marker=False, temperature="0.4", transcripts=True)
    assert "output_audio_transcription" not in config
    assert "input_audio_transcription" not in config
    assert adapter._dev_transcripts is False


def test_production_config_is_unchanged_by_the_PHI_knobs_existing():
    """Byte-comparable: with the transcript env var set but no marker, the
    deployed config must equal the one without it -- the capture feature
    changed nothing in production. Temperature is held constant across both
    sides because it IS meant to apply in production now."""
    _, with_vars = _build(dev_marker=False, temperature="0.6", transcripts=True)
    _, without_vars = _build(dev_marker=False, temperature="0.6", transcripts=False)
    assert with_vars == without_vars


def test_dev_marker_alone_does_not_enable_capture():
    """The marker is necessary but NOT sufficient -- capture needs its own
    opt-in, so simply developing locally does not start writing PHI."""
    adapter, config = _build(dev_marker=True)
    assert "output_audio_transcription" not in config
    assert adapter._dev_transcripts is False


# --- temperature: deployable since 2026-08-10 --------------------------------

def test_dev_applies_temperature():
    _, config = _build(dev_marker=True, temperature="0.4")
    assert config["temperature"] == 0.4


def test_temperature_applies_in_production_too():
    """The 2026-08-10 promotion: a deployed service (no .env.DEV marker) MUST
    honor LIVE_TEMPERATURE, or the demo silently runs at Google's default 1.0
    -- a configuration no spell-back validation run ever used."""
    _, config = _build(dev_marker=False, temperature="0.4")
    assert config["temperature"] == 0.4


def test_unset_temperature_still_sends_nothing_in_production():
    """Promotion must not mean 'always send a temperature': unset stays unset,
    so a deploy that does not opt in keeps Google's default exactly as before."""
    _, config = _build(dev_marker=False, temperature="")
    assert "temperature" not in config


def test_dev_enables_transcript_capture():
    adapter, config = _build(dev_marker=True, transcripts=True)
    assert config["output_audio_transcription"] == {}
    assert config["input_audio_transcription"] == {}
    assert adapter._dev_transcripts is True


def test_transcript_capture_does_not_disturb_the_language_bias():
    """The ASR language-code hint decorates the SAME transcription blocks; the
    dev capture uses setdefault so it must not clobber a bias already applied."""
    with patch("google.genai.Client"), patch.object(
        live_mod, "DEV_LOGGING_ENABLED", True
    ):
        adapter = live_mod.LiveAIGemini(model="gemini-live-2.5-flash-native-audio")
        adapter._enable_transcripts = True
        adapter.set_transcription_language_codes(["es-US"])
        settings = Settings()
        settings.LIVE_DEV_TRANSCRIPTS = True
        config = adapter._build_live_config(settings)
    assert config["input_audio_transcription"] == {"language_codes": ["es-US"]}
    assert config["output_audio_transcription"] == {"language_codes": ["es-US"]}


# --- the unsafe-value guards -------------------------------------------------

@pytest.mark.parametrize("bad", ["0", "0.0", "-1", "2.5", "abc", "  "])
def test_unsafe_or_malformed_temperature_is_ignored_not_passed_through(bad):
    """0 is KNOWN to break native audio (googleapis/js-genai#1578: runaway /
    no-audio output and a 1011 session close), and a typo must not silently
    break every session. Both fall back to Google's default by omission."""
    _, config = _build(dev_marker=True, temperature=bad)
    assert "temperature" not in config


@pytest.mark.parametrize("good", ["0.3", "0.6", "1.0", "2.0"])
def test_in_range_temperatures_are_applied(good):
    _, config = _build(dev_marker=True, temperature=good)
    assert config["temperature"] == float(good)


# --- the output-audio dump knob (bd 0rpu Stage 0) -----------------------------

def _build_dump(*, dev_marker: bool, dump: bool):
    with patch("google.genai.Client"), patch.object(
        live_mod, "DEV_LOGGING_ENABLED", dev_marker
    ):
        adapter = live_mod.LiveAIGemini(model="gemini-live-2.5-flash-native-audio")
        adapter._enable_transcripts = False
        settings = Settings()
        settings.LIVE_DEV_AUDIO_DUMP = dump
        adapter._build_live_config(settings)
        return adapter


def test_audio_dump_off_in_production_even_with_env_set():
    """PHI gate: no .env.DEV marker -> the dump latch stays False and appending
    audio writes NOTHING, even with the env knob on."""
    adapter = _build_dump(dev_marker=False, dump=True)
    assert adapter._dev_audio_dump is False
    adapter._dev_dump_audio(b"\x00\x01" * 512)
    assert len(adapter._dump_buf) == 0
    adapter._dev_flush_audio_dump("test")
    assert adapter._dump_gen == 0  # nothing flushed


def test_audio_dump_needs_its_own_opt_in():
    """The dev marker alone must not start writing PHI."""
    adapter = _build_dump(dev_marker=True, dump=False)
    assert adapter._dev_audio_dump is False


def test_audio_dump_produces_readable_wav(tmp_path, monkeypatch):
    """ON: buffered audio flushes to a wave-readable file with the playback
    params (mono, 16-bit, AUDIO_OUT_RATE), and the generation counter advances."""
    import wave

    monkeypatch.chdir(tmp_path)  # writes go under tmp backend/logs/audio_out
    adapter = _build_dump(dev_marker=True, dump=True)
    assert adapter._dev_audio_dump is True
    adapter._dev_dump_audio(b"\x00\x01" * 2400)
    adapter._dev_flush_audio_dump("turn_complete")
    wavs = list((tmp_path / "backend" / "logs" / "audio_out").rglob("*.wav"))
    assert len(wavs) == 1
    with wave.open(str(wavs[0]), "rb") as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 24000)
        assert w.getnframes() == 2400
    assert adapter._dump_gen == 1
    # An empty buffer must not produce a zero-length WAV.
    adapter._dev_flush_audio_dump("turn_complete")
    assert adapter._dump_gen == 1
