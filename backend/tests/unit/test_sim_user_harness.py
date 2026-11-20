"""
Unit tests for the simulated-user integration in
scripts/spikes/measure_form_session_costs.py (bd polyglot-pdf-tmu0f, E.3):
the per-generation recorder + turn gate, the SimDriver loop, the fail-fast
guards, scoring/cost lines, the committed per-run records, and a run()-level
end-to-end on a fake session.

Fully offline: a scripted fake model stands in for Gemini Live, a fake Cloud
STT stands in for Google, the offline StubActor stands in for Haiku. No
network, no API key. Form kits are NOT in git (CLAUDE.md scar #10): the schema
is a synthetic one built from the persona's own field ids, and nothing here
reads form-kits/. ASCII only.
"""
import asyncio
import fnmatch
import hashlib
import json
import random
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPIKES_DIR = str(_REPO_ROOT / "scripts" / "spikes")
if _SPIKES_DIR not in sys.path:
    sys.path.insert(0, _SPIKES_DIR)

import measure_form_session_costs as mfsc  # noqa: E402
from sim_user import actor as sim_actor  # noqa: E402

PERSONA = sim_actor.load_default_persona()
FIDS = list(PERSONA.facts)

# Short enough that a 22-field session runs in seconds, long enough that the
# playback condition is the ONLY thing holding the gate shut in the gate test.
FAST = mfsc.SimTiming(
    quiet_window_s=0.03, tool_resume_grace_s=0.05, gate_timeout_s=3.0,
    response_timeout_s=3.0, poll_s=0.01, usage_settle_s=0.0,
    chunk_sleep_s=0.0, max_redecide=3, max_consecutive_stalls=3,
    max_consecutive_fallbacks=5, silence_close_s=None)
FLOW_AUDIO_S = 0.1
SILENCE = mfsc.SimTiming(**{**FAST.__dict__, "silence_close_s": 0.15})


# ---------------------------------------------------------------------------
# synthetic schema + fakes
# ---------------------------------------------------------------------------
def synthetic_schema(drop=()):
    return {"form_metadata": {},
            "fields": [{"id": fid, "name": f["label"], "type": "text",
                        "section_id": "s1", "validation": {"required": False}}
                       for fid, f in PERSONA.facts.items() if fid not in drop]}


class ModelScript:
    """A tiny interviewer: asks each persona field in order, reads the answer
    back, and confirms on a yes. Shared by every fake session below."""

    def __init__(self, persona=PERSONA):
        self.persona = persona
        self.fids = list(persona.facts)
        self.k = 0
        self.stage = "ask"

    def question(self):
        f = self.persona.facts[self.fids[self.k]]
        return "What is your %s?" % f["keywords"][0]

    def greeting(self):
        return {"say": "Hello. " + self.question()}

    def respond(self, user_text):
        if self.k >= len(self.fids):
            return {"say": "All done."}
        fid = self.fids[self.k]
        f = self.persona.facts[fid]
        t = (user_text or "").lower()
        has_answer = f["answer"].lower() in t or f["spoken"].lower() in t
        readback = "I have %s. Is that correct?" % f["spoken"]
        if self.stage == "ask":
            if has_answer:
                self.stage = "readback"
                return {"say": readback, "fill": (fid, f["value"])}
            return {"say": self.question()}
        if t.startswith(("yes", "correct")):
            self.k += 1
            self.stage = "ask"
            tail = self.question() if self.k < len(self.fids) else "All done."
            return {"say": "Thank you. " + tail, "confirm": fid}
        if has_answer:
            return {"say": readback, "fill": (fid, f["value"])}
        return {"say": readback}


def fake_stt(pcm):
    return {"text": "stt heard something", "confidence": 0.95, "n_results": 1,
            "seconds": round(len(pcm) / 48000.0, 3), "billed_seconds": 15}


class FakeSession:
    """Driver-level fake: the model writes straight into a recorder and a
    state dict. `inject` records when the user started speaking."""

    def __init__(self, audio_s=FLOW_AUDIO_S, timing=FAST, tts_kind="gtts",
                 withhold=(), late_s=None, drip_s=0.0, talk_over=False):
        self.rec = mfsc.GenerationRecorder(
            quiet_window_s=timing.quiet_window_s,
            tool_resume_grace_s=timing.tool_resume_grace_s,
            silence_close_s=timing.silence_close_s)
        # response indices (0 = greeting) whose turn_complete is withheld;
        # late_s sends it that many seconds later; drip_s spreads the audio.
        self.withhold = set(withhold)
        self.late_s = late_s
        self.drip_s = drip_s
        self.talk_over = talk_over      # model audio arrives mid-injection
        self.n_emitted = 0
        self.state = {}
        self.client = SimpleNamespace(state=self.state)
        self.model = ModelScript()
        self.audio_s = audio_s
        self.inject_starts = []
        self.last_text = ""
        self.tasks = []
        self.tts = mfsc.TTSMouth(tts_kind, self._synth)

    def _synth(self, text):
        self.last_text = text
        return b"\x00\x00" * 640  # 40 ms at 16 kHz

    async def _emit(self, out):
        rec = self.rec
        await asyncio.sleep(0.005)
        if out.get("fill") or out.get("confirm"):
            rec.tool_start("update_form_fields")
            if out.get("fill"):
                fid, val = out["fill"]
                self.state[fid] = {"value": val, "confirmed": False}
            if out.get("confirm"):
                self.state[out["confirm"]]["confirmed"] = True
            rec.tool_end("update_form_fields")
        say = out["say"]
        rec.on_transcript(say[:4])
        rec.on_transcript(say[4:])
        idx = self.n_emitted
        self.n_emitted += 1
        if self.drip_s:
            part = int(24000 * self.audio_s) // 5
            for _ in range(5):
                rec.on_audio(b"\x00\x00" * part)
                await asyncio.sleep(self.drip_s / 5)
        else:
            rec.on_audio(b"\x00\x00" * int(24000 * self.audio_s))
        if idx in self.withhold:
            if self.late_s is not None:
                async def late():
                    await asyncio.sleep(self.late_s)
                    rec.boundary("turn_complete")
                self.tasks.append(asyncio.ensure_future(late()))
            return
        rec.boundary("turn_complete")

    async def greet(self):
        await self._emit(self.model.greeting())

    async def inject(self, pcm):
        self.inject_starts.append(time.monotonic())
        await asyncio.sleep(0.005)
        if self.talk_over:
            self.rec.on_audio(b"\x00\x00" * 480)
            self.rec.boundary("turn_complete")
            await asyncio.sleep(0.005)
        t_end = time.monotonic()
        self.tasks.append(asyncio.ensure_future(
            self._emit(self.model.respond(self.last_text))))
        return t_end


def make_driver(session, *, actor=None, ears="transcript", stt_fn=None,
                max_user_turns=500, timing=FAST):
    return mfsc.SimDriver(
        persona=PERSONA, actor=actor or sim_actor.StubActor(PERSONA),
        recorder=session.rec, client=session.client, tts=session.tts,
        inject=session.inject, stt_fn=stt_fn or fake_stt, ears=ears,
        max_user_turns=max_user_turns, timing=timing, rng=random.Random(0))


def run_driver(session, driver, finalize=True):
    async def go():
        await session.greet()
        await driver.run()
        if finalize:
            await driver.finalize_divergence()
    asyncio.run(go())


class FlakyActor:
    """The stub's decisions, flagged as a fallback per `pattern` (True =
    fallback), cycling."""

    def __init__(self, pattern, error="RuntimeError: boom"):
        self.stub = sim_actor.StubActor(PERSONA)
        self.pattern = list(pattern)
        self.error = error
        self.n = 0

    async def decide(self, model_text, history):
        d = await self.stub.decide(model_text, history)
        if self.pattern[self.n % len(self.pattern)]:
            d.fallback_used = True
            d.valid = False
            d.raw = {"error": self.error}
        self.n += 1
        return d


class SpyActor:
    def __init__(self):
        self.stub = sim_actor.StubActor(PERSONA)
        self.seen = []

    async def decide(self, model_text, history):
        self.seen.append(model_text)
        return await self.stub.decide(model_text, history)


