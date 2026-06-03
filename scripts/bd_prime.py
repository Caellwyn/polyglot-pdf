#!/usr/bin/env python3
"""SessionStart/PreCompact hook wrapper around ``bd prime``.

Why this exists
---------------
The generic ``bd prime`` output ends with a "SESSION CLOSE PROTOCOL" block whose
checklist is ``git status`` -> ``git add`` -> ``git commit`` -> ``git push`` and
declares "Work is not done until pushed." For polyglot-pdf that is **stale and
misleading**: the repo ships through reviewed PRs into ``dev`` driven by the
``/closeout`` skill, never a local merge to ``main`` and never a bare
``git push`` as the finish line (bd polyglot-pdf-4ln).

We cannot edit the generic block in place, and ``bd``'s only override knob
(``.beads/PRIME.md``) replaces the ENTIRE output -- which would silently drop the
``bd remember`` persistent-memories block that prime injects. So instead we run
``bd prime`` unchanged (memories + full command reference intact) and append a
project-specific correction that supersedes the generic close protocol.

The override text lives in ``.claude/prime-closeout-override.md`` (tracked, so it
is reviewable/version-controlled). We resolve it relative to THIS file, not the
process cwd, so the hook behaves identically from a git worktree.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OVERRIDE = REPO_ROOT / ".claude" / "prime-closeout-override.md"
BOOTSTRAP = REPO_ROOT / "scripts" / "beads_remote_bootstrap.py"
# Written by beads_remote_bootstrap.py only after a successful hydrate from
# refs/dolt/data. In a remote container its presence is the authoritative
# "live store is here" signal (see _beads_unhydrated).
HYDRATION_MARKER = REPO_ROOT / ".beads" / ".cache" / ".hydrated"


def _is_remote_container() -> bool:
    """True in an ephemeral remote/web container (authenticated local-proxy git
    origin with the ``local_proxy@`` username marker). There, the committed
    .beads/issues.jsonl is never authoritative."""
    try:
        p = subprocess.run(
            ["git", "remote", "get-url", "origin"], cwd=REPO_ROOT,
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
    return "local_proxy@" in (p.stdout or "")


def _store_empty_or_broken() -> bool:
    """True when bd cannot open the DB at all, or opens an *empty* store. The empty
    case matters -- ``bd prime`` (which we just ran) auto-creates an empty,
    perfectly-openable DB, so a fresh container looks "fine" while pointing at zero
    issues. Any probe failure is treated as un-hydrated."""
    try:
        p = subprocess.run(
            ["bd", "stats", "--json"], cwd=REPO_ROOT,
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return True
    if p.returncode != 0 or not (p.stdout or "").strip():
        return True
    try:
        import json
        return int(json.loads(p.stdout)["summary"]["total_issues"]) == 0
    except Exception:  # noqa: BLE001
        return True


def _beads_unhydrated() -> bool:
    """True when this container's beads store isn't the live one.

    In a **remote container**, require a successful bootstrap (the hydration
    marker) regardless of issue count: a stale committed .beads/issues.jsonl can
    make bd report a populated-but-outdated store, so "issues > 0" is NOT enough --
    only the marker proves the live refs/dolt/data store was hydrated. Elsewhere
    (the maintainer's local checkout, or an already-bootstrapped remote container)
    fall back to flagging just a genuinely empty/unopenable store, so a populated
    local never trips the banner."""
    if _is_remote_container() and not HYDRATION_MARKER.exists():
        return True
    return _store_empty_or_broken()


def _bootstrap_banner() -> str:
    return (
        "\n"
        "============================================================\n"
        "BEADS STORE NOT HYDRATED IN THIS CONTAINER\n"
        "------------------------------------------------------------\n"
        "This remote/web container does not yet hold the live beads\n"
        "store (refs/dolt/data). Any issues shown so far may be EMPTY\n"
        "or a STALE committed snapshot -- not the current tracker.\n"
        "Hydrate first, then `bd ready` / `bd show` reflect the truth:\n"
        "\n"
        "    python scripts/beads_remote_bootstrap.py\n"
        "\n"
        "After that, ALWAYS `bd dolt pull` before `bd ready` and before\n"
        "any push -- other sessions write concurrently; the local store\n"
        "is only a cache, never trusted between operations.\n"
        "\n"
        "(Ignore any \"No git remote configured\" line above -- this repo\n"
        "DOES sync beads, through refs/dolt/data over the git origin.)\n"
        "Details: docs/components/beads-remote-bootstrap.md\n"
        "============================================================\n"
    )

# bd is given this long to emit prime context before we treat it as hung. Prime
# is a fast local read, so a generous ceiling still bounds a wedged session.
BD_TIMEOUT_SEC = 30

# The prime output and the override both contain non-ASCII (e.g. the 🚨 emoji
# in the close-protocol heading). On Windows the default stdout codec is cp1252,
# which raises UnicodeEncodeError on those characters. Force UTF-8 with
# errors="replace" so a rare un-encodable byte degrades to a placeholder instead
# of crashing the hook. reconfigure() exists on 3.7+ TextIO streams but can be
# absent (older/3rd-party streams) or raise on a detached/redirected stream, so
# guard both -- this is a SessionStart/PreCompact hook and must never hard-fail.
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        try:
            _reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def main() -> int:
    # Pass through any flags the hook might supply (e.g. --memories-only on
    # PreCompact in MCP mode). Run from the repo root so bd resolves the
    # workspace consistently regardless of the session's cwd. Degrade gracefully
    # on any failure: a hook that crashes with a traceback is worse than one that
    # emits a one-line note and lets the session start. errors="replace" guards
    # against non-UTF8 bytes in bd's output.
    try:
        result = subprocess.run(
            ["bd", "prime", *sys.argv[1:]],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=BD_TIMEOUT_SEC,
        )
    except FileNotFoundError:
        sys.stderr.write(
            "bd_prime.py: 'bd' not found on PATH -- install beads or activate "
            "the right environment; skipping prime context.\n"
        )
        return 1
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            f"bd_prime.py: 'bd prime' did not finish within {BD_TIMEOUT_SEC}s; "
            "skipping prime context.\n"
        )
        return 1

    sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)

    # If the beads store is not usable here (fresh/empty remote container), emit
    # one actionable bootstrap instruction. The bootstrap is idempotent, so a rare
    # false positive is harmless. Only when the helper actually exists.
    if BOOTSTRAP.exists() and _beads_unhydrated():
        sys.stdout.write(_bootstrap_banner())

    # Only append the close-protocol correction when prime actually emitted the
    # generic protocol it is meant to correct. --memories-only output omits it,
    # so appending there would be noise.
    if OVERRIDE.exists() and "SESSION CLOSE PROTOCOL" in result.stdout:
        sys.stdout.write("\n")
        sys.stdout.write(OVERRIDE.read_text(encoding="utf-8"))

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
