"""Audio helper adapter using librosa and soundfile.

Provides small, well-documented helpers used by the backend to convert
arbitrary audio inputs into raw PCM16@16k mono bytes suitable for Gemini.

This file intentionally implements a minimal, dependency-backed API so tests
can import it and callers don't have to rely directly on librosa/soundfile
APIs.
"""
from __future__ import annotations

import io
from typing import Tuple

import numpy as np
import soundfile as sf
import librosa


def _ensure_mono(y: np.ndarray) -> np.ndarray:
    """Convert multi-channel audio to mono by averaging channels."""
    if y.ndim == 1:
        return y
    # average across channels
    return np.mean(y, axis=1)


def resample_to_pcm16_mono(audio_bytes: bytes, target_rate: int = 16000) -> Tuple[bytes, int]:
    """Read audio bytes (wav/pcm/raw where soundfile can decode) and return
    PCM16 little-endian mono bytes at target_rate.

    Returns a tuple of (pcm16_bytes, samplerate) where samplerate == target_rate.

    Raises: RuntimeError if the audio can't be decoded.
    """
    try:
        bio = io.BytesIO(audio_bytes)
        # soundfile can read many container formats
        y, sr = sf.read(bio, dtype='float32')
    except Exception:
        # Try to interpret raw PCM16 little-endian as a fallback
        try:
            # If we can't decode the container, assume it's raw PCM16 little-endian
            arr = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            y = arr
            sr = target_rate
        except Exception as exc:
            raise RuntimeError(f"Unable to decode audio bytes: {exc}")

    y = _ensure_mono(np.asarray(y))

    if sr != target_rate:
        y = librosa.resample(y, orig_sr=sr, target_sr=target_rate)
        sr = target_rate

    # Clip and convert to int16 little-endian
    y = np.clip(y, -1.0, 1.0)
    pcm16 = (y * 32767.0).astype(np.int16)
    return pcm16.tobytes(), sr


def convert_float_array_to_pcm16_bytes(y: np.ndarray) -> bytes:
    """Helper to convert a float32 numpy array in range [-1, 1] to PCM16LE bytes."""
    y = _ensure_mono(y)
    y = np.clip(y, -1.0, 1.0)
    pcm16 = (y * 32767.0).astype(np.int16)
    return pcm16.tobytes()


def read_wav_and_return_pcm16(audio_path: str, target_rate: int = 16000) -> bytes:
    """Convenience: load a file from disk and return PCM16LE bytes at target_rate."""
    y, sr = librosa.load(audio_path, sr=target_rate, mono=True)
    return convert_float_array_to_pcm16_bytes(y)