# ---------------------------------------------------------------------------
# GenerationRecorder: PCM sliced per generation at the boundary
# ---------------------------------------------------------------------------
class TestRecorderCapture:
    def test_pcm_transcript_sliced_at_each_boundary(self):
        rec = mfsc.GenerationRecorder(clock=lambda: 0.0)
        rec.on_audio(b"\x01\x00" * 100, ts=1.0)
        rec.on_transcript("Hel", 1.0)
        rec.on_transcript("lo.", 1.1)
        rec.on_audio(b"\x02\x00" * 50, ts=1.2)
        rec.boundary("turn_complete", 1.3)
        rec.on_audio(b"\x03\x00" * 10, ts=2.0)
        rec.boundary("interrupted", 2.1)
        assert rec.n_closed == 2
        g0, g1 = rec.closed
        assert g0["pcm"] == b"\x01\x00" * 100 + b"\x02\x00" * 50
        assert g0["transcript"] == "Hello."
        assert g0["reason"] == "turn_complete"
        assert g0["t_first_audio"] == 1.0
        assert g0["audio_s"] == pytest.approx(150 * 2 / 48000.0)
        assert g1["pcm"] == b"\x03\x00" * 10
        assert g1["reason"] == "interrupted"
        assert g1["transcript"] == ""

    def test_empty_boundary_and_housekeeping_edges(self):
        rec = mfsc.GenerationRecorder(clock=lambda: 0.0)
        rec.on_audio(b"\x01\x00" * 4, ts=1.0)
        rec.boundary("buffer_cap", 1.1)      # housekeeping: must not close
        assert rec.n_closed == 0
        rec.boundary("turn_complete", 1.2)
        rec.boundary("turn_complete", 1.2)   # duplicate edge: nothing open
        assert rec.n_closed == 1
        assert rec.empty_boundaries == 1

    def test_tool_calls_recorded_with_their_generation(self):
        rec = mfsc.GenerationRecorder(clock=lambda: 0.0)
        rec.tool_start("update_form_fields", 1.0)
        rec.tool_end("update_form_fields", 1.1)
        rec.on_audio(b"\x00\x00" * 8, ts=1.2)
        rec.boundary("turn_complete", 1.3)
        assert rec.closed[0]["tool_calls"] == ["update_form_fields"]
        assert rec.closed[0]["pending_tools_at_close"] == 0

    def test_public_view_has_no_pcm(self):
        rec = mfsc.GenerationRecorder(clock=lambda: 0.0)
        rec.on_audio(b"\x00\x00" * 8, ts=1.0)
        rec.boundary("turn_complete", 1.1)
        pub = rec.public_generation(rec.closed[0])
        assert "pcm" not in pub
        json.dumps(pub)

    def test_fake_client_send_bytes_and_transcript_feed_the_recorder(self):
        client = mfsc.FakeClientWebSocket(
            synthetic_schema(), [{"field_id": FIDS[0]}])
        assert client.gen_recorder is None  # scripted default
        asyncio.run(client.send_bytes(b"\x07\x00" * 5))  # no recorder: no-op
        client.gen_recorder = mfsc.GenerationRecorder()

        async def go():
            await client.send_json({"type": "transcript", "data": "Hi there"})
            await client.send_bytes(b"\x09\x00" * 6)
        asyncio.run(go())
        client.gen_recorder.boundary("turn_complete")
        g = client.gen_recorder.closed[0]
        assert g["pcm"] == b"\x09\x00" * 6
        assert g["transcript"] == "Hi there"


# ---------------------------------------------------------------------------
# The gate: each condition holds it shut on its own
# ---------------------------------------------------------------------------
def _closed_gen(rec, first=10.0, audio_s=2.0, reason="turn_complete"):
    rec.on_audio(b"\x00\x00" * int(24000 * audio_s), ts=first)
    rec.boundary(reason, first)


def _scenario_all_open():
    rec = mfsc.GenerationRecorder(quiet_window_s=1.0, tool_resume_grace_s=2.0)
    _closed_gen(rec)                       # playback 10.0 -> 12.0
    return rec, 13.5, None


def _scenario_open_generation():
    rec, _, _ = _scenario_all_open()
    rec.on_audio(b"\x00\x00" * 4800, ts=13.0)   # a new generation is streaming
    return rec, 15.0, "closed_ok"


def _scenario_session_close():
    rec = mfsc.GenerationRecorder(quiet_window_s=1.0, tool_resume_grace_s=2.0)
    _closed_gen(rec, reason="session_close")
    return rec, 13.5, "closed_ok"


def _scenario_no_generation():
    return mfsc.GenerationRecorder(quiet_window_s=1.0), 13.5, "closed_ok"


def _scenario_pending_tool():
    rec = mfsc.GenerationRecorder(quiet_window_s=1.0, tool_resume_grace_s=2.0)
    rec.on_audio(b"\x00\x00" * 4800, ts=10.0)
    rec.tool_start("update_form_fields", 10.0)
    rec.boundary("turn_complete", 10.1)    # closed while the tool is in flight
    return rec, 13.5, "no_pending_tool"


def _scenario_tool_resume_grace():
    rec = mfsc.GenerationRecorder(quiet_window_s=1.0, tool_resume_grace_s=2.0)
    rec.on_audio(b"\x00\x00" * 4800, ts=10.0)
    rec.tool_start("update_form_fields", 10.0)
    rec.boundary("turn_complete", 10.1)
    rec.tool_end("update_form_fields", 13.0)   # returns after the edge
    return rec, 14.0, "no_pending_tool"        # grace runs to 15.0


def _scenario_playback_not_ended():
    rec = mfsc.GenerationRecorder(quiet_window_s=1.0)
    _closed_gen(rec)                       # playback 10.0 -> 12.0
    return rec, 11.5, "playback_ended"     # quiet (1.5 >= 1.0), still playing


def _scenario_not_quiet():
    rec = mfsc.GenerationRecorder(quiet_window_s=1.0)
    _closed_gen(rec, audio_s=0.1)          # playback over by 10.1
    return rec, 10.5, "quiet"


GATE_SCENARIOS = [
    _scenario_all_open, _scenario_open_generation, _scenario_session_close,
    _scenario_no_generation, _scenario_pending_tool,
    _scenario_tool_resume_grace, _scenario_playback_not_ended,
    _scenario_not_quiet,
]


class TestGateState:
    @pytest.mark.parametrize("scenario", GATE_SCENARIOS,
                             ids=[s.__name__ for s in GATE_SCENARIOS])
    def test_exactly_the_expected_condition_fails(self, scenario):
        rec, now, failing = scenario()
        st = rec.gate_state(now)
        conditions = ("closed_ok", "no_pending_tool", "playback_ended", "quiet")
        for c in conditions:
            assert st[c] is (c != failing), (scenario.__name__, c, st)
        assert st["open"] is (failing is None)

    def test_tool_resume_grace_elapses(self):
        rec, _, _ = _scenario_tool_resume_grace()
        assert rec.gate_state(15.5)["open"] is True

    def test_interrupted_edge_opens_the_gate_too(self):
        rec = mfsc.GenerationRecorder(quiet_window_s=1.0)
        _closed_gen(rec, reason="interrupted")
        assert rec.gate_state(13.5)["open"] is True

    def test_playback_queues_behind_an_earlier_generation(self):
        rec = mfsc.GenerationRecorder(quiet_window_s=0.0)
        _closed_gen(rec, first=10.0, audio_s=4.0)    # 10.0 -> 14.0
        _closed_gen(rec, first=10.5, audio_s=1.0)    # queues: 14.0 -> 15.0
        assert rec.gate_state(14.5)["playback_ended"] is False
        assert rec.gate_state(15.1)["playback_ended"] is True


