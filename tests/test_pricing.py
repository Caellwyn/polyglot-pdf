"""Tests for family-keyed Gemini pricing (bd polyglot-pdf-lky).

The cost calc must select the right per-token rate row based on the active
model's family, so a 2.5 vs 3.1 A/B is costed with each family's real rates.
"""
from __future__ import annotations

import pytest

from backend.config import (
    DEFAULT_PRICING_FAMILY,
    GEMINI_PRICING_BY_FAMILY,
    get_pricing_for_model,
    model_family,
)


# A fixed token bundle reused across rate assertions.
TEXT_IN = 1_000_000
AUDIO_IN = 1_000_000
TEXT_OUT = 1_000_000
AUDIO_OUT = 1_000_000


def _cost(model_name: str) -> float:
    """Total cost for 1M tokens in each modality, at the model's family rates."""
    p = get_pricing_for_model(model_name)
    return (
        TEXT_IN * p["text_input"]
        + AUDIO_IN * p["audio_input"]
        + TEXT_OUT * p["text_output"]
        + AUDIO_OUT * p["audio_output"]
    )


class TestModelFamilyMapping:
    @pytest.mark.parametrize(
        "model_name,expected",
        [
            ("gemini-live-2.5-flash-native-audio", "2.5"),
            ("gemini-live-2.5-flash-preview", "2.5"),
            ("gemini-3.1-flash-live-preview", "3.1"),
            ("GEMINI-3.1-FLASH-LIVE-PREVIEW", "3.1"),  # case-insensitive
        ],
    )
    def test_known_models_map_to_family(self, model_name, expected):
        assert model_family(model_name) == expected

    @pytest.mark.parametrize(
        "model_name,expected",
        [
            # Real model IDs verified against ai.google.dev/gemini-api/docs
            # (and pricing) on 2026-05-30 — pins the mapping to reality, not
            # just synthetic names. The "-preview-12-2025" suffix must NOT let
            # the "12-2025" date false-match family "2.5".
            ("gemini-2.5-flash-native-audio-preview-12-2025", "2.5"),
            ("gemini-2.5-flash-native-audio-latest", "2.5"),
            ("gemini-3.1-flash-live-preview", "3.1"),
            ("gemini-3.1-flash-tts-preview", "3.1"),
        ],
    )
    def test_real_google_model_ids_map_correctly(self, model_name, expected):
        assert model_family(model_name) == expected

    @pytest.mark.parametrize("model_name", ["", None, "gemini-9.9-unknown", "banana"])
    def test_unknown_models_fall_back_to_default(self, model_name):
        assert model_family(model_name) == DEFAULT_PRICING_FAMILY

    @pytest.mark.parametrize(
        "model_name",
        [
            "gemini-3.10-flash-live-preview",  # '3.1' must NOT match '3.10'
            "gemini-3.11-flash",
            "gemini-12.5-turbo",               # '2.5' must NOT match '12.5'
            "gemini-2.50-flash",               # '2.5' must NOT match '2.50'
        ],
    )
    def test_version_prefix_collisions_do_not_false_match(self, model_name):
        # A future version whose number merely starts with a known family key
        # must fall back to default, not silently bill at the wrong family.
        assert model_family(model_name) == DEFAULT_PRICING_FAMILY

    def test_first_listed_family_wins_when_name_contains_both(self):
        # Contrived, but pins the deterministic tie-break (insertion order).
        assert model_family("gemini-2.5-vs-3.1-comparison") == "2.5"


class TestFamilyKeyedRates:
    def test_known_token_count_yields_2_5_rate(self):
        # 2.5: 0.50 + 3.00 + 2.00 + 12.00 per 1M each = $17.50 for the bundle.
        assert _cost("gemini-live-2.5-flash-native-audio") == pytest.approx(17.50)

    def test_known_token_count_yields_3_1_rate(self):
        # 3.1: 0.75 + 3.00 + 4.50 + 12.00 per 1M each = $20.25 for the bundle.
        assert _cost("gemini-3.1-flash-live-preview") == pytest.approx(20.25)

    def test_2_5_and_3_1_costs_differ(self):
        # The whole point of family keying: same tokens, different bill.
        assert _cost("gemini-live-2.5-flash-native-audio") != _cost(
            "gemini-3.1-flash-live-preview"
        )

    def test_per_token_rates_are_per_1m_divided(self):
        p25 = get_pricing_for_model("gemini-live-2.5-flash-native-audio")
        assert p25["text_input"] == pytest.approx(0.50 / 1_000_000)
        assert p25["audio_output"] == pytest.approx(12.00 / 1_000_000)
        p31 = get_pricing_for_model("gemini-3.1-flash-live-preview")
        assert p31["text_input"] == pytest.approx(0.75 / 1_000_000)
        assert p31["audio_input"] == pytest.approx(3.00 / 1_000_000)
        assert p31["text_output"] == pytest.approx(4.50 / 1_000_000)
        assert p31["audio_output"] == pytest.approx(12.00 / 1_000_000)


class TestBackwardCompatAlias:
    def test_default_family_is_present(self):
        assert DEFAULT_PRICING_FAMILY in GEMINI_PRICING_BY_FAMILY

    def test_legacy_gemini_pricing_alias_matches_default_family(self):
        # Old code importing GEMINI_PRICING must keep getting the default rates.
        from backend.config import GEMINI_PRICING

        assert GEMINI_PRICING == GEMINI_PRICING_BY_FAMILY[DEFAULT_PRICING_FAMILY]

    def test_alias_is_a_copy_not_the_live_family_dict(self):
        # Mutating the alias must NOT corrupt the family dict for other callers.
        import backend.config as cfg

        original = cfg.GEMINI_PRICING_BY_FAMILY[DEFAULT_PRICING_FAMILY]["text_input"]
        cfg.GEMINI_PRICING["text_input"] = 999.0
        try:
            assert (
                cfg.GEMINI_PRICING_BY_FAMILY[DEFAULT_PRICING_FAMILY]["text_input"]
                == original
            )
        finally:
            cfg.GEMINI_PRICING["text_input"] = original
