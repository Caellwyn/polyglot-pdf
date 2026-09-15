"""Scan tier-1 + tier-2 docs for staleness AND enforce the sprint-archive protocol.

This script does the following warn-only checks in one pass (deliberately
count-free -- bd polyglot-pdf-nlbck -- see the "Why every check lives in one
script" paragraph below):

1. **Doc freshness.** Each tier-1 doc (TIER1_DOCS: CLAUDE.md, docs/INDEX.md,
   docs/technical_guide.md) and each `docs/components/*.md` /
   `docs/standards/*.md` / `docs/doctrine/*.md` may declare a `**Tracks:**`
   line listing space- or comma-separated paths or globs of code it owns, plus a
   `*Last updated: YYYY-MM-DD*` line near the top. Compares the doc's
   **claimed** "last updated" date (parsed from the `*Last updated:*`
   line) to each tracked file's last commit timestamp; flags docs whose
   tracked code is newer than the stamp. Tier-1 docs without a `**Tracks:**`
   line are simply skipped (same as tier-2).

2. **Sprint-archive protocol.** Sprint plan files at `docs/sprint_*.md`
   should be archived to `docs/archive/` once the sprint ships, with a
   row added to `docs/archive_completed_plans.md`. The closeout-checklist
   step that owns this was silently skipped 11 sprints in a row before
   it was made a numbered item (CLAUDE.md sprint closeout step 5). To
   prevent re-drift: this script also diffs the actual `docs/sprint_*.md`
   files at root against the "Active sprint plans" row in `docs/INDEX.md`
   and warns on orphans (at root but unlisted — closeout missed) or
   missing files (listed but absent — stale INDEX reference).

3. **Doc conventions.** No `Previously:`/`Prior:`/`Earlier:` chronological
   chains and no "history section" headings in tier-1/tier-2 docs -- see
   `check_doc_conventions` for the full rationale.

4. **Code-citation bounds** (bd polyglot-pdf-3pii5). A `` `file.py:N` ``
   citation whose line number has run past the cited file's current EOF --
   the mechanical, false-positive-safe half of catching citation drift; see
   `check_code_citations` for why it deliberately does NOT try to verify a
   citation points at the SPECIFIC construct its prose names.

Why every check lives in one script, not one script per check: they're
all facets of the same doc discipline, and they all want the same hook
(warn-only on every commit, full sweep at sprint closeout). Splitting
them into separate scripts would duplicate the argparse/exit-code/print
plumbing across each one; co-locating them means the closeout
`python scripts/check_doc_freshness.py` invocation already covers all of
them -- deliberately count-free phrasing (bd polyglot-pdf-82rzp), so
adding a fifth check here never requires updating this paragraph.

Why parse the stamp instead of using the doc's git commit time? Because the
sprint-closeout checklist tells the user to "bump its *Last updated:* line"
to fix staleness — the script needs to actually trust that line. Using the
doc's git commit time has a confusing failure mode: a docs commit that
includes both a code edit AND a doc bump still flags as stale on the next
run because both touch the same commit and the comparison is `file_ct >
doc_ct`. Parsing the stamp keeps the user's mental model honest: bump the
date, get a green check.

Fallback: if the doc has no parseable `*Last updated:* YYYY-MM-DD*` line,
the script falls back to the doc's git commit time.

FRESHNESS ACKS (bd polyglot-pdf-fytzi). A doc is fresh if it was EDITED after
its code changed OR explicitly REVIEWED after its code changed. The second is
what `--ack` records, in `docs/freshness/<slug>.ack`. It exists because the
honest action -- reading a doc and finding it still correct -- previously left
the stale flag ON (the only ways to clear it were a stamp bump, which
conflicted between parallel PRs, or a no-op doc commit). So the flag stopped
being read: 24 of the 28 tracked docs are stale.

The ack's timestamp is the ACK FILE'S OWN commit time, never a SHA recorded
inside it. This repo squash-merges, so a branch commit never joins dev's
history and a SHA-anchored ack would be orphaned the moment its PR merged; a
tracked file's `git log -1` resolves to the squash commit on dev instead.
An ack is NOT permanent: once tracked code commits past the ack, the doc is
stale again.

Modes:
  --all (default)  scan every doc; print each stale doc + the offending
                   newer code paths. Used by the sprint closeout checklist.
  --staged         scan only docs whose tracked code is in the current git
                   staging area.
  --ack DOC --because "..."
                   record that DOC was reviewed and is still accurate.
                   --because is MANDATORY; the tool auto-fills which tracked
                   files were stale, so the review is visible in the diff.

The sprint-archive check runs in BOTH modes — it's cheap (two filesystem
listings + one regex) and the orphan signal is worth surfacing on every
commit, not just at closeout.

Exit code: always 0 -- warn-only, never blocks. The real consumer is the
sprint-closeout checklist, which treats the output as a triage list. (There is
NO pre-commit hook wired in this repo; earlier revisions of this docstring said
otherwise and were wrong -- bd polyglot-pdf-olphy removes the matching claim
from doc-architecture.md.)

Usage:
  python scripts/check_doc_freshness.py
  python scripts/check_doc_freshness.py --staged
  python scripts/check_doc_freshness.py --all --quiet  # suppress "OK" lines
  python scripts/check_doc_freshness.py --ack docs/standards/x.md --because "..." 

Notes:
- Tracked-file timestamps come from `git log -1 --format=%ct <path>`, not
  filesystem mtimes — mtimes are unreliable across worktrees, clones, and
  fresh checkouts.
- Glob expansion uses pathlib's `Path.rglob` semantics — `app/routes/*.py`
  matches one level, `app/**/*.py` matches recursively. Both are accepted.
- A doc with no tracked files (no `**Tracks:**` line) is silently skipped.
- `**Tracks:**` tokens may be space- OR comma-separated; trailing commas are
  stripped so `` `a.py`, `b.py` `` parses to two clean tokens.
- A tracked path that doesn't exist (typo, deleted file) is reported as a
  warning so the doc gets fixed.
- The stamp is parsed at day-granularity; the script treats the stamp as
  **end-of-day UTC** so a same-day code commit doesn't false-flag, AND so
  the result is deterministic across developer machines and CI (using
  local time would produce different stale/ok verdicts in different
  timezones).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Suppress the child console window every git.exe spawn opens on Windows
# (bd polyglot-pdf-5k32 / bd polyglot-pdf-rdftu). This mirrors
# swarm_config.windowless_creationflags(); it is duplicated rather than
# imported because importing swarm_config has a PATH side effect and this
# script runs from a git hook where an import failure must never be fatal.
# getattr guards a surprise Python build: degrade to 0 (windows reappear)
# rather than crash.
def windowless_creationflags() -> int:
    """subprocess creationflags that suppress child console windows on Windows."""
    if sys.platform == "win32":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0

DOC_DIRS = ["docs/components", "docs/standards", "docs/doctrine"]
# Freshness ACKS -- the cheap "I reviewed this doc; it is still accurate"
# record (bd polyglot-pdf-fytzi).
#
# WHY A FILE AND NOT A SHA. This repo squash-merges every PR, so a branch
# commit never joins dev's history: a recorded branch SHA is orphaned the
# moment its own PR merges, and an ack keyed on one would go permanently
# false-stale exactly when it started mattering. A tracked FILE has no such
# problem -- `git log -1 <file>` resolves to the SQUASH commit on dev, which
# is a real ancestor. Verified against tests/test_technical_guide_routes_table.py,
# added on a branch and squashed as PR #622. So the ack's timestamp comes
# from the ack file itself; the SHA inside it is a human breadcrumb only and
# is never compared.
#
# NOT dot-prefixed: a `.freshness/` directory risks gitignore shadowing and
# is invisible to anyone browsing the tree. test_doc_freshness.py pins that
# this path is not ignored -- a silently-ignored ack dir would fail in the
# worst direction (acks vanish on merge, docs look stale, trust erodes).
ACK_DIR = "docs/freshness"
ACK_SUFFIX = ".ack"
# Path separator in a flattened ack filename. Must be a character that cannot
# appear in a doc path component, or the doc -> ack mapping stops being
# injective and one doc's ack can clear another's staleness. See ack_path().
ACK_SEP = "~"
TRACKS_RE = re.compile(r"\*\*Tracks:\*\*\s*(.+)$", re.MULTILINE)
# Match *Last updated: YYYY-MM-DD ...* (anything after the date is fine —
# some docs include a parenthetical sprint annotation).
LAST_UPDATED_RE = re.compile(
    r"^\*Last updated:\s*(\d{4})-(\d{2})-(\d{2})", re.MULTILINE
)
# Forbidden patterns on tier-1 + tier-2 docs (current-state only):
# - `Previously:` / `Prior:` / `Prior,` / `Earlier:` / `Earlier,` followed
#   (within a short lookahead) by a YYYY-MM-DD date, "Sprint NN", "same
#   day"/"same week", or a bead-id reference (a backtick-quoted token, e.g.
#   "bd `polyglot-pdf-x`", or a bare hyphenated token, e.g. "bd
#   polyglot-pdf-x" -- bead ids always contain a hyphen, which is what lets
#   this alternative avoid matching an ordinary word like "bd is the
#   tracker"). This shape is the chronological-narrative pattern we want to
#   ban (both stamp chains AND rationale-section prose that strings sprint
#   events together) -- doc-architecture.md section 3 is explicit that the
#   rule covers the PATTERN, not just the `Previously:` spelling, and four
#   real docs shipped `Earlier:`/`Earlier,`/`Prior,` chains this regex missed
#   before it was widened (bd polyglot-pdf-6dn2n/cqyke/f6wb6/riffn -- the
#   found shapes were "Earlier, bd polyglot-pdf-6x1j: ..." and "Prior, same
#   day (bd ...)", NOT followed by a literal date, which is why the date-only
#   follow-up was widened to also cover a bead-id or same-day/week
#   reference). Bare references like "(do NOT chain `Previously:` prose)" or
#   pedagogical mentions in CLAUDE.md itself are exempt because they don't
#   have this follow-up shape; ordinary prose use of "earlier"/"prior" (e.g.
#   "an earlier version", "earlier same-week changes") is exempt because the
#   word is never immediately followed by `:`/`,`.
#   KNOWN ACCEPTED RISK (bd polyglot-pdf-gz7dv): "Prior:"/"Earlier:" directly
#   followed by literal "same day"/"Sprint N" prose is indistinguishable from
#   a real chain by local pattern matching alone -- e.g. "Prior: same day we
#   shipped this" would still false-positive. Zero such occurrences exist in
#   the current corpus; a future false positive is a one-line rephrase, not a
#   blocker, so this risk is accepted rather than narrowed further (a tighter
#   regex would also risk missing real chains of that exact shape).
# - Section headers like `## Update history` / `## Recent sprint history` /
#   `## Changelog` / `## Sprint history` (any heading level >= 2). Other
#   "Sprint ..." headings (e.g. `## Sprint test retirement`) are NOT
#   matched -- only the specific historical-narrative slugs.
PREVIOUSLY_CHAIN_RE = re.compile(
    r"\b(?:Previously|Prior|Earlier)[:,]\s*"
    r"(?:\d{4}-\d{2}-\d{2}"
    r"|Sprint\s+\d"
    r"|same[\s-](?:day|week)"
    r"|bd\s+`[\w-]+`"
    r"|bd\s+[\w]+-[\w-]+"
    r")",
    re.IGNORECASE,
)
HISTORY_HEADING_RE = re.compile(
    r"^##+\s+(?:Recent\s+sprint\s+history|Update\s+history|Changelog|Sprint\s+history)\b",
    re.MULTILINE | re.IGNORECASE,
)
# Tier-1 docs (under docs/) plus CLAUDE.md at the repo root.
# Tier-2 docs are covered by DOC_DIRS.
# The kit template ships the first three; add your own project-wide docs
# (product vision, testing guide, etc.) here as you create them -- each is
# checked for the current-state-only discipline (no `Previously:` chains,
# no history sections).
TIER1_DOCS = [
    "CLAUDE.md",
    "docs/INDEX.md",
    "docs/technical_guide.md",
]
# doc-architecture.md is deliberately NOT in TIER1_DOCS: TRACKS_RE.search()
# takes the FIRST `**Tracks:**` mention in the file, which is its own intro
# prose ("...carries no `**Tracks:**` line because it owns no code path"),
# NOT the fenced **Tracks:** example syntax further down (that's the third
# match and is never reached) -- either way, parse_tracks() would try to
# freshness-check the trailing prose words as if they were globs (e.g.
# "line", "because", "it", "owns", "no"). But it IS the file that DEFINES
# the current-state-only rule, so it must still be covered by the CONVENTION
# scan (no Previously:/Prior:/Earlier: chains, no history sections) even
# though it skips the freshness-staleness half. It was exempt from BOTH
# checks before this line (bd polyglot-pdf-r8d9r).
CONVENTION_ONLY_DOCS = [
    "docs/doc-architecture.md",
]

# --- Sprint-archive check constants ---
INDEX_MD = REPO_ROOT / "docs" / "INDEX.md"
DOCS_DIR = REPO_ROOT / "docs"
# The "Active sprint plans" row in INDEX.md's "Architecture & process" table.
# Match the whole row by anchoring on the literal `sprint_<N>_<slug>_plan.md`
# cell WHEREVER it appears in the row. The real INDEX.md row leads with a
# `**Active sprint plans**` label cell and carries the literal in the SECOND
# cell, so the old anchor (start-of-row immediately followed by the literal)
# never matched and the checker always warned (bd polyglot-pdf-rt4). We now
# require the literal to follow a cell boundary (`|` + optional whitespace)
# anywhere in a table row -- that keeps it a real cell (not prose mentioning
# the template name) while being position-agnostic.
ACTIVE_PLAN_ROW_RE = re.compile(
    r"^\|(?:.*\|)?\s*`sprint_<N>_<slug>_plan\.md`.*$",
    re.MULTILINE,
)
# Within that row, pull out plan basenames from `](...)` href targets.
# A href is "active at root" if the path doesn't start with `archive/` —
# rows often mention archive/* paths as context ("Completed plans live in
# archive/...") and those don't count as claims of currently-active plans.
PLAN_HREF_RE = re.compile(r"\]\(([^)]*)\)")


# Last-commit times for EVERY path in history, resolved in ONE git invocation.
# None until the first git_commit_time() call populates it (see _commit_times).
_COMMIT_TIME_CACHE: dict[str, int] | None = None


def _commit_times() -> dict[str, int]:
    """Map repo-relative posix path -> unix time of the commit that last touched it.

    ONE `git log` walk for the whole repo, not one `git log -1` per file. The
    per-file shape was quadratic in practice -- this script checks N docs and
    each doc tracks M files, so a real run spawned 263 git.exe processes and
    took 48.7s. On Windows every one of those is a visible console window, and
    under that load they start failing with "Not enough memory resources are
    available"; that is the terminal cascade of bd polyglot-pdf-rdftu (same
    shape as the bd/dolt conjoin in bd polyglot-pdf-5k32). The single walk is
    0.6s for this repo's full history.

    `git log --name-only` lists commits newest-first, so the FIRST time a path
    appears is its last-commit time -- hence setdefault, never overwrite.

    A path missing from the map has no commit touching it (untracked, or new in
    the working tree); callers treat that as None exactly as before.
    """
    global _COMMIT_TIME_CACHE
    if _COMMIT_TIME_CACHE is not None:
        return _COMMIT_TIME_CACHE
    times: dict[str, int] = {}
    try:
        result = subprocess.run(
            ["git", "log", "--format=C%ct", "--name-only"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            creationflags=windowless_creationflags(),
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        # No git, or not a repo. Every lookup then reports "no commit time",
        # which callers already handle (the doc falls back to its
        # *Last updated:* stamp, or is reported as not-yet-committed).
        _COMMIT_TIME_CACHE = times
        return times
    ct: int | None = None
    for line in result.stdout.splitlines():
        # Commit header lines are our own "C<digits>" sentinel. A PATH could
        # theoretically look like that too, so require the whole line to match
        # rather than just the prefix.
        if line.startswith("C") and line[1:].isdigit():
            ct = int(line[1:])
            continue
        name = line.strip()
        if name and ct is not None:
            times.setdefault(name, ct)
    _COMMIT_TIME_CACHE = times
    return times


# Prefix-max over the commit-time map, memoized per directory. Kept separate
# from _COMMIT_TIME_CACHE (exact paths) so a directory can never shadow a file.
_DIR_TIME_CACHE: dict[str, int | None] = {}


def _dir_commit_time(rel: str) -> int | None:
    """Newest commit time of anything UNDER directory `rel`, or None if empty.

    `git log -1 -- <dir>` reports the last commit touching anything in that
    tree, and a **Tracks:** token is allowed to name a directory (expand_token
    returns a non-glob path that merely exists, which includes directories).
    The flat name->time map only holds FILES, so a directory token must be
    answered by scanning for paths under it -- otherwise every directory token
    silently resolved to "no commit time" and its doc stopped being flagged
    stale. That is a SILENT under-report (the check passes when it should
    warn), so it is the dangerous direction to get wrong.
    """
    if rel in _DIR_TIME_CACHE:
        return _DIR_TIME_CACHE[rel]
    prefix = rel.rstrip("/") + "/"
    best: int | None = None
    for path, ct in _commit_times().items():
        if path.startswith(prefix) and (best is None or ct > best):
            best = ct
    _DIR_TIME_CACHE[rel] = best
    return best


def git_commit_time(path: Path) -> int | None:
    """Return the unix timestamp of the file's last commit, or None if untracked."""
    try:
        rel = path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return None
    exact = _commit_times().get(rel)
    if exact is not None:
        return exact
    # Not a known file path. It may be a DIRECTORY token, whose commit time is
    # the newest commit under it (matching `git log -1 -- <dir>`). Guard on
    # is_dir() so a plain untracked FILE still returns None as before.
    if path.is_dir():
        return _dir_commit_time(rel)
    return None


