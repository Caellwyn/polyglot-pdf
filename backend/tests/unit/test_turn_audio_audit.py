"""
Unit tests for the Live-model measurement instruments (bd polyglot-pdf-r3ham.1,
bd polyglot-pdf-uzecd):

  - scripts/spikes/turn_audio_audit.py classifies the developer-reported
    gemini-3.8-live audio defects: silent_turn (transcript present, audio
    empty), silent_after_tool, missing_completion, runaway_audio.
  - measure_form_session_costs.py's FakeClientWebSocket feeds the audit from
    the real backend->client surfaces (send_bytes audio, transcript messages).
  - --model tiers resolve to honest ids: "2.5" is the explicit 2.5 native-audio
    id (never the 3.8 production constant) and "3.8" is the production tier,
    in BOTH measure_form_session_costs.py and diag_compression_matrix_sdk28.py.

Hermetic: no network, no live model call. ASCII only.
"""
import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPIKES_DIR = str(_REPO_ROOT / "scripts" / "spikes")
if _SPIKES_DIR not in sys.path:
    sys.path.insert(0, _SPIKES_DIR)

import turn_audio_audit as taa  # noqa: E402
import measure_form_session_costs as harness  # noqa: E402

from backend.config import (  # noqa: E402
    MODEL_NATIVE_PREMIUM,
    MODEL_NATIVE_STANDARD,
    MODEL_NATIVE_STANDARD_VERTEX,
    TEXT_GENERATION_PRICING,
    model_family,
)

# 24 kHz PCM16 mono: 48 bytes per millisecond.
_BYTES_PER_MS = 48


def _ms(n_ms: float) -> int:
    return int(n_ms * _BYTES_PER_MS)


class TestSilentTurn:
    def test_transcript_without_audio_is_flagged(self):
        a = taa.TurnAudioAudit()
        a.transcript("Please spell your last name.", 1.0)
        a.boundary("turn_complete", 1.5)
        s = a.finalize(2.0)
        assert s["silent_turn"] == 1
        assert a.turns[0]["flags"]["silent_turn"] is True

    def test_transcript_with_near_silent_audio_is_flagged(self):
        a = taa.TurnAudioAudit()
        a.audio(_ms(120), 1.0)
        a.transcript("What is your date of birth?", 1.1)
        a.boundary("turn_complete", 1.5)
        assert a.finalize(2.0)["silent_turn"] == 1

    def test_spoken_turn_is_not_flagged(self):
        a = taa.TurnAudioAudit()
        a.audio(_ms(2500), 1.0)
        a.transcript("What is your date of birth?", 1.1)
        a.boundary("turn_complete", 4.0)
        s = a.finalize(5.0)
        assert s["silent_turn"] == 0
        assert s["transcript_observed"] is True

    def test_threshold_edge(self):
        # Exactly at the threshold is NOT silent; just under it is.
        a = taa.TurnAudioAudit()
        a.audio(_ms(taa.SILENT_AUDIO_MS), 1.0)
        a.transcript("x", 1.0)
        a.boundary("turn_complete", 2.0)
        b = taa.TurnAudioAudit()
        b.audio(_ms(taa.SILENT_AUDIO_MS) - 2, 1.0)
        b.transcript("x", 1.0)
        b.boundary("turn_complete", 2.0)
        assert a.finalize(3.0)["silent_turn"] == 0
        assert b.finalize(3.0)["silent_turn"] == 1


