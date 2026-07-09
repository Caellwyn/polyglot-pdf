"""Structural contract for the /closeout skill (.claude/skills/closeout/SKILL.md).

The skill is step 3 of the agent-swarm epic (bd 32qp). These are NOT behavior
tests (a skill body is a prompt, not code) -- they pin the frontmatter and
body invariants that, if broken, would silently change how the skill runs:

  - name must match the directory (Claude Code requirement) and be kebab-case.
  - It must NOT carry `disable-model-invocation` (the orchestrator is allowed
    to auto-trigger closeout) and must NOT carry `context: fork` (forking
    would lose main-thread beads serialization -- the whole reason it stays
    inline, per the plan).
  - It must reference the deterministic scripts it wraps (the three step-2
    scripts + check_doc_freshness), so a rename without a skill update is caught.
  - It must encode the Claude-only review flow (2026-07-08): a Sonnet/Haiku
    fresh-eyes inner loop (pre-PR, looped to NO-GAPS) and an Opus-4.8 outer review
    (two independent clearing passes), then open a non-draft PR and make the merge
    decision: auto-merge a routine low-risk PR that reviewed CLEAN, else ping the
    maintainer for a consequence-bearing one (bd 16pj). There is NO external
    reviewer -- the `@codex review` trigger, `pr_review_watcher.py`, and
    `requested_reviewers` are dead path. NO drafts and NO ready-flip. Regression
    guards assert the old "hard stop before `gh pr create`" wording, the
    draft/ready-flip wording, AND the old blanket "never run `gh pr merge`" ban are
    all gone.
"""

import pathlib
import re

import pytest


SKILL_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / ".claude" / "skills" / "closeout" / "SKILL.md"
)


@pytest.fixture(scope="module")
def skill_text():
    assert SKILL_PATH.exists(), "{} is missing".format(SKILL_PATH)
    return SKILL_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def frontmatter(skill_text):
    m = re.match(r"^---\n(.*?)\n---\n", skill_text, re.DOTALL)
    assert m, "SKILL.md must open with a YAML frontmatter block"
    return m.group(1)


@pytest.fixture(scope="module")
def body(skill_text):
    # The skill body with the YAML frontmatter stripped. Body-contract tests
    # assert against THIS, not skill_text -- otherwise a phrase that lives only
    # in the `description:` frontmatter could satisfy a body invariant (the
    # operative instructions are in the body, the description is just metadata).
    return re.sub(r"^---\n.*?\n---\n", "", skill_text, count=1, flags=re.DOTALL)


# --- frontmatter contract ---

def test_name_matches_directory_and_is_kebab(frontmatter):
    m = re.search(r"^name:\s*(\S+)\s*$", frontmatter, re.MULTILINE)
    assert m, "frontmatter must declare a name"
    name = m.group(1)
    assert name == "closeout", "name must match the directory 'closeout'"
    # Claude Code's kebab-case pattern.
    assert re.fullmatch(r"[a-z][a-z0-9-]*[a-z0-9]", name)


def test_has_description(frontmatter):
    assert re.search(r"^description:\s*\S", frontmatter, re.MULTILINE)


def test_is_model_invocable(frontmatter):
    # The orchestrator MAY auto-trigger closeout, so the field that would
    # disable that must be absent (the plan + Josh confirmed this).
    assert "disable-model-invocation" not in frontmatter


def test_runs_inline_not_forked(frontmatter):
    # context: fork would run the body in a forked subagent and lose
    # main-thread beads serialization -- explicitly NOT wanted.
    assert "context:" not in frontmatter
    assert "agent:" not in frontmatter


# --- body contract ---

def test_references_the_wrapped_scripts(skill_text):
    # The deterministic scripts the skill wraps, plus the reused freshness
    # checker -- a rename of any of these without updating the skill is caught.
    for script in (
        "scripts/closeout_housekeeping.py",
        "scripts/journal_scaffold.py",
        "scripts/bd_safe.py",
        "scripts/check_doc_freshness.py",
        "scripts/closeout_finish.py",
    ):
        assert script in skill_text, "skill must reference {}".format(script)


def test_documents_mechanical_handoff(skill_text):
    # The skill must describe the closeout-runner delegation + the --dry-run
    # preview (bd polyglot-pdf-hrn.13) so the cheap-model handoff stays documented.
    assert "closeout-runner" in skill_text
    assert "--dry-run" in skill_text


