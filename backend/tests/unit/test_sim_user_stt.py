"""
Unit tests for scripts/spikes/sim_user_stt.py (bd polyglot-pdf-wqnxr, E.2):
the shared STT divergence scorer lifted out of stt_readback_diff2.py.

Hermetic: synthetic inputs only, a FAKE Cloud STT client, no network and no
live call. Names no kit field id (CLAUDE.md scar #10). ASCII only.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPIKES_DIR = str(_REPO_ROOT / "scripts" / "spikes")
if _SPIKES_DIR not in sys.path:
    sys.path.insert(0, _SPIKES_DIR)

import sim_user_stt as stt  # noqa: E402
import stt_readback_diff2 as diff2  # noqa: E402

RATE = 24000


def _pcm(seconds: float, rate: int = RATE) -> bytes:
    return b"\x00\x00" * int(round(seconds * rate))


def _stt(text, conf=0.95, seconds=3.0, billed=15, **kw):
    return {"text": text, "confidence": conf, "seconds": seconds,
            "billed_seconds": billed, "n_results": 1, **kw}


class _FakeSpeech:
    """Just enough of google.cloud.speech for recognize()."""
    class AudioEncoding:
        LINEAR16 = "LINEAR16"

    class RecognitionConfig:
        AudioEncoding = None

        def __init__(self, **kw):
            self.kw = kw

    class SpeechContext:
        def __init__(self, **kw):
            self.kw = kw

    class RecognitionAudio:
        def __init__(self, content):
            self.content = content


_FakeSpeech.RecognitionConfig.AudioEncoding = _FakeSpeech.AudioEncoding


class _FakeClient:
    def __init__(self, text="hello there", conf=0.9, raises=None):
        self.calls = []
        self._text, self._conf, self._raises = text, conf, raises

    def recognize(self, config, audio):
        self.calls.append((config, audio))
        if self._raises:
            raise self._raises
        alt = SimpleNamespace(transcript=self._text, confidence=self._conf)
        return SimpleNamespace(results=[SimpleNamespace(alternatives=[alt])])


# --------------------------------------------------------------------------
# verdicts
# --------------------------------------------------------------------------
class TestVerdicts:
    def test_aligned(self):
        r = stt.score_generation(
            "What is your date of birth please",
            _stt("What is your date of birth"))
        assert r["verdict"] == "ALIGNED"
        assert r["divergence"] is not None and r["divergence"] < 0.2
        assert r["letter_diffs"] == []

    def test_spelling_desync(self):
        r = stt.score_generation(
            "Got it, that is A N A.", _stt("Got it that is A N N A"))
        assert r["verdict"] == "SPELLING_DESYNC"
        assert len(r["letter_diffs"]) == 1
        d = r["letter_diffs"][0]
        assert d["transcript_letters"] == "ANA"
        assert d["stt_letters"] == "ANNA"
        assert d["match"] is False
        assert any(op[0] == "insert" for op in d["opcodes"])

    def test_spelling_match_is_aligned(self):
        r = stt.score_generation("Spell it A N A", _stt("Spell it A N A"))
        assert r["verdict"] == "ALIGNED"
        assert r["letter_diffs"][0]["match"] is True

    def test_utterance_desync(self):
        r = stt.score_generation(
            "Please tell me your mailing address street",
            _stt("Banana pancakes taste wonderful yesterday", seconds=3.5))
        assert r["verdict"] == "UTTERANCE_DESYNC"
        assert r["divergence"] > 0.8

    def test_partial(self):
        # 2 of 5 audio words appear in the transcript -> containment 0.4.
        r = stt.score_generation(
            "alpha bravo charlie delta echo",
            _stt("alpha bravo xray yankee zulu", seconds=4.0))
        assert r["verdict"] == "PARTIAL"

    def test_low_containment_just_under_partial_is_utterance_desync(self):
        # 1 of 5 audio words in the transcript -> containment 0.2 (< 0.35).
        r = stt.score_generation(
            "alpha bravo charlie delta echo",
            _stt("alpha xray yankee zulu whiskey", seconds=4.0))
        assert r["verdict"] == "UTTERANCE_DESYNC"

    def test_short_clip_too_short_to_judge(self):
        r = stt.score_generation(
            "alpha bravo charlie", _stt("xray yankee zulu", seconds=1.5))
        assert r["verdict"] == "TOO_SHORT_TO_JUDGE"
        assert r["divergence"] is None

    def test_low_confidence_without_spelling_is_unscoreable(self):
        r = stt.score_generation("alpha bravo", _stt("alpha bravo", conf=0.4))
        assert r["verdict"] == "LOW_CONFIDENCE"
        assert r["divergence"] is None

    def test_low_confidence_with_spelling_is_scored_and_flagged(self):
        r = stt.score_generation("it is A N A", _stt("it is A N N A", conf=0.4))
        assert r["verdict"] == "SPELLING_DESYNC"
        assert r["needs_hand_check"] is True

    def test_no_transcript(self):
        r = stt.score_generation("", _stt("hello world"))
        assert r["verdict"] == "NO_TRANSCRIPT"

    def test_no_audio(self):
        assert stt.score_generation("hello", None)["verdict"] == "NO_AUDIO"

    def test_empty_stt_text_is_no_speech(self):
        assert stt.score_generation("hello", _stt(""))["verdict"] == "NO_SPEECH_DETECTED"

    def test_too_short_and_error_pass_through(self):
        r = stt.score_generation("hello", {"text": "", "verdict": "TOO_SHORT",
                                           "billed_seconds": 0})
        assert r["verdict"] == "TOO_SHORT"
        r = stt.score_generation("hello", {"text": "", "verdict": "STT_ERROR",
                                           "error": "x"})
        assert r["verdict"] == "STT_ERROR"

    def test_stt_fields_recorded(self):
        r = stt.score_generation("hi there", _stt("hi there", conf=0.91, billed=30))
        assert (r["stt_text"], r["stt_confidence"], r["billed_seconds"]) == (
            "hi there", 0.91, 30)

    def test_divergence_is_deterministic_and_bounded(self):
        a = stt.word_divergence("alpha bravo charlie", "alpha bravo delta")
        assert a == stt.word_divergence("alpha bravo charlie", "alpha bravo delta")
        assert 0.0 < a < 1.0
        assert stt.word_divergence("alpha", "alpha") == 0.0
        assert stt.word_divergence("alpha", "zulu") == 1.0
        assert stt.word_divergence("", "") == 0.0
        assert stt.word_divergence("alpha", "") == 1.0


# --------------------------------------------------------------------------
# letters / expected spellings
# --------------------------------------------------------------------------
class TestLetters:
    def test_pseudo_word_recovery(self):
        # Cloud STT returns "J-O-H-N" as "J0hn" (zero for O).
        assert stt.letters("the name is J0hn") == "JOHN"
        assert stt.letter_runs("J0hn and A N A") == ["JOHN", "ANA"]

    def test_runs_and_acronyms(self):
        assert stt.letters("J. O. H. N.") == "JOHN"
        assert stt.letters("my S S N is here") == ""  # acronym excluded
        assert stt.letters("A B") == ""  # under three letters is prose

    def test_pseudo_word_diff_in_score(self):
        r = stt.score_generation("spelled J-O-H-N", _stt("spelled J0hn"))
        assert r["letter_diffs"][0]["stt_letters"] == "JOHN"
        assert r["letter_diffs"][0]["match"] is True

    def test_expected_spellings(self):
        r = stt.score_generation(
            "the name is A N A okay", _stt("the name is A N N A okay"),
            expected_spellings=["A-N-A", "Anna", "Zed"])
        by = {e["expected"]: e for e in r["expected_spellings"]}
        assert by["A-N-A"] == {"expected": "A-N-A", "in_transcript": True,
                               "in_stt": False}
        assert by["Anna"]["in_stt"] is True and by["Anna"]["in_transcript"] is False
        assert by["Zed"]["in_transcript"] is False and by["Zed"]["in_stt"] is False

    def test_expected_spelling_not_found_inside_other_word(self):
        r = stt.score_generation("I like banana bread", _stt("I like banana bread"),
                                 expected_spellings=["ANA"])
        assert r["expected_spellings"][0]["in_transcript"] is False

    def test_no_expected_means_empty_list(self):
        assert stt.score_generation("a b c d", _stt("a b c d"))["expected_spellings"] == []


# --------------------------------------------------------------------------
# long clips: sync STT only takes ~1 minute
# --------------------------------------------------------------------------
class _PieceClient:
    """Fake client: answers each request with the next canned reply and
    records the audio length it was given."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.sizes = []
        self.calls = 0

    def recognize(self, config, audio):
        self.sizes.append(len(audio.content))
        i = self.calls
        self.calls += 1
        r = self.replies[i]
        if isinstance(r, Exception):
            raise r
        text, conf = r
        alt = SimpleNamespace(transcript=text, confidence=conf)
        return SimpleNamespace(results=[SimpleNamespace(alternatives=[alt])])