# ---------------------------------------------------------------------------
# Exit criterion 1: the user never speaks before simulated playback ends
# ---------------------------------------------------------------------------
class TestGateEnforcedInTheLoop:
    def test_user_does_not_speak_before_playback_ends(self):
        session = FakeSession(audio_s=0.4)   # all audio arrives at once
        driver = make_driver(session, max_user_turns=4)
        run_driver(session, driver)
        assert len(session.inject_starts) == 4
        assert driver.gate_violations == 0
        for k, t_start in enumerate(session.inject_starts):
            g = session.rec.closed[k]    # the generation this turn answers
            assert t_start >= g["t_first_audio"] + g["audio_s"] - 0.002, k
        assert all(t["gate_open_at_start"] for t in driver.user_turns)

    def test_gate_violation_is_counted_when_the_gate_shuts_at_start(self):
        session = FakeSession()
        driver = make_driver(session, max_user_turns=3)
        real = session.rec.gate_state
        calls = {"at_start": 0}

        def flaky(now=None):
            st = real(now)
            if now is not None:   # the check made as the user starts speaking
                calls["at_start"] += 1
                if calls["at_start"] == 2:
                    return dict(st, open=False, quiet=False)
            return st
        session.rec.gate_state = flaky
        run_driver(session, driver)
        assert driver.gate_violations == 1
        flags = [t["gate_open_at_start"] for t in driver.user_turns]
        assert flags == [True, False, True]

    def test_gate_timeout_is_a_stall_not_a_spoken_turn(self):
        session = FakeSession()
        timing = mfsc.SimTiming(**{**FAST.__dict__, "gate_timeout_s": 0.2,
                                   "max_consecutive_stalls": 2})
        driver = make_driver(session, timing=timing)

        async def go():
            await session.greet()
            session.rec.on_audio(b"\x00\x00" * 480)   # a generation never closes
            await driver.run()
        asyncio.run(go())
        assert driver.user_turns == []
        assert driver.gate_timeouts >= 1
        assert driver.stop_reason == "stalls"
        assert driver.gate_violations == 0


# ---------------------------------------------------------------------------
# Exit criterion 2 (driver level): a full W-7 persona session, offline stub
# ---------------------------------------------------------------------------
class TestFullSessionOnFakeSession:
    def test_every_fact_field_filled_and_confirmed(self):
        session = FakeSession()
        driver = make_driver(session)
        run_driver(session, driver)
        assert driver.stop_reason == "complete"
        assert driver.all_done()
        assert mfsc.count_filled_confirmed(session.state, FIDS) == len(FIDS)
        assert driver.gate_violations == 0
        assert mfsc.count_off_sheet(PERSONA, driver.user_turns) == 0
        assert len(driver.fallbacks) == 0

    def test_max_user_turns_stops_the_run(self):
        session = FakeSession()
        driver = make_driver(session, max_user_turns=3)
        run_driver(session, driver)
        assert driver.stop_reason == "max_user_turns"
        assert len(driver.user_turns) == 3

    def test_ears_transcript_vs_stt_choose_the_text(self):
        for ears, needle in (("transcript", "application type"),
                             ("stt", "stt heard something")):
            session = FakeSession()
            spy = SpyActor()
            driver = make_driver(session, actor=spy, ears=ears,
                                 max_user_turns=1)
            run_driver(session, driver)
            assert needle in spy.seen[0], (ears, spy.seen[0])
            assert driver.user_turns[0]["ears"] == ears

    def test_one_stt_pass_per_generation_in_both_ears_modes(self):
        for ears in ("transcript", "stt"):
            session = FakeSession()
            calls = []

            def counting(pcm, calls=calls):
                calls.append(len(pcm))
                return fake_stt(pcm)
            driver = make_driver(session, ears=ears, stt_fn=counting,
                                 max_user_turns=4)
            run_driver(session, driver)
            n_gens = session.rec.n_closed
            assert n_gens >= 4
            assert len(calls) == n_gens, ears
            recs = driver.generation_records
            assert len(recs) == n_gens
            assert all(r["persona_id"] == PERSONA.persona_id for r in recs)
            assert all("score" in r and "verdict" in r["score"] for r in recs)

    def test_divergence_scores_expected_spellings_of_spellable_facts(self):
        session = FakeSession()
        driver = make_driver(session, max_user_turns=1)
        run_driver(session, driver)
        spelled = [f["spell"] for f in PERSONA.facts.values()
                   if f.get("spellable")]
        assert driver.expected_spellings == spelled
        scored = driver.generation_records[0]["score"]
        assert [e["expected"] for e in scored["expected_spellings"]] == spelled


# ---------------------------------------------------------------------------
# Fail fast on a degraded actor
# ---------------------------------------------------------------------------
class TestFallbackFailFast:
    def test_five_consecutive_fallbacks_abort_the_run(self):
        session = FakeSession()
        driver = make_driver(session, actor=FlakyActor([True]))
        run_driver(session, driver, finalize=False)
        assert driver.aborted is True
        assert driver.stop_reason == "fallback_streak"
        assert len(driver.fallbacks) == 5
        assert driver.fallbacks[-1]["error"] == "RuntimeError: boom"
        assert "boom" in driver.abort_message
        # it stopped at the fifth decision: the fifth turn was never spoken
        assert len(driver.user_turns) == 4

    def test_a_good_decision_resets_the_streak(self):
        session = FakeSession()
        driver = make_driver(session, actor=FlakyActor([True] * 4 + [False]),
                             max_user_turns=15)
        run_driver(session, driver, finalize=False)
        assert driver.aborted is False
        assert driver.stop_reason == "max_user_turns"
        assert len(driver.fallbacks) == 12   # 4 of every 5 decisions, counted

    def test_non_fallback_actor_records_zero(self):
        session = FakeSession()
        driver = make_driver(session, max_user_turns=2)
        run_driver(session, driver, finalize=False)
        assert driver.fallbacks == [] and driver.aborted is False


# ---------------------------------------------------------------------------
# Long playback, withheld completion, stall streaks
# ---------------------------------------------------------------------------
def _timing(**kw):
    return mfsc.SimTiming(**{**FAST.__dict__, **kw})


class TestLongPlaybackIsNotAStall:
    def test_gate_timeout_runs_from_expected_playback_end(self):
        # 1.2 s of audio arrives at once; the gate timeout is 0.3 s. Waiting
        # for playback longer than the timeout must not count as a stall.
        timing = _timing(gate_timeout_s=0.3)
        session = FakeSession(audio_s=1.2, timing=timing)
        driver = make_driver(session, timing=timing, max_user_turns=2)
        run_driver(session, driver)
        assert len(driver.user_turns) == 2
        assert driver.gate_timeouts == 0
        assert driver.stalls == 0
        assert driver.gate_violations == 0
        assert all(t["gate_wait_s"] >= 1.0 for t in driver.user_turns)

    def test_response_timeout_extends_while_audio_is_still_arriving(self):
        timing = _timing(response_timeout_s=0.2)
        session = FakeSession(audio_s=0.1, timing=timing, drip_s=0.6)
        driver = make_driver(session, timing=timing, max_user_turns=2)
        run_driver(session, driver)
        assert driver.stalls == 0
        assert [t["response_stalled"] for t in driver.user_turns] == [False] * 2

    def test_expected_playback_end_counts_the_open_generation(self):
        rec = mfsc.GenerationRecorder(clock=lambda: 0.0)
        rec.on_audio(b"\x00\x00" * 48000, ts=10.0)     # 2.0 s, still open
        assert rec.expected_playback_end() == pytest.approx(12.0)
        rec.boundary("turn_complete", 10.1)
        assert rec.expected_playback_end() == pytest.approx(12.0)


def _silence_rec(**kw):
    kw.setdefault("silence_close_s", 5.0)
    return mfsc.GenerationRecorder(quiet_window_s=1.0, tool_resume_grace_s=2.0,
                                   clock=lambda: 0.0, **kw)


