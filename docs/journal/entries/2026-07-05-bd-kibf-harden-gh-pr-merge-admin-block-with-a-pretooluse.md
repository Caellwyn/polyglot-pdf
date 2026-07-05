---
date: 2026-07-05
bead: polyglot-pdf-kibf
title: "Harden gh pr merge --admin block with a PreToolUse hook (settings wildcard is fragile)"
tags: [doctrine, testing]
---

## Trigger

The auto-merge policy (bd `polyglot-pdf-16pj`) lets the orchestrator run
`gh pr merge` itself for a routine low-risk PR, gated on CI/required checks being
green. `gh pr merge --admin` bypasses that gate (it merges a PR that does not meet
requirements). 16pj denied `--admin` via three space-wildcard patterns in
settings.json, but claude-code-guide confirmed the Bash permission matcher does
only substring/space-glob matching and is fragile for flag validation. bd kibf
adds the robust layer: a PreToolUse hook that tokenizes the command.

## What shipped

- **`scripts/block_admin_merge_hook.py`** -- a PreToolUse hook that models the ARGV
  the shell actually passes to `gh`. It undoes line continuations + turns newlines
  into command boundaries, normalizes a Windows-path `gh` executable to forward
  slashes, tokenizes with `shlex(posix=True)` (the real post-quote-removal argv),
  re-splits on embedded operators, partitions into command fragments on
  operator/boundary tokens (`; && || | & ( ) \``), skips reserved words
  (`if`/`then`/...), env-assignments, and wrapper prefixes (`sudo`/`eval`/`timeout`/
  `xargs`/...), then matches `gh pr [inherited flags] merge ... --admin` -- honoring
  gh's value-taking options so `--body --admin` (a body of "--admin") is NOT the
  flag. DENIES only a real admin-merge; on anything else (legit merge, `--admin`
  inside a quoted arg, `gh pr merge --admin` named in another command's args, a word
  ending in "gh", a non-Bash tool, malformed stdin) it exits 0 with no output, so
  the normal permission flow (incl. the settings.json denies) still applies. Never
  emits `permissionDecision: "allow"`, so it can only ADD a restriction.
- **`.claude/settings.json`** -- wired the hook as a `PreToolUse` hook with
  `matcher: "Bash"`. The three `--admin` wildcard denies are KEPT as the first layer
  (defense-in-depth; bd kibf exit criterion 2). Force-push / `bd dolt push --force`
  denies untouched.
