---
date: 2026-09-15
bead: polyglot-pdf-rdftu
title: "infra: closeout spawns 263 visible git.exe console windows (cascade)"
tags: [harness, performance, testing]
---

## Trigger

The maintainer reported terminal windows opening and closing with no visible
work in them, sometimes escalating into a runaway cascade that had to be
manually stopped -- and, by the end of the session, a machine that was "almost
unusable" with windows actively stealing keyboard focus mid-typing.

The initial guess in the report was "maybe the bead code itself." That turned
out to be one of three separate mechanisms, and not the one that mattered most.

## What shipped

Three distinct causes were found. Two are fixed here; the third was
misdiagnosed twice before being pinned, which is the interesting part.

**1. Quadratic spawn count in the doc-freshness checker (fixed).**
`check_doc_freshness.git_commit_time()` shelled out `git log -1` PER FILE,
inside a nested per-doc/per-tracked-file loop. Measured on the real tree: 36
docs -> **263 git.exe processes, 48.7s**. Replaced with a single
`git log --name-only` walk populating a path -> commit-time map, memoized.
Result: **263 spawns -> 1, 48.7s -> 0.9s, output byte-identical** on the full
doc set.

Directory tokens needed explicit handling and nearly shipped broken. A
`**Tracks:**` line may name a DIRECTORY, and `git log -1 -- <dir>` means
"newest commit under it"; a flat filename map answers `None` there. That is
the *dangerous* direction -- the doc silently stops being flagged stale rather
than erroring. Caught by diffing against the original implementation's output,
which is why the byte-identical comparison was worth doing at all.

