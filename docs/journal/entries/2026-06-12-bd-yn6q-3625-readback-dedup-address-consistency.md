---
date: 2026-06-12
bead: polyglot-pdf-yn6q
title: "Dedup per-field read-back in confirmation policy (yn6q) + address-consistency prompt block (3625)"
tags: [conventions, hotfix]
---

## Trigger

Two maintainer live-demo reports (2026-06-11), bundled because both are pure
prompt-template work in the same files: (1) polyglot-pdf-yn6q -- Gemini read
each confirmed value back twice in section 1; (2) polyglot-pdf-3625 -- Gemini
silently accepted West Virginia + an Iowa zip code + a Canadian province with
no cross-check.

## What shipped

yn6q: `get_confirmation_policy` (backend/services/ai_context.py) for sections
1-2, the last section, and the non-sectioned default ended with a per-field
directive ("Confirm each field with the user before moving on" / "Only
proceed after user confirms") that duplicated WORKFLOW step 3's "Always read
back user provided value and ask 'Is that correct?'" in the system
instruction -- two per-field read-back orders, so Gemini double-read. The
policy strings are now prefixed "When ALL fields in this section are
confirmed:" and the duplicate per-field sentence is removed; the block is
unambiguously end-of-section. Note: section 2 receives the same policy text
as section 1 (both are `section_number <= 2`); the maintainer happened to
observe the double-read only in section 1 -- the fix covers both. Static
analysis only; live double-read disappearance still needs a demo pass.

3625: both SYSTEM_INSTRUCTION and JIT_SYSTEM_INSTRUCTION (backend/config.py)
gain a 4-line ADDRESS CONSISTENCY block: after filling any address-cluster
field, cross-check state/zip/province/country coherence with world knowledge,
name the specific conflict, ask the user to verify both fields, accept their
answer if they insist.

Fresh-eyes triage breakdown: recorded in the PR merge ping (assess loop run
pre-PR per closeout Step 5.5).

## Lessons

Prompt directives have scope (per-field vs end-of-section); when the same
imperative appears at two scopes the model executes both. Keep each behavior
ordered in exactly one place, and label blocks with their scope ("When ALL
fields...") instead of relying on section-header context.

## Doc freshness

No tier-2 doc quotes the confirmation-policy or system-instruction text
(grep: "Confirm each field" / "ADDRESS CONSISTENCY" -- zero doc hits). Docs
flagged stale by the checker track files this branch did not change
(worktree-creation mtime noise); reviewed and left.

## Files touched

- backend/config.py -- ADDRESS CONSISTENCY block in both instruction
  templates (3625).
- backend/services/ai_context.py -- end-of-section scoping + dedup of the
  per-field read-back in get_confirmation_policy (yn6q).
- docs/journal/entries/2026-06-12-bd-yn6q-3625-readback-dedup-address-consistency.md
  -- this entry.
