---
date: 2026-09-16
bead: polyglot-pdf-prskq
title: "docs(claude): document manual Windows PATH setup needed for native bd.exe resolution"
tags: [harness, conventions]
---

## Trigger

Filed by the fresh-eyes reviewer during the closeout of bd polyglot-pdf-6peeg
(PR #810). That bead removed the tracked `env.PATH` override from
`.claude/settings.json` because no single literal is correct on both Windows
and POSIX, and replaced it with an entry in the maintainer's own persistent
Windows user PATH.

The reviewer's point: that replacement is MACHINE state, captured nowhere in
the repo. A fresh Windows contributor -- or the maintainer on a new machine --
gets no native `bd.exe` resolution, silently falls back to npm's POSIX-shell
shim, and reinstates the focus-stealing console-window cascade that bd
polyglot-pdf-rdftu (PR #806) fixed.

## What shipped

A new `### 2. Windows: put the native bd.exe ahead of npm's shim` section in
[`docs/beads-setup.md`](../../beads-setup.md), under the existing "Per-machine
(once per computer)" heading -- the doc that already owns one-time Windows
prerequisites (long paths, the maintainer role), so a contributor doing setup
meets it in sequence rather than having to know to look.

It covers, in order: **who it applies to** (npm installs only -- a
directly-installed release binary has no shim, called out twice so a
non-npm reader skips it); **why it matters** (npm puts `bd`, `bd.cmd` and
`bd.ps1` in `%APPDATA%\npm\` and that directory goes on PATH, while the
package's own `bin\` holding the real `bd.exe` does not, so a bare `bd` from
Git Bash hits the `#!/bin/sh` script and Windows launches `sh.exe` to run it);
**the fix** (a PowerShell block that resolves the directory from
`$env:APPDATA`, refuses if `bd.exe` is absent, backs up the existing user PATH
to the Desktop, and is idempotent via a `-notlike` guard); **how to verify**
(`where bd` in a NEW terminal, first line must end in
`\@beads\bd\bin\bd.exe`, with the failure mode named); and **why it cannot
live in the repo** (the separator problem from 6peeg, plus the pointer to
`tests/test_claude_settings_env.py` that keeps machine paths out of the shared
settings).

It also records that Python callers need nothing -- `scripts/swarm_config.py`
already prepends the same directory at import time -- so the reader knows the
step is specifically about *shell* callers (the skills and hooks that run bare
`bd`) and does not go looking for a second Python-side fix.

Renumbered the following section (long-path prerequisites 2 -> 3, maintainer
role 3 -> 4); the file had no external cross-references to the old numbering
(checked `docs/`, `.claude/`, `CLAUDE.md`).

**Every claim was verified against the live machine or the cited file rather
than written from memory:** `$env:APPDATA` resolves to the real bin dir and
`bd.exe` is present there; the `-notlike` guard correctly reports the entry as
already installed, so a re-run is a no-op; `where bd` returns the exe as its
first line; `scripts/swarm_config.py` does derive from `expanduser("~")`, guard
on the file existing, and join with `os.pathsep`; npm does ship exactly the
three launchers named; and `tests/test_claude_settings_env.py` exists with the
guards described.

## Lessons

**A fix that lives in machine state is not finished until the repo says so.**
6peeg's change was correct -- the shared config genuinely could not express a
platform-specific PATH -- but "correct" moved the requirement somewhere no
clone can see. The reviewer catching that is the difference between a fix that
holds for one machine and one that holds for the project. When a fix's
replacement is *outside* the repo, the deliverable includes writing it down.

**Doc instructions are code you have not run.** Every command in this section
was executed against the real environment before shipping -- the path
resolution, the idempotence guard, and the `where bd` verification. A setup doc
whose commands were only reasoned about is exactly the kind that fails for the
next person, and the cost of checking was under a minute.

## Doc freshness

`docs/beads-setup.md` is the doc this bead edits; its `*Last updated:*` stamp
is bumped to 2026-09-16 with a pointer to this entry. It carries no
`**Tracks:**` line, so the freshness checker does not compare it against code
commit times -- which is correct for a setup doc that tracks an external
install shape rather than a code path.

The convention and code-citation checks both report clean. No other tier-1/2
doc makes a claim this change contradicts: `scripts/swarm_config.py`'s own
comment already describes the Python-side prepend, and this section cites it
rather than restating it.

## Files touched

- `docs/beads-setup.md` -- new per-machine section 2 (native `bd.exe` ahead of
  npm's shim, with rationale, verification, and why it cannot be repo state);
  following sections renumbered 3 and 4; `*Last updated:*` stamp bumped with a
  pointer to this entry.
