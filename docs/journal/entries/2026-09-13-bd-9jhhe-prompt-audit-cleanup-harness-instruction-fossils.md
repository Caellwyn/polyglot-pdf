---
date: 2026-09-13
bead: polyglot-pdf-9jhhe
title: "Prompt-audit cleanup: harness instruction fossils"
tags: [harness, doctrine, conventions]
---

## Trigger

The maintainer ran `/claude-api prompt-audit` (2026-09-12) over the whole
worktree. The audit covers three prompt surfaces with three target models: the
Gemini Live system instruction and tool declarations (Gemini 2.5 / 3.1), the
schema-editor extraction pipeline that calls Claude through the local CLI
(Opus 5), and the Claude Code harness files (Fable 5.1 orchestrator with
Sonnet / Haiku / Opus subagents). The first two came back clean: every emphatic
line on the Gemini surface is either a developer comment, vendor-recommended
language-adherence phrasing, or a prohibition tied to a measured regression on
the current model, and the CLI transport makes prefill / `budget_tokens` /
forced `tool_choice` structurally absent from the extraction path. The
findings were in the harness files, and they were not shouting (CLAUDE.md has
three reasoned NEVERs). They were migration-relative phrasing: rules written as
diffs against a policy the model never saw.

## What shipped

- `.github/copilot-instructions.md` deleted. It scripted a Copilot review
  protocol (poll for `LGTM`, assign the PR to the watcher) that CLAUDE.md
  declares dead path; no workflow under `.github/workflows/` references it.
  `docs/doctrine/branch-protection-setup.md` no longer names it.
- `voice-harness/SKILL.md`: the runnable example used the field id its own
  preamble says no longer exists in the v2 schema; it now carries a placeholder
  pointing at bd `polyglot-pdf-tcemw`. The `mcp__Claude_in_Chrome__*` literal
  (which matched no tool in the current session) became a capability
  description. The resolved-incident retrospective for bd `0ux` was condensed
  to one sentence stating what the harness is for.
- `CLAUDE.md`: the `gh pr merge` and `deploy-demo.sh` permissions are stated
  directly instead of as "NO LONGER on the NEVER list (autonomy increase
  <date>)". The dead-path sentence about `@codex review` /
  `pr_review_watcher.py` / `requested_reviewers` now lives in one operative
  place (closeout `SKILL.md` Step 5.6 and its hard-rules header) and was cut
  from three restatements.
- `run-local/SKILL.md`: "As of 2026-06-10" dropped from a standing permission.
- `experimentation/SKILL.md`: "the old claim was overturned" rewritten as the
  current rule.
- `fresh-eyes-reviewer.md`: the fictional $1000 bounty line removed; the
  sentence's real requirement ("be specific and well-reasoned") stays.
- `scripts/spikes/dependency_inventory_bake.py`: default model
  `claude-opus-4-8` -> `claude-opus-5`, matching its sibling spike.

Report-only findings left for a later pass (not filed as beads: they are
layout preferences on working text, not defects): the ~80 lines of shared
convention triplicated across the three reviewer agents, the four "deliberately
conservative for now" hedges in CLAUDE.md's escalation section, and the
effort-400 Workflow fallback, which is still load-bearing and self-flagged for
removal once the upstream bug is fixed.

Review record: fresh-eyes (Sonnet) NO-GAPS in one round, all three exit
criteria PASS. Opus cross-surface review, one pass, GAPS-FOUND (2), both
dispositioned without a code change: (1) `tests/e2e/voice-harness/RUNBOOK.md`
still names the retired `p1_line1_aliennumber` field id -- pre-existing on
`origin/dev`, owned by bd `polyglot-pdf-tcemw`; (2) the same runbook still
mandates the Chrome MCP tool sequence the skill no longer names -- a docs
consistency nit, filed with (1) as bd `polyglot-pdf-gicvm`. The retired
`scripts/pr_review_watcher.py` comment citing the deleted file is bd
`polyglot-pdf-cknwq`. The reviewer also traced two contracts the inner
enumeration omitted (the CLAUDE.md dead-path sentence removal against
`tests/test_claude_md_review_flow*.py`, and the bounty-line removal against
`tests/test_reviewer_agents_are_read_only.py`): both green.

## Lessons

- An instruction file can be a fossil while every sentence in it is
  individually true. `copilot-instructions.md` described a real protocol; the
  protocol just had no reader. The tell is a governing doc that names the
  mechanism as retired while the mechanism's own file survives.
- A skill's runnable example is the part that gets copy-pasted, so a
  mid-migration warning in the preamble does not protect it. Put the
  placeholder in the command, not above it.
- "NO LONGER on the NEVER list" is a changelog entry, not a rule. The
  freshness checker's `Previously:` regex does not catch this shape, so it
  survived in the one file whose own rule forbids it.

## Doc freshness

`docs/standards/bead-tiers.md` tracks `.claude/agents/`; its prose (reviewer
roster and tier routing) is unaffected by the bounty-line removal, so it was
reviewed and its stamp bumped. `CLAUDE.md` carries no stamp. Every other doc
prep flagged stale tracks files this branch did not touch and was left as-is.
Beads housekeeping: no orphans; the two stale in-progress beads (`0dsv4`,
`ih428`) belong to the maintainer's other active work and were left as-is.
`docs/doctrine/branch-protection-setup.md` prose updated (one sentence) to
reflect the deletion; no stamp bump because the checker did not flag it stale.

## Files touched

- `.github/copilot-instructions.md` (deleted)
- `CLAUDE.md`
- `.claude/skills/closeout/SKILL.md`
- `.claude/skills/voice-harness/SKILL.md`
- `.claude/skills/run-local/SKILL.md`
- `.claude/skills/experimentation/SKILL.md`
- `.claude/agents/fresh-eyes-reviewer.md`
- `docs/doctrine/branch-protection-setup.md`
- `docs/standards/bead-tiers.md` (stamp)
- `scripts/spikes/dependency_inventory_bake.py`
- `docs/journal/entries/2026-09-13-bd-9jhhe-prompt-audit-cleanup-harness-instruction-fossils.md`
