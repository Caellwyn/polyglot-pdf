# Workflow doctrine: beads + the agent-swarm tooling

*Last updated: 2026-06-11.*

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
- **Claim before you edit.** After picking a bead, run `bd_safe.py claim <id>`
  BEFORE touching any file. Its collision checks (below) refuse a bead another
  worker already owns. Skipping the claim is what causes duplicate-work
  collisions even when the pull cadence is followed.
- **Dependency direction is easy to invert:** the FIRST arg to `bd dep add` is
  what gets BLOCKED. Epic wiring is a different edge type: bd rejects a
  task-blocks-epic blocks edge, so epic-child is `bd dep add <child> <epic>
  -t parent-child`. `bd_safe.py dep-add --epic/--child` emits that form and
  makes it un-invertible; `--blocked/--prereq` covers plain blocks edges.

## Self-selection + the change-surface collision guard

Selecting the next bead is a JUDGMENT call (continue an epic vs. bundle small
nits vs. priority) made SAFE by a deterministic write-overlap guard. The
`/next-bead` skill is the front door; `scripts/next_bead.py` is its engine.

- **Every bead declares its change-surfaces** -- a structured `metadata.surfaces`
  list of the files/dirs it will **MODIFY** (not read; reads don't collide).
  Declare at creation -- `--metadata` takes a full JSON object, e.g.
  `bd create ... --metadata '{"surfaces":["scripts/","docs/x.md"]}'` -- and via
  the spawn convention. A trailing slash (`scripts/`, `.claude/skills/`) means
  "this directory and anything nested under it." **Only positively-stated,
  actually-overlapping surfaces block** (bd polyglot-pdf-6hr): a bead with no
  declared surfaces (UNKNOWN -- unannotated, or a tooling-failure read) does NOT
  collide, so one undeclared in-progress bead can't freeze the whole board.
  Declaring surfaces is still worthwhile -- it lets the guard PROVE a genuine
  overlap and block it -- but the absence of a declaration is permissive, not
  fail-closed. For an active claim that under-declared, the guard still derives
  its real footprint from its open PR first (bd polyglot-pdf-8y7).
- **`/next-bead` surfaces ready candidates and HARD-blocks write-overlaps.**
  `next_bead.py` cross-references each ready bead's surfaces against every ACTIVE
  claim (in_progress AND backed by a live branch/PR -- a stale claim does not
  block) and splits them into `available` vs `blocked`. **There is no
  orchestrator override:** two processes writing the same file is a conflict
  regardless of intent. You pick only from `available`. Selection + claiming
  only -- `/next-bead` never merges.
- **Three collision checks gate every claim** (`bd_safe.py claim`): (1) an OPEN
  PR whose TITLE carries the id; (2) a foreign branch carrying the id-suffix;
  (3) **change-surface overlap** with an active claim. Checks 1-2 catch a
  collision only AFTER a branch/PR exists; check 3 catches it at claim time.
  `--no-surface-check` drops only check 3 (a deliberate maintainer re-claim).

## The swarm scripts (zero model tokens)

The kit ships four deterministic scripts so the model does not spend turns on
mechanical toil:

- **`bd_safe.py`** -- `claim`/`close`/`dep-add` with pull/push bracketing,
  collision checks (will not claim a bead another worker's branch/PR already
  carries; excludes your own current worktree branch), and direction-safe edges.
- **`pr_review_watcher.py <pr#>` (RETIRED)** -- watched a PR for an external bot
  review's completion (Copilot, then Codex). It is now dead path: review is
  entirely Claude-based (an Opus-5 outer review run as orchestrator-driven
  subagents, read directly -- see [`review-flow.md`](review-flow.md)), so the
  closeout flow no longer launches this watcher. Retained only as inert history.
- **`closeout_housekeeping.py`** -- pull + `bd orphans` + `bd stale` + push;
  surfaces lifecycle slips (closed-in-commits-but-open, stale in-progress).
- **`journal_scaffold.py <bead-id>`** -- emits the journal-entry skeleton.

All four read project config (repo slug, bead prefix) from `swarm.config.json`.

## Bead creation requirements

Every code-change bead carries an **`## Exit criteria`** section in its **body**
-- the contract for what "done" means, written so any later agent (or reviewer)
can score it. See [`planning.md`](planning.md) for the full rubric doctrine; the
creation-time mechanics:

- **In the body, not metadata JSON.** Exit criteria live as a greppable
  `## Exit criteria` markdown section in the bead description, NOT as a
  `metadata` key. They must be readable with `bd show <id>` and `grep`.
- **1-3 binary, testable criteria** stating what resolution looks like -- e.g.
  "microphone streams seamlessly across breakpoint crossings and overlay
  switches." Binary (PASS/FAIL), outcome-based, with an implicit or explicit
  verify step.
- **Written at CREATION time -- the norm.** The creator has the observational
  context to state what success looks like; **filing a code-change bead without
  exit criteria is an incomplete filing.** Write them when you file.
- **Claim-time gate is the backstop.** The legacy ~250-bead backlog retrofits
  lazily: `/next-bead` checks at claim time and writes criteria for any bead that
  slipped through without them (see that skill's claim-time gate step). The gate
  catches slipped filings; it does not replace the creation-time norm.
- **Epic children inherit; standalone tickets get their own.** A child bead's
  `## Exit criteria` names the >= 1 parent criterion it is on the hook for; a
  standalone ticket writes its own 1-3 (a ticket whose work clusters into more
  than ~3 distinct criteria is a signal to split it -- see `planning.md`).
- **Translate to tests where feasible** -- a criterion that can be a test should
  be (test-first encouraged); the test is then the verify step.
- **Mechanical validation is deliberately DEFERRED.** There is intentionally no
  `validate_bead_body.py` gate yet -- convention first. If you observe drift
  (beads filed without criteria faster than the claim-time gate catches them),
  file a follow-up bead to add mechanical validation; do not build it pre-emptively.

## Bead lifecycle

- **A bead never spans PRs; a PR closes at least one bead.** One bead = exactly
  one PR. If mid-flight you discover a second PR worth of work, split the bead
  before opening PR #2. A PR **may** bundle several whole beads when each is too
  small to warrant its own PR cycle (a separate cycle per tiny bead wastes review
  resources) -- closeout then closes all of them. Every PR closes at least one
  bead (never zero).
- **Close the bead(s) at PR handoff**, not at sprint-end.
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
- **Auto-triggered end (drain):** when a long session auto-compacts near
  context-fill, a drain directive is surfaced post-compaction; the orchestrator
  **finishes or splits** its in-flight bead (close what shipped, file a new bead
  for the remainder -- the tracker is the handoff, no side-channel note) and stops
  claiming new work. See [`drain-handover.md`](drain-handover.md).

## Worktree hazards (scar tissue)

- **Run every git command via `git -C "<worktree-abs-path>"`.** The shell cwd
  resets between tool calls; a chained `cd <main-repo> && git ...` operates on
  the MAIN checkout, silently landing commits on the wrong branch.
- **Never delete the worktree's own branch from inside it** -- it empties the
  working tree and strands the session. Leave merged worktrees/branches in place;
  sweep them in bulk from a separate checkout later.
