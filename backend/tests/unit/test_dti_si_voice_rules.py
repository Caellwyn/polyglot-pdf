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

import pytest

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
    # not have displaced the pace rule that shares it. Ordering alone is a weak
    # assertion (SPEECH STYLE sits at the top, so it passes trivially), so pin
    # that the pace prose actually lives BETWEEN the two anchors -- otherwise
    # deleting the pace sentences would leave this test green.
    si = _settings().DTI_SYSTEM_INSTRUCTION
    start, end = si.index("SPEECH STYLE"), si.index("ARTICULATION")
    assert start < end
    between = si[start:end]
    for phrase in (
        "Speak SLOWLY and calmly in every language",
        "ten percent slower",
        "from the FIRST word to the LAST",
        # the per-character read-back rule shares this block and must survive
        "N ... G ... U ... Y ... E ... N",
    ):
        assert phrase in between, f"SPEECH STYLE lost: {phrase}"


def test_legacy_si_block_order_is_register_then_pace_then_articulation():
    # The legacy SI's rules live in REGISTER, not SPEECH STYLE. Pinned because
    # an earlier revision of this change put BOTH articulation blocks into
    # DTI_SYSTEM_INSTRUCTION by mistake -- nothing would have caught it.
    si = _settings().SYSTEM_INSTRUCTION
    assert si.index("REGISTER") < si.index("PACE:") < si.index("ARTICULATION")


def test_each_si_has_exactly_one_articulation_block():
    for name, si in _both_sis():
        assert si.count("ARTICULATION (say every word clearly)") == 1, name


def test_articulation_text_is_identical_across_both_sis():
    # The two constants wrap differently in source but must concatenate to the
    # SAME rule. Without this, the copies could drift in any prose no other
    # assertion happens to name, with the whole suite still green.
    def _block(si):
        start = si.index("ARTICULATION (say every word clearly)")
        return si[start:si.index("\n\n", start)]

    s = _settings()
    assert _block(s.DTI_SYSTEM_INSTRUCTION) == _block(s.SYSTEM_INSTRUCTION)


# --- Option recital rules (bd polyglot-pdf-6bq8) ------------------------------
# The voice model summarized or skipped multiple-choice options ("you can pick
# one of the options shown") on W-7 reason (8 options) and I-90 Part 2 Section A
# (12 options). Users may not be able to read the form, so the recital IS their
# access to the choices. The SI carries the behavioral rule; the per-field
# injection carries the count + a compact imperative on exactly the turns that
# have options.

OPTIONS_FIELD = {
    "id": "reason",
    "name": "Reason",
    "spoken_name": "reason for applying",
    "type": "radio",
    "options": [
        {"value": "yes", "label": "Yes"},
        {"value": "no", "label": "No"},
        {"value": "maybe", "label": "Maybe"},
    ],
}


def test_dti_si_carries_presenting_options_rule():
    si = _settings().DTI_SYSTEM_INSTRUCTION
    assert "PRESENTING OPTIONS:" in si
    assert "read EVERY option aloud" in si
    # The user cannot see the form -- the model's voice is the only access.
    assert "your voice is their ONLY access to the choices" in si
    # The observed failure phrasing is banned by naming the sanctioned behavior
    # AND the specific deflection.
    assert "NEVER refer to 'the options shown'" in si


def test_dti_si_forbids_partial_or_summarized_option_lists():
    si = _settings().DTI_SYSTEM_INSTRUCTION
    assert "Never summarize the list" in si
    assert "never skip or merge options" in si
    assert "never stop partway" in si


def test_dti_si_one_at_a_time_phrase_is_prohibition_only():
    # The recital prescription must not share the prohibition's literal phrase:
    # "read ... one option at a time" vs "do NOT walk the options one at a
    # time" collided 270 chars apart (2nd Opus outer review, this PR). The only
    # surviving "one at a time" must live inside the Do-NOT sentence.
    si = _settings().DTI_SYSTEM_INSTRUCTION
    assert si.count("one at a time") == 1
    i = si.index("one at a time")
    assert "Do NOT walk the" in si[max(0, i - 60):i]


def test_dti_si_forbids_one_by_one_yes_no_option_walk():
    # Observed live (this bead's harness run): the model turned an 8-option
    # checkbox_group into "Is it X?" one option per turn -- the user never
    # hears the full set of choices. Banned by name, and the WORKFLOW ask step
    # carries the recital so the numbered steps agree with PRESENTING OPTIONS.
    si = _settings().DTI_SYSTEM_INSTRUCTION
    assert "Do NOT walk the options one at a time as separate yes/no questions" in si
    assert "present the WHOLE list first" in si
    # The recital is wired into WORKFLOW step 1, not only the options block.
    workflow = si[si.index("WORKFLOW:"):si.index("TOOL PROTOCOL:")]
    assert "read EVERY option aloud" in workflow
    assert "never one-by-one as yes/no questions" in workflow


