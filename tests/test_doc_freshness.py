"""Tests for scripts/check_doc_freshness.py.

Sprint 47 staging-feedback closeout: freshness check now parses the doc's
`*Last updated: YYYY-MM-DD*` line as the comparison source instead of using
the doc's git commit time. The user is told (in CLAUDE.md sprint-closeout
step 1) to bump the stamp; the script needs to actually trust it.

These tests pin:
  - the parser handles the canonical format + variants (with / without
    trailing parenthetical);
  - the parser returns None on missing / malformed input (fallback to the
    git-commit-time path stays intact);
  - end-of-day **UTC** semantics — a same-day code commit doesn't false-
    flag, AND the result is the same regardless of the developer's local
    timezone (Copilot review on PR #100).
"""
import datetime
import importlib.util
import pathlib
import sys

import pytest


# Load the script as a module without running its CLI main(). The script
# isn't on sys.path by default; this is the cleanest way to import a
# scripts/*.py file in-process.
SCRIPT_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "scripts" / "check_doc_freshness.py"
)
spec = importlib.util.spec_from_file_location("check_doc_freshness", SCRIPT_PATH)
freshness = importlib.util.module_from_spec(spec)
sys.modules["check_doc_freshness"] = freshness
spec.loader.exec_module(freshness)


def _make_doc(tmp_path, body):
    p = tmp_path / "test_doc.md"
    p.write_text(body, encoding="utf-8")
    return p


class TestParseLastUpdatedTs:

    def test_canonical_format(self, tmp_path):
        doc = _make_doc(tmp_path, "# Foo\n\n*Last updated: 2026-04-28*\n\nbody\n")
        ts = freshness.parse_last_updated_ts(doc)
        assert ts is not None
        # End-of-day UTC on 2026-04-28 — fixed value regardless of
        # developer's local timezone (Copilot review fix on PR #100).
        expected = datetime.datetime(
            2026, 4, 28, 23, 59, 59, tzinfo=datetime.timezone.utc,
        ).timestamp()
        assert ts == int(expected)

    def test_with_trailing_parenthetical(self, tmp_path):
        doc = _make_doc(
            tmp_path,
            "# Foo\n\n*Last updated: 2026-04-28 (Sprint 47 staging-feedback)*\n\nbody\n",
        )
        ts = freshness.parse_last_updated_ts(doc)
        assert ts is not None
        expected = datetime.datetime(
            2026, 4, 28, 23, 59, 59, tzinfo=datetime.timezone.utc,
        ).timestamp()
        assert ts == int(expected)

    def test_missing_stamp_returns_none(self, tmp_path):
        doc = _make_doc(tmp_path, "# Foo\n\nbody without a stamp\n")
        assert freshness.parse_last_updated_ts(doc) is None

    def test_template_stub_returns_none(self, tmp_path):
        # The README template uses YYYY-MM-DD as a literal placeholder.
        doc = _make_doc(tmp_path, "# Foo\n\n*Last updated: YYYY-MM-DD (Sprint NN)*\n\nbody\n")
        assert freshness.parse_last_updated_ts(doc) is None

    def test_malformed_date_returns_none(self, tmp_path):
        doc = _make_doc(tmp_path, "# Foo\n\n*Last updated: 2026-13-99*\n\nbody\n")
        assert freshness.parse_last_updated_ts(doc) is None

    def test_end_of_day_semantics_beats_same_day_commit_utc(self, tmp_path):
        """A doc stamped 2026-04-28 (end-of-day = 23:59:59 UTC) is newer
        than a code commit at 19:00 UTC the same day. This is the bug
        fix: bumping the stamp once per day should always read as 'fresh'
        for any commit made earlier that UTC-day."""
        doc = _make_doc(tmp_path, "# Foo\n\n*Last updated: 2026-04-28*\n")
        doc_ts = freshness.parse_last_updated_ts(doc)
        # Same-day morning commit timestamp (UTC).
        code_ts = int(datetime.datetime(
            2026, 4, 28, 7, 30, 0, tzinfo=datetime.timezone.utc,
        ).timestamp())
        assert doc_ts > code_ts

    def test_timezone_independence(self, tmp_path):
        """The parsed timestamp must be deterministic across timezones --
        otherwise the freshness check produces different stale/ok results
        on different developer machines / CI environments. Since we treat
        the stamp as end-of-day UTC, the integer timestamp is fixed."""
        doc = _make_doc(tmp_path, "# Foo\n\n*Last updated: 2026-04-28*\n")
        ts = freshness.parse_last_updated_ts(doc)
        # 2026-04-28T23:59:59Z is unix 1777420799 (independent of local TZ).
        assert ts == 1777420799


class TestStaleComparisonUsesParsedStamp:
    """Integration check: when both the parsed stamp and the (mocked) git
    commit time are available, the parsed stamp wins."""

    def test_stale_when_stamp_predates_code(self, tmp_path, monkeypatch):
        # Doc stamped a year before the code commit -> stale.
        doc = _make_doc(
            tmp_path,
            "# Foo\n\n*Last updated: 2025-04-01*\n\n**Tracks:** `scripts/swarm_config.py`\n",
        )
        # The tracked glob must match a file that actually exists in this repo
        # so the comparison branch fires. Force git_commit_time on it to a 2026
        # UTC ts (after the stamp) -> stale.
        future_ts = int(datetime.datetime(
            2026, 4, 28, 12, 0, 0, tzinfo=datetime.timezone.utc,
        ).timestamp())

        def fake_git_ct(path):
            return future_ts if "swarm_config" in str(path) else None

        monkeypatch.setattr(freshness, "git_commit_time", fake_git_ct)
        status, stale, _ = freshness.check_doc(doc)
        assert status == "stale"
        assert any("swarm_config" in str(fp) for fp, _, _ in stale)

    def test_fresh_when_stamp_postdates_code(self, tmp_path, monkeypatch):
        doc = _make_doc(
            tmp_path,
            "# Foo\n\n*Last updated: 2026-04-28*\n\n**Tracks:** `scripts/swarm_config.py`\n",
        )
        # Code committed BEFORE the stamp (UTC) -> fresh.
        past_ts = int(datetime.datetime(
            2026, 4, 27, 12, 0, 0, tzinfo=datetime.timezone.utc,
        ).timestamp())

        def fake_git_ct(path):
            return past_ts if "swarm_config" in str(path) else None

        monkeypatch.setattr(freshness, "git_commit_time", fake_git_ct)
        status, stale, _ = freshness.check_doc(doc)
        assert status == "ok"
        assert stale == []


class TestParseTracks:
    """parse_tracks() must accept space- AND comma-separated **Tracks:**
    lines. The comma case is the gfb.3 bug: a token like `a.py,` (trailing
    comma not stripped) matched no files, producing a spurious
    'matched no files' warning. technical_guide.md uses commas."""

    def test_space_separated(self, tmp_path):
        doc = _make_doc(
            tmp_path,
            "# Foo\n\n**Tracks:** `a/b.py` `c/d.py` `e/*.py`\n",
        )
        assert freshness.parse_tracks(doc) == ["a/b.py", "c/d.py", "e/*.py"]

    def test_comma_separated_strips_trailing_commas(self, tmp_path):
        # The exact shape technical_guide.md uses (gfb.2).
        doc = _make_doc(
            tmp_path,
            "# Foo\n\n**Tracks:** `backend/main.py`, `backend/config.py`, "
            "`backend/routes/*.py`, `firebase.json`, `deploy-*.sh`\n",
        )
        assert freshness.parse_tracks(doc) == [
            "backend/main.py",
            "backend/config.py",
            "backend/routes/*.py",
            "firebase.json",
            "deploy-*.sh",
        ]
        # No token retains a trailing comma (the bug signature).
        assert not any(t.endswith(",") for t in freshness.parse_tracks(doc))

    def test_no_tracks_line_returns_empty(self, tmp_path):
        doc = _make_doc(tmp_path, "# Foo\n\nbody, with a comma, but no tracks\n")
        assert freshness.parse_tracks(doc) == []


