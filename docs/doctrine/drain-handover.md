# Drain / handover doctrine (R2)

*Last updated: 2026-06-12.*

How a long-running orchestrator session retires **cleanly** when it approaches
context-fill, instead of degrading turn-by-turn through repeated auto-compaction.
This is the R2 step of the harness-autonomy roadmap (bd
[`polyglot-pdf-h2r.2`](../../.beads/issues.jsonl), epic `polyglot-pdf-h2r`).
Plan of record: [`docs/sprint_1_harness-tuning_plan.md`](../sprint_1_harness-tuning_plan.md) (`R2`).

## Why

Claude Code auto-compacts the conversation when it nears the context window. Each
auto-compaction is lossy. A session that keeps claiming new beads across several
compactions accumulates compaction loss and burns tokens re-deriving its own
state. The cheaper, higher-quality move is to **stop claiming new work once the
session is clearly winding down**, finish (or cleanly split) what is already in
flight, and let a fresh successor session pick up **from the beads tracker** with
full context.

**The tracker IS the handoff.** There is no side-channel handover note, no parallel
handoff file -- beads already holds the durable state (done / ready / blocked, exit
criteria, dependencies), and the successor rehydrates from `bd ready` + `bd show`.
The drain protocol's whole job is to leave the **bead state clean and non-lossy**:
if the session is mid-bead when it drains, it **splits the bead** per the existing
lifecycle + SPEAR rules (close what shipped, file a new bead for the remainder)
rather than inventing a note. See [`workflow.md`](workflow.md#bead-lifecycle) and
[`planning.md`](planning.md).

The trigger is free: PreCompact already fires near context-fill and already runs a
hook (zero extra model turns). R2 gives that moment a job -- raise a **drain
flag** -- and surfaces the flag to the orchestrator on the very next turn.

## The mechanism (two hooks + a marker)

A single PreCompact hook cannot tell the orchestrator anything: **PreCompact
stdout is not injected into the model's context** (only a fixed set of hooks,
SessionStart among them, can inject `additionalContext`). So the signal is carried
by a durable marker file across two hooks, implemented by
[`scripts/drain_flag.py`](../../scripts/drain_flag.py):

1. **`PreCompact` (auto only) -> `drain_flag.py precompact`.** On an *auto*
   compaction it writes a session-scoped marker under `.beads/.runtime/`
   (gitignored; never source of truth). A *manual* `/compact` is a deliberate user
   action and never drains.
2. **post-compaction `SessionStart` (`source == "compact"`) ->
   `drain_flag.py sessionstart`.** It reads the marker and prints the documented
   `hookSpecificOutput.additionalContext` JSON, so the **first post-compaction
   orchestrator turn** sees the drain directive. The marker is consumed (deleted)
   so the directive surfaces exactly once.

A non-compact `SessionStart` (`startup` / `resume` / `clear`) is a *fresh* session:
it never drains, and it sweeps any stale marker so a leftover flag from a crashed
prior session cannot spuriously drain it. It surfaces **nothing** -- a fresh
session rehydrates from `bd ready` on its own (via the existing `bd_prime`
SessionStart hook); there is no note to inject.

Two undocumented-but-load-bearing assumptions are handled defensively (see the
module docstring): the PreCompact `trigger` field is corroborated by the hook's
`matcher: "auto"`; and because `session_id` stability across compaction is
undocumented, a marker is matched to the post-compaction SessionStart by
`session_id` **or** `transcript_path` (the transcript path is stable -- it is the
same conversation file).

## The protocol -- a bead-split decision tree (what the orchestrator does)

