"""Shared STT read-back scoring: model OUTPUT AUDIO vs its own transcript.

Lifted from scripts/spikes/stt_readback_diff2.py (bd 0rpu, the "v2" method) so
the simulated-user harness (epic polyglot-pdf-ya4vi, E.3) can score every
generation without re-implementing it. diff2 now imports from here; the logic
below is the diff2 logic, unchanged -- see
scripts/spikes/0rpu_desync_attribution_findings.md for what the verdicts mean.

NEVER add a prompt. v1 used a generative model as the STT with a priming
prompt and fabricated output on thin audio (retracted). Cloud STT v1 with
`model=default` and A-Z phrase hints (a decoding bias, not a prompt) is the
method. One independent request per generation.

PUBLIC API
  letter_runs(text) / letters(text)      spelled-letter runs (pseudo-word aware)
  words(text) / containment(a, t)        normalized words / audio-in-text share
  decide_verdict(...)                    the pure ALIGNED/PARTIAL/DESYNC rules
  classify_pair(...)                     guards 2-4 + decide_verdict
  make_speech_client()                   Cloud STT client (quota project bound)
  recognize(client, speech, bytes, rate) one request (diff2's _recognize)
  recognize_pcm(client, pcm, rate_hz)    raw PCM; TOO_SHORT never sent
  billed_seconds_for(n_bytes, rate_hz)   15 s round-up per request
  score_generation(transcript, stt, expected_spellings)
  summarize_run(records, worst_n)

Divergence metric: word-level `1 - difflib.SequenceMatcher(None, a, b).ratio()`
over the normalized (stop-word-stripped) word lists of the transcript (a) and
the STT text (b). Deterministic; 0.0 = identical, 1.0 = nothing in common.

PII: transcripts and STT text are PHI-adjacent. Callers must not commit them.

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

import itertools
import os
import re
from difflib import SequenceMatcher

# Verdicts that mean "this row cannot support a conclusion" -- kept OUT of any
# rate denominator, because counting them silently is how v1 produced phantom
# statistics. NO_AUDIO (no PCM was captured for the generation) is the one
# addition for the harness.
UNSCOREABLE = {
    "WAV_MISSING", "TOO_SHORT", "NO_SPEECH_DETECTED",
    "LOW_CONFIDENCE", "NO_TRANSCRIPT", "STT_ERROR", "TOO_SHORT_TO_JUDGE",
    "NO_AUDIO",
}

# Below this the clip cannot hold a spoken read-back; v1's artifacts were 0.11 s.
MIN_SECONDS = 0.60
# Cloud STT confidence below this is not trustworthy enough to call a mismatch.
MIN_CONFIDENCE = 0.60
# Containment thresholds used by decide_verdict.
ALIGNED_CONTAINMENT = 0.6
PARTIAL_CONTAINMENT = 0.35
# Clips shorter than this give containment too few words to be reliable.
JUDGEABLE_SECONDS = 2.0

# Cloud STT v1 standard model price and billing increment.
STT_USD_PER_MINUTE = 0.024
STT_BILLING_INCREMENT_S = 15

LETTER_HINTS = [chr(c) for c in range(ord("A"), ord("Z") + 1)]
LETTER_HINT_BOOST = 12.0

_ACRONYMS = {"ITIN", "SSN", "IRS", "USA", "ZIP", "VAD", "APO", "PO"}
_STOP = {"a", "an", "the", "is", "are", "and", "or", "of", "to", "your",
         "you", "please", "say", "if", "so", "that", "what", "how", "do",
         "okay", "on", "in", "it", "not", "from", "one", "just", "me",
         "let", "check"}


def letter_runs(text: str) -> list:
    """Spelled-letter runs as a list ('J-O-H-N' / 'J. O. H. N.' -> ['JOHN']).

    Minimum THREE letters, and known acronyms excluded: two-letter dotted
    abbreviations and acronyms are prose, not spell-outs.
    """
    # Cloud STT COLLAPSES a spelled run into a pseudo-word rather than emitting
    # isolated letters (phrase hints do not stop it): "J-O-H-N" comes back as
    # "J0hn", with a zero for the letter O. Recover the run in two steps --
    # normalize the zero, then treat a leading-capital pseudo-word that the
    # recognizer spelled (marked by that 0-for-O, or by mixed case mid-word) as
    # a spelled sequence. Without this the letter comparator silently drops the
    # single most diagnostic token in the corpus.
    text = text or ""
    for m in set(re.findall(r"\b[A-Za-z]*0[A-Za-z]+\b", text)):
        text = text.replace(m, "-".join(m.replace("0", "O").upper()))
    out = []
    for chunk in re.findall(r"\b(?:[A-Za-z][\s\.\-,]+){1,}[A-Za-z]\b", text):
        letters_ = re.findall(r"[A-Za-z]", chunk)
        seq = "".join(letters_).upper()
        if seq in _ACRONYMS:
            continue
        if len(letters_) >= 3:
            out.append(seq)
    return out


def letters(text: str) -> str:
    """All spelled-letter runs of `text` concatenated (diff2's `_letters`)."""
    return "".join(letter_runs(text))


def words(text: str) -> list:
    up = re.sub(r"[^a-z0-9 ]", " ", (text or "").lower())
    return [w for w in up.split() if w and w not in _STOP]


def containment(audio_text: str, track_text: str):
    """How much of the AUDIO's content appears in the transcript window."""
    aw, tw = words(audio_text), set(words(track_text))
    if not aw:
        return None
    return sum(1 for w in aw if w in tw) / len(aw)


def make_speech_client(project=None):
    """Cloud STT client with the quota project bound (lazy import).

    Local ADC has no quota project, and speech.googleapis.com requires one
    (403 otherwise). Bind it explicitly to the same project Vertex bills to.
    `project` (when given) wins over the environment.
    """
    from google.cloud import speech as speech_mod
    project = (project or os.environ.get("GOOGLE_CLOUD_QUOTA_PROJECT")
               or os.environ.get("GOOGLE_CLOUD_PROJECT"))
    if project:
        import google.auth
        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds = creds.with_quota_project(project)
        return speech_mod.SpeechClient(credentials=creds)
    return speech_mod.SpeechClient()


def recognize(client, speech, audio_bytes: bytes, rate: int) -> dict:
    """One independent Cloud STT request. No prompt, no context, no history.

    SPELLED LETTERS. Left to itself the recognizer REASSEMBLES a spelled run
    into a word -- "J-O-H-N" comes back as "J0hn" (with a zero for O). That is
    the recognizer being helpful in precisely the wrong way here: the letters
    ARE the measurement. Phrase hints bias it toward isolated letter tokens.
    Hints are a decoding bias, not a prompt: they cannot invent content that
    is not in the audio, so they do not reintroduce the v1 priming hazard.
    """
    letter_hints = speech.SpeechContext(
        phrases=list(LETTER_HINTS),
        boost=LETTER_HINT_BOOST,
    )
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=rate,
        language_code="en-US",
        enable_automatic_punctuation=True,
        # The model speaks digits and spelled letters; 'default' handles both
        # better than the phone models for studio-quality synthetic audio.
        model="default",
        speech_contexts=[letter_hints],
    )
    resp = client.recognize(config=config, audio=speech.RecognitionAudio(content=audio_bytes))
    parts, confs = [], []
    for result in resp.results:
        if not result.alternatives:
            continue
        alt = result.alternatives[0]
        parts.append(alt.transcript)
        confs.append(alt.confidence)
    return {
        "text": " ".join(p.strip() for p in parts).strip(),
        "confidence": round(min(confs), 3) if confs else 0.0,
        "n_results": len(parts),
    }