def ack_path(doc: Path) -> Path:
    """The ack file for a doc: docs/freshness/<flattened-doc-path>.ack.

    The slug flattens the doc's repo-relative path (docs/components/auth.md
    -> components~auth.md.ack) so every doc gets a UNIQUE, one-per-file ack.
    One file per doc is the whole point: two sessions acking two different
    docs touch two different files and never conflict -- the property the
    single shared `*Last updated:*` line did not have.

    UNIQUENESS IS LOAD-BEARING, so the separator must be a character that
    cannot occur in a path component. An earlier version used `__`, which
    collides: `docs/components/auth.md` and `docs/components__auth.md` both
    flatten to `components__auth.md.ack`, and one doc's ack would silently
    clear the other's staleness -- a wrong answer with no error. `~` is not
    legal in this repo's doc names and is rejected below if it ever appears,
    so the mapping stays injective by construction rather than by luck.
    """
    resolved = doc.resolve()
    try:
        rel = resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        # A doc outside REPO_ROOT (tmp_path fixtures; a doc passed by absolute
        # path from elsewhere). It can have no ack in this repo, but it must
        # not CRASH the checker -- freshness is warn-only and a path shape has
        # no business taking it down. Fall back to the bare filename so the
        # derived path is still well-formed and simply will not exist.
        rel = resolved.name
    if rel.startswith("docs/"):
        rel = rel[len("docs/"):]
    if ACK_SEP in rel:
        # Refuse rather than return a path that could shadow another doc's
        # ack. A doc name containing the separator is not a supported shape;
        # silently mapping it somewhere plausible is how a checker starts
        # giving confidently wrong answers.
        raise ValueError(
            f"doc path contains the ack separator {ACK_SEP!r}, which would "
            f"make its ack file ambiguous: {rel}"
        )
    return REPO_ROOT / ACK_DIR / (rel.replace("/", ACK_SEP) + ACK_SUFFIX)


