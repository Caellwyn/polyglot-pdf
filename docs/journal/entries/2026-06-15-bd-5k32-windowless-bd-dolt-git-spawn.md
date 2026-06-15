---
date: 2026-06-15
bead: polyglot-pdf-5k32
title: "infra: spawn bd/dolt/git windowless on Windows to kill the git.exe console-window storm"
tags: [harness, hotfix]
---

## Trigger

The maintainer reported an intermittent Windows problem: while code agents
work, "dozens of terminal windows" sometimes appear at once and grind the
desktop to a halt. It was correlated with subagents that interact with the
beads tracker. Filed as bd polyglot-pdf-5k32 (P3, observed twice on 2026-06-11,
sometimes also failing with "Not enough memory resources are available").

## What shipped

Root cause: the beads tracker syncs through a *git-backed* Dolt remote
(`origin = git+https://github.com/Caellwyn/polyglot-pdf.git`). On `bd dolt
push`/`pull`, Dolt periodically does a noms storage "conjoin" and, because the
remote is git-backed, shells out to `git.exe` once per data chunk (`git
cat-file -s <hash>`). Each console-subsystem grandchild in the
`bd.exe -> dolt.exe -> git.exe` tree pops its own visible console window on
Windows, and a conjoin fires dozens at once -- the storm. It is intermittent
because only the chunk-heavy conjoin triggers it, not every sync.

The window-spawners are third-party Go/Node binaries we cannot patch. But the
top of the process tree -- Python launching `bd` -- is ours. The fix spawns
that top process with the Windows `CREATE_NO_WINDOW` flag: a process created
that way has no console, and its `dolt`/`git.exe` descendants inherit "no
console" and allocate no window. The storm is suppressed at the root without
touching any third-party binary.

Concretely:
- New shared helper `swarm_config.windowless_creationflags()` -- returns
  `subprocess.CREATE_NO_WINDOW` on win32 (via `getattr`, so a surprise build
  degrades to 0 rather than crashing), else `0`. `creationflags=0` is an
  accepted, ignored kwarg on POSIX, so the same call site is a cross-platform
  no-op off Windows (verified).
- Applied at every agent-path `bd`/`dolt`/`git` spawn: the `_run`/`subprocess.run`
  of `bd_safe.py`, `closeout_housekeeping.py`, `closeout_finish.py`,
  `bd_prime.py` (3 sites -- the SessionStart hook), and `journal_scaffold.py`.
- Inlined the same win32 check into `beads_remote_bootstrap.py`'s `run()` helper
  (via `kw.setdefault`, so a caller's explicit creationflags still wins) rather
  than importing `swarm_config` -- the bootstrap must stay standalone (it can run
  before `scripts/` is importable).
- Regression test `test_run_passes_windowless_creationflags` pins that `_run`
  forwards the flag (using a sentinel value so the assertion is meaningful on CI
  Linux, where the real value is 0).

Verified end-to-end: a real `bd dolt push` (the conjoin trigger) now spawns with
`creationflags=0x8000000` (`CREATE_NO_WINDOW`) and exits 0; the full touched-
script suite is green (154 tests at fix time; 349 at closeout prep).

Decisions made and why mine to make (defended in the merge ping):
- **Window suppression over the bead's other two candidates** (migrating to a
  native DoltHub/sql-server remote, or scheduled `dolt gc`). Suppression is the
  contained, zero-new-dependency fix. A remote migration is a new
  operational/cost dependency -- a step-2 escalation -- and `gc` only reduces
  frequency rather than removing the windows. The remote migration remains the
  bigger lever if the maintainer ever wants to kill the conjoin entirely; not in
  this bead's scope.
- **`CREATE_NO_WINDOW` over `DETACHED_PROCESS`**: the callers capture
  stdout/stderr via pipes; `CREATE_NO_WINDOW` suppresses the window without
  disturbing those pipes, `DETACHED_PROCESS` is more aggressive and risks them.
- **Six scripts patched, not just the two that call `bd dolt` directly**: every
  agent-path `bd` spawn now carries the flag so no path is left to pop a stray
  window. Same one-line, no-op-off-Windows change each.

## Lessons

A git-backed Dolt remote turns every sync into per-chunk `git.exe` shell-outs;
on Windows that is a console-window generator. When you cannot patch the process
that spawns console children, `CREATE_NO_WINDOW` on the nearest *ancestor you
control* suppresses the whole subtree, because "no console" is inherited
downward. Recorded as bd memory `windows-git-window-storm-fix` for
repo-discoverability.

## Doc freshness

- Bumped `docs/components/beads-remote-bootstrap.md` (`Tracks:`
  `beads_remote_bootstrap.py` + `bd_prime.py`, both edited here) to 2026-06-15
  with a review note: the scripts gained a `creationflags=` arg but no bootstrap
  behavior the doc describes changed. Trimmed the doc's inline historical
  lineage tail to current-state-only per the doc-maintenance convention.
- Three other docs were flagged STALE by the freshness checker
  (`context-compression.md`, `tool-call-flow.md`, `confirmation-and-audit.md`),
  but they track `backend/services/*` files this branch did NOT touch -- their
  staleness predates this PR (other branches' 2026-06-13 work). Left as-is.

## Files touched

- `scripts/swarm_config.py` -- new `windowless_creationflags()` helper.
- `scripts/bd_safe.py` -- `_run` forwards the flag.
- `scripts/closeout_housekeeping.py` -- `_run` forwards the flag (dropped a now-used `noqa: F401`).
- `scripts/closeout_finish.py` -- `_run` forwards the flag.
- `scripts/bd_prime.py` -- 3 spawn sites forward the flag (dropped `noqa: F401`).
- `scripts/journal_scaffold.py` -- `bd show` spawn forwards the flag.
- `scripts/beads_remote_bootstrap.py` -- `run()` defaults to the win32 flag.
- `tests/test_bd_safe.py` -- regression test for flag forwarding.
- `docs/components/beads-remote-bootstrap.md` -- freshness bump + review note.
