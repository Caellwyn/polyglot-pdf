"""
Offline unit tests for the simulated-user actor core
(scripts/spikes/sim_user/actor.py, bd polyglot-pdf-ctzze).

Pins, with NO network and NO named kit field id (CLAUDE.md scar #10):
  - the persona fact sheet equals the W-7 strict answer key (drift test);
  - the move schema is a strict enum contract and validate_decision enforces it;
  - the renderer can only speak fact-sheet strings (no off-sheet value);
  - the non-spelling persona does not spell until asked;
  - StubActor drives a whole session offline;
  - HaikuActor builds the pinned request shape and falls back on bad output.

Field ids are always DERIVED from the persona JSON / W7_EXPECTED, never typed.
ASCII only.
"""
import asyncio
import json
import random
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPIKES_DIR = str(_REPO_ROOT / "scripts" / "spikes")
if _SPIKES_DIR not in sys.path:
    sys.path.insert(0, _SPIKES_DIR)

import measure_form_session_costs as harness  # noqa: E402
from sim_user import actor  # noqa: E402

PERSONA_PATH = (_REPO_ROOT / "scripts" / "spikes" / "sim_user" / "personas"
                / "w7_ana_nospell.json")
SEEDS = (0, 1, 2, 3, 7, 42)
SPELLED = re.compile(r"\b[A-Za-z](?: - [A-Za-z])+\b")


@pytest.fixture(scope="module")
def persona():
    return actor.load_persona(PERSONA_PATH)


def run(coro):
    return asyncio.run(coro)


def _first_with(persona, pred):
    return next(k for k, f in persona.facts.items() if pred(f))


def _name_key(persona):
    return _first_with(persona, lambda f: f["spellable"])


# --------------------------------------------------------------------- drift
class TestFactSheetDrift:
    def test_keys_equal_w7_expected(self, persona):
        assert set(persona.facts) == set(harness.W7_EXPECTED)

    def test_every_value_satisfies_expected(self, persona):
        bad = []
        for fid, f in persona.facts.items():
            exp = harness.W7_EXPECTED[fid]
            allowed = exp if isinstance(exp, (list, tuple)) else [exp]
            got = harness._canon_value(f["value"])
            if got not in {harness._canon_value(a) for a in allowed}:
                bad.append(fid)
        assert bad == []

    def test_persona_id_and_form(self, persona):
        assert persona.persona_id == "w7_ana_nospell_v1"
        assert persona.form == "w7"
        assert persona.behavior["spells_unprompted"] is False

    def test_load_persona_rejects_malformed(self, tmp_path):
        raw = json.loads(PERSONA_PATH.read_text(encoding="utf-8"))
        first = next(iter(raw["facts"]))
        raw["facts"][first].pop("answer")
        p = tmp_path / "bad.json"
        p.write_text(json.dumps(raw), encoding="utf-8")
        with pytest.raises(ValueError):
            actor.load_persona(p)

    def test_spellable_requires_spell(self, tmp_path, persona):
        raw = json.loads(PERSONA_PATH.read_text(encoding="utf-8"))
        raw["facts"][_name_key(persona)].pop("spell")
        p = tmp_path / "bad2.json"
        p.write_text(json.dumps(raw), encoding="utf-8")
        with pytest.raises(ValueError):
            actor.load_persona(p)


# -------------------------------------------------------------------- schema
class TestSchemaStrictness:
    def test_enums_and_additional_properties(self, persona):
        s = actor.move_schema(persona.facts)
        assert s["additionalProperties"] is False
        assert set(s["required"]) == {"move", "field_key"}
        assert set(s["properties"]) == {"move", "field_key"}
        assert s["properties"]["move"]["enum"] == list(actor.MOVES)
        keys = s["properties"]["field_key"]["enum"]
        assert set(keys) == set(persona.facts) | {"none"}
        assert len(keys) == len(persona.facts) + 1

    def test_validate_accepts_good(self, persona):
        k = next(iter(persona.facts))
        assert actor.validate_decision({"move": "answer", "field_key": k}, persona.facts)[0]
        assert actor.validate_decision({"move": "confirm", "field_key": "none"}, persona.facts)[0]

    def test_validate_rejects_unknown_move(self, persona):
        assert not actor.validate_decision(
            {"move": "shout", "field_key": "none"}, persona.facts)[0]

    def test_validate_rejects_unknown_key(self, persona):
        assert not actor.validate_decision(
            {"move": "answer", "field_key": "not_a_field"}, persona.facts)[0]

    @pytest.mark.parametrize("move", sorted(actor.FIELD_MOVES))
    def test_validate_rejects_field_move_with_none(self, persona, move):
        assert not actor.validate_decision(
            {"move": move, "field_key": "none"}, persona.facts)[0]

    def test_validate_rejects_extra_or_missing_keys(self, persona):
        k = next(iter(persona.facts))
        assert not actor.validate_decision(
            {"move": "answer", "field_key": k, "text": "x"}, persona.facts)[0]
        assert not actor.validate_decision({"move": "confirm"}, persona.facts)[0]
        assert not actor.validate_decision("answer", persona.facts)[0]