class TestSilenceClose:
    def _open_audio(self, rec, ts=10.0):
        rec.on_audio(b"\x00\x00" * 4800, ts=ts)

    def test_closes_with_reason_silence_and_opens_the_gate(self):
        rec = _silence_rec()
        self._open_audio(rec)
        assert rec.maybe_silence_close(14.9) is False
        assert rec.maybe_silence_close(15.1) is True
        assert rec.closed[0]["reason"] == "silence"
        assert rec.silence_closes == 1
        assert rec.gate_state(30.0)["open"] is True

    def test_each_blocking_condition_prevents_the_close(self):
        # transcript only: no audio yet
        rec = _silence_rec()
        rec.on_transcript("hi", 10.0)
        assert rec.maybe_silence_close(30.0) is False
        # tool pending
        rec = _silence_rec()
        self._open_audio(rec)
        rec.tool_start("t", 11.0)
        assert rec.maybe_silence_close(30.0) is False
        # inside the post-tool grace window
        rec.tool_end("t", 29.0)
        assert rec.maybe_silence_close(30.0) is False
        assert rec.maybe_silence_close(31.5) is True
        # disabled
        rec = _silence_rec(silence_close_s=None)
        self._open_audio(rec)
        assert rec.maybe_silence_close(99.0) is False
        # nothing open
        assert _silence_rec().maybe_silence_close(99.0) is False

    def test_recent_transcript_keeps_the_generation_open(self):
        rec = _silence_rec()
        self._open_audio(rec)
        rec.on_transcript("still talking", 14.0)
        assert rec.maybe_silence_close(15.5) is False
        assert rec.maybe_silence_close(19.5) is True

    def test_late_completion_is_recorded_not_a_phantom_generation(self):
        rec = _silence_rec()
        self._open_audio(rec)
        rec.maybe_silence_close(16.0)
        rec.boundary("turn_complete", 18.0)
        assert rec.n_closed == 1
        g = rec.closed[0]
        assert g["late_completion_reason"] == "turn_complete"
        assert g["late_completion_delay_s"] == pytest.approx(2.0)
        assert rec.late_completions == 1 and rec.empty_boundaries == 0
        rec.boundary("turn_complete", 18.1)    # a duplicate edge
        assert rec.late_completions == 1 and rec.empty_boundaries == 1
        pub = rec.public_generation(g)
        assert pub["late_completion_reason"] == "turn_complete"

    def test_boundary_after_new_audio_closes_the_new_generation(self):
        rec = _silence_rec()
        self._open_audio(rec)
        rec.maybe_silence_close(16.0)
        rec.on_audio(b"\x00\x00" * 480, ts=17.0)    # the model spoke again
        rec.boundary("turn_complete", 17.5)
        assert rec.n_closed == 2
        assert rec.closed[1]["reason"] == "turn_complete"
        assert "late_completion_reason" not in rec.closed[0]
        assert rec.late_completions == 0

    def test_loop_withheld_completion_is_a_normal_turn(self):
        session = FakeSession(timing=SILENCE, withhold={1})
        driver = make_driver(session, timing=SILENCE, max_user_turns=3)
        run_driver(session, driver)
        assert [g["reason"] for g in session.rec.closed][:3] == [
            "turn_complete", "silence", "turn_complete"]
        assert session.rec.silence_closes == 1
        assert len(driver.user_turns) == 3
        assert driver.stalls == 0 and driver.gate_timeouts == 0
        assert all(t["response_stalled"] is False for t in driver.user_turns)
        assert any(t["heard_silence_closed"] for t in driver.user_turns)
        assert driver.gate_violations == 0

    def test_loop_late_completion_makes_no_extra_generation(self):
        # silence close at ~0.1 s, the late edge at 0.2 s, the user (held by
        # the 0.3 s quiet window) speaks after that
        timing = _timing(silence_close_s=0.1, quiet_window_s=0.3)
        session = FakeSession(timing=timing, withhold={1}, late_s=0.2)
        driver = make_driver(session, timing=timing, max_user_turns=3)
        run_driver(session, driver)
        assert session.rec.n_closed == 4      # greeting + one per user turn
        late = [g for g in session.rec.closed if g["reason"] == "silence"]
        assert len(late) == 1
        assert late[0]["late_completion_reason"] == "turn_complete"
        assert session.rec.late_completions == 1


class TestSpellbackClip:
    """The client plays a name_spellback clip and the model stays silent; the
    simulated user has to hear that clip."""

    @staticmethod
    def _handle(client):
        async def go():      # _reply schedules on the running loop
            client._handle_spellback({"request_id": "r1"})
        asyncio.run(go())

    def _client(self, value="Ana"):
        client = mfsc.FakeClientWebSocket(
            synthetic_schema(), [{"field_id": FIDS[0]}])
        client.service = SimpleNamespace(
            handle_spellback_response=lambda rid, payload: None)
        client.state[FIDS[0]] = {"value": value, "confirmed": False}
        client.gen_recorder = mfsc.GenerationRecorder(
            spellback_s_per_token=0.5)
        return client

    def test_handler_feeds_the_backend_clip_text_to_the_open_generation(self):
        from backend.services.spellback_tts import build_spellback_text
        client = self._client("Ana")
        rec = client.gen_recorder
        rec.tool_start("name_spellback", 10.0)
        self._handle(client)
        rec.boundary("turn_complete", 10.2)
        g = rec.closed[0]
        assert g["spellback_text"] == build_spellback_text("Ana", "en-US")
        assert "A, N, A" in g["spellback_text"]
        assert rec.spellback_clips == 1
        assert g["audio_s"] == 0.0 and g["transcript"] == ""

    def test_scripted_client_without_recorder_is_unaffected(self):
        client = self._client()
        client.gen_recorder = None
        self._handle(client)
        assert client.spellback_events[0]["status"] == "delivered"

    def test_clip_text_is_heard_in_both_ears_modes(self):
        gens = [{"transcript": "", "stt": {"text": ""},
                 "spellback_text": "You said A, N, A. Is that correct?"},
                {"transcript": "ok", "stt": {"text": "okay"}}]
        for ears, want in (("transcript", "You said A, N, A. Is that correct? ok"),
                           ("stt", "You said A, N, A. Is that correct? okay")):
            assert mfsc.ears_text(gens, ears) == want

    def test_clip_playback_holds_the_gate(self):
        rec = mfsc.GenerationRecorder(
            quiet_window_s=0.0, spellback_s_per_token=0.5, clock=lambda: 0.0)
        rec.tool_start("name_spellback", 10.0)
        rec.on_spellback("one two three four", 10.0)     # 4 tokens -> 2.0 s
        rec.tool_end("name_spellback", 10.1)
        rec.boundary("turn_complete", 10.2)
        assert rec.expected_playback_end() == pytest.approx(12.0)
        assert rec.gate_state(11.0)["playback_ended"] is False
        assert rec.gate_state(12.1)["playback_ended"] is True
        assert rec.public_generation(rec.closed[0])["spellback_text"]

    def test_open_generation_playback_includes_the_clip(self):
        rec = mfsc.GenerationRecorder(spellback_s_per_token=0.5,
                                      clock=lambda: 0.0)
        rec.on_spellback("a b", 10.0)
        assert rec.expected_playback_end() == pytest.approx(11.0)

    def test_clip_after_the_generation_closed_attaches_to_it(self):
        rec = mfsc.GenerationRecorder(spellback_s_per_token=0.5,
                                      clock=lambda: 0.0)
        rec.on_audio(b"\x00\x00" * 480, ts=10.0)
        rec.boundary("turn_complete", 10.1)
        rec.on_spellback("a b c", 10.5)
        assert rec.n_closed == 1
        assert rec.closed[0]["spellback_text"] == "a b c"
        assert rec.playback_end == pytest.approx(12.0)

    def test_loop_hears_the_clip_and_waits_for_it(self):
        # one model turn that only plays a clip: no transcript, no audio
        timing = _timing(spellback_s_per_token=0.1)
        session = FakeSession(timing=timing)
        spy = SpyActor()
        driver = make_driver(session, actor=spy, timing=timing,
                             max_user_turns=1)
        clip = "You said A, N, A. Is that correct?"      # 8 tokens -> 0.8 s

        async def go():
            session.rec.tool_start("name_spellback")
            session.rec.on_spellback(clip)
            session.rec.tool_end("name_spellback")
            session.rec.boundary("turn_complete")
            await driver.run()
        asyncio.run(go())
        assert clip in spy.seen[0]
        assert driver.rec.spellback_clips == 1
        t = driver.user_turns[0]
        assert t["ears_text"] == clip
        assert t["gate_wait_s"] >= 0.6
        assert driver.gate_violations == 0


def _err_stt(pcm):
    return {"text": "", "confidence": 0.0, "n_results": 0, "seconds": 1.0,
            "billed_seconds": 0, "verdict": "STT_ERROR",
            "error": "403 quota project required"}


