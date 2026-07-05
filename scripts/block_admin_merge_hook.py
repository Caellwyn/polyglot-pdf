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
second layer: it TOKENIZES the command with ``shlex`` (respecting quotes) and denies
only when ``--admin`` appears as a real standalone flag token on a ``gh pr merge``
invocation.

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


# Benign leading tokens that precede the REAL command head (skip and keep looking).
# ``!`` is shell negation, ``xargs`` runs its argument as a command -- both still RUN
# the merge (``! gh pr merge ... --admin`` / ``xargs gh pr merge ... --admin``).
_PREFIXES = frozenset(
    {"sudo", "env", "command", "nice", "nohup", "time", "exec", "!", "xargs"}
)
# Shell metacharacters that START a new command context. Used to SPLIT the raw
# command into candidate sub-commands so a `gh pr merge --admin` after ANY of them
# (a newline, ; && || | &, inside a ( ) / { } group, or a `...`/$(...) command
# substitution) is still evaluated as a head. Backtick is included so
# `` `gh pr merge --admin` `` fragments like $(...) does.
_SPLIT_RE = re.compile(r"(?:\|\||&&|;|\||&|\n|\(|\)|\{|\}|`)")


def _tokenize(sub: str) -> list[tuple[str, bool]]:
    """Tokenize one candidate sub-command into ``(text, was_quoted)`` pairs.

    ``shlex.split(posix=True)`` treats ``\\`` as an escape and mangles
    ``C:\\tools\\gh`` into ``C:toolsgh``. ``posix=False`` preserves backslashes but
    keeps surrounding quotes on tokens. We run posix=False (so Windows paths survive)
    and strip a single layer of matching surrounding quotes -- but we RECORD that the
    token was quoted, so a bare ``--body '--admin'`` value (unwraps to ``--admin``)
    is NOT mistaken for the real bare ``--admin`` flag. A quoted argument is never a
    flag; only an UNQUOTED ``--admin`` token is.
    """
    try:
        raw = shlex.split(sub, comments=False, posix=False)
    except ValueError:
        # Unbalanced quotes in this fragment: fall back to a whitespace split so we
        # still see whole words (never a substring match). These are unquoted.
        return [(tok, False) for tok in sub.split()]
    out: list[tuple[str, bool]] = []
    for tok in raw:
        if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in ("'", '"'):
            out.append((tok[1:-1], True))   # fully-quoted argument -> unwrap, mark quoted
        else:
            out.append((tok, False))
    return out


def _is_gh(tok: str) -> bool:
    """True if ``tok`` names the ``gh`` executable (bare, path-qualified, or a
    Windows shim: gh / */gh / *\\gh / gh.exe / gh.cmd / gh.bat)."""
    low = tok.lower()
    if low in ("gh", "gh.exe", "gh.cmd", "gh.bat"):
        return True
    # Path-qualified: last path segment (either separator) is a gh executable.
    seg = re.split(r"[\\/]", tok)[-1].lower()
    return seg in ("gh", "gh.exe", "gh.cmd", "gh.bat")


def command_is_admin_merge(command: str) -> bool:
    """True iff ``command`` runs ``gh pr merge`` with ``--admin`` as a standalone flag.

    Robust against the evasion/false-positive classes a naive check misses:
      - ``--admin`` as a substring inside a QUOTED argument (``--body 'see --admin'``)
        is NOT a flag -> allowed.
      - ``--admin`` mentioned in ANOTHER command's arguments (``git commit -m
        '...gh pr merge --admin...'``, ``echo``, ``grep``) is NOT a gh invocation ->
        allowed. (This is why the first version blocked its own commit.)
      - ``gh pr merge --admin`` after a shell boundary -- newline, ``;`` ``&&`` ``||``
        ``|`` ``&``, or inside ``( )`` / ``{ }`` grouping, or behind ``exec``/``sudo``/
        ``env`` prefixes or a ``VAR=val`` assignment, or via a Windows path
        (``C:\\tools\\gh``) or shim (``gh.cmd``) -- IS caught.

    Strategy: split the RAW command on shell boundaries first (so newlines and
    grouping start fresh command contexts), then for each fragment check whether its
    HEAD token (after skipping benign prefixes / env-assignments) is a ``gh`` exe
    followed by ``pr merge`` with an ``--admin`` / ``--admin=`` flag before the next
    boundary.
    """
    if not command:
        return False
    # A POSIX shell removes a backslash-newline line continuation before word
    # splitting, so ``gh pr merge 5 \<newline>--admin`` is really one command. Undo it
    # first, or the newline-split would orphan ``--admin`` into its own fragment.
    command = re.sub(r"\\\r?\n", " ", command)
    for fragment in _SPLIT_RE.split(command):
        frag = fragment.strip()
        if not frag:
            continue
        tokens = _tokenize(frag)  # list of (text, was_quoted)
        # Skip leading env-assignments (VAR=val) and benign command prefixes -- but
        # only UNQUOTED ones (a quoted 'sudo' is an argument, not a real prefix) --
        # to find the real head of THIS fragment. Once a prefix has been seen, also
        # skip that prefix's OWN option tokens (``sudo -u foo``, ``nice -n 10``): a
        # leading ``-flag`` (and the plain value that may follow it) belongs to the
        # prefix, not to the wrapped command -- otherwise ``sudo -u foo gh pr merge
        # --admin`` never reaches ``gh`` as the head.
        idx = 0
        seen_prefix = False
        while idx < len(tokens):
            text, quoted = tokens[idx]
            is_assignment = (
                not quoted and "=" in text and not text.startswith("-")
                and text.split("=", 1)[0].replace("_", "").isalnum()
            )
            if is_assignment or (not quoted and text.lower() in _PREFIXES):
                seen_prefix = seen_prefix or (not quoted and text.lower() in _PREFIXES)
                idx += 1
                continue
            # After a prefix, its own option flags (and a following non-option value)
            # are not the command head -- skip them and keep looking for ``gh``.
            if seen_prefix and not quoted and text.startswith("-"):
                idx += 1
                # `-u foo` / `-n 10`: consume a single following plain value if present
                # and it is not itself an option or the gh executable.
                if idx < len(tokens):
                    nxt_text, nxt_quoted = tokens[idx]
                    if (not nxt_quoted and not nxt_text.startswith("-")
                            and not _is_gh(nxt_text)):
                        idx += 1
                continue
            break
        head = tokens[idx:]
        # The head (gh / pr / merge) must all be UNQUOTED command words: a quoted
        # 'gh' 'pr' 'merge' would be literal argument text, not the invocation.
        if (len(head) >= 3
                and not head[0][1] and _is_gh(head[0][0])
                and head[1] == ("pr", False) and head[2] == ("merge", False)):
            for arg_text, arg_quoted in head[3:]:
                # Only an UNQUOTED --admin / --admin= is the real flag; a quoted
                # value that merely equals "--admin" (from --body '--admin') is not.
                if not arg_quoted and (arg_text == "--admin" or arg_text.startswith("--admin=")):
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
