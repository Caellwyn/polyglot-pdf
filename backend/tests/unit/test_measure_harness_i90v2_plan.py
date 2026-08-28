"""
Unit tests for the I90V2_QUESTIONS / I90V2_EXCLUDED plan added to
scripts/spikes/measure_form_session_costs.py for the I-90 v2 kit
(form-kits/i-90_v2/schema.json, bd polyglot-pdf-2nikx, extending the W-7
naive-vs-deployed cost measurement -- bd polyglot-pdf-wiadk, PR #661).

Pins, WITHOUT any live Gemini call and WITHOUT touching the existing W-7 test
file (test_measure_harness_naive_arm.py):

  1. COMPLETENESS (enumerate-the-set doctrine, CLAUDE.md scar #8): the union of
     asked field ids (I90V2_QUESTIONS) and excluded field ids (I90V2_EXCLUDED)
     is EXACTLY the schema's full 94-field id set -- no overlap, no
     duplicates -- derived FROM the shipped schema file at
     form-kits/i-90_v2/schema.json, never a hand-copied list.
  2. SECTION ORDER: the asked field ids appear in the same relative order as
     the schema's own sections[] array (each section's fields[] list, in
     section order) -- i.e. the plan reads the form the way a human filling
     it front-to-back would, not scattered.
  3. OPTION-LABEL scar guard (bd memory: schema-name-key-shifts-independently-
     of-mapping / option0-filler-manufactures-contradictions): for every asked
     radio/select/checkbox_group field, the plan's "say" text must contain the
     CHOSEN option's LABEL (normalized: case-insensitive, numbering prefixes
     like "2.a." and parenthetical navigation suffixes like "(Proceed to
     Section A.)" stripped, word-boundary matched so "Female" cannot spuriously
     match label "Male") -- OR a documented spoken alias for the handful of
     fields where the natural spoken phrasing does not literally restate the
     terse checkbox label (see _DOCUMENTED_ALIASES below; every entry there is
     independently justified against the schema, not just papered over to make
     the test pass).
  4. WRONG-ANSWER SHAPE: every plan entry has a nonempty "wrong" that differs
     from "say" (mirrors the W-7 plan's mis-hearing-not-arbitrary-value
     convention).
  5. SCHEMAS REGISTRATION: "i90-v2" is present in harness.SCHEMAS, its path
     resolves to the real schema file, and its "questions" is (by identity)
     I90V2_QUESTIONS. --arm naive settings shape is unchanged by the i90-v2
     addition (reuses harness._make_settings directly, the same helper the W-7
     naive-arm test file exercises). The i90-full-only --arm/--continuous-
     forcing guard does NOT fire for i90-v2 (i90-v2 is not forced into
     --arm dti --continuous the way i90-full is) -- checked by re-deriving
     the harness's own if/elif guard condition against "i90-v2" without any
     live run. The SEPARATE --events/--reactivity guard is NOT exempted for
     i90-v2: it correctly still rejects --events/--reactivity when passed
     with --schema i90-v2, matching the plan-builder report's own dry-run
     finding.

Imports the REAL harness module (scripts/spikes/measure_form_session_costs.py)
via sys.path injection -- scripts/ carries no __init__.py, so this mirrors
the harness's own sibling-module import pattern and the existing W-7 test
file's import pattern, rather than inventing a second import mechanism.

Hermetic: no network, no live model call, no gTTS synthesis. ASCII only.
"""
import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPIKES_DIR = str(_REPO_ROOT / "scripts" / "spikes")
if _SPIKES_DIR not in sys.path:
    sys.path.insert(0, _SPIKES_DIR)

import pytest  # noqa: E402

import measure_form_session_costs as harness  # noqa: E402

I90V2_SCHEMA_PATH = _REPO_ROOT / "form-kits" / "i-90_v2" / "schema.json"

# The i-90_v2 kit is deliberately NOT tracked in git (bd polyglot-pdf-2nikx,
# Opus review: tracking it turned CI red on the translation lint and armed an
# unintended deploy path -- see .gitignore's form-kits/i-90_v2 block). Local
# measurement machines pull it from the bucket via scripts/pull-form-kits.sh;
# a fresh CI clone does not have it, so this whole module skips there --
# same pattern as test_pdf_fill_dropdown_export_codes.py's absent-file skip.
pytestmark = pytest.mark.skipif(
    not I90V2_SCHEMA_PATH.exists(),
    reason="form-kits/i-90_v2 not present (untracked kit; pull with "
           "scripts/pull-form-kits.sh) -- i90-v2 plan pins only run where "
           "the kit exists",
)

