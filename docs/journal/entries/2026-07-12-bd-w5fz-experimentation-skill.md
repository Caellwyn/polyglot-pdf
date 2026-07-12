---
date: 2026-07-12
bead: polyglot-pdf-w5fz
title: "Research skill: mandatory lit-review of prior journals/spike findings + maintainer-approved cost estimate before experiments"
tags: [doctrine, harness, conventions]
---

## Trigger

Maintainer directive (2026-07-12): create a repo skill that gates all
measurement/probe work on two steps -- a literature review of prior work, and
a maintainer-approved cost estimate -- before any live-model API spend. The
motivating incidents were concrete, not hypothetical: bd `polyglot-pdf-6cfu.5`
(2026-07-11/12) nearly re-ran a pro-tier form-level validator sweep with an
untuned prompt when `g1c_tuning_findings.md` already showed the tuned prompt
lifting flash-lite precision 0.77->0.96 @20-field chunks; and one Vertex
`gemini-2.5-flash` probe arm (bake-off, 2026-07-11, 107 calls) emitted 595k
thinking-output tokens = $1.49 = 92% of that day's entire Vertex bill, because
Vertex enables thinking on `2.5-flash` by default and nobody set a budget.
Tracked as bd `polyglot-pdf-w5fz`.

## What shipped

`.claude/skills/experimentation/SKILL.md` (named `experimentation`, not
`research`, per a follow-up maintainer request in the same session -- "research"
risked being confused with web search). Two mandatory gates:

- **Gate 1 (prior-work audit):** search `scripts/spikes/*_findings.md`,
  `docs/journal/entries/` (via `docs/journal/TAGS.md`), `bd memories`/`bd recall`,
  and existing `backend/scripts/probe_*.py` / `scripts/spikes/*.py` scripts
  before writing new code; explicitly flags anything dated before the
  `google-genai` 1.38.0 -> 2.8.0 SDK cutover (2026-06-11, PR #156) as a stale
  hypothesis needing a re-check, not settled fact.
- **Gate 2 (cost estimate + go-ahead):** a formula tied to the live
  `GEMINI_PRICING_BY_FAMILY` table in `backend/config.py`, the flash-lite-by-
  default rule, the Vertex-thinking-budget trap, and a per-instance go-ahead
  threshold before spending (mirroring the demo-deploy per-instance-ask
  posture in CLAUDE.md), plus mid-sweep pruning discipline learned from the
  `0zp3` ~$80 surprise bill (an already-rejected model carried through a full
  multi-round sweep because nobody pruned it after round 1).

The skill also covers running the probe correctly (Vertex-only per the
2026-07-12 directive, deploy-fidelity per the `h04c` 1011 incident,
serialize-for-clean-measurement, the `get_settings` by-reference monkeypatch
trap from `jnjj.25`, distrust-your-own-harness-code from the `g3` cost-harness
investigation), links out to the `voice-harness` and `run-local` skills for
generating realistic app traffic, and closes with how to record findings so
the next session's Gate 1 audit actually finds them (extend
`scripts/spikes/<topic>_findings.md`, update the invariant doc if one changed,
`bd remember` durable process lessons).

Two doc-map pointers were added so future sessions discover the skill:
`CLAUDE.md`'s "Before changing..." trigger table (a new row for
measurement/probe experiments) and `docs/standards/testing.md`'s
"Live-endpoint probes and spikes" section (a lead-in sentence pointing to the
skill before the deploy-fidelity rule, since that section is the natural
landing spot for anyone about to write a probe).

No out-of-scope findings; nothing deferred.

## Lessons

This entry is itself the record of the lit-review-first / cost-estimate-first
lesson (already captured as bd memory `research-lit-review-before-experiments`
and `cost-discipline-for-live-model-experiments-learned-the`); the skill is
the durable, discoverable enforcement mechanism the maintainer asked for so
the lesson isn't only in memory. No new generalizable lesson beyond what the
skill itself encodes.

## Doc freshness

Bumped `docs/standards/testing.md`'s `*Last updated:*` line (added the skill
pointer above the deploy-fidelity section) and added one row to `CLAUDE.md`'s
doc-map table (CLAUDE.md has no `**Tracks:**` line so the freshness checker
does not track it directly). `scripts/closeout_prep.py`'s doc-freshness pass
flagged a long list of other STALE docs (`docs/components/*`,
`docs/standards/ai-models.md`, etc.) -- all pre-existing staleness from
unrelated code changes elsewhere on `dev` (e.g. `backend/config.py`,
`live_ai_gemini.py`, `websocket_routes.py` edits from other merged PRs), none
of which this PR's diff touches. Left as-is per the prep script's own
guidance ("if a stale doc tracks files your branch did NOT touch, leave it").

## Files touched

- `.claude/skills/experimentation/SKILL.md` -- new skill (created)
- `CLAUDE.md` -- added a doc-map row pointing to the new skill
- `docs/standards/testing.md` -- added a lead-in pointer to the skill above
  the "Live-endpoint probes and spikes" section; bumped `*Last updated:*`
- `docs/journal/entries/2026-07-12-bd-w5fz-experimentation-skill.md` -- this entry