def ack_commit_time(doc: Path) -> int | None:
    """Commit time of this doc's ack file, or None if it has no committed ack.

    An ack that exists in the working tree but is not yet committed has no
    commit time. That is deliberate and is handled by the caller: the ack
    still COUNTS during a session (so triage-then-commit works within one
    closeout), but its durable freshness value only exists once committed.
    """
    ack = ack_path_or_none(doc)
    if ack is None or not ack.exists():
        return None
    return git_commit_time(ack)


def ack_path_or_none(doc: Path) -> Path | None:
    """ack_path(), but None instead of raising for an unsupported doc path.

    The READ paths (freshness checking) must be total: this script is
    warn-only and must never take down a closeout over a filename. The WRITE
    path (--ack) deliberately keeps the raising version, so an author naming
    a doc unsupportedly is told rather than given a silently-shadowed ack.
    """
    try:
        return ack_path(doc)
    except ValueError:
        return None


def read_ack(doc: Path) -> dict[str, str] | None:
    """Parse a doc's ack file into its fields, or None if there is no ack.

    Format is deliberately trivial (`key: value` lines) -- the ack's job is
    to be READABLE IN A DIFF. A reviewer must be able to see what was
    verified and why without running anything.
    """
    ack = ack_path_or_none(doc)
    if ack is None or not ack.exists():
        return None
    fields: dict[str, str] = {}
    for line in ack.read_text(encoding="utf-8").splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


def write_ack(doc: Path, because: str, verified: list[Path]) -> Path:
    """Record that this doc was reviewed against its tracked code.

    `verified` is AUTO-FILLED by the caller from the files that actually
    triggered staleness -- the author does not get to type a convenient
    list. Together with the mandatory `because`, that is what makes a blind
    ack impossible: the diff shows which files were supposedly checked and
    the stated reason, so a reviewer has something real to judge.
    """
    ack = ack_path(doc)
    ack.parent.mkdir(parents=True, exist_ok=True)
    head = git_head_sha() or "unknown"
    rels = sorted(fp.resolve().relative_to(REPO_ROOT).as_posix() for fp in verified)
    body = (
        f"doc: {doc.resolve().relative_to(REPO_ROOT).as_posix()}\n"
        f"verified: {', '.join(rels) if rels else '(no tracked files were stale)'}\n"
        f"because: {because}\n"
        # Informational ONLY -- never compared. See the ACK_DIR note above:
        # this SHA is orphaned by squash-merge and would be a false anchor.
        f"sha: {head}\n"
    )
    ack.write_text(body, encoding="utf-8")
    return ack


def git_head_sha() -> str | None:
    """Short HEAD sha, for the ack's human breadcrumb line."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
            creationflags=windowless_creationflags(),
        )
        return result.stdout.strip() or None
    except subprocess.CalledProcessError:
        return None


def staged_files() -> set[Path]:
    """Return absolute paths of files currently staged for commit."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
            creationflags=windowless_creationflags(),
        )
    except subprocess.CalledProcessError:
        return set()
    return {(REPO_ROOT / line).resolve() for line in result.stdout.splitlines() if line}


