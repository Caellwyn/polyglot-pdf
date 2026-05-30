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

# The prime output and the override both contain non-ASCII (e.g. the 🚨 emoji
# in the close-protocol heading). On Windows the default stdout codec is cp1252,
# which raises UnicodeEncodeError on those characters, so force UTF-8.
for _stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(_stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")


def main() -> int:
    # Pass through any flags the hook might supply (e.g. --memories-only on
    # PreCompact in MCP mode). Run from the repo root so bd resolves the
    # workspace consistently regardless of the session's cwd.
    result = subprocess.run(
        ["bd", "prime", *sys.argv[1:]],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)

    # Only append the close-protocol correction when prime actually emitted the
    # generic protocol it is meant to correct. --memories-only output omits it,
    # so appending there would be noise.
    if OVERRIDE.exists() and "SESSION CLOSE PROTOCOL" in result.stdout:
        sys.stdout.write("\n")
        sys.stdout.write(OVERRIDE.read_text(encoding="utf-8"))

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
