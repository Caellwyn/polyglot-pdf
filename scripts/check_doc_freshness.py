"""Scan tier-1 + tier-2 docs for staleness AND enforce the sprint-archive protocol.

This script does two warn-only checks in one pass:

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

Why both checks live in one script: they're two halves of the same doc
discipline, and they want the same hook (warn-only on every commit, full
sweep at sprint closeout). Splitting them into two scripts would
duplicate the argparse/exit-code/print plumbing; co-locating them means
the closeout `python scripts/check_doc_freshness.py` invocation
already covers both.

Why parse the stamp instead of using the doc's git commit time? Because the
sprint-closeout checklist tells the user to "bump its *Last updated:* line"
to fix staleness — the script needs to actually trust that line. Using the
doc's git commit time has a confusing failure mode: a docs commit that
includes both a code edit AND a doc bump still flags as stale on the next
run because both touch the same commit and the comparison is `file_ct >
doc_ct`. Parsing the stamp keeps the user's mental model honest: bump the
date, get a green check.

Fallback: if the doc has no parseable `*Last updated:* YYYY-MM-DD*` line,
the script falls back to the doc's git commit time (the prior behavior).

Two modes:
  --all (default)  scan every doc; print each stale doc + the offending
                   newer code paths. Used by the sprint closeout checklist.
  --staged         scan only docs whose tracked code is in the current git
                   staging area. Used by the pre-commit hook.

The sprint-archive check runs in BOTH modes — it's cheap (two filesystem
listings + one regex) and the orphan signal is worth surfacing on every
commit, not just at closeout.

Exit code: always 0. The hook decides whether to be loud (it isn't —
warn-only, never blocks). Sprint closeout treats output as a checklist.

Usage:
  python scripts/check_doc_freshness.py
  python scripts/check_doc_freshness.py --staged
  python scripts/check_doc_freshness.py --all --quiet  # suppress "OK" lines

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
DOC_DIRS = ["docs/components", "docs/standards", "docs/doctrine"]
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


def git_commit_time(path: Path) -> int | None:
    """Return the unix timestamp of the file's last commit, or None if untracked."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "--", str(path.relative_to(REPO_ROOT))],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        out = result.stdout.strip()
        return int(out) if out else None
    except (subprocess.CalledProcessError, ValueError):
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
    if doc_ct is None:
        return ("ok", [], [f"{doc.relative_to(REPO_ROOT)}: doc not yet committed and has no parseable *Last updated:* stamp"])
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
    ``docs/`` or ``docs/archive/``, not in any DOC_DIRS subdirectory
    (``components/`` / ``standards/`` / ``doctrine/``)."""
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

    The scan covers TIER1_DOCS (CLAUDE.md + docs/*.md top-level files) AND
    every doc under DOC_DIRS (docs/components/*.md + docs/standards/*.md +
    docs/doctrine/*.md). Tier-3 docs (docs/dev_journal.md, docs/journal/*,
    docs/archive/*) are explicitly NOT scanned -- chronological history is
    the whole point there.
    """
    findings: list[tuple[Path, str]] = []
    # find_docs() already returns tier-1 (TIER1_DOCS) + tier-2 docs, but a
    # caller may pass an explicit `docs` list (e.g. tests) that omits tier-1.
    # Union the explicit tier-1 list in either way, then dedupe so a doc
    # isn't scanned twice.
    targets: list[Path] = [
        p for rel in TIER1_DOCS if (p := repo_root / rel).is_file()
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
    args = parser.parse_args()

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

    # Always exit 0 — this is a warn-only check.
    return 0


if __name__ == "__main__":
    sys.exit(main())
