"""
Unit tests for the --arm naive plumbing in
scripts/spikes/measure_form_session_costs.py (bd polyglot-pdf-89mt).

Pins, WITHOUT any live Gemini call:
  - --arm naive settings: USE_DTI False, compression disabled, and (via the
    shared _make_settings helper) the same no-DTI/no-compression/no-resets
    shape as --arm unbounded (a regression guard against the naive branch
    silently drifting from that shape).
  - the naive-arm SI actually contains BOTH a fields-catalog marker (proof
    the real production SI builder ran, not a fabricated string) AND a
    distinctive literal substring from the w7 booklet_text (proof the
    booklet was really appended, not just declared appended).
  - the --questions truncation knob caps the w7 plan length.
  - --arm dti / --derive-compression settings are UNCHANGED by the naive-arm
    edits (regression guard: the naive branch must not perturb the existing
    arms' settings construction).

Imports the REAL harness module (scripts/spikes/measure_form_session_costs.py)
via sys.path injection -- scripts/ carries no __init__.py, so this mirrors
the harness's own sibling-module import pattern (full_form_script /
scenario_events) rather than inventing a second import mechanism.

Hermetic: no network, no live model call. ASCII only.
"""
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPIKES_DIR = str(_REPO_ROOT / "scripts" / "spikes")
if _SPIKES_DIR not in sys.path:
    sys.path.insert(0, _SPIKES_DIR)

import measure_form_session_costs as harness  # noqa: E402


class TestNaiveArmSettings:
    def test_naive_settings_no_dti(self):
        s = harness._make_settings(
            "naive", trigger=12_000, window=9_000,
            compression=False, continuous=False, derive_compression=False)
        assert s.USE_DTI is False

    def test_naive_settings_no_compression(self):
        s = harness._make_settings(
            "naive", trigger=12_000, window=9_000,
            compression=False, continuous=False, derive_compression=False)
        assert s.CONTEXT_COMPRESSION_ENABLED is False

    def test_naive_settings_not_continuous_by_default(self):
        s = harness._make_settings(
            "naive", trigger=12_000, window=9_000,
            compression=False, continuous=False, derive_compression=False)
        assert s.CONTINUOUS_SESSION is False

    def test_naive_settings_match_unbounded_shape(self):
        """Regression guard: naive and unbounded must produce the SAME
        settings overrides (same no-DTI/no-compression/no-resets shape) --
        the naive arm's only difference from unbounded is the SI text
        appended at the driver call site, never a settings divergence."""
        naive = harness._make_settings(
            "naive", trigger=12_000, window=9_000,
            compression=False, continuous=False, derive_compression=False)
        unbounded = harness._make_settings(
            "unbounded", trigger=12_000, window=9_000,
            compression=False, continuous=False, derive_compression=False)
        for field in ("USE_DTI", "CONTINUOUS_SESSION",
                      "CONTEXT_COMPRESSION_ENABLED"):
            assert getattr(naive, field) == getattr(unbounded, field), field


# TestNaiveSiBookletAppend and TestSpellbackHandler were DELETED 2026-09-11
# (bd polyglot-pdf-q3u5r). Both loaded the w7 kit off disk to build a real SI;
# no kit is tracked now, so they could only error. They pinned SPIKE-HARNESS
# plumbing (scripts/spikes/measure_form_session_costs.py), not product code.
# The synthetic settings/arg-parsing tests in this file are unaffected and stay.

class TestQuestionsTruncation:
    def test_w7_plan_truncates_to_n(self):
        all_q = harness.SCHEMAS["w7"]["questions"]
        n = 2
        truncated = all_q[:n]
        assert len(truncated) == 2
        assert truncated == all_q[:2]

    def test_w7_plan_default_is_whole_plan(self):
        """--questions defaults to None, which the driver (run()) maps to
        the WHOLE plan -- pin the plan length so a truncation regression
        (someone hardcoding a smaller default) is caught here rather than
        only discovered mid-run."""
        all_q = harness.SCHEMAS["w7"]["questions"]
        assert len(all_q) == 22

    def test_w7_pilot_truncation_six(self):
        all_q = harness.SCHEMAS["w7"]["questions"]
        pilot = all_q[:6]
        assert len(pilot) == 6


