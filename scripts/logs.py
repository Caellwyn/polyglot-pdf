#!/usr/bin/env python3
"""
logs.py -- explorer for the dev Gemini I/O logs (bd polyglot-pdf-2m9).

The dev logger (backend/utils/dev_file_logger.py) writes one JSON object per line
to backend/logs/gemini_<date>.jsonl. This CLI is the navigation layer so debugging
does not mean eyeballing raw JSONL or grepping: it indexes by session, renders
ordered per-session timelines, and surfaces errors / audio flow / turn boundaries.

Pure stdlib (no pandas/duckdb required) so it always runs from the backend venv or
plain python. The optional `sql` subcommand uses DuckDB if installed (it reads the
.jsonl natively) and otherwise prints an install hint.

Event schema (per line): timestamp, direction, message_type, session_id,
ws_session_id, content{...} (content may carry seq, model, frames, bytes, ...).

Usage (from repo root):
  python scripts/logs.py sessions                  # index: one row per Gemini session
  python scripts/logs.py session <id|prefix>       # ordered timeline of one session
  python scripts/logs.py errors                    # error / invalid / rejected events
  python scripts/logs.py tail [-n N]               # last N events across all sessions
  python scripts/logs.py types                     # message_type histogram
  python scripts/logs.py sql "<query>"             # DuckDB SQL over the jsonl (optional)

Options:
  --file PATH     explicit jsonl (default: newest backend/logs/gemini_*.jsonl)
  --date YYYY-MM-DD   pick a specific daily file
  --json          machine-readable output (for the agent to parse)
"""

import argparse
import glob
import json
import os
import sys
from collections import OrderedDict, defaultdict

# The captured frontend console lines are full of emoji; Windows' default cp1252
# stdout raises UnicodeEncodeError on them. Force UTF-8 so this explorer never
# crashes on the very logs it exists to read (scar #6, but here we must DISPLAY
# non-ASCII we don't control, not avoid emitting it).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _repo_root():
    # scripts/ lives at the repo root; logs are under backend/logs.
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _default_log_file(date=None):
    logs_dir = os.path.join(_repo_root(), "backend", "logs")
    if date:
        p = os.path.join(logs_dir, f"gemini_{date}.jsonl")
        return p if os.path.exists(p) else None
    candidates = sorted(glob.glob(os.path.join(logs_dir, "gemini_*.jsonl")))
    return candidates[-1] if candidates else None


def _load(path):
    """Yield parsed events; tolerate trailing/partial lines."""
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception as e:
                print(f"[logs] skipping unparseable line {ln}: {e}", file=sys.stderr)
    return rows


def _short(s, n=10):
    s = str(s or "")
    return s[:n]


def _ts(row):
    return str(row.get("timestamp", ""))


def _hhmmss(row):
    t = _ts(row)
    # ISO -> HH:MM:SS
    return t[11:19] if len(t) >= 19 else t


# ----------------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------------

def cmd_sessions(rows, args):
    """Top-level index: one row per Gemini session, ordered by first event."""
    by_sess = OrderedDict()
    for r in rows:
        sid = r.get("session_id") or "(none)"
        s = by_sess.setdefault(sid, {
            "session_id": sid,
            "ws": r.get("ws_session_id"),
            "first": _ts(r), "last": _ts(r),
            "events": 0, "text_turns": 0, "tool_calls": 0,
            "audio_in": 0, "gemini_send": 0, "audio_out": 0, "errors": 0,
            "model": None,
        })
        s["events"] += 1
        s["last"] = _ts(r)
        mt = r.get("direction"), r.get("message_type")
        c = r.get("content") or {}
        if c.get("model"):
            s["model"] = c["model"]
        if mt[1] == "text_turn":
            s["text_turns"] += 1
        elif mt[1] == "tool_call":
            s["tool_calls"] += 1
        elif mt[1] == "audio_summary":
            # keep the LATEST frame count seen (rollups are cumulative)
            if mt[0] == "send":
                s["audio_in"] = max(s["audio_in"], c.get("frames", 0))  # reached queue
            else:
                s["audio_out"] = max(s["audio_out"], c.get("frames", 0))
        elif mt[1] == "gemini_send":
            s["gemini_send"] = max(s["gemini_send"], c.get("frames", 0))  # crossed to Gemini
        elif mt[1] in ("error", "invalid_tool_call", "field_update_rejected", "gemini_send_failed"):
            s["errors"] += 1

    sessions = list(by_sess.values())
    if args.json:
        print(json.dumps(sessions, indent=2, default=str))
        return

    if not sessions:
        print("(no sessions)")
        return
    # aIn = frames that reached the backend audio queue; gSnd = frames actually
    # handed to Gemini via send_realtime_input; aOut = Gemini audio frames back.
    hdr = (f"{'session':12} {'start':8} {'end':8} {'evt':>4} {'txt':>3} {'tool':>4} "
           f"{'aIn':>5} {'gSnd':>5} {'aOut':>5} {'err':>3}  model")
    print(hdr)
    print("-" * len(hdr))
    for s in sessions:
        print(f"{_short(s['session_id'],12):12} "
              f"{s['first'][11:19]:8} {s['last'][11:19]:8} "
              f"{s['events']:>4} {s['text_turns']:>3} {s['tool_calls']:>4} "
              f"{s['audio_in']:>5} {s['gemini_send']:>5} {s['audio_out']:>5} {s['errors']:>3}  "
              f"{_short(s['model'],28)}")
    # The one-line health read the agent wants first -- pinpoints WHICH layer broke:
    print()
    for s in sessions:
        flow = []
        if s["audio_in"] == 0:
            flow.append("NO mic audio reached the backend queue")
        elif s["gemini_send"] == 0:
            flow.append("audio queued but NOT sent to Gemini (sender starved/erroring)")
        elif s["gemini_send"] < s["audio_in"] * 0.5:
            flow.append(f"audio LAGS into Gemini (queued {s['audio_in']} vs sent {s['gemini_send']})")
        if s["audio_in"] and s["audio_out"] == 0:
            flow.append("audio reached Gemini but NO audio response")
        if flow:
            print(f"  ! {_short(s['session_id'],12)}: " + "; ".join(flow))


