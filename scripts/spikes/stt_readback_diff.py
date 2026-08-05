"""STT-score the model's OUTPUT AUDIO against its own text transcript (bd 0rpu).

THE QUESTION THIS ANSWERS: during spelled name read-backs, does the audio the
model actually GENERATED match the text track it reported? The 2026-08-05
investigation proved the two can diverge (user heard "J-O-H-N, Joshua" while the
transcript said "J-O-S-H-U-A") and that the divergence correlates with a
context-compression eviction. Ears cannot be automated; STT can. This script is
the measurable-proof instrument the maintainer asked for ("We need measurable
proof, so STT").

INPUTS (both produced by a local run with LIVE_DEV_TRANSCRIPTS=true and
LIVE_DEV_AUDIO_DUMP=true -- see scripts/dev-local.sh):
  - a backend/logs/audio_out/gemini_<date>/ directory of per-generation WAVs
  - the matching backend/logs/gemini_<date>.jsonl dev log, whose `audio_dump`
    records carry {file, gen, first_seq, last_seq} and whose `transcript`
    records carry spoken_by_model text stamped with seq

METHOD, per generation WAV:
  1. collect the transcript text whose seq falls in [first_seq, last_seq]
     (plus a small tail margin -- transcript events can trail the audio);
  2. send the WAV to Vertex gemini-2.5-flash (audio understanding) with a
     transcribe-verbatim prompt;
  3. normalize both sides (uppercase, letters extracted from spell-outs);
  4. verdict: MATCH | AUDIO_TEXT_DESYNC | NO_SPELLING (nothing spelled on either
     side -- not evidence either way) | NO_TRANSCRIPT.

Emits a JSON report next to the audio dir + a human summary to stdout.

BILLING: Vertex ONLY (all-live-model-work-on-Vertex law). Cost is printed
before any call; audio input at flash rates is cents for a full session.
PII: WAVs and transcripts are PHI. The report lives beside the gitignored
audio dir by default; keep it out of commits.

Usage (from repo root, backend venv):
  backend/.venv/Scripts/python.exe scripts/spikes/stt_readback_diff.py \
      --audio-dir backend/logs/audio_out/gemini_2026-08-05 \
      --jsonl backend/logs/gemini_2026-08-05.jsonl [--yes]

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

# Rough audio tokenization rate for the cost print (Gemini docs: ~32 tok/sec).
_AUDIO_TOK_PER_SEC = 32
# gemini-2.5-flash paid-tier audio input $1.00/M tok (text out negligible here).
_USD_PER_MTOK_AUDIO = 1.00

_STT_PROMPT = (
    "Transcribe this audio VERBATIM. It is a form assistant speaking English. "
    "If letters are spelled out individually, write them as single letters "
    "separated by hyphens (example: J-O-H-N). Include every word you hear. "
    "Output ONLY the transcription, no commentary."
)


def _client():
    from google import genai  # deferred so --help works without the SDK

    if os.environ.get("VERTEXAI", "true").lower() == "true":
        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not project:
            print("VERTEXAI mode but GOOGLE_CLOUD_PROJECT unset; relying on ADC "
                  "default project.", flush=True)
        return genai.Client(
            vertexai=True,
            project=project,
            location=os.environ.get("VERTEX_LOCATION", "us-central1"),
        )
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("VERTEXAI=false but GEMINI_API_KEY unset", flush=True)
        sys.exit(2)
    return genai.Client(api_key=key)


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
    """Extract the spelled-letter sequence from a read-back, normalized.

    Accepts 'J-O-H-N', 'J. O. H. N.', 'J O H N', 'j-o-h-n' -- returns 'JOHN'.
    Multiple spell-outs concatenate in order. Empty string when nothing is
    spelled (a normal sentence has no isolated single-letter runs).
    """
    # Single letters separated by non-letter separators, in runs of >= 2.
    run = re.findall(r"\b(?:[A-Za-z][\s\.\-,]+){1,}[A-Za-z]\b", text)
    out = []
    for chunk in run:
        letters = re.findall(r"[A-Za-z]", chunk)
        # Only count it as a spell-out if every token in the chunk was a single
        # letter (the regex guarantees separators between single letters).
        # Minimum THREE letters: two-letter dotted abbreviations ("U.S.",
        # "e.g.") are normal prose, not spell-outs, and produced a false
        # AUDIO_TEXT_DESYNC on the smoke run (option label "U.S. citizen").
        if len(letters) >= 3:
            out.append("".join(letters).upper())
    return "".join(out)


def _norm(text: str) -> str:
    return re.sub(r"[^A-Z0-9 ]", "", text.upper()).strip()


def _wav_seconds(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / float(w.getframerate() or 24000)
    except Exception:
        return 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--audio-dir", required=True)
    ap.add_argument("--jsonl", required=True)
    ap.add_argument("--model", default="gemini-2.5-flash")
    ap.add_argument("--out", default=None,
                    help="report path (default: <audio-dir>/stt_report.json)")
    ap.add_argument("--seq-tail", type=int, default=40,
                    help="transcript seq margin past last_seq (events trail audio)")
    ap.add_argument("--yes", action="store_true",
                    help="skip the cost confirmation prompt")
    args = ap.parse_args()

    audio_dir = Path(args.audio_dir)
    jsonl = Path(args.jsonl)
    rows = _load_jsonl(jsonl)

    # audio_dump records tie WAVs to seq ranges; transcript records carry text.
    dumps = [r["content"] for r in rows
             if r.get("message_type") == "audio_dump" and isinstance(r.get("content"), dict)]
    transcripts = [(r["content"].get("seq", 0), r["content"].get("spoken_by_model") or "")
                   for r in rows
                   if r.get("message_type") == "transcript"
                   and isinstance(r.get("content"), dict)
                   and (r["content"].get("spoken_by_model") or "")]

    if not dumps:
        print("No audio_dump records in the JSONL -- was LIVE_DEV_AUDIO_DUMP on?")
        return 2

    # Pre-spend gate (experimentation skill): estimate before calling.
    total_sec = sum(_wav_seconds(audio_dir / Path(d["file"]).name) for d in dumps)
    est_usd = total_sec * _AUDIO_TOK_PER_SEC / 1e6 * _USD_PER_MTOK_AUDIO
    print(f"generations: {len(dumps)}  audio: {total_sec:.1f}s  "
          f"est STT cost: ${est_usd:.4f}  model: {args.model} (Vertex)")
    if not args.yes:
        reply = input("proceed? [y/N] ").strip().lower()
        if reply != "y":
            print("aborted")
            return 1

    from google.genai import types
    client = _client()

    results = []
    for d in dumps:
        wav_path = audio_dir / Path(d["file"]).name
        if not wav_path.exists():
            results.append({**d, "verdict": "WAV_MISSING"})
            continue
        lo, hi = d.get("first_seq") or 0, (d.get("last_seq") or 0) + args.seq_tail
        # The generation's own transcript: seq within [lo, hi].
        text_track = "".join(t for s, t in transcripts if lo <= s <= hi)

        audio = wav_path.read_bytes()
        try:
            resp = client.models.generate_content(
                model=args.model,
                contents=[
                    types.Part.from_bytes(data=audio, mime_type="audio/wav"),
                    _STT_PROMPT,
                ],
                # Vertex enables thinking BY DEFAULT on 2.5-flash; unbounded
                # thinking tokens dwarf the answer and bust the cost estimate
                # (experimentation skill Gate 2; same pattern as
                # text_ai_gemini.py's ThinkingConfig plumb). Transcription
                # needs no reasoning: budget 0, temperature 0.
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            stt_text = (resp.text or "").strip()
        except Exception as exc:  # noqa: BLE001 -- report, don't crash the sweep
            results.append({**d, "verdict": "STT_ERROR", "error": str(exc)[:200]})
            continue

        letters_stt = _letters(stt_text)
        letters_txt = _letters(text_track)
        if not text_track:
            verdict = "NO_TRANSCRIPT"
        elif not letters_stt and not letters_txt:
            verdict = "NO_SPELLING"
        elif letters_stt == letters_txt:
            verdict = "MATCH"
        else:
            verdict = "AUDIO_TEXT_DESYNC"

        results.append({
            "gen": d.get("gen"), "file": str(wav_path),
            "first_seq": d.get("first_seq"), "last_seq": d.get("last_seq"),
            "reason": d.get("reason"),
            "stt_text": stt_text, "transcript_text": text_track,
            "letters_stt": letters_stt, "letters_transcript": letters_txt,
            "verdict": verdict,
        })
        mark = "OK " if verdict in ("MATCH", "NO_SPELLING") else "!! "
        print(f"{mark}gen {d.get('gen'):>3} {verdict:<18} "
              f"stt={letters_stt or '-':<12} txt={letters_txt or '-'}")

    summary = {
        "runs": len(results),
        "match": sum(1 for r in results if r["verdict"] == "MATCH"),
        "desync": sum(1 for r in results if r["verdict"] == "AUDIO_TEXT_DESYNC"),
        "no_spelling": sum(1 for r in results if r["verdict"] == "NO_SPELLING"),
        "other": sum(1 for r in results if r["verdict"] not in
                     ("MATCH", "AUDIO_TEXT_DESYNC", "NO_SPELLING")),
    }
    out_path = Path(args.out) if args.out else audio_dir / "stt_report.json"
    out_path.write_text(json.dumps({"summary": summary, "results": results},
                                   indent=2), encoding="utf-8")
    print(f"\nSUMMARY {json.dumps(summary)}")
    print(f"report: {out_path}")
    # Non-zero when desync observed, so a driver script can branch on it.
    return 0 if summary["desync"] == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