class TestSttHealth:
    def test_quota_project_resolution(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_CLOUD_QUOTA_PROJECT", raising=False)
        monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
        assert mfsc.resolve_quota_project() == mfsc.VERTEX_PROJECT_DEFAULT
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "vertex-proj")
        assert mfsc.resolve_quota_project() == "vertex-proj"
        monkeypatch.setenv("GOOGLE_CLOUD_QUOTA_PROJECT", "quota-proj")
        assert mfsc.resolve_quota_project() == "quota-proj"

    def test_unresolvable_quota_project_fails_fast(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_CLOUD_QUOTA_PROJECT", raising=False)
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "")
        with pytest.raises(SystemExit) as ei:
            mfsc.resolve_quota_project()
        assert "quota project" in str(ei.value)

    def test_preflight_probe(self):
        mfsc.probe_stt(fake_stt)
        with pytest.raises(SystemExit) as ei:
            mfsc.probe_stt(_err_stt)
        assert "403 quota project required" in str(ei.value)
        with pytest.raises(SystemExit):
            mfsc.probe_stt(lambda pcm: {"text": "", "error": "boom"})

    def test_error_text_is_kept_in_every_generation_record(self):
        session = FakeSession()
        driver = make_driver(session, stt_fn=_err_stt, max_user_turns=2)
        run_driver(session, driver)
        recs = driver.generation_records
        assert recs and all(
            r["stt_error"] == "403 quota project required" for r in recs)
        assert all(r["score"]["verdict"] == "STT_ERROR" for r in recs)

    def test_systematic_failure_marks_the_divergence_invalid(self):
        session = FakeSession()
        driver = make_driver(session, stt_fn=_err_stt, max_user_turns=3)
        run_driver(session, driver)
        rep = driver.divergence_report()
        assert rep["valid"] is False
        assert rep["stt_error_rate"] == 1.0
        assert rep["first_error"] == "403 quota project required"

    def test_error_rate_threshold(self):
        def pattern(bad_every):
            n = {"i": 0}

            def fn(pcm):
                n["i"] += 1
                return _err_stt(pcm) if n["i"] % bad_every == 0 else fake_stt(pcm)
            return fn
        for fn, valid in ((pattern(4), True), (pattern(1), False)):
            session = FakeSession()
            driver = make_driver(session, stt_fn=fn, max_user_turns=7)
            run_driver(session, driver)
            assert driver.stt_calls >= 6
            assert driver.divergence_report()["valid"] is valid

    def test_a_healthy_run_is_valid(self):
        session = FakeSession()
        driver = make_driver(session, max_user_turns=3)
        run_driver(session, driver)
        assert driver.divergence_report()["valid"] is True

    def test_unsent_clips_are_not_counted_as_calls(self):
        session = FakeSession(audio_s=0.0)       # no audio -> NO_AUDIO
        driver = make_driver(session, max_user_turns=2)
        run_driver(session, driver)
        assert driver.stt_calls == 0
        assert driver.divergence_report()["valid"] is False

    def test_ears_stt_aborts_when_the_opening_calls_all_fail(self):
        session = FakeSession()
        driver = make_driver(session, stt_fn=_err_stt, ears="stt")
        run_driver(session, driver, finalize=False)
        assert driver.aborted is True
        assert driver.stop_reason == "stt_failure"
        assert "403 quota project required" in driver.abort_message
        assert len(driver.user_turns) == mfsc.SIM_STT_FIRST_K - 1


class TestGateViolationMeasuresOverlap:
    """gate_violations is a measurement: did the model talk while the user
    was speaking (or was the gate shut when the user started)?"""

    def test_model_audio_during_the_users_speech_is_a_violation(self):
        session = FakeSession(talk_over=True)
        driver = make_driver(session, max_user_turns=2)
        run_driver(session, driver)
        assert len(driver.user_turns) == 2
        # the gate was open at the start of every turn ...
        assert all(t["gate_open_at_start"] for t in driver.user_turns)
        # ... yet the model talked over the user, and that is what counts
        assert driver.gate_violations == 2
        for t in driver.public_user_turns():
            assert t["overlapped"] is True
            assert t["overlap_audio_s"] > 0
            assert t["gate_violation"] is True

    def test_clean_turns_are_not_violations(self):
        session = FakeSession()
        driver = make_driver(session, max_user_turns=3)
        run_driver(session, driver)
        assert driver.gate_violations == 0
        for t in driver.public_user_turns():
            assert t["overlapped"] is False
            assert t["overlap_audio_s"] == 0.0
            assert t["gate_violation"] is False

    def test_gate_shut_at_start_still_counts(self):
        session = FakeSession()
        driver = make_driver(session, max_user_turns=1)
        real = session.rec.gate_state

        def flaky(now=None):
            st = real(now)
            return dict(st, open=False) if now is not None else st
        session.rec.gate_state = flaky
        run_driver(session, driver)
        assert driver.gate_violations == 1
        assert driver.user_turns[0]["overlapped"] is False

    def test_recorder_overlap_window(self):
        rec = mfsc.GenerationRecorder(clock=lambda: 0.0)
        rec.on_audio(b"\x00\x00" * 24000, ts=10.0)       # 1.0 s, opens a gen
        rec.boundary("turn_complete", 10.1)
        rec.on_audio(b"\x00\x00" * 12000, ts=20.0)       # 0.5 s, opens a gen
        assert rec.overlap(9.0, 9.9) == (0.0, 0)
        assert rec.overlap(9.0, 10.0) == (pytest.approx(1.0), 1)
        assert rec.overlap(15.0, 25.0) == (pytest.approx(0.5), 1)
        assert rec.overlap(10.5, 19.9) == (0.0, 0)


class TestStaleViewAfterRedecideCap:
    def test_generations_closed_after_the_decision_view_are_heard_next(self):
        timing = _timing(max_redecide=0)
        session = FakeSession(timing=timing)
        spy = SpyActor()
        state = {"n": 0}

        class Interrupting:
            """On the first decision the model speaks again while the actor
            is still deciding, so a generation closes after the view."""
            async def decide(self, model_text, history):
                state["n"] += 1
                if state["n"] == 1:
                    await session._emit({"say": "extra unheard words"})
                return await spy.decide(model_text, history)

        driver = make_driver(session, actor=Interrupting(), timing=timing,
                             max_user_turns=2)
        run_driver(session, driver)
        heard = [i for t in driver.user_turns for i in t["generations_heard"]]
        extra = next(g["index"] for g in session.rec.closed
                     if "extra unheard words" in g["transcript"])
        assert extra in heard                       # not skipped
        assert extra not in driver.user_turns[0]["generations_heard"]
        assert "extra unheard words" in spy.seen[1]  # fed the next turn's ears
        assert "extra unheard words" not in spy.seen[0]


class TestStallStreaks:
    def test_a_received_generation_resets_the_response_streak(self):
        session = FakeSession()
        driver = make_driver(session, max_user_turns=0)
        driver._consec_stalls = 2
        run_driver(session, driver, finalize=False)
        # no user turn was ever taken, so only the "got a generation, no
        # previous turn" branch can have reset it
        assert driver.user_turns == []
        assert driver._consec_stalls == 0

    def _flaky_gate(self, session, closed_for_s):
        """The poll-time gate stays shut for `closed_for_s` after its first
        poll (None = forever)."""
        real = session.rec.gate_state
        t_first = {}

        def gs(now=None):
            st = real(now)
            if now is None:
                t0 = t_first.setdefault("t", time.monotonic())
                if closed_for_s is None or time.monotonic() - t0 < closed_for_s:
                    return dict(st, open=False)
            return st
        session.rec.gate_state = gs

    def test_gate_timeouts_below_the_limit_recover_and_reset(self):
        timing = _timing(gate_timeout_s=0.2)
        session = FakeSession(timing=timing)
        self._flaky_gate(session, 0.6)         # 2 timeouts, then open
        driver = make_driver(session, timing=timing, max_user_turns=2)
        run_driver(session, driver)
        assert driver.gate_timeouts == 2
        assert driver.stop_reason == "max_user_turns"
        assert len(driver.user_turns) == 2
        assert driver._consec_gate_timeouts == 0

    def test_gate_timeouts_at_the_limit_stop_the_run(self):
        timing = _timing(gate_timeout_s=0.1)
        session = FakeSession(timing=timing)
        self._flaky_gate(session, None)
        driver = make_driver(session, timing=timing, max_user_turns=2)
        run_driver(session, driver, finalize=False)
        assert driver.stop_reason == "stalls"
        assert driver.user_turns == []
        assert driver.gate_timeouts == 3

    def test_turn_records_carry_stall_flag_and_gate_wait(self):
        session = FakeSession()
        driver = make_driver(session, max_user_turns=3)
        run_driver(session, driver)
        for t in driver.public_user_turns():
            assert t["response_stalled"] in (True, False)
            assert isinstance(t["gate_wait_s"], float)