def billed_seconds_for(n_bytes: int, rate_hz: int) -> int:
    """Billed seconds of one request: duration rounded UP to 15 s increments.

    `n_bytes` is 16-bit mono PCM. Integer arithmetic (no float drift at exact
    multiples). Zero bytes bill zero; any audio bills at least one increment.
    """
    samples = n_bytes // 2
    if samples <= 0 or rate_hz <= 0:
        return 0
    per = rate_hz * STT_BILLING_INCREMENT_S
    return -(-samples // per) * STT_BILLING_INCREMENT_S


# Cloud STT sync recognize rejects audio over 1 minute (400 "Sync input too
# long"); longer clips are recognized in consecutive pieces of at most this.
MAX_SYNC_SECONDS = 55


def recognize_pcm(client, pcm: bytes, rate_hz: int = 24000, speech=None) -> dict:
    """STT of raw 16-bit mono PCM (no WAV header). Same shape as `recognize`.

    Adds `seconds` and `billed_seconds`. A clip under MIN_SECONDS is NOT sent
    (the client is never called): it returns verdict TOO_SHORT with
    billed_seconds 0. A request that raises returns verdict STT_ERROR (not
    billed: Cloud STT bills successful recognitions). `speech` is the
    google.cloud.speech module; imported lazily when omitted.
    """
    seconds = round((len(pcm) // 2) / float(rate_hz), 3) if rate_hz else 0.0
    if not pcm:
        return {"text": "", "confidence": 0.0, "n_results": 0,
                "seconds": 0.0, "billed_seconds": 0, "verdict": "NO_AUDIO"}
    if seconds < MIN_SECONDS:
        return {"text": "", "confidence": 0.0, "n_results": 0,
                "seconds": seconds, "billed_seconds": 0, "verdict": "TOO_SHORT"}
    if speech is None:
        from google.cloud import speech as speech_mod
        speech = speech_mod
    piece_bytes = 2 * rate_hz * MAX_SYNC_SECONDS
    if len(pcm) > piece_bytes:
        return _recognize_pieces(client, speech, pcm, rate_hz, seconds,
                                 piece_bytes)
    try:
        rec = recognize(client, speech, pcm, rate_hz)
    except Exception as exc:  # noqa: BLE001
        return {"text": "", "confidence": 0.0, "n_results": 0,
                "seconds": seconds, "billed_seconds": 0,
                "verdict": "STT_ERROR", "error": str(exc)[:200]}
    rec["seconds"] = seconds
    rec["billed_seconds"] = billed_seconds_for(len(pcm), rate_hz)
    return rec


def _recognize_pieces(client, speech, pcm: bytes, rate_hz: int,
                      seconds: float, piece_bytes: int) -> dict:
    """A clip over the sync limit: consecutive <= MAX_SYNC_SECONDS pieces,
    each recognized with the same config. Texts are joined in order with a
    space, confidence is the duration-weighted mean over pieces that
    returned a result, and billing is the sum of each piece's own 15 s
    rounding. A failing piece makes the whole clip STT_ERROR (pieces already
    recognized stay billed)."""
    texts, weights, confs = [], [], []
    n_results = billed = 0
    pieces = [pcm[i:i + piece_bytes] for i in range(0, len(pcm), piece_bytes)]
    # A tail under MIN_SECONDS is not worth its own request (the API would
    # get a clip too short to hold speech); fold it into the previous piece,
    # which stays well under the sync limit.
    min_bytes = int(MIN_SECONDS * rate_hz) * 2
    if len(pieces) > 1 and len(pieces[-1]) < min_bytes:
        tail = pieces.pop()
        pieces[-1] += tail
    for piece in pieces:
        try:
            rec = recognize(client, speech, piece, rate_hz)
        except Exception as exc:  # noqa: BLE001
            return {"text": "", "confidence": 0.0, "n_results": 0,
                    "seconds": seconds, "billed_seconds": billed,
                    "verdict": "STT_ERROR", "error": str(exc)[:200]}
        billed += billed_seconds_for(len(piece), rate_hz)
        if rec["text"]:
            texts.append(rec["text"])
        if rec["n_results"]:
            weights.append(len(piece) // 2)
            confs.append(rec["confidence"])
        n_results += rec["n_results"]
    conf = (sum(w * c for w, c in zip(weights, confs)) / sum(weights)
            if weights else 0.0)
    return {"text": " ".join(texts), "confidence": round(conf, 3),
            "n_results": n_results, "seconds": seconds,
            "billed_seconds": billed,
            "pieces": len(pieces)}


def decide_verdict(letters_stt: str, letters_txt: str, letters_near: str,
                   cont, seconds: float) -> str:
    """The diff2 verdict rules (pure). See stt_readback_diff2's comments.

    (a) CONTAINMENT VETO: containment >= 0.6 means the two tracks said the
        same sentence, so a one-sided letter run is window bleed.
    (b) ONE-SIDED SPELLING is evidence only when the AUDIO spelled something
        the text did not, or the two spellings CONFLICT.
    A spelled run the AUDIO produced is suspicious only when it appears
    NOWHERE in the adjacent text.
    """
    audio_spelling_supported = bool(letters_stt) and letters_stt in letters_near
    spelling_conflict = (bool(letters_stt) and bool(letters_txt)
                         and letters_stt != letters_txt
                         and not audio_spelling_supported)
    audio_only_spelling = (bool(letters_stt) and not letters_txt
                           and not audio_spelling_supported)
    if cont is None:
        return "NO_SPEECH_DETECTED"
    if spelling_conflict or audio_only_spelling:
        return "SPELLING_DESYNC"
    if letters_txt and not letters_stt:
        # Text spelled, audio did not: real only if the sentences also
        # diverge; otherwise it is window bleed.
        return ("SPELLING_DESYNC"
                if (cont < ALIGNED_CONTAINMENT and letters_txt not in letters_near)
                else "ALIGNED")
    if cont >= ALIGNED_CONTAINMENT:
        return "ALIGNED"
    if seconds < JUDGEABLE_SECONDS:
        # Short clips give the containment metric too few words to be
        # reliable (runA gen 19: 1.7 s, "born in" misheard as "boarding").
        return "TOO_SHORT_TO_JUDGE"
    if cont >= PARTIAL_CONTAINMENT:
        return "PARTIAL"
    return "UTTERANCE_DESYNC"


def classify_pair(stt_text: str, confidence: float, text_track: str,
                  text_neighbourhood: str, seconds: float):
    """Guards 2-4 then decide_verdict. Returns (verdict, extras).

    `extras` holds exactly the keys diff2 merged into a row at each stage, in
    the same order: needs_hand_check (after the confidence guard), then
    letters_stt / letters_transcript / letters_neighbourhood / containment.
    """
    extras: dict = {}
    # Guard 2: the recognizer heard nothing. A dedicated STT returns empty
    # rather than inventing -- exactly the property v1 lacked.
    if not stt_text:
        return "NO_SPEECH_DETECTED", extras
    # Guard 3: heard something, but not confidently enough to accuse --
    # UNLESS the clip contains a spelled run. Confidence is ALSO a corruption
    # signal (healthy rows 0.93-0.99, corrupted 0.34-0.65), so discarding
    # low-confidence spellings deletes precisely the failures this scorer
    # exists to find. Score those rows and flag them for a human read.
    low_conf = confidence < MIN_CONFIDENCE
    if low_conf and not letters(stt_text):
        return "LOW_CONFIDENCE", extras
    extras["needs_hand_check"] = bool(low_conf)
    # Guard 4: no transcript to compare against -> pairing cannot be judged.
    if not text_track:
        return "NO_TRANSCRIPT", extras
    letters_stt = letters(stt_text)
    letters_txt = letters(text_track)
    letters_near = letters(text_neighbourhood)
    cont = containment(stt_text, text_track)
    extras.update({
        "letters_stt": letters_stt,
        "letters_transcript": letters_txt,
        "letters_neighbourhood": letters_near,
        "containment": round(cont, 3) if cont is not None else None,
    })
    return decide_verdict(letters_stt, letters_txt, letters_near, cont, seconds), extras


def word_divergence(transcript: str, stt_text: str) -> float:
    """1 - SequenceMatcher ratio over normalized word lists, in [0, 1].

    Both empty -> 0.0 (nothing to disagree about); exactly one empty -> 1.0.
    """
    a, b = words(transcript), words(stt_text)
    if not a and not b:
        return 0.0
    if not a or not b:
        return 1.0
    return round(1.0 - SequenceMatcher(None, a, b).ratio(), 4)


def _letter_diffs(transcript: str, stt_text: str) -> list:
    t_runs, s_runs = letter_runs(transcript), letter_runs(stt_text)
    out = []
    for t, s in itertools.zip_longest(t_runs, s_runs, fillvalue=""):
        ops = SequenceMatcher(None, t, s).get_opcodes()
        out.append({
            "transcript_letters": t,
            "stt_letters": s,
            "match": t == s,
            "opcodes": [list(op) for op in ops],
        })
    return out


def _spelling_checks(expected_spellings, transcript: str, stt_text: str) -> list:
    """For each expected spelling: does each side contain it?

    Contained = the normalized letters appear inside a spelled-letter run of
    that side, or as a whole word of that side (so "ANA" is not found inside
    "banana").
    """
    t_runs, s_runs = letter_runs(transcript), letter_runs(stt_text)
    t_words = set(re.sub(r"[^a-z0-9 ]", " ", (transcript or "").lower()).split())
    s_words = set(re.sub(r"[^a-z0-9 ]", " ", (stt_text or "").lower()).split())
    out = []
    for exp in expected_spellings:
        norm = re.sub(r"[^A-Za-z]", "", exp or "").upper()
        in_t = bool(norm) and (any(norm in r for r in t_runs)
                               or norm.lower() in t_words)
        in_s = bool(norm) and (any(norm in r for r in s_runs)
                               or norm.lower() in s_words)
        out.append({"expected": exp, "in_transcript": in_t, "in_stt": in_s})
    return out


def score_generation(transcript: str, stt, expected_spellings=None) -> dict:
    """Score one generation: transcript vs the STT of its emitted audio.

    `stt` is a `recognize_pcm` dict (keys text / confidence / seconds /
    billed_seconds, optionally verdict / error), or None when no audio was
    captured (-> NO_AUDIO). Verdict vocabulary and semantics are diff2's
    (ALIGNED / PARTIAL / SPELLING_DESYNC / UTTERANCE_DESYNC; unscoreable:
    TOO_SHORT, LOW_CONFIDENCE, NO_TRANSCRIPT, NO_AUDIO, NO_SPEECH_DETECTED,
    STT_ERROR, TOO_SHORT_TO_JUDGE). `divergence` is word_divergence() for
    scoreable verdicts and None otherwise. The transcript is both the window
    and the neighbourhood here: the harness pairs one generation's transcript
    with its own audio, so there is no neighbouring generation to widen to.
    """
    transcript = transcript or ""
    stt = stt or None
    rec = {
        "transcript": transcript,
        "stt_text": (stt or {}).get("text", ""),
        "stt_confidence": (stt or {}).get("confidence"),
        "billed_seconds": (stt or {}).get("billed_seconds", 0),
        "seconds": (stt or {}).get("seconds"),
        "divergence": None,
        "needs_hand_check": False,
        "letter_diffs": [],
        "expected_spellings": [],
    }
    if stt is None:
        rec["verdict"] = "NO_AUDIO"
        return rec
    pre = stt.get("verdict")
    if pre in UNSCOREABLE:
        rec["verdict"] = pre
        return rec
    if stt.get("error"):
        rec["verdict"] = "STT_ERROR"
        return rec
    seconds = stt.get("seconds")
    verdict, extras = classify_pair(
        stt.get("text", ""), float(stt.get("confidence") or 0.0),
        transcript, transcript,
        float(seconds) if seconds is not None else JUDGEABLE_SECONDS)
    rec["verdict"] = verdict
    rec["needs_hand_check"] = bool(extras.get("needs_hand_check", False))
    for key in ("letters_stt", "letters_transcript", "containment"):
        if key in extras:
            rec[key] = extras[key]
    if verdict not in UNSCOREABLE:
        rec["divergence"] = word_divergence(transcript, rec["stt_text"])
    rec["letter_diffs"] = _letter_diffs(transcript, rec["stt_text"])
    if expected_spellings:
        rec["expected_spellings"] = _spelling_checks(
            expected_spellings, transcript, rec["stt_text"])
    return rec


def summarize_run(records: list, worst_n: int = 5) -> dict:
    """Run-level summary over `score_generation` records.

    n_scored    records whose verdict is not in UNSCOREABLE.
    n_divergent scored records whose verdict is anything other than ALIGNED
                (PARTIAL counts: it is a measured disagreement, not a pass).
    divergence_rate n_divergent / n_scored, None when nothing was scored.
    worst       top `worst_n` scored records by divergence (ties keep input
                order), each with transcript and stt_text.
    stt_billed_seconds sums every record's billed_seconds (unscoreable rows
                that were still sent, e.g. LOW_CONFIDENCE, are billed).
    stt_cost_usd = billed seconds / 60 * $0.024.
    """
    scored = [r for r in records if r.get("verdict") not in UNSCOREABLE]
    divergent = [r for r in scored if r.get("verdict") != "ALIGNED"]
    verdict_counts: dict = {}
    for r in records:
        v = r.get("verdict")
        verdict_counts[v] = verdict_counts.get(v, 0) + 1
    ranked = sorted(
        (r for r in scored if r.get("divergence") is not None),
        key=lambda r: -r["divergence"])  # sorted() is stable
    worst = [{
        "verdict": r.get("verdict"),
        "divergence": r.get("divergence"),
        "transcript": r.get("transcript", ""),
        "stt_text": r.get("stt_text", ""),
    } for r in ranked[:max(worst_n, 0)]]
    billed = sum(int(r.get("billed_seconds") or 0) for r in records)
    return {
        "n_generations": len(records),
        "n_scored": len(scored),
        "n_divergent": len(divergent),
        "divergence_rate": (round(len(divergent) / len(scored), 4)
                            if scored else None),
        "verdict_counts": dict(sorted(verdict_counts.items(),
                                      key=lambda kv: str(kv[0]))),
        "worst": worst,
        "stt_billed_seconds": billed,
        "stt_cost_usd": round(billed / 60.0 * STT_USD_PER_MINUTE, 6),
    }