# ----------------------------------------------------------------- renderer
def _all_combos(persona):
    keys = list(persona.facts) + ["none"]
    for move in actor.MOVES:
        for key in keys:
            if move in actor.FIELD_MOVES and key == "none":
                continue
            yield move, key


def _fact_strings(persona):
    out = set()
    for f in persona.facts.values():
        for k in ("answer", "spoken", "spell"):
            if f.get(k):
                out.add(f[k])
    return out


class TestNoOffSheetValues:
    def test_values_spoken_are_fact_strings(self, persona):
        allowed = _fact_strings(persona)
        n = 0
        for move, key in _all_combos(persona):
            for seed in SEEDS:
                r = actor.render(move, key, persona, random.Random(seed))
                n += 1
                assert r.move == move
                for v in r.values_spoken:
                    assert v in allowed
                    assert v in r.text
        assert n > 100

    def test_digit_runs_come_from_the_sheet(self, persona):
        sheet = " ".join(f["spoken"] + " " + f["answer"]
                         for f in persona.facts.values())
        sheet_runs = set(re.findall(r"\d+", sheet))
        for move, key in _all_combos(persona):
            for seed in SEEDS:
                r = actor.render(move, key, persona, random.Random(seed))
                for run_ in re.findall(r"\d+", r.text):
                    assert run_ in sheet_runs, (move, key, r.text)

    def test_spelled_runs_come_from_the_sheet(self, persona):
        spells = {f["spell"] for f in persona.facts.values() if f.get("spell")}
        for move, key in _all_combos(persona):
            for seed in SEEDS:
                r = actor.render(move, key, persona, random.Random(seed))
                for m in SPELLED.findall(r.text):
                    assert m in spells, (move, key, r.text)

    def test_text_is_template_plus_values_only(self, persona):
        for move, key in _all_combos(persona):
            r = actor.render(move, key, persona, random.Random(5))
            rest = r.text
            for v in r.values_spoken:
                rest = rest.replace(v, "")
            assert not re.search(r"\d", rest)
            assert len(rest) < 60

    def test_render_rejects_bad_input(self, persona):
        with pytest.raises(ValueError):
            actor.render("shout", "none", persona, random.Random(0))
        with pytest.raises(ValueError):
            actor.render("answer", "none", persona, random.Random(0))


class TestNonSpellingPersona:
    def test_answer_on_names_has_no_spelled_run(self, persona):
        names = [k for k, f in persona.facts.items() if f["spellable"]]
        assert names
        for k in names:
            for seed in SEEDS:
                r = actor.render("answer", k, persona, random.Random(seed))
                assert not SPELLED.search(r.text)
                assert persona.facts[k]["spell"] not in r.text

    def test_fact_answers_contain_no_spelling(self, persona):
        for f in persona.facts.values():
            assert not SPELLED.search(f["answer"])

    def test_spell_move_does_spell(self, persona):
        k = _name_key(persona)
        r = actor.render("spell", k, persona, random.Random(0))
        assert persona.facts[k]["spell"] in r.text


# --------------------------------------------------------------- StubActor
def _city_fact(persona):
    return next(fid for fid, f in persona.facts.items()
                if "97477" in f["spoken"])


class TestSpelledCorrections:
    def _spellable(self, persona):
        return [fid for fid, f in persona.facts.items() if f["spellable"]]

    def _plain(self, persona):
        return [fid for fid, f in persona.facts.items() if not f["spellable"]]

    def test_correcting_a_spellable_fact_spells_it(self, persona):
        for fid in self._spellable(persona):
            f = persona.facts[fid]
            for seed in range(12):
                r = actor.render("reject_and_correct", fid, persona,
                                 random.Random(seed))
                assert f["spell"] in r.text, (fid, r.text)
                assert r.values_spoken == [f["spell"]]
                assert r.move == "reject_and_correct"
                assert r.text.startswith(("No,", "Sorry, no"))

    def test_non_spellable_facts_keep_the_answer_based_correction(self, persona):
        for fid in self._plain(persona):
            f = persona.facts[fid]
            r = actor.render("reject_and_correct", fid, persona,
                             random.Random(0))
            assert f["answer"] in r.text
            assert r.values_spoken == [f["answer"]]

    def test_spelled_corrections_are_on_the_sheet(self, persona):
        allowed = set()
        for f in persona.facts.values():
            allowed.update({f["answer"], f["spoken"]})
            if f.get("spell"):
                allowed.add(f["spell"])
        for fid in persona.facts:
            for seed in range(6):
                r = actor.render("reject_and_correct", fid, persona,
                                 random.Random(seed))
                assert all(v in allowed for v in r.values_spoken)
                assert all(v in r.text for v in r.values_spoken)


