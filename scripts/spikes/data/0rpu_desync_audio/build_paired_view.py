"""Build the PAIRED view: live-model transcript vs Cloud STT, per generation.

WHY. The defect is only visible when you put two records side by side for the
SAME generation: what the model's own TEXT track said it was saying, and what
Cloud STT heard in the audio it actually produced. Those live in different
files keyed by sequence ranges, so this script does the join once and emits a
flat table.

That table is what a spell-back-tool session needs: it shows the SHAPE of the
failure (which spellings substitute for which) and gives a ready-made
before/after harness -- re-run the tool arm, rebuild this view, and compare
`audio_spelled` against `text_spelled` per row.

Usage (from this directory, backend venv):
  python build_paired_view.py            # writes paired_view.csv + .md
  python build_paired_view.py --run reanchor_control

ASCII only.
"""
from __future__ import annotations

import argparse
import csv
import glob
import io
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))

# Verdicts that carry no conclusion (see the scorer's own _UNSCOREABLE set).
UNSCOREABLE = {"WAV_MISSING", "TOO_SHORT", "NO_SPEECH_DETECTED",
               "LOW_CONFIDENCE", "NO_TRANSCRIPT", "STT_ERROR",
               "TOO_SHORT_TO_JUDGE"}


def letters(text: str) -> str:
    """Spelled-letter runs, normalizing Cloud STT's collapsed form.

    The recognizer renders a spelled run as a pseudo-word with a ZERO for the
    letter O ("J-O-H-N" -> "J0hn"). Recover it or the run is invisible.
    """
    text = text or ""
    for m in set(re.findall(r"\b[A-Za-z]*0[A-Za-z]+\b", text)):
        text = text.replace(m, "-".join(m.replace("0", "O").upper()))
    out = []
    for chunk in re.findall(r"\b(?:[A-Za-z][\s\.\-,]+){1,}[A-Za-z]\b", text):
        seq = "".join(re.findall(r"[A-Za-z]", chunk)).upper()
        if seq in {"ITIN", "SSN", "IRS", "USA", "ZIP", "APO", "PO"}:
            continue
        if len(seq) >= 3:
            out.append(seq)
    return " ".join(out)


def load_stt(run: str):
    """Newest corrected-instrument report for a run (v5 > v4 > final)."""
    for suffix in ("stt_v5.json", "stt_v4.json", "stt_final.json"):
        p = os.path.join(HERE, f"{run}__{suffix}")
        if os.path.exists(p):
            return json.load(io.open(p, encoding="utf-8")), suffix
    return None, None


def load_field_timeline(run: str):
    """(timestamp_ms, field_id) from the run's tool calls -- which field was
    current when a generation was produced."""
    p = os.path.join(HERE, f"{run}__transcript.jsonl")
    if not os.path.exists(p):
        return []
    import datetime
    out = []
    for ln in io.open(p, encoding="utf-8"):
        try:
            r = json.loads(ln)
        except Exception:
            continue
        if r.get("message_type") != "tool_call":
            continue
        c = r.get("content") or {}
        args = c.get("arguments") or {}
        fid = None
        if isinstance(args, dict):
            fid = args.get("field_id")
            if not fid and isinstance(args.get("fields"), list) and args["fields"]:
                first = args["fields"][0]
                if isinstance(first, dict):
                    fid = first.get("field_id") or first.get("id")
        if not fid:
            continue
        try:
            ts = datetime.datetime.fromisoformat(r["timestamp"]).timestamp() * 1000
        except Exception:
            continue
        out.append((ts, fid))
    return sorted(out)