class TestFreshnessScanCoversTier1:
    """gfb.3 core bug: the freshness loop iterated find_docs(), which only
    globbed DOC_DIRS — so tier-1 docs with a **Tracks:** line (e.g.
    technical_guide.md) were never freshness-checked. find_docs() now
    includes TIER1_DOCS, and an intentionally-stale tier-1 doc must flag."""

    def test_find_docs_includes_existing_tier1_docs(self):
        docs = freshness.find_docs()
        tier1_on_disk = {
            freshness.REPO_ROOT / rel
            for rel in freshness.TIER1_DOCS
            if (freshness.REPO_ROOT / rel).is_file()
        }
        # Every tier-1 doc that exists on disk must be in the scan set.
        # (This is an integration assertion against the live checkout: it
        # presumes at least one TIER1_DOCS path resolves on disk. In a
        # sparse/partial checkout where none do, the first assert is the
        # signal — fix the checkout or TIER1_DOCS, not this test.)
        assert tier1_on_disk, (
            "no TIER1_DOCS path resolved on disk "
            f"({freshness.TIER1_DOCS}) under {freshness.REPO_ROOT} — "
            "sparse checkout or a renamed tier-1 doc?"
        )
        assert tier1_on_disk.issubset(set(docs))

    def test_find_docs_skips_absent_tier1_docs(self, monkeypatch):
        # A TIER1_DOCS entry that doesn't exist must be silently skipped,
        # not crash or appear in the result.
        monkeypatch.setattr(
            freshness, "TIER1_DOCS",
            freshness.TIER1_DOCS + ["docs/does_not_exist.md"],
        )
        docs = freshness.find_docs()
        assert all("does_not_exist" not in str(d) for d in docs)

    def test_doc_dirs_includes_doctrine(self):
        # bd polyglot-pdf-riffn: docs/doctrine used to be entirely excluded
        # from DOC_DIRS, so a chain violation there (review-flow.md's
        # "Prior, same day" chain) was invisible to the convention scan even
        # though CLAUDE.md/the closeout skill already treat docs/doctrine/*
        # as tier 2. Pin the membership directly, not just via "the checker
        # currently reports clean" (which a DOC_DIRS revert would not break
        # on its own if no doctrine file happened to violate the regex).
        assert "docs/doctrine" in freshness.DOC_DIRS

    def test_find_docs_walks_doctrine_directory(self, tmp_path, monkeypatch):
        # Integration-level companion to the assertion above: prove
        # find_docs() actually WALKS docs/doctrine (not just that the string
        # is in the list) by pointing REPO_ROOT at a synthetic tree.
        monkeypatch.setattr(freshness, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(freshness, "TIER1_DOCS", [])
        doctrine_dir = tmp_path / "docs" / "doctrine"
        doctrine_dir.mkdir(parents=True)
        doctrine_doc = doctrine_dir / "some-doctrine.md"
        doctrine_doc.write_text("# X\n\n*Last updated: 2026-05-20.*\n", encoding="utf-8")
        docs = freshness.find_docs()
        assert doctrine_doc in docs

    # bd polyglot-pdf-3t190: three comment/docstring sites in
    # scripts/check_doc_freshness.py hand-list DOC_DIRS' membership as prose
    # ("docs/components/*.md / docs/standards/*.md") rather than deriving it,
    # so adding docs/doctrine to DOC_DIRS (bd riffn) silently desynced them --
    # the classic enumerate-the-set miss (CLAUDE.md scar #7): some sites were
    # updated, three were not.
    #
    # bd polyglot-pdf-u3miz: the first cut of this pin used a whole-file
    # `source.count(d) >= 2` threshold, which was VACUOUS -- the DOC_DIRS
    # assignment itself plus two ALREADY-correct sites (find_docs() and
    # check_doc_conventions() docstrings) satisfy count>=2 for every entry
    # regardless of whether the three sites this bead actually fixes are
    # stale. Guard the PROPERTY (each of these three specific prose blocks
    # individually names every DOC_DIRS entry), not a proxy count that can
    # be satisfied by unrelated text elsewhere in the file. Isolate each
    # block by a stable anchor string near it, independent of exact line
    # numbers so a later reflow doesn't false-fail this test.
    # bd polyglot-pdf-uquqs: the second cut of this test bounded each site's
    # window by the NEXT anchor in a shared file-order list, replacing a
    # magic 400-char constant. That approach only works when anchors sit
    # CLOSE together -- it broke for the module-docstring site, whose "next"
    # anchor (the main() comment, deep in the file) is ~29,000 chars away,
    # so the computed window swallowed several ALREADY-correct sites in
    # between and passed vacuously even when the module docstring itself
    # was stale. Guard the property directly instead: give each site an
    # EXPLICIT (start_anchor, end_anchor) pair that brackets exactly its own
    # paragraph/comment/string, independent of any other site's position.
    # bd polyglot-pdf-ly00c: two more DOC_DIRS prose sites (find_docs() and
    # check_doc_conventions()'s own docstrings) were correct but unpinned --
    # the bd u3miz test-file comment even named them as "ALREADY-correct",
    # yet they were never added here. Pin the whole set, not the subset that
    # happened to motivate the first fix.
    _SITE_ANCHORS = [
        (
            "This script does two warn-only checks in one pass:",
            "2. **Sprint-archive protocol.**",
            "module docstring",
        ),
        (
            "find_docs() returns tier-1",
            "docs = find_docs()",
            "main() find_docs() comment",
        ),
        (
            "No docs to check (no tier-1 docs on disk",
            "return 0",
            "empty-corpus print",
        ),
        (
            "Return tier-1 + tier-2 docs to scan for freshness, sorted.",
            "docs = list(find_tier1_docs())",
            "find_docs() docstring",
        ),
        (
            "Scan tier-1 + tier-2 docs for forbidden current-state-only violations.",
            "findings: list[tuple[Path, str]] = []",
            "check_doc_conventions() docstring",
        ),
    ]

    @pytest.mark.parametrize("start_anchor,end_anchor,block_name", _SITE_ANCHORS)
    def test_each_doc_dirs_prose_site_names_every_entry(
        self, start_anchor, end_anchor, block_name
    ):
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        idx = source.find(start_anchor)
        assert idx != -1, (
            f"start anchor {start_anchor!r} for the {block_name!r} prose "
            f"block not found -- the site may have been reworded; update "
            f"this test's anchor deliberately, don't just delete it."
        )
        end_idx = source.find(end_anchor, idx + len(start_anchor))
        assert end_idx != -1, (
            f"end anchor {end_anchor!r} for the {block_name!r} prose block "
            f"not found after its start -- the site may have been "
            f"reworded; update this test's anchor deliberately."
        )
        # A tight, EXPLICIT boundary for exactly this site's own paragraph --
        # cannot swallow a sibling site regardless of how any block (this
        # one or another) is reworded, because the end anchor is specific to
        # THIS site, not derived from another site's position.
        window = source[idx:end_idx]
        for d in freshness.DOC_DIRS:
            assert d in window, (
                f"the {block_name!r} prose block does not mention DOC_DIRS "
                f"entry {d!r} -- this is the exact desync bd 3t190 was filed "
                f"against (some sites were updated, this one was not)."
            )

    # bd polyglot-pdf-6j0dj: a FOURTH stale enumeration site (missed by
    # 3t190's own set-enumeration -- CLAUDE.md scar #7 recurring one level
    # in). Rephrased to a generic "any DOC_DIRS subdirectory" claim rather
    # than hand-listing members again, so it cannot desync the same way a
    # fifth DOC_DIRS addition would otherwise silently miss it. Pin that it
    # stays generic (does not regress to a hand-listed two-directory form).
    def test_is_sprint_plan_docstring_refers_to_doc_dirs_generically(self):
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        idx = source.find("def is_sprint_plan")
        assert idx != -1, "is_sprint_plan def not found -- was it renamed?"
        window = source[idx: idx + 1200]
        assert "DOC_DIRS" in window, (
            "is_sprint_plan's docstring no longer refers to DOC_DIRS "
            "generically -- if it now hand-lists directory names again, "
            "restore the generic phrasing or extend "
            "test_each_doc_dirs_prose_site_names_every_entry to cover it."
        )

    # bd polyglot-pdf-lm2oq: CONVENTION_ONLY_DOCS (added by bd r8d9r) is a
    # SECOND membership list feeding check_doc_conventions()'s target union,
    # alongside TIER1_DOCS and DOC_DIRS -- but unlike DOC_DIRS it had no
    # prose pin, which is exactly the unpinned-enumeration shape bd 3t190
    # burned six review rounds on. Pin the two sites that enumerate the
    # CONVENTION-SCANNED set specifically (not the freshness-only set, which
    # DOC_DIRS' _SITE_ANCHORS above already covers): check_doc_conventions()'s
    # own docstring, and docs/doc-architecture.md's "Sprint plans are exempt"
    # paragraph (the one enumeration site outside the script).
    def test_check_doc_conventions_docstring_names_convention_only_docs(self):
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        idx = source.find(
            "Scan tier-1 + tier-2 docs for forbidden current-state-only violations."
        )
        assert idx != -1, "check_doc_conventions() docstring anchor not found"
        end_idx = source.find("findings: list[tuple[Path, str]] = []", idx)
        assert end_idx != -1
        window = source[idx:end_idx]
        assert "CONVENTION_ONLY_DOCS" in window, (
            "check_doc_conventions()'s docstring enumerates its scanned set "
            "but no longer names CONVENTION_ONLY_DOCS -- this is the exact "
            "desync shape CONVENTION_ONLY_DOCS was never pinned against "
            "(bd polyglot-pdf-lm2oq)."
        )

    def test_doc_architecture_sprint_plan_paragraph_names_the_exemption_mechanism(
        self,
    ):
        # doc-architecture.md deliberately does NOT hand-list the scanned
        # set's membership (bd polyglot-pdf-jfq16's lesson, applied
        # preemptively) -- so this doesn't assert "CONVENTION_ONLY_DOCS"
        # appears verbatim. It asserts the paragraph still points at the
        # SOURCE OF TRUTH (is_sprint_plan()'s docstring in the script)
        # rather than re-stating a membership list that could desync again.
        doc_path = (
            pathlib.Path(__file__).resolve().parent.parent
            / "docs" / "doc-architecture.md"
        )
        text = doc_path.read_text(encoding="utf-8")
        idx = text.find("Sprint plans are exempt from this rule.")
        assert idx != -1, "the 'Sprint plans are exempt' paragraph moved or was reworded"
        end_idx = text.find("\n\n", idx)
        window = text[idx:end_idx if end_idx != -1 else idx + 1500]
        assert "is_sprint_plan()" in window and "check_doc_freshness.py" in window, (
            "the 'Sprint plans are exempt' paragraph no longer points at "
            "is_sprint_plan()'s docstring in scripts/check_doc_freshness.py "
            "as the source of truth for the scanned-set membership -- if it "
            "now hand-lists members again, that's the desync shape "
            "bd polyglot-pdf-lm2oq / jfq16 exist to prevent."
        )

    # bd polyglot-pdf-09e35: check_doc_conventions()'s docstring used to
    # claim the tier-1 scan covers "docs/*.md top-level files" -- wrong,
    # TIER1_DOCS is exactly the three named entries below, and several real
    # docs/*.md top-level files (doc-architecture.md, schema_format.md,
    # branch-protection-setup.md, beads-setup.md,
    # archive_completed_plans.md) are NOT in it. Pin the actual membership
    # directly so a future docstring claim can't silently drift from it
    # again -- criterion 2 of the bead requires this exact pin, not just a
    # mention-of-a-different-list check (which is what lm2oq's tests above
    # cover; that's a distinct claim).
    def test_tier1_docs_is_exactly_the_three_named_entries(self):
        assert freshness.TIER1_DOCS == [
            "CLAUDE.md",
            "docs/INDEX.md",
            "docs/technical_guide.md",
        ], (
            "TIER1_DOCS membership changed -- if this is a deliberate "
            "addition/removal, update this pin AND re-check every prose "
            "site that describes TIER1_DOCS's scope (bd polyglot-pdf-09e35) "
            "for staleness, don't just widen this assertion."
        )

    # bd polyglot-pdf-r8d9r: docs/doc-architecture.md -- the file that
    # DEFINES the current-state-only rule -- was exempt from the convention
    # scan that enforces it (not in TIER1_DOCS, not under DOC_DIRS). It
    # can't simply join TIER1_DOCS: TRACKS_RE.search() takes the file's
    # FIRST `**Tracks:**` mention -- its own intro prose, not the fenced
    # **Tracks:** example further down -- and would misparse that prose as
    # a genuine declaration, trying to freshness-check nonexistent globs.
    # CONVENTION_ONLY_DOCS covers it for the convention scan specifically,
    # without subjecting it to the freshness-staleness half.
    def test_doc_architecture_is_in_convention_only_docs(self):
        assert "docs/doc-architecture.md" in freshness.CONVENTION_ONLY_DOCS

    def test_doc_architecture_is_convention_scanned(self, tmp_path, monkeypatch):
        # Integration-level: a REAL chain violation (the canonical
        # "Previously: <date>" shape, no incidental keyword collisions) in
        # THIS file must be caught by check_doc_conventions() -- not merely
        # present in a list somewhere. Point REPO_ROOT at a synthetic tree so
        # this doesn't require mutating the real repo file.
        monkeypatch.setattr(freshness, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(freshness, "TIER1_DOCS", [])
        monkeypatch.setattr(freshness, "DOC_DIRS", [])
        doc_dir = tmp_path / "docs"
        doc_dir.mkdir()
        stacked_stamp_doc = doc_dir / "doc-architecture.md"
        stacked_stamp_doc.write_text(
            "# Doc architecture\n\n"
            "*Last updated: 2026-08-18. Previously: 2026-08-17 a different "
            "fix landed.*\n\nbody\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            freshness, "CONVENTION_ONLY_DOCS", ["docs/doc-architecture.md"]
        )
        findings = freshness.check_doc_conventions(repo_root=tmp_path)
        assert findings, (
            "docs/doc-architecture.md was NOT convention-scanned -- a "
            "chain-shaped stamp in it should have been caught and was not "
            "(the exact regression bd r8d9r was filed against)."
        )
        # Negative control: the SAME setup with CONVENTION_ONLY_DOCS emptied
        # must find NOTHING -- proving the finding above came from being in
        # that list, not from some other scan path picking the file up.
        monkeypatch.setattr(freshness, "CONVENTION_ONLY_DOCS", [])
        findings_without_coverage = freshness.check_doc_conventions(repo_root=tmp_path)
        assert findings_without_coverage == [], (
            "check_doc_conventions() found the doc even with "
            "CONVENTION_ONLY_DOCS emptied -- the positive assertion above "
            "is not actually testing CONVENTION_ONLY_DOCS coverage."
        )

    def test_stale_tier1_doc_with_tracks_is_flagged(self, tmp_path, monkeypatch):
        # Acceptance test from the bead: an intentionally-stale stamp on a
        # tier-1 doc that has a Tracks line gets flagged. We point a fake
        # tier-1 doc at a real repo file and force its commit time past the
        # stamp.
        tier1 = _make_doc(
            tmp_path,
            "# Tier1\n\n*Last updated: 2025-04-01*\n\n"
            "**Tracks:** `scripts/swarm_config.py`\n",
        )
        tier1 = tier1.rename(tmp_path / "fake_tier1.md")
        monkeypatch.setattr(freshness, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(freshness, "TIER1_DOCS", ["fake_tier1.md"])

        future_ts = int(datetime.datetime(
            2026, 4, 28, 12, 0, 0, tzinfo=datetime.timezone.utc,
        ).timestamp())

        # The tracked token must resolve to a real file under the patched
        # REPO_ROOT, so create it; force its commit time to after the stamp.
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "swarm_config.py").write_text("x\n", encoding="utf-8")

        def fake_git_ct(path):
            return future_ts if "swarm_config" in str(path) else None

        monkeypatch.setattr(freshness, "git_commit_time", fake_git_ct)
        docs = freshness.find_docs()
        assert tier1 in docs  # tier-1 doc is in the scan set
        status, stale, _ = freshness.check_doc(tier1)
        assert status == "stale"
        assert any("swarm_config" in str(fp) for fp, _, _ in stale)


# ---------------------------------------------------------------------------
# Sprint-archive protocol checks (added to enforce CLAUDE.md closeout step 5)
#
# The closeout step that moves shipped sprint plans from docs/ root to
# docs/archive/ was silently skipped 11 sprints in a row before it was
# made a numbered checklist item. These tests pin the diff logic so the
# enforcement is mechanical rather than memory-based.
# ---------------------------------------------------------------------------


def _make_index(tmp_path, active_row_body: str | None = None) -> pathlib.Path:
    """Build a minimal INDEX.md fixture with the right table shape.

    `active_row_body` is the body of the cell that carries the active-plan
    links — typically a string with one or more `[`name`](href)` links.
    Pass None to omit the row entirely (tests the "missing row" warning).

    The row mirrors the REAL docs/INDEX.md layout: a leading
    `**Active sprint plans**` label cell, then the literal
    `sprint_<N>_<slug>_plan.md` template token and the active-plan links in
    the SECOND cell. The original fixture put the literal in the first cell,
    which the old anchor matched — but the real INDEX never had that shape,
    so CI stayed green while the checker warned in production
    (bd polyglot-pdf-rt4). Keeping the fixture faithful is what closes that gap.
    """
    head = "# docs/ — Master Index\n\n## Architecture & process\n\n"
    head += "| File | Purpose |\n|------|---------|\n"
    head += "| [`technical_guide.md`](technical_guide.md) | Stuff |\n"
    if active_row_body is not None:
        head += (
            f"| **Active sprint plans** | `sprint_<N>_<slug>_plan.md` -- "
            f"{active_row_body} |\n"
        )
    head += "| [`product_vision.md`](product_vision.md) | Stuff |\n"
    p = tmp_path / "INDEX.md"
    p.write_text(head, encoding="utf-8")
    return p


class TestParseActivePlansFromIndex:
    """The parser pulls plan basenames out of INDEX.md's Active row, and
    correctly ignores `archive/`-prefixed hrefs that are usually contextual
    references rather than claims of currently-active plans."""

    def test_extracts_basenames_from_bare_hrefs(self, tmp_path):
        index = _make_index(
            tmp_path,
            "Active sprint plans (currently "
            "[`sprint_49_9_eager_queue_recompute_plan.md`](sprint_49_9_eager_queue_recompute_plan.md), "
            "[`sprint_51_sms_plan.md`](sprint_51_sms_plan.md))",
        )
        active, warnings = freshness.parse_active_plans_from_index(index)
        assert active == {
            "sprint_49_9_eager_queue_recompute_plan.md",
            "sprint_51_sms_plan.md",
        }
        assert warnings == []

    def test_ignores_archive_prefixed_hrefs(self, tmp_path):
        # archive/* references in the same row are context, not active claims.
        index = _make_index(
            tmp_path,
            "Active sprint plans (currently [`sprint_51_sms_plan.md`](sprint_51_sms_plan.md)). "
            "Completed plans live in [`archive/`](archive/), see "
            "[archive/sprint_47_secretary_revamp_plan.md](archive/sprint_47_secretary_revamp_plan.md)",
        )
        active, warnings = freshness.parse_active_plans_from_index(index)
        assert active == {"sprint_51_sms_plan.md"}
        assert warnings == []

    def test_missing_row_warns(self, tmp_path):
        # No `sprint_<N>_<slug>_plan.md` row in the table at all.
        index = _make_index(tmp_path, active_row_body=None)
        active, warnings = freshness.parse_active_plans_from_index(index)
        assert active == set()
        assert warnings  # must surface a warning
        assert "missing the" in warnings[0].lower() or "missing" in warnings[0].lower()

    def test_missing_index_file_warns(self, tmp_path):
        index = tmp_path / "nope.md"
        active, warnings = freshness.parse_active_plans_from_index(index)
        assert active == set()
        assert warnings
        assert "not found" in warnings[0].lower()

    def test_real_index_row_parses_without_warning(self):
        """Regression for bd polyglot-pdf-rt4: the live docs/INDEX.md row
        leads with a `**Active sprint plans**` label cell and carries the
        literal in the second cell. The old anchor (start-of-row + literal)
        never matched it, so the checker always warned in production while
        this suite stayed green. Run the parser against the REAL file so a
        future row-shape change that breaks the anchor fails CI here."""
        real_index = freshness.REPO_ROOT / "docs" / "INDEX.md"
        if not real_index.is_file():
            import pytest
            pytest.skip("docs/INDEX.md not present in this checkout")
        active, warnings = freshness.parse_active_plans_from_index(real_index)
        # The row must be found and parsed -- no "missing row" warning.
        assert warnings == [], f"unexpected warnings parsing real INDEX.md: {warnings}"
        # ...and href extraction must actually pull active plans out when the
        # row links any. Asserting only `warnings == []` would let a broken
        # PLAN_HREF_RE (or a changed link format) leave `active` empty while
        # warnings stay clean -- the sprint-archive check would silently become
        # a no-op (fresh-eyes finding on PR #46). Tie the assertion to reality
        # (sprint plans actually present at docs/ root) rather than a hardcoded
        # name, so this stays correct between sprints (when none are active).
        root_plans = freshness.find_root_sprint_plans(real_index.parent)
        if root_plans:
            assert active, (
                "INDEX row parsed but extracted no active plan basenames while "
                f"{sorted(root_plans)} exist at docs/ root -- PLAN_HREF_RE or the "
                "INDEX link format may have changed"
            )


class TestCheckSprintArchive:
    """Diff actual root sprint plans against INDEX active claims. Three
    cases that matter: matched (clean), orphan (at root, unlisted), missing
    (listed, absent)."""

    def _make_docs_dir(self, tmp_path, root_plan_names):
        docs = tmp_path / "docs"
        docs.mkdir()
        for name in root_plan_names:
            (docs / name).write_text("# stub\n", encoding="utf-8")
        return docs

    def test_clean_when_root_matches_index(self, tmp_path):
        docs = self._make_docs_dir(
            tmp_path,
            ["sprint_49_9_eager_queue_recompute_plan.md", "sprint_51_sms_plan.md"],
        )
        index = _make_index(
            tmp_path,
            "Active sprint plans (currently "
            "[`sprint_49_9_eager_queue_recompute_plan.md`](sprint_49_9_eager_queue_recompute_plan.md), "
            "[`sprint_51_sms_plan.md`](sprint_51_sms_plan.md))",
        )
        # Place the index inside docs/ to mirror the real layout.
        (docs / "INDEX.md").write_text(index.read_text(encoding="utf-8"), encoding="utf-8")
        orphans, missing, warnings = freshness.check_sprint_archive(docs, docs / "INDEX.md")
        assert orphans == set()
        assert missing == set()
        assert warnings == []

    def test_orphan_at_root_not_in_index(self, tmp_path):
        # Root has TWO plans but INDEX only lists one — the other is the
        # closeout-skipped case (sprint shipped, plan didn't move to archive).
        docs = self._make_docs_dir(
            tmp_path,
            [
                "sprint_47_secretary_revamp_plan.md",  # should have been archived
                "sprint_51_sms_plan.md",
            ],
        )
        (docs / "INDEX.md").write_text(
            _make_index(
                tmp_path,
                "Active (currently [`sprint_51_sms_plan.md`](sprint_51_sms_plan.md))",
            ).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        orphans, missing, warnings = freshness.check_sprint_archive(docs, docs / "INDEX.md")
        assert orphans == {"sprint_47_secretary_revamp_plan.md"}
        assert missing == set()
        assert warnings == []

    def test_missing_listed_in_index_not_at_root(self, tmp_path):
        # INDEX lists a plan that doesn't exist at root — stale reference,
        # likely a forgotten cleanup after the file was archived.
        docs = self._make_docs_dir(tmp_path, ["sprint_51_sms_plan.md"])
        (docs / "INDEX.md").write_text(
            _make_index(
                tmp_path,
                "Active (currently "
                "[`sprint_51_sms_plan.md`](sprint_51_sms_plan.md), "
                "[`sprint_99_imaginary_plan.md`](sprint_99_imaginary_plan.md))",
            ).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        orphans, missing, warnings = freshness.check_sprint_archive(docs, docs / "INDEX.md")
        assert orphans == set()
        assert missing == {"sprint_99_imaginary_plan.md"}
        assert warnings == []

    def test_both_orphan_and_missing(self, tmp_path):
        # Mixed case: one plan at root unlisted, one listed plan absent.
        docs = self._make_docs_dir(tmp_path, ["sprint_47_secretary_revamp_plan.md"])
        (docs / "INDEX.md").write_text(
            _make_index(
                tmp_path,
                "Active (currently [`sprint_99_imaginary_plan.md`](sprint_99_imaginary_plan.md))",
            ).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        orphans, missing, _ = freshness.check_sprint_archive(docs, docs / "INDEX.md")
        assert orphans == {"sprint_47_secretary_revamp_plan.md"}
        assert missing == {"sprint_99_imaginary_plan.md"}

    def test_empty_root_and_empty_index_is_clean(self, tmp_path):
        # No plans anywhere — that's clean (e.g. between sprints).
        docs = self._make_docs_dir(tmp_path, [])
        (docs / "INDEX.md").write_text(
            _make_index(tmp_path, "Active (none currently)").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        orphans, missing, warnings = freshness.check_sprint_archive(docs, docs / "INDEX.md")
        assert orphans == set()
        assert missing == set()
        assert warnings == []


class TestReportSprintArchive:
    """The reporter prints concrete remediation hints when it flags
    something. We verify the orphan + missing branches actually surface
    in stdout — that's what makes the warn-only check actionable."""

    def test_clean_state_quiet_prints_nothing(self, tmp_path, monkeypatch, capsys):
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "INDEX.md").write_text(
            _make_index(tmp_path, "Active (none)").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        flagged = freshness.report_sprint_archive(
            quiet=True, docs_dir=docs, index_path=docs / "INDEX.md",
        )
        out = capsys.readouterr().out
        assert flagged is False
        assert out == ""  # quiet + clean = silent

    def test_clean_state_verbose_prints_clean_marker(self, tmp_path, capsys):
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "INDEX.md").write_text(
            _make_index(tmp_path, "Active (none)").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        flagged = freshness.report_sprint_archive(
            quiet=False, docs_dir=docs, index_path=docs / "INDEX.md",
        )
        out = capsys.readouterr().out
        assert flagged is False
        assert "clean" in out.lower()

    def test_orphan_branch_surfaces_remediation(self, tmp_path, capsys):
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "sprint_47_secretary_revamp_plan.md").write_text("stub", encoding="utf-8")
        (docs / "INDEX.md").write_text(
            _make_index(tmp_path, "Active (none)").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        flagged = freshness.report_sprint_archive(
            quiet=True, docs_dir=docs, index_path=docs / "INDEX.md",
        )
        out = capsys.readouterr().out
        assert flagged is True
        assert "orphaned" in out.lower()
        assert "sprint_47_secretary_revamp_plan.md" in out
        assert "git mv" in out  # actionable hint
        assert "archive_completed_plans.md" in out

    def test_missing_branch_surfaces_remediation(self, tmp_path, capsys):
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "INDEX.md").write_text(
            _make_index(
                tmp_path,
                "Active (currently [`sprint_99_imaginary_plan.md`](sprint_99_imaginary_plan.md))",
            ).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        flagged = freshness.report_sprint_archive(
            quiet=True, docs_dir=docs, index_path=docs / "INDEX.md",
        )
        out = capsys.readouterr().out
        assert flagged is True
        assert "missing" in out.lower()
        assert "sprint_99_imaginary_plan.md" in out
        assert "INDEX.md" in out  # actionable hint


class TestDocConventionsRegexes:
    """The two regexes (PREVIOUSLY_CHAIN_RE + HISTORY_HEADING_RE) detect
    forbidden 'current-state only' violations on tier-1 + tier-2 docs.

    Tier-1 docs (CLAUDE.md, docs/INDEX.md, docs/technical_guide.md, plus any
    others a project adds to TIER1_DOCS) and tier-2 docs (docs/components/*.md,
    docs/standards/*.md) must NOT carry chronological history -- it lives in
    the journal. The CI test below asserts the current repo state has no
    violations; the regex unit tests here pin the detection logic.
    """

    def test_previously_chain_in_stamp_detected(self):
        # Canonical chain shape: "Previously: 2026-05-19. ..."
        assert freshness.PREVIOUSLY_CHAIN_RE.search(
            "*Last updated: 2026-05-20. Previously: 2026-05-19. Sprint 68 ...*"
        ) is not None

    def test_previously_chain_with_sprint_detected(self):
        # Variant: "Previously: Sprint NN ..."
        assert freshness.PREVIOUSLY_CHAIN_RE.search(
            "Previously: Sprint 66 PR 1 shipped..."
        ) is not None

    def test_pedagogical_previously_NOT_flagged(self):
        # CLAUDE.md teaches the rule by name. A bare "Previously:" mention
        # inside backticks or quoted prose (no date / no Sprint NN follow-up)
        # must NOT be flagged or the script reports itself.
        assert freshness.PREVIOUSLY_CHAIN_RE.search(
            "do NOT chain `Previously:` prose into the stamp line"
        ) is None
        assert freshness.PREVIOUSLY_CHAIN_RE.search(
            "the legacy 'Previously:' chain pattern"
        ) is None

    # bd polyglot-pdf-6dn2n/cqyke/f6wb6/riffn: the checker only caught the
    # literal "Previously:" spelling; four real docs shipped "Earlier:" /
    # "Earlier," / "Prior," chains that passed it silently. Pin every
    # keyword x follow-up-shape combination separately (per-parametrization,
    # not one representative case -- a mutation reddening some cases says
    # nothing about the rest).
    @pytest.mark.parametrize("keyword", ["Previously", "Prior", "Earlier"])
    @pytest.mark.parametrize("sep", [":", ","])
    @pytest.mark.parametrize(
        "followup",
        [
            "2026-05-19 the thing happened",
            "Sprint 66 PR 1 shipped",
            "same day (bd `polyglot-pdf-ofh6`): more prose",
            "same-week changes landed",
            "bd polyglot-pdf-6x1j: guarded hard delete",
            "bd `polyglot-pdf-2zk3` corrected the framing",
        ],
    )
    def test_chain_keyword_x_followup_detected(self, keyword, sep, followup):
        text = f"*Last updated: 2026-08-18. {keyword}{sep} {followup}.*"
        assert freshness.PREVIOUSLY_CHAIN_RE.search(text) is not None, (
            f"missed chain shape: {keyword!r} + {sep!r} + {followup!r}"
        )

    @pytest.mark.parametrize("keyword", ["Previously", "Prior", "Earlier"])
    def test_pedagogical_mention_of_each_keyword_NOT_flagged(self, keyword):
        # Same carve-out as the canonical "Previously:" case, now proven for
        # each newly-added keyword: a bare mention with no date/Sprint/bead-id/
        # same-day follow-up must not self-flag.
        assert freshness.PREVIOUSLY_CHAIN_RE.search(
            f"do NOT chain `{keyword}:` prose into the stamp line"
        ) is None

    def test_ordinary_prose_use_of_earlier_prior_NOT_flagged(self):
        # "earlier"/"prior" appear constantly in ordinary prose (never glued
        # to `:`/`,`) -- these must never trip the chain detector.
        assert freshness.PREVIOUSLY_CHAIN_RE.search(
            "earlier same-week changes are in their own entries"
        ) is None
        assert freshness.PREVIOUSLY_CHAIN_RE.search(
            "An earlier version of this doc described a different flow"
        ) is None
        assert freshness.PREVIOUSLY_CHAIN_RE.search(
            "prior art in this space suggests a simpler approach"
        ) is None

    # bd polyglot-pdf-gz7dv: the widened `bd[\s`]` alternative false-positived
    # on ordinary prose that happens to contain the bare word "bd" right
    # after the keyword+separator -- "earlier, bd is the tracker" is not a
    # bead-id reference. Tightened to require the bead-id SHAPE (a
    # backtick-quoted token, or a bare hyphenated token) rather than just the
    # literal "bd". Pin both the fix and its accepted residual gap.
    @pytest.mark.parametrize(
        "text",
        [
            "earlier, bd is the tracker",
            "Prior, bd ready lists it",
        ],
    )
    def test_bare_bd_word_NOT_flagged_as_bead_id(self, text):
        assert freshness.PREVIOUSLY_CHAIN_RE.search(text) is None, (
            f"false-positived on ordinary prose containing the bare word "
            f"'bd': {text!r}"
        )

    @pytest.mark.parametrize(
        "text",
        [
            "Earlier, bd polyglot-pdf-6x1j: guarded hard delete",
            "Prior, same day (bd `polyglot-pdf-ofh6`)",
        ],
    )
    def test_real_bead_id_chain_still_detected_after_bd_tightening(self, text):
        # The bd-tightening fix (above) must not also break detection of the
        # real chain shapes it was widened to catch in the first place.
        assert freshness.PREVIOUSLY_CHAIN_RE.search(text) is not None, (
            f"bd-shape tightening broke detection of a real chain: {text!r}"
        )

    def test_same_day_sprint_residual_false_positive_documented(self):
        # KNOWN ACCEPTED RISK (bd polyglot-pdf-gz7dv): "Prior:"/"Earlier:"
        # immediately followed by literal "same day"/"Sprint N" prose is
        # indistinguishable from a real chain by local pattern matching --
        # this test documents the accepted gap rather than asserting a
        # narrower behavior that doesn't exist. If this ever starts
        # returning None, the regex changed; update this test deliberately,
        # don't just delete it.
        assert freshness.PREVIOUSLY_CHAIN_RE.search(
            "prior: same day we shipped this"
        ) is not None

    def test_update_history_heading_detected(self):
        for heading in (
            "## Update history",
            "### Update history",
            "## Recent sprint history",
            "## Changelog",
            "### Sprint history",
        ):
            assert freshness.HISTORY_HEADING_RE.search(
                f"# Doc\n\nbody\n\n{heading}\n\n- 2026-05-20 thing\n"
            ) is not None, f"failed to match: {heading!r}"

    def test_unrelated_h2_NOT_flagged(self):
        # The regex must not catch arbitrary `##` headers -- only the
        # historical-narrative shapes.
        for heading in (
            "## Routes",
            "## Services",
            "## Design rationale (load-bearing decisions)",
            "## What's safe to change vs. load-bearing",
            "## Tests",
        ):
            assert freshness.HISTORY_HEADING_RE.search(
                f"# Doc\n\nbody\n\n{heading}\n"
            ) is None, f"falsely matched: {heading!r}"


class TestCheckDocConventionsOnTmpDocs:
    """End-to-end check_doc_conventions() exercise against synthetic docs.

    `repo_root=tmp_path` shifts TIER1_DOCS resolution into tmp_path (where
    those tier-1 paths do not exist + are silently skipped), so the only
    docs actually scanned are the explicit `docs=[doc]` list.
    """

    def test_clean_doc_produces_no_findings(self, tmp_path):
        doc = _make_doc(tmp_path, "# Foo\n\n*Last updated: 2026-05-20.*\n\n## Routes\n\nbody\n")
        findings = freshness.check_doc_conventions(docs=[doc], repo_root=tmp_path)
        assert findings == []

    def test_doc_with_previously_chain_flagged(self, tmp_path):
        doc = _make_doc(
            tmp_path,
            "# Foo\n\n*Last updated: 2026-05-20. Previously: 2026-05-19. Sprint 68 ...*\n\nbody\n",
        )
        findings = freshness.check_doc_conventions(docs=[doc], repo_root=tmp_path)
        assert len(findings) == 1
        assert findings[0][0] == doc
        assert "Previously" in findings[0][1]

    # bd polyglot-pdf-fpp6n: the finding message must name the ACTUAL matched
    # keyword, not a hardcoded "Previously:" -- a maintainer greps the
    # reported string to find the violation. Mutation-verified: reverting
    # scripts/check_doc_freshness.py's message construction to the old
    # hardcoded literal makes these fail (confirmed by hand before writing).
    @pytest.mark.parametrize(
        "chain_text,expected_keyword",
        [
            ("Prior: 2026-05-19 the thing shipped", "Prior:"),
            ("Prior, same day (bd `polyglot-pdf-x`)", "Prior,"),
            ("Earlier: 2026-05-19 docs audit", "Earlier:"),
            ("Earlier, bd polyglot-pdf-x: guarded delete", "Earlier,"),
        ],
    )
    def test_finding_message_names_actual_matched_keyword(
        self, tmp_path, chain_text, expected_keyword
    ):
        doc = _make_doc(
            tmp_path,
            f"# Foo\n\n*Last updated: 2026-05-20. {chain_text}*\n\nbody\n",
        )
        findings = freshness.check_doc_conventions(docs=[doc], repo_root=tmp_path)
        assert len(findings) == 1
        assert expected_keyword in findings[0][1], (
            f"finding message {findings[0][1]!r} does not name the actual "
            f"matched keyword {expected_keyword!r}"
        )
        # And it must NOT claim "Previously:" when that isn't what matched.
        if expected_keyword != "Previously:":
            assert "'Previously:'" not in findings[0][1], (
                f"finding message wrongly hardcodes 'Previously:' for a "
                f"{expected_keyword!r} match: {findings[0][1]!r}"
            )

    def test_doc_with_history_section_flagged(self, tmp_path):
        doc = _make_doc(
            tmp_path,
            "# Foo\n\n*Last updated: 2026-05-20.*\n\nbody\n\n## Update history\n\n- 2026-05-20 X\n",
        )
        findings = freshness.check_doc_conventions(docs=[doc], repo_root=tmp_path)
        assert len(findings) == 1
        assert findings[0][0] == doc
        assert "history" in findings[0][1].lower()

    def test_rationale_prose_with_previously_sprint_is_flagged(self, tmp_path):
        # Per the docstring + the strict-mode body audit: rationale-section
        # prose stringing sprint events together is also forbidden. Pin
        # this so a future contributor who tries to "soften" the regex
        # back to stamp-only fails this test.
        doc = _make_doc(
            tmp_path,
            "# Foo\n\n*Last updated: 2026-05-20.*\n\n"
            "## Design rationale\n\n"
            "- Some current decision. Previously: Sprint 47 used the legacy approach.\n",
        )
        findings = freshness.check_doc_conventions(docs=[doc], repo_root=tmp_path)
        assert len(findings) == 1
        assert "Previously" in findings[0][1]

    def test_sprint_plan_is_exempt_from_convention_scan(self, tmp_path):
        # bd polyglot-pdf-h2r.3: sprint plans are a chronological plan of record
        # (tier-2 reachable, NOT tier-1), so the current-state-only convention
        # does NOT apply. A plan that WOULD trip both checks (a `Previously:
        # Sprint NN` chain AND an `## Update history` section) must produce NO
        # findings, because check_doc_conventions skips sprint plans. The plan
        # must live at docs/ root (location-aware exemption).
        docs = tmp_path / "docs"
        docs.mkdir()
        plan = docs / "sprint_9_some_feature_plan.md"
        plan.write_text(
            "# Sprint 9 plan\n\n*Last updated: 2026-06-12.*\n\n"
            "Previously: Sprint 8 took the other approach.\n\n"
            "## Update history\n\n- 2026-06-01 R1 shipped\n- 2026-06-12 R2 shipped\n",
            encoding="utf-8",
        )
        findings = freshness.check_doc_conventions(docs=[plan], repo_root=tmp_path)
        assert findings == []

    def test_component_doc_named_sprint_is_still_scanned(self, tmp_path):
        # Guard the exemption's BOUNDARY: the exemption is for sprint PLANS (at
        # docs/ root or docs/archive/), not for any tier-2 doc whose name starts
        # with `sprint_`. A `docs/components/sprint_vad.md` is a normal
        # current-state component doc and must still be flagged for a history
        # section. (This is the case Finding 3 surfaced -- a basename-only match
        # would have wrongly exempted it.)
        comp = tmp_path / "docs" / "components"
        comp.mkdir(parents=True)
        plan_named = comp / "sprint_vad.md"
        plan_named.write_text(
            "# VAD\n\n*Last updated: 2026-05-20.*\n\nbody\n\n## Changelog\n\n- x\n",
            encoding="utf-8",
        )
        findings = freshness.check_doc_conventions(docs=[plan_named], repo_root=tmp_path)
        assert len(findings) == 1  # NOT exempted -- it is a component doc, not a plan

    def test_is_sprint_plan_predicate(self):
        # The single source of truth for the exemption. Location-aware: only
        # sprint_*.md at docs/ root or docs/archive/ is a plan.
        assert freshness.is_sprint_plan(pathlib.Path("docs/sprint_1_harness_plan.md"))
        assert freshness.is_sprint_plan(pathlib.Path("docs/archive/sprint_3_voice_plan.md"))
        # location boundary: a sprint_-named doc NOT at docs/ root or archive/ is
        # NOT a plan (must still be convention-scanned). Covers all THREE
        # DOC_DIRS members (bd polyglot-pdf-to61i) -- doctrine was missing.
        assert not freshness.is_sprint_plan(pathlib.Path("docs/components/sprint_vad.md"))
        assert not freshness.is_sprint_plan(pathlib.Path("docs/standards/sprint_conventions.md"))
        assert not freshness.is_sprint_plan(pathlib.Path("docs/doctrine/sprint_planning.md"))
        # non-sprint names are never plans.
        assert not freshness.is_sprint_plan(pathlib.Path("docs/technical_guide.md"))
        assert not freshness.is_sprint_plan(pathlib.Path("CLAUDE.md"))
        assert not freshness.is_sprint_plan(pathlib.Path("docs/components/sprint.md"))


class TestCurrentRepoIsCleanOfChainsAndHistorySections:
    """CI gate: every tier-1 and tier-2 doc in this repo must be clean.

    This is the rule that prevents stamp chains and 'Update history' sections
    from accumulating again. The pre-commit hook surfaces violations as
    warnings; this test fails CI if they're committed.
    """

    def test_no_history_chains_in_current_state_docs(self):
        findings = freshness.check_doc_conventions()
        if findings:
            lines = [
                f"  {doc.relative_to(freshness.REPO_ROOT).as_posix()}: {msg}"
                for doc, msg in findings
            ]
            raise AssertionError(
                "Tier-1 / tier-2 docs must be CURRENT STATE ONLY (no `Previously:` "
                "chains, no history sections). Move chronological content into "
                "dev_journal.md. See CLAUDE.md 'Doc maintenance rules'.\n\n"
                "Violations:\n" + "\n".join(lines)
            )


class TestEveryTier2DocHasTracksOrIsExempt:
    """CI gate: a docs/standards/*.md or docs/components/*.md file with no
    ``**Tracks:**`` line is SILENTLY skipped by the freshness-staleness half
    of the scan (parse_tracks() returns [] -> "no dependencies" -> never
    flagged STALE) -- not reported, just invisibly never-checked. That's the
    opposite of the doc-freshness system's whole point: a doc going stale
    unnoticed. bd polyglot-pdf-teizj found docs/standards/schema-key-visibility.md
    in exactly this state (real tracked source files cited throughout its
    prose, but no **Tracks:** line to make the checker see them).

    Pin the SET, not the instance: every doc under DOC_DIRS's two content
    subdirectories (docs/standards, docs/components -- docs/doctrine docs are
    process/workflow docs and are not expected to track source code the same
    way) must carry a **Tracks:** line UNLESS it's on the explicit exemption
    list below. A new doc added without one, and without being deliberately
    added to the exemption list, fails this test instead of silently opting
    out.
    """

    # Index/README pages have no tracked source of their own -- they point at
    # other docs, not code. Adding a doc here must be a deliberate choice,
    # same discipline as CONVENTION_ONLY_DOCS / TIER1_DOCS.
    EXEMPT_FROM_TRACKS_LINE = {
        "docs/standards/README.md",
        "docs/components/README.md",
    }

    def test_every_standards_and_components_doc_has_tracks_or_is_exempt(self):
        missing = []
        for rel_dir in ("docs/standards", "docs/components"):
            for path in sorted((freshness.REPO_ROOT / rel_dir).glob("*.md")):
                rel = path.relative_to(freshness.REPO_ROOT).as_posix()
                if rel in self.EXEMPT_FROM_TRACKS_LINE:
                    continue
                text = path.read_text(encoding="utf-8")
                if not freshness.TRACKS_RE.search(text):
                    missing.append(rel)
        assert not missing, (
            "the following docs/standards or docs/components docs have no "
            "**Tracks:** line, so check_doc_freshness.py silently skips "
            "them instead of ever reporting OK/STALE -- either add a "
            "**Tracks:** line naming the source it documents, or add the "
            "path to TestEveryTier2DocHasTracksOrIsExempt.EXEMPT_FROM_TRACKS_LINE "
            "as a deliberate choice (bd polyglot-pdf-teizj):\n  "
            + "\n  ".join(missing)
        )


class TestFreshnessAcks:
    """The ack: a cheap, squash-proof 'I reviewed this; it is still accurate'
    (bd polyglot-pdf-fytzi).

    WHY THE ACK EXISTS. Before it, the only ways to clear a stale flag were a
    stamp bump (which conflicted between parallel PRs) or a doc commit (noise).
    So the HONEST action -- reading the doc and finding it correct -- left the
    flag ON, and the flag stopped being read: 24 of 28 tracked docs are stale.

    WHY IT IS A FILE AND NOT A SHA. This repo squash-merges, so a branch commit
    never joins dev's history and a recorded branch SHA is orphaned the instant
    its PR merges. A tracked file's `git log -1` resolves to the SQUASH commit
    on dev instead, which is a real ancestor -- so the ack's timestamp survives
    exactly where a SHA would not. test_ack_survives_squash_merge pins that.
    """

    def _doc_tracking_swarm_config(self, tmp_path):
        return _make_doc(
            tmp_path,
            "# Foo\n\n*Last updated: 2025-04-01*\n\n"
            "**Tracks:** `scripts/swarm_config.py`\n",
        )

    def _code_at(self, year):
        return int(datetime.datetime(
            year, 4, 28, 12, 0, 0, tzinfo=datetime.timezone.utc,
        ).timestamp())

    def test_ack_clears_staleness(self, tmp_path, monkeypatch):
        """The core promise: reviewed-and-still-accurate clears the flag."""
        doc = self._doc_tracking_swarm_config(tmp_path)
        code_ts = self._code_at(2026)
        ack_ts = code_ts + 86_400  # acked the day AFTER the code moved

        def fake_git_ct(path):
            if "swarm_config" in str(path):
                return code_ts
            if str(path).endswith(freshness.ACK_SUFFIX):
                return ack_ts
            return None

        monkeypatch.setattr(freshness, "git_commit_time", fake_git_ct)
        # Without an ack the doc is stale...
        assert freshness.check_doc(doc)[0] == "stale"
        # ...and with one it is not.
        monkeypatch.setattr(freshness, "ack_commit_time", lambda d: ack_ts)
        assert freshness.check_doc(doc)[0] == "ok"

    def test_ack_older_than_the_code_does_not_clear(self, tmp_path, monkeypatch):
        """THE MUTATION THAT MATTERS. An ack must not be a permanent
        get-out-of-stale card: once the code moves PAST the ack, the doc is
        stale again. Without this the ack would be strictly worse than the
        stamp it replaces -- ack once, never hear about the doc again."""
        doc = self._doc_tracking_swarm_config(tmp_path)
        code_ts = self._code_at(2026)
        stale_ack = code_ts - 86_400  # acked the day BEFORE the code moved

        def fake_git_ct(path):
            return code_ts if "swarm_config" in str(path) else None

        monkeypatch.setattr(freshness, "git_commit_time", fake_git_ct)
        monkeypatch.setattr(freshness, "ack_commit_time", lambda d: stale_ack)
        status, stale, _ = freshness.check_doc(doc)
        assert status == "stale"
        assert any("swarm_config" in str(fp) for fp, _, _ in stale)

    def test_ack_survives_squash_merge(self, tmp_path, monkeypatch):
        """THE DESIGN'S LOAD-BEARING PROPERTY, pinned.

        Under squash-merge the ack FILE lands on dev inside the squash commit,
        so its commit time is the squash commit's time -- at or after the code
        it was acked against, even though the branch commits are gone. Model
        that: code and ack share one commit timestamp (the squash), and the
        doc must read FRESH. A SHA-anchored design fails here, which is why
        this test exists rather than a SHA-ancestry one."""
        doc = self._doc_tracking_swarm_config(tmp_path)
        squash_ts = self._code_at(2026)

        def fake_git_ct(path):
            return squash_ts if "swarm_config" in str(path) else None

        monkeypatch.setattr(freshness, "git_commit_time", fake_git_ct)
        monkeypatch.setattr(freshness, "ack_commit_time", lambda d: squash_ts)
        # Equal timestamps: the strict `file_ct > doc_ct` compare treats the
        # doc+code-in-one-squash case as fresh, which is correct.
        assert freshness.check_doc(doc)[0] == "ok"

    def test_ack_path_is_unique_per_doc_and_flattened(self):
        """One ack file per doc is what makes acks conflict-free: two sessions
        acking two docs touch two different files. A collision here would
        reintroduce the shared-line problem the ack replaces."""
        a = freshness.ack_path(freshness.REPO_ROOT / "docs/components/auth.md")
        b = freshness.ack_path(freshness.REPO_ROOT / "docs/standards/testing.md")
        assert a != b
        assert a.name == "components__auth.md" + freshness.ACK_SUFFIX
        assert a.parent == freshness.REPO_ROOT / freshness.ACK_DIR
        # Flattened: no nested dirs to create, no path-separator surprises.
        assert "/" not in a.name and "\\" not in a.name

    def test_ack_dir_is_not_gitignored(self):
        """A silently-ignored ack directory fails in the WORST direction: acks
        vanish at commit, every acked doc reads stale again, and the mechanism
        looks broken rather than absent. Pin that the path is committable."""
        import subprocess
        probe = (freshness.REPO_ROOT / freshness.ACK_DIR
                 / ("probe.md" + freshness.ACK_SUFFIX))
        result = subprocess.run(
            ["git", "check-ignore", str(probe)],
            cwd=freshness.REPO_ROOT, capture_output=True, text=True,
        )
        # rc 1 == "not ignored". rc 0 would mean a gitignore rule shadows it.
        assert result.returncode == 1, (
            f"{freshness.ACK_DIR}/ is gitignored -- acks would never reach the "
            f"repo: {result.stdout.strip()}"
        )

    def test_write_ack_records_the_verified_files_and_reason(self, tmp_path, monkeypatch):
        """The ack's CONTENT is the anti-gaming surface. A bare marker gives a
        reviewer nothing to judge; the auto-filled file list plus the mandatory
        reason are what make a blind ack visible in the diff."""
        monkeypatch.setattr(freshness, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(freshness, "git_head_sha", lambda: "abc1234")
        doc = tmp_path / "docs" / "components" / "thing.md"
        doc.parent.mkdir(parents=True)
        doc.write_text("# Thing\n", encoding="utf-8")
        code = tmp_path / "backend" / "thing.py"
        code.parent.mkdir(parents=True)
        code.write_text("x = 1\n", encoding="utf-8")

        ack = freshness.write_ack(doc, "re-read against the handler; unchanged", [code])
        body = ack.read_text(encoding="utf-8")
        assert "verified: backend/thing.py" in body
        assert "because: re-read against the handler; unchanged" in body
        assert "sha: abc1234" in body
