---
date: 2026-09-15
bead: polyglot-pdf-6peeg
title: "fix(claude): settings.json PATH override uses ';' and drops a real PATH entry on macOS/Linux"
tags: [harness, conventions]
---

## Trigger

Filed by the Opus cross-surface reviewer during the closeout of bd
polyglot-pdf-rdftu (PR #806). That bead added an `env.PATH` override to
`.claude/settings.json` so `bd` would resolve to the native `bd.exe` rather
than npm's POSIX-shell shim -- the shim was spawning a console window on every
`bd` call and, across concurrent agent sessions, producing a focus-stealing
window cascade.

The reviewer traced that value onto a platform it was never aimed at and found
it is not the harmless no-op the sibling bead (polyglot-pdf-enot7, the
hardcoded-username angle) assumed.

## What shipped

**The bug.** `.claude/settings.json` is TRACKED, so its env block ships to
every contributor on every OS. The value was

    "PATH": "C:\\Users\\caell\\...\\@beads\\bd\\bin;${PATH}"

The separator is `;` (Windows). POSIX splits PATH on `:`, so the expanded
value yields the fields `'C'`, `'\Users\caell\...\bd\bin;/usr/local/bin'`,
`'/usr/bin'`, `'/bin'` -- and `/usr/local/bin` stops being a searchable entry.
That is where Homebrew/npm put `bd`, `gh` and `node` on macOS, so the override
meant to FIX bd resolution would break bd AND gh on machines it never targeted.
Reproduced before fixing.

**Why it was removed rather than repaired.** No single literal is correct
everywhere, and each plausible repair fails somewhere:

| Candidate | Windows | POSIX |
|---|---|---|
| `...bd\bin;${PATH}` (shipped) | works | **corrupts** -- swallows the first entry |
| `...bd\bin:${PATH}` | **breaks** -- `C:` splits into its own field | intact |
| `/c/Users/.../bd/bin:${PATH}` (MSYS) | resolves in Git Bash, **fails** for Windows-native processes | intact |

The MSYS row is the trap worth remembering: it resolves under `which bd` in
Git Bash, so it looks portable, but `shutil.which` returns `None` for it --
every Python caller would silently lose the native `bd.exe` and fall back to
the shim, quietly reinstating the cascade rdftu just fixed. Verified directly
rather than reasoned about.

Claude Code settings support no OS conditionals, and the usual escape hatch
does not exist here either: **`.claude/settings.local.json` is also TRACKED in
this repo**, so "move it to the local file" would have shipped the same value
to the same people. That fact is what ruled out the otherwise-obvious fix.

**The replacement.** The directory now lives in the maintainer's own
persistent Windows user PATH, where it is machine-local and separator-native
by construction, and the shared file is OS-agnostic again. Verified a fresh
process with no `settings.json` env resolves `where bd` to
`...\@beads\bd\bin\bd.exe` FIRST, ahead of the npm shim -- so rdftu's cascade
fix still holds. The user PATH went 11 -> 12 entries with every original
preserved; a backup was written to the Desktop before the change.

`scripts/swarm_config.py` already solves the in-process half of this correctly
and was the model for the reasoning: derive from `expanduser("~")` (no
hardcoded username), guard on the file existing (inert elsewhere), join with
`os.pathsep` (correct separator per platform). Nothing about that path changed.

**Also closes the sibling.** With no machine path in the shared file at all,
bd polyglot-pdf-enot7 (hardcoded username) has nothing left to fix; the new
guard bans that shape too.

## Lessons

**"Tracked or not?" is the first question about any config fix, not a
detail.** The standard advice for a machine-specific setting -- move it to
`settings.local.json` -- is correct in most repos and wrong in this one,
because that file is tracked here. Checking `git ls-files` took seconds and
changed the entire approach; accepting the conventional answer would have
shipped the same bug to the same people under a different filename.

**A value that "works" on the machine you are testing on can be wrong by
construction.** The `;` separator was verified working -- on Windows, where
Git Bash silently normalizes a Windows-style PATH into MSYS form. That
normalization is the reason the bug was invisible locally and is exactly what
does not happen on the platform it breaks. Local green said nothing about it.

**Pin the reasoning when the fix is a ban.** A future reader looking at "no
env.PATH allowed" will reasonably wonder why the separator was not simply
corrected. The parametrized `test_no_separator_choice_would_have_been_safe`
asserts mechanically that BOTH choices corrupt one platform, so the question
is answered by a test rather than by prose that can drift -- and if the
premise ever changes, that test fails and invites revisiting the ban.

## Doc freshness

No tier-1/tier-2 doc documents the `.claude/settings.json` env block, so none
makes a claim this change contradicts (checked `docs/components/`,
`docs/standards/`, `docs/doctrine/`). The freshness checker flags no doc whose
`**Tracks:**` globs cover `.claude/settings.json` or `tests/`.

`scripts/swarm_config.py`'s own comment already states the correct pattern for
the in-process case and needed no change -- this bead did not alter that path.

## Files touched

- `.claude/settings.json` -- `env` block removed (3 lines).
- `tests/test_claude_settings_env.py` -- NEW. Bans `env.PATH` in any tracked
  settings file; bans machine-specific absolute paths (drive-letter, MSYS
  `/c/`, hardcoded home dir) under ANY env key; and pins the reasoning with a
  parametrized separator test.