class TestSilentAfterTool:
    def test_tool_then_no_audio_is_flagged(self):
        a = taa.TurnAudioAudit()
        a.user_turn_end(0.0)
        a.tool_call("update_form_fields", 1.0)
        a.boundary("turn_complete", 1.2)
        a.user_turn_end(5.0)
        s = a.finalize(6.0)
        assert s["silent_after_tool"] == 1

    def test_audio_before_tool_does_not_count_as_after(self):
        a = taa.TurnAudioAudit()
        a.user_turn_end(0.0)
        a.audio(_ms(3000), 0.5)
        a.tool_call("update_form_fields", 1.0)
        a.boundary("turn_complete", 1.2)
        assert a.finalize(6.0)["silent_after_tool"] == 1

    def test_speech_between_tools_then_silence_after_last_is_flagged(self):
        # Only audio after the LAST call counts: speech after call A must not
        # mask silence after call B.
        a = taa.TurnAudioAudit()
        a.user_turn_end(0.0)
        a.tool_call("update_form_fields", 1.0)
        a.audio(_ms(2000), 1.2)
        a.tool_call("confirm_field", 3.5)
        a.boundary("turn_complete", 3.7)
        assert a.finalize(6.0)["silent_after_tool"] == 1

    def test_tool_then_speech_is_clean(self):
        a = taa.TurnAudioAudit()
        a.user_turn_end(0.0)
        a.tool_call("update_form_fields", 1.0)
        a.audio(_ms(2000), 1.3)
        a.boundary("turn_complete", 3.5)
        assert a.finalize(6.0)["silent_after_tool"] == 0

    def test_speech_across_a_mid_exchange_boundary_still_counts(self):
        # The server may close a generation at the tool call and open a new one
        # for the post-tool speech; the exchange-level check must not care.
        a = taa.TurnAudioAudit()
        a.user_turn_end(0.0)
        a.tool_call("update_form_fields", 1.0)
        a.boundary("turn_complete", 1.1)
        a.audio(_ms(2000), 1.4)
        a.boundary("turn_complete", 3.5)
        assert a.finalize(6.0)["silent_after_tool"] == 0

    @pytest.mark.parametrize("tool", sorted(taa.SILENT_OK_TOOLS))
    def test_silent_contract_tools_are_exempt(self, tool):
        a = taa.TurnAudioAudit()
        a.user_turn_end(0.0)
        a.tool_call(tool, 1.0)
        a.boundary("turn_complete", 1.2)
        assert a.finalize(6.0)["silent_after_tool"] == 0

    def test_exchange_without_tools_is_not_flagged(self):
        a = taa.TurnAudioAudit()
        a.user_turn_end(0.0)
        a.boundary("turn_complete", 1.0)
        assert a.finalize(2.0)["silent_after_tool"] == 0


class TestCompletionAndRunaway:
    def test_audio_with_no_boundary_before_next_user_turn(self):
        a = taa.TurnAudioAudit()
        a.audio(_ms(1500), 1.0)
        a.user_turn_end(4.0)
        s = a.finalize(5.0)
        assert s["missing_completion"] == 1
        assert a.turns[0]["end_reason"] == "next_user_turn"

    def test_audio_open_at_run_end(self):
        a = taa.TurnAudioAudit()
        a.audio(_ms(1500), 1.0)
        assert a.finalize(5.0)["missing_completion"] == 1

    @pytest.mark.parametrize("reason", ["turn_complete", "interrupted",
                                        "session_close"])
    def test_real_boundaries_complete_the_turn(self, reason):
        a = taa.TurnAudioAudit()
        a.audio(_ms(1500), 1.0)
        a.boundary(reason, 2.0)
        assert a.finalize(5.0)["missing_completion"] == 0

    @pytest.mark.parametrize("reason,expected", [
        ("turn_complete", True), ("interrupted", False),
        ("session_close", False), ("next_user_turn", False), ("run_end", False)])
    def test_per_turn_turn_complete_field(self, reason, expected):
        a = taa.TurnAudioAudit()
        a.audio(_ms(1500), 1.0)
        if reason == "next_user_turn":
            a.user_turn_end(2.0)
        elif reason != "run_end":
            a.boundary(reason, 2.0)
        a.finalize(5.0)
        assert a.turns[0]["turn_complete"] is expected

    def test_buffer_cap_does_not_split_a_runaway_turn(self):
        a = taa.TurnAudioAudit()
        a.audio(_ms(15_000), 1.0)
        a.boundary("buffer_cap", 16.0)
        a.audio(_ms(10_000), 16.0)
        a.boundary("turn_complete", 26.5)
        s = a.finalize(27.0)
        assert s["turns"] == 1
        assert s["runaway_audio"] == 1

    def test_buffer_cap_is_not_a_boundary(self):
        a = taa.TurnAudioAudit()
        a.audio(_ms(1500), 1.0)
        a.boundary("buffer_cap", 1.5)
        a.user_turn_end(4.0)
        assert a.finalize(5.0)["missing_completion"] == 1

    def test_duplicate_boundary_is_counted_not_flagged(self):
        a = taa.TurnAudioAudit()
        a.audio(_ms(1500), 1.0)
        a.boundary("turn_complete", 2.0)
        a.boundary("turn_complete", 2.01)
        s = a.finalize(5.0)
        assert s["turns"] == 1
        assert s["empty_boundaries"] == 1

    def test_runaway_audio(self):
        a = taa.TurnAudioAudit()
        a.audio(_ms(taa.RUNAWAY_AUDIO_MS + 1000), 1.0)
        a.boundary("turn_complete", 30.0)
        b = taa.TurnAudioAudit()
        b.audio(_ms(5000), 1.0)
        b.boundary("turn_complete", 7.0)
        assert a.finalize(31.0)["runaway_audio"] == 1
        assert b.finalize(8.0)["runaway_audio"] == 0