def field_at(timeline, ms):
    cur = ""
    for ts, fid in timeline:
        if ts <= ms:
            cur = fid
        else:
            break
    return cur


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", default=None, help="limit to one run tag")
    args = ap.parse_args()

    runs = sorted({os.path.basename(p).split("__")[0]
                   for p in glob.glob(os.path.join(HERE, "*__stt_*.json"))})
    if args.run:
        runs = [r for r in runs if r == args.run]

    rows = []
    import datetime
    for run in runs:
        rep, which = load_stt(run)
        if not rep:
            continue
        timeline = load_field_timeline(run)
        # audio_dump records carry gen -> timestamp, for the field lookup.
        gen_ts = {}
        tp = os.path.join(HERE, f"{run}__transcript.jsonl")
        if os.path.exists(tp):
            for ln in io.open(tp, encoding="utf-8"):
                try:
                    r = json.loads(ln)
                except Exception:
                    continue
                if r.get("message_type") == "audio_dump":
                    c = r.get("content") or {}
                    try:
                        gen_ts[c.get("gen")] = datetime.datetime.fromisoformat(
                            r["timestamp"]).timestamp() * 1000
                    except Exception:
                        pass
        per_run = []
        for r in rep.get("results", []):
            verdict = r.get("verdict", "")
            stt_text = r.get("stt_text") or ""
            txt_text = r.get("transcript_text") or ""
            a_sp = r.get("letters_stt") or letters(stt_text)
            t_sp = r.get("letters_transcript") or letters(txt_text)
            ms = gen_ts.get(r.get("gen"))
            per_run.append({
                "run": run,
                "gen": r.get("gen"),
                "field_at_gen": field_at(timeline, ms) if ms else "",
                "verdict": verdict,
                "scoreable": "no" if verdict in UNSCOREABLE else "yes",
                "seconds": r.get("seconds"),
                "stt_confidence": r.get("confidence"),
                "text_spelled": t_sp,
                "audio_spelled": a_sp,
                # THREE-WAY, not two. The model asks on one generation and
                # spells on the NEXT, so a row with a spelling on only ONE side
                # is usually that one-generation offset, not a substitution.
                # Only BOTH-populated-and-different is a hard mismatch; the
                # one-sided rows are marked `offset?` and must be read against
                # their neighbour before being counted.
                "spelling_matches": (
                    "" if not (a_sp or t_sp)
                    else "yes" if a_sp == t_sp
                    else "NO" if (a_sp and t_sp)
                    else "offset?"),
                "MODEL_SAID_text_track": " ".join(txt_text.split())[:200],
                "AUDIO_ACTUALLY_SAID_stt": " ".join(stt_text.split())[:200],
                "wav": os.path.basename(str(r.get("file") or "")),
                "source_report": f"{run}__{which}",
            })

        # Resolve each row against its NEIGHBOURS: the model asks on gen N and
        # spells on N+1, so a spelling legitimately lands one generation away
        # from its own text. A spelling is CORROBORATED when it appears in the
        # text track of this row or either neighbour; only an uncorroborated
        # audio spelling is the substitution defect.
        for idx, row in enumerate(per_run):
            a_sp = row["audio_spelled"]
            near = set()
            for k in (idx - 1, idx, idx + 1):
                if 0 <= k < len(per_run):
                    near.update((per_run[k]["text_spelled"] or "").split())
            if not a_sp:
                row["spelling_matches"] = "" if not row["text_spelled"] else "text-only"
            elif all(tok in near for tok in a_sp.split()):
                row["spelling_matches"] = "yes"
            else:
                row["spelling_matches"] = "NO"
            row["text_spelled_nearby"] = " ".join(sorted(t for t in near if t))
        rows.extend(per_run)

    if not rows:
        print("no rows -- are the *__stt_*.json reports present?")
        return 2

    cols = list(rows[0].keys())
    out_csv = os.path.join(HERE, "paired_view.csv")
    with io.open(out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    # A readable digest of just the rows where spelling diverged.
    bad = [r for r in rows if r["spelling_matches"] == "NO"]
    textonly = [r for r in rows if r["spelling_matches"] == "text-only"]
    lines = ["# Paired view -- live-model text track vs Cloud STT of the audio",
             "",
             f"{len(rows)} generations across {len(runs)} runs.",
             "",
             f"- **{len(bad)} HARD MISMATCHES** -- both tracks spelled, and they",
             "  differ. These are the defect.",
             f"- {len(textonly)} rows where only the TEXT track spelled (the model",
             "  asked but the audio for that generation carried no spelling) --",
             "  normal, since the spelling lands on the neighbouring generation.",
             "",
             "Full table: `paired_view.csv`. Rebuild: `python build_paired_view.py`.",
             "",
             "## HARD MISMATCHES -- audio spelled something the text did not",
             "",
             "| run | gen | field | AUDIO spelled | text nearby | conf | wav |",
             "|---|---|---|---|---|---|---|"]
    for r in bad:
        lines.append(
            f"| {r['run']} | {r['gen']} | {r['field_at_gen'] or '-'} | "
            f"**{r['audio_spelled'] or '-'}** | "
            f"{r.get('text_spelled_nearby') or '-'} | "
            f"{r['stt_confidence']} | `{r['wav']}` |")
    lines += ["",
              "## How to use this for the spell-back tool",
              "",
              "Re-run an arm with the tool enabled, rebuild this view, and compare",
              "`audio_spelled` against `text_spelled` per row. The tool works when",
              "every scoreable spelled row reads `spelling_matches = yes`.",
              "",
              "Watch the confidence column: healthy generations score 0.93-0.99 and",
              "corrupted spelled read-backs score 0.34-0.65, so a row that becomes",
              "UNSCOREABLE is not a pass -- it is a row that must be hand-checked.",
              ]
    io.open(os.path.join(HERE, "paired_view.md"), "w",
            encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"wrote paired_view.csv ({len(rows)} rows) and paired_view.md "
          f"({len(bad)} spelling mismatches)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
