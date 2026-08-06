"""STT-score the model's OUTPUT AUDIO against its own text transcript -- v2.

WHY v2 (bd 0rpu, 2026-08-06). v1 used Gemini-as-STT with a prompt that said
"a form assistant speaking English" and gave "example: J-O-H-N". On a 0.11 s
scrap of audio that prompt PRIMED a plausible completion, and the model
returned "Okay, so the first name is J-A-M-E-S." -- a fully-formed sentence
that cannot fit in 0.11 s. Two published findings rested on that artifact and
were retracted. A generative model asked to transcribe will INVENT when the
audio is thin; a dedicated recognizer returns empty or low-confidence instead.

v2 therefore:
  - uses Cloud Speech-to-Text (google-cloud-speech), not a generative model:
    no prompt, so nothing to prime, and no completion behaviour;
  - carries METADATA on every row (duration, bytes, confidence, flush reason)
    so an artifact is visible in the row itself rather than inferred later;
  - rejects rows that cannot support a verdict (sub-second audio, empty or
    low-confidence recognition) with an explicit verdict rather than scoring
    them;
  - reports the transcript-pairing basis per row (seq window + whether the
    window was empty) so pairing bugs are auditable instead of silent.

Each recognize() call is independent: one request per generation, no session,
no shared context, no history.

BILLING: Cloud STT standard model, ~$0.024/minute (v1 API, <=60 min/month free
tier). A 30-generation run is ~90 s of audio => well under a cent. ADC, same
credentials as Vertex.
PII: WAVs and transcripts are PHI -- the report lands beside the gitignored
audio dir. Never commit it.

Usage (from repo root, backend venv):
  backend/.venv/Scripts/python.exe scripts/spikes/stt_readback_diff2.py \
      --audio-dir backend/logs/audio_out/gemini_2026-08-06 \
      --jsonl backend/logs/gemini_2026-08-06.jsonl [--yes]

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import wave
from pathlib import Path

# Verdicts that mean "this row cannot support a conclusion" -- kept OUT of any
# rate denominator, because counting them silently is how v1 produced phantom
# statistics.
_UNSCOREABLE = {
    "WAV_MISSING", "TOO_SHORT", "NO_SPEECH_DETECTED",
    "LOW_CONFIDENCE", "NO_TRANSCRIPT", "STT_ERROR", "TOO_SHORT_TO_JUDGE",
}

# Below this the clip cannot hold a spoken read-back; v1's artifacts were 0.11 s.
_MIN_SECONDS = 0.60
# Cloud STT confidence below this is not trustworthy enough to call a mismatch.
_MIN_CONFIDENCE = 0.60


def _wav_meta(path: Path) -> dict:
    """Duration/rate/bytes -- the metadata that makes an artifact self-evident."""
    try:
        with wave.open(str(path), "rb") as w:
            rate = w.getframerate() or 24000
            frames = w.getnframes()
            return {
                "seconds": round(frames / float(rate), 3),
                "sample_rate": rate,
                "channels": w.getnchannels(),
                "bytes": path.stat().st_size,
            }
    except Exception:
        return {"seconds": 0.0, "sample_rate": 0, "channels": 0,
                "bytes": path.stat().st_size if path.exists() else 0}


def _load_jsonl(path: Path) -> list:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def _letters(text: str) -> str:
    """Extract spelled-letter runs ('J-O-H-N' / 'J. O. H. N.' -> 'JOHN').

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
    for m in set(re.findall(r"\b[A-Za-z]*0[A-Za-z]+\b", text)):
        text = text.replace(m, "-".join(m.replace("0", "O").upper()))
    out = []
    for chunk in re.findall(r"\b(?:[A-Za-z][\s\.\-,]+){1,}[A-Za-z]\b", text):
        letters = re.findall(r"[A-Za-z]", chunk)
        seq = "".join(letters).upper()
        if seq in {"ITIN", "SSN", "IRS", "USA", "ZIP", "VAD", "APO", "PO"}:
            continue
        if len(letters) >= 3:
            out.append(seq)
    return "".join(out)


def _words(text: str) -> list:
    stop = {"a", "an", "the", "is", "are", "and", "or", "of", "to", "your",
            "you", "please", "say", "if", "so", "that", "what", "how", "do",
            "okay", "on", "in", "it", "not", "from", "one", "just", "me",
            "let", "check"}
    up = re.sub(r"[^a-z0-9 ]", " ", (text or "").lower())
    return [w for w in up.split() if w and w not in stop]