def test_dti_si_licenses_the_long_recital():
    # A brevity-biased audio model shortens what feels too long unless told the
    # length is intended.
    si = _settings().DTI_SYSTEM_INSTRUCTION
    assert "Reading a long list takes a while -- that is expected and correct" in si


def test_initiating_templates_carry_option_recital():
    # The initiating templates are the strongest per-turn directive the model
    # sees at session start. The RESUME template's unqualified "in one short
    # sentence" overrode the SI's recital rule live (a resume onto a choice
    # field compressed 8 options into a yes/no about the first); both templates
    # now scope brevity away from option fields.
    s = _settings()
    for name in ("INITIATING_MESSAGE", "RESUME_INITIATING_MESSAGE"):
        tpl = getattr(s, name)
        assert "read EVERY option aloud" in tpl, name
    # The resume brevity rule survives, but only for option-less fields.
    assert "in one short sentence if the field has no options" in s.RESUME_INITIATING_MESSAGE


def test_dti_si_standard_list_carve_out():
    # Selects (e.g. the 50-state lists) must not force a recital; the carve-out
    # is guidance-marked (the injection marks the list), offer-based, and read
    # in full the moment the user asks or hesitates. "standard list" covers
    # both markers the render emits ("standard list" for selects, "long
    # standard list" for oversized radio/checkbox groups).
    si = _settings().DTI_SYSTEM_INSTRUCTION
    assert "marks as a standard list" in si
    assert "read ALL of it the moment they ask" in si


def test_render_field_guidance_options_carry_count_and_recital_imperative():
    text = render_field_guidance(OPTIONS_FIELD)
    assert (
        "Options (3 -- read ALL 3 aloud when asking; "
        "the user cannot see them): [" in text
    )
    # All options still present, in order.
    assert '"Yes" (use value: yes), "No" (use value: no), "Maybe" (use value: maybe)]' in text


def test_render_field_guidance_select_always_asks_directly():
    # Type scoping (bd polyglot-pdf-s503, maintainer directive): a select/
    # dropdown NEVER gets the read-ALL imperative, whatever its count -- the
    # 50-state lists and the height feet/inches numeric selects all ask
    # directly with an offer to read.
    for n in (7, 12, 50):
        field = {
            "id": "state", "name": "State", "spoken_name": "state",
            "type": "select",
            "options": [{"value": f"s{i}", "label": f"S{i}"} for i in range(n)],
        }
        text = render_field_guidance(field)
        assert f"Options ({n} -- standard list; ask directly and offer to " in text
        assert f"read all {n} aloud): [" in text
        assert "read ALL" not in text
        # Every option still rides the injection -- the marker changes the
        # ask, never the model's access to the full list.
        for i in range(n):
            assert f"s{i}" in text


def test_render_field_guidance_long_radio_group_marks_long_standard_list():
    from backend.services.ai_context import LONG_OPTION_LIST_THRESHOLD

    n = LONG_OPTION_LIST_THRESHOLD + 1
    field = {
        "id": "big_group",
        "name": "Big group",
        "spoken_name": "big group",
        "type": "radio",
        "options": [
            {"value": f"s{i}", "label": f"Choice {i}"} for i in range(n)
        ],
    }
    text = render_field_guidance(field)
    assert f"Options ({n} total -- long standard list; ask directly and " in text
    assert f"offer to read all {n} aloud): [" in text
    for i in range(n):
        assert f"s{i}" in text


def test_i90_height_selects_are_never_force_recited():
    # bd polyglot-pdf-e5a7 (closed by this PR): the REAL shipped I-90 height
    # fields are selects and must never carry the read-ALL imperative -- a
    # synthetic-only pin would stay green if someone re-typed them to radio in
    # the kit, silently restoring the "zero, one, two, ... eleven" recital.
    import json
    from pathlib import Path

    kit = Path(__file__).resolve().parents[3] / "form-kits" / "i-90" / "schema.json"
    schema = json.loads(kit.read_text(encoding="utf-8"))
    fields = {f["id"]: f for f in schema["fields"]}
    for fid in ("p3_line8_heightfeet", "p3_line8_heightinches"):
        f = fields[fid]
        assert f["type"] == "select", fid
        text = render_field_guidance(f)
        assert "read ALL" not in text, fid
        assert "standard list; ask directly" in text, fid


