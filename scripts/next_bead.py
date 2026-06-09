"""next_bead.py -- deterministic candidate surfacing + write-overlap guard.

The selection half of the R1 self-selection step (bd polyglot-pdf-h2r.1). It is
the `/next-bead` skill's zero-token engine: the skill makes the JUDGMENT call
(continue an epic vs. bundle nits vs. which of several safe candidates), and
this script makes the judgment SAFE by pre-computing, for every ready bead,
whether its declared change-surfaces collide with any active claim.

What it does
------------
  1. `bd dolt pull`                       -- freshest state (claims included).
  2. `bd ready --json`                    -- the ready candidates.
  3. active claims = in_progress beads that are ALSO backed by a live branch or
     open PR (the h2r.1 "active claim" definition; a stale in_progress bead with
     no live work does NOT block).
  4. For each candidate, prefix-aware overlap of its `metadata.surfaces` against
     the union of active-claim surfaces -> AVAILABLE or BLOCKED.
  5. Emit JSON: `{ "available": [...], "blocked": [...], "active_claims": [...] }`
     (and, by default, a short human summary on stderr).

The overlap math lives in bd_safe.py (the same logic the `claim` backstop uses),
so there is ONE definition of "surfaces collide" and the selection guard and the
claim guard can never disagree.

This script NEVER claims, edits, or merges. It only reports. The skill claims
(via `bd_safe.py claim`, which re-runs the guard as a backstop). Selection-only
is the safe first autonomy step (h2r.1: "touches only claiming, never merging").

Exit codes: 0 success (even if everything is blocked -- "nothing safe to pick"
is a valid, reportable answer); 1 a bd/git/gh command failed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Reuse bd_safe's surface-overlap + active-claim machinery so there is a single
# source of truth for "do these collide." Importing it also pulls its UTF-8
# stdout reconfigure. The path insert mirrors bd_safe's own (works whether run
# directly or imported by the test harness).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bd_safe  # noqa: E402

EXIT_OK = 0
EXIT_FAIL = 1


def _ready_candidates() -> list:
    """`bd ready --json` -> list of candidate bead dicts (id, title, ...)."""
    proc = bd_safe._run(["bd", "ready", "--json"], check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            "bd ready failed: {}".format(
                (proc.stderr or "").strip() or "no stderr"
            )
        )
    try:
        return json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError("bd ready returned unparseable JSON: {}".format(exc))


def _classify(candidates: list, active_ids: list) -> dict:
    """Split candidates into available vs blocked by surface-overlap.

    `active_ids` is the precomputed active-claim id list (so we query each
    claim's surfaces once, not once per candidate). A candidate is BLOCKED if
    its surfaces overlap ANY active claim's surfaces; the blocking claim id and
    the offending surface pair are recorded for the report.
    """
    # Cache each active claim's surfaces once. Active claims get PR-DERIVATION
    # (the _bead_surfaces default): a mid-flight claim that declared no surfaces
    # but has an open PR contributes its real diff footprint instead of blocking
    # everything as UNKNOWN (bd polyglot-pdf-8y7).
    claim_surfaces = {aid: bd_safe._bead_surfaces(aid) for aid in active_ids}

    available, blocked = [], []
    for cand in candidates:
        cand_id = cand.get("id")
        if not cand_id:
            continue
        # Candidates are READY beads (open, no open PR yet by definition), so PR
        # derivation would be ~50 wasted `gh` calls with nothing to find -- read
        # only their DECLARED surfaces.
        mine = bd_safe._bead_surfaces(cand_id, derive_from_prs=False)
        blockers = []
        for aid, theirs in claim_surfaces.items():
            if bd_safe._surfaces_overlap(mine, theirs):
                blockers.append({
                    "claim": aid,
                    "candidate_surfaces": mine or ["(none declared)"],
                    "claim_surfaces": theirs or ["(none declared)"],
                })
        row = {
            "id": cand_id,
            "title": cand.get("title", ""),
            "priority": cand.get("priority"),
            "surfaces": mine,
        }
        if blockers:
            row["blocked_by"] = blockers
            blocked.append(row)
        else:
            available.append(row)
    return {"available": available, "blocked": blocked}


def cmd_next(args: argparse.Namespace) -> int:
    stale_warning = None
    if not args.no_pull:
        try:
            bd_safe._dolt_pull()
        except Exception as exc:  # noqa: BLE001
            # On a remote container bd's dolt-native pull can fail/hang even though
            # the store was freshly hydrated over the proxy (bd polyglot-pdf-j47). A
            # failed pull must TAINT the output as possibly-stale, not abort the whole
            # engine -- otherwise /next-bead is unusable on remote. Freshness is still
            # checkable: the bootstrap stamps the loaded refs/dolt/data commit in
            # .beads/.cache/.hydrated.
            detail = (str(exc).strip().splitlines() or ["see logs"])[0]
            stale_warning = (
                "bd dolt pull failed ({}); candidates may be STALE -- verify the "
                "store is fresh (.beads/.cache/.hydrated stamps the loaded "
                "refs/dolt/data commit) before acting on this list.".format(detail)
            )

    candidates = _ready_candidates()
    # Active claims are independent of any single candidate, so compute once with
    # a sentinel exclude (no candidate is itself an active claim by definition --
    # ready beads are open, not in_progress).
    active_ids = bd_safe._active_claim_ids(exclude_id="")
    result = _classify(candidates, active_ids)
    result["active_claims"] = active_ids
    if stale_warning:
        result["stale_warning"] = stale_warning

    print(json.dumps(result, indent=2))

    if stale_warning:
        print("\nWARNING: {}".format(stale_warning), file=sys.stderr)
    if not args.quiet:
        avail, blk = result["available"], result["blocked"]
        print(
            "\n{} ready: {} AVAILABLE, {} BLOCKED by write-overlap "
            "({} active claim(s)).".format(
                len(avail) + len(blk), len(avail), len(blk), len(active_ids)
            ),
            file=sys.stderr,
        )
        for row in avail:
            print("  AVAILABLE {} -- {}".format(row["id"], row["title"]),
                  file=sys.stderr)
        for row in blk:
            who = ", ".join(b["claim"] for b in row["blocked_by"])
            print("  BLOCKED   {} -- overlaps {}".format(row["id"], who),
                  file=sys.stderr)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Surface ready beads + flag write-overlap with active claims."
    )
    parser.add_argument(
        "--no-pull",
        action="store_true",
        help="Skip the `bd dolt pull` (assume state is already fresh).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="JSON only on stdout; suppress the human summary on stderr.",
    )
    parser.set_defaults(func=cmd_next)
    return parser


def main(argv: list | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except RuntimeError as exc:
        print("ERROR: {}".format(exc))
        return EXIT_FAIL
    except KeyboardInterrupt:
        print("ERROR: interrupted.")
        return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