def _match_session(rows, key):
    """Resolve a session id by exact match or unique prefix."""
    ids = []
    for r in rows:
        sid = r.get("session_id")
        if sid and sid not in ids:
            ids.append(sid)
    exact = [i for i in ids if i == key]
    if exact:
        return exact[0]
    pref = [i for i in ids if i.startswith(key) or key in i]
    if len(pref) == 1:
        return pref[0]
    if len(pref) > 1:
        print(f"[logs] ambiguous session '{key}': {pref}", file=sys.stderr)
        return None
    print(f"[logs] no session matching '{key}' (have: {ids})", file=sys.stderr)
    return None


def cmd_session(rows, args):
    """Ordered timeline of a single session, interleaving frontend console lines.

    Gemini events key on session_id (LiveAI-*); frontend console events
    (direction='frontend') only have ws_session_id (the fss_* form session). We
    include console lines whose ws_session_id matches this Gemini session's
    ws_session_id, so the timeline shows e.g. a "[PTT] press" line right next to the
    audio_summary frames it produced. Sorted by timestamp."""
    sid = _match_session(rows, args.id)
    if not sid:
        sys.exit(1)
    gemini = [r for r in rows if r.get("session_id") == sid]
    ws_ids = {r.get("ws_session_id") for r in gemini if r.get("ws_session_id")}
    console = [r for r in rows
               if r.get("direction") == "frontend" and r.get("ws_session_id") in ws_ids]
    events = sorted(gemini + console, key=lambda r: _ts(r))
    if args.json:
        print(json.dumps(events, indent=2, default=str))
        return
    print(f"session {sid}  ({len(events)} events)")
    print("-" * 72)
    for r in events:
        c = r.get("content") or {}
        d, mt = r.get("direction"), r.get("message_type")
        extra = ""
        if mt == "text_turn":
            extra = " " + repr(str(c.get("text", ""))[:80])
        elif mt == "audio_summary":
            extra = f" frames={c.get('frames')} bytes={c.get('bytes')}"
        elif mt == "tool_call":
            extra = f" {c.get('tool_name')} {json.dumps(c.get('arguments', {}), default=str)[:80]}"
        elif mt in ("activity_start", "activity_end"):
            extra = f" source={c.get('source')}"
        elif mt in ("session_open", "session_close"):
            extra = " " + json.dumps({k: v for k, v in c.items() if k not in ("seq", "model")}, default=str)[:80]
        elif mt in ("error", "invalid_tool_call"):
            extra = " " + json.dumps(c, default=str)[:120]
        elif mt == "model_response":
            extra = " " + repr(str(c.get("text") or c.get("transcript") or "")[:80])
        elif mt == "event_shape":
            # Compact: only show the TRUE flags / non-zero lens, so the signal
            # (did Gemini hear us? send anything?) is not buried.
            flags = []
            for k in ("has_audio", "has_server_content", "interrupted",
                      "turn_complete", "generation_complete", "tool_call"):
                if c.get(k):
                    flags.append(k)
            for k in ("input_transcription_len", "output_transcription_len", "model_turn_parts"):
                if c.get(k):
                    flags.append(f"{k}={c.get(k)}")
            extra = " " + (", ".join(flags) if flags else "(empty)")
        elif mt and mt.startswith("console_"):
            extra = " " + str(c.get("text", ""))[:110]
        seq = c.get("seq")
        print(f"  {_hhmmss(r)} #{str(seq or '').rjust(3)} {str(d):7} {str(mt):16}{extra}")


