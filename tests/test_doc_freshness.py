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
        # NOT a plan (must still be convention-scanned).
        assert not freshness.is_sprint_plan(pathlib.Path("docs/components/sprint_vad.md"))
        assert not freshness.is_sprint_plan(pathlib.Path("docs/standards/sprint_conventions.md"))
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
