"""Every reviewer agent must carry the read-only-on-the-working-tree rule.

WHY THIS EXISTS (bd polyglot-pdf-fytzi, 2026-08-22). The three reviewer agents
are given `Bash`, and their frontmatter `description:` said "Read-only on the
codebase" -- but that field is ROUTING METADATA the orchestrator reads when
picking an agent, not an instruction the agent itself sees. Nothing in any
agent's BODY said not to mutate the tree.

A reviewer then did exactly what nothing forbade: it ran experiments in the
worktree the author was actively editing, stashed the author's uncommitted fix,
and later restored files outright. The same two fixes had to be reconstructed
twice, and the author spent the round chasing "my change vanished".

These are presence-checks over prose, in the style of test_agents_md.py: they
pin that the RULE and its load-bearing prohibitions exist in each agent's body,
not their exact wording. The set of agents is DERIVED from the directory (any
file whose description says it reviews), so a FOURTH reviewer added later is
covered automatically instead of quietly shipping without the rule -- that is
the enumerate-the-set lesson (CLAUDE.md scar #7) applied to agent prompts.
"""
import pathlib

import pytest

AGENTS_DIR = pathlib.Path(__file__).resolve().parent.parent / ".claude" / "agents"

# The reviewers this rule governs. Derived, not hand-listed: any agent file
# whose name ends in -reviewer is one, so a new reviewer inherits the pin.
REVIEWER_FILES = sorted(AGENTS_DIR.glob("*reviewer*.md"))


def _body(path: pathlib.Path) -> str:
    """The agent's prompt body -- everything AFTER the YAML frontmatter.

    Deliberately excludes frontmatter: a `description:` claiming "read-only"
    is exactly the false comfort that let this bug ship. The agent reads the
    BODY, so the body is what must carry the rule.
    """
    text = path.read_text(encoding="utf-8")
    parts = text.split("---\n", 2)
    return parts[2] if len(parts) >= 3 else text


def test_reviewer_set_is_not_empty():
    """Guard the guard: if the glob stops matching, every test below would
    vacuously pass over an empty set."""
    assert REVIEWER_FILES, f"no *reviewer*.md found under {AGENTS_DIR}"
    names = {p.name for p in REVIEWER_FILES}
    # The three that existed when this rule was written. A missing one means a
    # rename that should be deliberate, not silent.
    assert {
        "fresh-eyes-reviewer.md",
        "docs-reviewer.md",
        "cross-surface-reviewer.md",
    } <= names, f"a known reviewer disappeared or was renamed: {sorted(names)}"


@pytest.mark.parametrize("path", REVIEWER_FILES, ids=lambda p: p.name)
def test_body_states_the_read_only_rule(path):
    """The rule must be in the BODY, not just the frontmatter description."""
    body = _body(path).lower()
    assert "read-only" in body, (
        f"{path.name}: the agent body never says it is read-only. A "
        "`description:` field saying so does NOT reach the agent."
    )


@pytest.mark.parametrize("path", REVIEWER_FILES, ids=lambda p: p.name)
def test_body_forbids_the_commands_that_destroyed_work(path):
    """Name the actual weapons, not just the principle.

    `git stash` and `git checkout`/`restore` are what silently ate the author's
    work; a rule that says only "be careful" would not have stopped it.
    """
    body = _body(path).lower()
    for forbidden in ("git stash", "checkout"):
        assert forbidden in body, (
            f"{path.name}: body does not name `{forbidden}` as forbidden -- "
            "this is the command class that destroyed uncommitted work"
        )


@pytest.mark.parametrize("path", REVIEWER_FILES, ids=lambda p: p.name)
def test_body_carves_out_bead_filing(path):
    """The write ban must not silently forbid the reviewer's OWN output channel.

    `.beads/` is TRACKED in this repo (`git ls-files .beads/` lists it; it is
    not gitignored), so `bd create` writes inside the repo -- which the blanket
    "never write inside the repo" rule technically forbids. An agent reading it
    literally would stop filing beads, which these same files call the one
    intolerable outcome. Caught by the Opus cross-surface review of bd
    polyglot-pdf-fytzi, which spotted the contradiction between two rules in
    the same file.
    """
    # Anchor to the READ-ONLY SECTION, not the whole body. Every reviewer also
    # carries bead-filing INSTRUCTIONS further down (a `bd create ...` command
    # block), so a naive whole-body search for "bd create" passes even with the
    # carve-out deleted -- verified: it did. That is a test passing for the
    # wrong reason, which proves nothing about the rule it claims to guard.
    body = _body(path)
    start = body.index("## YOU ARE READ-ONLY")
    end = body.index("\n## ", start + 1)
    section = body[start:end].lower()
    # Assert the SANCTIONED COMMANDS, not the vocabulary. A keyword check for
    # "exception"/"bead" is defeatable by a decoy that uses both words while
    # NEGATING the rule ("There is no exception here; a bead is not relevant")
    # -- verified: such a decoy passed. Naming the commands the reviewer must
    # be allowed to run is the part with actual content.
    assert "bd create" in section, (
        f"{path.name}: the read-only section must name `bd create` as allowed. "
        ".beads/ is TRACKED, so a blanket 'never write inside the repo' "
        "forbids the reviewer's own output channel unless carved out here."
    )
    # And the carve-out must stay NARROW: hand-editing those files is still
    # banned, or the exception swallows the rule.
    assert "hand-edit" in section, (
        f"{path.name}: the bead carve-out must still forbid hand-editing "
        ".beads/ files -- otherwise it licenses arbitrary writes there"
    )


@pytest.mark.parametrize("path", REVIEWER_FILES, ids=lambda p: p.name)
def test_body_still_permits_verification(path):
    """The rule must not read as 'do less work'.

    A reviewer that stops running tests to stay safe is a worse reviewer. The
    prompt has to say tests are encouraged and give the mutation-testing
    workaround, or the fix trades one failure mode for another.
    """
    body = _body(path).lower()
    assert "run tests" in body or "running tests" in body, (
        f"{path.name}: body forbids writing without explicitly permitting "
        "test runs -- reviewers must not read this as 'verify less'"
    )
