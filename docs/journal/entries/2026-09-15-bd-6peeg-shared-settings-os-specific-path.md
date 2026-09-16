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

**Assess outcome.** Exit criterion 1 PASS. Fresh-eyes returned
`GAPS-FOUND (2)`, both correct:

- **The guard's own scope was too narrow** -- and in exactly the way this repo
  keeps getting caught by. `SHARED_SETTINGS` was HAND-LISTED
  (`settings.json` + `settings.local.json`) and silently omitted the third
  tracked config, `.claude/launch.json`. Now derived by GLOB over
  `.claude/*.json`, so a new tracked config is covered the day it appears.
- **The machine-path patterns were a blacklist and were already defeated.**
  Three hand-written "looks machine-specific" regexes missed
  `%APPDATA%\npm\...` (a Windows env-var reference) and `/opt/homebrew/bin` (a
  POSIX absolute path with no `Users`/`home` segment) -- both verified slipping
  past. Replaced with a single pattern expressing the positive property (a
  value must not name an absolute location on somebody's disk), plus
  parametrized cases pinning every known evasion BY NAME and a companion set
  asserting portable values are still accepted, so tightening the pattern into
  uselessness also fails.

Deferred: `polyglot-pdf-prskq` (nothing in the repo documents the manual user
PATH step this fix relies on, so a fresh Windows clone gets no native `bd.exe`
and rdftu's cascade could quietly return there).

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

**A hand-listed scope is the bug, every time.** The first draft of the guard
enumerated two settings files by name and missed the third tracked config in
the same directory -- while the file's own docstring claimed to cover "any
tracked settings file." That is scar tissue #8 reproduced inside a test
written to enforce scar tissue #8. Deriving the list by glob is both shorter
and correct; hand-listing is what needs justifying, not the reverse.

**A blacklist of "bad-looking" values is one spelling from defeat, and the
first draft proved it.** Three patterns matching drive letters, MSYS paths and
`Users`/`home` segments looked thorough and missed two ordinary shapes
(`%APPDATA%\...`, `/opt/homebrew/bin`). The fix was to stop enumerating what is
wrong and state what is RIGHT -- a portable value never names an absolute
location on a disk -- then pin the known evasions by name so the pattern
cannot silently narrow. Same lesson as
`pin-message-tests-with-allowlists`: assert the sanctioned shape, then assert
no residue.

## Doc freshness

No tier-1/tier-2 doc documents the `.claude/settings.json` env block, so none
makes a claim this change contradicts (checked `docs/components/`,
`docs/standards/`, `docs/doctrine/`). The freshness checker flags no doc whose
`**Tracks:**` globs cover `.claude/settings.json` or `tests/`.

`scripts/swarm_config.py`'s own comment already states the correct pattern for
the in-process case and needed no change -- this bead did not alter that path.

## Files touched

- `.claude/settings.json` -- `env` block removed (3 lines).
- `tests/test_claude_settings_env.py` -- NEW. Scope derived by GLOB over every
  tracked `.claude/*.json`. Bans `env.PATH` (any casing) in any of them; bans
  values naming an absolute machine location under ANY env key, via a single
  allowlist-shaped pattern rather than a blacklist of bad spellings; pins every
  known evasion by name AND asserts portable values still pass; and pins the
  reasoning with a parametrized separator test.