def cmd_errors(rows, args):
    errs = [r for r in rows
            if r.get("message_type") in ("error", "invalid_tool_call", "field_update_rejected")]
    if args.json:
        print(json.dumps(errs, indent=2, default=str))
        return
    if not errs:
        print("(no errors)")
        return
    for r in errs:
        print(f"{_hhmmss(r)} {_short(r.get('session_id'),12):12} {r.get('message_type'):22} "
              f"{json.dumps(r.get('content', {}), default=str)[:120]}")


def cmd_tail(rows, args):
    n = args.n or 40
    tail = rows[-n:]
    if args.json:
        print(json.dumps(tail, indent=2, default=str))
        return
    for r in tail:
        c = r.get("content") or {}
        print(f"{_hhmmss(r)} {_short(r.get('session_id'),12):12} {str(r.get('direction')):7} "
              f"{str(r.get('message_type')):16} {json.dumps({k:v for k,v in c.items() if k!='seq'}, default=str)[:90]}")


def cmd_console(rows, args):
    """Frontend console lines (direction='frontend'), optionally level-filtered."""
    want = (args.level or "all")
    out = []
    for r in rows:
        if r.get("direction") != "frontend":
            continue
        lvl = (r.get("message_type") or "").replace("console_", "")
        if want == "error" and lvl != "error":
            continue
        if want == "warn" and lvl not in ("warn", "error"):
            continue
        out.append(r)
    if args.json:
        print(json.dumps(out, indent=2, default=str))
        return
    if not out:
        print("(no frontend console events -- is devConsoleCapture installed + backend local?)")
        return
    for r in out:
        c = r.get("content") or {}
        lvl = (r.get("message_type") or "").replace("console_", "")
        print(f"{_hhmmss(r)} {_short(r.get('ws_session_id'),14):14} {lvl:5} {str(c.get('text',''))[:140]}")


def cmd_types(rows, args):
    hist = defaultdict(int)
    for r in rows:
        hist[(r.get("direction"), r.get("message_type"))] += 1
    items = sorted(hist.items(), key=lambda kv: -kv[1])
    if args.json:
        print(json.dumps([{"direction": k[0], "message_type": k[1], "count": v} for k, v in items], indent=2))
        return
    for (d, mt), v in items:
        print(f"{v:5}  {str(d):8} {mt}")


def cmd_sql(rows, args):
    """Arbitrary SQL over the jsonl via DuckDB (optional dependency)."""
    try:
        import duckdb  # type: ignore
    except Exception:
        print("[logs] DuckDB not installed. Install it in the backend venv:", file=sys.stderr)
        print("       backend/.venv/Scripts/pip install duckdb", file=sys.stderr)
        print("       Then: python scripts/logs.py sql \"SELECT message_type, count(*) "
              "FROM logs GROUP BY 1\"", file=sys.stderr)
        sys.exit(2)
    con = duckdb.connect()
    # read_json_auto handles the nested 'content' as a struct/json column.
    con.execute(f"CREATE VIEW logs AS SELECT * FROM read_json_auto('{args.file}')")
    res = con.execute(args.query).fetchall()
    cols = [d[0] for d in con.description]
    if args.json:
        print(json.dumps([dict(zip(cols, row)) for row in res], indent=2, default=str))
        return
    print("  ".join(cols))
    for row in res:
        print("  ".join(str(x) for x in row))


def main():
    p = argparse.ArgumentParser(description="Explore dev Gemini I/O logs (bd polyglot-pdf-2m9).")
    p.add_argument("--file", help="explicit jsonl file (default: newest backend/logs/gemini_*.jsonl)")
    p.add_argument("--date", help="pick backend/logs/gemini_<date>.jsonl")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("sessions", help="index: one row per session")
    sp = sub.add_parser("session", help="timeline of one session")
    sp.add_argument("id", help="session id or unique prefix")
    sub.add_parser("errors", help="error / invalid / rejected events")
    cp = sub.add_parser("console", help="frontend console lines (devConsoleCapture)")
    cp.add_argument("--level", choices=["all", "warn", "error"], default="all")
    tp = sub.add_parser("tail", help="last N events")
    tp.add_argument("-n", type=int, default=40)
    sub.add_parser("types", help="message_type histogram")
    qp = sub.add_parser("sql", help="DuckDB SQL over the jsonl (view name: logs)")
    qp.add_argument("query")

    args = p.parse_args()

    path = args.file or _default_log_file(args.date)
    if not path or not os.path.exists(path):
        print(f"[logs] no log file found (looked in backend/logs/). "
              f"Run the local stack with backend/.env.DEV present to generate one.", file=sys.stderr)
        sys.exit(1)
    args.file = path

    if args.cmd == "sql":
        cmd_sql(None, args)
        return

    rows = _load(path)
    print(f"[logs] {os.path.relpath(path, _repo_root())}  ({len(rows)} events)\n", file=sys.stderr)
    {
        "sessions": cmd_sessions,
        "session": cmd_session,
        "errors": cmd_errors,
        "console": cmd_console,
        "tail": cmd_tail,
        "types": cmd_types,
    }[args.cmd](rows, args)


if __name__ == "__main__":
    main()