def test_covers_doc_freshness_step(skill_text):
    # The skill must run the freshness checker and point at the doc-architecture
    # system that governs which docs to bump.
    assert "check_doc_freshness.py" in skill_text
    assert "doc-architecture.md" in skill_text


def test_opens_normal_pr_and_claude_reviews(body):
    # The flow opens a NORMAL PR and reviews it entirely with Claude: a fresh-eyes
    # inner loop (pre-PR) and an Opus-4.8 outer review. Pin against the BODY so the
    # operative instruction is checked, not a description mention.
    lo = body.lower()
    assert "gh pr create" in body
    assert "fresh-eyes" in lo          # inner-loop reviewer
    assert "opus" in lo                # outer-review model
    # There is NO external bot watcher in the operative flow anymore -- the outer
    # review is orchestrator-driven subagents read directly.
    assert "no bot watcher" in lo or "read directly" in lo, \
        "skill must state the outer review is read directly, not bot-watched"


def test_no_draft_pr(body):
    # Drafts are forbidden: the draft->ready flip is a redundant Copilot
    # trigger (scarce tokens). The skill may MENTION --draft in a prohibition
    # ("Do NOT pass --draft"), but must never INVOKE `gh pr create ... --draft`
    # and must never flip a draft to ready.
    assert not re.search(r"gh pr create[^\n]*--draft", body), \
        "skill must NOT invoke `gh pr create --draft`"
    assert "gh pr ready" not in body, "skill must NOT flip a draft to ready"
    # The prohibition prose SHOULD be present (positive signal that the
    # no-draft rule is explicit, not just absent).
    assert re.search(r"(do not|don't|never)[^\n]*`--draft`", body.lower()), \
        "skill should explicitly forbid --draft"


def test_outer_review_loops_until_clean(body):
    # The Opus-4.8 outer review is not one-shot: fix -> re-spawn until two
    # independent Opus passes both clear (NO-GAPS on the identical diff). Assert
    # against the BODY so the operative loop instruction is pinned. Review is
    # entirely Claude-based -- there is NO external reviewer and NO bot-trigger.
    lo = body.lower()
    assert "opus" in lo, "skill body must name the Opus-4.8 outer reviewer"
    assert re.search(r"(until|loop)[^\n]*(clean|no-gaps)", lo), \
        "skill body must loop the outer review until it clears"
    assert "two independent" in lo, \
        "skill must require two independent Opus clearing passes"
    # Regression guard: the retired external-reviewer triggers must NOT be the
    # active mechanism. `@codex review`, `requested_reviewers`, and
    # `pr_review_watcher.py` may appear ONLY in an explicit retired/dead-path/
    # do-not-use note, never as a live instruction.
    for needle in ("@codex review", "requested_reviewers", "pr_review_watcher"):
        for line in body.splitlines():
            if needle in line.lower():
                l = line.lower()
                assert any(w in l for w in (
                    "never", "do not", "retired", "dead path", "ignore", "no ")), \
                    "{} may appear only in a retired/do-not-use note: {}".format(
                        needle, line)


def test_merge_endpoint_is_auto_merge_or_ping(body):
    # Autonomy increase (bd polyglot-pdf-16pj, 2026-07-04): the endpoint is a
    # FORK, not an unconditional ping. A routine low-risk PR that an adversarial
    # reviewer cleared CLEAN with green checks is AUTO-MERGED (gh pr merge); a
    # consequence-bearing PR is pinged to the maintainer. There is still no
    # ready-flip (no draft), and force-push stays barred.
    lo = body.lower()
    # Both arms of the fork must be present.
    assert "ping" in lo and "maintainer" in lo, "ping arm must remain"
    assert "gh pr merge" in body and "auto-merge" in lo, \
        "skill must describe the auto-merge arm"
    assert "consequence-bearing" in lo, \
        "skill must gate auto-merge on the consequence-bearing test"
    # The skill must NOT reinstate the old blanket ban on merging.
    assert not re.search(r"never run `gh pr merge`", lo), \
        "the blanket 'never run gh pr merge' ban was removed under bd 16pj"
    # Force-push / force dolt-push stay barred regardless of the merge change.
    assert "force" in lo, "force-push must still be called out as barred"
    # Regression guards: neither the old hard-stop NOR the draft/ready-flip
    # design may reappear.
    assert "hard stop before `gh pr create`" not in lo
    assert "do not run `gh pr create`" not in lo
    assert "gh pr ready" not in body


def test_mentions_fresh_eyes_review(skill_text):
    assert "fresh-eyes" in skill_text.lower()
    assert ".claude/agents/fresh-eyes-reviewer.md" in skill_text
