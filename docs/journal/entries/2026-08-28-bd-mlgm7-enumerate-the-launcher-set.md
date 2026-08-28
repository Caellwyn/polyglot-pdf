---
date: 2026-08-28
bead: polyglot-pdf-mlgm7
title: "fix(scripts): enumerate the uvicorn launcher SET -- three fixes found five launchers"
tags: [hotfix, harness, verification, scar-8]
---

## Trigger

bd `polyglot-pdf-b5nmq` (PR #660) fixed the reload-watch scoping in two
launchers, and its cross-surface review filed a bead for a third,
`scripts/dev-local.sh` -- notably the one `.claude/skills/run-local/SKILL.md`
tells agents to prefer, so the maintainer's original symptom persisted on the
agent path while the human path was fixed.

That bead was the prompt to stop fixing instances. This is the third time the
same bug has been "fixed" by patching whichever launcher was reported:
PR #650 fixed one, b5nmq fixed two more, and each round's fix was correct
about the instance and silent about the rest of the set.

## Root cause (unchanged from b5nmq)

uvicorn's `WatchFilesReload` supervisor DROPS any `--reload-dir` that is a
child of the process cwd and watches the cwd instead:

```python
for directory in config.reload_dirs:
    if Path.cwd() not in directory.parents:
        self.reload_dirs.append(directory)
if Path.cwd() not in self.reload_dirs:
    self.reload_dirs.append(Path.cwd())
```

From the repo root that resolves to watching everything, `.claude/worktrees/`
and its ~130 sibling checkouts included. The startup banner prints the
CONFIG, not the effective watch set, which is why every round looked
verified.

## What the enumeration actually found

Not one more launcher. **Five files, six invocations:**

| File | Was | Note |
|---|---|---|
| `scripts/dev-local.sh` | `cd $REPO_ROOT` + relative `--reload-dir` | the filed bead |
| `scripts/dev_env.ps1` | same shape | never noticed by anyone |
| `README.md` | bare `--reload`, no scoping at all | the documented onboarding command |
| `test-pdf-filling.md` | bare `--reload` | genuinely unscoped |
| `DEBUG_PDF_FILLING.md` | already `cd backend` | correct by luck |
| `scripts/start-token-monitor.sh` | echoes correct advice | found only by the widened regex |

The README was the worst of them: no scoping whatsoever, and it is what a new
contributor copies first.

## The guard, and four rounds of it being defeatable

The point of this bead was to pin the SET (CLAUDE.md scar #8), so the test
matters more than the fixes. It took four corrections, each found by a
reviewer or by a case written to contradict one -- never by the test passing:

1. **File-wide substring search.** A mutated README passed on an unrelated
   `cd backend` ~300 lines from the launch. Evidence region wider than the
   claim.
2. **8-line window before the launch.** False-positived both shell scripts,
   whose `cd` sits above a long env-var block.
3. **40-line window.** `dev-local.ps1` still failed -- PowerShell takes the
   cwd as an ARGUMENT, so `-WorkingDirectory` lands ~80 lines AFTER the args.
4. **Bidirectional window.** Baseline green, but wide enough forward to sweep
   in the kill/cleanup blocks, so both shell-script mutations passed again.

Then the fresh-eyes round found that even the construct-matching version was
still **file-wide**: I had described it as fixing the anchoring problem, and
it had only narrowed the needle. A second unscoped launch in an
already-scoped file passed on the first one's `cd`.

The shape that finally holds: **one case per INVOCATION**, with the evidence
segment running from the previous invocation to this one, so no launch can
reuse another's setup. Plus a named exemption for `-WorkingDirectory`
trailing its launch, kept as its own pattern so nothing else inherits it.

The same round found `_RELOAD_RE` required the dotted `backend.main:app`,
silently excluding the bare `main:app` spelling -- and widening it is what
surfaced the fifth launcher and the two docs. **The enumeration was itself
under-enumerated.**

## Verification

Baseline 8 passed; reverting each of the six invocations to its repo-root
form turns exactly one case red; restore green. The discovery guard was
verified the same way -- narrowing `_LAUNCHER_GLOBS` makes it report
"found 2: ..." rather than the `TypeError` the Opus round caught it raising
on a partial regression (it unpacked bare Paths as pairs; only TOTAL
breakage hid it, since an empty generator never iterates).

Full backend suite: 2897 passed, 8 skipped.

## Lessons

**"I enumerated the set" is a claim that needs the same scrutiny as any
other.** It was made twice in this chain and was wrong both times -- first
missing two launchers, then missing a whole spelling that hid three more
invocations. An enumeration is only as complete as the pattern that produced
it, and that pattern is itself an unenumerated guess until something forces
it to fail.

**Guard the discovery pass, not just the property.** `test_the_launcher_set_
is_non_empty` earned its place within minutes of being written: it caught
the discovery regex missing `dev-local.ps1`, which builds an argument ARRAY
rather than a command string. A set-pinning test whose *finder* silently
narrows is worse than no test, because the per-item checks then pass
vacuously. Give the finder a floor, and make the floor real -- 4 stopped
being a floor the moment a fifth launcher appeared.

**Count where the findings come from.** Across b5nmq and mlgm7: six rounds,
every one surfaced by a reviewer or by a deliberately adversarial case.
Zero were surfaced by a check going green. That ratio is the argument for
mutation-testing the guard with the defect someone else just found, rather
than with the sites the guard was written from.