def parse_tracks(doc_path: Path) -> list[str]:
    """Return the list of glob/path tokens declared in the doc's **Tracks:** line."""
    text = doc_path.read_text(encoding="utf-8")
    m = TRACKS_RE.search(text)
    if not m:
        return []
    line = m.group(1).strip()
    # Tokens may be space- OR comma-separated, and wrapped in backticks.
    # Split on whitespace-or-comma so a comma-separated list
    # (`` `a.py`, `b.py` ``) doesn't yield trailing-comma tokens like
    # `a.py,` that match no files. Then strip backticks and any stray
    # surrounding commas from each token.
    tokens = [t.strip("`,").strip() for t in re.split(r"[\s,]+", line)]
    return [t for t in tokens if t]


def parse_last_updated_ts(doc_path: Path) -> int | None:
    """Parse the doc's `*Last updated: YYYY-MM-DD ...*` line into a unix
    timestamp. Returns None if the line is missing or unparseable.

    The stamp is treated as **end-of-day UTC** (23:59:59Z on the stamp's
    day) so that:
      1. A same-day code commit doesn't false-flag the doc as stale
         (day-granularity is the right cadence; we don't ask doc-writers
         to track HH:MM:SS).
      2. The result is deterministic across developer machines and CI —
         using local time would produce different stale/ok verdicts in
         different timezones (Copilot review #100). Git commit timestamps
         from `%ct` are absolute Unix epochs, so the stamp side needs to
         be timezone-stable too.
    """
    import datetime
    try:
        text = doc_path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = LAST_UPDATED_RE.search(text)
    if not m:
        return None
    try:
        d = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None
    # End-of-day UTC: 23:59:59Z on the stamp's day.
    end_of_day_utc = datetime.datetime.combine(
        d, datetime.time(23, 59, 59), tzinfo=datetime.timezone.utc,
    )
    return int(end_of_day_utc.timestamp())


def expand_token(token: str) -> list[Path]:
    """Expand a tracked-paths token (literal path or glob) into actual files.

    Resolves globs against REPO_ROOT. Returns empty list if nothing matches.
    """
    # If the token has no glob characters and points at a real file, return it.
    p = REPO_ROOT / token
    if not any(ch in token for ch in "*?["):
        return [p] if p.exists() else []
    # Otherwise, glob from REPO_ROOT.
    matches = list(REPO_ROOT.glob(token))
    return [m for m in matches if m.is_file()]


def find_tier1_docs() -> list[Path]:
    """Return the tier-1 docs (TIER1_DOCS) that actually exist on disk.

    These carry a `**Tracks:**` line in the same shape as tier-2 docs (e.g.
    technical_guide.md tracks backend/main.py et al.). find_docs() globs only
    DOC_DIRS, so it prepends THIS function's result to bring tier-1 into the
    freshness scan. Missing entries (a doc not yet created) are silently
    skipped.
    """
    return [p for rel in TIER1_DOCS if (p := REPO_ROOT / rel).is_file()]


def find_docs() -> list[Path]:
    """Return tier-1 + tier-2 docs to scan for freshness, sorted.

    Tier-1: TIER1_DOCS (CLAUDE.md, docs/INDEX.md, docs/technical_guide.md).
    Tier-2: every `docs/components/*.md` + `docs/standards/*.md` +
    `docs/doctrine/*.md` (excluding README.md). Docs without a `**Tracks:**`
    line are skipped downstream by check_doc(); including them here is
    harmless.
    """
    docs = list(find_tier1_docs())
    for d in DOC_DIRS:
        dir_path = REPO_ROOT / d
        if not dir_path.is_dir():
            continue
        for md in dir_path.glob("*.md"):
            if md.name == "README.md":
                continue
            docs.append(md)
    return sorted(set(docs))


def check_doc(
    doc: Path,
    *,
    only_if_staged: set[Path] | None = None,
) -> tuple[str, list[tuple[Path, int, int]], list[str]]:
    """Check one doc for staleness.

    Returns (status, stale_files, warnings).
      status: "ok", "stale", "skipped", "no-tracks"
      stale_files: list of (path, file_ct, doc_ct) for each newer file
      warnings: list of human-readable warnings (e.g. tracked path missing)

    --staged mode semantics: the staged change IS the staleness trigger. We
    don't compare to git log (the change isn't committed). We flag any doc
    whose tracked code is staged BUT the doc itself is NOT staged. If the
    doc is staged too, the author updated it in the same commit — silent OK.
    """
    tokens = parse_tracks(doc)
    if not tokens:
        return ("no-tracks", [], [])
    # Prefer the doc's claimed "*Last updated:* YYYY-MM-DD" line as the
    # comparison source -- the closeout checklist tells the user to bump
    # this line, so the script needs to actually trust it. Fall back to
    # git commit time if the stamp is missing or unparseable so a doc that
    # hasn't been migrated to the new format still works.
    doc_ct = parse_last_updated_ts(doc)
    if doc_ct is None:
        doc_ct = git_commit_time(doc)
    # THE ACK (bd polyglot-pdf-fytzi). A doc is fresh if it was EDITED after
    # its code changed OR explicitly REVIEWED after its code changed. Before
    # the ack, only the first counted -- so the honest action ("I read it; it
    # is still accurate") left the stale flag ON, which is precisely why 21
    # of 28 tracked docs sit stale and the signal stopped being read.
    #
    # An UNCOMMITTED ack counts as "now": it is the author saying so during
    # this session, and triage-then-commit has to work inside one closeout.
    # Its durable value arrives when it is committed (closeout requires that
    # before the PR opens).
    ack_ct = ack_commit_time(doc)
    if ack_ct is None:
        pending = ack_path_or_none(doc)
        if pending is not None and pending.exists():
            # Uncommitted ack: it counts NOW so triage-then-commit works
            # inside one closeout. mtime is used only for this pre-commit
            # window -- every durable comparison uses git commit times, per
            # this module's note that mtimes do not survive clones.
            ack_ct = int(pending.stat().st_mtime)
    if ack_ct is not None:
        doc_ct = ack_ct if doc_ct is None else max(doc_ct, ack_ct)
    if doc_ct is None:
        return ("ok", [], [f"{doc.relative_to(REPO_ROOT)}: doc not yet committed, and has no *Last updated:* stamp or freshness ack"])
    # If --staged AND the doc itself is staged, the author already updated it.
    if only_if_staged is not None and doc.resolve() in only_if_staged:
        return ("ok", [], [])
    stale: list[tuple[Path, int, int]] = []
    warnings: list[str] = []
    matched_any = False
    for token in tokens:
        matches = expand_token(token)
        if not matches:
            warnings.append(
                f"  warning: tracked path '{token}' matched no files — "
                "fix the **Tracks:** line"
            )
            continue
        for fp in matches:
            matched_any = True
            if only_if_staged is not None:
                if fp.resolve() not in only_if_staged:
                    continue
                # Stale: doc is not staged but its tracked code is.
                stale.append((fp, 0, doc_ct))
                continue
            file_ct = git_commit_time(fp)
            if file_ct is None:
                continue  # untracked; nothing to compare
            if file_ct > doc_ct:
                stale.append((fp, file_ct, doc_ct))
    if only_if_staged is not None and not matched_any:
        return ("skipped", stale, warnings)
    return ("stale" if stale else "ok", stale, warnings)


