---
date: 2026-08-03
bead: polyglot-pdf-xfdb
title: "Sprint-18 C12: lint message copy pass -- plain language, verified consequence, named remedy"
tags: [schema-editor, lint, guidance, translation]
---

## Trigger

First child of the sprint-18 editor-UX epic (polyglot-pdf-4qul, plan
docs/sprint_18_editor-ux-overhaul_plan.md, decision 12). Maintainer
directives from the 2026-08-02/03 hands-on sessions: no jargon ("no one
knows what deixis means"), every warning must say what to DO, and any
stated consequence must be true ("is the 500-char limit blocking? what
happens?"). Ordered FIRST in the chain so message text is stable before
C1's seen-fingerprints ship.

## What shipped

Every user-facing lint/flag message rewritten to state (a) what happened,
(b) the verified consequence, (c) the action -- across
backend/services/schema_lint.py (~49 emission sites),
translation_lint.py, translation_verify.py, option_translation.py, and
scripts/authoring/enrich_instructions.py (persisted flag templates). No
rule id, severity, path shape, or emission condition changed; the
[identity:<sha1>] path contract is byte-identical. ValidationPanel gained
refreshed RULE_LABELS plus a new exported RULE_REMEDIES map (one
imperative sentence per rule; consumed by C1 later). The
checkFieldComplete-vs-lint mapping table is committed (the companion entry
2026-08-03-bd-xfdb-rule-message-tables.md).

Two verified-consequence rewrites worth recording:

- help-instructions-too-long: INSTRUCTIONS_HARD_CHARS=500 is LINT-ONLY.
  ai_context.py (line 88) and manifest_service.py pass help.instructions
  through WHOLE -- nothing truncates; the text rides into the model
  context on every ask and can be spoken aloud in full. The message now
  says exactly that (cost every turn, may be read aloud entirely,
  shorten + move depth to never-spoken Details).
- help-instructions-screen-ref: "deixis" is gone; the message names the
  actual pattern ("see page 7", "check the box below") and the fix.

Exit-criterion amendment (logged on the bead, not silent): criterion 3's
"twins added or explicitly mapped" widened to allow explicit DEFERRAL
with rationale -- the two choice-field PDF-mapping checks have no
backend twin because field-unbacked exempts choice types BY DESIGN;
inventing that rule is a C1/C4 design decision, not a copy-pass call.

## Lessons

- A warning's stated consequence must be traced before it is written:
  the old 500-char message implied a hard delivery bound that does not
  exist anywhere in the delivery path. Copy edits are correctness edits
  when the copy makes claims about runtime behavior.
- Message text is load-bearing test surface: 9 assertions across 8 files
  pinned old substrings. All updated allowlist-style (assert the
  sanctioned phrase), and one was mutation-verified (reverted the
  help-instructions-missing message, watched
  test_lint_missing_instructions_aggregates_and_respects_exclusions
  fail, restored).

## Verification

Backend full suite from the worktree: 2534 passed (incl. the new gate-cap and remedy-parity pins), 3 skipped, 3
deselected, exit 0. test_lint_rule_parity.py: 4 passed (RULE_LABELS
coverage intact, declaration shape preserved, and the new RULE_REMEDIES
map pinned to the same coverage -- Opus round 2). schema-editor vitest:
73 files / 1086 tests passed. tsc --noEmit clean.

## Doc freshness

No tier-1/tier-2 doc documents individual lint message text. The rule
CATALOGUE in schema_lint.py's module docstring was updated in place in the
fresh-eyes round-2 fix (the deixis line, the disproven spoken-ask-hint
claim); the details-overflow line there was already accurate. The sprint-18 plan doc rides this same PR (cherry-picked commit).

## Files touched

- backend/services/schema_lint.py -- all emission-site messages + docstring
- backend/services/translation_lint.py / translation_verify.py /
  option_translation.py -- flag message templates
- scripts/authoring/enrich_instructions.py -- guidance flag templates
- schema-editor/src/components/ValidationPanel.tsx -- RULE_LABELS refresh
  + new exported RULE_REMEDIES
- backend/tests/* + tests/* + ValidationPanel.test.tsx -- 9 allowlist
  assertion updates
- docs/journal/entries/2026-08-03-bd-xfdb-rule-message-tables.md -- rule->message + checkFieldComplete mapping tables
