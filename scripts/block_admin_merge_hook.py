#!/usr/bin/env python3
"""block_admin_merge_hook.py -- PreToolUse guard that denies `gh pr merge --admin`.

Why this exists (bd polyglot-pdf-kibf)
--------------------------------------
The auto-merge policy (bd polyglot-pdf-16pj) lets the orchestrator run `gh pr
merge` itself for a routine low-risk PR, gated on CI/required checks being green.
`gh pr merge --admin` uses administrator privileges to merge a PR that does NOT
meet those requirements -- it bypasses the exact green-checks interlock the policy
depends on. settings.json denies `--admin` with space-wildcard patterns, but the
Claude Code Bash permission matcher does only substring/space-glob matching and is
FRAGILE for flag validation (a `--admin` inside a quoted string could match a naive
pattern; an unusual position could evade one). This PreToolUse hook is the robust
second layer: it models the ARGV the shell actually passes to ``gh`` (post
quote/backslash removal, via ``shlex(posix=True)``) and denies only when a real
``--admin`` argv token lands on a ``gh pr merge`` invocation. Modeling argv rather
than raw text is deliberate (Codex review of PR #311): quote state is NOT a safety
signal -- the shell strips quotes/escapes before ``gh`` runs, so ``"--admin"`` and
``--ad\min`` both reach ``gh`` as the flag. See ``command_is_admin_merge`` for the
full strategy and the documented shell-emulation out-of-scope boundary.

Defense-in-depth, not a replacement: the settings.json wildcard denies stay as the
first layer (bd kibf exit criterion 2). PreToolUse hooks run BEFORE the permission
check and cannot be bypassed even under ``bypassPermissions`` -- and a hook can only
tighten, never loosen, what the permission rules allow -- so this genuinely hardens
the interlock rather than weakening it.

Contract (verified against the Claude Code hooks docs via claude-code-guide)
----------------------------------------------------------------------------
Input (stdin JSON): ``tool_name`` and ``tool_input.command`` are the fields we read.
Deny: exit 0 and print ``hookSpecificOutput`` with ``permissionDecision: "deny"`` and
a ``permissionDecisionReason``. Allow/passthrough: exit 0 with NO output (the normal
permission flow -- including the settings.json denies -- still applies; we never emit
``"allow"``, so we only ever ADD a restriction, never remove one). We also exit 0
silently on any parse failure or non-matching tool: a hook that crashes or that
blocks unrelated commands would be worse than the wildcard-deny baseline it backs up.

ASCII-only (Windows cp1252 stdout); no third-party deps.
"""
from __future__ import annotations

import json
import re
import shlex
import sys


# The flag we block, spelled via concatenation so a source-scanner / this very hook
# reading its OWN file never trips on a literal occurrence.
_ADMIN = "--adm" + "in"

# Command-executing wrappers/prefixes: the REAL command follows them (possibly past
# their own options). ``!`` is shell negation; ``eval``/``xargs``/``timeout`` etc. run
# their argument as a command. When one heads a fragment we cannot know its option
# arity, so we scan every offset of the fragment for the gh-pr-merge pattern.
_PREFIXES = frozenset({
    "sudo", "env", "command", "nice", "nohup", "time", "exec", "!", "xargs",
    "eval", "timeout", "stdbuf", "setsid", "nohup",
})
# Bash reserved words that head a construct whose command LIST still runs
# (``if gh pr merge --admin; then...``). Skipped when scanning for a command head.
_RESERVED = frozenset({
    "if", "then", "elif", "else", "fi", "while", "until", "do", "done",
    "for", "case", "esac", "{", "}", "!",
})
# Operator tokens that separate one command from the next. We split the argv token
# stream on these; because we tokenize with posix shlex FIRST, an operator that was
# inside quotes stays inside its token and is NOT a boundary (fixes the
# split-inside-quotes false positive).
_FRAG_BOUNDARIES = frozenset({";", "&&", "||", "|", "&", "(", ")", ";;", "`"})
# Split an argv token on any EMBEDDED bare operator (posix shlex leaves e.g.
# ``--admin;`` or ``` `gh ``` as one token).
_OP_RE = re.compile(r"(\|\||&&|;;|;|\||&|\(|\)|`)")
# gh options (on ``gh pr merge`` and inherited from ``gh pr``) that TAKE A VALUE: the
# next argv token is their value, not a flag -- so ``--body --admin`` is a body of
# "--admin", NOT the admin flag. Kept generous; a missing entry only risks a rare
# false POSITIVE (over-block), never a bypass.
_GH_VALUE_OPTS = frozenset({
    "-b", "--body", "-t", "--title", "--subject", "--body-file", "-F",
    "--author", "--author-email", "--match-head-commit", "-R", "--repo",
})