# ---------------------------------------------------------------------------
# Guards: fact sheet vs schema, flags
# ---------------------------------------------------------------------------
class TestGuards:
    def test_missing_fact_key_fails_fast(self):
        mfsc.check_factsheet_against_schema(PERSONA, synthetic_schema())
        with pytest.raises(SystemExit) as ei:
            mfsc.check_factsheet_against_schema(
                PERSONA, synthetic_schema(drop=(FIDS[3],)))
        assert FIDS[3] in str(ei.value)

    def test_kit_hash_is_the_file_sha256(self, tmp_path):
        p = tmp_path / "schema.json"
        p.write_bytes(b'{"fields": []}')
        assert mfsc.kit_sha256(p) == hashlib.sha256(b'{"fields": []}').hexdigest()

    @pytest.mark.parametrize("argv,needle", [
        (["--schema", "i90"], "W-7 only"),
        (["--schema", "w7", "--arm", "dti"], "--continuous"),
        (["--schema", "w7", "--continuous"], "--arm dti"),
        (["--schema", "w7", "--arm", "dti", "--continuous",
          "--max-user-turns", "0"], "max-user-turns"),
    ])
    def test_sim_flag_validation(self, argv, needle):
        args = mfsc.build_parser().parse_args(["--user", "sim"] + argv)
        with pytest.raises(SystemExit) as ei:
            mfsc.validate_sim_args(args, PERSONA)
        assert needle in str(ei.value)

    def test_persona_for_another_form_is_refused(self):
        other = sim_actor.Persona("p", "i90", "d", {"spells_unprompted": False},
                                  PERSONA.facts)
        args = mfsc.build_parser().parse_args(
            ["--user", "sim", "--schema", "w7", "--arm", "dti",
             "--continuous"])
        with pytest.raises(SystemExit):
            mfsc.validate_sim_args(args, other)
        mfsc.validate_sim_args(args, PERSONA)   # the real persona passes

    def test_cli_defaults_keep_the_scripted_path(self):
        args = mfsc.build_parser().parse_args([])
        assert args.user == "script"
        assert args.ears == "transcript"
        assert args.actor == "haiku"
        assert args.tts == "gtts"
        assert args.persona is None
        assert args.max_user_turns == mfsc.SIM_DEFAULT_MAX_USER_TURNS == 150


# ---------------------------------------------------------------------------
# Scoring + cost helpers
# ---------------------------------------------------------------------------
class TestScoringHelpers:
    def test_filled_confirmed_needs_both_and_counts_declined_empty(self):
        state = {FIDS[0]: {"value": "x", "confirmed": True},
                 FIDS[1]: {"value": "y", "confirmed": False},
                 FIDS[2]: {"value": "", "confirmed": True},     # declined
                 FIDS[3]: {"value": None, "confirmed": True}}
        assert mfsc.count_filled_confirmed(state, FIDS) == 2

    def test_off_sheet_counts_only_non_fact_sheet_strings(self):
        f = PERSONA.facts[FIDS[2]]
        ok = [{"values_spoken": [f["answer"], f["spoken"], f["spell"]]}]
        assert mfsc.count_off_sheet(PERSONA, ok) == 0
        bad = ok + [{"values_spoken": ["Anna"]}, {"values_spoken": []}]
        assert mfsc.count_off_sheet(PERSONA, bad) == 1

    def test_rendered_values_are_always_on_sheet(self):
        rng = random.Random(0)
        turns = []
        for fid in FIDS:
            for move in ("answer", "spell", "reject_and_correct"):
                r = sim_actor.render(move, fid, PERSONA, rng)
                turns.append({"values_spoken": r.values_spoken})
        assert mfsc.count_off_sheet(PERSONA, turns) == 0

    def test_ears_text_selection(self):
        gens = [{"transcript": " one ", "stt": {"text": "uno"}},
                {"transcript": "two", "stt": {"text": ""}}]
        assert mfsc.ears_text(gens, "transcript") == "one two"
        assert mfsc.ears_text(gens, "stt") == "uno"

    def test_tts_cost_per_kind(self):
        gt = mfsc.TTSMouth("gtts", lambda t: b"")
        ch = mfsc.TTSMouth("chirp3", lambda t: b"")
        for m in (gt, ch):
            m.synth("a" * 1000)
            m.synth("b" * 1000)
        assert gt.chars == ch.chars == 2000
        assert gt.cost_usd == 0.0
        assert ch.cost_usd == pytest.approx(0.06)

    def test_strip_wav_header(self):
        pcm = b"\x01\x00\x02\x00"
        wav = (b"RIFF" + b"\x00" * 4 + b"WAVEfmt " + b"\x00" * 20
               + b"data" + len(pcm).to_bytes(4, "little") + pcm)
        assert mfsc._strip_wav_header(wav) == pcm
        assert mfsc._strip_wav_header(pcm) == pcm


# ---------------------------------------------------------------------------
# run()-level: --user sim end to end on a fake session
# ---------------------------------------------------------------------------
class Hub:
    """Shared state between the fake adapter, service and TTS in a run()."""

    def __init__(self):
        self.last_text = ""
        self.adapters = []
        self.services = []
        self.audio_s = FLOW_AUDIO_S
        self.model = ModelScript()
        self.stt_calls = 0
        self.stt_project = None
        self.stt_fail_after_probe = False
        self.pending_during_tool = []
        self.withhold = set()      # response indices with no turn_complete
        self.n_responses = 0


class FakeAdapter:
    def __init__(self, *a, hub=None, **k):
        self.hub = hub
        hub.adapters.append(self)
        self._session_ready = True
        self._session_total_tokens = 0
        self._session_text_input_tokens = 0
        self._session_audio_input_tokens = 0
        self._session_text_output_tokens = 0
        self._session_audio_output_tokens = 0
        noop = lambda *a, **k: None  # noqa: E731
        self._log = SimpleNamespace(info=noop, warning=noop, error=noop,
                                    exception=noop, critical=noop,
                                    bind=lambda **kw: self._log)
        self._on_raw_usage = None
        self._on_tool_call = self._default_tool
        self.flush_reasons = []

    async def _default_tool(self, name, arguments):
        # what the turn gate would see while this tool callback is in flight
        rec = self.hub.services[0].client.gen_recorder
        self.hub.pending_during_tool.append(
            None if rec is None else rec.pending_tools)
        return {"status": "ok"}

    def set_session_context(self, **kw):
        pass

    def set_callbacks(self, *a, **k):
        pass

    def _dev_flush_audio_dump(self, reason):
        self.flush_reasons.append(reason)

    def is_session_active(self):
        return True

    async def finalize(self):
        pass

    def get_resumption_handle(self):
        return None


class FakeService:
    def __init__(self, live_ai=None, settings=None, text_ai=None,
                 text_ai_pro=None, hub=None):
        self.adapter = live_ai
        self.hub = hub
        self.client = None
        self._spoken_language = None
        self.chunks = 0
        hub.services.append(self)

    def build_form_context_message(self, *a, **k):
        return "SI"

    async def start_session(self, websocket=None, send_transcript=False, **k):
        self.client = websocket
        self.send_transcript = send_transcript

    async def send_initiating_message(self, lang, hint):
        asyncio.ensure_future(self._respond(self.hub.model.greeting()))

    async def send_activity_start(self):
        pass

    async def stream_audio(self, chunk):
        self.chunks += 1

    async def send_activity_end(self):
        out = self.hub.model.respond(self.hub.last_text)
        asyncio.ensure_future(self._respond(out))

    def handle_confirm_field_response(self, *a, **k):
        pass

    async def _respond(self, out):
        c, ad = self.client, self.adapter
        await asyncio.sleep(0.01)
        if out.get("fill") or out.get("confirm"):
            await ad._on_tool_call("update_form_fields", {})
        if out.get("fill"):
            fid, val = out["fill"]
            await c.send_json({"type": "form_updated", "data": {
                "form_state": {fid: {"value": val}}}})
        if out.get("confirm"):
            await c.send_json({"type": "confirm_field", "request_id": "r",
                               "field_id": out["confirm"]})
        say = out["say"]
        await c.send_json({"type": "transcript", "data": say[:5]})
        await c.send_json({"type": "transcript", "data": say[5:]})
        await c.send_bytes(b"\x00\x00" * int(24000 * self.hub.audio_s))
        ad._session_total_tokens += 100
        ad._session_text_input_tokens += 60
        ad._session_audio_input_tokens += 20
        ad._session_text_output_tokens += 10
        ad._session_audio_output_tokens += 10
        idx = self.hub.n_responses
        self.hub.n_responses += 1
        if idx not in self.hub.withhold:
            ad._dev_flush_audio_dump("turn_complete")


