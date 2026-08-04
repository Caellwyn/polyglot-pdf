---
date: 2026-08-03
bead: polyglot-pdf-xfdb
title: "Sprint-18 C12 reference tables: rule->message map + checkFieldComplete/lint mapping"
tags: [schema-editor, lint, reference]
---

# Sprint-18 C12 reference tables

Durable companion to 2026-08-03-bd-xfdb-lint-message-copy-pass.md. The
checkFieldComplete mapping table below carries the DEFERRED-with-rationale
decisions that sprint-18 children C1/C4 pick up -- do not delete.

bd polyglot-pdf-xfdb. Plan: docs/sprint_18_editor-ux-overhaul_plan.md,
decision 12 + the C12 bead entry.

## What changed

Rewrote every user-facing lint/flag message so a non-technical reviewer can
read (a) what happened, (b) the real consequence, and (c) what to do about
it, without touching any rule id, severity, path shape, or emission
condition:

- `backend/services/schema_lint.py` -- all ~49 `LintFinding(...)` emission
  sites (condition/operator/arity/reference checks, option-value hygiene,
  show-if cycles, PDF widget-claim checks, read-only/unlock checks, legacy
  trigger-side logic, required-top-level, to-review-pending, and the
  guidance-content rules: help-instructions-*, help-details-*).
- `backend/services/translation_lint.py` -- the mechanical per-string check
  messages (digits, masks, do-not-translate terms, script, wrong-language
  markers, glossary pins, empty-string) and the per-language coverage /
  unreadable-schema messages.
- `backend/services/translation_verify.py` -- the verify/rectify loop's
  persisted flag messages (rectified-clean, unresolved-after-bounded-
  rectify, verification-unavailable).
- `backend/services/option_translation.py` -- the ambiguous-source
  self-flag message (translator under-determined).
- `scripts/authoring/enrich_instructions.py` -- the guidance verify/rectify
  loop's persisted flag messages (judge-unavailable, ungrounded-dropped x3
  call sites, rectified x2 call sites).
- `schema-editor/src/components/ValidationPanel.tsx` -- refreshed several
  `RULE_LABELS` entries for clarity (kept short); added a new exported
  `RULE_REMEDIES: Record<string, string>` map, one imperative sentence per
  rule, not yet consumed anywhere (a later bead wires it into the embedded
  findings UI, C1).

Two mandatory specifics from the bead:

- `help-instructions-screen-ref`: no longer says "deixis" (a word nobody
  recognizes). New message: "the instructions say things like 'see page 7'
  or 'check the box below', which mean nothing when spoken aloud --
  rewrite them to say the actual requirement in words."
- `help-instructions-too-long`: rewritten to state the VERIFIED runtime
  consequence, traced through the code before writing the message:
  `INSTRUCTIONS_HARD_CHARS = 500` (backend/services/guidance_contract.py:66)
  is a LINT-ONLY bound -- nothing in the delivery path truncates at it.
  `backend/services/ai_context.py` builds the per-field guidance block with
  `f"Instructions: {guidance['instructions']}"` (line 88), passing
  `help.instructions` through WHOLE into the model's context on every ask
  of that field; `backend/services/manifest_service.py` similarly reads
  `help.instructions` verbatim into `field_info["description"]`. The
  assistant can therefore read the full text aloud EVERY time it asks,
  and it costs tokens on every turn -- not "truncated". New message: "these
  instructions are {N} characters, over the 500-character limit -- nothing
  gets cut off, but the assistant may read all of it out loud every time it
  asks this question, and it adds cost on every turn; shorten it to a quick
  spoken hint and move the extra depth into Details, which is never spoken
  aloud."

## Rule -> message summary (see the commit diff for exact text)

