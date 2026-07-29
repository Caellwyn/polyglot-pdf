"""Pick the fresh-eyes review model from diff size -- purely mechanical.

What this is
------------
A **deterministic, zero-model-token** router (plan Change #2, bd
polyglot-pdf-hrn.4 -- A/B arm B). It reads ``git diff --shortstat`` for the
branch vs the integration branch, sums insertions + deletions, and prints a
single model name on stdout:

  - ``haiku``   for a SMALL diff (<= the changed-line threshold, default 80);
  - ``sonnet``  otherwise.

That is the whole contract: **diff size in, model name out.** Closeout's
Step 5.5.b (item 1) captures the printed name and passes it to the fresh-eyes
subagent (``model: <picked>``) for the EARLY rounds. On a small diff the cheap
model does the first pass; the fresh-eyes prompt's self-escalation clause (the
JUDGMENT half of arm B) lets a Haiku run bump itself back to Sonnet when the
change is risky despite being short. (The FINAL clearing round is forced to Opus
by the closeout loop regardless of this router's output -- bd polyglot-pdf-dgoa,
clause 5; this router governs the early rounds only.) The split is deliberate:

  - **This script makes NO risk judgment.** Size is the only signal. Adding a
    "is this risky?" check here would force an extra expensive orchestrator
    turn on every small diff -- exactly the cost this router exists to avoid. The risk
    call happens INSIDE the fresh-eyes turn that was going to run anyway, by the
    cheap model (see ``.claude/agents/fresh-eyes-reviewer.md``).
  - **Size is a coarse proxy, on purpose.** A 5-line change to Gemini wiring is
    riskier than an 800-line docs reflow; the script can't know that, so it
    routes on the cheap-to-measure axis and leaves severity to the reviewer.

The session-wide ``CLAUDE_CODE_SUBAGENT_MODEL`` override forces every subagent to
one model regardless of this script, so when that env var is set the picker is
moot and closeout skips calling it.

Base ref
--------
Defaults to ``origin/dev`` (this repo's integration branch -- the same base the
fresh-eyes reviewer and the doc-freshness gate diff against). Override with
``--base`` for a different integration branch. The three-dot form
(``base...HEAD``) measures the diff introduced by THIS branch since it forked
from the base -- not unrelated commits that landed on the base meanwhile -- which
matches what a reviewer actually reads.

Worktree safety
---------------
``git diff`` runs against the repository containing the cwd, so invoking this
from a worktree measures THAT worktree's branch. (Unlike the path-resolving
scripts, there is no file to write, so there is no wrong-checkout hazard -- the
only output is the model name on stdout.)

Exit codes
----------
  0  a model name was chosen from a real shortstat and printed.
  1  the diff could not be measured (git failed, or the base ref is unknown).
     In that case the script STILL prints a usable model -- ``sonnet``, the
     safe/more-capable default -- so closeout never breaks on a routing hiccup,
     but the non-zero code lets a human notice the fallback. **Fail toward the
     capable model, never toward the cheap one:** a missed escalation is a
     worse failure than an unnecessary Sonnet pass.

Usage
-----
  python scripts/pick_review_model.py
  python scripts/pick_review_model.py --base origin/main --threshold 120
  python scripts/pick_review_model.py --shortstat " 3 files changed, 10 insertions(+)"
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys

# Changed-line threshold (insertions + deletions). A diff AT OR BELOW this many
# changed lines routes to the cheap model; anything larger gets Sonnet. 80 is
# the plan's "<= ~80 changed lines" figure -- a deliberately round, conservative
# cut chosen so the cheap model only sees genuinely small diffs. Exposed as
# --threshold for experiments. (It was once going to be tuned from the telemetry
# ledger's Haiku-escalation rate; that ledger was removed in bd polyglot-pdf-40r4,
# so retuning now means measuring escalations directly.)
DEFAULT_THRESHOLD = 80

# Fail toward the capable model: any measurement failure prints this, never the
# cheap one. A missed Sonnet escalation costs a real bug; an unnecessary Sonnet
# pass costs only tokens.
SAFE_FALLBACK_MODEL = "sonnet"

# The two model names this router emits. They are the short aliases Claude Code's
# subagent `model:` field accepts (haiku|sonnet|opus|<id>|inherit) -- closeout
# passes the printed value straight through as the fresh-eyes model.
CHEAP_MODEL = "haiku"
CAPABLE_MODEL = "sonnet"

# Matches the numeric prefixes git emits in `--shortstat`, e.g.
#   " 23 files changed, 2277 insertions(+), 346 deletions(-)"
# Insertions and deletions are each OPTIONAL: a delete-only change omits the
# insertions clause and vice versa (" 1 file changed, 5 deletions(-)"). We sum
# whichever are present; a wholly EMPTY shortstat (no diff) yields 0.
_INSERTIONS_RE = re.compile(r"(\d+)\s+insertion")
_DELETIONS_RE = re.compile(r"(\d+)\s+deletion")


def changed_lines(shortstat: str) -> int:
    """Return insertions + deletions parsed from a ``git diff --shortstat`` line.

    Empty/blank input (git's output for "no changes") -> 0. A shortstat with
    only insertions or only deletions counts just that side. The ``N files
    changed`` count is intentionally ignored -- the threshold is about how much
    a reviewer must read (lines), not how many files it spans.
    """
    if not shortstat or not shortstat.strip():
        return 0
    ins = _INSERTIONS_RE.search(shortstat)
    dels = _DELETIONS_RE.search(shortstat)
    total = 0
    if ins:
        total += int(ins.group(1))
    if dels:
        total += int(dels.group(1))
    return total


def pick_model(lines: int, threshold: int = DEFAULT_THRESHOLD) -> str:
    """Map a changed-line count to a model name. <= threshold -> cheap, else capable."""
    return CHEAP_MODEL if lines <= threshold else CAPABLE_MODEL


def get_shortstat(base: str) -> str:
    """Return ``git diff --shortstat <base>...HEAD`` output (stripped).

    Raises RuntimeError on any git failure (missing repo, unknown base ref, git
    not on PATH) so the caller can fall back deterministically rather than crash.
    The three-dot range measures the diff THIS branch introduced since it forked
    from ``base`` -- the same view the reviewer reads.
    """
    try:
        proc = subprocess.run(
            ["git", "diff", "--shortstat", "{}...HEAD".format(base)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("git diff --shortstat {}...HEAD timed out".format(base))
    except OSError as exc:
        raise RuntimeError("git could not run: {}".format(exc))
    if proc.returncode != 0:
        raise RuntimeError(
            "git diff --shortstat {}...HEAD failed (exit {}): {}".format(
                base, proc.returncode, proc.stderr.strip() or "no stderr"
            )
        )
    return proc.stdout.strip()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--base",
        default="origin/dev",
        help="Integration branch to diff against (default: origin/dev).",
    )
    p.add_argument(
        "--threshold",
        type=int,
        default=DEFAULT_THRESHOLD,
        help="Changed-line cutoff; <= this -> haiku, else sonnet "
        "(default: {}).".format(DEFAULT_THRESHOLD),
    )
    p.add_argument(
        "--shortstat",
        default=None,
        help="Use this literal shortstat string instead of running git "
        "(for tests / manual checks). Skips the git call entirely.",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Also print the changed-line count + reasoning to stderr.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.shortstat is not None:
        shortstat = args.shortstat.strip()
    else:
        try:
            shortstat = get_shortstat(args.base)
        except RuntimeError as exc:
            # Fail toward the capable model so a routing hiccup never silently
            # downgrades the review. Print sonnet (usable) but exit 1 so the gap
            # is noticeable.
            sys.stderr.write(
                "pick_review_model.py: {} -- falling back to {}.\n".format(
                    exc, SAFE_FALLBACK_MODEL
                )
            )
            print(SAFE_FALLBACK_MODEL)
            return 1

    lines = changed_lines(shortstat)
    model = pick_model(lines, args.threshold)
    if args.verbose:
        sys.stderr.write(
            "pick_review_model.py: {} changed line(s) (threshold {}) -> {}\n".format(
                lines, args.threshold, model
            )
        )
    print(model)
    return 0


if __name__ == "__main__":
    sys.exit(main())