class TestFakeClientFeedsAudit:
    def _client(self):
        return harness.FakeClientWebSocket({"fields": []}, [])

    def test_send_bytes_feeds_audio(self):
        c = self._client()
        asyncio.run(c.send_bytes(b"\x00" * _ms(1000)))
        c.audit.boundary("turn_complete", 10_000.0)
        assert c.audit.turns[0]["audio_ms"] == pytest.approx(1000.0, abs=1)

    def test_transcript_message_feeds_transcript_chars(self):
        c = self._client()
        asyncio.run(c.send_json({"type": "transcript", "data": "Hello there"}))
        c.audit.boundary("turn_complete", 10_000.0)
        assert c.audit.turns[0]["transcript_chars"] == len("Hello there")
        assert c.audit.summary()["silent_turn"] == 1


class TestModelTierResolution:
    def test_38_is_the_production_tier(self):
        assert harness.resolve_model_id("3.8", vertex=True) == MODEL_NATIVE_STANDARD_VERTEX
        assert harness.resolve_model_id("3.8", vertex=False) == MODEL_NATIVE_STANDARD

    @pytest.mark.parametrize("vertex", [True, False])
    def test_25_is_really_25(self, vertex):
        mid = harness.resolve_model_id("2.5", vertex=vertex)
        assert model_family(mid) == "2.5"
        assert mid not in (MODEL_NATIVE_STANDARD, MODEL_NATIVE_STANDARD_VERTEX)

    def test_31_has_no_vertex_id(self):
        assert harness.resolve_model_id("3.1", vertex=False) == MODEL_NATIVE_PREMIUM
        with pytest.raises(ValueError):
            harness.resolve_model_id("3.1", vertex=True)

    def test_every_tier_label_matches_its_family(self):
        # The uzecd defect: a tier labelled X ran a model of family Y.
        for tier, ids in harness.MODELS.items():
            for svc, mid in ids.items():
                if mid is None:
                    continue
                assert model_family(mid) == tier, (tier, svc, mid)


class TestTextSidecarPricing:
    """The harness prices secretary/validator calls from the canonical
    backend/config.py TEXT_GENERATION_PRICING, so every model the backend can
    call is priced (bd polyglot-pdf-r3ham.1: the harness-local table had no
    3.1-flash-lite row and billed every lite call at the 2.5-pro rate)."""

    @pytest.mark.parametrize("model", sorted(TEXT_GENERATION_PRICING))
    def test_every_canonical_text_model_is_priced(self, model):
        rates, unpriced = harness._rates_for_model(model)
        assert unpriced is False
        row = TEXT_GENERATION_PRICING[model]
        assert rates == {"input": row["text_input"],
                         "cached_input": row["cached_input"],
                         "output": row["text_output"]}

    def test_production_lite_models_are_priced(self):
        from backend.config import Settings
        from backend.adapters.text_ai_gemini import TextAIGemini
        for model in (Settings().MODEL_LABELING,
                      *TextAIGemini.DEFAULT_FALLBACK_MODELS):
            assert harness._rates_for_model(model)[1] is False, model

    def test_lite_call_is_not_priced_at_the_pro_rate(self):
        lite = harness.price_text_usage(10_000, 0, 200, model="gemini-3.1-flash-lite")
        pro = harness.price_text_usage(10_000, 0, 200, model="gemini-2.5-pro")
        assert pro > lite * 3

    def test_unknown_model_still_flags_unpriced(self):
        assert harness._rates_for_model("gemini-99-imaginary")[1] is True


def _load_diag():
    path = Path(_SPIKES_DIR) / "diag_compression_matrix_sdk28.py"
    spec = importlib.util.spec_from_file_location("_diag_matrix_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestDiagMatrixTierResolution:
    def test_tier_labels_match_family(self):
        diag = _load_diag()
        for tier in ("3.8", "2.5", "3.1"):
            assert model_family(diag.MODELS[tier]) == tier, tier
        for tier, mid in diag.VERTEX_IDS.items():
            assert model_family(mid) == tier, (tier, mid)

    def test_vertex_ids_are_exactly_the_tiers_with_a_vertex_model(self):
        diag = _load_diag()
        assert set(diag.VERTEX_IDS) == {"3.8", "2.5"}
        assert diag.VERTEX_IDS["3.8"] == MODEL_NATIVE_STANDARD_VERTEX