**2. Unprotected spawns -- the incomplete half of bd polyglot-pdf-5k32 (fixed).**
5k32 (PR #205, 2026-06-15) diagnosed this exact mechanism and shipped
`swarm_config.windowless_creationflags()`, but applied it only to the
SessionStart hook scripts in frame at the time. The /closeout path was missed.
AST-enumerated the whole `scripts/` tree: **17 unprotected sites across 11
files**, all now passing `creationflags`. (`beads_remote_bootstrap.run()` sets
it via `kw.setdefault` and forwards `**kw` -- already correct, and a false
positive in the first enumeration pass.)

Per scar tissue #8, the fix pins the **set**, not the instances:
`backend/tests/unit/test_script_spawns_are_windowless.py` statically asserts
every subprocess spawn under `scripts/` passes `creationflags`, scope derived
by EXCLUSION so a new script is covered the day it appears, plus a vacuity
guard so a broken scanner fails loudly instead of passing on zero files.

**3. The actual focus-stealing cascade: npm's POSIX-shell `bd` shim (fixed).**
`bd` on PATH is a `#!/bin/sh` script. Windows cannot execute that directly, so
EVERY `bd` call spawns `sh.exe` to interpret it, and each `sh.exe` carries a
console window that takes focus. Caught live in a process snapshot:

    "C:\Program Files\Git\usr\bin\sh.exe" /c/Users/caell/AppData/Roaming/npm/bd dolt push
    "C:\Program Files\Git\usr\bin\sh.exe" /c/Users/caell/AppData/Roaming/npm/bd create "--title=..."

With several agent sessions each doing pull-before-read / push-after-write,
that is the rhythmic cascade (peak measured: 261 concurrent `git.exe`, 74
`sh.exe`). The npm package also ships a native `bd.exe` (PE32+, same version
1.0.5) whose bin directory is NOT on PATH by default. Prepending it via
`.claude/settings.json` `env.PATH` makes `bd` resolve to the executable.
Measured A/B, one `bd ready` each: **npm shim -> 1 sh.exe; native exe -> 0.**

`settings.json` is the load-bearing half: neither login shells nor Claude
Code's Bash tool source `~/.bashrc` (verified both), so the equivalent shell
profile fix does not reach agent sessions -- which are the cascade source.

**Deferred / filed.**
- `polyglot-pdf-mlcgn` (P3) -- move the dolt remote off the git-backed URL
  (`git+https://`, 235 MiB in `refs/dolt/data`). Real sync cost, but
  **retitled and downgraded** during this work: it was filed claiming to be
  the cascade fix, which was wrong. Carries a note to re-measure before
  spending on it.

**Assess outcome.** Exit criteria scored 2/2 PASS (see PR body). Fresh-eyes and
the outer cross-surface review both cleared; round counts and triage breakdown
are in the merge ping.

## Lessons

**A regression fixed three months ago can return as the same symptom from a
different cause.** 5k32 fixed *a* console-window storm; this session found two
more mechanisms producing an identical user-visible symptom. The first fix was
correct and still insufficient, which is scar tissue #8 in its purest form --
and why the guard here pins the set rather than the 17 instances.

**Diagnosis went wrong twice before landing, and the pattern is worth naming.**
Both wrong answers came from finding a *real* mechanism and stopping. The
credential helper genuinely does spawn `sh.exe` twice per authenticated git
op; the git-backed dolt remote genuinely does drive parallel fetches. Neither
was the focus-stealing cascade. The thing that actually settled it was a
process snapshot with full command lines taken *during* a cascade -- direct
observation of the running system, not inference from plausible mechanisms.
**When a symptom has several plausible causes, go measure which one is firing
rather than fixing the most plausible.**

**Verify the fix eliminates the mechanism, not just that it looks right.** The
credential-helper theory survived a long time because swapping helpers
*sounds* like it removes the shell. `GIT_TRACE=1` showed git-for-Windows
shells out for EVERY credential helper -- `manager`, `wincred`, and an
absolute `.exe` path alike -- so the swap would have changed nothing while
appearing to fix it. An absolute path containing a space additionally BREAKS
auth when shelled. (The maintainer's global gitconfig was modified to test
this and restored byte-identical; auth re-verified.)

**A mutation that does not apply proves nothing** (existing standards rule,
re-confirmed the hard way). One mutation-verification pass here silently
no-op'd because the regex required a `[:N]` slice that was not in the source;
the test "passed" against an unmutated file. Always confirm the mutation
actually landed before reading the result -- this is why
`docs/standards/testing.md` says to check.

**Test stubs that pin an exact signature break on correct changes.** Adding
`creationflags=` broke `test_guidance_regen_serialization`'s `fake_run`, which
declared a fixed parameter list. A stub standing in for `subprocess.run` must
take `**kwargs`; pinning the exact set makes a *correct* production change
look like a test failure. Fixed and mutation-verified it still catches the
`uuid4 -> getpid` scratch-path collision it exists for.

## Doc freshness

No tier-1/tier-2 doc makes a claim this change contradicts. The
`**Tracks:**` globs over `scripts/` do not cover `check_doc_freshness.py`'s
internals, and no doc documents the `bd` shim-vs-exe resolution (it was not
known until this session). CLAUDE.md scar tissue #8 (enumerate the set) is
cited by the new guard rather than restated -- per the current-state-only
rule, this entry is the chronological record.

`docs/standards/testing.md` already carries the "test the tests" /
mutation-verify rules that the no-op mutation lesson above reconfirms; no new
one-liner was added because it would restate an existing rule verbatim.

## Files touched

- `scripts/check_doc_freshness.py` -- batched `_commit_times()` map +
  `_dir_commit_time()` prefix-max for directory tokens; local
  `windowless_creationflags()`; 7 spawn sites protected.
- `scripts/closeout_prep.py`, `scripts/pick_review_model.py`,
  `scripts/drain_flag.py`, `scripts/verify_service_reachable.py`,
  `scripts/pr_review_watcher.py`, `scripts/bootstrap_admin_user.py`,
  `scripts/bootstrap_editor_user.py`, `scripts/bootstrap_voice_dev.py`,
  `scripts/spikes/run_guard.py`, `scripts/bakeoff/llm_providers.py`,
  `scripts/bakeoff/order_probe.py` -- `creationflags` added to every spawn
  site (17 total), helper added where absent.
- `backend/tests/unit/test_script_spawns_are_windowless.py` -- NEW. Static
  AST guard pinning the whole spawn set + vacuity guard.
- `tests/test_doc_freshness.py` -- `TestBatchedCommitTimes`: real-git fixture
  (two commits per path, reverse order, so a `setdefault -> overwrite`
  regression cannot survive), directory-token parity against git itself,
  one-invocation spawn guard, creationflags guard.
- `backend/tests/unit/test_guidance_regen_serialization.py` -- `fake_run`
  given `**kwargs`.
- `.claude/settings.json` -- `env.PATH` prepends the native `bd.exe` bin dir.
