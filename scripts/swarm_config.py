"""Project-specific configuration for the claude-swarm-kit scripts.

The swarm scripts (bd_safe.py, pr_review_watcher.py, journal_scaffold.py,
closeout_housekeeping.py) are otherwise product-agnostic. The two values that
DO differ per project live here, resolved in this precedence order:

  1. Environment variable  (SWARM_REPO / SWARM_BEAD_PREFIX /
     SWARM_REVIEW_REVIEWER_SLUG) -- wins if set.
  2. swarm.config.json at the repo root  -- the committed per-project config.
  3. The hardcoded fallbacks below  -- last resort; edit them if you prefer
     not to ship a swarm.config.json.

`repo` is the GitHub "OWNER/REPO" slug (used by `gh pr list` / `gh pr create`).
`bead_prefix` is the beads issue-id prefix (e.g. "myproject" if ids look like
`myproject-ab12`); it is informational -- the scripts derive the branch-grep
suffix from the FULL id at runtime, so this is only used for help text and
validation hints.
`review_reviewer_slug` is the bot login requested via the GitHub reviewer API
to fire an automated PR code review (see the fallback comment below for why this
is a reviewer request, NOT a comment mention).

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
# The PR-review bot requested via the GitHub reviewer API (NOT a comment
# mention). Requesting this bot as a reviewer fires Copilot CODE REVIEW; posting
# an "@copilot please review" COMMENT instead invokes the Copilot CODING AGENT
# (clones the repo, runs MCP servers, commits) -- the wrong product (bd
# polyglot-pdf-1pr, confirmed on throwaway PR #74). To switch reviewers later
# (e.g. Codex, bd hrn.9) set SWARM_REVIEW_REVIEWER_SLUG or the config key; the
# closeout glue + watcher are otherwise reviewer-agnostic.
_FALLBACK_REVIEW_REVIEWER_SLUG = "copilot-pull-request-reviewer[bot]"

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


def review_reviewer_slug() -> str:
    """Bot login requested via the GitHub reviewer API to fire a PR code review.

    Env > config file > fallback. Default is Copilot's review bot. NOTE: this is
    requested as a REVIEWER (POST .../requested_reviewers), never @-mentioned in a
    comment (a comment routes to the coding agent -- bd polyglot-pdf-1pr).
    """
    return (
        os.environ.get("SWARM_REVIEW_REVIEWER_SLUG", "").strip()
        or _config.get("review_reviewer_slug", "").strip()
        or _FALLBACK_REVIEW_REVIEWER_SLUG
    )


def example_bead_id() -> str:
    """A representative bead id for help text, e.g. 'myproject-ab12'."""
    return "{}-ab12".format(bead_prefix())
