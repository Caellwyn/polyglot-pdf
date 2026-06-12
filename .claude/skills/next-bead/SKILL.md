---
name: next-bead
description: Pick the next bead to work on -- safely. Runs the deterministic candidate engine (ready beads + a HARD change-surface write-overlap block against active claims), then you make the judgment call among the SAFE candidates (continue an epic vs. bundle small nits vs. priority) and claim it via bd_safe.py. Selection + claiming only; NEVER merges. Use at the START of a work session, or after closing a bead, before touching any file. Optional argument: a hint about what to prioritize (e.g. /next-bead finish the docs epic).
---

# Pick the next bead (self-selection + collision guard)

You are choosing what to work on next. This skill encodes the R1 self-selection
step (bd `polyglot-pdf-h2r.1`): a **deterministic engine** does the unsafe-to-
eyeball part (which ready beads would collide on writes with work already in
flight), and **you** do the judgment part (which of the safe candidates is the
right next move). It ends by **claiming** the chosen bead -- never by editing or
merging.

> **Why this exists.** Picking a bead from `bd ready` and going straight to
> editing -- without claiming -- is how two sessions end up doing the same work
> (the PR #65/#64 collision). Claiming alone isn't enough either: the same-bead
> claim check only fires once the other worker has a branch/PR. This skill adds
> the EARLIER guard -- comparing the files each bead will *modify* -- so an
> overlapping pick is refused before anyone edits. See
> [`docs/doctrine/workflow.md`](../../../docs/doctrine/workflow.md).

**The optional argument** (`$1`) is a prioritization hint, not a bead id -- e.g.
`/next-bead finish the harness epic` or `/next-bead something small`. Weigh it in
the judgment step; it never overrides the hard write-overlap block.

> **Repo layout (polyglot-pdf).** The Python interpreter is the backend venv in
> the MAIN repo (`backend/.venv`); worktrees have none, and **remote/web
> containers have no venv at all** -- so fall back to `python3`. Resolve it from
> anywhere via the git common dir and run the WORKTREE's own script copy:
> ```bash
> R="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"
> WT="$(git rev-parse --show-toplevel)"
> PY="$R/backend/.venv/Scripts/python.exe"; [ -x "$PY" ] || PY="$R/backend/.venv/bin/python"; [ -x "$PY" ] || PY=python3
> ```
> Shell state does NOT persist between tool calls -- prepend these in the SAME
> Bash call as the script.

## Step 1 -- Run the deterministic engine (zero-token)

```bash
R="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"; WT="$(git rev-parse --show-toplevel)"; PY="$R/backend/.venv/Scripts/python.exe"; [ -x "$PY" ] || PY="$R/backend/.venv/bin/python"; [ -x "$PY" ] || PY=python3; "$PY" "$WT/scripts/next_bead.py"
```

`next_bead.py` runs `bd dolt pull`, then emits JSON with three keys:

- **`available`** -- ready beads whose declared change-surfaces do NOT overlap
  any active claim. **These are the only beads you may pick.**
- **`blocked`** -- ready beads refused by the write-overlap guard, each with the
  `blocked_by` claim(s) and the offending surface pair. **Do not pick these**,
  and **do not override** -- two processes writing the same file is a conflict
  regardless of intent (h2r.1: no orchestrator override). If a blocked bead is
  genuinely the most important next thing, that means you should be *continuing
  the active claim that blocks it*, not starting a colliding second one.
- **`active_claims`** -- the in-progress beads (backed by a live branch/PR) the
  guard checked against.

The summary on stderr is the quick read; the JSON on stdout is authoritative.

**If `available` is empty:** every ready bead collides with active work (or there
are no ready beads). Do NOT force a pick. Either continue an existing active
claim, or report to the maintainer that there is no collision-free work to start
and stop.

## Step 2 -- The judgment call (yours)

Among the **`available`** candidates only, choose the next bead. This is the part
a script can't make -- weigh, in roughly this order:

1. **Epic continuation.** If you (or the current plan) are mid-epic and an
   available child continues it, prefer that -- coherent context beats
   context-switching. The `$1` hint often points here.
2. **Nit-bundling.** Several tiny available beads touching a shared, non-
   conflicting area can be **bundled into one cleanup PR** (the bead/PR contract
   allows one PR = several whole small beads). Prefer this over a full PR cycle
   per trivial bead. Only bundle beads whose surfaces don't conflict with each
   OTHER either (re-run the engine's logic in your head: disjoint surfaces).
3. **Priority + readiness.** Otherwise take the highest-priority available bead
   (`bd ready` is already priority-ordered; the engine preserves it).

State the choice and the one-line reason (which of the three above), per the
decide-and-note doctrine. This is a decide-it-yourself call -- do NOT escalate
*which* available bead to pick (CLAUDE.md "Escalation vs. autonomy", step 3).

> A note on what is NOT yours: if the only sensible next work is a **blocked**
> bead, or there is no available work and the plan itself is unclear on what to
> do, that can be a step-2 escalation (an ambiguous/untenable situation). But
> "which of several safe candidates" is always yours.

## Step 3 -- Set up the worktree + branch, then CLAIM

1. **Be on the right branch.** Claim from inside the bead's own worktree/branch
   (`<type>/<id-suffix>-<slug>`, cut off `origin/dev`) so the claim's collision
   checks correctly exclude your own branch. If you're bundling several beads,
   pick the primary bead's id for the branch.
2. **Claim via the safe wrapper** (it re-runs ALL three collision checks --
   PR, branch, and the surface guard -- as a backstop, then pull/claim/push):
   ```bash
   R="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"; WT="$(git rev-parse --show-toplevel)"; PY="$R/backend/.venv/Scripts/python.exe"; [ -x "$PY" ] || PY="$R/backend/.venv/bin/python"; [ -x "$PY" ] || PY=python3; "$PY" "$WT/scripts/bd_safe.py" claim <full-bead-id>
   ```
   - **Exit 0 `CLAIMED:`** -> proceed to the work.
   - **Exit 2 `ABORT`** -> a collision appeared between Step 1 and now (a race:
     another worker claimed in the gap). Do NOT re-claim or override. Go back to
     Step 1, re-run the engine, and pick a different available bead.
   - **Exit 1 `ERROR`** -> a tooling failure (bd/gh/git); surface it, don't guess.
3. **If you bundled multiple beads**, claim each one (same command per id). A
   later bead in the bundle that aborts means it's no longer safe to include --
   drop it from the bundle and continue with the rest.

## Step 4 -- Exit-criteria gate (the claim-time backstop), BEFORE any edit

A code-change bead must carry an **`## Exit criteria`** section in its body --
the contract for what "done" means. The norm is that the section is written at
**creation** time (see
[`workflow.md`](../../../docs/doctrine/workflow.md#bead-creation-requirements)); this
gate is the **backstop** that retrofits the legacy backlog lazily, so a bead that
slipped through without criteria gets them before any code is touched.

After a clean `CLAIMED:` and **before you edit any file:**

1. **Read the bead body** (`bd show <full-bead-id>`). Look for an
   `## Exit criteria` section.
2. **If it is present** -- nothing to do; proceed to the work. (For an epic
   child, confirm it names the >= 1 parent criterion it inherits.)
3. **If it is missing** -- derive **1-3 binary, testable criteria** from the
   bead's description (what does resolution look like; what would you read/run/
   observe to call it done) and **append them to the bead body** with a bracketed
   write BEFORE editing any file:
   ```bash
   bd dolt pull && bd update <full-bead-id> --description "<existing description>

   ## Exit criteria

   1. <binary, outcome-based criterion + how to verify>
   2. ...
   " && bd dolt push
   ```
   (Preserve the existing description -- append the section, don't overwrite it.
   `bd update --description` replaces the field, so include the prior text. If the
   bead is an epic child, inherit >= 1 parent criterion rather than inventing
   unrelated ones.)

Only after the bead has exit criteria do you start editing. Skipping this gate on
a criteria-less bead reintroduces the silent-scope-drift problem the rubric
exists to prevent.

> **Plan-traceability checkpoint (claim time).** As you read the bead body, note
> the plan it traces to -- the owning epic's `plan:` metadata pointer (`bd show
> <epic-id>`). As you work, any choice that commits to a *direction the plan
> neither states nor implies* is a step-2 escalation, not a decide-yourself call;
> implementation/structure/process choices stay yours (decide-by-default). This is
> the escalation **lens**, not a new gate -- full rule in
> [`planning.md`](../../../docs/doctrine/planning.md#plan-traceability) and CLAUDE.md
> "Escalation vs. autonomy" step 2.

When the work is done, ship it through **`/closeout`** (which closes the bead(s)
and pings the maintainer to merge -- this skill never merges).

## What this skill never does

- **Never merges** -- selection + claiming only (the safe first autonomy step).
- **Never overrides the write-overlap block** -- no flag, no judgment exception.
  (`bd_safe.py claim --no-surface-check` exists for a deliberate *maintainer*
  re-claim, not for the orchestrator to bypass the guard here.)
- **Never picks a `blocked` bead.**

## The change-surfaces contract (declare what you'll MODIFY)

The guard is only as good as the `surfaces` beads declare. A bead's
`metadata.surfaces` is a structured list of the files/dirs it will **MODIFY**
(not merely read -- reads don't collide). Conventions:

- **Declare at creation.** New beads should list their write targets when known.
  `--metadata` takes a full JSON object (it REPLACES the metadata), so include
  any other keys you're setting:
  `bd create ... --metadata '{"surfaces":["scripts/","docs/x.md"]}'`.
  To add surfaces to a bead that already has metadata, prefer reading the JSON,
  adding the key, and re-setting the whole object (or use `bd update
  --set-metadata` for scalar keys). Use forward slashes; a trailing slash
  (`scripts/`, `.claude/skills/`) means "this directory and anything under it"
  and is the right granularity when the exact files aren't known yet.
- **A bead with NO declared surfaces is treated as UNKNOWN** -- it conservatively
  collides with everything (it could touch anything), so it both blocks others
  and is blocked by any active claim. Declaring surfaces is what makes a bead
  schedulable alongside others.
- **"Change, not touch."** Files you only read do not belong in `surfaces`.
- If mid-work you discover you must modify a file outside your declared surfaces,
  update the bead's `surfaces` so a concurrent picker sees the real footprint.