@pytest.fixture
def sim_env(tmp_path, monkeypatch):
    hub = Hub()
    schema_path = tmp_path / "w7_schema.json"
    schema_path.write_text(json.dumps(synthetic_schema()), encoding="utf-8")
    monkeypatch.setitem(mfsc.SCHEMAS, "w7",
                        {**mfsc.SCHEMAS["w7"], "path": schema_path})
    monkeypatch.setattr(mfsc, "LiveAIGemini",
                        lambda *a, **k: FakeAdapter(*a, hub=hub, **k))
    monkeypatch.setattr(mfsc, "FormFillingService",
                        lambda **k: FakeService(hub=hub, **k))
    monkeypatch.setattr(mfsc, "SIM_TIMING", FAST)

    async def fast_wait_turn(adapter, tracker_field="_session_total_tokens",
                             last=0, timeout=40.0):
        t0 = time.monotonic()
        while time.monotonic() - t0 < 5.0:
            cur = getattr(adapter, tracker_field, 0) or 0
            if cur > last:
                return cur
            await asyncio.sleep(0.005)
        return last
    monkeypatch.setattr(mfsc, "_wait_turn", fast_wait_turn)

    def synth(text, *a, **k):
        hub.last_text = text
        return b"\x00\x00" * 640
    monkeypatch.setattr(mfsc, "synth_cached", synth)
    monkeypatch.setattr(mfsc, "_make_tts",
                        lambda kind: mfsc.TTSMouth(kind, synth))

    def make_stt_fn(project=None):
        hub.stt_project = project

        def fn(pcm):
            hub.stt_calls += 1
            if hub.stt_fail_after_probe and hub.stt_calls > 1:
                return {"text": "", "confidence": 0.0, "n_results": 0,
                        "seconds": 1.0, "billed_seconds": 0,
                        "verdict": "STT_ERROR", "error": "403 quota project"}
            return fake_stt(pcm)
        return fn
    monkeypatch.setattr(mfsc, "_make_stt_fn", make_stt_fn)
    return SimpleNamespace(hub=hub, tmp=tmp_path, schema_path=schema_path,
                           monkeypatch=monkeypatch)


def parse(env, *extra, user="sim"):
    argv = ["--schema", "w7", "--arm", "dti", "--continuous",
            "--user", user, "--actor", "stub",
            "--out-dir", str(env.tmp / "out")] + list(extra)
    return mfsc.build_parser().parse_args(argv)


def run_args(args):
    return asyncio.run(mfsc.run(args))


def read_one(out, pattern):
    files = sorted(Path(out).glob(pattern))
    assert len(files) == 1, files
    return json.loads(files[0].read_text(encoding="utf-8")), files[0]


class TestRunLevelEndToEnd:
    def test_sim_run_fills_and_confirms_the_whole_fact_sheet(self, sim_env):
        rc = run_args(parse(sim_env))
        assert rc == 0
        out = sim_env.tmp / "out"
        summary, _ = read_one(out, "*.summary.json")
        sim = summary["sim_user"]
        n = len(FIDS)
        assert sim["persona_id"] == PERSONA.persona_id
        assert sim["filled_confirmed"] == n
        assert sim["fact_fields"] == n
        assert sim["correct_vs_factsheet"] == {
            "matched": n, "total": n, "accuracy": 1.0}
        assert sim["off_sheet_values"] == 0
        assert sim["gate_violations"] == 0
        assert sim["fallbacks"]["count"] == 0
        assert sim["stop_reason"] == "complete"
        assert sim["aborted"] is False
        assert sim["user_turns"] >= n
        assert sim["kit_sha256"] == hashlib.sha256(
            sim_env.schema_path.read_bytes()).hexdigest()
        # the existing scoring path is untouched and agrees
        assert summary["headline"]["fill_accuracy"]["matched"] == n

    def test_cost_split_sums_to_the_total(self, sim_env):
        run_args(parse(sim_env, "--tts", "chirp3"))
        summary, _ = read_one(sim_env.tmp / "out", "*.summary.json")
        cost = summary["sim_user"]["cost"]
        assert set(cost) == {"gemini_live_usd", "sidecar_text_usd",
                             "actor_usd", "tts_usd", "stt_usd", "total_usd"}
        assert cost["gemini_live_usd"] == summary["headline"]["voice_usd"] > 0
        assert cost["sidecar_text_usd"] == summary["headline"]["text_usd"]
        chars = summary["sim_user"]["tts"]["chars"]
        assert chars > 0
        assert cost["tts_usd"] == pytest.approx(chars / 1e6 * 30.0, abs=1e-6)
        # every generation with audio was sent to STT once: 15 s billed each
        div = summary["sim_user"]["divergence"]
        assert cost["stt_usd"] == div["stt_cost_usd"] > 0
        assert cost["total_usd"] == pytest.approx(
            cost["gemini_live_usd"] + cost["sidecar_text_usd"]
            + cost["actor_usd"] + cost["tts_usd"] + cost["stt_usd"], abs=1e-5)

    def test_gtts_costs_nothing(self, sim_env):
        run_args(parse(sim_env))
        summary, _ = read_one(sim_env.tmp / "out", "*.summary.json")
        assert summary["sim_user"]["cost"]["tts_usd"] == 0.0
        assert summary["sim_user"]["tts"]["kind"] == "gtts"

    def test_committed_record_has_persona_id_everywhere_and_no_pcm(self, sim_env):
        run_args(parse(sim_env))
        out = sim_env.tmp / "out"
        doc, path = read_one(out / "sim_user", "*.sim-user.json")
        assert path.name.endswith(".sim-user.json")
        assert not fnmatch.fnmatch(path.name, "*.debug.json")
        assert doc["persona_id"] == PERSONA.persona_id
        assert doc["summary"]["gate_violations"] == 0
        assert doc["run_meta"]["kit_sha256"] == doc["summary"]["kit_sha256"]
        assert doc["generations"] and doc["user_turns"]
        for rec in doc["generations"] + doc["user_turns"]:
            assert rec["persona_id"] == PERSONA.persona_id
        for g in doc["generations"]:
            assert "pcm" not in g
            assert g["score"]["verdict"]
            assert g["transcript"] == g["score"]["transcript"]
        for t in doc["user_turns"]:
            assert t["gate_open_at_start"] is True
        text = path.read_text(encoding="utf-8")
        assert '"pcm"' not in text
        assert not list(out.rglob("*.debug.json"))

    def test_withheld_completion_is_closed_by_silence_and_reported(self, sim_env):
        sim_env.hub.withhold = {5}
        sim_env.monkeypatch.setattr(mfsc, "SIM_TIMING", SILENCE)
        assert run_args(parse(sim_env)) == 0
        summary, _ = read_one(sim_env.tmp / "out", "*.summary.json")
        sim = summary["sim_user"]
        assert sim["silence_closes"] == 1
        assert sim["late_completions"] == 0
        assert sim["stop_reason"] == "complete"
        assert sim["filled_confirmed"] == len(FIDS)
        assert sim["stalls"] == 0
        doc, _ = read_one(sim_env.tmp / "out" / "sim_user", "*.sim-user.json")
        assert [g["reason"] for g in doc["generations"]].count("silence") == 1

    def test_user_turn_records_are_diagnosable(self, sim_env):
        run_args(parse(sim_env))
        doc, _ = read_one(sim_env.tmp / "out" / "sim_user", "*.sim-user.json")
        for t in doc["user_turns"]:
            assert t["response_stalled"] in (True, False)
            assert isinstance(t["gate_wait_s"], float)
        for g in doc["generations"]:
            assert "late_completion_reason" in g
        sim = doc["summary"]
        assert sim["silence_closes"] == 0 and sim["late_completions"] == 0
        assert sim["spellback_clips"] == 0

    def test_tool_callbacks_are_visible_to_the_gate(self, sim_env):
        run_args(parse(sim_env))
        # the real tool tap marks a callback in flight while it runs ...
        assert sim_env.hub.pending_during_tool
        assert set(sim_env.hub.pending_during_tool) == {1}
        # ... and records the call on the generation that made it
        doc, _ = read_one(sim_env.tmp / "out" / "sim_user", "*.sim-user.json")
        with_tools = [g for g in doc["generations"] if g["tool_calls"]]
        assert with_tools
        assert all(g["tool_calls"] == ["update_form_fields"]
                   for g in with_tools)

    def test_every_generation_gets_one_stt_call(self, sim_env):
        run_args(parse(sim_env))
        doc, _ = read_one(sim_env.tmp / "out" / "sim_user", "*.sim-user.json")
        # one pre-flight probe + one call per generation
        assert sim_env.hub.stt_calls == len(doc["generations"]) + 1

    def test_the_model_audio_boundaries_are_what_the_adapter_flushes(self, sim_env):
        run_args(parse(sim_env))
        doc, _ = read_one(sim_env.tmp / "out" / "sim_user", "*.sim-user.json")
        ad = sim_env.hub.adapters[0]
        assert len(doc["generations"]) == ad.flush_reasons.count("turn_complete")

    def test_fact_key_missing_from_the_kit_aborts_before_any_session(self, sim_env):
        # A fact key that is NOT in W7_EXPECTED, so the canon drift guard
        # cannot be what stops the run: only the fact-sheet check can.
        raw = json.loads(sim_actor.PERSONA_DIR.joinpath(
            "w7_ana_nospell.json").read_text(encoding="utf-8"))
        raw["facts"]["zz_not_in_the_kit"] = dict(raw["facts"][FIDS[0]])
        persona_path = sim_env.tmp / "persona_extra.json"
        persona_path.write_text(json.dumps(raw), encoding="utf-8")
        with pytest.raises(SystemExit) as ei:
            run_args(parse(sim_env, "--persona", str(persona_path),
                           "--max-user-turns", "2"))
        assert "zz_not_in_the_kit" in str(ei.value)
        assert sim_env.hub.adapters == []

    def test_sim_run_requests_the_model_output_transcript(self, sim_env):
        run_args(parse(sim_env, "--max-user-turns", "1"))
        assert sim_env.hub.services[0].send_transcript is True

    def test_degraded_actor_aborts_nonzero_and_says_so(self, sim_env, capsys):
        sim_env.monkeypatch.setattr(
            mfsc, "build_actor",
            lambda kind, persona: FlakyActor([True], error="401 bad key"))
        rc = run_args(parse(sim_env))
        assert rc == 3
        out = capsys.readouterr().out
        assert "[sim-abort]" in out and "401 bad key" in out
        summary, _ = read_one(sim_env.tmp / "out", "*.summary.json")
        sim = summary["sim_user"]
        assert sim["aborted"] is True
        assert sim["fallbacks"]["count"] == 5
        assert sim["fallbacks"]["errors"][0]["error"] == "401 bad key"
        assert sim["filled_confirmed"] < len(FIDS)

    def test_missing_haiku_key_fails_fast_without_a_session(self, sim_env, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        args = parse(sim_env)
        args.actor = "haiku"
        with pytest.raises(SystemExit) as ei:
            run_args(args)
        assert "ANTHROPIC_API_KEY" in str(ei.value)
        assert sim_env.hub.adapters == []


class TestRunLevelSttHealth:
    def test_stt_is_billed_to_the_resolved_quota_project(self, sim_env, monkeypatch):
        monkeypatch.delenv("GOOGLE_CLOUD_QUOTA_PROJECT", raising=False)
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "vertex-proj")
        run_args(parse(sim_env, "--max-user-turns", "1"))
        assert sim_env.hub.stt_project == "vertex-proj"

    def test_preflight_failure_aborts_before_any_session(self, sim_env):
        sim_env.monkeypatch.setattr(
            mfsc, "_make_stt_fn", lambda project=None: _err_stt)
        with pytest.raises(SystemExit) as ei:
            run_args(parse(sim_env))
        assert "pre-flight" in str(ei.value)
        assert "403 quota project required" in str(ei.value)
        assert sim_env.hub.adapters == []

    def test_healthy_run_reports_a_valid_divergence_log(self, sim_env):
        assert run_args(parse(sim_env)) == 0
        summary, _ = read_one(sim_env.tmp / "out", "*.summary.json")
        sim = summary["sim_user"]
        assert sim["divergence_valid"] is True
        assert sim["stt"]["stt_errors"] == 0 and sim["stt"]["stt_calls"] > 0
        assert sim["divergence"]["n_scored"] > 0

    def test_run_with_failing_stt_exits_nonzero_and_says_why(self, sim_env, capsys):
        sim_env.hub.stt_fail_after_probe = True
        rc = run_args(parse(sim_env))
        assert rc == 4
        assert "[sim-invalid]" in capsys.readouterr().out
        summary, _ = read_one(sim_env.tmp / "out", "*.summary.json")
        sim = summary["sim_user"]
        assert sim["divergence_valid"] is False
        assert sim["stt"]["first_error"] == "403 quota project"
        assert sim["divergence"]["n_scored"] == 0
        doc, _ = read_one(sim_env.tmp / "out" / "sim_user", "*.sim-user.json")
        assert all(g["stt_error"] == "403 quota project"
                   for g in doc["generations"])