| Rule | What changed |
|---|---|
| unknown-operator | plain "not a recognized rule" + allowed list |
| value-arity | names what shape is actually needed per arity (none/list/scalar) |
| condition-malformed (multiple sites) | "rebuild it in the condition builder" instead of type-name jargon |
| composite-depth (x2 sites) | "pick one shape" / "flatten it" |
| ref-unresolved-field | "does not exist in this form -- pick a real field or delete the rule" |
| operator-trigger (x2 sites) | names the field type plainly, gives the fix |
| ref-option-value | "not one of the answer choices ... pick one of its real choices" |
| option-value-missing | "no stored value -- set one" |
| option-value-comma | "breaks multi-select answers spoken aloud -- remove the comma" |
| option-value-slug | states the required format plainly |
| option-value-duplicate | "give each answer choice its own unique value" |
| show-if-cycle | "none of them can ever resolve ... break the loop" |
| dump-widget-multiclaim (x2 sites) | "filling it will misbehave -- unclaim it from all but one" |
| dump-widget-unclaimed | "can never be filled in -- add a field for it" |
| field-unbacked | "an answer here can never be written to the form ... connect it" |
| field-claim-unresolvable | "no box with that name exists ... reconnect it" |
| readonly-conditional-no-unlock | "once it appears, no one can ever fill it in" |
| unlock-missing-flag-change | "the filled PDF will silently stay locked" |
| legacy-trigger-side-logic | "that behavior is silently lost; rebuild it as show_if / require_if" |
| required-top-level | "nothing actually enforces it ... will silently accept it left blank" |
| to-review-pending (x2 sites) | "waiting for a human to decide where it belongs" |
| help-details-no-reference-floor (x2 sites) | "cannot be verified as accurate -- add the booklet text" |
| help-details-not-contained (x2 sites) | "must be copied word-for-word from the booklet, never paraphrased" |
| help-instructions-missing | "the assistant will ask about them with no help text at all" |
| help-instructions-too-long | VERIFIED consequence, see above |
| help-instructions-label-restatement | "adds anything -- or clear it and leave it empty" |
| help-instructions-screen-ref | no "deixis", see above |
| help-details-oversize | "text past that point is invisible to it in the moment" |
| help-details-headings-missing | "no one can scan it or jump to a section" |
| guidance-identity-stale | already plain; unchanged |
| translation-mechanical (empty/digits/masks/dnt/script/wrong-language/pins) | dropped the internal `check-id:` prefix jargon, plain consequence + fix per check |
| translation-coverage | "a {lang} session will hear the ENGLISH text instead" (kept the pinned "covers N/M" + "ENGLISH" test substrings) |
| translation-ambiguous-source | "could not tell what this English text means without more context" |
| translation-drift-rectified / translation-drift-unresolved | "review the correction" / "a human needs to review and correct it by hand" |
| instructions-enrich-unavailable | "no guidance text was written for this form at all" |
| instructions-ungrounded-dropped (x3 sites) | each names the actual reason (no supported guidance / never checked / failed a safety check) |
| instructions-rectified (x2 sites) | "check the correction reads right" / "worth rewriting to add real substance" |

## checkFieldComplete structural-check -> backend-lint-rule mapping

`schema-editor/src/utils/validation.ts`'s `checkFieldComplete` pushes into
its `errors` array (the band that flips a field's `isComplete` to false)
in exactly five places:

| # | Check (validation.ts) | Message | Backend lint twin | Note |
|---|---|---|---|---|
| 1 | `!field.id` | "Missing field ID" | no twin | Structurally can't happen from the editor UI (id is assigned at field creation); schema_lint's `fields_by_id` build silently skips non-string ids rather than flagging them. Genuinely client-only: a malformed id would only arise from a hand-edited JSON import, which the editor's own load path already guards elsewhere. Not promoted -- no observed real-world path to trigger it, and inventing a backend rule for a client-load-time invariant would be scope creep. |
| 2 | `!field.type` | "Missing field type" | no twin | Same reasoning as #1 -- FormField's type is required by the TS type system on every construction path in the editor; nothing in schema_lint checks for a missing `type` key because the Pydantic v2 model layer (a separate validator, not schema_lint) already rejects it on publish. Recorded as "no twin -- deferred to C1/C4 decision" per the conservative instruction, since promoting it would require deciding whether schema_lint should duplicate model-layer structural validation. |
| 3 | choice field, no field-level name, ALL options unmapped | "No PDF mapping: neither the field nor its options name a PDF widget" | PARTIAL twin: `field-unbacked` does NOT cover this (choice types are in `FIELD_LEVEL_NAME_EXEMPT_TYPES`, by design -- identity lives per-option). The dump-gated `dump-widget-unclaimed` / `field-claim-unresolvable` rules would catch the underlying PDF-widget gap, but ONLY when a dump is loaded (mark-complete gate, not the dumpless POST /lint). | Genuine gap on the dump-less path: a fresh choice field with zero PDF mapping at all lints clean until a dump is loaded. This is exactly the kind of "genuinely structural, no backend twin" case the bead calls out -- but per "be conservative", NOT promoted here: it needs a dump-less, per-option "does ANY of {field, options[]} carry a pdf_field_name" check, which is a new rule shape, not a copy of an existing one, and deciding its severity/scope is a real design call. Recorded as "no twin -- deferred to C1/C4 decision." |
| 4 | choice field, no field-level name, SOME options unmapped | "Options missing a PDF widget mapping: {names}" | same partial-twin situation as #3 | Same reasoning; deferred alongside #3. |
| 5 | non-choice field, no `pdf_field_name` | "Missing PDF field name" | `field-unbacked` (ERROR, `backend/services/schema_lint.py` `_check_field_backing`) -- fires for exactly this case: `source=pdf`, type outside `FIELD_LEVEL_NAME_EXEMPT_TYPES`, no `pdf_field_name` at all. | Real twin. Already an ERROR-class backend rule; no promotion needed. |

Conservative call: checks #1 and #2 are client-load-time invariants with no
observed real-world trigger path (not "genuinely structural" defects a
saved kit can carry) -- not promoted. Checks #3/#4 ARE a genuine structural
gap with no backend twin on the dump-less path, but designing the new
dump-less per-option coverage rule is a real scope/severity decision, not
a mechanical copy of an existing rule -- deferred to C1/C4 rather than
invented here per the bead's conservatism instruction. Check #5 already has
a real backend twin (`field-unbacked`) and needed no change.

No new backend lint rule was added by this bead.

`validateSchema`'s separate errors (duplicate field id, dangling
section/field references) were also reviewed for completeness even though
outside `checkFieldComplete`'s errors band specifically: "Duplicate field
ID" and "References non-existent section" have no backend schema_lint twin
either, for the same client-load-time-invariant reasoning as #1/#2 above;
not in scope for this bead's mapping (the bead named `checkFieldComplete`
specifically) and not promoted.

