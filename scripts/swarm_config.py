"""Project-specific configuration for the claude-swarm-kit scripts.

The swarm scripts (bd_safe.py, pr_review_watcher.py, journal_scaffold.py,
closeout_housekeeping.py) are otherwise product-agnostic. The two values that
DO differ per project live here, resolved in this precedence order:

  1. Environment variable  (SWARM_REPO / SWARM_BEAD_PREFIX) -- wins if set.
  2. swarm.config.json at the repo root  -- the committed per-project config.
  3. The hardcoded fallbacks below  -- last resort; edit them if you prefer
     not to ship a swarm.config.json.

`repo` is the GitHub "OWNER/REPO" slug (used by `gh pr list` / `gh pr create`).
`bead_prefix` is the beads issue-id prefix (e.g. "myproject" if ids look like
`myproject-ab12`); it is informational -- the scripts derive the branch-grep
suffix from the FULL id at runtime, so this is only used for help text and
validation hints.

(There is NO external PR reviewer and no reviewer-slug config. Review is entirely
Claude-based and runs PRE-PR -- a fresh-eyes inner loop then one outer
adversarial pass (Opus for a source diff, Haiku for docs-only, none for
trivial), both on the local branch, before the PR opens (see
`docs/doctrine/review-flow.md`). The OpenAI Codex reviewer -- and Copilot before
it -- are retired (the maintainer's Codex subscription ended 2026-07-08); no bot
reads the PR.)

The kit's init script (`scripts/swarm_init.py`) writes swarm.config.json for
you; you normally never edit this file.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# On Windows, Python subprocess.run(["bd", ...]) cannot execute .CMD shims
# (they need the Windows shell), so it falls through to whichever bd.exe
# appears first in the subprocess PATH -- which may be an older standalone
# installer. The npm-installed bd package ships its own bd.exe under
# node_modules/@beads/bd/bin/; prepend that directory so subprocess always
# uses the npm-installed version when present. No-op on Linux/Mac (the path
# doesn't exist there). Runs at import time so every script that does
# `import swarm_config` gets the fix automatically.
_NPM_BD_BIN = os.path.join(
    os.path.expanduser("~"),
    "AppData", "Roaming", "npm", "node_modules", "@beads", "bd", "bin",
)
if os.path.isfile(os.path.join(_NPM_BD_BIN, "bd.exe")) or os.path.isfile(
    os.path.join(_NPM_BD_BIN, "bd")
):
    os.environ["PATH"] = _NPM_BD_BIN + os.pathsep + os.environ.get("PATH", "")

# Windows console-window suppression for spawned bd/dolt/git subprocesses.
#
# A `bd dolt push`/`pull` against this repo's git-backed Dolt remote
# (git+https://...) makes dolt shell out to git.exe once per chunk during a
# noms "conjoin" (git cat-file -s <hash>). On Windows every one of those
# console-subsystem grandchildren (bd.exe -> dolt.exe -> git.exe) pops a
# visible console window, and a conjoin can fire dozens at once -- the storm
# that grinds the desktop to a halt (bd polyglot-pdf-5k32). The spawner is
# third-party Go/Node code we cannot patch, but CREATE_NO_WINDOW on the
# top-of-tree spawn we DO own (Python -> bd) starts bd with no console; its
# dolt/git descendants then inherit "no console" and allocate no window.
# CREATE_NO_WINDOW (not DETACHED_PROCESS) is the right flag here: it suppresses
# the window without disturbing the captured stdout/stderr pipes the callers
# rely on. No-op off Windows (the flag does not exist there).
def windowless_creationflags() -> int:
    """subprocess creationflags that suppress child console windows on Windows.

    Returns subprocess.CREATE_NO_WINDOW on Windows, else 0. Pass straight into
    subprocess.run(..., creationflags=windowless_creationflags()) -- this is
    the single lever that keeps a bd/dolt/git conjoin from spawning dozens of
    visible console windows (bd polyglot-pdf-5k32).
    """
    if sys.platform == "win32":
        # CREATE_NO_WINDOW is present on every Windows Python that ships the
        # _winapi-backed subprocess flags (3.7+); guard with getattr so a
        # surprise build degrades to 0 (windows reappear) rather than crashing.
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


# Last-resort fallbacks. The init script normally writes swarm.config.json so
# these are never reached; left as obvious placeholders so a misconfigured
# project fails loudly rather than silently targeting the wrong repo.
_FALLBACK_REPO = "OWNER/REPO"
_FALLBACK_BEAD_PREFIX = "project"

_CONFIG_FILENAME = "swarm.config.json"


def _load_config_file() -> dict:
    """Read swarm.config.json from the repo root, or {} if absent/unreadable.

    The repo root is found by walking up from this file until a directory
    containing swarm.config.json (or a .git) is found, so the scripts work
    from any cwd (worktrees included).
    """
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        candidate = parent / _CONFIG_FILENAME
        if candidate.is_file():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
    return {}


_config = _load_config_file()


def repo() -> str:
    """GitHub OWNER/REPO slug. Env > config file > fallback."""
    return (
        os.environ.get("SWARM_REPO", "").strip()
        or _config.get("repo", "").strip()
        or _FALLBACK_REPO
    )


def bead_prefix() -> str:
    """Beads issue-id prefix (informational). Env > config file > fallback."""
    return (
        os.environ.get("SWARM_BEAD_PREFIX", "").strip()
        or _config.get("bead_prefix", "").strip()
        or _FALLBACK_BEAD_PREFIX
    )


def example_bead_id() -> str:
    """A representative bead id for help text, e.g. 'myproject-ab12'."""
    return "{}-ab12".format(bead_prefix())