class TestRunLevelExitCodes:
    def test_incomplete_run_exits_5_with_a_clear_line(self, sim_env, capsys):
        rc = run_args(parse(sim_env, "--max-user-turns", "2"))
        assert rc == 5
        out = capsys.readouterr().out
        assert "[sim-incomplete] stop_reason=max_user_turns" in out
        assert "filled_confirmed=" in out
        summary, _ = read_one(sim_env.tmp / "out", "*.summary.json")
        assert summary["sim_user"]["stop_reason"] == "max_user_turns"
        # artifacts are still written
        read_one(sim_env.tmp / "out" / "sim_user", "*.sim-user.json")

    def test_complete_run_exits_0(self, sim_env):
        assert run_args(parse(sim_env)) == 0

    def test_invalid_stt_outranks_incomplete(self, sim_env):
        sim_env.hub.stt_fail_after_probe = True
        assert run_args(parse(sim_env, "--max-user-turns", "2")) == 4

    def test_actor_abort_outranks_incomplete(self, sim_env):
        sim_env.monkeypatch.setattr(
            mfsc, "build_actor",
            lambda kind, persona: FlakyActor([True], error="401"))
        assert run_args(parse(sim_env)) == 3

    def test_exit_codes_are_documented(self):
        helptext = mfsc.build_parser().format_help()
        for code in ("3 actor", "4 Cloud STT", "5 incomplete"):
            assert code in " ".join(helptext.split())

    def test_gate_violations_in_the_summary_is_the_overlap_measure(self, sim_env):
        run_args(parse(sim_env, "--max-user-turns", "2"))
        doc, _ = read_one(sim_env.tmp / "out" / "sim_user", "*.sim-user.json")
        assert doc["summary"]["gate_violations"] == 0
        for t in doc["user_turns"]:
            assert "overlap_audio_s" in t and "overlapped" in t


class TestChirp3CacheIgnored:
    def test_chirp3_cache_is_ignored_and_the_gtts_cache_is_not(self):
        lines = [ln.strip() for ln in (_REPO_ROOT / ".gitignore").read_text(
            encoding="utf-8").splitlines()]
        assert "scripts/spikes/fixtures/audio_cache_chirp3/" in lines
        assert not any(ln.rstrip("/").endswith("fixtures/audio_cache")
                       for ln in lines)


class TestScriptedModeUnaffected:
    def test_scripted_run_writes_no_sim_artifacts(self, sim_env):
        args = parse(sim_env, "--questions", "2", user="script")
        assert run_args(args) == 0
        out = sim_env.tmp / "out"
        summary, _ = read_one(out, "*.summary.json")
        meta, _ = read_one(out, "*.meta.json")
        assert "sim_user" not in summary
        assert "sim_user" not in meta and "user" not in meta
        assert not (out / "sim_user").exists()
        assert summary["headline"]["fill_accuracy"]["total"] == 2
        assert sim_env.hub.adapters  # the fake session did run
        assert sim_env.hub.stt_calls == 0  # scripted mode never calls STT

    def test_gitignore_still_ignores_debug_artifacts(self):
        lines = (_REPO_ROOT / ".gitignore").read_text(encoding="utf-8").split()
        assert "*.debug.json" in lines
