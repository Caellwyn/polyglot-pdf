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
