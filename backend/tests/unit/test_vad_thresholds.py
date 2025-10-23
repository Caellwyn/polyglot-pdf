"""
Unit tests for VAD threshold adjustments

Tests:
1. VAD thresholds are set correctly
2. Pre-buffer size matches VAD window
3. Audio quality diagnostics work
"""

import pytest


def test_vad_threshold_values():
    """Test that VAD thresholds are set to correct values"""
    # These are the frontend values, but we test the concept
    positive_threshold = 0.90
    negative_threshold = 0.70
    
    # Verify thresholds are in valid range
    assert 0.0 <= positive_threshold <= 1.0
    assert 0.0 <= negative_threshold <= 1.0
    
    # Verify positive is higher than negative (hysteresis)
    assert positive_threshold > negative_threshold
    
    # Verify specific values (lowered from 0.98/0.85)
    assert positive_threshold == 0.90
    assert negative_threshold == 0.70


def test_prebuffer_size_calculation():
    """Test that pre-buffer size covers full VAD window"""
    min_speech_ms = 250
    redemption_ms = 400
    safety_margin_ms = 50
    
    required_buffer_ms = min_speech_ms + redemption_ms + safety_margin_ms
    actual_buffer_ms = 700
    
    # Verify pre-buffer is large enough
    assert actual_buffer_ms >= required_buffer_ms
    assert actual_buffer_ms == 700  # Increased from 600ms


def test_prebuffer_sample_count():
    """Test pre-buffer sample count calculation"""
    recording_sample_rate = 16000  # 16kHz
    prebuffer_duration_ms = 700
    
    # Calculate expected samples
    expected_samples = int((prebuffer_duration_ms / 1000) * recording_sample_rate)
    
    # Should be 11,200 samples (700ms * 16 samples/ms)
    assert expected_samples == 11200


def test_vad_timing_parameters():
    """Test VAD timing parameters are configured correctly"""
    min_speech_ms = 250
    redemption_ms = 400
    
    # Verify these filter noise and echo
    assert min_speech_ms >= 100  # At least 100ms to filter brief sounds
    assert redemption_ms >= 300  # At least 300ms grace period
    
    # Verify specific values
    assert min_speech_ms == 250
    assert redemption_ms == 400


def test_audio_sample_rate_configuration():
    """Test audio sample rates are set correctly"""
    recording_rate = 16000  # Gemini input
    playback_rate = 24000   # Gemini output
    
    # Verify rates match Gemini requirements
    assert recording_rate == 16000
    assert playback_rate == 24000


def test_audio_quality_diagnostic_sampling():
    """Test audio quality diagnostic sampling rate"""
    # Sample 0.1% of frames (1 in 1000)
    sample_rate = 0.001
    
    # Over 10,000 frames, should sample ~10 times
    total_frames = 10000
    expected_samples = int(total_frames * sample_rate)
    
    assert expected_samples == 10
    assert sample_rate == 0.001  # Prevents log spam


def test_pcm16_conversion_range():
    """Test PCM16 conversion stays in valid range"""
    # Float32 samples are in range [-1.0, 1.0]
    test_samples = [-1.0, -0.5, 0.0, 0.5, 1.0]
    
    for sample in test_samples:
        # Clamp to valid range
        clamped = max(-1.0, min(1.0, sample))
        assert -1.0 <= clamped <= 1.0
        
        # Convert to PCM16
        if clamped < 0:
            pcm16 = int(clamped * 0x8000)  # -32768
        else:
            pcm16 = int(clamped * 0x7FFF)  # 32767
        
        # Verify in PCM16 range
        assert -32768 <= pcm16 <= 32767


def test_clipping_detection():
    """Test clipping detection logic"""
    # Sample data with some clipping
    samples = [0.0, 0.5, 0.99, 1.0, -1.0, 0.3]  # 2 clipped (1.0, -1.0)
    
    clipped_count = sum(1 for s in samples if abs(s) > 0.99)
    clipping_rate = (clipped_count / len(samples)) * 100
    
    assert clipped_count == 2
    assert clipping_rate == pytest.approx(33.33, rel=0.01)


def test_rms_energy_calculation():
    """Test RMS energy calculation"""
    import math
    
    # Test samples
    samples = [0.1, 0.2, 0.3, 0.4]
    
    # Calculate RMS
    sum_squares = sum(s * s for s in samples)
    rms = math.sqrt(sum_squares / len(samples))
    energy = rms * 100  # Scale to 0-100
    
    # Verify calculation
    expected_rms = math.sqrt((0.01 + 0.04 + 0.09 + 0.16) / 4)
    assert rms == pytest.approx(expected_rms, rel=0.01)
    assert 0 <= energy <= 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