def fmt_ts(ts: int, *, utc: bool = False) -> str:
    """Format a unix timestamp as 'YYYY-MM-DD HH:MM'.

    Pass `utc=True` for parsed *Last updated:* stamps (end-of-day UTC) so
    the displayed date matches the doc's claimed stamp regardless of the
    developer's local timezone. Tracked-file commit times stay in local
    for human readability — those are wall-clock-relative anyway.
    """
    import datetime
    if utc:
        dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
    else:
        dt = datetime.datetime.fromtimestamp(ts)
    return dt.strftime("%Y-%m-%d %H:%M")


def parse_active_plans_from_index(index_path: Path = INDEX_MD) -> tuple[set[str], list[str]]:
    """Pull plan basenames out of INDEX.md's 'Active sprint plans' row.

    Returns (active_basenames, warnings).
      active_basenames: set of plan filenames declared currently-active-at-root
        (i.e. the href doesn't start with `archive/`).
      warnings: human-readable issues with the row itself (missing, unparseable).

    A plan is "currently active at root" if INDEX.md's row links to it with
    a bare basename href (e.g. `(sprint_51_sms_plan.md)`). References inside
    the same row that point at `archive/...` are ignored — those are usually
    contextual mentions of completed plans for navigation, not claims of
    activity.
    """
    warnings: list[str] = []
    if not index_path.is_file():
        return (set(), [f"INDEX.md not found at {index_path}"])
    try:
        text = index_path.read_text(encoding="utf-8")
    except OSError as e:
        return (set(), [f"could not read {index_path}: {e}"])
    m = ACTIVE_PLAN_ROW_RE.search(text)
    if not m:
        warnings.append(
            f"  warning: INDEX.md is missing the `sprint_<N>_<slug>_plan.md` row "
            "in the Architecture & process table — sprint-archive check "
            "cannot determine which plans are currently active"
        )
        return (set(), warnings)
    row = m.group(0)
    active: set[str] = set()
    for href_match in PLAN_HREF_RE.finditer(row):
        href = href_match.group(1).strip()
        # Skip archive/ refs — those are context, not claims of currently-active.
        # Also skip pure-anchor refs like `#section`.
        if href.startswith("archive/") or href.startswith("#"):
            continue
        # Take only the basename. Plans are always at docs/ root, so a
        # bare basename or a `./basename` form is what we expect.
        basename = href.rsplit("/", 1)[-1]
        if basename.startswith("sprint_") and basename.endswith(".md"):
            active.add(basename)
    return (active, warnings)


def find_root_sprint_plans(docs_dir: Path = DOCS_DIR) -> set[str]:
    """Return basenames of sprint plan files at docs/ root (not archive/)."""
    if not docs_dir.is_dir():
        return set()
    return {p.name for p in docs_dir.glob("sprint_*.md") if p.is_file()}


def is_sprint_plan(path: Path) -> bool:
    """True for a sprint plan doc: a ``sprint_*.md`` file living at ``docs/`` root
    (active) or under ``docs/archive/`` (archived).

    Sprint plans are a tier-2 reachable doc but a CHRONOLOGICAL plan of record:
    they sequence a sprint (R1 -> R2 -> R3 ...) and record A/B notes, so the
    current-state-only convention (no ``Previously:`` chains / history sections)
    deliberately does NOT apply to them (bd polyglot-pdf-h2r.3; see
    docs/doc-architecture.md "Sprint plans are exempt"). This is the single
    source of truth for that exemption -- ``check_doc_conventions`` skips any
    target it matches, so the exemption holds even if a plan is ever added to
    ``TIER1_DOCS`` by a future hand.

    The LOCATION matters: the exemption is for plans specifically, NOT for any
    tier-2 doc that happens to start with ``sprint_``. A
    ``docs/components/sprint_vad.md`` is a normal current-state component doc and
    must still be convention-scanned -- so we require the file to sit directly in
    ``docs/`` or ``docs/archive/``, not in any DOC_DIRS subdirectory. (Deliberately
    NOT hand-listing DOC_DIRS' members here -- see bd polyglot-pdf-jfq16: a
    parenthetical member-list is exactly the shape that keeps desyncing.)"""
    if not (path.name.startswith("sprint_") and path.name.endswith(".md")):
        return False
    parent = path.parent.name
    grandparent = path.parent.parent.name
    # docs/sprint_*.md  -> parent dir is "docs"
    # docs/archive/sprint_*.md -> parent is "archive", grandparent is "docs"
    return parent == "docs" or (parent == "archive" and grandparent == "docs")


def check_sprint_archive(
    docs_dir: Path = DOCS_DIR,
    index_path: Path = INDEX_MD,
) -> tuple[set[str], set[str], list[str]]:
    """Diff actual root-level sprint plans against INDEX.md's active list.

    Returns (orphans, missing, warnings).
      orphans: basenames at docs/ root but NOT listed in INDEX active row.
        These are the closeout-skipped case — sprint shipped, plan didn't move.
      missing: basenames listed in INDEX active row but NOT at docs/ root.
        These are stale references — plan was archived (or never created)
        but INDEX still claims it's active.
      warnings: structural issues with INDEX (missing row, unparseable, etc.)
    """
    active, warnings = parse_active_plans_from_index(index_path)
    at_root = find_root_sprint_plans(docs_dir)
    orphans = at_root - active
    missing = active - at_root
    return (orphans, missing, warnings)


def check_doc_conventions(
    docs: list[Path] | None = None,
    repo_root: Path = REPO_ROOT,
) -> list[tuple[Path, str]]:
    """Scan tier-1 + tier-2 docs for forbidden current-state-only violations.

    Returns a list of (doc_path, message) findings. The two patterns this
    detects are codified in CLAUDE.md "Doc maintenance rules":
      1. `Previously:`/`Prior:`/`Prior,`/`Earlier:`/`Earlier,` followed by a
         date, `Sprint NN`, "same day/week", or a bead-id reference --
         anywhere in the doc, not just the stamp. This bans both stamp
         chains AND rationale-section prose that strings sprint events
         together (`Previously: Sprint 47 used X approach.`). The journal
         entry is the chronological record; the doc is current-state only.
      2. `## Recent sprint history` / `## Update history` / `## Changelog` /
         `## Sprint history` headings -- same reason.

    The scan covers TIER1_DOCS (the specific files it names -- CLAUDE.md,
    docs/INDEX.md, docs/technical_guide.md -- NOT every docs/*.md top-level
    file), CONVENTION_ONLY_DOCS (meta-docs that would otherwise misparse
    under TRACKS_RE -- see that constant's comment for the exact reason --
    so they opt out of the freshness-staleness half but must still be
    convention-scanned -- currently just docs/doc-architecture.md), AND
    every doc under DOC_DIRS (docs/components/*.md + docs/standards/*.md +
    docs/doctrine/*.md).
    Tier-3 docs (docs/dev_journal.md, docs/journal/*, docs/archive/*) are
    explicitly NOT scanned -- chronological history is the whole point
    there.
    """
    findings: list[tuple[Path, str]] = []
    # find_docs() already returns tier-1 (TIER1_DOCS) + tier-2 docs, but a
    # caller may pass an explicit `docs` list (e.g. tests) that omits tier-1.
    # Union the explicit tier-1 + convention-only lists in either way, then
    # dedupe so a doc isn't scanned twice.
    targets: list[Path] = [
        p for rel in TIER1_DOCS + CONVENTION_ONLY_DOCS
        if (p := repo_root / rel).is_file()
    ]
    if docs is None:
        docs = find_docs()
    for d in docs:
        if d not in targets:
            targets.append(d)
    for doc in targets:
        # Sprint plans are exempt from the current-state-only convention: they
        # are a chronological plan of record (see is_sprint_plan). Skip them
        # here even if one is ever in TIER1_DOCS, so the exemption can't silently
        # lapse (bd polyglot-pdf-h2r.3).
        if is_sprint_plan(doc):
            continue
        try:
            text = doc.read_text(encoding="utf-8")
        except OSError:
            continue
        # Check 1: Previously:/Prior:/Earlier: (or the `,` variants) anywhere
        # in the doc.
        for m in PREVIOUSLY_CHAIN_RE.finditer(text):
            # Find the line number (1-indexed) the match lands on.
            line_no = text.count("\n", 0, m.start()) + 1
            # Name the ACTUAL matched keyword+separator (e.g. "Earlier,"), not
            # a hardcoded "Previously:" -- a maintainer grepping for the
            # string this message names must find the real violation.
            matched_text = m.group(0).split(None, 1)[0]
            findings.append((
                doc,
                f"line {line_no}: {matched_text!r} chain detected -- "
                "stamps must be one line; chronological history lives in dev_journal.md",
            ))
            break  # one finding per doc is enough; the human will read it all
        # Check 2: history-section heading anywhere in the doc.
        for m in HISTORY_HEADING_RE.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            heading = m.group(0).strip()
            findings.append((
                doc,
                f"line {line_no}: history section detected ({heading!r}) -- "
                "move the content to dev_journal.md and drop the section",
            ))
            break
    return findings


