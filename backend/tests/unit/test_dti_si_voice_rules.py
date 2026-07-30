"""Spec for the 2026-07-16 voice-misfire SI rules (bd polyglot-pdf-oqkj + h7wx).

Tester-driven gaps in the DTI system instruction and injection templates:
  - dates: the model forwarded the field's format requirement to the USER
    ("give it as year, month, day") instead of converting a naturally spoken
    date itself;
  - options: labels reach the model in English only, and it sometimes read
    them aloud verbatim in a Spanish session (Male/Female; a residency type);
  - language slips: es->pt word substitutions ("distrito quintal") -- Google's
    documented power phrasing is "RESPOND UNMISTAKABLY IN <language>"
    (docs/genai_docs/live-api-best-practices.md), now carried by the SI, both
    initiating templates, and the per-injection spoken-language anchor;
  - read-back: confirmation values must come from the update tool's
    stored-value echo (bd h7wx), never the model's own memory, and the model
    must never fill a value the user did not say (live phantom "12345678").

These tests pin the RULE TEXT (content contracts, ASCII-only per scar #6), in
the style of test_recovery_prompt.py.
"""
import re

from backend.config import Settings
from backend.services.ai_context import render_field_guidance


SIMPLE_FIELD = {
    "id": "p1_city",
    "name": "City or Town",
    "spoken_name": "city or town",
    "type": "text",
}


def _settings() -> Settings:
    # A fresh instance, NOT the lru_cached get_settings() singleton (test-order
    # isolation; bd memory get-settings-singleton-test-ordering-trap).
    return Settings()


# --- DATES rule (bd oqkj) ---------------------------------------------------

def test_dti_si_has_dates_rule_convert_yourself():
    si = _settings().DTI_SYSTEM_INSTRUCTION
    assert "DATES:" in si
    assert "NEVER ask the user to restate a date" in si
    assert "YOURSELF" in si


# --- Option-label language rule (bd oqkj) ------------------------------------

def test_dti_si_forbids_verbatim_english_option_labels():
    si = _settings().DTI_SYSTEM_INSTRUCTION
    assert "NEVER read an English label aloud verbatim" in si
    # The English value stays reserved for the tool call.
    assert "only for the tool call" in si


# --- UNMISTAKABLY language lock (bd oqkj) -------------------------------------

def test_dti_si_carries_unmistakably_language_lock():
    si = _settings().DTI_SYSTEM_INSTRUCTION
    assert "UNMISTAKABLY" in si


def test_initiating_templates_carry_unmistakably():
    s = _settings()
    assert "UNMISTAKABLY in {spoken_language}" in s.INITIATING_MESSAGE
    assert "UNMISTAKABLY in {spoken_language}" in s.RESUME_INITIATING_MESSAGE


def test_per_injection_anchor_carries_unmistakably():
    text = render_field_guidance(
        SIMPLE_FIELD, fill_language="English", spoken_language="Spanish"
    )
    # The ghv4 anchor survives...
    assert "Speak Spanish aloud" in text
    # ...and now carries the power phrasing on EVERY injection.
    assert "respond UNMISTAKABLY in Spanish" in text


# --- Read-back-from-echo + never-fill-unspoken (bd h7wx) ----------------------

def test_dti_si_workflow_reads_back_from_stored_value_echo():
    si = _settings().DTI_SYSTEM_INSTRUCTION
    assert "stored_values" in si
    assert "NEVER read a value back from your own memory" in si


def test_dti_si_forbids_filling_unspoken_values():
    si = _settings().DTI_SYSTEM_INSTRUCTION
    assert "NEVER fill a field with a value the user has not explicitly given" in si


# --- Recovery prompt level 1 (bd yo5t) ----------------------------------------

def test_recovery_level_1_forbids_filling_before_answer():
    prompt = _settings().RECOVERY_PROMPT_LEVEL_1
    assert "Do not fill or change any field until the user answers" in prompt


# --- ARTICULATION / diction rules (bd polyglot-pdf-e1x9) ----------------------
# The voice model slurred and mispronounced words. The DTI SI's SPEECH STYLE
# block already covered PACE (slow) and per-character read-back; these rules add
# ARTICULATION, which it did not cover. Pinned on BOTH SIs -- USE_DTI=true is the
# production default, but the legacy path must not silently regress.

