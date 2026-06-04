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
  - It must encode the NORMAL-PR parallel-review flow: open a non-draft PR
    (Copilot round 1 fires on open, in parallel with fresh-eyes), fix the
    combined issues, loop Copilot until no comments, then close the bead +
    ping Josh to merge. NO drafts and NO ready-flip -- the draft->ready flip
    is itself a Copilot trigger and would cost a redundant review (Copilot
    tokens are scarce). Regression guards assert both the old "hard stop
    before `gh pr create`" wording AND the draft/ready-flip wording are gone.
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


def test_opens_normal_pr_and_parallel_reviews(body):
    # The flow opens a NORMAL PR (Copilot round 1 fires on open) and runs
    # fresh-eyes in parallel. Pin against the BODY so the operative
    # instruction is checked, not a description mention.
    lo = body.lower()
    assert "gh pr create" in body
    assert "pr_review_watcher.py" in body  # review watcher started for a review-worthy PR
    assert "fresh-eyes" in lo          # fresh-eyes spawned alongside


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


def test_copilot_loops_until_clean(body):
    # The Copilot round is not one-shot: adopt -> push -> re-review until it
    # reports no comments. Assert against the BODY (not the description) so the
    # operative loop instruction is what's pinned. The re-review is REQUESTED by
    # re-requesting the reviewer (NOT an @-mention comment -- that invokes the
    # coding agent, bd polyglot-pdf-1pr), and all four watch states (incl.
    # TIMEOUT) must be handled -- a TIMEOUT must never be treated as clean.
    lo = body.lower()
    assert re.search(r"(until|loop)[^\n]*(clean|no comment)", lo), \
        "skill body must loop Copilot until it has no comments"
    assert "requested_reviewers" in lo, \
        "skill must re-request the reviewer (the reviewer API) to re-trigger review"
    # Regression guard: the @-mention must NOT be POSTED as a comment body -- that
    # invokes the Copilot coding agent, not code review (bd polyglot-pdf-1pr). The
    # skill may NAME the pattern to forbid it (it does), so guard the active
    # trigger shape (`-f body=...@copilot please review`), not the mere mention.
    assert not re.search(r"body=['\"]?@copilot please review", body), \
        "skill must NOT POST @copilot please review as a comment (invokes the coding agent)"
    assert "timeout" in lo, "skill must handle pr_review_watcher's TIMEOUT state"


def test_ping_to_merge_is_the_autonomous_endpoint(body):
    # The autonomous endpoint is: Copilot clean -> close bead -> ping the
    # maintainer to merge. There is no ready-flip (no draft). The merge is the
    # maintainer's (allow_auto_merge=false) and the skill must forbid auto-merge.
    lo = body.lower()
    assert "ping" in lo and "maintainer" in lo
    assert "allow_auto_merge" in body  # the interlock that keeps merge manual
    assert "gh pr merge" in body and re.search(r"never run `gh pr merge`", lo), \
        "skill must explicitly forbid running gh pr merge"
    # Regression guards: neither the old hard-stop NOR the draft/ready-flip
    # design may reappear.
    assert "hard stop before `gh pr create`" not in lo
    assert "do not run `gh pr create`" not in lo
    assert "gh pr ready" not in body


def test_mentions_fresh_eyes_review(skill_text):
    assert "fresh-eyes" in skill_text.lower()
    assert ".claude/agents/fresh-eyes-reviewer.md" in skill_text
