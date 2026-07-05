"""Tests for scripts/block_admin_merge_hook.py (bd polyglot-pdf-kibf).

The hook is the robust second layer behind the settings.json wildcard denies: it
tokenizes the Bash command and denies `gh pr merge --admin` regardless of flag
position or quoting, while never blocking a legitimate merge (or a `--admin`
substring that is only inside a quoted argument). These tests pin exactly that
contract -- including the evasion forms the wildcard deny cannot reliably catch.
"""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_HOOK_PATH = _REPO / "scripts" / "block_admin_merge_hook.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("block_admin_merge_hook", _HOOK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hook = _load_hook()


# --------------------------------------------------------------------------- #
# command_is_admin_merge -- the detection core
# --------------------------------------------------------------------------- #
BLOCK = [
    "gh pr merge 301 --admin",
    "gh pr merge --admin 301",
    "gh pr merge 301 --squash --admin",
    "gh pr merge --admin",
    "gh pr merge 301 --admin=true",
    "gh pr merge 301 --squash --admin --delete-branch",
    "FOO=bar gh pr merge 301 --admin",          # env prefix
    "/usr/bin/gh pr merge 301 --admin",         # path prefix
    "gh pr merge 301 --admin --match-head-commit abc",
    "sudo gh pr merge 301 --admin",             # benign command prefix
    "git fetch && gh pr merge 301 --admin",     # gh as head after a separator
    "false || gh pr merge 5 --admin",           # gh as head after ||
    # Evasion forms fresh-eyes found (all must be caught):
    "(gh pr merge 5 --admin)",                   # subshell
    "{ gh pr merge 5 --admin; }",                # brace group
    "! gh pr merge 5 --admin",                   # negation
    "exec gh pr merge 5 --admin",                # exec prefix
    "git fetch\ngh pr merge 301 --admin",        # embedded real newline
    "true; gh pr merge 5 --admin",               # after ;
    "echo hi | gh pr merge 5 --admin",           # after a pipe (contrived but a head)
    r"C:\tools\gh pr merge 5 --admin",           # Windows backslash path
    "/usr/bin/gh pr merge 5 --admin --admin",    # duplicate flag
    "gh.cmd pr merge 5 --admin",                 # Windows .cmd shim
    "gh.bat pr merge 5 --admin",                 # Windows .bat shim
    "GH_TOKEN=x FOO=y gh pr merge 5 --admin",    # multiple env assignments
    # Round-2 fresh-eyes bypasses (all must be caught):
    "`gh pr merge 5 --admin`",                    # backtick command substitution
    "$(gh pr merge 5 --admin)",                   # $(...) command substitution
    "xargs gh pr merge 5 --admin",               # xargs runs its argument as a command
    # Round-3 fresh-eyes: prefix carrying its own option flag/value, + line-continuation
    "sudo -u foo gh pr merge 5 --admin",         # sudo with -u value before gh
    "nice -n 10 gh pr merge 5 --admin",          # nice with -n value before gh
    "sudo -E gh pr merge 5 --admin",             # sudo with a valueless flag
    "gh pr merge 5 \\\n--admin",                 # backslash-newline line continuation
]
# OUT OF SCOPE (documented, not blocked): forms where the gh command is TEMPLATED or
# nested inside an opaque argument, which would need full recursive shell emulation
# to detect -- the settings.json wildcard denies remain the backstop for these:
#   - `bash -c "gh pr merge 5 --admin"` / `sh -c "..."`  (merge is a quoted -c arg)
#   - `xargs -I{} gh pr merge {} --admin`               (gh command is placeholder-templated)
#   - `GH=gh; $GH pr merge 5 --admin`                   (variable indirection)
OUT_OF_SCOPE = [
    'bash -c "gh pr merge 5 --admin"',
    "xargs -I{} gh pr merge {} --admin",
]

