"""Run the session-start / closeout beads audits with pull/push bracketing.

Background
----------
CLAUDE.md prescribes two ~1-second beads audits that catch lifecycle slips:

  - `bd orphans`  -- beads closed in commits but still OPEN in the tracker
                     (an R2 slip: the bead was finished but never closed).
  - `bd stale --status in_progress -d 1`
                  -- beads IN_PROGRESS with no update in >24h (an R3 slip:
                     work was claimed and then abandoned without a transition).

Both must run AFTER a `bd dolt pull` (the local Dolt DB is a cache; the
remote is truth) so the audit reflects what every worker has done, not just
this machine. This script is the deterministic step the /closeout skill
wraps -- it spends zero model tokens and leaves the model only the judgment
(what to do about any slip it surfaces).

This is a READ-ONLY audit: it pulls, reports, and does a final push so the
local cache stays in sync, but it never claims/closes/defers anything --
those are write decisions the orchestrator (the only beads writer) makes,
using bd_safe.py.

Usage
-----
    python scripts/closeout_housekeeping.py [--stale-days N]

Exit codes: 0 if both audits ran and found nothing; 3 if either audit
surfaced a slip (distinct from 1, a tooling failure, so a caller can branch
"there's lifecycle work to triage" vs "the audit itself broke"). The
slip-found signal is advisory -- the orchestrator decides what to do.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

# bd emits UTF-8 (e.g. a U+2713 check mark in a clean-audit line). Printing
# that to a cp1252 Windows console crashes with UnicodeEncodeError. Reconfigure
# stdout/stderr to UTF-8 with errors="replace" so a stray glyph degrades to a
# replacement char rather than killing the script -- the same robustness the
# captured-subprocess decode already has. (Python 3.7+ has reconfigure.)
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_SLIP_FOUND = 3

# Wall-clock cap per bd call (a cold Dolt remote pull can be slow). Same
# hang-becomes-a-reported-failure discipline as the rest of the swarm.
SUBPROCESS_TIMEOUT_SEC = 120


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=SUBPROCESS_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            "command timed out after {}s: {}".format(
                SUBPROCESS_TIMEOUT_SEC, " ".join(cmd)
            )
        )
    except OSError as exc:
        raise RuntimeError("could not run {}: {}".format(cmd[0], exc))
    if check and proc.returncode != 0:
        raise RuntimeError(
            "command failed (exit {}): {}\n{}".format(
                proc.returncode,
                " ".join(cmd),
                (proc.stderr or proc.stdout or "").strip() or "no output",
            )
        )
    return proc


# bd prints a "nothing found" sentinel line for a clean audit (e.g.
# "No orphaned issues found", "No stale issues found (all active)"). The
# marker must be matched on a SENTINEL line, not anywhere in the output: a
# stale-bead row carries the bead's TITLE, which could itself contain the
# substring "no stale" / "all active" and would false-classify a real slip
# as clean. So: (1) the output must contain a sentinel marker AND (2) it must
# contain NO bead-id row. A bead id is the project prefix + suffix (e.g.
# "myproject-ab12", or a multi-segment prefix like "my-project-ab12"); its
# presence means the audit listed at least one bead.
_CLEAN_MARKERS = ("no orphan", "no stale", "all active")

# Matches a bead id token like "myproject-ab12" or "my-project-ab12" anywhere
# in a line. Generic over the project prefix: <word>-<...>-<alnum-suffix> with
# AT LEAST ONE hyphen (so a single-token prefix like "myproject-ab12" matches,
# not only multi-segment prefixes). Final segment must contain a digit so a
# plain hyphenated English phrase ("fast-path", "opt-in") does not false-match
# -- bead suffixes are alphanumeric and effectively always carry a digit.
_BEAD_ID_RE = re.compile(
    r"\b[a-z][a-z0-9]*(?:-[a-z0-9]+)*-[a-z0-9]*[0-9][a-z0-9]*\b", re.IGNORECASE
)


def _audit_is_clean(output: str) -> bool:
    lo = output.lower()
    if not any(marker in lo for marker in _CLEAN_MARKERS):
        return False
    # A sentinel phrase is present, but a listed stale/orphan bead row would
    # carry a bead id -- if any line has one, the audit is NOT clean.
    return not _BEAD_ID_RE.search(output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Beads closeout audits (orphans + stale) with pull/push."
    )
    parser.add_argument(
        "--stale-days",
        type=int,
        default=1,
        help="bd stale threshold in days (default 1, matching CLAUDE.md).",
    )
    args = parser.parse_args(argv)

    # Pull + the two audits must succeed before we have anything to report.
    try:
        _run(["bd", "dolt", "pull"])
        orphans = _run(["bd", "orphans"], check=False)
        stale = _run(
            ["bd", "stale", "--status", "in_progress",
             "-d", str(args.stale_days)],
            check=False,
        )
    except RuntimeError as exc:
        print("ERROR: {}".format(exc))
        return EXIT_FAIL

    # Print the captured audits BEFORE the final push. The push is a sync
    # convenience, not part of the report; a transient push failure must not
    # discard the orphans/stale data we already have (the script's whole
    # point is surfacing it).
    print("=== bd orphans ===")
    print(orphans.stdout.strip() or "(no output)")
    print("\n=== bd stale (in_progress > {}d) ===".format(args.stale_days))
    print(stale.stdout.strip() or "(no output)")

    # Final push keeps the local cache synced (the pull may have advanced the
    # working set); safe no-op if nothing changed. A failure here is reported
    # but does NOT discard the audit verdict already printed above.
    try:
        _run(["bd", "dolt", "push"])
    except RuntimeError as exc:
        print("\nWARNING: final `bd dolt push` failed (audit above is still "
              "valid): {}".format(exc))

    orphans_clean = _audit_is_clean(orphans.stdout)
    stale_clean = _audit_is_clean(stale.stdout)
    if orphans_clean and stale_clean:
        print("\nRESULT: CLEAN -- no lifecycle slips.")
        return EXIT_OK
    print(
        "\nRESULT: SLIP-FOUND -- triage the audits above "
        "(orphans -> close; stale -> transition per R3)."
    )
    return EXIT_SLIP_FOUND


if __name__ == "__main__":
    sys.exit(main())
