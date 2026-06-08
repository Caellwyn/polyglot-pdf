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

(The PR reviewer is OpenAI Codex. It AUTO-REVIEWS on PR open -- round 1 needs no
trigger (the "@codex review" nudge rides in the PR body); round 2+ re-reviews use
an "@codex review" comment posted by the closeout Step-7 loop, NOT by
`closeout_finish.py`. There is no reviewer-slug config to set; the Copilot
reviewer-API slug was removed at the Codex cutover, bd hrn.9.)

The kit's init script (`scripts/swarm_init.py`) writes swarm.config.json for
you; you normally never edit this file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

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