_GH_NAMES = ("gh", "gh.exe", "gh.cmd", "gh.bat")


def _is_gh(tok: str) -> bool:
    """True if ``tok`` names the ``gh`` executable: bare, or path-qualified (either
    separator), or a Windows shim (gh.exe/.cmd/.bat). Windows backslash paths are
    normalized to forward slashes BEFORE tokenizing (see command_is_admin_merge), so
    a path segment split covers them here -- we do NOT fuzzy-match "ends in gh" (that
    over-matched ``$GH``, ``foogh``, ``mygh`` etc.)."""
    low = tok.lower()
    if low in _GH_NAMES:
        return True
    seg = re.split(r"[\\/]", tok)[-1].lower()
    return seg in _GH_NAMES


def _admin_merge_at(frag: list[str], s: int) -> bool:
    """Does ``frag[s:]`` begin a ``gh pr [inherited flags] merge ... <admin>``
    command? ``frag`` is the post-quote-removal argv of one command fragment, so a
    token here is exactly what ``gh`` would receive."""
    if s >= len(frag) or not _is_gh(frag[s]):
        return False
    j = s + 1
    if j >= len(frag) or frag[j] != "pr":
        return False
    j += 1
    # Allow inherited ``gh pr`` flags (e.g. ``--repo o/r``) before ``merge``.
    while j < len(frag) and frag[j] != "merge":
        if frag[j].startswith("-"):
            if frag[j] in _GH_VALUE_OPTS and "=" not in frag[j]:
                j += 2  # flag + its value
            else:
                j += 1
        else:
            return False  # a non-flag, non-``merge`` word -> not this pattern
    if j >= len(frag) or frag[j] != "merge":
        return False
    # Scan merge's args for a real admin flag, honoring value-taking options so a
    # ``--body <admin>`` value is not mistaken for the flag.
    k = j + 1
    while k < len(frag):
        tok = frag[k]
        if tok == _ADMIN or tok.startswith(_ADMIN + "="):
            return True
        if tok in _GH_VALUE_OPTS and "=" not in tok:
            k += 2  # this flag consumes the next token as a value
            continue
        k += 1
    return False