When a turn begins with the **DRAIN SIGNAL** directive in context, the
orchestrator **does NOT claim a new bead.** It runs the decision tree below. This
is **pure doctrine over existing `bd` mechanics** -- no new tooling. Every branch
rests on rules already in [`workflow.md`](workflow.md#bead-lifecycle) ("a bead never
spans PRs"; "any in-progress bead you stop without a PR in sight needs an explicit
state transition -- close / defer / drop the claim") and
[`planning.md`](planning.md) (exit criteria; MECE; epic-child vs standalone).

The goal of every branch is the same: **leave the tracker clean and non-lossy**, so
the successor's `bd ready` is a complete and accurate picture.

**Case A -- nothing in flight (between beads).** The common case. Do not claim the
next bead. Run normal end-of-session housekeeping
(`closeout_housekeeping.py` slip audits, final `bd dolt push`), ping the
maintainer, and **STOP**. The successor's `bd ready` already shows what is next.

**Case B -- the in-flight bead is nearly done.** If *finishing the whole bead* is
cheaper than splitting (a few more edits to reach a coherent, shippable state),
**finish it** -> `/closeout` -> ping -> **STOP**. Drain means "start no NEW work,"
not "abandon nearly-done work." Prefer this over a split whenever finishing is the
smaller move.

**Case C -- work is at a coherent, PR-able checkpoint, but the bead has real
remaining scope.** **Split the bead:**

1. **Rewrite the in-flight bead's `## Exit criteria`** to match *what was actually
   delivered*, and let this PR close it (`/closeout`). (Per
   [`planning.md`](planning.md), criteria describe what shipped; do not close
   against criteria you did not meet.)
2. **File a new bead for the remainder** -- an epic child if the original was under
   an epic (MECE with its siblings, inheriting >= 1 parent criterion), else a
   standalone ticket with its own 1-3 exit criteria. Give it its
   `metadata.surfaces`, and **carry the dependency edges forward** (anything that
   depended on the original now depends on the remainder). Use `bd_safe.py` /
   bracketed `bd create` (`bd_safe.py` has no `create` subcommand -- bracket the
   `bd create` with `bd dolt pull` / `push`).
3. **Ping, STOP.** The successor sees the remainder bead in `bd ready`.

**Case D -- work is half-edited / not coherent (no clean PR is possible).** First
try to reach a coherent checkpoint **cheaply** (finish the current function / get
the suite to green) -> then fall into Case B or C. If that is genuinely not
reachable:

1. **Commit the WIP to the branch** so nothing is lost to git.
2. **Split**: file the remainder bead whose body documents *exactly* what is
   done-on-branch vs. what remains, and **names the branch**. **Defer** the
   original bead (the explicit state transition for "stopped, no PR shipped") --
   do **not** close it (no PR closed it).
3. **Ping with the branch name + the remainder bead id, STOP.** The branch holds
   the code; the bead holds "where it stands + what is next." Non-lossy, and still
   entirely inside the tracker -- no side-channel file.

Spawning the successor automatically is **out of scope for R2** (left conceptual:
maximize autonomy and work-vs-burn efficiency under hard bounds; leaning
bounded-pool/budget; the 5-hour quota is the existing backstop). Revisit once the
A/B token curves exist.

## Settings wiring (maintainer-applied)

The orchestrator's auto-mode guard blocks self-edits to
[`.claude/settings.json`](../../.claude/settings.json), so the hook wiring below is
**applied by the maintainer** (or landed by the PR reviewer's agent). Two hook
additions, no allowlist change needed (hook commands run via the harness regardless
of the Bash allowlist, and the script has no orchestrator-invoked subcommand):

**`hooks.SessionStart`** -- add a third command after `bd_prime.py`:
```json
{ "type": "command", "command": "python scripts/drain_flag.py sessionstart" }
```

**`hooks.PreCompact`** -- add a SECOND matcher block (keep the existing
`bd_prime.py` one):
```json
{
  "matcher": "auto",
  "hooks": [
    { "type": "command", "command": "python scripts/drain_flag.py precompact" }
  ]
}
```

Until those land, the mechanism is dormant -- `drain_flag.py` and its tests prove
the behavior, but no drain fires until the hooks are wired.

## See also

- [`workflow.md`](workflow.md#session-start--end) -- session start/end cadence
  (drain is the auto-triggered end).
- The verified Claude Code hook facts (PreCompact stdout is not context-facing;
  SessionStart `source=compact` can inject `additionalContext`; the `trigger` /
  `session_id`-stability gaps) are recorded in the R2 journal entry under
  [`docs/journal/entries/`](../journal/entries/).
