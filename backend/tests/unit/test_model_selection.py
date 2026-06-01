"""Unit tests for native-audio model selection (USE_PREMIUM_MODEL -> MODEL_NATIVE).

Covers the `_resolve_model` validator and its alignment with the family-keyed
pricing table. We pass values via the Settings constructor rather than env vars:
the field defaults read os.getenv at class-definition time, so setting os.environ
after import would NOT affect a later Settings() — constructor args are the
reliable way to exercise the validator. See bd polyglot-pdf-4cm.
"""

import os

import pytest

from backend.config import (
    MODEL_NATIVE_PREMIUM,
    MODEL_NATIVE_STANDARD,
    Settings,
    model_family,
)


def test_standard_tier_resolves_to_2_5_native():
    s = Settings(USE_PREMIUM_MODEL=False, MODEL_NATIVE="")
    assert s.MODEL_NATIVE == MODEL_NATIVE_STANDARD
    assert s.MODEL_NATIVE == "gemini-2.5-flash-native-audio-preview-12-2025"


def test_premium_tier_resolves_to_3_1_live():
    s = Settings(USE_PREMIUM_MODEL=True, MODEL_NATIVE="")
    assert s.MODEL_NATIVE == MODEL_NATIVE_PREMIUM
    assert s.MODEL_NATIVE == "gemini-3.1-flash-live-preview"


def test_default_resolves_to_3_1_premium():
    """Regression: with NO flag supplied, the default tier is premium/3.1.

    bd polyglot-pdf-4p0 flipped the `USE_PREMIUM_MODEL` field default to true
    because the 2.5 native-audio preview is flaky on the audio path
    (bd polyglot-pdf-daa). Pin the no-arg default so a future accidental flip
    back to 2.5 is caught here. The field default is read from os.getenv at
    class-definition time, so an explicit `USE_PREMIUM_MODEL` env override would
    invalidate this assertion — skip in that case rather than report a false fail.
    """
    if os.getenv("USE_PREMIUM_MODEL") is not None:
        pytest.skip("USE_PREMIUM_MODEL is set in the env; can't assert the code default")
    s = Settings(MODEL_NATIVE="")  # USE_PREMIUM_MODEL left at its field default
    assert s.USE_PREMIUM_MODEL is True
    assert s.MODEL_NATIVE == MODEL_NATIVE_PREMIUM == "gemini-3.1-flash-live-preview"


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
