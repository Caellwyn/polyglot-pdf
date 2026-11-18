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
import sys
import wave
from pathlib import Path

# The shared v2 helpers live in sim_user_stt.py (public names); the private
# names below are thin aliases so this CLI reads as it always did.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sim_user_stt as _shared  # noqa: E402

_UNSCOREABLE = _shared.UNSCOREABLE
_MIN_SECONDS = _shared.MIN_SECONDS
_MIN_CONFIDENCE = _shared.MIN_CONFIDENCE
_letters = _shared.letters
_words = _shared.words
_containment = _shared.containment
_recognize = _shared.recognize


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
    client = _shared.make_speech_client()

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
        # The transcript stream LEADS the audio-dump boundaries: a spelling
        # spoken in this generation routinely lands in the PREVIOUS
        # generation's seq window. Widen the comparison window backwards to
        # the previous dump's start so the pair is judged on the same
        # utterance, not on a boundary accident.
        prev_los = [x.get("first_seq") for x in dumps
                    if x.get("first_seq") is not None and (x.get("first_seq") or 0) < lo]
        neighbour_lo = max(prev_los) if prev_los else lo
        next_los = [x.get("first_seq") for x in dumps
                    if (x.get("first_seq") or 0) > own_hi and x.get("first_seq") is not None]
        boundary = min(next_los) if next_los else None
        hi = min(own_hi + args.seq_tail, boundary - 1) if boundary is not None \
            else own_hi + args.seq_tail
        text_track = "".join(t for s, t in transcripts if lo <= s <= hi)
        # Adjacent-inclusive text used ONLY for spelled-run comparison.
        text_neighbourhood = "".join(t for s, t in transcripts
                                     if neighbour_lo <= s <= hi)
        base["seq_window"] = [lo, hi]
        base["neighbour_window"] = [neighbour_lo, hi]
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

        # Guards 2-4 + the verdict rules live in sim_user_stt.classify_pair
        # (verbatim lift of the logic that used to be inline here).
        verdict, extras = _shared.classify_pair(
            rec["text"], rec["confidence"], text_track, text_neighbourhood,
            meta["seconds"])
        base.update(extras)
        if "letters_stt" not in extras:  # a guard returned before comparison
            results.append({**base, "verdict": verdict})
            continue
        letters_stt = extras["letters_stt"]
        letters_txt = extras["letters_transcript"]
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
        "needs_hand_check": [r["gen"] for r in results if r.get("needs_hand_check")],
    }
    out_path = Path(args.out) if args.out else audio_dir / "stt_report_v2.json"
    out_path.write_text(json.dumps({"summary": summary, "results": results}, indent=2),
                        encoding="utf-8")
    print(f"\nSUMMARY {json.dumps(summary)}")
    print(f"report: {out_path}")
    return 0 if summary["desync"] == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
