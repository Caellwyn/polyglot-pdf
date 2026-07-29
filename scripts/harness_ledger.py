"""Harness cost telemetry: parse a session transcript -> per-session ledger row.

What this is
------------
A **deterministic, zero-model-token** script (plan section Change #1, bd
polyglot-pdf-hrn.1). It parses the Claude Code session transcript JSONL and
writes one JSON file to ``docs/journal/telemetry/`` so the A/B harness
experiment has a real dataset instead of anecdote. Each closeout gets its own
file (named by timestamp + session prefix), so parallel PRs never conflict on
GitHub. Closeout writes the row via closeout_finish.py (Step 6); the standalone
call documented at Step 7 is the hand-run fallback. It spends no model tokens --
the orchestrator only passes the handful of facts a script cannot read off the
transcript (Copilot rounds, maintainer touchpoints, etc.) as flags.

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

# Resolve paths relative to THIS file, not the process cwd, so the script
# writes to the worktree's own docs/journal/ regardless of where it is invoked
# from (the worktree-safety lesson: a cwd-relative path silently targets the
# wrong checkout). Path(__file__) is scripts/harness_ledger.py, so
# parent.parent is the repo (worktree) root.
REPO_ROOT = Path(__file__).resolve().parent.parent
TELEMETRY_DIR = REPO_ROOT / "docs" / "journal" / "telemetry"
# Legacy path kept for backwards-compat reads; new writes go to TELEMETRY_DIR.
LEDGER_PATH = REPO_ROOT / "docs" / "journal" / "harness_ledger.jsonl"
EXPERIMENT_STATE_PATH = REPO_ROOT / ".beads" / "experiment_state.json"
# Committed sentinel dropped when the FINAL report is written (bd polyglot-pdf-hrn.17).
# The arm counter is derived by counting rows, and rows are never deleted, so the
# arm_BC>10 "write the report" directive would otherwise fire on every future
# closeout forever. When this file exists in TELEMETRY_DIR, phase_directive
# short-circuits to a terminal "experiment closed" message. Delete it to re-open
# the experiment. Kept as a bare filename (not a frozen path) so a monkeypatched
# TELEMETRY_DIR in tests is honored -- the path is derived at call time.
REPORT_DONE_FILENAME = "REPORT_DONE"

VALID_ARMS = ("A", "B", "C", "BC")
VALID_COST_CATEGORIES = ("production", "audit")


# --------------------------------------------------------------------------- #
# Cost computation (bd polyglot-pdf-cb6i)
# --------------------------------------------------------------------------- #
# Per-million-token base rates (USD), keyed by model-id PREFIX so a dated id like
# "claude-haiku-4-5-20251001" resolves to the "claude-haiku-4-5" entry. Source:
# the claude-api skill (shared/models.md), 2026-07-28. Update here if prices
# drift; re-verify via /claude-api.
#
# Sonnet 5 is priced at the STANDARD $3.00/$15.00, and that is what billing
# actually charges -- VERIFIED against live `claude -p` calls on 2026-07-28,
# which reconcile to an implied input rate of $3.0000/MTok to four decimals.
# The docs advertise an introductory $2.00/$10.00 through 2026-08-31, but it is
# NOT being applied to this account, so do NOT "correct" this row down to the
# intro rate: that would introduce a ~33% under-report, the same silent
# under-costing this table exists to prevent. Re-probe before changing it.
MODEL_PRICES_PER_MTOK = {
    "claude-opus-5": {"input": 5.00, "output": 25.00},
    "claude-sonnet-5": {"input": 3.00, "output": 15.00},
    "claude-opus-4-8": {"input": 5.00, "output": 25.00},
    "claude-opus-4-7": {"input": 5.00, "output": 25.00},
    "claude-opus-4-6": {"input": 5.00, "output": 25.00},
    # Opus/Sonnet 4.5 are still active models; include them so a session still on
    # those ids is priced, not silently dropped to $0 as unpriced (Codex PR #261).
    "claude-opus-4-5": {"input": 5.00, "output": 25.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    "claude-fable-5": {"input": 10.00, "output": 50.00},
}

# Prompt-cache multipliers applied to the BASE INPUT rate (shared/prompt-caching.md):
#   read  -> 0.1x; write -> 1.25x at 5-minute TTL, 2.0x at 1-hour TTL.
#
# Transcript records DO carry the TTL split, in `usage.cache_creation`
# (`ephemeral_1h_input_tokens` / `ephemeral_5m_input_tokens`), so we price each
# bucket at its own multiplier instead of assuming one global TTL (bd
# polyglot-pdf-aefl). MEASURED 2026-07-28 across 1,480 usage-bearing records in
# the three most recent sessions: 26,512,214 cache-creation tokens, ALL of them
# ephemeral_1h and zero ephemeral_5m -- the previous flat 1.25x assumption
# under-reported every one of them by 37.5%.
#
# Legacy fallback: a record with the flat `cache_creation_input_tokens` but no
# `cache_creation` breakdown (older transcript layout) is bucketed to 5m, which
# preserves the historical pricing of already-written rows rather than silently
# re-pricing them upward. compute_cost reports which happened via
# `cache_write_ttl_source`.
CACHE_READ_MULTIPLIER = 0.1
CACHE_WRITE_MULTIPLIER_5M = 1.25   # 5-minute TTL
CACHE_WRITE_MULTIPLIER_1H = 2.0    # 1-hour TTL (what Claude Code actually uses)
# Back-compat alias: some callers/tests referenced the old single constant.
CACHE_WRITE_MULTIPLIER = CACHE_WRITE_MULTIPLIER_5M


def _price_for_model(model_id: str) -> dict | None:
    """Resolve a model id to its {input, output} per-MTok rate by longest-prefix
    match (so a dated id resolves to its family). Returns None if unknown."""
    if not model_id:
        return None
    # Longest matching prefix wins (defensive; the keys don't currently overlap).
    best = None
    for prefix, rate in MODEL_PRICES_PER_MTOK.items():
        if model_id.startswith(prefix) and (best is None or len(prefix) > len(best[0])):
            best = (prefix, rate)
    return best[1] if best else None


def _split_cache_writes(counts: dict) -> tuple[int, int, int]:
    """Split cache-creation tokens into (measured_1h, measured_5m, assumed_5m).

    The first two come from the per-TTL fields parsed off `usage.cache_creation`
    -- i.e. the transcript stated the TTL. The third is any flat
    `cache_creation_input_tokens` those buckets do not account for: a legacy
    record with no breakdown, or a TTL kind we do not model yet. It is priced at
    the 5m rate, preserving the historical pricing of rows written before the
    split existed rather than silently re-pricing them upward.

    Returning the assumed bucket SEPARATELY (rather than folded into 5m) is what
    lets compute_cost label a session honestly -- see its ttl_source block.

    Every bucket is clamped at 0. Token counts off the wire are never negative,
    but a hand-built or future-schema row could be -- and an unclamped negative
    would both blend the effective rate and surface as a negative token count in
    the reported diagnostic, rather than being contained here.

    The assumed bucket is taken from `cache_creation_assumed_input_tokens` when
    present, because parse_transcript computes it PER RECORD (bd
    polyglot-pdf-9qf2). Deriving it here by subtracting aggregates is wrong:
    records are not uniform -- some carry a breakdown with a zero flat field --
    so on a model mixing those with a genuinely legacy record, the subtraction
    cancels the legacy tokens to zero and prices them at $0 while reporting
    "measured". The subtraction survives only as a fallback for hand-built
    counts dicts (tests, callers) that never saw parse_transcript.
    """
    flat = max(0, counts.get("cache_creation_input_tokens", 0) or 0)
    m_1h = max(0, counts.get("cache_creation_1h_input_tokens", 0) or 0)
    m_5m = max(0, counts.get("cache_creation_5m_input_tokens", 0) or 0)
    if "cache_creation_assumed_input_tokens" in counts:
        assumed = max(0, counts.get("cache_creation_assumed_input_tokens") or 0)
    else:
        assumed = max(0, flat - (m_1h + m_5m))
    return m_1h, m_5m, assumed


def _cost_for_counts(counts: dict, rate: dict) -> float:
    """USD cost for one model's token counts at the given {input, output} rate.

    counts keys: input_tokens (uncached remainder), output_tokens,
    cache_read_input_tokens (priced at 0.1x input), and cache-creation tokens
    priced per TTL bucket -- 1h at 2.0x input, 5m at 1.25x (see
    _split_cache_writes for the legacy fallback).
    """
    in_rate = rate["input"] / 1_000_000
    out_rate = rate["output"] / 1_000_000
    inp = counts.get("input_tokens", 0) or 0
    out = counts.get("output_tokens", 0) or 0
    cache_read = counts.get("cache_read_input_tokens", 0) or 0
    write_1h, write_5m, write_assumed = _split_cache_writes(counts)
    return (
        inp * in_rate
        + out * out_rate
        + cache_read * in_rate * CACHE_READ_MULTIPLIER
        + write_1h * in_rate * CACHE_WRITE_MULTIPLIER_1H
        + (write_5m + write_assumed) * in_rate * CACHE_WRITE_MULTIPLIER_5M
    )


def compute_cost(models: dict | None) -> dict:
    """Turn the per-(actor, model) token breakdown into a USD cost block that
    mirrors the `tokens`/`models` structure: per-model + per-actor + total, plus
    a list of any unpriced model ids (warn-only -- an unknown model contributes
    $0 and is flagged, never crashes).

    `models` shape (from parse_transcript): {actor: {model_id: {<token counts>}}}.

    NOTE on the `cache_write_tokens_*` fields: they describe the whole
    TRANSCRIPT, including models absent from MODEL_PRICES_PER_MTOK (those wrote
    the tokens even though they contribute $0 and are listed in
    `unpriced_models`). So they can EXCEED the tokens reflected in `total`, and
    cross-multiplying them by the cache multipliers will not reconcile to
    `total` whenever `unpriced_models` is non-empty -- measured at 52% of
    cache-write tokens on one real transcript. Check `unpriced_models` first.
    """
    out = {"orchestrator": {}, "subagent": {}, "by_model": {}, "unpriced_models": []}
    actor_totals = {"orchestrator": 0.0, "subagent": 0.0}
    by_model: dict = {}
    unpriced: set = set()
    # Cache-write buckets, accumulated from the SAME per-model split that prices
    # them, so the reported ttl_source can never disagree with what was charged.
    measured_1h = measured_5m = assumed_5m = 0

    for actor in ("orchestrator", "subagent"):
        for model_id, counts in ((models or {}).get(actor) or {}).items():
            # Defend the warn-only promise against a malformed/None counts dict
            # (parse_transcript never produces this, but a hand-crafted or
            # future-schema row might) -- treat it as zero rather than raising.
            if not isinstance(counts, dict):
                counts = {}
            # Accumulate the cache-write buckets for EVERY model, priced or not:
            # an unpriced model still wrote cache tokens, and the diagnostic
            # describes the transcript, not just the billable part of it.
            m1h, m5m, a5m = _split_cache_writes(counts)
            measured_1h += m1h
            measured_5m += m5m
            assumed_5m += a5m
            rate = _price_for_model(model_id)
            if rate is None:
                unpriced.add(model_id)
                cost = 0.0
            else:
                cost = _cost_for_counts(counts, rate)
            out[actor][model_id] = round(cost, 6)
            actor_totals[actor] += cost
            by_model[model_id] = round(by_model.get(model_id, 0.0) + cost, 6)

    out["by_model"] = by_model
    out["orchestrator_total"] = round(actor_totals["orchestrator"], 6)
    out["subagent_total"] = round(actor_totals["subagent"], 6)
    out["total"] = round(actor_totals["orchestrator"] + actor_totals["subagent"], 6)
    out["unpriced_models"] = sorted(unpriced)

    # Report what the cache writes ACTUALLY were rather than a fixed assumption
    # (bd polyglot-pdf-aefl). "measured" means every cache-write token came from
    # the usage.cache_creation TTL breakdown; "assumed-5m" means none did and the
    # legacy fallback priced them all at 1.25x; "mixed" means both happened.
    #
    # These totals are accumulated from the SAME per-model _split_cache_writes
    # calls that did the pricing (see the loop above), never re-derived from
    # global sums. Re-deriving globally is wrong in two ways that both mislabel
    # real transcripts: one model's measured tokens cancel another's assumed
    # ones, and a record with a breakdown but a zero flat field (93 such records
    # / 1.1M tokens observed in one live session) reads as "no cache writes at
    # all" on a real, non-zero cost.
    if measured_1h == 0 and assumed_5m == 0 and measured_5m == 0:
        ttl_source = "none"          # genuinely no cache writes
    elif assumed_5m == 0:
        ttl_source = "measured"      # every write token came from a breakdown
    elif measured_1h == 0 and measured_5m == 0:
        ttl_source = "assumed-5m"    # wholly legacy transcript
    else:
        ttl_source = "mixed"
    out["cache_write_ttl_source"] = ttl_source
    out["cache_write_tokens_1h"] = measured_1h
    out["cache_write_tokens_5m"] = measured_5m + assumed_5m
    # Split out so a reader can tell a measured 5m write from a fallback guess.
    out["cache_write_tokens_5m_assumed"] = assumed_5m
    return out


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


def discover_subagent_transcripts(transcript: Path) -> list[Path]:
    """Find the spawned-subagent sidecar transcripts for a main transcript.

    A spawned subagent (e.g. fresh-eyes, an Agent/Task call) does NOT write its
    turns into the main session JSONL as ``isSidechain`` rows -- it writes its OWN
    transcript under a ``subagents/`` directory keyed by the main transcript's stem:

        ~/.claude/projects/<sanitized-cwd>/<session-uuid>.jsonl          (main)
        ~/.claude/projects/<sanitized-cwd>/<session-uuid>/subagents/agent-<id>.jsonl

    So the main transcript alone has zero subagent tokens (bd polyglot-pdf-17k);
    the per-actor split needs these sidecars folded in. The sidecar records DO
    carry ``isSidechain: true``, so once their lines are read the existing actor
    bucketing files them under ``subagent`` automatically. Returns the sidecar
    paths (empty list if the dir is absent -- a session with no spawned subagents).
    """
    subagents_dir = transcript.with_suffix("") / "subagents"
    if not subagents_dir.is_dir():
        return []
    return sorted(p for p in subagents_dir.glob("agent-*.jsonl") if p.is_file())


# --------------------------------------------------------------------------- #
# Transcript parsing
# --------------------------------------------------------------------------- #
def _iter_records(path: Path):
    """Yield parsed JSON objects from a JSONL file, skipping malformed lines.

    Used for BOTH the session transcript and the telemetry ledger -- each is
    appended line-by-line, and a crashed write can leave a final partial line.
    We skip unparseable lines rather than abort -- a single bad line must not
    cost the whole telemetry row (or the whole derived count).
    """
    with path.open(encoding="utf-8", errors="replace") as f:
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

    Spawned-subagent tokens are read from the ``subagents/agent-*.jsonl`` sidecars
    next to the main transcript (bd polyglot-pdf-17k) -- the main JSONL has no
    subagent rows, so without the sidecars the ``subagent`` bucket reads 0. The
    sidecar rows carry ``isSidechain: true``, so they bucket as ``subagent`` via the
    same actor rule. Sidecar ``sessionId``/``timestamp`` are ignored for the
    session id and wall-clock span -- those stay anchored to the MAIN transcript so
    a subagent's own session id / a late-finishing subagent does not redefine them.
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
            # Per-TTL split of the line above, read off usage.cache_creation
            # (bd polyglot-pdf-aefl). These are a BREAKDOWN of
            # cache_creation_input_tokens, not additional tokens -- never sum
            # them with it. Absent on legacy records, which leaves them 0 and
            # sends the flat count down the assumed-5m fallback.
            "cache_creation_1h_input_tokens": 0,
            "cache_creation_5m_input_tokens": 0,
            # Per-record unattributed remainder (legacy records with no
            # breakdown). Computed at parse time, NOT by subtracting aggregates
            # -- see the note at the accumulation site (bd polyglot-pdf-9qf2).
            "cache_creation_assumed_input_tokens": 0,
        }

    tokens_by_actor: dict[str, dict] = {"orchestrator": _zero(), "subagent": _zero()}
    # models_by_actor[actor][model] -> token dict
    models_by_actor: dict[str, dict[str, dict]] = {
        "orchestrator": defaultdict(_zero),
        "subagent": defaultdict(_zero),
    }
    turns = {"orchestrator": 0, "subagent": 0}

    def _accumulate(rec: dict, *, anchor_meta: bool, force_actor: str | None = None) -> None:
        """Fold one record's tokens into the actor buckets.

        ``anchor_meta`` true (the MAIN transcript only) also advances the session id
        + wall-clock span; sidecar files pass false so a subagent's own session id /
        timestamps never redefine them.

        ``force_actor`` pins the bucket regardless of the record's ``isSidechain``
        flag. Sidecar files pass ``"subagent"``: a record in
        ``subagents/agent-*.jsonl`` IS a subagent turn by definition, so it must not
        leak into the orchestrator bucket even on the (unobserved) chance a sidecar
        assistant row lacks the flag. Main-transcript records pass None and bucket by
        the flag as before."""
        nonlocal session_id, first_ts, last_ts
        if anchor_meta:
            if session_id is None and rec.get("sessionId"):
                session_id = rec["sessionId"]
            ts = rec.get("timestamp")
            if ts:
                if first_ts is None:
                    first_ts = ts
                last_ts = ts
        if rec.get("type") != "assistant":
            return
        message = rec.get("message") or {}
        usage = message.get("usage") or {}
        if not usage:
            return
        actor = force_actor or ("subagent" if rec.get("isSidechain") else "orchestrator")
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

        # Per-TTL cache-write split (bd polyglot-pdf-aefl). Newer records carry
        # usage.cache_creation = {ephemeral_1h_input_tokens, ephemeral_5m_...};
        # older ones omit it entirely.
        #
        # The unattributed remainder is computed HERE, per record, while this
        # record's own flat count and breakdown are still paired -- NOT later by
        # subtracting aggregates (bd polyglot-pdf-9qf2). Records are not uniform:
        # some carry a breakdown with a ZERO flat field (93 such records / 1.1M
        # tokens in one live session), and when those aggregate alongside a
        # genuinely legacy record on the same model, an aggregate-level
        # subtraction cancels the legacy tokens to zero -- pricing them at $0 and
        # reporting "measured". Bucketing per record makes that impossible.
        #
        # The remainder is anchored on the LARGER of the flat count and the
        # breakdown's own total, so a TTL kind we do not model yet still gets
        # priced (bd polyglot-pdf-41c1). Anchoring on the flat field alone drops
        # such tokens to $0 whenever the flat field is also 0 -- and a non-zero
        # breakdown beside a zero flat field is a real shape, not a hypothetical
        # (167 such records in the local corpus). An unknown kind is charged at
        # the conservative 5m rate and surfaces as "assumed-5m"/"mixed" rather
        # than vanishing while the block claims there were no cache writes.
        cache_creation = usage.get("cache_creation")
        flat_cc = max(0, usage.get("cache_creation_input_tokens") or 0)
        rec_1h = rec_5m = other_cc = 0
        if isinstance(cache_creation, dict):
            rec_1h = max(0, cache_creation.get("ephemeral_1h_input_tokens") or 0)
            rec_5m = max(0, cache_creation.get("ephemeral_5m_input_tokens") or 0)
            for key, val in cache_creation.items():
                if key in ("ephemeral_1h_input_tokens", "ephemeral_5m_input_tokens"):
                    continue
                # Match by KEY MEANING, not just value type (bd
                # polyglot-pdf-dxgj). Summing every numeric member would charge
                # any future non-token sibling as cache-write tokens -- a
                # `ttl_seconds: 3600` would overcharge 3.25x. That is not
                # speculative schema-shape: `usage.server_tool_use` already
                # carries non-token integer counts (web_search_requests /
                # web_fetch_requests). Only `*_input_tokens` members are tokens.
                # Note the failure directions differ: missing a real token kind
                # under-reports, while charging a non-token key over-reports --
                # so this guard is deliberately narrow. It matches the
                # `ephemeral_<ttl>_input_tokens` shape the two known kinds use,
                # NOT a bare `*_input_tokens` suffix: a summary member such as
                # `total_input_tokens` would pass the looser test and be charged
                # a second time on top of the buckets it summarizes.
                if not (key.startswith("ephemeral_") and key.endswith("_input_tokens")):
                    continue
                if isinstance(val, (int, float)) and not isinstance(val, bool):
                    other_cc += max(0, int(val))
        rec_assumed = max(0, max(flat_cc, rec_1h + rec_5m + other_cc) - (rec_1h + rec_5m))
        for dst, val in (
            ("cache_creation_1h_input_tokens", rec_1h),
            ("cache_creation_5m_input_tokens", rec_5m),
            ("cache_creation_assumed_input_tokens", rec_assumed),
        ):
            tokens_by_actor[actor][dst] += val
            models_by_actor[actor][model][dst] += val

    for rec in _iter_records(transcript):
        _accumulate(rec, anchor_meta=True)
    # Fold in spawned-subagent sidecar transcripts (bd polyglot-pdf-17k). Sidecar
    # records are force-bucketed to "subagent" (a row in subagents/ IS a subagent
    # turn); meta stays anchored to main. This assumes the MAIN transcript holds NO
    # copy of the sidecar rows -- empirically the main JSONL has zero isSidechain
    # rows when subagents are spawned (the subagent's turns live only in the
    # sidecar), so there is no double-count. If a future Claude Code layout wrote a
    # subagent's turns into BOTH places, this would over-count and need a dedup by
    # record uuid.
    for sidecar in discover_subagent_transcripts(transcript):
        for rec in _iter_records(sidecar):
            _accumulate(rec, anchor_meta=False, force_actor="subagent")

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
    deterministic; closeout passes ``date -u +%Y-%m-%dT%H:%M:%SZ`` (the explicit
    form -- ``%F``/``%T`` are GNU-only).
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
        # USD cost derived from the per-model token counts (bd polyglot-pdf-cb6i).
        "cost_usd": compute_cost(parsed.get("models")),
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


def _row_filename(row: dict) -> str:
    """Return the filename for a per-row telemetry file.

    Format: ``<recorded_at_hyphens>-<session_id_prefix8>.json``
    Colons are replaced with hyphens because NTFS forbids colons in filenames.
    """
    ts = (row.get("recorded_at") or "0000-00-00T00-00-00Z").replace(":", "-")
    sid = (row.get("session_id") or "unknown")[:8]
    return "{}-{}.json".format(ts, sid)


def append_row(row: dict, telemetry_dir: Path = TELEMETRY_DIR) -> Path:
    """Write one JSON file to telemetry_dir and return its path.

    Each row gets a uniquely-named file (<timestamp>-<session_prefix>.json) so
    parallel PRs never touch the same path and GitHub merges them trivially --
    no .gitattributes union driver needed for server-side merges.
    """
    telemetry_dir.mkdir(parents=True, exist_ok=True)
    dest = telemetry_dir / _row_filename(row)
    dest.write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return dest


def _row_key(row: dict) -> tuple:
    """Return a dedup key for a telemetry row: (recorded_at, session_id).

    Used by _iter_all_rows to avoid counting a row twice when it appears in
    both the per-file dir (new) and the legacy JSONL (old), which can happen
    during the migration window when both sources coexist.
    """
    return (row.get("recorded_at") or "", row.get("session_id") or "")


def _iter_all_rows(
    telemetry_dir: Path = TELEMETRY_DIR,
    legacy_path: Path = LEDGER_PATH,
):
    """Yield all rows from the new per-file dir and the legacy JSONL.

    Scans telemetry_dir/*.json (sorted for determinism) then reads the legacy
    harness_ledger.jsonl, skipping any row whose (recorded_at, session_id) key
    was already yielded from the per-file dir. This handles three cases:
    1. Pure new-style (telemetry dir populated, JSONL empty/absent): dir only.
    2. Pure legacy (dir absent/empty): JSONL only.
    3. Migration window (dir AND JSONL have rows): dir for all migrated rows;
       JSONL for any NEW rows appended by pre-migration branches still in flight.
    """
    seen: set = set()
    if telemetry_dir.is_dir():
        for p in sorted(telemetry_dir.glob("*.json")):
            try:
                row = json.loads(p.read_text(encoding="utf-8", errors="replace"))
            except (json.JSONDecodeError, OSError):
                continue
            seen.add(_row_key(row))
            yield row
    if legacy_path.is_file():
        for row in _iter_records(legacy_path):
            if _row_key(row) not in seen:
                yield row


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


def phase_directive(state: dict, sentinel: Path | None = None) -> str:
    """Return the next-step directive string for the current counts.

    Thresholds are the plan's (section Change #1, "Experiment-state counter"):
      baseline_A <= 15            -> Phase A: run as-is, just measure.
      baseline_A > 15             -> Phase A done -- start B/C toggling.
      arm_B > 10 and arm_C > 10   -> arms done -- report; if both adopted, run BC.
      arm_BC > 10                 -> Combined arm done -- final report.
    Checked most-advanced-state-first (BC -> independent arms -> Phase A) so a
    session deep into the experiment gets its current directive, not an earlier
    phase's.

    Once the FINAL report is written the REPORT_DONE sentinel exists; because the
    counter is derived by counting (never-deleted) rows, arm_BC>10 would nag the
    write-the-report directive on every future closeout otherwise. The sentinel
    short-circuits to a terminal "experiment closed" line (bd polyglot-pdf-hrn.17).
    ``sentinel`` defaults to ``TELEMETRY_DIR/REPORT_DONE`` derived at call time so a
    monkeypatched TELEMETRY_DIR (tests) is honored rather than a frozen import-time path.
    """
    if sentinel is None:
        sentinel = TELEMETRY_DIR / REPORT_DONE_FILENAME
    if sentinel.is_file():
        return (
            "Harness A/B experiment CLOSED -- see "
            "docs/journal/telemetry/FINAL_REPORT.md. Arm B+C adopted as the "
            "standing default; no per-closeout experiment action. (Delete "
            "docs/journal/telemetry/REPORT_DONE to re-open.)"
        )
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


_ARM_TO_KEY = {"A": "baseline_A", "B": "arm_B", "C": "arm_C", "BC": "arm_BC"}


def derive_experiment_state(
    ledger_path: Path = LEDGER_PATH,
    telemetry_dir: Path = TELEMETRY_DIR,
) -> dict:
    """Recompute the experiment-state counter by COUNTING all rows by arm.

    Reads both the new per-file telemetry dir and the legacy JSONL (via
    _iter_all_rows) so pre-migration rows still count. baseline_A = #rows with
    arm=="A", arm_B = #"B", arm_C = #"C", arm_BC = #"BC". Rows with a null /
    unknown arm count toward nothing. ``phase`` is derived from the counts so it
    never drifts from the numbers.
    """
    state = {"baseline_A": 0, "arm_B": 0, "arm_C": 0, "arm_BC": 0, "phase": "A"}
    for row in _iter_all_rows(telemetry_dir, ledger_path):
        key = _ARM_TO_KEY.get(row.get("arm") or "")
        if key:
            state[key] += 1
    # Derive a coarse phase label from the counts (A -> B/C -> BC -> report).
    if state["arm_BC"] > 10:
        state["phase"] = "report"
    elif state["arm_B"] > 10 and state["arm_C"] > 10:
        state["phase"] = "BC"
    elif state["baseline_A"] > 15:
        state["phase"] = "BC-toggle"
    else:
        state["phase"] = "A"
    return state


def refresh_experiment_state(
    ledger_path: Path = LEDGER_PATH,
    state_path: Path = EXPERIMENT_STATE_PATH,
    telemetry_dir: Path = TELEMETRY_DIR,
) -> dict:
    """Re-derive the counter from all rows and write the local cache file.

    Returns the derived state. The cache file (``.beads/experiment_state.json``)
    is gitignored -- it is a convenience view for humans / ``cat``, NOT a
    source of truth and never committed, so it can never collide on a merge.
    Call this AFTER appending the row so the new row is counted.
    """
    state = derive_experiment_state(ledger_path, telemetry_dir)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
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
        help="Experiment arm this session ran (A/B/C/BC). Recorded on the row; "
        "the counter is derived by counting rows per arm.",
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
        help="Skip refreshing the gitignored .beads/experiment_state.json cache. "
        "Counts come from the ledger regardless, so this is cosmetic.",
    )
    p.add_argument(
        "--print-directive",
        action="store_true",
        help="Print the current phase directive (derived from the ledger) and "
        "exit -- writes nothing.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse + assemble the row and print it, but do not append it or "
        "refresh the cache.",
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
        # Derive from all rows (new dir + legacy JSONL) on demand (not the cache
        # file) so it works even with the gitignored cache absent. Pass paths
        # explicitly so a test's monkeypatched values are honored.
        print(phase_directive(derive_experiment_state(LEDGER_PATH, TELEMETRY_DIR)))
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
        print("\n[dry-run] not appended; cache not refreshed.", file=sys.stderr)
        return 0

    # Pass module-level paths explicitly (not via the functions' def-time
    # default args) so a monkeypatched TELEMETRY_DIR / LEDGER_PATH is honored
    # in tests and any runtime reassignment.
    try:
        dest = append_row(row, TELEMETRY_DIR)
    except OSError as e:
        sys.stderr.write(f"harness_ledger.py: failed to write telemetry file: {e}\n")
        return 1

    # Emit the repo-relative path so closeout_finish.py can capture it and
    # stage exactly that file (no glob, no git add -A).
    try:
        dest_display = dest.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        dest_display = dest.as_posix()
    print(f"TELEMETRY_FILE: {dest_display}")

    if not args.no_counter:
        # The counter is arm-attributed accumulation, so a run without --arm is
        # almost always a closeout that forgot the flag (the row also lands with
        # arm=null and contributes to no arm's count). Warn loudly but don't
        # hard-fail: an intentional no-arm run is rare but legitimate, and a
        # telemetry row must never block the merge. --no-counter is the explicit
        # "skip refreshing the cache" path and is silent. The COUNTS come from
        # all rows regardless of this flag -- refresh only rewrites the
        # gitignored local cache.
        if not args.arm:
            sys.stderr.write(
                "harness_ledger.py: WARNING -- no --arm given; the row records "
                "arm=null and contributes to no arm's count. Pass "
                "--arm A|B|C|BC (or --no-counter to skip the cache refresh).\n"
            )
        state = refresh_experiment_state(LEDGER_PATH, EXPERIMENT_STATE_PATH, TELEMETRY_DIR)
        print(f"Experiment state: {json.dumps(state)}")
        print(f"Directive: {phase_directive(state)}")
    else:
        print(f"Telemetry file written (cache not refreshed).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
