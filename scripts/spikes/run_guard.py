"""Hard spend/runaway guard for live voice experiments (bd 0rpu).

WHY THIS EXISTS. On 2026-08-06 an interrupt-triggered re-anchor arm billed
$9.93 in 105 SECONDS. The pre-spend estimate was ~$1. The feature under test
(inject text on every `interrupted` event) removed the turn bound the estimate
assumed: injection -> model speaks -> barge-in interrupts it -> injection, at
~80 ms per cycle. A correctness flag gated WHETHER it ran; nothing gated HOW
OFTEN. This module is that missing bound.

Run it ALONGSIDE a live experiment. It polls the run's token log and kills the
backend the moment any tripwire fires:

  --max-usd      cumulative session cost ceiling (hard stop)
  --max-turns    total billed turns (a runaway shows up here first)
  --max-rate     turns per minute over a 30 s window (catches a tight loop
                 long before the dollar ceiling does)
  --max-minutes  wall-clock ceiling

Kill is by PORT, not PID: a backgrounded uvicorn outlives its shell and the
reload child survives `kill $!` (repo scar tissue).

Usage:
  python scripts/spikes/run_guard.py --token-log backend/logs/token_usage.jsonl \\
      --port 8001 --max-usd 2.00 --max-turns 120 --max-rate 40 --max-minutes 12

Exit 0 = clean finish (log stopped growing), 3 = tripwire fired and the run was
killed. ASCII only.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Suppress the child console window every subprocess opens on Windows
# (bd polyglot-pdf-5k32 / bd polyglot-pdf-rdftu). Duplicated rather than
# imported from swarm_config because importing that module mutates PATH and
# loads a config file -- side effects this script must not take on.
def windowless_creationflags() -> int:
    """subprocess creationflags that suppress child console windows on Windows."""
    if sys.platform == "win32":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0



def _read_events(path: Path) -> list:
    if not path.exists():
        return []
    out = []
    try:
        with io.open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        return out
    return out


def _cost(events: list) -> float:
    total = 0.0
    for r in events:
        c = r.get("cost") or {}
        total += sum(v for k, v in c.items()
                     if isinstance(v, (int, float)) and k.endswith("_usd"))
    return total


def _kill_port(port: int) -> bool:
    """Kill whatever is LISTENING on `port` (Windows netstat + taskkill)."""
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True,
            creationflags=windowless_creationflags(),
                             timeout=20).stdout
    except Exception:
        return False
    pids = set()
    for line in out.splitlines():
        if f":{port}" in line and "LISTENING" in line.upper():
            parts = line.split()
            if parts and parts[-1].isdigit():
                pids.add(parts[-1])
    killed = False
    for pid in pids:
        try:
            subprocess.run(["taskkill", "/F", "/PID", pid],
                creationflags=windowless_creationflags(),
                           capture_output=True, timeout=20)
            killed = True
        except Exception:
            pass
    return killed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--token-log", required=True)
    ap.add_argument("--port", type=int, default=8001)
    ap.add_argument("--max-usd", type=float, default=2.00)
    ap.add_argument("--max-turns", type=int, default=120)
    ap.add_argument("--max-rate", type=float, default=40.0,
                    help="max billed turns per minute (30 s window)")
    ap.add_argument("--max-minutes", type=float, default=12.0)
    ap.add_argument("--poll-sec", type=float, default=2.0)
    ap.add_argument("--idle-exit-sec", type=float, default=90.0,
                    help="exit cleanly after this long with no new turns")
    ap.add_argument("--startup-grace-sec", type=float, default=180.0,
                    help="how long to wait for the token log to appear before "
                         "aborting (a guard on a missing log is blind)")
    args = ap.parse_args()

    log = Path(args.token_log)
    # A guard watching a log that never appears is not a guard -- it is a
    # 12-minute nap. (Observed: the NATO arm ran with the guard pointed at a
    # token log that had been deleted before the run, so it saw turns=0
    # throughout and only fired on wall-clock, after the run was already over.)
    # Wait for the log to APPEAR, and refuse to run if it never does.
    appear_deadline = time.time() + args.startup_grace_sec
    while not log.exists():
        if time.time() > appear_deadline:
            print(f"[guard] ABORT: {log} never appeared within "
                  f"{args.startup_grace_sec:.0f}s -- the guard would be blind. "
                  f"Check --token-log points at the RUN's log.")
            return 2
        time.sleep(1.0)

    started = time.time()
    last_growth = time.time()
    last_n = 0
    window = []  # (timestamp, cumulative_turns)

    print(f"[guard] watching {log}")
    print(f"[guard] tripwires: <= ${args.max_usd:.2f}, <= {args.max_turns} turns, "
          f"<= {args.max_rate}/min, <= {args.max_minutes} min")

    while True:
        time.sleep(args.poll_sec)
        events = _read_events(log)
        n = len(events)
        usd = _cost(events)
        now = time.time()

        if n > last_n:
            last_growth = now
            last_n = n

        window.append((now, n))
        window[:] = [(t, c) for t, c in window if now - t <= 30.0]
        rate = 0.0
        if len(window) >= 2:
            dt = window[-1][0] - window[0][0]
            dn = window[-1][1] - window[0][1]
            if dt > 0:
                rate = dn * 60.0 / dt

        trip = None
        if usd >= args.max_usd:
            trip = f"COST ${usd:.4f} >= ${args.max_usd:.2f}"
        elif n >= args.max_turns:
            trip = f"TURNS {n} >= {args.max_turns}"
        elif rate > args.max_rate:
            trip = f"RATE {rate:.1f}/min > {args.max_rate}/min (runaway loop)"
        elif (now - started) / 60.0 >= args.max_minutes:
            trip = f"WALL CLOCK {(now-started)/60.0:.1f} min >= {args.max_minutes}"

        if trip:
            print(f"[guard] TRIPWIRE: {trip}")
            print(f"[guard] killing port {args.port} ...")
            ok = _kill_port(args.port)
            print(f"[guard] kill {'succeeded' if ok else 'found nothing to kill'}")
            print(f"[guard] final: turns={n} cost=${usd:.4f} "
                  f"elapsed={(now-started)/60.0:.1f}min")
            return 3

        if now - last_growth >= args.idle_exit_sec and n > 0:
            print(f"[guard] no new turns for {args.idle_exit_sec:.0f}s -- run looks done")
            print(f"[guard] final: turns={n} cost=${usd:.4f} "
                  f"elapsed={(now-started)/60.0:.1f}min")
            return 0

        print(f"[guard] turns={n:4d} cost=${usd:7.4f} rate={rate:5.1f}/min "
              f"elapsed={(now-started)/60.0:4.1f}min", flush=True)


if __name__ == "__main__":
    sys.exit(main())
