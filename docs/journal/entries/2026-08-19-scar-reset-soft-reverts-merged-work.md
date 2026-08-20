---
date: 2026-08-19
bead: none (direct maintainer request)
title: "fix(closeout): catch a squash that silently reverts merged work"
tags: [git, closeout, harness, testing, scar-tissue]
---

## Trigger

Maintainer, after I nearly reverted another session's merged work while
squashing two wip commits on bd polyglot-pdf-06u5o: *"is there a scar tissue
note we can leave to prevent this in the future? this would be a big problem."*

## The trap

`git reset --soft <branch-name>` moves the branch pointer to that commit while
keeping YOUR OLD TREE as the content. Every commit on the base your branch never
had gets rewound. The near-miss deleted the whole `kkos` static-bundle change
including a journal entry and a 135-line test file.

**It is not a stale-ref problem** -- which is what I documented first and had to
correct. The cause is resetting to anything that is not the branch's MERGE-BASE.
A fully current `origin/dev` does it just as readily; being behind the base is
the entire condition, and in a long-lived worktree you usually are. The original
incident WAS a reset against `origin/dev`, so my first rule would have prescribed
the command that caused it.

**Why every normal check misses it:** no error, a clean `git status`, a green
suite (the reverted work's tests are reverted with it), and a plausible file
list. The only tell was the stat line -- "11 files changed, 261 deletions" on a
change touching 4 files.

## What shipped

Three layers, because a doc note only helps if someone is reading the right doc
at the moment they type the command:

1. **CLAUDE.md scar #3** (tier-1, auto-loaded): reset to the merge-base, never a
   branch name. Folded into the existing worktree scar -- same class, a git
   command silently operating on something other than what you meant.
2. **`bd remember`** (repo-discoverable from any session or machine): mechanism,
   why the usual checks miss it, correct spellings, recovery procedure. It also
   records that its own first version was wrong.
3. **`closeout_prep`** flags it mechanically, NAMING the casualties rather than
   counting them -- a count does not tell you whose work is about to vanish.

## The detector: blob identity, arrived at by being wrong three times

- `--diff-filter=D` alone missed the commoner shape (the base EDITS an existing
  file rather than adding one).
- `--diff-filter=DM` caught that shape and fired on this very commit's own three
  intentional edits -- the cry-wolf failure that makes a warning worthless.
- I then claimed **no post-hoc signal could discriminate**, having tested four
  candidates. All four inspected commit TOPOLOGY, which the reset genuinely
  destroys. **Content does not.** A rewound file is byte-identical to an older
  version in the base's history; an edited file matches none of them.

The **ancestry gate** is load-bearing, but not for the reason I first wrote. It
is not about diff noise (the three-dot range already handles that) -- it
separates "this branch REVERTED their work" from "this branch is simply BEHIND
the base". Without it, two live worktrees false-positive.

## Seven review rounds, and what they were actually finding

The prevention rule stabilised at round 2. **Every round after that found an
error in my CLAIMS about the guard, not the guard itself:**

- **R3:** a documented "deliberate limit" that was not real.
- **R4:** the operand swap silently disabled the whole guard with 38 tests green;
  a rewound RENAME reported OK; and ~30s added to every closeout (one `rev-parse`
  spawn per revision -- 0.82s for just 20 of `backend/config.py`'s 129).
  Replaced with one `cat-file --batch-check` per file: 0.12s end-to-end.
- **R5:** the rename test **was never committed**. My squash ran `reset --soft`
  before staging it, so the commit message claimed 40 tests while the commit held
  38 -- a confident claim about state I had not verified, which is the same
  failure as the original incident.
- **R6:** `_git_in` copied `os.environ` wholesale, so an inherited `GIT_DIR`
  turned `git init` on the scratch dir into a no-op re-init of the AMBIENT repo.
  **A test suite whose subject is "do not silently mutate someone else's git
  history" was one env var from doing exactly that.** My first fix was also
  incomplete: it isolated the commands the TEST ran, while the code under test
  shells out through its own helper and inherits the environment regardless.
- **R7:** disputed one of two mutations I had called inert. Unresolved -- see
  below.

## The lesson that generalises

**"Measured" must mean "measured on this input", not "measured on two inputs and
generalised".** Three separate times I stated a conclusion more broadly than the
evidence supported: the false limit (R3), the wrong ancestry justification (R4),
and the "inert" claim (R7). Each time the code was fine and the description was
not -- and a comment that misdescribes a guard is how the guard gets deleted.

The second lesson: **a stub cannot see a command-line flag.** Four mutations
(`-z` on each diff, `--no-renames`, the operand order) passed a fully green suite
because every stub matched on `args[:3]` and returned a canned string. Only
real-repo tests pin those.

## Collateral damage, and its repair

An earlier revision of these tests -- before R6 fixed the isolation -- clobbered
the `nit-sweep-12` worktree, leaving it with 1 file instead of 3002.

Assessed rather than assumed: local `dev` is intact (identical to `origin/dev`,
all 3002 files); the reported junk commits on `dev` **do not exist**. Only that
one worktree was hit, its reflog shows a single entry ("Created from dev"), so it
had no commits and **no work was lost**. Reset to `origin/dev`; all 14 worktrees
swept for low file counts; the new guard reports clean everywhere.

## Unresolved, filed rather than forced

Round 7 reported that `rev-list base` -> `rev-list HEAD` diverges (both
false-positives and silent misses). I could not reproduce it in three
constructions, and the test I added does not catch the mutation. The shipped code
keeps `base` on the semantic argument -- the question is whether the branch
rewound to something the BASE held, so the branch's own history is not a
candidate set -- and the source comment says explicitly that this is reasoning,
not measurement, and that a reviewer disagrees. Filed for someone to settle with
a reproduction or a proof.

The cross-surface reviewer independently noted the trace supports keeping `base`:
the `commits[1:]` base-tip skip is only sound if `commits[0]` is deterministically
the base tip, which `rev-list <base>` guarantees and `rev-list HEAD` does not.

## Known limits, stated rather than glossed

- The check **also fires on a deliberate revert**, which is indistinguishable
  from outside. ATTENTION, not FAIL -- confirm intent; do not read a fire as
  proof of the trap.
- Two mutations remain deliberately unpinned (`len(commits) < 2`, and the
  disputed `rev-list` ref). The first is provably inert; the second is the filed
  disagreement.

## Follow-ups filed

`polyglot-pdf-rzran` (test-isolation pairing is not mechanically enforced -- a
future test can call `_git_in` and forget `clean_git_env`), `polyglot-pdf-aqjg2`
(the closeout skill's Step-0 triage list does not mention the two new ATTENTION
causes), plus the unresolved `rev-list` bead.

## The pre-commit hook, deliberately not shipped

A hook that catches this at the moment of harm is prototyped and works -- it sees
the trap in the index before the commit lands, so it catches reverted EDITS too.
It is not in this change: installing it affects all 14 worktrees including the
maintainer's other live sessions, which is their call to make when those are
idle.