# Matches a code citation like `pdf_fill_routes.py:142` or
# `pdf_fill_routes.py:142-144` -- a backtick-quoted path fragment (with or
# without directory segments) followed by `:` and a 1-indexed line number,
# optionally a `-` and an end line for a range.
CODE_CITATION_RE = re.compile(
    r"`([\w./-]+\.(?:py|ts|tsx|js)):(\d+)(?:-(\d+))?`"
)


def _tracked_files_by_basename(repo_root: Path = REPO_ROOT) -> dict[str, list[str]]:
    """basename -> list of tracked repo-relative paths sharing that basename.

    Built from `git ls-files`, not a filesystem walk -- an untracked scratch
    file must never resolve a citation (it could vanish and the check would
    have "verified" against nothing).
    """
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
            creationflags=windowless_creationflags(),
        )
    except subprocess.CalledProcessError:
        return {}
    by_basename: dict[str, list[str]] = {}
    for line in result.stdout.splitlines():
        if not line:
            continue
        by_basename.setdefault(line.rsplit("/", 1)[-1], []).append(line)
    return by_basename


def check_code_citations(
    docs: list[Path] | None = None,
    repo_root: Path = REPO_ROOT,
) -> list[tuple[Path, str]]:
    """Flag `file.py:N` doc citations that run past EOF or land on a blank line.

    bd polyglot-pdf-3pii5: a line-number citation silently rots the moment
    the cited file gains or loses lines above the citation -- nothing
    mechanically checks it, so a doc can cite the wrong construct for
    sprints with no signal. This is the narrowly-scoped, mechanical half of
    that bead's fix: it catches the most severe forms of drift (a citation
    now pointing past the end of the file entirely, bd polyglot-pdf-3pii5;
    or landing on a blank line, bd polyglot-pdf-vdcm4) without trying to
    verify the cited line contains the SPECIFIC construct the surrounding
    prose names -- that would require inferring a claim from natural-
    language prose, which is exactly the over-general-checker trap CLAUDE.md
    warns about (a checker that infers a claim from text must scope the
    evidence region to exactly the claim, and prose is not a reliable
    scoping signal here). An in-bounds, non-blank citation is not proven
    CORRECT by this check -- it can still name the WRONG construct on a
    real line (see bd polyglot-pdf-vdcm4's manual fixes, which this check
    could not have caught) -- but an out-of-bounds or blank one is proven
    WRONG. Concretely: inserting a line ABOVE a citation shifts it downward
    without ever pushing it past EOF or onto a blank line, so that drift
    (the more common real-world case -- a function added earlier in the
    file, not the file truncated) stays invisible to this check. Symbol-name
    anchors (this bead's OTHER, preferred fix) are immune to that shift; a
    line-number citation never is, no matter how this check is strengthened
    -- which is why re-anchoring, not a smarter citation checker, is the
    durable answer for any citation this check can't reach.

    Resolution is deliberately conservative: a citation resolves only when
    its path fragment names an EXACT tracked path, or its bare basename is
    UNIQUE across the tracked tree (`git ls-files`, not a filesystem walk --
    an untracked file must never "verify" a citation). Filenames repeat in
    this repo (`form_models.py`, `secretary_context.py`, 19 others) -- a
    citation whose basename is ambiguous is silently SKIPPED, not guessed
    at, because guessing which of several same-named files a bare `:N`
    citation means is the same shorthand-resolved-against-the-wrong-scope
    trap that bit bd polyglot-pdf-abn4o three times. Known limitation: a
    citation into an ambiguous-basename file goes unchecked until it either
    gains enough path segments to disambiguate, or the collision is
    resolved. This under-covers rather than over-claims.
    """
    findings: list[tuple[Path, str]] = []
    if docs is None:
        docs = find_docs()
    by_basename = _tracked_files_by_basename(repo_root)
    for doc in docs:
        try:
            text = doc.read_text(encoding="utf-8")
        except OSError:
            continue
        for m in CODE_CITATION_RE.finditer(text):
            fragment, start_s, end_s = m.group(1), m.group(2), m.group(3)
            start = int(start_s)
            end = int(end_s) if end_s else start
            if "/" in fragment:
                # A path fragment with directory segments must match a
                # tracked path's TAIL exactly (not just contain it as a
                # substring) -- "outes.py/foo.py" tail-matching "routes.py"
                # would be a false resolution.
                candidates = [
                    p for p in by_basename.get(fragment.rsplit("/", 1)[-1], [])
                    if p == fragment or p.endswith("/" + fragment)
                ]
            else:
                candidates = by_basename.get(fragment, [])
            if len(candidates) != 1:
                continue  # unresolvable or ambiguous -- skip, don't guess
            target = repo_root / candidates[0]
            try:
                target_lines = target.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
            except OSError:
                continue
            line_count = len(target_lines)
            if end > line_count:
                line_no = text.count("\n", 0, m.start()) + 1
                findings.append((
                    doc,
                    f"line {line_no}: citation `{m.group(0)[1:-1]}` cites "
                    f"line {end} but {candidates[0]} has only {line_count} "
                    "lines -- the citation has drifted past EOF",
                ))
            elif start == end and not target_lines[start - 1].strip():
                # Single-line citation landing on a blank -- only checked for
                # a SINGLE line (not a range): a range citing a blank line
                # inside it (e.g. a blank separator line within a function
                # body) is common and not a sign of drift, whereas a bare
                # `:N` pointing at nothing is a strong drift signal no range
                # citation shares.
                line_no = text.count("\n", 0, m.start()) + 1
                findings.append((
                    doc,
                    f"line {line_no}: citation `{m.group(0)[1:-1]}` cites "
                    f"line {end} of {candidates[0]}, which is blank -- the "
                    "citation has drifted off its target",
                ))
    return findings


def report_doc_conventions(*, quiet: bool = False) -> bool:
    """Print convention-check findings. Returns True if anything was flagged.

    Same warn-only severity as the per-doc freshness pass. The CI test at
    `tests/test_doc_freshness.py::test_no_history_chains_in_current_state_docs`
    fails CI on the same findings -- the pre-commit hook just surfaces them
    earlier.
    """
    findings = check_doc_conventions()
    if not findings:
        if not quiet:
            print("\nDoc conventions: clean (no 'Previously:'/'Prior:'/'Earlier:' chains, no history sections in tier-1/tier-2 docs).")
        return False
    print()
    print("[doc-conventions] current-state-only violations -- tier-1 and tier-2 docs")
    print("                  must not carry chronological history. Move offending")
    print("                  content to dev_journal.md.")
    for doc, msg in findings:
        rel = doc.relative_to(REPO_ROOT).as_posix()
        print(f"  {rel}: {msg}")
    print()
    print("  See CLAUDE.md 'Doc maintenance rules' for the canonical one-line stamp shape.")
    return True


