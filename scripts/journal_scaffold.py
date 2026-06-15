"""Emit a journal-entry skeleton (frontmatter + 5 sections) for a bead.

Background
----------
CLAUDE.md closeout item 3 requires a per-file journal entry at
`docs/journal/entries/YYYY-MM-DD-bd-<code>-<slug>.md` for every sprint, with:

  - YAML frontmatter: required `date`, `bead`, `title`, `tags`; optional
    `sprint`, `pr`.
  - A body with the standard five sub-sections: Trigger / What shipped /
    Lessons / Doc freshness / Files touched.

Hand-typing the frontmatter (and re-deriving the filename slug, the UTC date,
the bead id) every closeout is deterministic toil. This script reads the
bead's metadata via `bd show <id> --json` and emits the skeleton, leaving the
model to write only the prose -- the part that needs judgment. Zero model
tokens for the mechanics; the journal fork skill (bd e4dg) consumes a diff
summary, this fills the structure.

The script does NOT pick tags -- tags require judgment against the
controlled vocabulary in docs/journal/TAGS.md (a wrong tag is worse than a
placeholder). It emits a `tags: []` placeholder with a reminder comment so
the author fills it from TAGS.md.

Usage
-----
    python scripts/journal_scaffold.py <bead-id> [--sprint N] [--pr STR]
        [--date YYYY-MM-DD] [--out PATH] [--print]

By default it writes to docs/journal/entries/<date>-bd-<suffix>-<slug>.md and
prints the path. `--print` writes nothing and emits the skeleton to stdout
(useful for a skill that pipes it). `--date` overrides today's UTC date (the
default), `--out` overrides the computed path. It refuses to overwrite an
existing file (journal entries are append-only at the corpus level).

Exit codes: 0 success; 1 a failure (bd unavailable, bead not found, target
file already exists).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make this script's dir importable so `import swarm_config` works under both
# direct execution and importlib-based test loading (see bd_safe.py note).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import swarm_config  # noqa: E402

# bd emits UTF-8 (bead titles); --print writes the skeleton to stdout. A
# cp1252 Windows console would crash on a non-cp1252 glyph in a title, so
# reconfigure to UTF-8 with errors="replace" (Python 3.7+).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

EXIT_OK = 0
EXIT_FAIL = 1

SUBPROCESS_TIMEOUT_SEC = 60

# Anchor to the repo root (this file is <repo>/scripts/journal_scaffold.py),
# NOT the process cwd -- otherwise invoking the script from inside scripts/
# (or after a harness chdir) would silently write the entry to
# scripts/docs/journal/entries/ and lose it from the real journal.
ENTRIES_DIR = Path(__file__).resolve().parent.parent / "docs" / "journal" / "entries"

# Body skeleton: the five sub-sections CLAUDE.md closeout item 3 mandates,
# in order, each with a one-line prompt so the author knows what belongs
# there. Kept as plain ASCII (scar rule 9 -- this is a .py heredoc, not .md
# prose); the emitted FILE is .md and may carry richer prose once the author
# fills it.
BODY_TEMPLATE = """## Trigger

<!-- Why this work happened: the bead, the plan section it traces to, the
problem or request that kicked it off. -->

## What shipped

<!-- The concrete change. Design points, decisions, anything deferred (with
the bead id it was filed under). -->

## Lessons