- **`tests/test_block_admin_merge_hook.py`** -- 78 tests pinning the detection core
  (block forms incl. subshell/brace-group/negation/exec, embedded newline, Windows
  backslash path + `.cmd`/`.bat` shims, env-assignment and separator prefixes, and
  `--admin=`; allow forms incl. the quoted-string evasion, the `gh pr merge --admin`
  mentioned-in-another-command's-args case, `--administrator`/substring near-misses)
  and the stdin/stdout main() contract (deny JSON shape, silent passthrough, non-Bash
  ignore, malformed-stdin survival).

Verified end-to-end by piping a real hook payload to the script: an admin-merge
emits the deny JSON; a legit `--squash --match-head-commit` merge emits nothing.

## Lessons

- **Why the hook succeeds where the wildcard deny cannot:** the settings matcher
  sees a raw string; the hook sees TOKENS. `gh pr merge 5 --body 'do not use
  --admin'` matches a naive `*--admin*` wildcard (the substring is there) but is a
  perfectly legitimate command -- only the tokenizer knows `--admin` is inside a
  quoted argument, not a flag. Tokenize before you validate a flag. (Extends
  [[bash-permission-wildcard-trailing-only]].)
- **A command-detection guard must distinguish the command being RUN from text in
  another command's ARGUMENTS -- caught when the hook blocked its own commit.** The
  first cut scanned for `gh pr merge ... --admin` anywhere in the token stream, so a
  `git commit -m "...block gh pr merge --admin..."` (the flag named in the commit
  message) was denied -- the hook refused to let me commit itself. The fix: only
  treat `gh pr merge` as an admin-merge when `gh` is an actual COMMAND HEAD.
- **`shlex.split` alone is NOT a safe basis for a shell-command security guard --
  adversarial fresh-eyes found 6 bypasses in the first head-detection cut.** shlex
  (posix=True) silently merges newlines (so `git fetch\ngh pr merge 5 --admin`
  slipped through), mangles Windows backslash paths (`C:\tools\gh` -> `C:toolsgh`, so
  a path-qualified gh evaded on a Windows-only repo), and does not understand
  grouping/negation (`(gh pr merge 5 --admin)`, `{ ...; }`, `! ...`) or `exec` -- all
  of which slipped through, some ALSO evading the wildcard-deny layer (worst case:
  both layers bypassed). Redesign: SPLIT the raw command on all shell boundaries
  first (`\n ; && || | & ( ) { }`) so each fragment starts a fresh command context,
  tokenize each fragment with `posix=False` (backslashes survive) + a single
  quote-unwrap, skip benign leading prefixes (`sudo`/`env`/`exec`/`!`/`VAR=val`), and
  match a `gh` exe (incl. `gh.cmd`/`gh.bat` Windows shims, path-qualified) head
  followed by `pr merge` + an `--admin` token. A SECOND adversarial round then found
  2 more: backtick/`$(...)`/`xargs` (added `` ` `` to the split set + `xargs` to the
  prefixes) and a false POSITIVE where a bare-quoted `--body '--admin'` value
  unwrapped to look like the flag (fixed by having `_tokenize` return `(text,
  was_quoted)` pairs so a quoted arg is never treated as a flag). 78 tests pin all of
  it. **Lesson: a security guard over shell strings needs boundary-splitting +
  head-anchoring + quote-tracking, not a flat token scan -- and it must be tested
  against the wrapping idioms (subshell, newline, path, negation, substitution),
  not just the happy path.**
- **Round 3 closed two more statically-fixable false negatives INSIDE the hook's own
  advertised scope.** A benign prefix carrying its own option flag (`sudo -u foo gh pr
  merge --admin`, `nice -n 10 ...`) defeated the head-skip -- the loop stopped at the
  prefix's `-u`/`-n` option -- so the prefix-skip now also consumes a prefix's leading
  `-flag` (and a single following plain value). And a backslash-newline line
  continuation (`gh pr merge 5 \<newline>--admin`, which POSIX joins before word
  splitting) was orphaning `--admin` into its own fragment -- fixed by stripping
  `\<newline>` before the boundary split. Both came with false-positive guards
  (`sudo -u foo systemctl...`, `nice -n 10 gh pr view`, `sudo apt install gh` still
  pass).
- **Draw and TEST the scope boundary explicitly.** Some forms (`bash -c "gh pr merge
  ... --admin"`, `xargs -I{} gh pr merge {} --admin`, `GH=gh; $GH pr merge --admin`)
  run a merge but the gh command is nested in an opaque arg, placeholder-templated,
  or behind variable indirection -- catching them needs full shell emulation, well
  past a static head-matcher. Rather than pretend or chase them, they are documented
  out of scope with a pinning test (`test_templated_or_nested_forms_are_documented_
  out_of_scope`) asserting they return False, and the settings.json wildcard denies
  remain their backstop. A known, tested boundary beats an unbounded ambition.
- **The Codex OUTER review found a DESIGN FLAW four fresh-eyes rounds missed:
  quote state is not a safety signal.** After 4 pre-PR fresh-eyes rounds returned
  NO-GAPS, Codex (on PR #311) found 7 more issues, the core one being architectural:
  the hook used "was this token quoted?" to decide a `--admin` was a safe value --
  but the shell REMOVES quotes/backslashes before `gh` runs, so `gh pr merge
  "--admin"` and `gh pr merge --ad\min` both reach `gh` with a real `--admin` argv
  token. The whole quote-tracking approach was wrong-headed. Fix = model the ARGV
  the shell builds: tokenize with `shlex(posix=True)` (which does exactly the shell's
  quote/escape removal), so what the check sees IS what `gh` receives. This also
  fixed a false POSITIVE (splitting the RAW string on `(`/backtick fired inside
  quoted args like `git commit -m 'note (gh pr merge --admin)'`) -- tokenizing FIRST
  keeps in-quote operators inside their token. **Lesson: for a shell-command security
  guard, model the executed argv, never the surface syntax; and different reviewers
  find different bug classes -- the outer adversarial review earned its place even
  after the inner loop went clean.** The redesign also promoted two
  formerly-out-of-scope forms (`xargs -I{}`, some `$VAR`-free templating) to caught,
  and fixed a greedy `endswith("gh")` that would have false-positived `$GH`/`foogh`.
  The Opus-4.8 fallback review of the redesign (Codex was quota-out) then confirmed
  all 7 closed and found ONE more real bypass: a persistent gh flag BEFORE the
  subcommand -- `gh --repo o/r pr merge 5 --admin` -- which gh/Cobra accepts and
  which slipped BOTH the hook (it required `pr` immediately after `gh`) and the
  contiguous-`gh pr merge` wildcard denies. Fixed by skipping inherited gh flags
  between `gh` and `pr` too (mirroring the `pr`->`merge` skip). **The persistent-flag
  position is the kind of gap you only find by knowing the tool's actual grammar --
  Cobra accepts persistent flags before OR after the subcommand.**
- **PreToolUse hooks are a real security layer, not advisory.** Per the docs they
  run BEFORE the permission-mode check and cannot be bypassed even under
  `bypassPermissions`; a hook can tighten but never loosen what permission rules
  allow. That is exactly the "can't be evaded" property a checks-bypass guard needs
  -- stronger than the wildcard deny it backs up.

## Doc freshness

- No tier-1/tier-2 doc changes. The hook's own rationale + contract live in its
  module docstring (current-state). No CLAUDE.md change (16pj already documents the
  auto-merge interlock; this hardens its enforcement, not its policy).

## Files touched

- `scripts/block_admin_merge_hook.py` -- new PreToolUse hook.
- `.claude/settings.json` -- PreToolUse wiring (wildcard denies retained).
- `tests/test_block_admin_merge_hook.py` -- new; 78 tests.
- `docs/journal/entries/2026-07-05-bd-kibf-...md` -- this entry.