def report_code_citations(*, quiet: bool = False) -> bool:
    """Print out-of-bounds or blank-line `file.py:N` citation findings.

    Same warn-only severity as the per-doc freshness pass. The CI test at
    `tests/test_doc_freshness.py::test_no_out_of_bounds_code_citations`
    fails CI on the same findings (bd polyglot-pdf-3pii5 for the past-EOF
    check, bd polyglot-pdf-vdcm4 for the blank-line check).
    """
    findings = check_code_citations()
    if not findings:
        if not quiet:
            print("\nCode citations: clean (no `file.py:N` citation points past its file's current EOF or at a blank line).")
        return False
    print()
    print("[code-citations] line-number citations that have drifted --")
    print("                  past EOF (the cited file is now shorter) or onto a blank line.")
    for doc, msg in findings:
        rel = doc.relative_to(REPO_ROOT).as_posix()
        print(f"  {rel}: {msg}")
    print()
    print("  Fix the line number, or re-anchor to a symbol name (preferred -- see")
    print("  bd polyglot-pdf-3pii5 and CLAUDE.md scar #7).")
    return True


def report_sprint_archive(
    *,
    quiet: bool = False,
    docs_dir: Path = DOCS_DIR,
    index_path: Path = INDEX_MD,
) -> bool:
    """Print sprint-archive findings. Returns True if anything was flagged.

    The report uses the same warn-only severity as the per-doc freshness
    pass — it prints concrete remediation hints (the exact `git mv` command,
    the file to add a row to) so the user can act without re-reading
    CLAUDE.md.
    """
    orphans, missing, warnings = check_sprint_archive(docs_dir, index_path)
    flagged = bool(orphans or missing or warnings)
    if warnings:
        print()
        for w in warnings:
            print(w)
    if orphans:
        print()
        print("[sprint-archive] orphaned plan files at docs/ root (not listed as active in INDEX.md):")
        for name in sorted(orphans):
            print(f"  - docs/{name}")
        print()
        print("  If shipped: `git mv docs/<file> docs/archive/<file>` and add a")
        print("  row to docs/archive_completed_plans.md (Sprint Plans table).")
        print("  If still active: add it to INDEX.md's `sprint_<N>_<slug>_plan.md`")
        print("  row (Architecture & process table).")
        print("  See CLAUDE.md sprint closeout step 5 for the full protocol.")
    if missing:
        print()
        print("[sprint-archive] INDEX.md lists these plans as active but the files are missing from docs/ root:")
        for name in sorted(missing):
            print(f"  - docs/{name}")
        print()
        print("  Either restore the file (if accidentally deleted) or remove the")
        print("  reference from INDEX.md's `sprint_<N>_<slug>_plan.md` row.")
    if not flagged and not quiet:
        print("\nSprint-archive protocol: clean (root sprint plans match INDEX.md active list).")
    return flagged


ACK_RATE_HINT = 3


def run_ack(doc_arg: str, because: str | None) -> int:
    """Handle `--ack <doc> --because "<reason>"`. Returns an exit code.

    This is the ONE place the ack is created, and it deliberately refuses
    more than it accepts: no reason, no ack; unknown doc, no ack; a doc that
    is not actually stale gets told so rather than silently acked.
    """
    if not because or not because.strip():
        print("ERROR: --ack requires --because \"<one line on why it is still accurate>\".")
        print("  A reason-less ack is the stamp bump this mechanism exists to replace:")
        print("  it clears the flag while proving nothing to the next reader.")
        return 2

    doc = (REPO_ROOT / doc_arg).resolve()
    if not doc.is_file():
        print(f"ERROR: no such doc: {doc_arg}")
        return 2

    status, stale, _warnings = check_doc(doc)
    if status == "no-tracks":
        print(f"ERROR: {doc_arg} has no **Tracks:** line, so it is not freshness-checked.")
        print("  Give it a Tracks: line (or add it to the no-tracks allowlist) instead of acking it.")
        return 2

    verified = [fp for fp, _fct, _dct in stale]
    if not verified:
        print(f"{doc_arg} is already fresh -- nothing to ack.")
        return 0

    ack = write_ack(doc, because.strip(), verified)
    rel = ack.relative_to(REPO_ROOT).as_posix()
    print(f"Acked {doc_arg} against {len(verified)} tracked file(s) -> {rel}")
    for fp in sorted(verified):
        print(f"    verified: {fp.relative_to(REPO_ROOT).as_posix()}")
    print("  COMMIT this ack with your change -- an uncommitted ack does not survive the PR.")

    # Bulk acking is audit work, not closeout work. This is a hint, not a
    # block: the honest bulk case (the corpus audit) has its own bead where
    # the labor is priced, and a session quietly acking its way out of a
    # closeout is exactly the failure this mechanism must not enable.
    #
    # SCOPED TO THIS BRANCH, deliberately. Counting every ack in the repo
    # would fire forever the moment the corpus audit lands its ~20 acks --
    # turning the one signal that catches ack-spam into permanent background
    # noise. That is the same alarm-fatigue death the stale-doc flag already
    # died of, and it would be self-inflicted.
    branch_acks = branch_ack_count()
    if branch_acks > ACK_RATE_HINT:
        print(f"\n  NOTE: this branch now carries {branch_acks} acks. Acking several docs in")
        print("  one branch is audit work -- see the docs-audit bead rather than clearing")
        print("  them at closeout.")
    return 0


def _porcelain_ack_paths(line: str) -> set[str]:
    """Ack paths named by one `git status --porcelain -uall` line.

    Porcelain lines are `XY <path>`, and a RENAME is `R  <old> -> <new>` --
    which names two paths, only one of which still exists. Keeping both is
    deliberate: an ack renamed INTO this branch is new work here, and a set()
    collapses any double-count. Quoted paths (git quotes names with spaces or
    non-ASCII) are unquoted so the suffix test still matches.
    """
    if len(line) < 4:
        return set()
    payload = line[3:].strip()
    # NOTE: this text-mode parser is the FALLBACK. branch_ack_count() reads
    # `--porcelain -z`, where rename pairs are NUL-separated records and no
    # arrow-splitting is needed at all -- see _porcelain_z_ack_paths(). Arrow
    # splitting is unfixable in general: with `RM old.ack -> new -> weird.ack`
    # you cannot tell which arrow separates the pair and which is part of the
    # filename. So this path deliberately does NOT split; it reads the whole
    # payload as one path. That under-counts a rename's old path in the text
    # fallback (harmless -- the count only drives an advisory hint) rather
    # than inventing a path that does not exist.
    parts = [payload]
    out: set[str] = set()
    for part in parts:
        if part.startswith('"') and part.endswith('"') and len(part) > 1:
            part = part[1:-1]
        if part.endswith(ACK_SUFFIX):
            out.add(part)
    return out