def _containment(audio_text: str, track_text: str):
    """How much of the AUDIO's content appears in the transcript window."""
    aw, tw = _words(audio_text), set(_words(track_text))
    if not aw:
        return None
    return sum(1 for w in aw if w in tw) / len(aw)


def _recognize(client, speech, audio_bytes: bytes, rate: int) -> dict:
    """One independent Cloud STT request. No prompt, no context, no history.

    SPELLED LETTERS. Left to itself the recognizer REASSEMBLES a spelled run
    into a word -- "J-O-H-N" comes back as "J0hn" (with a zero for O). That is
    the recognizer being helpful in precisely the wrong way here: the letters
    ARE the measurement. Phrase hints bias it toward isolated letter tokens.
    Hints are a decoding bias, not a prompt: they cannot invent content that
    is not in the audio, so they do not reintroduce the v1 priming hazard.
    """
    letter_hints = speech.SpeechContext(
        phrases=[chr(c) for c in range(ord("A"), ord("Z") + 1)],
        boost=12.0,
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--audio-dir", required=True)
    ap.add_argument("--jsonl", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--seq-tail", type=int, default=40)
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    audio_dir = Path(args.audio_dir)
    rows = _load_jsonl(Path(args.jsonl))

    dumps = [r["content"] for r in rows
             if r.get("message_type") == "audio_dump" and isinstance(r.get("content"), dict)]
    transcripts = [(r["content"].get("seq", 0), r["content"].get("spoken_by_model") or "")
                   for r in rows
                   if r.get("message_type") == "transcript"
                   and isinstance(r.get("content"), dict)
                   and (r["content"].get("spoken_by_model") or "")]
    if not dumps:
        print("No audio_dump records -- was LIVE_DEV_AUDIO_DUMP on?")
        return 2

    total_sec = sum(_wav_meta(audio_dir / Path(d["file"]).name)["seconds"] for d in dumps)
    # Cloud STT bills per 15 s increment, ~$0.024/min.
    est_usd = (total_sec / 60.0) * 0.024
    print(f"generations: {len(dumps)}  audio: {total_sec:.1f}s  "
          f"est Cloud STT cost: ${est_usd:.4f}")
    if not args.yes:
        if input("proceed? [y/N] ").strip().lower() != "y":
            print("aborted")
            return 1

    from google.cloud import speech as speech_mod
    # Local ADC has no quota project, and speech.googleapis.com requires one
    # (403 otherwise). Bind it explicitly to the same project Vertex bills to.
    project = (os.environ.get("GOOGLE_CLOUD_QUOTA_PROJECT")
               or os.environ.get("GOOGLE_CLOUD_PROJECT"))
    if project:
        import google.auth
        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds = creds.with_quota_project(project)
        client = speech_mod.SpeechClient(credentials=creds)
    else:
        client = speech_mod.SpeechClient()

    results = []
    for d in dumps:
        wav_path = audio_dir / Path(d["file"]).name
        base = {
            "gen": d.get("gen"),
            "file": wav_path.name,
            "flush_reason": d.get("reason"),
            "first_seq": d.get("first_seq"),
            "last_seq": d.get("last_seq"),
        }
        if not wav_path.exists():
            results.append({**base, "verdict": "WAV_MISSING"})
            continue

        meta = _wav_meta(wav_path)
        base.update(meta)

        # Guard 1: too short to contain a read-back. v1's retracted artifacts
        # were 0.11 s clips that a generative model "completed" into sentences.
        if meta["seconds"] < _MIN_SECONDS:
            results.append({**base, "verdict": "TOO_SHORT"})
            continue

        # PAIRING. The transcript window MUST NOT bleed in a neighbouring
        # generation's text: v1's `last_seq + tail` window pulled the NEXT
        # generation's spelling into this row and scored it as a mismatch
        # (runA gen 8: containment 1.0 -- the sentences matched perfectly --
        # yet a stray "J-O-S-E" from the following turn made it SPELLING_DESYNC).
        # Bound the window by the NEXT dump's first_seq instead of a fixed tail,
        # and record the basis so a pairing bug is auditable per row.
        lo = d.get("first_seq") or 0
        own_hi = d.get("last_seq") or lo
        next_los = [x.get("first_seq") for x in dumps
                    if (x.get("first_seq") or 0) > own_hi and x.get("first_seq") is not None]
        boundary = min(next_los) if next_los else None
        hi = min(own_hi + args.seq_tail, boundary - 1) if boundary is not None \
            else own_hi + args.seq_tail
        text_track = "".join(t for s, t in transcripts if lo <= s <= hi)
        base["seq_window"] = [lo, hi]
        base["window_bounded_by_next_gen"] = boundary is not None
        base["transcript_text"] = text_track

        try:
            with wave.open(str(wav_path), "rb") as w:
                pcm = w.readframes(w.getnframes())
            rec = _recognize(client, speech_mod, pcm, meta["sample_rate"])
        except Exception as exc:  # noqa: BLE001
            results.append({**base, "verdict": "STT_ERROR", "error": str(exc)[:200]})
            continue

        base.update({"stt_text": rec["text"], "confidence": rec["confidence"]})

        # Guard 2: the recognizer heard nothing. A dedicated STT returns empty
        # rather than inventing -- exactly the property v1 lacked.
        if not rec["text"]:
            results.append({**base, "verdict": "NO_SPEECH_DETECTED"})
            continue
        # Guard 3: heard something, but not confidently enough to accuse.
        if rec["confidence"] < _MIN_CONFIDENCE:
            results.append({**base, "verdict": "LOW_CONFIDENCE"})
            continue
        # Guard 4: no transcript to compare against -> pairing cannot be judged.
        if not text_track:
            results.append({**base, "verdict": "NO_TRANSCRIPT"})
            continue

        letters_stt = _letters(rec["text"])
        letters_txt = _letters(text_track)
        cont = _containment(rec["text"], text_track)
        base.update({
            "letters_stt": letters_stt,
            "letters_transcript": letters_txt,
            "containment": round(cont, 3) if cont is not None else None,
        })

        # The two streams INTERLEAVE: a transcript fragment belonging to the
        # next generation can carry a seq inside this generation's own range,
        # so bounding the window is necessary but not sufficient. Guard the
        # residue two ways.
        #
        # (a) CONTAINMENT VETO. If every word the audio spoke is present in the
        #     window (containment 1.0), the two tracks said the SAME sentence --
        #     a letter run appearing on only one side is then bleed, not a
        #     desync. runA gen 8: sentences identical, a stray "J-O-S-E" from
        #     the following turn made it a false SPELLING_DESYNC.
        # (b) ONE-SIDED SPELLING is only evidence when the AUDIO spelled
        #     something the text did not, or the two spellings CONFLICT. Text
        #     spelling with silent audio is the classic bleed signature.
        spelling_conflict = bool(letters_stt) and bool(letters_txt) and letters_stt != letters_txt
        audio_only_spelling = bool(letters_stt) and not letters_txt
        if cont is None:
            verdict = "NO_SPEECH_DETECTED"
        elif spelling_conflict or audio_only_spelling:
            verdict = "SPELLING_DESYNC"
        elif letters_txt and not letters_stt:
            # Text spelled, audio did not: real only if the sentences also
            # diverge; otherwise it is window bleed.
            verdict = "SPELLING_DESYNC" if cont < 0.6 else "ALIGNED"
        elif cont >= 0.6:
            verdict = "ALIGNED"
        elif meta["seconds"] < 2.0:
            # Short clips give the containment metric too few words to be
            # reliable (runA gen 19: 1.7 s, "born in" misheard as "boarding").
            verdict = "TOO_SHORT_TO_JUDGE"
        elif cont >= 0.35:
            verdict = "PARTIAL"
        else:
            verdict = "UTTERANCE_DESYNC"
        results.append({**base, "verdict": verdict})

        mark = "!! " if verdict.endswith("DESYNC") else "   "
        print(f"{mark}gen {str(d.get('gen')):>3} {verdict:18s} "
              f"{meta['seconds']:5.2f}s conf={base.get('confidence', 0):.2f} "
              f"{letters_stt or '-':<10}/{letters_txt or '-'}")

    scoreable = [r for r in results if r["verdict"] not in _UNSCOREABLE]
    desync = [r for r in scoreable if r["verdict"].endswith("DESYNC")]
    summary = {
        "generations": len(results),
        "scoreable": len(scoreable),
        "unscoreable": len(results) - len(scoreable),
        "desync": len(desync),
        "desync_gens": [r["gen"] for r in desync],
        "rate_pct": round(100.0 * len(desync) / len(scoreable), 1) if scoreable else None,
        "by_verdict": {v: sum(1 for r in results if r["verdict"] == v)
                       for v in sorted({r["verdict"] for r in results})},
    }
    out_path = Path(args.out) if args.out else audio_dir / "stt_report_v2.json"
    out_path.write_text(json.dumps({"summary": summary, "results": results}, indent=2),
                        encoding="utf-8")
    print(f"\nSUMMARY {json.dumps(summary)}")
    print(f"report: {out_path}")
    return 0 if summary["desync"] == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