class TestStubReadbackEquivalence:
    def _decide(self, persona, text):
        fid = _city_fact(persona)
        hist = [{"model_text": "q", "move": "answer", "field_key": fid}]
        return run(actor.StubActor(persona).decide(text, hist))

    def test_digits_spoken_as_words_match_the_digit_value(self, persona):
        d = self._decide(
            persona, "Springfield, Oregon, United States, nine seven four "
            "seven seven. Is that correct?")
        assert (d.move, d.field_key) == ("confirm", "none")

    def test_a_different_spoken_digit_is_rejected(self, persona):
        d = self._decide(
            persona, "Springfield, Oregon, United States, nine seven seven "
            "four seven. Is that correct?")
        assert d.move == "reject_and_correct"
        assert d.field_key == _city_fact(persona)

    def test_digits_as_digits_still_match(self, persona):
        d = self._decide(
            persona, "Springfield, Oregon, United States, 97477. Is that "
            "correct?")
        assert d.move == "confirm"

    def test_a_lone_digit_word_is_not_turned_into_a_digit(self, persona):
        assert actor._tokens("one of the two") == ["one", "of", "the", "two"]
        assert actor._tokens("nine seven four") == ["974"]


class TestStubActor:
    def test_question_gets_answer_on_that_field(self, persona):
        stub = actor.StubActor(persona)
        k = _name_key(persona)
        d = run(stub.decide("What is your %s?" % persona.facts[k]["keywords"][0], []))
        assert (d.move, d.field_key) == ("answer", k)
        assert d.valid and not d.fallback_used

    def test_spell_followup_spells_same_field(self, persona):
        stub = actor.StubActor(persona)
        k = _name_key(persona)
        hist = [{"model_text": "q", "move": "answer", "field_key": k}]
        d = run(stub.decide("How do you spell that?", hist))
        assert (d.move, d.field_key) == ("spell", k)

    def test_correct_readback_confirms(self, persona):
        stub = actor.StubActor(persona)
        k = _name_key(persona)
        hist = [{"model_text": "q", "move": "answer", "field_key": k}]
        d = run(stub.decide("I have %s. Is that correct?" % persona.facts[k]["spoken"], hist))
        assert d.move == "confirm"

    def test_spelled_readback_confirms(self, persona):
        stub = actor.StubActor(persona)
        k = _name_key(persona)
        hist = [{"model_text": "q", "move": "answer", "field_key": k}]
        d = run(stub.decide("That is %s. Is that right?" % persona.facts[k]["spell"], hist))
        assert d.move == "confirm"

    def test_wrong_readback_rejects_and_corrects(self, persona):
        stub = actor.StubActor(persona)
        k = _name_key(persona)
        hist = [{"model_text": "q", "move": "answer", "field_key": k}]
        d = run(stub.decide("I have Zzyzx. Is that correct?", hist))
        assert (d.move, d.field_key) == ("reject_and_correct", k)

    def test_unmatched_text_acknowledges(self, persona):
        d = run(actor.StubActor(persona).decide("Welcome, this is a draft.", []))
        assert (d.move, d.field_key) == ("acknowledge", "none")

    def test_offline_end_to_end_every_field_answered(self, persona):
        stub = actor.StubActor(persona)
        history = []
        answered = set()
        for fid, f in persona.facts.items():
            prompt = "Next, what is your %s?" % f["label"].lower()
            d = run(stub.decide(prompt, history))
            assert (d.move, d.field_key) == ("answer", fid), (fid, prompt)
            history.append(actor.history_entry(prompt, d))
            actor.render(d.move, d.field_key, persona, random.Random(1))
            answered.add(d.field_key)
            readback = "I have %s. Is that correct?" % f["spoken"]
            d2 = run(stub.decide(readback, history))
            assert d2.move == "confirm", (fid, readback)
            history.append(actor.history_entry(readback, d2))
        assert answered == set(persona.facts)

    def test_every_keyword_routes_to_its_field(self, persona):
        stub = actor.StubActor(persona)
        for fid, f in persona.facts.items():
            kw = f["keywords"][0]
            d = run(stub.decide("Please tell me about your %s." % kw, []))
            assert d.field_key == fid, (fid, kw)


# --------------------------------------------------------------- HaikuActor
class FakeClient:
    def __init__(self, text=None, usage=None, stop_reason="end_turn", exc=None):
        self.calls = []
        self._text, self._exc, self._stop = text, exc, stop_reason
        self._usage = usage or SimpleNamespace(
            input_tokens=1200, output_tokens=15,
            cache_read_input_tokens=1000, cache_creation_input_tokens=200)
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._exc:
            raise self._exc
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self._text)],
            usage=self._usage, stop_reason=self._stop)