## Mutation-verify

Target: `backend/tests/unit/test_guidance_contract.py::test_lint_missing_instructions_aggregates_and_respects_exclusions`,
which pins the updated `help-instructions-missing` message text (asserts
`"1 of 2 fields" in hits[0].message`).

1. Confirmed green on the current code: `1 passed in 0.21s`.
2. Reverted `backend/services/schema_lint.py`'s aggregated message back to
   the pre-C12 wording ("1 of 2 askable fields have no help.instructions
   ..."), leaving the test assertion (which now expects "1 of 2 fields")
   untouched.
3. Re-ran the same test -- it FAILED as expected:
   `AssertionError: assert ('1 of 2 fields' in '1 of 2 askable fields have
   no help.instructions (a) -- ...')`. This proves the test actually pins
   the new phrasing and would catch a message regression, not just the
   rule id.
4. Restored the fixed wording and re-ran -- back to `1 passed in 0.15s`.

## Test results

- Backend full suite (`PYTHONPATH=<worktree> ... pytest -m "not external" -q`,
  run from the worktree root, venv from the main repo):
  `2530 passed, 3 skipped, 3 deselected` in 308s, exit code 0.
- `backend/tests/unit/test_lint_rule_parity.py` (RULE_LABELS parity + the
  guidance-staleness rule-id pin): `3 passed`.
- Frontend vitest (`node node_modules/vitest/vitest.mjs run --reporter=dot`,
  foreground, via a junction to the main repo's `schema-editor/node_modules`):
  `73 test files passed, 1086 tests passed` in ~21s.
- `node node_modules/typescript/bin/tsc --noEmit -p tsconfig.json`: no
  output, exit code 0.

Seven backend test failures surfaced on the first full-suite run, all from
tests pinning the OLD message text verbatim (allowlist substrings that
matched the exact old wording); each was updated to assert the new
sanctioned phrase rather than loosened into a blacklist:
- `test_schema_lint.py::test_unknown_operator_trips_once` --
  `"allowed:"` -> `"change it to one of:"`.
- `test_translation_lint.py::test_lint_kit_schema_flags_and_skips` --
  `"wrong-script"` -> `"no cyrillic-alphabet characters"` (also corrected
  a wrong guess of "russian" vs the actual script name "cyrillic").
- `test_translation_lint.py::test_lint_kits_unreadable_schema_fail_open` --
  `"unreadable schema"` -> `"could not be read"`.
- `test_translation_verify.py::test_mechanical_failure_skips_judge_on_the_way_in`
  -- `"dnt-violated"` -> `"supposed to stay in English"`.
- `tests/test_enrich_instructions.py::test_judge_omission_drops_field` --
  `"omitted"` -> `"never quality-checked"`.
- `tests/test_enrich_instructions.py::test_rectify_to_empty_flags_as_dropped`
  -- `"rectifier emptied"` -> `"no guidance could be written"`.
- `tests/test_translate_option_labels_cli.py::test_flags_block_and_artifact`
  -- `"under-determined"` -> `"could not tell what this English text means"`
  (both the console-must-NOT-show and the artifact-DOES-carry assertions
  updated together, preserving the cp1252-safety test intent).

Two frontend test failures in `ValidationPanel.test.tsx` from tests
hard-coding old `RULE_LABELS` display strings in their own mock fixtures
(not backend-sourced): `'Unknown operator'` -> `'Unrecognized comparison'`,
`'Translation drift (needs human review)'` -> `'Translation needs human
review'`.

No rule id, severity, path shape, or emission condition changed anywhere;
only message/label text and (in ValidationPanel.tsx) some RULE_LABELS
values plus the new RULE_REMEDIES export.
