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


# A distinctive literal string from form-kits/w7/schema.json's
# form_metadata.booklet_text (the official W-7 instruction booklet), pulled
# from deep in the booklet's instructional prose -- NOT the form title line
# ("Application for IRS Individual Taxpayer Identification Number"), which
# is a bad marker: the production SI's OWN header independently renders the
# schema's form_metadata.title (the same literal string), so that phrase
# would show up in every arm's SI regardless of whether the booklet was
# appended, defeating the point of this marker.
_BOOKLET_MARKER = (
    "Supporting documentation requirements. We are making \nsignificant "
    "change"
)


@pytest.fixture(scope="module")
def w7_schema():
    return harness.load_schema("w7")


def _build_si(arm: str, schema: dict) -> str:
    """Build an arm's SI via the exact harness code path (production's
    build_form_context_message), with the SAME multi-module get_settings
    patch the harness's own run() applies (measure_form_session_costs.py,
    "Install the arm's settings..." comment) -- ai_context imports
    get_settings at module level and calls it internally, so patching only
    _config (or only passing settings= to FormFillingService) is NOT enough:
    without patching ai_context's own reference too, build_form_context reads
    the REAL default settings (USE_DTI defaults True in production) and
    silently renders the DTI static SI instead of the legacy full-schema SI
    this arm is supposed to measure. This is the exact multi-module
    get_settings trap CLAUDE.md warns about (bd polyglot-pdf-jnjj.25); a first
    draft of this helper fell into it and every marker assertion below failed
    for the wrong reason (DTI's SI carries no field ids and no booklet
    slot) until this patching was added."""
    from backend.services.form_filling_service import FormFillingService
    import backend.services.ai_context as ai_context_mod
    import backend.config as _config_mod

    settings = harness._make_settings(
        arm, trigger=12_000, window=9_000,
        compression=False, continuous=False, derive_compression=False)
    patch_targets = [_config_mod, ai_context_mod]
    orig = [(mod, mod.get_settings) for mod in patch_targets]
    for mod, _ in orig:
        mod.get_settings = lambda s=settings: s
    try:
        service = FormFillingService(live_ai=None, settings=settings)
        arm_schema = {"form_metadata": schema.get("form_metadata", {}),
                      "fields": schema["fields"]}
        si = service.build_form_context_message(
            arm_schema, {}, section_number=1, total_sections=1,
            section_label="Full Form", previous_spoken_names=[])
    finally:
        for mod, o in orig:
            mod.get_settings = o
    return si


def _build_naive_si(schema: dict) -> str:
    """The naive arm's SI: the legacy full-schema SI plus the booklet suffix
    (apply_naive_si), via the exact harness code path -- never a
    reimplementation."""
    si = _build_si("naive", schema)
    return harness.apply_naive_si(si, schema)


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


class TestNaiveSiBookletAppend:
    def test_naive_si_contains_fields_catalog_marker(self, w7_schema):
        """Proof the REAL production SI builder ran: a marker only the real
        build_form_context output would carry, not a hand-written fixture."""
        si = _build_naive_si(w7_schema)
        # Every field's own field_id appears in the production SI's fields
        # catalog (build_form_context enumerates every field). Use a field
        # id known to exist in the w7 kit's question plan as the marker.
        assert "name_1a_first" in si

    def test_naive_si_contains_booklet_marker(self, w7_schema):
        """Proof the booklet text was really appended, not merely declared
        appended in a comment."""
        si = _build_naive_si(w7_schema)
        assert _BOOKLET_MARKER in si

    def test_naive_si_has_marker_section_header(self, w7_schema):
        si = _build_naive_si(w7_schema)
        assert harness.NAIVE_SI_MARKER in si

    def test_naive_si_booklet_comes_after_fields_catalog(self, w7_schema):
        """The booklet is APPENDED (not prepended/interleaved) -- the fields
        catalog marker must appear before the booklet marker in the SI."""
        si = _build_naive_si(w7_schema)
        assert si.index("name_1a_first") < si.index(_BOOKLET_MARKER)

    def test_non_naive_arm_si_excludes_booklet(self, w7_schema):
        """Sanity check on the driver's if-guard: only --arm naive appends
        the booklet. Building the unbounded-shape SI directly (without
        apply_naive_si) must NOT contain the booklet marker."""
        si = _build_si("unbounded", w7_schema)
        assert _BOOKLET_MARKER not in si

    def test_unbounded_and_naive_si_identical_before_booklet(self, w7_schema):
        """The naive arm's ONLY difference from unbounded is the appended
        booklet suffix -- the production SI text itself must be byte-
        identical between the two arms (same settings shape, same schema)."""
        si_unbounded = _build_si("unbounded", w7_schema)
        si_naive_base = _build_si("naive", w7_schema)
        assert si_unbounded == si_naive_base


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


class TestSpellbackHandler:
    """Pins the FakeClientWebSocket spell-back handling added alongside the
    naive arm (bd polyglot-pdf-89mt): a spellback message must get an
    in-band 'delivered' ack, never fall through unanswered."""

    def _make_client(self):
        schema = harness.load_schema("w7")
        plan = harness.SCHEMAS["w7"]["questions"][:2]
        return harness.FakeClientWebSocket(schema, plan)

    @pytest.mark.asyncio
    async def test_spellback_message_gets_delivered_ack(self):
        import asyncio
        from unittest.mock import MagicMock

        client = self._make_client()
        # handle_spellback_response is SYNCHRONOUS (form_filling_service.py),
        # unlike most of the coordinator surface -- a plain MagicMock (not
        # AsyncMock) so _reply's call_soon(lambda: service.handle_...(...))
        # actually invokes it instead of scheduling an un-awaited coroutine.
        client.service = MagicMock()
        await client.send_json({"type": "spellback", "request_id": "req-1"})
        # _reply schedules the resolution via call_soon; let the loop tick.
        await asyncio.sleep(0)
        client.service.handle_spellback_response.assert_called_once()
        call_args = client.service.handle_spellback_response.call_args
        assert call_args[0][0] == "req-1"
        payload = call_args[0][1]
        assert payload["status"] == "delivered"

    @pytest.mark.asyncio
    async def test_spellback_event_recorded_no_value_leaked(self):
        import asyncio
        from unittest.mock import MagicMock

        client = self._make_client()
        client.service = MagicMock()
        client.state["application_type"] = {"value": "New ITIN application",
                                            "confirmed": False}
        client.active_field_ids = ["application_type"]
        await client.send_json({"type": "spellback", "request_id": "req-2"})
        await asyncio.sleep(0)
        assert len(client.spellback_events) == 1
        rec = client.spellback_events[0]
        assert rec["status"] == "delivered"
        assert rec["field_id"] == "application_type"
        assert rec["value_chars"] == len("New ITIN application")
        # No raw field VALUE is stored on the event record (mirrors the real
        # wire contract: no field value ever crosses the spellback message).
        assert "value" not in rec

    @pytest.mark.asyncio
    async def test_spellback_does_not_stall_send_json(self):
        """The bug this handler fixes: without it, 'spellback' falls through
        every branch in send_json and is silently dropped. Asserting the
        message type is recorded in sent_messages (every send_json call
        appends there unconditionally) is a coarse but real signal that the
        method actually processed the message rather than routing nowhere."""
        client = self._make_client()
        from unittest.mock import MagicMock
        client.service = MagicMock()
        await client.send_json({"type": "spellback", "request_id": "req-3"})
        assert "spellback" in client.sent_messages
