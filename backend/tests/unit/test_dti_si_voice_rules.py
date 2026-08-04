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
    # The recital is wired into WORKFLOW step 1, not only the options block --
    # and step 1 must carry the SAME carve-outs as PRESENTING OPTIONS: an
    # unqualified step-1 imperative contradicted the two-option rule on every
    # confirm-path turn (Opus fresh-eyes, prompt-tuning PR).
    workflow = si[si.index("WORKFLOW:"):si.index("TOOL PROTOCOL:")]
    assert "read EVERY option aloud" in workflow
    assert "never one-by-one as yes/no questions" in workflow
    assert "ONE natural question for a TWO-option field" in workflow
    assert "ask directly for a standard list" in workflow


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
        # Both 2-option markers sit on the RECITAL side of the ask-directly
        # gate -- which one fires is the multi-select question below, not this
        # test's concern. What this pins is that NO option-bearing type
        # silently reaches the select-style ask-directly branch.
        assert "standard list; ask directly" not in text, ftype
        if ftype == "checkbox_group":
            # A 2-option MULTI-select recites (bd polyglot-pdf-9tuu): the
            # natural-question marker asserts an exclusive choice, which would
            # foreclose selecting BOTH.
            assert "read ALL 2 aloud when asking" in text, ftype
        else:
            # Single-select: one natural question IS the ask (bd 41fi).
            assert "ask ONE natural question that makes both choices clear" in text, ftype
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


def test_substantive_two_option_pair_keeps_the_full_recital():
    # bd polyglot-pdf-575i criterion 1: I-90 'p7_checkbox7' is a 2-option RADIO
    # whose labels are ~23- and ~27-word legal declarations ("I am not an
    # attorney ... with the applicant's consent" vs "I am an attorney ... my
    # representation extends / does not extend beyond ..."). Its spoken_name
    # ("Is the preparer an attorney or not") collapses to an attorney yes/no,
    # so ONE natural question drops the representation-scope clause -- load-
    # bearing legal text the user never hears. Too long to fold into one
    # question => the normal recital stands.
    f = _load_kit_field("i-90", "p7_checkbox7")
    assert len(f["options"]) == 2
    text = render_field_guidance(f)
    assert "Options (2 -- read ALL 2 aloud when asking; " in text
    assert "ask ONE natural question" not in text
    # Both declarations ride the injection in full -- the marker changes the
    # ask, never the model's access to the text.
    assert "my representation of the applicant" in text


def test_two_option_word_threshold_admits_the_navigation_padded_yes_no():
    # The threshold's live boundary case, and why it is not lower. W-7
    # 'previously_received_itin_or_irsn' IS a genuine yes/no ("Have you
    # previously received an ITIN?"), but its labels are padded to 17 words with
    # the printed-form navigation the SI already tells the model not to speak
    # ("Yes. Complete line 6f. If more than one, list on a sheet and attach...").
    # It must KEEP the natural-question marker; a threshold at or below 17 would
    # regress it into "No/Don't know. Skip line 6f. -- which one applies?", the
    # exact recital bd 41fi removed.
    from backend.services.ai_context import TWO_OPTION_MAX_LABEL_WORDS

    f = _load_kit_field("w7", "previously_received_itin_or_irsn")
    longest = max(len((o["label"] or "").split()) for o in f["options"])
    assert longest > 12, "fixture no longer exercises the padded-label case"
    assert TWO_OPTION_MAX_LABEL_WORDS > longest
    text = render_field_guidance(f)
    assert "ask ONE natural question that makes both choices clear" in text


def test_two_option_word_threshold_boundary_is_inclusive():
    # A silent `<=` -> `<` flip (or a threshold nudge) would re-route every
    # exactly-at-threshold pair with the suite green -- the same durability
    # lesson as the long-list boundary pin above.
    from backend.services.ai_context import TWO_OPTION_MAX_LABEL_WORDS as W

    def pair(words):
        label = " ".join(f"w{i}" for i in range(words))
        return {
            "id": "f", "name": "F", "spoken_name": "f", "type": "radio",
            "options": [{"value": "a", "label": label},
                        {"value": "b", "label": "short"}],
        }

    assert "ask ONE natural question" in render_field_guidance(pair(W))
    assert f"read ALL 2 aloud" in render_field_guidance(pair(W + 1))