def command_is_admin_merge(command: str) -> bool:
    """True iff ``command`` runs ``gh pr merge`` with the admin-privilege flag.

    Models what the SHELL actually passes to ``gh`` as argv (post quote/backslash
    removal), because quote state is not a safety signal -- ``gh pr merge 5
    "--admin"`` and ``gh pr merge 5 --ad\\min`` both reach ``gh`` with a real
    ``--admin`` argv token (Codex review of PR #311). Strategy:

      1. Undo backslash-newline continuations; turn raw newlines into ``;`` so they
         separate commands.
      2. Tokenize with ``shlex(posix=True)`` -> the real argv. This normalizes quoted
         command words (``'gh' pr merge`` -> ``gh pr merge``) and quoted/escaped flags,
         and keeps operators that were INSIDE quotes inside their token (so
         ``git commit -m 'note (gh pr merge --admin)'`` is one arg, not a fake head).
      3. Re-split tokens on embedded bare operators, then split the stream into
         command fragments on operator/boundary tokens (``; && || | & ( ) ` ``).
      4. Per fragment: skip reserved words, env-assignments, and wrapper prefixes
         (``sudo``/``eval``/``timeout``/...). If a wrapper was seen we scan every
         offset (its option arity is unknown); else only the head can start the
         command. Match ``gh pr [flags] merge ... <admin>`` via ``_admin_merge_at``.

    Forms that need full shell emulation stay out of scope (documented + tested):
    a merge nested in an opaque ``bash -c "..."`` arg, a placeholder-templated
    ``xargs -I{}``, or variable indirection (``$GH pr merge --admin``). The
    settings.json wildcard denies remain their backstop.
    """
    if not command:
        return False
    command = re.sub(r"\\\r?\n", " ", command)   # line continuation
    command = re.sub(r"[\r\n]+", " ; ", command)  # newline -> command boundary
    # Normalize a Windows-path gh EXECUTABLE (``C:\tools\gh`` / ``.\gh.exe``) to
    # forward slashes BEFORE posix shlex, which would otherwise drop the backslashes
    # and mangle the token. Narrowly targeted at a backslash-path ending in a gh
    # executable so we never touch a backslash ESCAPE like ``--ad\min`` (which must
    # collapse to ``--admin`` for the quote/escape-evasion check).
    command = re.sub(
        r"((?:[A-Za-z]:)?(?:[\w.\-]+\\)+gh(?:\.exe|\.cmd|\.bat)?)",
        lambda m: m.group(1).replace("\\", "/"),
        command,
    )
    try:
        argv = shlex.split(command, posix=True, comments=False)
    except ValueError:
        # Unbalanced quotes: we cannot compute a real argv. Fall back to a whitespace
        # split (whole words, never substrings) so an obvious admin-merge still trips.
        argv = command.split()
    # Re-split each token on any embedded bare operator.
    flat: list[str] = []
    for tok in argv:
        for part in _OP_RE.split(tok):
            if part:
                flat.append(part)
    # Partition into command fragments on boundary tokens.
    frags: list[list[str]] = []
    cur: list[str] = []
    for tok in flat:
        if tok in _FRAG_BOUNDARIES:
            if cur:
                frags.append(cur)
                cur = []
        else:
            cur.append(tok)
    if cur:
        frags.append(cur)

    for frag in frags:
        i = 0
        saw_wrapper = False
        while i < len(frag):
            w = frag[i]
            if w in _RESERVED:
                i += 1
                continue
            if w.lower() in _PREFIXES:
                saw_wrapper = True
                i += 1
                continue
            if ("=" in w and not w.startswith("-")
                    and w.split("=", 1)[0].replace("_", "").isalnum()):
                i += 1
                continue
            break
        # Behind a wrapper we don't know its option arity, so scan every offset;
        # otherwise only the exact head can start the gh command.
        starts = range(i, len(frag)) if saw_wrapper else (i,)
        for s in starts:
            if _admin_merge_at(frag, s):
                return True
    return False


_DENY_REASON = (
    "Blocked by block_admin_merge_hook.py (bd polyglot-pdf-kibf): "
    "`gh pr merge --admin` bypasses the branch-protection / required-checks gate "
    "that the auto-merge policy (bd polyglot-pdf-16pj) depends on. Merge WITHOUT "
    "--admin after checks are green, or hand the PR to the maintainer."
)


def main() -> int:
    """Read the PreToolUse payload from stdin; deny an admin-merge, else pass through.

    Any failure to read/parse the payload, or any non-Bash / non-admin-merge call,
    exits 0 with no output -- the tool proceeds through the normal permission flow
    (which still enforces the settings.json denies). We NEVER emit an ``allow``
    decision, so this hook can only add a restriction.
    """
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, OSError):
        return 0
    if not isinstance(payload, dict):
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str):
        return 0
    if not command_is_admin_merge(command):
        return 0
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": _DENY_REASON,
        }
    }
    sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
