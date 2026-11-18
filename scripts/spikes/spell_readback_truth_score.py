"""Score spelled name read-backs against GROUND TRUTH (bd polyglot-pdf-r3ham.3).

stt_readback_diff2.py compares the model's audio to its OWN transcript. On
gemini-3.8-live the transcript arrives bundled with the audio and its seq
window straddles generations, so that pairing mislabels clean read-backs.
This pass instead takes, for each spelled-name step of driver_w7_desync, the
dumped generation(s) whose dump time falls between the field FILL and the
"yes" injection -- i.e. the read-back -- and compares the Cloud STT letters of
that audio to (a) the scripted spelling and (b) the stored value.

Usage: python p2score.py <run_dir> [<run_dir> ...]   (needs stt.json per run)
"""
import json
import os
import sys
from datetime import datetime

TRUTH = {"spell_john": "JOHN", "spell_joshua": "JOSHUA", "spell_johnson": "JOHNSON",
         "spell_maria": "MARIA", "spell_jose": "JOSE", "spell_smith": "SMITH"}
ORDER = ["JOHN", "JOSHUA", "JOHNSON", "MARIA", "JOSE", "SMITH"]


def lev(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def ts_ms(s):
    return datetime.fromisoformat(s).timestamp() * 1000.0


def score_run(d):
    rep = json.load(open(os.path.join(d, "report.json"), encoding="utf-8"))
    stt = json.load(open(os.path.join(d, "stt.json"), encoding="utf-8"))
    by_file = {os.path.basename(r["file"]): r for r in stt["results"]}
    dumps = []
    jl = ("combined.jsonl" if os.path.exists(os.path.join(d, "combined.jsonl")) else
          [f for f in os.listdir(d) if f.startswith("gemini_") and f.endswith(".jsonl")][0])
    for line in open(os.path.join(d, jl), encoding="utf-8"):
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("message_type") == "audio_dump":
            f = os.path.basename(str((r.get("content") or {}).get("file", "")).replace("\\", "/"))
            dumps.append((ts_ms(r["timestamp"]), f))
    rows = []
    for st in rep["steps"]:
        if st.get("kind") != "spell":
            continue
        truth = TRUTH[st["fixture"]]
        stored = (st.get("value") or "").upper()
        lo, hi = st.get("tFill"), st.get("tConfirm")
        row = {"run": os.path.basename(d), "field": st.get("fieldId"), "truth": truth,
               "stored": stored, "confirmed": st.get("confirmed")}
        if not lo:
            row["class"] = "NOT_FILLED"
            rows.append(row)
            continue
        hi = hi or lo + 30000
        cands = [by_file.get(f) for t, f in dumps if lo - 500 <= t <= hi + 1500]
        cands = [c for c in cands if c]
        letters = ""
        for c in cands:
            ls = (c.get("letters_stt") or "").upper()
            if len(ls) > len(letters):
                letters, row["stt_text"], row["conf"] = ls, c.get("stt_text"), c.get("confidence")
        if "stt_text" not in row and cands:
            best = max(cands, key=lambda c: c.get("seconds") or 0)
            row["stt_text"], row["conf"] = best.get("stt_text"), best.get("confidence")
        row["heard"] = letters
        prev_names = ORDER[:ORDER.index(truth)]
        if not cands:
            row["class"] = "NO_READBACK_AUDIO"
        elif not letters:
            row["class"] = "NOT_SPELLED"
        elif letters == truth or truth in letters:
            row["class"] = "EXACT"
        elif any(p == letters or (p in letters and truth not in letters) for p in prev_names):
            row["class"] = "STICKY_PREVIOUS"
        else:
            row["class"] = "ADD_DROP(lev=%d)" % lev(letters, truth)
        row["stored_ok"] = stored == truth
        rows.append(row)
    return rows


if __name__ == "__main__":
    allrows = []
    for d in sys.argv[1:]:
        allrows += score_run(d)
    for r in allrows:
        print("%-28s %-16s truth=%-8s stored=%-8s heard=%-16s %s conf=%s" % (
            r["run"][:28], r["field"], r["truth"], r["stored"], r.get("heard", ""),
            r["class"], r.get("conf")))
        print("      STT: %r" % (r.get("stt_text"),))
    scoreable = [r for r in allrows if r["class"] in ("EXACT", "STICKY_PREVIOUS") or r["class"].startswith("ADD_DROP")]
    errs = [r for r in scoreable if r["class"] != "EXACT"]
    stored_err = [r for r in allrows if r.get("stored") and not r.get("stored_ok")]
    print(json.dumps({"spelled_readbacks_scoreable": len(scoreable), "readback_errors": len(errs),
                      "stored_value_errors": len(stored_err),
                      "classes": {c: sum(1 for r in allrows if r["class"] == c) for c in sorted({r["class"] for r in allrows})}}))