ALLOW = [
    "gh pr merge 301 --squash --match-head-commit abc123",   # the legit auto-merge
    "gh pr merge 301 --squash",
    "gh pr merge 301",
    "gh pr merge 301 --body 'do not use --admin here'",       # --admin only inside a quoted arg
    "gh pr comment 301 --body '--admin'",                     # not a merge
    "gh pr view 301",
    "git push origin dev",
    "gh pr merge 301 --administrator",                         # a DIFFERENT flag, not --admin
    # The false positive that blocked this hook's OWN commit: gh pr merge ... --admin
    # appearing as ARGUMENT TEXT to a different command must pass through.
    "git commit -m 'feat: block gh pr merge --admin via hook'",
    "echo 'gh pr merge 301 --admin'",
    "git commit -F /tmp/msg.txt",                             # message file mentions it, cmd does not
    "printf 'do not run gh pr merge --admin'",
    "grep -r 'gh pr merge --admin' scripts/",                 # searching for the string
    "gh pr merge 301 --admin-is-not-a-flag",                  # --admin as a prefix of a longer flag
    "gh pr merge 301 --administrator",                        # (repeat) longer flag, not --admin
    # gh pr merge mentioned as args to another command, after separators:
    "git fetch && git commit -m 'gh pr merge --admin note'",  # 2nd cmd is git commit, not gh
    "echo done; echo 'gh pr merge --admin'",                  # both sides are echo
    "cat file | grep 'gh pr merge --admin'",                  # piped into grep, not gh
    # The ValueError/whitespace-fallback false positive fresh-eyes found -- substrings
    # of other words must NOT match (pr<-prefer, merge<-mergetool, admin<-administrator):
    "gh prefer mergetool administrator config",
    "gh config set mergetool.prompt false",                  # merge substring, not a merge cmd
    # Round-2 fresh-eyes false positive: a quoted arg value that is EXACTLY --admin
    # is NOT the flag (it's the value of --body). Must PASS.
    "gh pr merge 301 --body '--admin'",
    "gh pr merge 301 --body \"--admin\"",
    "gh pr merge 301 --title '--admin' --body ok",
]


@pytest.mark.parametrize("command", BLOCK)
def test_admin_merge_is_detected(command):
    assert hook.command_is_admin_merge(command) is True, command


@pytest.mark.parametrize("command", ALLOW)
def test_non_admin_merge_is_allowed(command):
    assert hook.command_is_admin_merge(command) is False, command


@pytest.mark.parametrize("command", OUT_OF_SCOPE)
def test_templated_or_nested_forms_are_documented_out_of_scope(command):
    # These execute a merge but the gh command is nested/opaque/templated, which a
    # static head-matcher cannot resolve without emulating a shell. They are
    # DELIBERATELY not caught here; the settings.json wildcard --admin denies are the
    # backstop. This test pins the KNOWN boundary so a future change that accidentally
    # starts catching (or claims to catch) them is noticed and re-evaluated.
    assert hook.command_is_admin_merge(command) is False, command


def test_unbalanced_quotes_fall_back_conservative():
    # shlex cannot parse this; the conservative substring fallback should still
    # deny an obvious admin-merge rather than let a mangled bypass through.
    assert hook.command_is_admin_merge("gh pr merge 301 --admin 'oops") is True
    # ...but a non-merge unparseable string is not force-blocked.
    assert hook.command_is_admin_merge("echo 'unterminated") is False


# --------------------------------------------------------------------------- #
# main() -- the stdin/stdout hook contract
# --------------------------------------------------------------------------- #
def _run_main(monkeypatch, payload):
    """Feed `payload` (dict or raw str) to main() on stdin; return (rc, stdout)."""
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    monkeypatch.setattr("sys.stdin", io.StringIO(raw))
    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)
    rc = hook.main()
    return rc, buf.getvalue()


def test_main_denies_admin_merge(monkeypatch):
    rc, out = _run_main(monkeypatch, {
        "tool_name": "Bash",
        "tool_input": {"command": "gh pr merge 301 --admin"},
    })
    assert rc == 0
    decision = json.loads(out)["hookSpecificOutput"]
    assert decision["hookEventName"] == "PreToolUse"
    assert decision["permissionDecision"] == "deny"
    assert "kibf" in decision["permissionDecisionReason"]


def test_main_passes_through_legit_merge(monkeypatch):
    rc, out = _run_main(monkeypatch, {
        "tool_name": "Bash",
        "tool_input": {"command": "gh pr merge 301 --squash --match-head-commit abc"},
    })
    # Exit 0, NO output -> normal permission flow applies (we never emit "allow").
    assert rc == 0
    assert out == ""


def test_main_ignores_non_bash_tool(monkeypatch):
    rc, out = _run_main(monkeypatch, {
        "tool_name": "Edit",
        "tool_input": {"command": "gh pr merge 301 --admin"},  # not a Bash call
    })
    assert rc == 0
    assert out == ""


def test_main_survives_malformed_stdin(monkeypatch):
    rc, out = _run_main(monkeypatch, "not json at all {{{")
    assert rc == 0
    assert out == ""


def test_main_survives_missing_command(monkeypatch):
    rc, out = _run_main(monkeypatch, {"tool_name": "Bash", "tool_input": {}})
    assert rc == 0
    assert out == ""
