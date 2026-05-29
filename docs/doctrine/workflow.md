# Workflow doctrine: beads + the agent-swarm tooling

*Last updated: <DATE>.*

The load-bearing rules for how work moves through this project. Product-agnostic;
ported from the claude-swarm-kit. Adapt the specifics, keep the principles.

## Beads is the system of record

[Beads](https://github.com/steveyegge/beads) (`bd`) tracks everything that
outlives a conversation. Do NOT use ad-hoc TODO lists or markdown checklists for
durable work.

- **A new session resumes via `bd ready` / `bd show <id>`**, NOT by reopening a
  plan file and guessing where it left off. The plan is reference material the
  bead points at; in-flight state (ordering, done/blocked) lives in beads.
- **Step ordering lives in beads edges, not prose.** "Do A then B then C"
  becomes `bd dep add B A && bd dep add C B` so `bd ready` surfaces only A.
- **Pull before reads, push after every write:** `bd dolt pull && bd <write> && bd dolt push`.
  The local store is a cache; the remote is truth. Skipping the pull is the
  parallel-claim bug class (two workers claim the same bead because neither saw
  the other's claim). `scripts/bd_safe.py` brackets every write for you.
- **Dependency direction is easy to invert:** the FIRST arg to `bd dep add` is
  what gets BLOCKED. An epic is blocked BY its children, so `bd dep add <epic>
  <child>`. `bd_safe.py dep-add --epic/--child` makes this un-invertible.

## The swarm scripts (zero model tokens)

The kit ships four deterministic scripts so the model does not spend turns on
mechanical toil:

- **`bd_safe.py`** -- `claim`/`close`/`dep-add` with pull/push bracketing,
  collision checks (will not claim a bead another worker's branch/PR already
  carries; excludes your own current worktree branch), and direction-safe edges.
- **`copilot_watch.py <pr#>`** -- watches a PR for Copilot review COMPLETION and
  exits with a classified verdict (COMMENTS / CLEAN / ERROR / TIMEOUT). Run via
  the harness background mechanism so the agent is woken once with the result.
- **`closeout_housekeeping.py`** -- pull + `bd orphans` + `bd stale` + push;
  surfaces lifecycle slips (closed-in-commits-but-open, stale in-progress).
- **`journal_scaffold.py <bead-id>`** -- emits the journal-entry skeleton.

All four read project config (repo slug, bead prefix) from `swarm.config.json`.

## Bead lifecycle

- **One bead = one PR.** If mid-flight you discover a second PR worth of work,
  split the bead before opening PR #2.
- **Close the bead at PR handoff**, not at sprint-end.
- **Any in-progress bead you stop without a PR in sight needs an explicit state
  transition** before you walk away (close / defer / drop the claim).
- **Branch + PR carry the bead ID:** branch `<type>/<id-suffix>-<slug>`, PR title
  `<scope>(<context>): <summary> (bd <full-id>)`. The collision checks key on this.

## Session start / end

- **Start:** `bd dolt pull`, then `bd ready` + the slip audits (via
  `closeout_housekeeping.py`).
- **End:** file beads for remaining work, run quality gates, close finished
  beads, final `bd dolt push`, push the branch + open the PR. Work is not done
  until both `bd dolt push` and `git push` succeed.

## Worktree hazards (scar tissue)

- **Run every git command via `git -C "<worktree-abs-path>"`.** The shell cwd
  resets between tool calls; a chained `cd <main-repo> && git ...` operates on
  the MAIN checkout, silently landing commits on the wrong branch.
- **Never delete the worktree's own branch from inside it** -- it empties the
  working tree and strands the session. Leave merged worktrees/branches in place;
  sweep them in bulk from a separate checkout later.
