"""Harness cost telemetry: parse a session transcript -> per-session ledger row.

What this is
------------
A **deterministic, zero-model-token** script (plan §Change #1, bd
polyglot-pdf-hrn.1). It parses the Claude Code session transcript JSONL and
appends one row to ``docs/journal/harness_ledger.jsonl`` so the A/B harness
experiment has a real dataset instead of anecdote. Closeout calls it at the
end (Step 8.5). It spends no model tokens -- the orchestrator only passes the
handful of facts a script cannot read off the transcript (Copilot rounds,
maintainer touchpoints, etc.) as flags.

The orchestrator-vs-subagent split is the whole point
-----------------------------------------------------
Every assistant turn in the transcript carries ``message.usage`` (input /
output / cache tokens) and ``message.model``. Subagent turns are marked
``isSidechain: true``; orchestrator turns are ``false`` (or absent). That one
boolean is exactly the "where did an arm actually save" signal the experiment
needs -- arm B (fresh-eyes tiering) moves cost between the orchestrator and a
cheaper subagent model, so we bucket tokens by actor AND by model.

What the script reads vs. what the orchestrator supplies
--------------------------------------------------------
**Auto-parsed (mechanical, no judgment):**
  - token totals, split by actor (orchestrator / subagent) and by model;
  - the subagent models actually used (the arm-B / Haiku-escalation signal);
  - wall-clock span (first -> last transcript timestamp);
  - the session id.

**Supplied by the orchestrator as flags (judgment a script can't make):**
  - ``--bead`` (one or more bead ids this closeout resolves);
  - ``--arm`` (A / B / C / BC -- which experiment arm this session ran);
  - ``--cost-category`` (``production`` vs ``audit``: measurement / cross-arm
    bug-reporting work is bucketed ``audit`` and **never charged to the arm
    doing it**, per the plan's fairness rule);
  - ``--copilot-rounds``, ``--maintainer-touchpoints``, ``--deferred-nits``,
    ``--haiku-escalations``, ``--errors-shipped`` -- the babysitting / quality
    counters, all diagnostic numbers (NOT kill-switches).

Splitting tokens by review/triage/fix *phase* is left to an optional
``--phase-tokens`` JSON flag: the transcript has no machine-readable phase
boundary, so forcing the script to guess would be worse than letting the
orchestrator (which knows when it switched phases) pass the split when it has
it. Omitted -> the row records actor/model totals only.

Transcript discovery
--------------------
Claude Code stores transcripts at ``~/.claude/projects/<sanitized-cwd>/<uuid>.jsonl``
where ``<sanitized-cwd>`` is the process cwd with every non-alphanumeric
character replaced by ``-``. We derive that from ``os.getcwd()`` (which is the
worktree path at closeout time -- the transcript dir is keyed by the worktree
cwd, so this is worktree-correct) and pick the **most-recently-modified**
``*.jsonl`` in it. ``--transcript PATH`` overrides discovery (used by the
tests and any resumed-session edge case where the newest file is ambiguous).

Exit codes
----------
  0  row appended (or --dry-run printed it).
  1  could not find / parse a transcript, or a write failed. The closeout
     treats this as warn-only -- a missing ledger row must never block a
     merge -- but a non-zero code lets a human notice the telemetry gap.

Usage
-----
  python scripts/harness_ledger.py --bead polyglot-pdf-hrn.1 --arm A \\
      --cost-category production --copilot-rounds 1 --maintainer-touchpoints 1
  python scripts/harness_ledger.py --transcript path/to/session.jsonl --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

# Resolve the ledger path relative to THIS file, not the process cwd, so the
# script writes to the worktree's own docs/journal/ regardless of where it is
# invoked from (the worktree-safety lesson: a cwd-relative path silently
# targets the wrong checkout). Path(__file__) is scripts/harness_ledger.py, so
# parent.parent is the repo (worktree) root.
REPO_ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = REPO_ROOT / "docs" / "journal" / "harness_ledger.jsonl"
EXPERIMENT_STATE_PATH = REPO_ROOT / ".beads" / "experiment_state.json"

VALID_ARMS = ("A", "B", "C", "BC")
VALID_COST_CATEGORIES = ("production", "audit")


# --------------------------------------------------------------------------- #
# Transcript discovery
# --------------------------------------------------------------------------- #
def sanitize_cwd(cwd: str) -> str:
    """Return the Claude Code project-dir name for a working directory.

    Claude Code names the per-project transcript directory by replacing every
    non-alphanumeric character in the absolute cwd with ``-`` (so a Windows
    path ``C:\\Users\\me\\proj`` becomes ``C--Users-me-proj``). Verified
    against this repo's own transcript dir name at build time.
    """
    return re.sub(r"[^A-Za-z0-9]", "-", cwd)


def claude_projects_dir() -> Path:
    """Return ``~/.claude/projects`` (honoring CLAUDE_CONFIG_DIR if set)."""
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    base = Path(config_dir) if config_dir else Path.home() / ".claude"
    return base / "projects"


def discover_transcript(cwd: str | None = None) -> Path | None:
    """Find the current session's transcript JSONL, or None if not found.

    Derives ``~/.claude/projects/<sanitized-cwd>/`` and returns the
    most-recently-modified ``*.jsonl`` directly inside it. A resumed session
    can leave several JSONL files in the dir; the newest by mtime is the live
    one (the one closeout is running inside).
    """
    cwd = cwd or os.getcwd()
    project_dir = claude_projects_dir() / sanitize_cwd(cwd)
    if not project_dir.is_dir():
        return None
    candidates = [p for p in project_dir.glob("*.jsonl") if p.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


# --------------------------------------------------------------------------- #
# Transcript parsing
# --------------------------------------------------------------------------- #
def _iter_records(transcript: Path):
    """Yield parsed JSON objects from a transcript, skipping malformed lines.

    Transcripts are appended line-by-line; a crashed write can leave a final
    partial line. We skip unparseable lines rather than abort -- a single bad
    line must not cost the whole telemetry row.
    """
    with transcript.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def parse_transcript(transcript: Path) -> dict:
    """Parse a transcript into the mechanical (auto-derived) ledger fields.

    Returns a dict with:
      session_id              first non-empty sessionId seen
      first_ts / last_ts      ISO-8601 strings (transcript timestamps) or None
      tokens                  {orchestrator, subagent, total} each an
                              input/output/cache_read/cache_creation dict
      models                  {actor: {model: {input, output, ...}}}
      assistant_turns         {orchestrator: int, subagent: int}

    "Actor" is ``subagent`` when the record's ``isSidechain`` is true, else
    ``orchestrator``. Token counts come from ``message.usage`` on assistant
    records; we sum input/output/cache fields. Cache reads are tracked
    separately because they are billed differently and conflating them with
    fresh input would distort cross-arm cost comparison.
    """
    session_id: str | None = None
    first_ts: str | None = None
    last_ts: str | None = None

    def _zero() -> dict:
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        }

    tokens_by_actor: dict[str, dict] = {"orchestrator": _zero(), "subagent": _zero()}
    # models_by_actor[actor][model] -> token dict
    models_by_actor: dict[str, dict[str, dict]] = {
        "orchestrator": defaultdict(_zero),
        "subagent": defaultdict(_zero),
    }
    turns = {"orchestrator": 0, "subagent": 0}

    for rec in _iter_records(transcript):
        if session_id is None and rec.get("sessionId"):
            session_id = rec["sessionId"]
        ts = rec.get("timestamp")
        if ts:
            if first_ts is None:
                first_ts = ts
            last_ts = ts
        if rec.get("type") != "assistant":
            continue
        message = rec.get("message") or {}
        usage = message.get("usage") or {}
        if not usage:
            continue
        actor = "subagent" if rec.get("isSidechain") else "orchestrator"
        turns[actor] += 1
        model = message.get("model") or "unknown"
        for field in (
            "input_tokens",
            "output_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
        ):
            val = usage.get(field) or 0
            tokens_by_actor[actor][field] += val
            models_by_actor[actor][model][field] += val

    total = _zero()
    for actor_tokens in tokens_by_actor.values():
        for field, val in actor_tokens.items():
            total[field] += val

    # Convert the defaultdicts to plain dicts for clean JSON.
    models_plain = {
        actor: {model: dict(toks) for model, toks in by_model.items()}
        for actor, by_model in models_by_actor.items()
    }

    return {
        "session_id": session_id,
        "first_ts": first_ts,
        "last_ts": last_ts,
        "tokens": {
            "orchestrator": tokens_by_actor["orchestrator"],
            "subagent": tokens_by_actor["subagent"],
            "total": total,
        },
        "models": models_plain,
        "assistant_turns": turns,
    }


def subagent_models(parsed: dict) -> list[str]:
    """Return the distinct models used by subagents (the arm-B / Haiku signal).

    Arm B routes fresh-eyes to a cheaper model on small diffs; this list is
    how the later report sees which model a session's subagents actually ran
    on (and whether a Haiku self-escalation bumped one back to Sonnet).
    """
    return sorted(parsed.get("models", {}).get("subagent", {}).keys())


# --------------------------------------------------------------------------- #
# Row assembly + append
# --------------------------------------------------------------------------- #
def build_row(parsed: dict, args: argparse.Namespace, *, recorded_at: str) -> dict:
    """Assemble the ledger row from parsed transcript + orchestrator flags.

    ``recorded_at`` is passed in (not read from a clock) so callers/tests stay
    deterministic; closeout passes ``date -u +%Y-%m-%dT%H:%M:%SZ``.
    """
    phase_tokens = None
    if args.phase_tokens:
        try:
            phase_tokens = json.loads(args.phase_tokens)
        except json.JSONDecodeError as e:
            raise SystemExit(f"--phase-tokens is not valid JSON: {e}")

    return {
        "recorded_at": recorded_at,
        "session_id": parsed.get("session_id"),
        "beads": list(args.bead or []),
        "arm": args.arm,
        "cost_category": args.cost_category,
        "wall_clock": {
            "first_ts": parsed.get("first_ts"),
            "last_ts": parsed.get("last_ts"),
        },
        "tokens": parsed.get("tokens"),
        "models": parsed.get("models"),
        "subagent_models": subagent_models(parsed),
        "assistant_turns": parsed.get("assistant_turns"),
        "phase_tokens": phase_tokens,
        # Babysitting / quality counters -- diagnostic numbers, not gates.
        "copilot_rounds": args.copilot_rounds,
        "maintainer_touchpoints": args.maintainer_touchpoints,
        "deferred_nits": args.deferred_nits,
        "haiku_escalations": args.haiku_escalations,
        "errors_shipped": args.errors_shipped,
    }


def append_row(row: dict, ledger_path: Path = LEDGER_PATH) -> None:
    """Append one JSON row (newline-terminated) to the ledger, creating it."""
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------- #
# Experiment-state counter
# --------------------------------------------------------------------------- #
def load_experiment_state(path: Path = EXPERIMENT_STATE_PATH) -> dict:
    """Read the experiment-state counter, or a fresh zeroed state if absent."""
    default = {"baseline_A": 0, "arm_B": 0, "arm_C": 0, "arm_BC": 0, "phase": "A"}
    if not path.is_file():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default
    # Merge over the default so a hand-edited file missing a key still works.
    default.update({k: v for k, v in data.items() if k in default})
    return default


def phase_directive(state: dict) -> str:
    """Return the next-step directive string for the current counts.

    Thresholds are the plan's (§Change #1, "Experiment-state counter"):
      baseline_A <= 15            -> Phase A: run as-is, just measure.
      baseline_A > 15             -> Phase A done -- start B/C toggling.
      arm_B > 10 and arm_C > 10   -> arms done -- report; if both adopted, run BC.
      arm_BC > 10                 -> Combined arm done -- final report.
    Checked most-advanced-state-first (BC -> independent arms -> Phase A) so a
    session deep into the experiment gets its current directive, not an earlier
    phase's.
    """
    if state.get("arm_BC", 0) > 10:
        return "Combined arm done (arm_BC > 10) -- write the FINAL report."
    if state.get("arm_B", 0) > 10 and state.get("arm_C", 0) > 10:
        return (
            "Independent arms done (arm_B > 10 and arm_C > 10) -- report B vs C "
            "vs A; if BOTH B and C are adopted, run the combined BC arm."
        )
    if state.get("baseline_A", 0) > 15:
        return (
            "Phase A done (baseline_A > 15) -- start B/C toggling "
            "(CLAUDE_CODE_SUBAGENT_MODEL controls B; CLOSEOUT_LOOP_MODE controls C)."
        )
    return "Phase A (baseline): run as-is, just measure (baseline_A <= 15)."


def bump_experiment_state(arm: str | None, path: Path = EXPERIMENT_STATE_PATH) -> dict:
    """Increment the counter for ``arm`` and persist. Returns the new state.

    Arm -> counter key: A->baseline_A, B->arm_B, C->arm_C, BC->arm_BC. An
    unknown / missing arm leaves the counters untouched (we still rewrite the
    file so a brand-new run materializes it). ``phase`` is recomputed from the
    counts so the stored phase never drifts from the numbers.
    """
    state = load_experiment_state(path)
    key = {"A": "baseline_A", "B": "arm_B", "C": "arm_C", "BC": "arm_BC"}.get(arm or "")
    if key:
        state[key] = state.get(key, 0) + 1
    # Derive a coarse phase label from the counts (A -> B/C -> BC -> report).
    if state["arm_BC"] > 10:
        state["phase"] = "report"
    elif state["arm_B"] > 10 and state["arm_C"] > 10:
        state["phase"] = "BC"
    elif state["baseline_A"] > 15:
        state["phase"] = "BC-toggle"
    else:
        state["phase"] = "A"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return state


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--transcript",
        type=Path,
        help="Explicit transcript JSONL path. Default: auto-discover from cwd.",
    )
    p.add_argument(
        "--bead",
        action="append",
        metavar="ID",
        help="Bead id this closeout resolves (repeatable for bundled beads).",
    )
    p.add_argument(
        "--arm",
        choices=VALID_ARMS,
        help="Experiment arm this session ran (A/B/C/BC). Bumps the counter.",
    )
    p.add_argument(
        "--cost-category",
        choices=VALID_COST_CATEGORIES,
        default="production",
        help="production (default) or audit. Audit work is never charged to "
        "the arm doing it (plan fairness rule).",
    )
    p.add_argument("--copilot-rounds", type=int, default=None)
    p.add_argument("--maintainer-touchpoints", type=int, default=None)
    p.add_argument("--deferred-nits", type=int, default=None)
    p.add_argument("--haiku-escalations", type=int, default=None)
    p.add_argument("--errors-shipped", type=int, default=None)
    p.add_argument(
        "--phase-tokens",
        metavar="JSON",
        help='Optional JSON mapping phase->token dict, e.g. \'{"review": {...}}\'.',
    )
    p.add_argument(
        "--recorded-at",
        default=None,
        help="ISO-8601 stamp for the row (default: derived UTC now). Closeout "
        "passes date -u +%%Y-%%m-%%dT%%H:%%M:%%SZ so the row time is UTC and "
        "deterministic across machines.",
    )
    p.add_argument(
        "--no-counter",
        action="store_true",
        help="Do not bump .beads/experiment_state.json (e.g. audit re-runs).",
    )
    p.add_argument(
        "--print-directive",
        action="store_true",
        help="Print the current phase directive and exit (no row, no bump).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse + assemble the row and print it, but do not append or bump.",
    )
    return p


def _recorded_at(args: argparse.Namespace) -> str:
    """Return the row stamp. Prefer the passed value; else derive UTC now.

    We allow a derived fallback (unlike the doc-freshness script's strict
    no-clock rule) because this row is a telemetry record, not a comparison
    input -- a slightly machine-local stamp never changes a verdict. Closeout
    still passes an explicit UTC stamp for cross-machine consistency.
    """
    if args.recorded_at:
        return args.recorded_at
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.print_directive:
        # Pass the module-level path explicitly so a test (or a runtime
        # reassignment of EXPERIMENT_STATE_PATH) is honored -- the function's
        # default arg is bound at def-time and would ignore a monkeypatch.
        print(phase_directive(load_experiment_state(EXPERIMENT_STATE_PATH)))
        return 0

    transcript = args.transcript or discover_transcript()
    if transcript is None:
        sys.stderr.write(
            "harness_ledger.py: could not locate a transcript JSONL for this "
            "session (looked in ~/.claude/projects/<sanitized-cwd>/). Pass "
            "--transcript PATH explicitly. Skipping telemetry row.\n"
        )
        return 1
    if not transcript.is_file():
        sys.stderr.write(f"harness_ledger.py: transcript not found: {transcript}\n")
        return 1

    try:
        parsed = parse_transcript(transcript)
    except OSError as e:
        sys.stderr.write(f"harness_ledger.py: could not read transcript: {e}\n")
        return 1

    row = build_row(parsed, args, recorded_at=_recorded_at(args))

    if args.dry_run:
        print(json.dumps(row, indent=2, ensure_ascii=False))
        print("\n[dry-run] not appended; counter not bumped.", file=sys.stderr)
        return 0

    # Pass module-level paths explicitly (not via the functions' def-time
    # default args) so a monkeypatched LEDGER_PATH / EXPERIMENT_STATE_PATH is
    # honored in tests and any runtime reassignment.
    try:
        append_row(row, LEDGER_PATH)
    except OSError as e:
        sys.stderr.write(f"harness_ledger.py: failed to append ledger row: {e}\n")
        return 1

    # Display the ledger path relative to the repo when it lives under it;
    # fall back to the absolute path otherwise (e.g. a test's tmp dir).
    try:
        ledger_display = LEDGER_PATH.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        ledger_display = str(LEDGER_PATH)

    if not args.no_counter:
        # The counter's whole purpose is arm-attributed accumulation, so a
        # bump without --arm is almost always a closeout that forgot the flag
        # (the row also lands with arm=null). Warn loudly but don't hard-fail:
        # an intentional no-arm bump is rare but legitimate, and a telemetry
        # row must never block the merge. --no-counter is the explicit
        # "I meant to skip the bump" path and is silent.
        if not args.arm:
            sys.stderr.write(
                "harness_ledger.py: WARNING -- no --arm given; the row records "
                "arm=null and the experiment counter is NOT bumped. Pass "
                "--arm A|B|C|BC (or --no-counter if this is deliberate).\n"
            )
        state = bump_experiment_state(args.arm, EXPERIMENT_STATE_PATH)
        print(f"Ledger row appended to {ledger_display}")
        print(f"Experiment state: {json.dumps(state)}")
        print(f"Directive: {phase_directive(state)}")
    else:
        print(f"Ledger row appended to {ledger_display} (counter not bumped).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