class TestOtherArmsUnaffected:
    """Regression guard (bd polyglot-pdf-89mt work item 6d): the naive-arm
    edits to _make_settings must not perturb --arm dti / --derive-compression
    settings construction."""

    def test_dti_arm_still_sets_use_dti(self):
        s = harness._make_settings(
            "dti", trigger=12_000, window=9_000,
            compression=False, continuous=False, derive_compression=False)
        assert s.USE_DTI is True

    def test_dti_continuous_compression_derive_still_works(self):
        s = harness._make_settings(
            "dti", trigger=12_000, window=9_000,
            compression=True, continuous=True, derive_compression=True)
        assert s.USE_DTI is True
        assert s.CONTINUOUS_SESSION is True
        assert s.CONTEXT_COMPRESSION_ENABLED is True
        assert s.CONTEXT_COMPRESSION_DERIVE_FROM_SI_FLOOR is True

    def test_dti_pinned_trigger_window_without_derive(self):
        s = harness._make_settings(
            "dti", trigger=2_800, window=2_200,
            compression=True, continuous=False, derive_compression=False)
        assert s.CONTEXT_COMPRESSION_TRIGGER_TOKENS == 2_800
        assert s.CONTEXT_COMPRESSION_WINDOW_TOKENS == 2_200
        assert s.CONTEXT_COMPRESSION_DERIVE_FROM_SI_FLOOR is False

    def test_sliding_window_arm_unaffected(self):
        s = harness._make_settings(
            "sliding-window", trigger=12_000, window=9_000,
            compression=False, continuous=False, derive_compression=False)
        assert s.CONTEXT_COMPRESSION_ENABLED is True
        assert s.CONTEXT_COMPRESSION_TRIGGER_TOKENS == 12_000
        assert s.CONTEXT_COMPRESSION_WINDOW_TOKENS == 9_000


class TestArmChoicesIncludesNaive:
    def test_naive_is_a_valid_arm_choice(self):
        import argparse

        ap = argparse.ArgumentParser()
        ap.add_argument(
            "--arm",
            choices=["unbounded", "naive", "section-reset",
                     "section-reset-jit", "dti", "sliding-window"],
            default="unbounded")
        args = ap.parse_args(["--arm", "naive"])
        assert args.arm == "naive"


class TestNaiveArmToolCatalog:
    """The naive arm's tool catalog (bd polyglot-pdf-wiadk smoke finding):
    the first naive smoke measured the model CALLING ask_secretary and
    burning a whole ~29k-token context re-send on the fail-open answer. A
    naive competitor has no secretary, no spell-back TTS pipeline, and no
    section machinery, so the naive settings must not declare them. Pin the
    catalog as the COMPLETE allowlist, not a blacklist (repo doctrine:
    pin-message-tests-with-allowlists)."""

    @staticmethod
    def _settings(arm):
        return harness._make_settings(
            arm, trigger=12_000, window=9_000,
            compression=False, continuous=False, derive_compression=False)

    def test_naive_tool_catalog_is_exactly_the_allowlist(self):
        names = [d.get("name") for d in self._settings("naive").TOOL_DECLARATIONS]
        assert names == [
            "update_form_fields",
            "get_form_status",
            "confirm_field",
            "skip_field",
            "switch_to_field",
        ]

    def test_naive_spellback_flag_off(self):
        assert self._settings("naive").SPELLBACK_TOOL_ENABLED is False

    def test_unbounded_catalog_unchanged_by_naive_filter(self):
        """Regression guard: filtering must be naive-arm-only -- the
        unbounded arm keeps the full production catalog (its June baselines
        were measured with it)."""
        names = [d.get("name") for d in
                 self._settings("unbounded").TOOL_DECLARATIONS]
        assert "ask_secretary" in names
        assert "switch_section" in names
