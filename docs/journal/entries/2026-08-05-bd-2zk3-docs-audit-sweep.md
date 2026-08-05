---
date: 2026-08-05
bead: polyglot-pdf-2zk3
title: "Docs audit: full-verification sweep of the tier 1-2 living docs"
tags: [docs, architecture, review-harness]
---

## Trigger

Maintainer-directed docs audit (2026-08-05): with 4-5 sessions closing out
concurrently, the tiered docs drift. The maintainer asked for every claim in
the tier 1-2 living references verified against code (explicitly opting into
Workflow fan-out with Haiku/Sonnet agents), full restructuring autonomy, and
sprint-plan archiving in scope; individual journal entries out of scope.
Companion to bd polyglot-pdf-n18q (the surface-contract map, PR #548).

## What shipped

Two Workflow fan-outs. First, 40 per-doc verifiers (28 Sonnet on code-coupled
docs, 12 Haiku on process docs) traced ~1,300 claims to code and returned 110
structured findings. After orchestrator triage, 29 fix agents applied 109
verified fixes (0 rejected; several agents corrected additional rot found in
passing). Notable drift caught: ws-protocol.md carried 35 stale line
citations; schema_format.md used an invalid enum value (supplement_b) in its
examples, had an omn_number/omb_number typo, and never documented
checkbox_group or schema_version; testing.md still said no E2E suite exists
(the voice-harness shipped 2026-06-09); validation-delegation.md's opening
claimed the validator REPLACED the in-SI ADDRESS-CONSISTENCY prose (it is
additive; the prose stays); config-deployment.md documented USE_DTI's default
as false (flipped true in bd 7872); auth.md denied the existence of
AuthContext.test.tsx; hipaa-pii-policy.md called StructuredLogger dead (it
logs token telemetry every turn).

Restructures (orchestrator-applied): sprint plans 1, 6, 8, and 11 archived
per protocol (epics hrn/s4dp/js7q/fc7t closed) with rows in
archive_completed_plans.md; the shelved sliding-window go/no-go brief
archived with a superseded banner; INDEX.md's active-sprint-plans cell
compressed from ~2,600 chars of prose to one clause per plan; the 2026-05-30
reorientation brief demoted everywhere to a historical snapshot in favor of
technical_guide.md's Surface contracts map; CLAUDE.md scar 5 corrected (the
part-named SI holdout was deleted in bd en2j); doc-architecture.md now calls
itself tier-2 and explicitly bans "Prior:" chain synonyms -- a dozen docs had
accumulated multi-entry stamp chains the checker's Previously:-only regex
never catches; every touched doc now carries the one-line stamp.

## Lessons

- Line-number citations rot fastest; the freshness gate (Tracks: lines) is
  what makes them maintainable at all. Docs whose Tracks lines were narrow
  (ws-protocol) rotted silently for weeks.
- The current-state-only rule needs to ban the PATTERN, not the keyword:
  "Prior:" chains passed the mechanical check while violating the rule.
- Fix agents must re-verify findings before applying: verifier suggestions
  were occasionally wrong in detail (a swapped line-order, a mis-attributed
  apply site) and the re-verification step caught them.

## Doc freshness

check_doc_freshness.py --all fully clean (freshness, sprint-archive protocol,
conventions); tests/test_doc_freshness.py 42/42; relative-link sweep over all
43 changed docs clean after repairing 7 links broken by the archive moves.

## Files touched

43 docs: CLAUDE.md, docs/INDEX.md, docs/doc-architecture.md,
docs/schema_format.md, docs/beads-setup.md, docs/branch-protection-setup.md,
docs/archive_completed_plans.md, docs/components/*.md (12),
docs/standards/*.md (15), docs/doctrine/*.md (4), five files moved into
docs/archive/, plus this entry.