def test_render_field_guidance_checkbox_group_gets_recital():
    field = {
        "id": "reason", "name": "Reason", "spoken_name": "reason",
        "type": "checkbox_group",
        "options": [{"value": f"v{i}", "label": f"R{i}"} for i in range(8)],
    }
    text = render_field_guidance(field)
    assert "Options (8 -- read ALL 8 aloud when asking; " in text


@pytest.mark.parametrize("ftype,expects_recital", [
    ("ABSENT", True),   # key omitted entirely (guidance defaults it to text)
    (None, True),       # key present with an explicit null (LLM-invented shape)
    ("", True),
    ("text", True),
    ("number", True),
    ("radio", True),
    ("checkbox_group", True),
    ("select", False),
])
def test_option_type_gate_defaults_toward_recital(ftype, expects_recital):
    # bd polyglot-pdf-cqx6: the gate names the ask-directly side (select), so
    # an option-bearing field with an unrecognized, null, or ABSENT type
    # degrades toward reading the choices aloud (the accessibility-safe
    # direction), never silently away from it. The explicit-None row is
    # distinct from the absent row: absent is defaulted upstream by
    # get_field_guidance, while a present-but-null type reaches the render's
    # own `or ""` guard (Opus outer review on this PR).
    field = {
        "id": "f", "name": "F", "spoken_name": "f",
        "options": [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}],
    }
    if ftype != "ABSENT":
        field["type"] = ftype
    text = render_field_guidance(field)
    if expects_recital:
        # A 2-option recital-side field gets the natural-question marker
        # (bd polyglot-pdf-41fi), still on the recital side of the gate --
        # never the select-style ask-directly marker.
        assert "ask ONE natural question that makes both choices clear" in text, ftype
        assert "standard list; ask directly" not in text, ftype
    else:
        assert "standard list; ask directly" in text, ftype
        assert "read ALL" not in text, ftype


def test_option_type_gate_unwraps_field_type_enum():
    # bd polyglot-pdf-285t: str(FieldType.RADIO) on a plain (str, Enum) is
    # 'FieldType.RADIO', which would silently divert a radio to ask-directly;
    # the render unwraps .value first. All production callers pass raw JSON
    # dicts today, so this pins the latent path.
    from backend.models.form_models import FieldType

    field = {
        "id": "r", "name": "R", "spoken_name": "r", "type": FieldType.RADIO,
        "options": [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}],
    }
    text = render_field_guidance(field)
    # 2 options -> the natural-question marker (bd 41fi), on the recital side.
    assert "ask ONE natural question that makes both choices clear" in text
    # The unwrap covers the model-visible Type: line too, not just the gate
    # (Opus outer review on the cqx6 PR: the half-fixed render printed
    # 'Type: FieldType.RADIO').
    assert "Type: radio" in text
    assert "FieldType" not in text

    field["type"] = FieldType.SELECT
    text = render_field_guidance(field)
    assert "standard list; ask directly" in text
    assert "Type: select" in text
    assert "FieldType" not in text


def test_render_field_guidance_threshold_boundary_is_exclusive():
    # Exactly-THRESHOLD options must still get the read-ALL branch; a silent
    # `>` -> `>=` flip would change every 20-option field with the suite green
    # (2nd Opus outer review, this PR).
    from backend.services.ai_context import LONG_OPTION_LIST_THRESHOLD as T

    def field_with(n):
        # radio: the boundary only exists for recital-eligible types (a select
        # takes the ask-directly branch at every count, bd polyglot-pdf-s503).
        return {
            "id": "f", "name": "F", "spoken_name": "f", "type": "radio",
            "options": [{"value": f"v{i}", "label": f"L{i}"} for i in range(n)],
        }

    at = render_field_guidance(field_with(T))
    assert f"Options ({T} -- read ALL {T} aloud when asking" in at
    above = render_field_guidance(field_with(T + 1))
    assert f"Options ({T + 1} total -- long standard list" in above


def test_initiating_templates_scope_recital_by_standard_list_carve_out():
    # The templates' recital directive must carry the SAME carve-out as the SI:
    # unqualified, a resume onto a 50-state select would demand a full recital
    # against the guidance's ask-directly marker (2nd Opus outer review on the
    # 6bq8 PR). The CONTIGUOUS phrase is asserted (bd polyglot-pdf-285t): two
    # split substrings stayed green if the carve-out clause dangled while
    # "standard list" survived elsewhere in the template.
    s = _settings()
    for name in ("INITIATING_MESSAGE", "RESUME_INITIATING_MESSAGE"):
        tpl = getattr(s, name)
        assert "marks the list as a standard list" in tpl, name
        assert "offer to read the full list" in tpl, name