def _both_sis():
    s = _settings()
    return (
        ("DTI_SYSTEM_INSTRUCTION", s.DTI_SYSTEM_INSTRUCTION),
        ("SYSTEM_INSTRUCTION", s.SYSTEM_INSTRUCTION),
    )


def test_both_sis_carry_articulation_rule():
    for name, si in _both_sis():
        assert "ARTICULATION" in si, f"{name} lost the articulation block"
        # The end of a word is the specific casualty of slurred speech.
        assert "full value through to the END of the word" in si, name


def test_articulation_generalizes_beyond_inflected_languages():
    # 17+ session languages, not all Indo-European: "word endings" is
    # meaningless in tonal/syllable-timed languages (Chinese, Vietnamese,
    # Thai, Japanese), so the rule names their equivalent failure mode too.
    for name, si in _both_sis():
        assert "tones or on evenly-timed syllables" in si, name
        assert "keep every tone and syllable distinct" in si, name


def test_articulation_is_scoped_to_delivery_not_word_choice():
    # Guards against the model reading "no casual contractions" as a licence
    # to drop the warm, conversational REGISTER.
    for name, si in _both_sis():
        assert "govern DELIVERY only, not" in si, name
        assert "never the same as being formal or stiff" in si, name


def test_both_sis_forbid_slurring_and_rushing():
    for name, si in _both_sis():
        for phrase in ("slur", "swallow syllables", "rush through a sentence"):
            assert phrase in si, f"{name} missing: {phrase}"


def test_both_sis_require_clause_pauses():
    for name, si in _both_sis():
        assert "pause between clauses" in si, name


def test_both_sis_forbid_fillers_and_casual_contractions():
    # Simulating casual/disfluent speech is a known audio-degradation trigger.
    for name, si in _both_sis():
        assert "no filler or hesitation sounds" in si, name
        assert "gonna" in si, name


def test_articulation_applies_in_every_language():
    # 17+ session languages: a rule pinned to English only would not travel.
    for name, si in _both_sis():
        assert "This applies in EVERY session language." in si, name


def test_both_sis_carry_the_slower_pace_target():
    # Tester feedback 2026-07-30: still rushing. A concrete relative target
    # beats piling on intensifiers, which saturate.
    for name, si in _both_sis():
        assert "ten percent slower" in si, name
        assert "err on the side of too slow" in si, name


def test_both_sis_forbid_accelerating_mid_sentence():
    # "Rushing" is typically starting well and speeding up, so the sustain
    # rule is pinned separately from the target pace itself.
    for name, si in _both_sis():
        assert "from the FIRST word to the LAST" in si, name
        assert "do not start slowly and then speed up" in si, name


def test_articulation_does_not_contradict_the_slow_pace_rule():
    # The articulation rules EXTEND the existing SPEECH STYLE block; they must
    # not have displaced the pace rule that shares it.
    si = _settings().DTI_SYSTEM_INSTRUCTION
    assert "SPEECH STYLE" in si
    assert "Speak SLOWLY and calmly in every language" in si
    assert si.index("SPEECH STYLE") < si.index("ARTICULATION")


def test_legacy_si_block_order_is_register_then_pace_then_articulation():
    # The legacy SI's rules live in REGISTER, not SPEECH STYLE. Pinned because
    # an earlier revision of this change put BOTH articulation blocks into
    # DTI_SYSTEM_INSTRUCTION by mistake -- nothing would have caught it.
    si = _settings().SYSTEM_INSTRUCTION
    assert si.index("REGISTER") < si.index("PACE:") < si.index("ARTICULATION")


def test_each_si_has_exactly_one_articulation_block():
    for name, si in _both_sis():
        assert si.count("ARTICULATION (say every word clearly)") == 1, name


# --- ASCII-only guard for every constant this change touched (scar #6) --------

def test_touched_constants_are_ascii_only():
    s = _settings()
    for name in (
        "DTI_SYSTEM_INSTRUCTION",
        "SYSTEM_INSTRUCTION",
        "INITIATING_MESSAGE",
        "RESUME_INITIATING_MESSAGE",
        "RECOVERY_PROMPT_LEVEL_1",
    ):
        value = getattr(s, name)
        assert not re.search(r"[^\x00-\x7F]", value), (
            f"{name} contains non-ASCII characters (scar #6)"
        )