@pytest.mark.parametrize("kit,fid,expect_natural", [
    # The two fields the threshold was calibrated to separate. Both must land
    # on the SAME side in EVERY baked language.
    ("i-90", "p7_checkbox7", False),
    ("w7", "previously_received_itin_or_irsn", True),
])
def test_two_option_branch_is_the_same_in_every_baked_language(kit, fid, expect_natural):
    # The gate must describe the FIELD, not the session. It briefly did not:
    # manifest_service._apply_label_overrides substitutes the session-language
    # label into opt["label"] BEFORE the render measures it, and word count is
    # not translation-invariant -- so an English-calibrated threshold applied to
    # translated text flipped both of these fields on SHIPPED kits (Opus outer
    # review, this PR): i-90 'p7_checkbox7' dropped under the threshold in
    # Chinese and Korean (re-introducing the bd 575i substance drop) and w7
    # 'previously_received_itin_or_irsn' rose over it in 8 of 17 languages
    # (re-introducing the bd 41fi recital). The render now reverse-maps the
    # override to recover the English label.
    #
    # Parametrized over EVERY language the kit actually bakes, not a sample:
    # the two failures above hit disjoint language sets, so any fixed sample
    # would have missed one of them.
    f = _load_kit_field(kit, fid)
    languages = sorted({
        lang
        for opt in f["options"]
        for lang in (opt.get("label_translations") or {})
    })
    assert len(languages) >= 15, f"{fid} is no longer a fully-baked fixture"

    marker = "ask ONE natural question that makes both choices clear"
    # English (no overrides) is the reference the threshold was calibrated on.
    assert (marker in render_field_guidance(f)) is expect_natural, f"{fid} english"

    for lang in languages:
        overrides = {
            opt["label"]: (opt.get("label_translations") or {})[lang]
            for opt in f["options"]
            if (opt.get("label_translations") or {}).get(lang)
        }
        text = render_field_guidance(f, option_label_overrides=overrides)
        assert (marker in text) is expect_natural, f"{fid} flipped in {lang}"
        # The translated labels still ride the injection -- the fix changes
        # only what the LENGTH rule measures, never what the model receives.
        for translated in overrides.values():
            assert translated in text, f"{fid} lost its {lang} label"


@pytest.mark.parametrize("bad_label", [1, None, 3.5, True])
def test_render_survives_a_non_string_option_label(bad_label):
    # schema_lint does not assert that a label is a string, _sanitize_options
    # copies it verbatim, and every render call site is unguarded -- so a
    # number/None label from an LLM-extracted or editor-drafted kit reached
    # `label.split()` and crashed the render mid-form (Opus outer review, this
    # PR; origin/dev rendered these fine because it measured no lengths).
    field = {
        "id": "f", "name": "F", "spoken_name": "f", "type": "radio",
        "options": [{"value": "a", "label": bad_label},
                    {"value": "b", "label": "B"}],
    }
    text = render_field_guidance(field)
    assert "Options (2" in text


def test_two_option_multi_select_is_not_forced_into_an_exclusive_choice():
    # bd polyglot-pdf-9tuu criterion 1: the marker (and the SI rule it triggers)
    # describes an EXCLUSIVE choice -- "a plain yes/no question ... an either/or
    # question otherwise ... do not ask which one applies". On a checkbox_group
    # the user may legitimately want BOTH, so a 2-option multi-select falls to
    # the recital, whose rule already says "or which ones, for a multi-select".
    # Latent today (no shipped kit has a 2-option checkbox_group -- counts run
    # 3/5/8) but kits are LLM-extracted and ship regularly.
    field = {
        "id": "accommodations", "name": "Accommodations",
        "spoken_name": "accommodations you need", "type": "checkbox_group",
        "options": [
            {"value": "deaf", "label": "Deaf or hard of hearing"},
            {"value": "blind", "label": "Blind or low vision"},
        ],
    }
    text = render_field_guidance(field)
    assert "Options (2 -- read ALL 2 aloud when asking; " in text
    assert "ask ONE natural question" not in text


@pytest.mark.parametrize("ftype", ["checkbox_group", "multiselect", "multi_select"])
def test_every_multi_select_spelling_escapes_the_exclusive_marker(ftype):
    # The gate is a name set, so an LLM-invented spelling of the same concept
    # must be listed to be caught. These are the spellings the schema surfaces
    # and the editor can emit; a new one arriving in a kit is the known
    # maintenance cost of a name set (the alternative, guessing multi-ness from
    # an unrecognized type, would break the cqx6 safe-default in the other
    # direction).
    field = {
        "id": "f", "name": "F", "spoken_name": "f", "type": ftype,
        "options": [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}],
    }
    text = render_field_guidance(field)
    assert "read ALL 2 aloud when asking" in text, ftype
    assert "ask ONE natural question" not in text, ftype