<!-- What generalizes. If a lesson applies anywhere in the codebase, also add
a one-liner to the relevant docs/standards/*.md and cite this entry. -->

## Doc freshness

<!-- Which components/ or standards/ docs were bumped (or reviewed + left
as-is). Note any CLAUDE.md changes. -->

## Files touched

<!-- Bullet list of files created/edited, one line each. -->
"""


def _run_bd_show(bead_id: str) -> dict:
    """Return the bead's metadata dict via `bd show <id> --json`.

    `bd show --json` emits a JSON array (the bead plus any context); the
    target bead is the first element whose id matches. encoding/errors guard
    the Windows cp1252 decode crash on a non-cp1252 byte in a title.
    """
    try:
        proc = subprocess.run(
            ["bd", "show", bead_id, "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=SUBPROCESS_TIMEOUT_SEC,
            # Suppress any transient git.exe console window bd spawns against the
            # git-backed Dolt cache on Windows (bd polyglot-pdf-5k32).
            creationflags=swarm_config.windowless_creationflags(),
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("bd show {} timed out".format(bead_id))
    except OSError as exc:
        raise RuntimeError("could not run bd: {}".format(exc))
    if proc.returncode != 0:
        raise RuntimeError(
            "bd show {} failed: {}".format(
                bead_id, (proc.stderr or "").strip() or "no stderr"
            )
        )
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("bd show {} returned non-JSON: {}".format(bead_id, exc))

    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item.get("id") == bead_id:
                return item
        # Do NOT fall back to data[0]: `bd show --json` may return related
        # context beads, and using the wrong one silently writes a mismatched
        # `bead:` field (the cross-reference to the tracker) into the entry.
        # An exact-id miss is an error, not a "pick the first one" situation.
        raise RuntimeError(
            "bd show {} returned no bead with that exact id "
            "(got {} bead(s), none matching)".format(bead_id, len(data))
        )
    raise RuntimeError("bd show {} returned no matching bead".format(bead_id))


def _slugify(title: str) -> str:
    """Lowercase-kebab slug from a bead title, for the filename.

    Strips a leading "Swarm step N:" / "[bug]" style prefix is NOT done --
    the full title slug is more searchable. Non-alphanumerics collapse to a
    single hyphen; the result is trimmed and capped so filenames stay sane.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    # Cap length so the path doesn't blow past Windows limits; keep whole words.
    if len(slug) > 50:
        slug = slug[:50].rsplit("-", 1)[0]
    return slug or "entry"


def _id_suffix(bead_id: str) -> str:
    """Filename bead code: the segment after the last hyphen of the id."""
    return bead_id.rsplit("-", 1)[-1]


def build_skeleton(bead: dict, *, date: str, sprint: int | None, pr: str | None) -> str:
    """Assemble frontmatter + body. Title is quoted (may contain a colon)."""
    title = bead.get("title", "").replace('"', "'")
    lines = ["---", "date: {}".format(date), "bead: {}".format(bead["id"])]
    lines.append('title: "{}"'.format(title))
    if sprint is not None:
        lines.append("sprint: {}".format(sprint))
    if pr is not None:
        lines.append('pr: "{}"'.format(pr))
    # tags is REQUIRED but needs human judgment against TAGS.md -- emit an
    # empty list with a reminder rather than guessing a wrong tag.
    lines.append("tags: []  # 1-5 tags, verbatim from docs/journal/TAGS.md")
    lines.append("---")
    lines.append("")
    return "\n".join(lines) + "\n" + BODY_TEMPLATE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit a journal-entry skeleton for a bead."
    )
    parser.add_argument("bead_id", help="Full bead id, e.g. {}".format(swarm_config.example_bead_id()))
    parser.add_argument("--sprint", type=int, default=None, help="Sprint number (optional)")
    parser.add_argument("--pr", default=None, help="PR label for multi-PR sprints (optional)")
    parser.add_argument(
        "--date",
        default=None,
        help="YYYY-MM-DD; defaults to today's UTC date (the doc-freshness rule).",
    )
    parser.add_argument("--out", default=None, help="Override the output path.")
    parser.add_argument(
        "--print",
        dest="to_stdout",
        action="store_true",
        help="Print the skeleton to stdout instead of writing a file.",
    )
    args = parser.parse_args(argv)

    date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        print("ERROR: --date must be YYYY-MM-DD, got {!r}".format(date))
        return EXIT_FAIL

    try:
        bead = _run_bd_show(args.bead_id)
    except RuntimeError as exc:
        print("ERROR: {}".format(exc))
        return EXIT_FAIL

    skeleton = build_skeleton(bead, date=date, sprint=args.sprint, pr=args.pr)

    if args.to_stdout:
        sys.stdout.write(skeleton)
        return EXIT_OK

    if args.out:
        out_path = Path(args.out)
    else:
        slug = _slugify(bead.get("title", ""))
        out_path = ENTRIES_DIR / "{}-bd-{}-{}.md".format(
            date, _id_suffix(args.bead_id), slug
        )

    if out_path.exists():
        print(
            "ERROR: {} already exists; journal entries are append-only "
            "(write a new file, never overwrite).".format(out_path)
        )
        return EXIT_FAIL

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(skeleton, encoding="utf-8")
    print("WROTE: {}".format(out_path))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