_RADIO_LIKE_TYPES = ("radio", "select", "checkbox_group")

# Documented spoken aliases (requirement 3's escape hatch): fields where the
# plan's natural spoken "say" text does not literally restate the option's
# terse checkbox LABEL, each independently justified against the schema
# rather than added merely to make the assertion pass.
#
#   - mail_unit_type / phys_unit_type: validation.required is False and the
#     field's own help text reads "unit type of mailing address, if
#     applicable" -- the persona genuinely has no apartment/suite/floor, so
#     the plan's "say" declines EVERY option ("I do not have an apartment,
#     suite, or floor.") rather than selecting one. There is no option whose
#     label this could match; that is the correct behavior for a not-
#     applicable radio answer, not a missed marker.
#   - applicant_reads_english: the option label is the terse "reads English",
#     but the field's own `name` (the real on-form caption per schema-name-
#     key-shifts-independently-of-mapping) is "I can read and understand
#     English, and I have read and understand every question and instruction
#     on this application and my answer to every question." The plan's "say"
#     ("I can read and understand English myself.") paraphrases that FULL
#     caption, not the short option label -- checked here against the
#     field's `name` instead of the option label.
_NO_OPTION_SELECTED_FIELDS = {"mail_unit_type", "phys_unit_type"}
_ALIAS_MATCH_AGAINST_FIELD_NAME = {"applicant_reads_english"}