class TestHaikuActor:
    def test_request_shape(self, persona):
        k = _name_key(persona)
        fc = FakeClient(json.dumps({"move": "answer", "field_key": k}))
        a = actor.HaikuActor(persona, client=fc)
        run(a.decide("What is your first name?", []))
        kw = fc.calls[0]
        assert kw["model"] == "claude-haiku-5-5"
        fmt = kw["output_config"]["format"]
        assert fmt["type"] == "json_schema"
        assert fmt["schema"] == actor.move_schema(persona.facts)
        assert kw["output_config"]["effort"] == "low"
        assert kw["thinking"] == {"type": "disabled"}
        for banned in ("temperature", "top_p", "top_k"):
            assert banned not in kw
        assert kw["messages"][0]["role"] == "user"
        assert kw["messages"][-1]["role"] == "user"
        assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
        assert kw["max_tokens"] <= 300

    def test_history_alternates_user_assistant(self, persona):
        k = _name_key(persona)
        fc = FakeClient(json.dumps({"move": "confirm", "field_key": "none"}))
        a = actor.HaikuActor(persona, client=fc)
        hist = [{"model_text": "q1", "move": "answer", "field_key": k}]
        run(a.decide("is that right?", hist))
        msgs = fc.calls[0]["messages"]
        assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
        assert json.loads(msgs[1]["content"]) == {"move": "answer", "field_key": k}

    def test_empty_model_text_never_reaches_the_api(self, persona):
        # A turn where the model said nothing (a silent tool turn) used to
        # put an empty user message in history: the Claude API answers 400
        # "user messages must have non-empty content" for every later request.
        k = _name_key(persona)
        a = actor.HaikuActor(persona, client=FakeClient("{}"))
        hist = [{"model_text": "", "move": "answer", "field_key": k},
                {"model_text": "   ", "move": "acknowledge",
                 "field_key": "none"},
                {"model_text": None, "move": "acknowledge",
                 "field_key": "none"},
                {"model_text": "real", "move": "answer", "field_key": k}]
        for current in ("", "   ", None, "now"):
            msgs = a.build_request(current, hist)["messages"]
            assert msgs
            for m in msgs:
                assert isinstance(m["content"], str) and m["content"].strip()
        msgs = a.build_request("now", hist)["messages"]
        assert msgs[0]["content"] == "(silence)"
        assert msgs[2]["content"] == "(silence)"
        assert msgs[4]["content"] == "(silence)"
        assert msgs[6]["content"] == "real"

    def test_system_prompt_has_sheet_and_rules(self, persona):
        s = actor.build_system_prompt(persona)
        for fid, f in persona.facts.items():
            assert fid in s and f["spoken"] in s
        assert "Never spell unless" in s
        for m in actor.MOVES:
            assert m in s

    def test_prompt_confirms_equivalent_readbacks_and_rejects_real_differences(self, persona):
        s = actor.build_system_prompt(persona)
        assert "says the same value" in s
        for phrase in ("spoken as words", "digit by digit",
                       "letters are spelled out", "said in words"):
            assert phrase in s
        assert "only when a value is actually different" in s
        assert "wrong letter, digit, name, place or date" in s
        assert "matches the fact exactly" not in s

    def test_prompt_allows_spelling_when_a_spelling_is_read_back_wrong(self, persona):
        s = actor.build_system_prompt(persona)
        assert ("Never spell unless the interviewer asks you to spell or "
                "reads a spelling back wrong") in s

    def test_valid_reply_parses(self, persona):
        k = _name_key(persona)
        fc = FakeClient(json.dumps({"move": "spell", "field_key": k}))
        d = run(actor.HaikuActor(persona, client=fc).decide("spell it", []))
        assert (d.move, d.field_key) == ("spell", k)
        assert d.valid and not d.fallback_used
        assert d.usage == {"input": 1200, "output": 15,
                           "cache_read": 1000, "cache_creation": 200}
        assert d.latency_s >= 0

    @pytest.mark.parametrize("bad", [
        "not json at all",
        '{"move": "answer", "field_key": "off_enum_key"}',
        '{"move": "answer", "field_key": "none"}',
        '{"move": "dance", "field_key": "none"}',
        '{"move": "confirm", "field_key": "none", "extra": 1}',
    ])
    def test_invalid_output_falls_back_to_stub(self, persona, bad):
        k = _name_key(persona)
        a = actor.HaikuActor(persona, client=FakeClient(bad))
        prompt = "What is your %s?" % persona.facts[k]["keywords"][0]
        d = run(a.decide(prompt, []))
        assert d.fallback_used is True
        assert d.valid is False
        assert (d.move, d.field_key) == ("answer", k)  # the stub's decision
        assert d.usage["input"] == 1200

    def test_exception_and_refusal_fall_back(self, persona):
        a = actor.HaikuActor(persona, client=FakeClient(exc=RuntimeError("429")))
        d = run(a.decide("Welcome.", []))
        assert d.fallback_used and d.move == "acknowledge"
        a2 = actor.HaikuActor(
            persona, client=FakeClient('{"move":"confirm","field_key":"none"}',
                                       stop_reason="refusal"))
        d2 = run(a2.decide("Welcome.", []))
        assert d2.fallback_used and d2.move == "acknowledge"

    def test_cost(self, persona):
        c = actor.estimate_cost_usd({"input": 1_000_000, "output": 1_000_000,
                                     "cache_read": 0, "cache_creation": 0})
        assert c == pytest.approx(0.60)