def test_f1040_line_reference_pair_still_asks_a_natural_question():
    # bd polyglot-pdf-575i criterion 2: f1040 'fld_3c' options are '1 Line 3a' /
    # '2 Line 3b' -- pure printed-form navigation, so SPEAK THE SUBSTANCE alone
    # would leave the model nothing to say. The mechanism is the SI's
    # all-navigation carve-out (pinned in
    # test_dti_si_handles_options_that_are_pure_print_navigation), NOT a render
    # change: the labels are short, so this stays a one-natural-question field
    # and the field's own name carries the meaning ("Check if your child's
    # dividends are included in ... 3a or ... 3b").
    f = _load_kit_field("f1040", "fld_3c")
    text = render_field_guidance(f)
    assert "ask ONE natural question that makes both choices clear" in text
    # Both line references reach the model verbatim -- they are the only thing
    # distinguishing the two options.
    assert "1 Line 3a" in text and "2 Line 3b" in text


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
    assert "ONE natural question that makes both choices clear IS the complete ask" in si
    assert "Do not recite the two labels as a list" in si
    # Both phrasings are named so the rule travels beyond yes/no pairs.
    assert "plain yes/no question when the options amount to yes and no" in si


def test_dti_si_two_option_rule_is_scoped_to_the_guidance_marker():
    # bd polyglot-pdf-575i + 9tuu: the rule used to open "TWO-option fields are
    # different", a bare COUNT test the model could apply to any n==2 field --
    # including the two the render now deliberately sends to the recital (long
    # substantive labels; a multi-select). The SI must key on the MARKER the
    # render emits, not on the count, or the two channels contradict each other
    # on exactly those fields.
    si = _settings().DTI_SYSTEM_INSTRUCTION
    assert "TWO-option fields, WHEN THE GUIDANCE MARKS THEM SO" in si
    assert "This applies ONLY when the guidance carries that two-option marker" in si
    # The recital branch's own marker text is named, so the model can tell the
    # two n==2 cases apart from the guidance alone.
    assert "the guidance marks 'read ALL 2 aloud'" in si
    # And the bare-count phrasing is GONE -- an allowlist pin is worthless if
    # the superseded wording survives elsewhere in the SI (memory: pin message
    # text with allowlists, then assert no residue).
    assert "TWO-option fields are different" not in si


def test_dti_si_handles_options_that_are_pure_print_navigation():
    # bd polyglot-pdf-575i criterion 2: f1040 'fld_3c' labels are '1 Line 3a' /
    # '2 Line 3b' -- pure printed-form navigation. SPEAK THE SUBSTANCE alone
    # would strip both to nothing, leaving the model no way to tell the options
    # apart. The carve-out's carve-out: when navigation is ALL there is, it IS
    # the option's identity and is spoken.
    si = _settings().DTI_SYSTEM_INSTRUCTION
    assert "would leave an option with NOTHING to say" in si
    assert "'1 Line 3a'" in si
    assert "the reference IS that option's only identity: say it as written" in si


def test_dti_si_speaks_substance_not_print_navigation():
    # bd c2jy criterion 1 (SI-prose mechanism): the recital conveys each
    # option's substance and omits printed-form navigation/cross-references
    # and screen wording.
    si = _settings().DTI_SYSTEM_INSTRUCTION
    assert "SPEAK THE SUBSTANCE of each option" in si
    assert "NEVER read aloud a label's printed-form NAVIGATION" in si
    assert "'(Proceed to Item 5.a)'" in si
    assert "'Skip line 6f'" in si
    assert "screen wording like 'Select Yes'" in si
    # The boundary runs between NAVIGATION (omit) and a cross-reference that
    # carries a REAL requirement (keep): W-7 reason option a's "you must also
    # check and complete box h" is a genuine multi-select obligation, not
    # cruft (fresh-eyes finding, this PR).
    assert "a REAL requirement or consequence of choosing that option" in si
    assert "is SUBSTANCE -- keep its meaning" in si
    # It is framed as the exception to the as-written rule, and MATCHING's
    # as-written line carries the coupling so the two rules cannot read as
    # contradicting each other.
    assert "the ONE exception to saying a label as written" in si
    assert "minus any printed-form navigation" in si


def test_initiating_templates_carry_two_option_carve_out():
    # Same lesson as the standard-list carve-out (bd s503): an unqualified
    # "read EVERY option aloud" in the templates would override the SI's
    # two-option rule on the initiating/resume paths.
    # CONTIGUOUS clause, same durability rule as the standard-list pin above
    # (bd 285t): split substrings stay green if the parenthetical detaches
    # from its condition.
    s = _settings()
    for name in ("INITIATING_MESSAGE", "RESUME_INITIATING_MESSAGE"):
        tpl = getattr(s, name)
        # Keyed on the guidance MARKER, not on a bare count (bd 575i + 9tuu):
        # the render now withholds the two-option marker from a long-labelled
        # pair and from a 2-option multi-select, and an unqualified "only TWO
        # options" here would re-assert the natural question on exactly those.
        assert ("the guidance marks the field as having TWO options (then ask "
                "ONE natural question that makes both choices clear)") in tpl, name
        assert "the field has only TWO options" not in tpl, name


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