class TestLongClipPieces:
    LIMIT = stt.MAX_SYNC_SECONDS

    def test_short_clip_is_one_request(self):
        c = _PieceClient([("hello", 0.9)])
        out = stt.recognize_pcm(c, _pcm(self.LIMIT), RATE, speech=_FakeSpeech)
        assert c.calls == 1
        assert "pieces" not in out
        assert out["text"] == "hello"

    def test_long_clip_is_split_in_order_and_joined(self):
        secs = 2 * self.LIMIT + 10                      # 120 s -> 3 pieces
        c = _PieceClient([("first part", 0.9), ("second part", 0.6),
                          ("third part", 0.9)])
        out = stt.recognize_pcm(c, _pcm(secs), RATE, speech=_FakeSpeech)
        assert c.calls == 3
        assert c.sizes == [2 * RATE * self.LIMIT] * 2 + [2 * RATE * 10]
        assert sum(c.sizes) == len(_pcm(secs))
        assert out["text"] == "first part second part third part"
        assert out["pieces"] == 3
        assert out["n_results"] == 3
        assert out["seconds"] == pytest.approx(secs)
        assert "verdict" not in out

    def test_billing_is_the_sum_of_each_pieces_own_rounding(self):
        secs = self.LIMIT + 1                           # 55 s + 1 s
        c = _PieceClient([("a", 0.9), ("b", 0.9)])
        out = stt.recognize_pcm(c, _pcm(secs), RATE, speech=_FakeSpeech)
        assert out["billed_seconds"] == 60 + 15         # not 60 for 56 s
        assert out["billed_seconds"] == (
            stt.billed_seconds_for(2 * RATE * self.LIMIT, RATE)
            + stt.billed_seconds_for(2 * RATE * 1, RATE))

    def test_confidence_is_the_duration_weighted_mean(self):
        secs = self.LIMIT + self.LIMIT // 5             # 55 s + 11 s
        c = _PieceClient([("a", 0.9), ("b", 0.4)])
        out = stt.recognize_pcm(c, _pcm(secs), RATE, speech=_FakeSpeech)
        want = (0.9 * self.LIMIT + 0.4 * (self.LIMIT // 5)) / secs
        assert out["confidence"] == pytest.approx(want, abs=1e-3)

    def test_a_failing_piece_is_an_stt_error_and_keeps_earlier_billing(self):
        c = _PieceClient([("a", 0.9), RuntimeError("quota")])
        out = stt.recognize_pcm(c, _pcm(self.LIMIT + 5), RATE,
                                speech=_FakeSpeech)
        assert out["verdict"] == "STT_ERROR"
        assert "quota" in out["error"]
        assert out["billed_seconds"] == 60

    def test_piece_boundaries_fall_on_whole_samples(self):
        c = _PieceClient([("a", 0.9), ("b", 0.9)])
        stt.recognize_pcm(c, _pcm(self.LIMIT + 2), RATE, speech=_FakeSpeech)
        assert all(n % 2 == 0 for n in c.sizes)


# --------------------------------------------------------------------------
# recognize_pcm / billing
# --------------------------------------------------------------------------
class TestRecognizePcm:
    def test_short_clip_never_calls_client(self):
        client = _FakeClient()
        out = stt.recognize_pcm(client, _pcm(0.3), RATE, speech=_FakeSpeech)
        assert client.calls == []
        assert out["verdict"] == "TOO_SHORT"
        assert out["billed_seconds"] == 0
        assert out["text"] == ""
        assert stt.score_generation("hello", out)["verdict"] == "TOO_SHORT"

    def test_empty_pcm_is_no_audio(self):
        client = _FakeClient()
        out = stt.recognize_pcm(client, b"", RATE, speech=_FakeSpeech)
        assert client.calls == [] and out["verdict"] == "NO_AUDIO"

    def test_long_clip_is_sent_without_a_prompt(self):
        client = _FakeClient(text="hello there", conf=0.9)
        out = stt.recognize_pcm(client, _pcm(1.0), RATE, speech=_FakeSpeech)
        assert len(client.calls) == 1
        config, audio = client.calls[0]
        assert set(config.kw) == {
            "encoding", "sample_rate_hertz", "language_code",
            "enable_automatic_punctuation", "model", "speech_contexts"}
        assert config.kw["model"] == "default"
        assert config.kw["sample_rate_hertz"] == RATE
        ctx = config.kw["speech_contexts"][0].kw
        assert ctx["boost"] == 12.0 and len(ctx["phrases"]) == 26
        assert out["text"] == "hello there" and out["confidence"] == 0.9
        assert out["seconds"] == 1.0 and out["billed_seconds"] == 15

    def test_client_error_becomes_stt_error_unbilled(self):
        client = _FakeClient(raises=RuntimeError("boom"))
        out = stt.recognize_pcm(client, _pcm(1.0), RATE, speech=_FakeSpeech)
        assert out["verdict"] == "STT_ERROR" and out["billed_seconds"] == 0

    @pytest.mark.parametrize("seconds,expected", [
        (1, 15), (15, 15), (16, 30), (30, 30), (30.5, 45), (0.7, 15)])
    def test_billed_seconds_rounds_up_to_15(self, seconds, expected):
        pcm = _pcm(seconds)
        assert stt.billed_seconds_for(len(pcm), RATE) == expected
        client = _FakeClient()
        out = stt.recognize_pcm(client, pcm, RATE, speech=_FakeSpeech)
        assert out["billed_seconds"] == expected

    def test_billed_seconds_zero_for_nothing(self):
        assert stt.billed_seconds_for(0, RATE) == 0


# --------------------------------------------------------------------------
# summarize_run
# --------------------------------------------------------------------------
class TestSummarizeRun:
    def _records(self):
        return [
            stt.score_generation("what is your date of birth", _stt("what is your date of birth", billed=15)),
            stt.score_generation("it is A N A", _stt("it is A N N A", billed=15)),
            stt.score_generation("tell me your mailing address street",
                                 _stt("banana pancakes taste wonderful yesterday", billed=30)),
            stt.score_generation("hello", {"text": "", "verdict": "TOO_SHORT",
                                           "billed_seconds": 0}),
            stt.score_generation("hello", None),
        ]

    def test_counts_rate_and_verdicts(self):
        s = stt.summarize_run(self._records())
        assert s["n_generations"] == 5
        assert s["n_scored"] == 3
        assert s["n_divergent"] == 2
        assert s["divergence_rate"] == round(2 / 3, 4)
        assert s["verdict_counts"] == {
            "ALIGNED": 1, "NO_AUDIO": 1, "SPELLING_DESYNC": 1,
            "TOO_SHORT": 1, "UTTERANCE_DESYNC": 1}

    def test_partial_counts_as_divergent(self):
        partial = stt.score_generation(
            "alpha bravo charlie delta echo",
            _stt("alpha bravo xray yankee zulu", seconds=4.0))
        assert partial["verdict"] == "PARTIAL"
        s = stt.summarize_run([partial])
        assert (s["n_scored"], s["n_divergent"], s["divergence_rate"]) == (1, 1, 1.0)

    def test_worst_ordering_and_limit(self):
        s = stt.summarize_run(self._records(), worst_n=2)
        assert [w["verdict"] for w in s["worst"]] == [
            "UTTERANCE_DESYNC", "SPELLING_DESYNC"]
        assert s["worst"][0]["divergence"] >= s["worst"][1]["divergence"]
        assert s["worst"][0]["transcript"].startswith("tell me")
        assert s["worst"][0]["stt_text"].startswith("banana")
        assert len(stt.summarize_run(self._records(), worst_n=1)["worst"]) == 1

    def test_cost(self):
        s = stt.summarize_run(self._records())
        assert s["stt_billed_seconds"] == 60
        assert s["stt_cost_usd"] == pytest.approx(0.024)

    def test_nothing_scored(self):
        s = stt.summarize_run([stt.score_generation("x", None)])
        assert s["n_scored"] == 0 and s["divergence_rate"] is None
        assert s["worst"] == [] and s["stt_cost_usd"] == 0.0


# --------------------------------------------------------------------------
# diff2 equivalence
# --------------------------------------------------------------------------
_CORPUS = [
    "", "J-O-H-N", "J. O. H. N.", "the name is J0hn", "A N A", "A N N A",
    "my S S N is 1 2 3", "A B", "Is this a first time application?",
    "Z-I-P code", "spell M0ses please", "I.R.S. and U S A", "a, b, c, d",
]


class TestDiff2Equivalence:
    def test_diff2_names_are_the_shared_implementations(self):
        assert diff2._letters is stt.letters
        assert diff2._words is stt.words
        assert diff2._containment is stt.containment
        assert diff2._recognize is stt.recognize
        assert diff2._UNSCOREABLE is stt.UNSCOREABLE
        assert diff2._MIN_SECONDS == stt.MIN_SECONDS == 0.60
        assert diff2._MIN_CONFIDENCE == stt.MIN_CONFIDENCE == 0.60

    @pytest.mark.parametrize("text", _CORPUS)
    def test_letters_equal_joined_runs(self, text):
        assert diff2._letters(text) == "".join(stt.letter_runs(text))

    def test_frozen_findings_rows_reproduce(self):
        path = (_REPO_ROOT / "scripts" / "spikes" / "data" / "0rpu_desync_audio"
                / "night_runA__stt_report_v2.json")
        if not path.exists():
            pytest.skip("findings data not present")
        rows = json.loads(path.read_text(encoding="utf-8"))["results"]
        checked = 0
        for r in rows:
            if "letters_stt" not in r:
                continue
            tt = r["transcript_text"]
            assert stt.letters(r["stt_text"]) == r["letters_stt"]
            assert stt.letters(tt) == r["letters_transcript"]
            cont = stt.containment(r["stt_text"], tt)
            assert round(cont, 3) == r["containment"]
            verdict, _ = stt.classify_pair(
                r["stt_text"], r["confidence"], tt, tt, r["seconds"])
            assert verdict == r["verdict"], r["gen"]
            checked += 1
        assert checked >= 10