# --------------------------------------------------------- API key / no Vertex
class TestHaikuApiOnly:
    def test_api_without_key_fails_fast(self, persona, monkeypatch):
        # A missing key must stop the run up front, not let every turn
        # quietly fall back to the stub and pass as a Haiku run.
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            actor.HaikuActor(persona)

    def test_constructs_with_key(self, persona, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
        actor.HaikuActor(persona)

    def test_no_vertex_client_anywhere(self):
        # Maintainer decision: Haiku goes through the Claude API (Anthropic
        # credits), never Vertex (Google pay-as-you-go billing).
        src = Path(actor.__file__).read_text(encoding="utf-8")
        assert "AnthropicVertex" not in src
        assert not hasattr(actor, "HaikuVertexActor")


# =========================================================================
# Per-form personas (bd polyglot-pdf-ya4vi.1 / ya4vi.2). Nothing below names
# a kit field id or reads form-kits/ (scar #10): ids come from the persona
# JSON and from the harness's own tables.
# =========================================================================
_PERSONAS_DIR = _REPO_ROOT / "scripts" / "spikes" / "sim_user" / "personas"
# (persona file, the strict key its true values are pinned to)
PINNED_PERSONAS = [
    ("w7_ana_nospell.json", "W7_EXPECTED"),
    ("w7_ana_selfcorrect.json", "W7_EXPECTED"),
    ("i90v2_elena_nospell.json", "I90V2_EXPECTED"),
]
SLIP_PERSONA = "w7_ana_selfcorrect.json"


def _load(name):
    return actor.load_persona(_PERSONAS_DIR / name)


def _expected_allowed(exp):
    allowed = exp if isinstance(exp, (list, tuple)) else [exp]
    return {harness._canon_value(a) for a in allowed}


@pytest.mark.parametrize("fname,table", PINNED_PERSONAS)
class TestPersonaPinnedToStrictKey:
    def test_keys_equal_the_strict_key(self, fname, table):
        persona = _load(fname)
        assert set(persona.facts) == set(getattr(harness, table))

    def test_every_true_value_satisfies_the_key(self, fname, table):
        persona = _load(fname)
        key = getattr(harness, table)
        bad = [fid for fid, f in persona.facts.items()
               if harness._canon_value(f["value"])
               not in _expected_allowed(key[fid])]
        assert bad == []

    def test_form_matches_a_registered_schema(self, fname, table):
        persona = _load(fname)
        assert persona.form in harness.SCHEMAS
        assert harness.SCHEMAS[persona.form]["expected"] is getattr(
            harness, table)

    def test_stub_routes_each_question_to_its_own_fact(self, fname, table):
        # the offline interviewers ask "What is your <keywords[0]>?"; the stub
        # must map that back to the SAME fact (no keyword collisions)
        persona = _load(fname)
        stub = actor.StubActor(persona)
        wrong = [fid for fid, f in persona.facts.items()
                 if stub._best_keyword_field(
                     "What is your %s?" % f["keywords"][0]) != fid]
        assert wrong == []


class TestI90V2Persona:
    def test_questions_and_persona_cover_the_same_fields_in_order(self):
        persona = _load("i90v2_elena_nospell.json")
        assert list(persona.facts) == [
            q["field_id"] for q in harness.I90V2_QUESTIONS]

    def test_identity_and_behavior(self):
        persona = _load("i90v2_elena_nospell.json")
        assert persona.persona_id == "i90v2_elena_nospell_v1"
        assert persona.form == "i90-v2"
        assert persona.behavior["spells_unprompted"] is False

    def test_declined_fields_are_empty_in_both_tables(self):
        persona = _load("i90v2_elena_nospell.json")
        declined = {fid for fid, e in harness.I90V2_EXPECTED.items()
                    if e == ""}
        assert declined
        assert {fid for fid, f in persona.facts.items()
                if f["value"] == ""} == declined

    def test_same_as_mailing_stays_a_natural_answer(self):
        # bd r3ham.10 measures how the model handles this phrasing: it must
        # not be reworded into a bare value
        persona = _load("i90v2_elena_nospell.json")
        same = [f for f in persona.facts.values()
                if "same as my mailing address" in f["answer"]]
        assert len(same) == 1
        assert same[0]["value"] in same[0]["answer"]

    def test_spell_strings_spell_the_value(self):
        persona = _load("i90v2_elena_nospell.json")
        spellable = [f for f in persona.facts.values() if f["spellable"]]
        assert spellable
        for f in spellable:
            assert f["spell"].replace(" - ", "").lower() == f["value"].lower()

    def test_default_persona_is_per_schema(self):
        for form in actor.DEFAULT_PERSONA_FILES:
            assert actor.load_default_persona(form).form == form
        assert actor.load_default_persona().persona_id == "w7_ana_nospell_v1"
        assert actor.load_default_persona("i90-v2").persona_id == \
            "i90v2_elena_nospell_v1"
        with pytest.raises(ValueError):
            actor.load_default_persona("i90")

    def test_sim_schemas_have_a_default_persona_and_a_strict_key(self):
        # the set of schemas --user sim accepts == the set with a default
        # persona, and each has a non-empty strict key
        assert set(harness.SIM_SCHEMAS) == set(actor.DEFAULT_PERSONA_FILES)
        for form in harness.SIM_SCHEMAS:
            assert harness.SCHEMAS[form]["expected"]


# ----------------------------------------------------------------- slips
class TestSlipFacts:
    def test_every_fact_of_the_selfcorrect_persona_has_a_slip(self):
        persona = _load(SLIP_PERSONA)
        assert persona.persona_id == "w7_ana_selfcorrect_v1"
        assert [fid for fid, f in persona.facts.items()
                if "slip" not in f] == []

    def test_selfcorrect_true_facts_equal_the_nospell_persona(self):
        slip, plain = _load(SLIP_PERSONA), _load("w7_ana_nospell.json")
        assert list(slip.facts) == list(plain.facts)
        for fid, f in slip.facts.items():
            assert {k: v for k, v in f.items() if k != "slip"} == \
                plain.facts[fid]

    def test_no_slip_satisfies_the_strict_key(self):
        # a field left holding its slip must score INCORRECT
        persona = _load(SLIP_PERSONA)
        holds = [fid for fid, f in persona.facts.items()
                 if harness._canon_value(f["slip"]["value"])
                 in _expected_allowed(harness.W7_EXPECTED[fid])]
        assert holds == []

    def test_a_slip_differs_from_the_truth_in_every_spoken_string(self):
        persona = _load(SLIP_PERSONA)
        for f in persona.facts.values():
            for k in ("value", "answer", "spoken"):
                assert f["slip"][k] != f[k]

    @pytest.mark.parametrize("mutate,why", [
        (lambda f: f.__setitem__("slip", "x"), "not an object"),
        (lambda f: f["slip"].pop("spoken"), "missing key"),
        (lambda f: f["slip"].__setitem__("extra", "x"), "extra key"),
        (lambda f: f["slip"].__setitem__("answer", ""), "empty"),
        (lambda f: f["slip"].__setitem__("value", 3), "not a string"),
        (lambda f: f["slip"].__setitem__("answer", f["answer"]), "equals truth"),
    ])
    def test_load_rejects_a_malformed_slip(self, tmp_path, mutate, why):
        raw = json.loads((_PERSONAS_DIR / SLIP_PERSONA).read_text(
            encoding="utf-8"))
        first = next(iter(raw["facts"]))
        mutate(raw["facts"][first])
        p = tmp_path / "bad_slip.json"
        p.write_text(json.dumps(raw), encoding="utf-8")
        with pytest.raises(ValueError):
            actor.load_persona(p)

    def test_stub_rejects_every_slip_readback_and_confirms_every_truth(self):
        persona = _load(SLIP_PERSONA)
        stub = actor.StubActor(persona)
        for fid, f in persona.facts.items():
            hist = [{"model_text": "q", "move": "answer", "field_key": fid}]
            bad = run(stub.decide("I have %s. Is that correct?"
                                  % f["slip"]["spoken"], hist))
            assert (bad.move, bad.field_key) == ("reject_and_correct", fid), fid
            good = run(stub.decide("I have %s. Is that correct?"
                                   % f["spoken"], hist))
            assert good.move == "confirm", fid


class TestSlipRendering:
    def test_first_answer_speaks_the_slip_then_the_truth(self):
        persona = _load(SLIP_PERSONA)
        for fid, f in persona.facts.items():
            spoken = set()
            first = actor.render("answer", fid, persona, random.Random(0),
                                 slips_spoken=spoken)
            assert first.slip is True
            assert first.values_spoken == [f["slip"]["answer"]]
            assert f["slip"]["answer"] in first.text
            assert spoken == set()          # render never marks; the caller does
            spoken.add(fid)
            second = actor.render("answer", fid, persona, random.Random(0),
                                  slips_spoken=spoken)
            assert second.slip is False
            assert second.values_spoken == [f["answer"]]

    def test_spell_and_correct_always_speak_the_truth(self):
        persona = _load(SLIP_PERSONA)
        for fid, f in persona.facts.items():
            for move in ("spell", "reject_and_correct"):
                r = actor.render(move, fid, persona, random.Random(1),
                                 slips_spoken=set())
                assert r.slip is False
                assert f["slip"]["answer"] not in r.text
                assert all(v in (f["answer"], f["spoken"], f.get("spell"))
                           for v in r.values_spoken)

    def test_no_slip_set_means_no_slips(self):
        persona = _load(SLIP_PERSONA)
        for fid, f in persona.facts.items():
            r = actor.render("answer", fid, persona, random.Random(0))
            assert r.slip is False and r.values_spoken == [f["answer"]]

    def test_a_persona_without_slips_never_slips(self):
        plain = _load("w7_ana_nospell.json")
        for fid in plain.facts:
            r = actor.render("answer", fid, plain, random.Random(0),
                             slips_spoken=set())
            assert r.slip is False


class TestActorNeverSeesTheSlip:
    def _slip_answers(self, persona):
        return [f["slip"]["answer"] for f in persona.facts.values()]

    def test_prompt_fact_sheet_lists_only_true_spoken_values(self):
        persona = _load(SLIP_PERSONA)
        text = actor.build_system_prompt(persona)
        for fid, f in persona.facts.items():
            line = next(x for x in text.splitlines()
                        if x.startswith("- %s | " % fid))
            assert line.split(" | ")[2] == f["spoken"]
        for s in self._slip_answers(persona):
            assert s not in text

    def test_prompt_tells_the_actor_to_judge_against_the_sheet_only(self):
        slip = actor.build_system_prompt(_load(SLIP_PERSONA))
        plain = actor.build_system_prompt(_load("w7_ana_nospell.json"))
        needle = "Judge every read-back ONLY against the fact sheet"
        assert needle in slip
        assert needle not in plain         # the no-slip personas are unchanged

    def test_request_carries_no_slip_text(self):
        persona = _load(SLIP_PERSONA)
        ha = actor.HaikuActor(persona, client=SimpleNamespace())
        fid = next(iter(persona.facts))
        hist = [{"model_text": "What is your first name?", "move": "answer",
                 "field_key": fid}]
        blob = json.dumps(ha.build_request("I have a read-back.", hist))
        for s in self._slip_answers(persona):
            assert s not in blob


# =========================================================================
# referee: the deterministic exact-match check on the actor's read-back
# verdicts. Parametrized over EVERY slipped fact in the persona, not a sample.
# =========================================================================
_REF_PERSONA = _load(SLIP_PERSONA)
_REF_FIDS = list(_REF_PERSONA.facts)


def _ref_long_enough(s):
    return actor.refereeable(s)


def _ref_hist(fid):
    return [{"model_text": "What is it?", "move": "answer", "field_key": fid}]


def _readback(value):
    return "I have %s. Is that correct?" % value


def _dec(move, fid=actor.NONE_KEY):
    return actor.Decision(move=move, field_key=fid)


@pytest.mark.parametrize("fid", _REF_FIDS)
class TestReferee:
    def test_a_reject_of_the_exact_true_value_becomes_a_confirm(self, fid):
        f = _REF_PERSONA.facts[fid]
        if not _ref_long_enough(f["spoken"]):
            pytest.skip("value too short to referee")
        d, label = actor.referee(_dec("reject_and_correct", fid),
                                 _readback(f["spoken"]), _ref_hist(fid),
                                 _REF_PERSONA, {fid})
        assert (d.move, d.field_key, label) == (
            "confirm", actor.NONE_KEY, "reject_to_confirm")

    def test_a_confirm_of_the_spoken_slip_becomes_a_reject(self, fid):
        f = _REF_PERSONA.facts[fid]
        if not _ref_long_enough(f["slip"]["spoken"]):
            pytest.skip("slip too short to referee")
        d, label = actor.referee(_dec("confirm"),
                                 _readback(f["slip"]["spoken"]),
                                 _ref_hist(fid), _REF_PERSONA, {fid})
        assert (d.move, d.field_key, label) == (
            "reject_and_correct", fid, "confirm_to_reject")

    def test_a_slip_not_yet_spoken_is_left_to_the_actor(self, fid):
        f = _REF_PERSONA.facts[fid]
        d, label = actor.referee(_dec("confirm"),
                                 _readback(f["slip"]["spoken"]),
                                 _ref_hist(fid), _REF_PERSONA, set())
        assert (d.move, label) == ("confirm", None)

    def test_a_read_back_holding_both_values_is_left_to_the_actor(self, fid):
        f = _REF_PERSONA.facts[fid]
        both = _readback("%s, or %s" % (f["spoken"], f["slip"]["spoken"]))
        for move, key in (("confirm", actor.NONE_KEY),
                          ("reject_and_correct", fid)):
            d, label = actor.referee(_dec(move, key), both, _ref_hist(fid),
                                     _REF_PERSONA, {fid})
            assert (d.move, label) == (move, None)

    def test_text_that_is_not_a_read_back_is_left_to_the_actor(self, fid):
        f = _REF_PERSONA.facts[fid]
        d, label = actor.referee(_dec("reject_and_correct", fid),
                                 "I have %s." % f["spoken"], _ref_hist(fid),
                                 _REF_PERSONA, {fid})
        assert (d.move, label) == ("reject_and_correct", None)

    def test_other_moves_are_never_touched(self, fid):
        f = _REF_PERSONA.facts[fid]
        for move in ("answer", "spell"):
            d, label = actor.referee(_dec(move, fid), _readback(f["spoken"]),
                                     _ref_hist(fid), _REF_PERSONA, {fid})
            assert (d.move, d.field_key, label) == (move, fid, None)


class TestRefereeLastReadback:
    """One heard window can hold two read-backs; the user answers the last one,
    so only it is evidence (bd ya4vi.3, I-90 run 20261120T232745Z turn 46)."""

    _ZIP = SimpleNamespace(facts={"z": {"value": "97203", "spoken": "9 7 2 0 3"}})
    _SLIP = SimpleNamespace(facts={"z": {
        "value": "97203", "spoken": "9 7 2 0 3",
        "slip": {"value": "97477", "spoken": "9 7 4 7 7"}}})

    def test_true_value_only_in_an_earlier_read_back_does_not_confirm(self):
        text = ("You provided the ZIP code nine seven two zero three. Is that "
                "correct? In the section regarding your information, what is "
                "your physical zip code?The physical zip code is nine zero two "
                "one zero. Is that correct?")
        d, label = actor.referee(_dec("reject_and_correct", "z"), text,
                                 _ref_hist("z"), self._ZIP, set())
        assert (d.move, label) == ("reject_and_correct", None)

    def test_true_value_in_the_last_read_back_still_confirms(self):
        text = ("The ZIP is nine zero two one zero. Is that correct? Sorry, "
                "the ZIP is nine seven two zero three. Is that correct?")
        d, label = actor.referee(_dec("reject_and_correct", "z"), text,
                                 _ref_hist("z"), self._ZIP, set())
        assert label == "reject_to_confirm"

    def test_slip_only_in_an_earlier_read_back_does_not_reject(self):
        text = ("The ZIP is nine seven four seven seven. Is that correct? "
                "I have updated it. The ZIP is nine seven two zero three now. "
                "Is that correct?")
        d, label = actor.referee(_dec("confirm"), text, _ref_hist("z"),
                                 self._SLIP, {"z"})
        assert (d.move, label) == ("confirm", None)

    def test_slip_in_the_last_read_back_still_rejects(self):
        text = ("The ZIP is nine seven two zero three. Is that correct? "
                "Actually I have nine seven four seven seven. Is that correct?")
        d, label = actor.referee(_dec("confirm"), text, _ref_hist("z"),
                                 self._SLIP, {"z"})
        assert label == "confirm_to_reject"

    @pytest.mark.parametrize("text", [
        "Your ZIP is nine seven two zero three? Is that right?",
        "Is it nine seven two zero three? Please confirm.",
        "Did I get that right? Your ZIP is nine seven two zero three.",
        "To confirm, your ZIP code is nine seven two zero three. Is that correct?",
        "The ZIP is nine seven two zero three. Is that correct? What is your city?",
        "<no speech>{pause} You said nine seven two zero three. Is that correct?",
    ])
    def test_one_read_back_is_judged_whatever_its_shape(self, text):
        d, label = actor.referee(_dec("reject_and_correct", "z"), text,
                                 _ref_hist("z"), self._ZIP, set())
        assert label == "reject_to_confirm"

    def test_last_readback_is_the_whole_text_for_one_cue(self):
        text = "Your ZIP is 97203? Is that right?"
        assert actor.last_readback(text) == text

    def test_last_readback_cuts_after_the_previous_cue(self):
        text = "ZIP 97203. Is that correct? Sorry, ZIP 90210. Is that correct?"
        assert actor.last_readback(text) == "? Sorry, ZIP 90210. Is that correct?"

    def test_last_readback_is_empty_without_a_cue(self):
        assert actor.last_readback("What is your ZIP code?") == ""
        assert actor.last_readback(None) == ""


class TestRefereeEdges:
    def test_every_slipped_fact_is_refereeable_both_ways(self):
        # the parametrized skips above must not quietly cover the whole set
        short = [fid for fid, f in _REF_PERSONA.facts.items()
                 if not (_ref_long_enough(f["spoken"])
                         and _ref_long_enough(f["slip"]["spoken"]))]
        assert len(short) < len(_REF_FIDS) // 4, short

    def test_a_spelled_read_back_matches_the_name(self):
        facts = {"n": {"value": "Corazon", "spoken": "Corazon",
                       "spell": "C - O - R - A - Z - O - N"}}
        p = SimpleNamespace(facts=facts)
        d, label = actor.referee(
            _dec("reject_and_correct", "n"),
            "You said C, O, R, A, Z, O, N. Is that correct?", _ref_hist("n"),
            p, set())
        assert label == "reject_to_confirm"

    def test_digit_words_match_a_digit_value(self):
        facts = {"t": {"value": "24981736", "spoken": "2 4 9 8 1 7 3 6"}}
        p = SimpleNamespace(facts=facts)
        d, label = actor.referee(
            _dec("reject_and_correct", "t"),
            "Your number is two four nine eight one seven three six. "
            "Is that correct?", _ref_hist("t"), p, set())
        assert label == "reject_to_confirm"

    @pytest.mark.parametrize("word", ["No", "Yes", "None", "AB"])
    def test_a_generic_or_short_value_is_never_refereed(self, word):
        facts = {"q": {"value": word.lower(), "spoken": word}}
        p = SimpleNamespace(facts=facts)
        d, label = actor.referee(_dec("reject_and_correct", "q"),
                                 "You said %s. Is that correct?" % word,
                                 _ref_hist("q"), p, set())
        assert (d.move, label) == ("reject_and_correct", None)

    def test_a_short_true_value_still_blocks_a_slip_override(self):
        # "Ana" vs slip "Alma": both in the read-back, so neither is acted on
        facts = {"n": {"value": "Ana", "spoken": "Ana",
                       "slip": {"value": "Alma", "spoken": "Alma"}}}
        p = SimpleNamespace(facts=facts)
        d, label = actor.referee(_dec("confirm"),
                                 "You said Alma or A, N, A. Is that correct?",
                                 _ref_hist("n"), p, {"n"})
        assert (d.move, label) == ("confirm", None)

    def test_a_value_inside_a_longer_word_does_not_match(self):
        facts = {"s": {"value": "male", "spoken": "Male"}}
        p = SimpleNamespace(facts=facts)
        d, label = actor.referee(_dec("reject_and_correct", "s"),
                                 "You said female. Is that correct?",
                                 _ref_hist("s"), p, set())
        assert (d.move, label) == ("reject_and_correct", None)

    def test_a_confirm_with_no_answered_field_is_left_alone(self):
        f = _REF_PERSONA.facts[_REF_FIDS[0]]
        d, label = actor.referee(_dec("confirm"),
                                 _readback(f["slip"]["spoken"]), [],
                                 _REF_PERSONA, set(_REF_FIDS))
        assert (d.move, label) == ("confirm", None)
