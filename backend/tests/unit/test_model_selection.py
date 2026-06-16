"""Unit tests for native-audio model selection (USE_PREMIUM_MODEL -> MODEL_NATIVE).

Covers the `_resolve_model` validator and its alignment with the family-keyed
pricing table. We pass values via the Settings constructor rather than env vars:
the field defaults read os.getenv at class-definition time, so setting os.environ
after import would NOT affect a later Settings() -- constructor args are the
reliable way to exercise the validator. See bd polyglot-pdf-4cm.
"""

import os

import pytest

from backend.config import (
    MODEL_NATIVE_PREMIUM,
    MODEL_NATIVE_STANDARD,
    MODEL_NATIVE_STANDARD_VERTEX,
    Settings,
    model_family,
)


def test_standard_tier_on_ai_studio_resolves_to_2_5_native():
    # AI Studio path (VERTEXAI=False): standard tier -> the AI Studio native-audio id.
    s = Settings(VERTEXAI=False, USE_PREMIUM_MODEL=False, MODEL_NATIVE="")
    assert s.MODEL_NATIVE == MODEL_NATIVE_STANDARD
    assert s.MODEL_NATIVE == "gemini-2.5-flash-native-audio-preview-12-2025"


def test_standard_tier_on_vertex_resolves_to_vertex_native():
    # Vertex path (VERTEXAI=True): standard tier -> the Vertex native-audio id,
    # because the AI Studio id 1008s on Vertex. Backend-aware resolution means a
    # Vertex deploy needs no MODEL_NATIVE pin (bd polyglot-pdf-a079). Still 2.5.
    s = Settings(VERTEXAI=True, USE_PREMIUM_MODEL=False, MODEL_NATIVE="")
    assert s.MODEL_NATIVE == MODEL_NATIVE_STANDARD_VERTEX
    assert s.MODEL_NATIVE == "gemini-live-2.5-flash-native-audio"
    assert model_family(s.MODEL_NATIVE) == "2.5"


def test_premium_tier_resolves_to_3_1_live():
    s = Settings(USE_PREMIUM_MODEL=True, MODEL_NATIVE="")
    assert s.MODEL_NATIVE == MODEL_NATIVE_PREMIUM
    assert s.MODEL_NATIVE == "gemini-3.1-flash-live-preview"


def test_default_resolves_to_2_5_standard():
    """Regression: with NO premium flag, the default tier is standard/2.5.

    2.5 is the default for latency (~170x faster per turn on the audio path).
    Pin it so a future accidental flip to 3.1 is caught here. Resolution is now
    BACKEND-AWARE (bd polyglot-pdf-a079): the standard tier's 2.5 id depends on
    VERTEXAI, so this test pins VERTEXAI=False to assert the AI Studio id
    specifically (the Vertex branch is covered by
    test_standard_tier_on_vertex_resolves_to_vertex_native). The field default is
    read from os.getenv at class-definition time, so an explicit
    `USE_PREMIUM_MODEL` env override would invalidate this -- skip in that case.
    """
    if os.getenv("USE_PREMIUM_MODEL") is not None:
        pytest.skip("USE_PREMIUM_MODEL is set in the env; can't assert the code default")
    s = Settings(VERTEXAI=False, MODEL_NATIVE="")  # USE_PREMIUM_MODEL at field default
    assert s.USE_PREMIUM_MODEL is False
    assert s.MODEL_NATIVE == MODEL_NATIVE_STANDARD == "gemini-2.5-flash-native-audio-preview-12-2025"


def test_explicit_model_native_overrides_flag():
    # A non-empty MODEL_NATIVE pin wins regardless of the premium flag.
    s = Settings(USE_PREMIUM_MODEL=True, MODEL_NATIVE="gemini-custom-pin")
    assert s.MODEL_NATIVE == "gemini-custom-pin"


def test_resolved_models_map_to_expected_pricing_families():
    # The whole point of the toggle is a comparable 2.5-vs-3.1 cost A/B.
    standard = Settings(USE_PREMIUM_MODEL=False, MODEL_NATIVE="")
    premium = Settings(USE_PREMIUM_MODEL=True, MODEL_NATIVE="")
    assert model_family(standard.MODEL_NATIVE) == "2.5"
    assert model_family(premium.MODEL_NATIVE) == "3.1"