def _porcelain_z_ack_paths(raw: str) -> set[str]:
    """Ack paths from `git status --porcelain -z -uall` output.

    THE POINT OF -z: records are NUL-separated and a rename/copy emits its two
    paths as TWO records (`R  new\\0old\\0`), so there is no arrow to parse and
    no ambiguity when a FILENAME itself contains " -> ". Text-mode parsing
    cannot resolve that case even in principle -- given
    `RM old.ack -> new -> weird.ack` you cannot tell which arrow is the
    separator. Reading -z removes the ambiguity by construction rather than
    guessing at it, which is why it is the primary path.

    Each record is `XY <path>` except the second half of a rename/copy pair,
    which is a bare path. Both forms are handled: anything ending in the ack
    suffix counts, whether or not it carries a status prefix.
    """
    out: set[str] = set()
    records = [r for r in raw.split("\0") if r]
    i = 0
    while i < len(records):
        record = records[i]
        # Slicing already yields "" for a record shorter than the prefix, so
        # no length guard is needed. (An earlier `if len(record) > 3 else ""`
        # was provably a no-op -- identical output for every input -- which is
        # why no mutation of it could fail a test. Defensive clutter that
        # cannot be wrong is also code that cannot be verified; dropped.)
        status, path = record[:2], record[3:]
        # DO NOT GUESS whether a record carries a status prefix. -z output has
        # a determinate structure: every record is "XY <path>", EXCEPT that a
        # rename/copy is followed by ONE extra record holding the bare source
        # path. So consume that follow-up positionally, driven by the status
        # code, instead of sniffing the string.
        #
        # An earlier version sniffed (`if record[2] == " "` -> strip 3 chars),
        # which mangled a bare source path whose third character is a space:
        # "ab cd/old.md.ack" became "cd/old.md.ack" -- an INVENTED path, and
        # the string still ended in .ack so the fallback never noticed.
        if path.endswith(ACK_SUFFIX):
            out.add(path)
        if status and status[0] in ("R", "C") and i + 1 < len(records):
            source = records[i + 1]          # bare path, no status prefix
            if source.endswith(ACK_SUFFIX):
                out.add(source)
            i += 2
            continue
        i += 1
    return out


def branch_ack_count(base: str = "origin/dev") -> int:
    """How many ack files THIS branch adds or changes, vs its merge base.

    Falls back to the working-tree count only if git cannot answer (a fresh
    repo with no base, a detached state) -- a wrong-but-bounded number beats
    crashing a warn-only tool.
    """
    try:
        merge_base = subprocess.run(
            ["git", "merge-base", base, "HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
            creationflags=windowless_creationflags(),
        ).stdout.strip()
        committed = subprocess.run(
            ["git", "diff", "--name-only", merge_base, "HEAD", "--", ACK_DIR],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
            creationflags=windowless_creationflags(),
        ).stdout.split()
        # Uncommitted acks count too: the session made them, they just have
        # not landed yet.
        pending = subprocess.run(
            # -uall is REQUIRED: without it git collapses a wholly-untracked
            # directory to ONE "?? docs/freshness/" line, so the first session
            # ever to create acks parsed zero of them and the hint stayed
            # silent for exactly the case it exists to catch.
            ["git", "status", "--porcelain", "-z", "-uall", "--", ACK_DIR],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
            creationflags=windowless_creationflags(),
        ).stdout
        names = {p for p in committed if p.endswith(ACK_SUFFIX)}
        names |= _porcelain_z_ack_paths(pending)
        return len(names)
    except (subprocess.CalledProcessError, OSError):
        ack_dir = REPO_ROOT / ACK_DIR
        return len(list(ack_dir.glob("*" + ACK_SUFFIX))) if ack_dir.is_dir() else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Only flag docs whose tracked code is in the staging area.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Scan every doc (default).",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress 'OK' lines.")
    parser.add_argument(
        "--ack",
        metavar="DOC",
        help="Record that DOC was reviewed and is still accurate. Requires "
             "--because. Writes docs/freshness/<slug>.ack listing the tracked "
             "files that were stale, so the review is visible in the diff.",
    )
    parser.add_argument(
        "--because",
        metavar="REASON",
        help="One line saying WHY the doc is still accurate. Mandatory with "
             "--ack: a bare ack is indistinguishable from the stamp-bump-"
             "without-reading habit this replaces.",
    )
    args = parser.parse_args()

    if args.ack:
        return run_ack(args.ack, args.because)
    if args.because:
        parser.error("--because is only meaningful with --ack")

    only_staged = staged_files() if args.staged else None
    # find_docs() returns tier-1 (TIER1_DOCS) + tier-2 (docs/components,
    # docs/standards, docs/doctrine) docs. The freshness loop below must
    # cover tier-1 too — technical_guide.md's **Tracks:** line was previously
    # unenforced because this loop only iterated the (then DOC_DIRS-only)
    # result.
    docs = find_docs()
    if not docs:
        print("No docs to check (no tier-1 docs on disk; "
              "docs/components/, docs/standards/, docs/doctrine/ are empty).")
        return 0

    any_stale = False
    any_warnings = False
    for doc in docs:
        status, stale, warnings = check_doc(doc, only_if_staged=only_staged)
        rel = doc.relative_to(REPO_ROOT).as_posix()
        if status == "no-tracks":
            if not args.quiet:
                print(f"  - {rel}: no **Tracks:** line, skipped")
            continue
        if status == "skipped":
            # In --staged mode, no tracked file is staged AND no token matched
            # any real file. Surface warnings (e.g. tracked path missing) so
            # broken **Tracks:** lines still get reported, then move on.
            if warnings:
                any_warnings = True
                print(f"  - {rel}:")
                for w in warnings:
                    print(w)
            continue
        if status == "stale":
            any_stale = True
            # Show the same source the comparison used (parsed stamp first,
            # commit-time fallback) so the user isn't confused by a date
            # that doesn't match either signal.
            doc_ts = parse_last_updated_ts(doc)
            if doc_ts is not None:
                # Format in UTC so the displayed date matches the stamp the
                # user wrote, regardless of their machine's timezone.
                stamp_label = f"*Last updated:* {fmt_ts(doc_ts, utc=True).split(' ')[0]}"
            else:
                doc_ts = git_commit_time(doc)
                stamp_label = (
                    f"last commit {fmt_ts(doc_ts)}" if doc_ts else "never committed"
                )
            print(f"  STALE: {rel}  ({stamp_label})")
            for fp, file_ct, doc_ct in stale:
                file_rel = fp.relative_to(REPO_ROOT).as_posix()
                if file_ct == 0:  # --staged mode placeholder
                    print(f"    -> {file_rel} (staged in this commit)")
                else:
                    print(f"    -> {file_rel} updated {fmt_ts(file_ct)}")
            for w in warnings:
                any_warnings = True
                print(w)
        else:
            if warnings:
                any_warnings = True
                print(f"  - {rel}:")
                for w in warnings:
                    print(w)
            elif not args.quiet:
                print(f"  - {rel}: OK")

    if not any_stale and not any_warnings:
        print("\nAll tier-1 + tier-2 docs are up to date.")
    elif any_stale:
        print("\nStale docs detected. Update the doc and bump its *Last updated:* line, ")
        print("or note the review in the closeout journal entry. Exit 0 (warn only).")

    # Sprint-archive protocol check. Runs in BOTH --all and --staged modes —
    # cheap (two FS reads + one regex), and the orphan signal is worth
    # surfacing on every commit, not just at sprint closeout. Output goes
    # below the per-doc freshness summary so it's visually distinct.
    report_sprint_archive(quiet=args.quiet)

    # Doc-convention check (current-state-only enforcement). Same warn-only
    # severity; the CI test in tests/test_doc_freshness.py is the gate.
    report_doc_conventions(quiet=args.quiet)

    # Out-of-bounds code-citation check (bd polyglot-pdf-3pii5). Same
    # warn-only severity; the CI test in tests/test_doc_freshness.py is the
    # gate.
    report_code_citations(quiet=args.quiet)

    # Always exit 0 — this is a warn-only check.
    return 0


if __name__ == "__main__":
    sys.exit(main())