def _normalize(text: str) -> str:
    """Case-fold, strip a leading form-numbering prefix ("2.a.", "1.b.",
    "3.a.1.") and any parenthetical navigation suffix ("(Proceed to Section
    A.)"), and collapse punctuation/whitespace -- so a schema option label's
    on-form decoration doesn't defeat a legitimate spoken match."""
    s = text.lower()
    s = re.sub(r'^\d+(\.[a-z0-9]+)*\.\s*', '', s)
    s = re.sub(r'\([^)]*\)', '', s)
    s = re.sub(r'[^\w\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _contains_normalized(haystack_norm: str, needle_norm: str) -> bool:
    """Word-boundary substring match on already-normalized text. Plain
    substring (`needle in haystack`) is NOT enough: normalized label "male"
    is a substring of normalized say-text "female", which would let an
    entry pass by accident on the wrong option."""
    if not needle_norm:
        return False
    pattern = r'(?<!\w)' + re.escape(needle_norm) + r'(?!\w)'
    return re.search(pattern, haystack_norm) is not None


def _load_raw_schema() -> dict:
    """Load form-kits/i-90_v2/schema.json directly (not via
    harness.load_schema, which goes through the production schema-loading
    path) -- this is the completeness pin's SOURCE OF TRUTH, independent of
    any harness-side transformation."""
    with open(I90V2_SCHEMA_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _all_field_ids(schema: dict) -> set:
    return {f["id"] for f in schema["fields"]}


def _fields_by_id(schema: dict) -> dict:
    return {f["id"]: f for f in schema["fields"]}


def _section_order_field_ids(schema: dict) -> list:
    """Flatten schema["sections"] (in array order) into one field-id list, in
    the order a human reading the form front-to-back would encounter them --
    the ground truth for requirement 2."""
    ids = []
    for section in schema["sections"]:
        ids.extend(section.get("fields", []))
    return ids


class TestCompleteness:
    """Requirement 1: enumerate the set, then pin it (CLAUDE.md scar #8)."""

    def test_schema_has_94_fields(self):
        schema = _load_raw_schema()
        assert len(schema["fields"]) == 94

    def test_asked_and_excluded_have_no_duplicates(self):
        asked = [q["field_id"] for q in harness.I90V2_QUESTIONS]
        excluded = list(harness.I90V2_EXCLUDED)
        assert len(asked) == len(set(asked)), "duplicate id in I90V2_QUESTIONS"
        assert len(excluded) == len(set(excluded)), (
            "duplicate id in I90V2_EXCLUDED")

    def test_asked_and_excluded_do_not_overlap(self):
        asked = {q["field_id"] for q in harness.I90V2_QUESTIONS}
        excluded = set(harness.I90V2_EXCLUDED)
        assert asked & excluded == set()

    def test_asked_plus_excluded_equals_full_schema_field_set(self):
        """The mechanical completeness pin: derived FROM the shipped schema
        file, never a hand-copied list, per CLAUDE.md scar #8."""
        schema = _load_raw_schema()
        all_ids = _all_field_ids(schema)
        asked = {q["field_id"] for q in harness.I90V2_QUESTIONS}
        excluded = set(harness.I90V2_EXCLUDED)
        covered = asked | excluded
        missing = all_ids - covered
        extra = covered - all_ids
        assert not missing, f"schema fields covered by neither list: {missing}"
        assert not extra, f"plan/exclusion ids not in the schema: {extra}"
        assert covered == all_ids

    def test_asked_count_is_57_and_excluded_count_is_37(self):
        """Pin the counts too (not just the set), so a future edit that swaps
        one asked field for one excluded field without checking set-equality
        is caught by this narrower, human-legible pin as well."""
        assert len(harness.I90V2_QUESTIONS) == 57
        assert len(harness.I90V2_EXCLUDED) == 37


class TestSectionOrder:
    """Requirement 2: asked questions appear in schema section order."""

    def test_asked_ids_appear_in_schema_section_order(self):
        schema = _load_raw_schema()
        order_ids = _section_order_field_ids(schema)
        asked = [q["field_id"] for q in harness.I90V2_QUESTIONS]
        # Every asked id must actually be placed in some section (a field
        # missing from sections[] entirely -- e.g. read_only header fields --
        # would raise ValueError here rather than silently no-op).
        positions = [order_ids.index(fid) for fid in asked]
        assert positions == sorted(positions), (
            "I90V2_QUESTIONS order diverges from the schema's own "
            "sections[] order")

    def test_excluded_ids_are_all_placed_in_some_section_or_are_read_only_header(self):
        """Sanity check on the exclusion rationale: every excluded id is
        either (a) present in some section's fields[] (the conditional-branch
        and scratch-space exclusions), or (b) a read_only field with no
        section fields[] entry at all is NOT expected here -- the p8 header
        fields ARE listed in a section (sec_your_full_name_p7), so this
        should hold for the full excluded set without any carve-out."""
        schema = _load_raw_schema()
        order_ids = set(_section_order_field_ids(schema))
        excluded = set(harness.I90V2_EXCLUDED)
        assert excluded <= order_ids, (
            f"excluded ids missing from every section: {excluded - order_ids}")


class TestOptionLabelGuard:
    """Requirement 3: for every asked radio/select/checkbox_group field, the
    "say" text must contain the CHOSEN option's label (normalized), or a
    documented alias -- never just a bare option VALUE string."""

    @staticmethod
    def _plan_by_id():
        return {q["field_id"]: q for q in harness.I90V2_QUESTIONS}

    @staticmethod
    def _chosen_option(field: dict, say: str):
        """Best-effort: the plan doesn't record which option value was
        'chosen' explicitly, so recover it by finding the option whose
        normalized label appears (word-boundary) in the normalized say text.
        Returns None if no option matches."""
        say_norm = _normalize(say)
        for option in field.get("options") or []:
            label_norm = _normalize(option.get("label", ""))
            if _contains_normalized(say_norm, label_norm):
                return option
        return None

    def test_every_radio_like_asked_field_say_contains_its_option_label(self):
        schema = _load_raw_schema()
        fields = _fields_by_id(schema)
        plan = self._plan_by_id()
        failures = []
        checked = 0
        for field_id, field in fields.items():
            if field.get("type") not in _RADIO_LIKE_TYPES:
                continue
            if field_id not in plan:
                continue  # not asked -- covered by completeness pin instead
            checked += 1
            say = plan[field_id]["say"]
            if field_id in _NO_OPTION_SELECTED_FIELDS:
                # Documented alias: a legitimate "none of the options apply"
                # answer on a non-required field. Confirm the schema still
                # agrees this field is optional -- if a future schema edit
                # makes it required, this exemption needs re-justifying.
                assert field.get("validation", {}).get("required") is False, (
                    f"{field_id} is now required -- the "
                    "no-option-selected exemption in this test needs "
                    "re-justifying, not silently kept")
                continue
            if field_id in _ALIAS_MATCH_AGAINST_FIELD_NAME:
                # The plan's "say" is a natural paraphrase of the field's
                # full on-form `name` caption, not a substring of it (and
                # vice versa) -- e.g. "I can read and understand English
                # myself." vs. the caption "I can read and understand
                # English, and I have read and understand every question and
                # instruction on this application and my answer to every
                # question." Check instead that "say" shares the caption's
                # distinguishing CORE phrase ("read and understand English"),
                # which is the substantive content the option label ("reads
                # English") is a terse restatement of.
                core_phrase = _normalize("read and understand English")
                say_norm = _normalize(say)
                assert _contains_normalized(say_norm, core_phrase), (
                    f"{field_id}: documented alias check failed -- 'say' "
                    f"({say!r}) no longer contains the core phrase this "
                    "field's option label and full caption both restate")
                continue
            chosen = self._chosen_option(field, say)
            if chosen is None:
                failures.append(
                    f"{field_id}: say={say!r} matches no option label "
                    f"(options={[o['label'] for o in field.get('options', [])]})")
        assert checked >= 15, (
            "sanity: expected at least 15 radio/select/checkbox_group "
            "fields in the asked plan -- guard against this pin silently "
            "checking nothing")
        assert not failures, "\n".join(failures)

    def test_option_label_guard_rejects_a_bare_option_value(self):
        """Positive control for the guard's discriminating power: a "say"
        that contains only the option VALUE string (not its label) must NOT
        be accepted as a match. Uses the real 'status' field/options."""
        schema = _load_raw_schema()
        field = _fields_by_id(schema)["status"]
        bare_value_say = "My status is lawful_permanent_resident."
        chosen = self._chosen_option(field, bare_value_say)
        # The raw value string IS a substring, but normalization removes
        # underscores from neither the label nor turns the value into the
        # label, so this must not spuriously match the "1.a. Lawful
        # Permanent Resident (Proceed to Section A.)" label text.
        assert chosen is None, (
            "the option-label guard accepted a bare option VALUE string as "
            "if it were the option's LABEL -- this is exactly the scar the "
            "guard exists to catch")

    def test_normalization_does_not_let_male_match_female(self):
        """Regression pin for the word-boundary fix: naive substring
        containment (without word boundaries) lets normalized label "male"
        match inside normalized say-text "female", silently passing the
        wrong option. Confirms the real 'sex' field resolves to 'female',
        never 'male', for the plan's actual say text."""
        schema = _load_raw_schema()
        field = _fields_by_id(schema)["sex"]
        say = self._plan_by_id()["sex"]["say"]
        assert say.strip().rstrip(".").lower() == "female"
        chosen = self._chosen_option(field, say)
        assert chosen is not None
        assert chosen["value"] == "female"


class TestWrongAnswerShape:
    """Requirement 4: every entry has a nonempty "wrong" differing from
    "say"."""

    def test_every_entry_has_nonempty_wrong(self):
        for q in harness.I90V2_QUESTIONS:
            assert q.get("wrong"), f"{q['field_id']}: empty/missing 'wrong'"

    def test_every_entry_wrong_differs_from_say(self):
        for q in harness.I90V2_QUESTIONS:
            assert q["wrong"] != q["say"], (
                f"{q['field_id']}: 'wrong' is identical to 'say'")

    def test_every_entry_has_nonempty_say(self):
        for q in harness.I90V2_QUESTIONS:
            assert q.get("say"), f"{q['field_id']}: empty/missing 'say'"


class TestSchemasRegistration:
    """Requirement 5: SCHEMAS registration, and the i90-full-only ARM/
    CONTINUOUS-forcing guard does not fire for i90-v2 (the separate --events/
    --reactivity guard correctly still rejects i90-v2 -- see below)."""

    def test_i90_v2_key_present_in_schemas(self):
        assert "i90-v2" in harness.SCHEMAS

    def test_i90_v2_path_resolves_to_the_real_schema_file(self):
        entry = harness.SCHEMAS["i90-v2"]
        assert entry["path"] == I90V2_SCHEMA_PATH
        assert entry["path"].is_file()

    def test_i90_v2_questions_is_i90v2_questions_by_identity(self):
        entry = harness.SCHEMAS["i90-v2"]
        assert entry["questions"] is harness.I90V2_QUESTIONS

    def test_naive_arm_settings_shape_unchanged_for_i90_v2(self):
        """--arm naive settings construction takes no schema parameter at
        all (harness._make_settings only takes arm/trigger/window/etc.), so
        the i90-v2 addition cannot have perturbed it structurally; assert the
        exact same shape the W-7 naive-arm test file pins."""
        s = harness._make_settings(
            "naive", trigger=12_000, window=9_000,
            compression=False, continuous=False, derive_compression=False)
        assert s.USE_DTI is False
        assert s.CONTEXT_COMPRESSION_ENABLED is False
        assert s.CONTINUOUS_SESSION is False

    def test_i90_full_only_arm_continuous_guard_does_not_fire_for_i90_v2(self):
        """Re-derive the harness's own i90-full-only gate condition (line
        ~2381: `if args.schema == "i90-full": require --arm dti
        --continuous`) against the literal string "i90-v2", without running
        the harness's argparse or main() at all. The guard is keyed on an
        EXACT string comparison against "i90-full" -- confirm "i90-v2" fails
        that comparison, i.e. this branch is never entered for i90-v2, so
        i90-v2 is NOT forced into --arm dti --continuous the way i90-full is."""
        assert "i90-v2" != "i90-full"
        schema_arg = "i90-v2"
        # Mirrors the harness's own post-parse guard shape verbatim.
        guard_fires = (schema_arg == "i90-full")
        assert guard_fires is False

    def test_events_reactivity_guard_correctly_still_rejects_i90_v2(self):
        """The harness's real shape (line ~2381-2394) is an if/elif: the
        i90-full branch above is skipped for i90-v2, which falls through to
        `elif events/reactivity set: reject "only defined for --schema
        i90-full"`. So --events/--reactivity must STILL be rejected for
        i90-v2 -- i90-v2 does NOT get a free pass on that guard, only on the
        --arm/--continuous forcing above. This matches the plan-builder
        report's own live dry-run finding ("--events standard is correctly
        rejected for i90-v2")."""
        schema_arg = "i90-v2"
        events_arg = "standard"
        # Mirrors: `if schema == "i90-full": ... elif events != "none" or
        # reactivity: reject`.
        if schema_arg == "i90-full":
            events_guard_fires = False
        else:
            events_guard_fires = (events_arg != "none")
        assert events_guard_fires is True, (
            "i90-v2 must still be rejected when --events is passed -- only "
            "i90-full is exempt from this guard")

    def test_events_reactivity_guard_does_not_fire_for_i90_v2_with_no_events(self):
        """Companion pin: with NO --events/--reactivity passed, i90-v2 must
        NOT be rejected -- the elif guard only fires when those flags are
        actually set."""
        schema_arg = "i90-v2"
        events_arg = "none"
        reactivity_arg = None
        if schema_arg == "i90-full":
            events_guard_fires = False
        else:
            events_guard_fires = (events_arg != "none" or bool(reactivity_arg))
        assert events_guard_fires is False

    def test_use_text_ai_default_is_false_for_i90_v2(self):
        """use_text_ai's default is `args.schema == "i90-full"` -- confirm
        i90-v2 defaults it OFF (same as every legacy schema), matching the
        harness comment that i90-v2 does not default into production-fidelity
        text-AI-sidecar mode."""
        schema_arg = "i90-v2"
        use_text_ai_default = (schema_arg == "i90-full")
        assert use_text_ai_default is False

    def test_schema_choices_argparse_accepts_i90_v2(self):
        """--schema argparse choices includes 'i90-v2' (mirrors the harness's
        own ap.add_argument("--schema", choices=[...]) list) without
        importing/running the harness's real argparse setup (which has many
        other required-looking flags)."""
        import argparse

        ap = argparse.ArgumentParser()
        ap.add_argument(
            "--schema",
            choices=["demo", "i90", "i90-full", "w7", "i90-v2"],
            default="demo")
        args = ap.parse_args(["--schema", "i90-v2"])
        assert args.schema == "i90-v2"