def test_render_field_guidance_substantive_lists_stay_below_threshold():
    # The two observed real-world cases (W-7 reason: 8, I-90 Part 2 Section A:
    # 12) must get the read-ALL imperative, not the long-list carve-out.
    from backend.services.ai_context import LONG_OPTION_LIST_THRESHOLD

    assert LONG_OPTION_LIST_THRESHOLD >= 12
    # And a genuine state list must clear it.
    assert LONG_OPTION_LIST_THRESHOLD < 50


def test_render_field_guidance_no_options_render_unchanged():
    # A field with no options must not grow any option prose.
    assert "Options" not in render_field_guidance(SIMPLE_FIELD)


# --- Prompt-tuning bundle (bd polyglot-pdf-41fi + c2jy) -----------------------
# 41fi: a two-option field IS one natural question -- the recital rule forced
# "Select No, Select Yes -- which one applies?" on yes/no fields. c2jy: labels
# quoting the printed form's own navigation ("(Proceed to Item Numbers 5.a. -
# 5.c.)", "Skip line 6f") were recited verbatim to users who cannot act on
# them. Mechanism for both: SI prose + (for 41fi) the n==2 render marker.

def _load_kit_field(kit, field_id):
    import json
    from pathlib import Path

    p = Path(__file__).resolve().parents[3] / "form-kits" / kit / "schema.json"
    schema = json.loads(p.read_text(encoding="utf-8"))
    return next(f for f in schema["fields"] if f["id"] == field_id)


def test_real_yes_no_fields_get_the_natural_question_marker():
    # bd 41fi criterion 1: the two named shipped fields render the two-option
    # marker, not the list recital.
    for kit, fid in (("i-90", "p3_checkbox4[1]"), ("f1040", "fld_digital_assets")):
        f = _load_kit_field(kit, fid)
        assert len(f["options"]) == 2, fid
        text = render_field_guidance(f)
        assert "ask ONE natural question that makes both choices clear" in text, fid
        assert "read ALL" not in text, fid


def test_real_multi_option_lists_keep_the_unconditional_recital():
    # bd 41fi + c2jy criterion 2: the two fields the original bug was about
    # still get the read-ALL imperative, kit-backed so a schema re-type or a
    # marker regression cannot slip through on synthetic fields alone.
    for kit, fid, n in (("w7", "reason", 8), ("i-90", "p2_checkbox2[5]", 12)):
        f = _load_kit_field(kit, fid)
        text = render_field_guidance(f)
        assert f"Options ({n} -- read ALL {n} aloud when asking; " in text, fid


def test_dti_si_two_option_rule():
    si = _settings().DTI_SYSTEM_INSTRUCTION
    assert "TWO-option fields are different" in si
    assert "ONE natural question that makes both choices clear IS the complete ask" in si
    assert "Do not recite the two labels as a list" in si
    # Both phrasings are named so the rule travels beyond yes/no pairs.
    assert "plain yes/no question when the options amount to yes and no" in si


def test_dti_si_speaks_substance_not_print_navigation():
    # bd c2jy criterion 1 (SI-prose mechanism): the recital conveys each
    # option's substance and omits printed-form navigation/cross-references
    # and screen wording.
    si = _settings().DTI_SYSTEM_INSTRUCTION
    assert "SPEAK THE SUBSTANCE of each option" in si
    assert "NEVER read aloud a label's printed-form navigation" in si
    assert "'(Proceed to Item 5.a)'" in si
    assert "'Skip line 6f'" in si
    assert "screen wording like 'Select Yes'" in si
    # It is framed as the exception to the as-written rule, and MATCHING's
    # as-written line carries the coupling so the two rules cannot read as
    # contradicting each other.
    assert "the ONE exception to saying a label as written" in si
    assert "minus any printed-form navigation" in si


def test_initiating_templates_carry_two_option_carve_out():
    # Same lesson as the standard-list carve-out (bd s503): an unqualified
    # "read EVERY option aloud" in the templates would override the SI's
    # two-option rule on the initiating/resume paths.
    s = _settings()
    for name in ("INITIATING_MESSAGE", "RESUME_INITIATING_MESSAGE"):
        tpl = getattr(s, name)
        assert "only TWO options" in tpl, name
        assert "ONE natural question that makes both choices clear" in tpl, name


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
